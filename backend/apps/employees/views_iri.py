"""
Vues pour la gestion des paiements IRI (Impôt sur les Revenus Intermittents)

Workflow :
1. Récupération des transactions DiameX avec préfixe ISI pour le mois
2. Parsing des descriptions ISI pour extraire les informations
3. Regroupement par Activ avec sous-totaux
4. Génération de la facture Excel selon le modèle
5. Export vers DiameXTemporaire (une ligne par Activ, Cat=631104)
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.utils import timezone
from decimal import Decimal
import json
import re

from apps.employees.models import PaiementIRI, PaiementIRIDetail
from apps.organization.models import Organisation
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.accounting.models import DiameXTemporaire, BaseDiameX
from apps.billing.models import Fournisseur


def _get_accessible_paiements_iri_queryset(user):
    queryset = PaiementIRI.objects.select_related('organisation')
    allowed_org_ids = get_user_accessible_gestionnaire_ids(user)
    if allowed_org_ids is None:
        return queryset
    if not allowed_org_ids:
        return queryset.none()
    return queryset.filter(organisation_id__in=allowed_org_ids)


def paiements_iri_liste(request):
    """
    Page principale de gestion des paiements IRI
    Filtre automatiquement par l'organisation de l'utilisateur connecté
    """
    # Récupérer l'organisation de l'utilisateur connecté
    user_organisation = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.poste:
            user_organisation = request.user.employe.poste.organisation

    # Années disponibles (de 2020 à année courante + 1)
    from datetime import datetime
    annee_courante = datetime.now().year
    annees = list(range(2020, annee_courante + 2))

    context = {
        'user_organisation': user_organisation,
        'annees': annees,
        'annee_courante': annee_courante,
    }

    return render(request, 'employees/paiements_iri_liste.html', context)


def api_paiements_iri_list(request):
    """
    API pour récupérer la liste des paiements IRI avec filtres
    """

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Non authentifié'}, status=401)

    annee = request.GET.get('annee')
    mois = request.GET.get('mois')
    organisation_id = request.GET.get('organisation_id')

    paiements = _get_accessible_paiements_iri_queryset(request.user)

    # Filtres supplémentaires
    if annee:
        paiements = paiements.filter(annee=int(annee))
    if mois:
        paiements = paiements.filter(mois=int(mois))
    if organisation_id:
        paiements = paiements.filter(organisation_id=organisation_id)

    # Statistiques
    total_montant_iri = paiements.aggregate(total=Sum('montant_total_iri'))['total'] or Decimal('0')
    total_montant_achats = paiements.aggregate(total=Sum('montant_total_achats'))['total'] or Decimal('0')
    nb_activ = paiements.values('organisation').distinct().count()

    # Convertir en liste
    paiements_list = []
    for p in paiements:
        nb_transactions = p.details.count()
        paiements_list.append({
            'id': str(p.id),
            'annee': p.annee,
            'mois': p.mois,
            'organisation': p.organisation.nom_organisation,
            'organisation_id': str(p.organisation_id),
            'nb_transactions': nb_transactions,
            'montant_total_achats': float(p.montant_total_achats),
            'montant_total': float(p.montant_total_iri),
            'statut': p.statut,
        'facture_generee': p.facture_generee,
        })

    return JsonResponse({
        'success': True,
        'paiements': paiements_list,
        'stats': {
            'total': len(paiements_list),
            'montant_total_iri': float(total_montant_iri),
            'montant_total_achats': float(total_montant_achats),
            'nb_activ': nb_activ,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_generer_paiement_iri(request):
    """
    API pour générer un paiement IRI à partir des transactions DiameX ISI

    Workflow:
    1. Récupère les transactions DiameX avec description commençant par "ISI_" ou "_ISI"
    2. Parse les descriptions pour extraire les informations
    3. Calcule le montant IRI (5% du montant OUT)
    4. Crée le paiement avec ses détails
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Non authentifié'}, status=401)

    try:
        annee = int(request.POST.get('annee'))
        mois = int(request.POST.get('mois'))
        organisation_id = request.POST.get('organisation_id')

        if not organisation_id:
            return JsonResponse({
                'success': False,
                'error': 'Organisation requise'
            }, status=400)

        organisation = Organisation.objects.get(id=organisation_id)

        # Vérifier si un paiement existe déjà pour ce mois/année/organisation
        existing = PaiementIRI.objects.filter(
            organisation=organisation,
            mois=mois,
            annee=annee
        ).first()

        if existing:
            return JsonResponse({
                'success': False,
                'error': f'Un paiement IRI existe déjà pour {organisation.nom_organisation} - {mois}/{annee}'
            }, status=400)

        # Récupérer toutes les transactions DiameX avec préfixe ISI
        # Critères: Description commence par "ISI" ET compte_code est un nombre
        transactions = BaseDiameX.objects.filter(
            Q(description__istartswith='ISI_') | Q(description__istartswith='_ISI') | Q(description__istartswith='ISI ')
        ).exclude(
            compte_code__isnull=True
        ).exclude(
            compte_code=''
        )

        # Filtrer par mois/année ET compte_code numérique
        # Note: date_m peut être None, donc on filtre en Python après
        transactions_mois = []
        for t in transactions:
            # Vérifier que compte_code est un nombre (pas "00PERS" ou autre texte)
            if t.compte_code and t.compte_code.isdigit():
                if t.date_m:
                    if t.date_m.year == annee and t.date_m.month == mois:
                        transactions_mois.append(t)

        if len(transactions_mois) == 0:
            return JsonResponse({
                'success': False,
                'error': f'Aucune transaction ISI trouvée pour {organisation.nom_organisation} en {mois}/{annee}'
            }, status=400)

        # Créer le paiement IRI
        paiement = PaiementIRI.objects.create(
            organisation=organisation,
            mois=mois,
            annee=annee,
            statut='brouillon',
            created_by=request.user
        )

        # Créer les détails à partir des transactions
        total_achats = Decimal('0')
        total_iri = Decimal('0')
        nb_details = 0

        for transaction in transactions_mois:
            # Montant de l'achat (OUT de la transaction)
            # Convertir en Decimal pour les calculs précis
            montant_achat = Decimal(str(transaction.montant_out)) if transaction.montant_out else Decimal('0')

            # Calcul IRI : 5% du montant
            montant_iri = montant_achat * Decimal('0.05')

            # Parser la description ISI
            # Format attendu: ISI_[Fournisseur]_[Libellé]_[Unité]_[Prix]_[Reste]
            # Exemples:
            # - "ISI_NIAINA CASH POINT_Frais Mvola_Fft_2000_Ar pour Mamiratra"
            # - "ISI_JAONAH_Boîte métallique_U_45000_x 20 pour stock"
            description = transaction.description or ''
            parts = description.strip('_').split('_')

            fournisseur_nom = parts[1] if len(parts) > 1 else 'Inconnu'
            libelle = parts[2] if len(parts) > 2 else description
            unite = parts[3] if len(parts) > 3 else None

            # Extraire le prix unitaire (4ème élément après le split)
            prix_unitaire = Decimal('0')
            if len(parts) > 4:
                try:
                    # Le prix peut contenir des chiffres avec ou sans virgule
                    prix_str = parts[4].replace(',', '').strip()
                    # Extraire les chiffres uniquement
                    prix_match = re.search(r'\d+', prix_str)
                    if prix_match:
                        prix_unitaire = Decimal(prix_match.group())
                except (ValueError, IndexError):
                    prix_unitaire = Decimal('0')

            # Le reste du texte (à partir du 5ème élément)
            reste = '_'.join(parts[5:]) if len(parts) > 5 else ''

            # Rechercher le fournisseur dans la table Fournisseur pour récupérer CIN et adresse
            # Utiliser la colonne 'fournisseur' de DiameX (ID Excel) pour lier à 'idxls' dans Fournisseurs
            fournisseur_cin = None
            fournisseur_adresse = None
            fournisseur_obj = None
            try:
                # Méthode 1: Utiliser la colonne 'fournisseur' de la transaction DiameX
                # qui contient l'ID Excel (idxls) du fournisseur (stocké comme chaîne)
                if transaction.fournisseur:
                    # Essayer de convertir en entier si c'est un ID numérique
                    try:
                        fournisseur_id = int(transaction.fournisseur)
                        fournisseur_obj = Fournisseur.objects.filter(
                            idxls=fournisseur_id
                        ).first()
                    except (ValueError, TypeError):
                        # Si ce n'est pas un nombre, c'est peut-être un nom
                        fournisseur_obj = Fournisseur.objects.filter(
                            nom_fournisseur__iexact=transaction.fournisseur
                        ).first()

                # Méthode 2 (fallback): Si pas trouvé par ID, essayer par nom de la description
                if not fournisseur_obj:
                    fournisseur_nom_clean = fournisseur_nom.strip()

                    # Recherche exacte (insensible à la casse)
                    fournisseur_obj = Fournisseur.objects.filter(
                        nom_fournisseur__iexact=fournisseur_nom_clean
                    ).first()

                    # Si toujours pas trouvé, recherche partielle
                    if not fournisseur_obj:
                        fournisseur_obj = Fournisseur.objects.filter(
                            nom_fournisseur__icontains=fournisseur_nom_clean
                        ).first()

                # Récupérer CIN et adresse si fournisseur trouvé
                if fournisseur_obj:
                    fournisseur_cin = fournisseur_obj.cin
                    fournisseur_adresse = fournisseur_obj.adresse
            except Exception:
                pass  # Si erreur, on continue avec None

            # Créer le détail
            PaiementIRIDetail.objects.create(
                paiement=paiement,
                id_access_source=transaction.id_access if hasattr(transaction, 'id_access') else None,
                numero_diamex_source=str(transaction.rec) if transaction.rec else '',
                base_diamex_source=transaction.prog or '',
                fournisseur_nom=fournisseur_nom,
                fournisseur_cin=fournisseur_cin,
                fournisseur_adresse=fournisseur_adresse,
                libelle=libelle,
                unite=unite,
                prix_unitaire=prix_unitaire,
                montant_achat=montant_achat,
                montant_iri=montant_iri,
                date_achat=transaction.date_rec,
                activ=transaction.activ or ''
            )

            total_achats += montant_achat
            total_iri += montant_iri
            nb_details += 1

        # Mettre à jour les totaux du paiement
        paiement.montant_total_achats = total_achats
        paiement.montant_total_iri = total_iri
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': f'Paiement IRI généré avec succès',
            'paiement_id': str(paiement.id),
            'nb_transactions': nb_details,
            'montant_total': float(total_iri),
            'montant_achats': float(total_achats)
        })

    except Organisation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Organisation introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_paiement_iri_detail(request, paiement_id):
    """
    API pour récupérer les détails d'un paiement IRI
    """

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Non authentifié'}, status=401)
    try:
        paiement = _get_accessible_paiements_iri_queryset(request.user).select_related(
            'created_by'
        ).get(id=paiement_id)

        # Récupérer les détails
        details = paiement.details.all().order_by('fournisseur_nom')

        details_list = []
        for d in details:
            details_list.append({
                'id': str(d.id),
                'id_access_source': d.id_access_source or '',
                'numero_diamex_source': d.numero_diamex_source or '',
                'base_diamex_source': d.base_diamex_source or '',
                'fournisseur_nom': d.fournisseur_nom,
                'fournisseur_cin': d.fournisseur_cin or '',
                'fournisseur_adresse': d.fournisseur_adresse or '',
                'libelle': d.libelle,
                'unite': d.unite or '',
                'prix_unitaire': float(d.prix_unitaire) if d.prix_unitaire else 0,
                'activ': d.activ,
                'montant_achat': float(d.montant_achat),
                'montant_iri': float(d.montant_iri),
                'date_achat': d.date_achat.strftime('%d/%m/%Y') if d.date_achat else '',
            })

        return JsonResponse({
            'success': True,
            'paiement': {
                'id': str(paiement.id),
                'organisation': paiement.organisation.nom_organisation,
                'mois': paiement.mois,
                'annee': paiement.annee,
                'periode_label': paiement.periode_label,
                'statut': paiement.statut,
                'montant_total_achats': float(paiement.montant_total_achats),
                'montant_total_iri': float(paiement.montant_total_iri),
                'facture_generee': paiement.facture_generee,
                'created_at': paiement.created_at.strftime('%d/%m/%Y %H:%M'),
                'created_by': paiement.created_by.get_full_name() if paiement.created_by else '',
            },
            'details': details_list
        })

    except PaiementIRI.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRI introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_paiement_iri(request, paiement_id):
    """
    Supprime un paiement IRI et tous ses détails
    """

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Non authentifié'}, status=401)
    try:
        paiement_qs = _get_accessible_paiements_iri_queryset(request.user).filter(id=paiement_id)
        paiement = paiement_qs.get()

        # Interdire la suppression uniquement si déjà exporté vers DiameX
        if paiement.statut == 'exporte':
            return JsonResponse({
                'success': False,
                'error': 'Un paiement exporté ne peut plus être supprimé'
            }, status=400)

        # Compter le nombre de détails
        nb_details = paiement.details.count()

        # Supprimer le paiement (cascade supprimera les détails)
        periode = paiement.periode_label
        paiement.delete()

        return JsonResponse({
            'success': True,
            'message': f'Paiement IRI "{periode}" supprimé avec succès ({nb_details} ligne(s) supprimée(s))'
        })

    except PaiementIRI.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRI introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_valider_paiement_iri(request, paiement_id):
    """
    API pour valider un paiement IRI (passer de brouillon à validé)
    """

    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Non authentifié'}, status=401)
    try:
        paiement_qs = _get_accessible_paiements_iri_queryset(request.user).filter(id=paiement_id)
        paiement = paiement_qs.get()

        # Vérifier que le paiement est en brouillon
        if paiement.statut != 'brouillon':
            return JsonResponse({
                'success': False,
                'error': f'Ce paiement est déjà {paiement.statut}'
            }, status=400)

        # Vérifier qu'il y a au moins un détail
        if not paiement.details.exists():
            return JsonResponse({
                'success': False,
                'error': 'Impossible de valider un paiement sans transactions'
            }, status=400)

        # Valider le paiement
        paiement.statut = 'valide'
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': f'Paiement IRI validé avec succès ({paiement.details.count()} transactions)'
        })

    except PaiementIRI.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRI introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
