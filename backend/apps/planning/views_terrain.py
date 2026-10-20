"""
Views pour le workflow de traitement des activités sur le terrain par les agents
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, models
from django.utils import timezone
from decimal import Decimal
import json

from .models import Planning, PlanningDetail, Designation, DesignationCompte, BonLivraison
from apps.billing.models import Fournisseur
from apps.organization.models import Organisation, Compte
from apps.geography.models import Village


@login_required
def traiter_activite(request, planning_id):
    """
    Vue principale pour traiter une activité sur le terrain
    Affiche les bons de livraison (table BonLivraison) et les avances (table PlanningDetail)
    """
    planning = get_object_or_404(Planning.objects.select_related(
        'employe', 'employe__base', 'employe__base__organisation', 'activite', 'ouvrage'
    ), id=planning_id)

    # Récupérer les bons de livraison depuis la nouvelle table BonLivraison
    bons_livraison = list(BonLivraison.objects.filter(
        planning=planning,
        utilise=False,  # Pas encore utilisé par l'agent
        retour=False  # Pas retourné
    ).select_related(
        'designation', 'point_eau', 'equipement', 'photo_justificatif'
    ).order_by('designation__nom'))

    # Récupérer les avances depuis PlanningDetail
    details_avances = list(PlanningDetail.objects.filter(
        planning=planning,
        designation__type_avance_caissiere='Avance',
        utilise=False,  # Pas encore utilisé
        retour=False  # Pas retourné
    ).select_related(
        'designation', 'designation__type_designation', 'fournisseur'
    ).order_by('designation__nom'))

    # Récupérer la liste des fournisseurs liés à l'ouvrage (par adresse)
    fournisseurs = []
    if planning.ouvrage:
        # Fournisseurs liés directement à l'ouvrage via adresse_relation
        fournisseurs = Fournisseur.objects.filter(
            adresse_relation__ouvrage=planning.ouvrage,
            actif=True
        ).distinct()

        # Si aucun fournisseur trouvé, récupérer tous les fournisseurs actifs
        if not fournisseurs.exists():
            fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')[:20]

    context = {
        'planning': planning,
        'bons_livraison': bons_livraison,
        'details_avances': details_avances,
        'fournisseurs': fournisseurs,
        'title': f'Traiter activité - {planning.activite.nom if planning.activite else "N/A"}',
    }

    return render(request, 'planning/traiter_activite.html', context)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def marquer_utilise_livraisons(request):
    """
    Marquer plusieurs bons de livraison comme utilisés en une seule fois
    Génère un seul numéro de bon de livraison pour toutes les lignes
    UTILISE LA TABLE BonLivraison (pas PlanningDetail)
    """
    try:
        from .utils import generer_numero_bon

        # Récupérer les IDs (séparés par des virgules)
        bon_ids_str = request.POST.get('detail_ids', '')
        if not bon_ids_str:
            return JsonResponse({
                'success': False,
                'error': 'Aucune livraison sélectionnée'
            }, status=400)

        bon_ids = [id.strip() for id in bon_ids_str.split(',') if id.strip()]

        if not bon_ids:
            return JsonResponse({
                'success': False,
                'error': 'Liste d\'IDs vide'
            }, status=400)

        # Récupérer tous les bons de livraison
        bons = BonLivraison.objects.filter(id__in=bon_ids)

        if not bons.exists():
            return JsonResponse({
                'success': False,
                'error': f'Aucun bon de livraison trouvé avec les IDs fournis: {bon_ids_str}'
            }, status=404)

        # Générer un seul numéro de bon pour toutes les lignes
        numero_bon = generer_numero_bon('livraison')

        # Marquer tous les bons comme utilisés
        bons_updated = []
        for bon in bons:
            bon.utilise = True
            bon.date_utilisation = timezone.now()
            bon.numero_bon = numero_bon
            bon.save()

            bons_updated.append({
                'id': str(bon.id),
                'designation': bon.designation.nom if bon.designation else 'N/A',
                'quantite': bon.quantite,
                'magasin': bon.magasin or 'N/A',
            })

        return JsonResponse({
            'success': True,
            'message': f'{len(bons_updated)} livraison(s) marquée(s) comme utilisée(s)',
            'numero_bon': numero_bon,
            'bons_updated': bons_updated
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def marquer_utilise_avances(request):
    """
    Marquer plusieurs avances comme utilisées en une seule fois
    Génère un seul numéro de bon d'avance pour toutes les lignes
    Supporte la mise à jour des quantités, prix et fournisseur
    """
    try:
        from .utils import generer_numero_bon

        # Récupérer les IDs (séparés par des virgules)
        detail_ids_str = request.POST.get('detail_ids', '')
        if not detail_ids_str:
            return JsonResponse({
                'success': False,
                'error': 'Aucune avance sélectionnée'
            }, status=400)

        detail_ids = [id.strip() for id in detail_ids_str.split(',') if id.strip()]

        if not detail_ids:
            return JsonResponse({
                'success': False,
                'error': 'Liste d\'IDs vide'
            }, status=400)

        # Récupérer les données mises à jour (si fournies)
        lignes_data_str = request.POST.get('lignes_data', '')
        lignes_data = {}
        if lignes_data_str:
            try:
                lignes_list = json.loads(lignes_data_str)
                # Créer un dictionnaire {id: ligne_data}
                lignes_data = {ligne['id']: ligne for ligne in lignes_list}
            except json.JSONDecodeError:
                pass

        # Récupérer tous les détails
        details = PlanningDetail.objects.filter(id__in=detail_ids)

        if not details.exists():
            return JsonResponse({
                'success': False,
                'error': f'Aucune avance trouvée avec les IDs fournis: {detail_ids_str}'
            }, status=404)

        # Vérifier que ce sont bien des avances
        for detail in details:
            if not (detail.designation and detail.designation.type_avance_caissiere == 'Avance'):
                return JsonResponse({
                    'success': False,
                    'error': f'Le détail {detail.id} n\'est pas une avance'
                }, status=400)

        # Récupérer le fournisseur et compte (optionnel)
        fournisseur_id = request.POST.get('fournisseur_id', '')
        compte_id = request.POST.get('compte', '')

        fournisseur_obj = None
        fournisseur_nom = ''
        if fournisseur_id:
            try:
                fournisseur_obj = Fournisseur.objects.get(id=fournisseur_id)
                fournisseur_nom = fournisseur_obj.nom_fournisseur
            except Fournisseur.DoesNotExist:
                pass

        compte_obj = None
        compte_nom = ''
        if compte_id:
            try:
                compte_obj = Compte.objects.get(id=compte_id)
                compte_nom = compte_obj.nom_compte
            except Compte.DoesNotExist:
                pass

        # Générer un seul numéro de bon pour toutes les lignes
        numero_bon = generer_numero_bon('avance')

        # Marquer toutes les avances comme utilisées
        details_updated = []
        for detail in details:
            detail_id_str = str(detail.id)

            # Mettre à jour avec les nouvelles valeurs si fournies
            if detail_id_str in lignes_data:
                ligne = lignes_data[detail_id_str]
                detail.quantity = Decimal(str(ligne.get('quantity', detail.quantity)))
                detail.pu = Decimal(str(ligne.get('pu', detail.pu)))
                detail.montant = detail.quantity * detail.pu

            # Mettre à jour fournisseur et compte
            if fournisseur_obj:
                detail.fournisseur = fournisseur_obj
            if compte_obj:
                detail.compte = compte_obj

            detail.utilise = True
            detail.date_utilisation = timezone.now()
            detail.numero_bon_avance = numero_bon
            detail.save()

            details_updated.append({
                'id': str(detail.id),
                'designation': detail.designation.nom if detail.designation else 'N/A',
                'quantity': float(detail.quantity),
                'pu': float(detail.pu) if detail.pu else 0,
                'montant': float(detail.montant) if detail.montant else 0,
            })

        return JsonResponse({
            'success': True,
            'message': f'{len(details_updated)} avance(s) marquée(s) comme utilisée(s)',
            'numero_bon': numero_bon,
            'details_updated': details_updated,
            'fournisseur': fournisseur_nom,
            'compte': compte_nom
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST", "GET"])
def verifier_bon_qrcode(request):
    """
    API pour scanner un QR Code et vérifier un bon de livraison/avance
    Utilisé par la caissière pour valider les bons
    """
    try:
        # Récupérer le numéro de bon (depuis le QR Code)
        numero_bon = request.GET.get('numero_bon') or request.POST.get('numero_bon')

        if not numero_bon:
            return JsonResponse({
                'success': False,
                'error': 'Numéro de bon manquant'
            }, status=400)

        # Chercher le bon dans les PlanningDetail
        details = PlanningDetail.objects.filter(numero_bon_livraison=numero_bon)

        if not details.exists():
            # Chercher aussi dans les bons d'avance
            details = PlanningDetail.objects.filter(numero_bon_avance=numero_bon)

        if not details.exists():
            return JsonResponse({
                'success': False,
                'error': f'Aucun bon trouvé avec le numéro {numero_bon}'
            }, status=404)

        # Préparer les informations du bon
        premier_detail = details.first()
        type_bon = 'Bon de livraison' if premier_detail.numero_bon_livraison == numero_bon else 'Bon d\'avance'

        lignes = []
        montant_total = 0

        for detail in details:
            lignes.append({
                'designation': detail.designation.nom if detail.designation else 'N/A',
                'quantity': detail.quantity,
                'utilise': detail.utilise,
                'date_utilisation': detail.date_utilisation.strftime('%d/%m/%Y %H:%M') if detail.date_utilisation else None,
            })

        return JsonResponse({
            'success': True,
            'bon': {
                'numero': numero_bon,
                'type': type_bon,
                'employe': premier_detail.planning.employe.nom_affichage if premier_detail.planning else 'N/A',
                'ouvrage': premier_detail.planning.ouvrage.nom_ouvrage if premier_detail.planning and premier_detail.planning.ouvrage else 'N/A',
                'date_creation': premier_detail.created_at.strftime('%d/%m/%Y %H:%M') if premier_detail.created_at else None,
                'statut': 'Utilisé' if premier_detail.utilise else 'En attente',
                'lignes': lignes,
                'nombre_lignes': len(lignes)
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def marquer_utilise_livraison(request, detail_id):
    """
    Marquer une livraison comme utilisée (avec photo optionnelle)
    Génère automatiquement un numéro de bon de livraison
    """
    try:
        from .utils import generer_numero_bon

        detail = get_object_or_404(PlanningDetail, id=detail_id)

        # Vérifier que c'est bien une livraison (via designation.type_avance_caissiere)
        if not (detail.designation and detail.designation.type_avance_caissiere == 'Bon de livraison'):
            return JsonResponse({
                'success': False,
                'error': 'Ce détail n\'est pas une livraison (type_avance_caissiere doit être "Bon de livraison")'
            }, status=400)

        # Marquer comme utilisé
        detail.utilise = True
        detail.date_utilisation = timezone.now()

        # Générer un numéro de bon de livraison si pas déjà fait
        if not detail.numero_bon_livraison:
            detail.numero_bon_livraison = generer_numero_bon('livraison')

        # Gérer l'upload de photo si présent
        if 'photo' in request.FILES:
            from apps.filemanager.models import FileUpload
            photo = request.FILES['photo']

            # Créer l'objet FileUpload
            file_upload = FileUpload.objects.create(
                file=photo,
                uploaded_by=request.user,
                file_type='image',
                description=f"Justificatif livraison - {detail.designation.nom}"
            )
            detail.photo_justificatif = file_upload

        detail.save()

        return JsonResponse({
            'success': True,
            'message': 'Livraison marquée comme utilisée',
            'numero_bon': detail.numero_bon_livraison,
            'detail': {
                'id': str(detail.id),
                'utilise': detail.utilise,
                'date_utilisation': detail.date_utilisation.isoformat() if detail.date_utilisation else None,
                'quantity': float(detail.quantity) if detail.quantity else 0,
                'pu': float(detail.pu) if detail.pu else 0,
                'montant': float(detail.montant) if detail.montant else 0
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def traiter_avance(request, detail_id):
    """
    Traiter une avance : modifier quantité/prix, ajouter fournisseur
    """
    try:
        detail = get_object_or_404(PlanningDetail, id=detail_id)

        # Vérifier que c'est bien une avance (via designation.type_avance_caissiere)
        if not (detail.designation and detail.designation.type_avance_caissiere == 'Avance'):
            return JsonResponse({
                'success': False,
                'error': 'Ce détail n\'est pas une avance (type_avance_caissiere doit être "Avance")'
            }, status=400)

        data = json.loads(request.body)

        with transaction.atomic():
            # Mettre à jour quantité et prix si fournis
            if 'quantity' in data and data['quantity']:
                detail.quantity = float(data['quantity'])

            if 'pu' in data and data['pu']:
                detail.pu = Decimal(str(data['pu']))

            # Recalculer le montant
            if detail.quantity and detail.pu:
                detail.montant = Decimal(str(detail.quantity)) * detail.pu

            # Gérer le fournisseur
            if 'fournisseur_id' in data and data['fournisseur_id']:
                fournisseur = get_object_or_404(Fournisseur, id=data['fournisseur_id'])
                detail.fournisseur = fournisseur
            elif 'nouveau_fournisseur' in data and data['nouveau_fournisseur']:
                # Créer un nouveau fournisseur
                nouveau = data['nouveau_fournisseur']
                fournisseur = Fournisseur.objects.create(
                    nom_fournisseur=nouveau.get('nom'),
                    telephone=nouveau.get('telephone', ''),
                    email=nouveau.get('email', ''),
                    numero_nif=nouveau.get('nif', ''),
                    numero_stat=nouveau.get('stat', '')
                )
                detail.fournisseur = fournisseur

            # Marquer comme utilisé
            detail.utilise = True
            detail.date_utilisation = timezone.now()

            # Générer un numéro de bon d'avance si pas déjà fait
            if not detail.numero_bon_avance:
                from .utils import generer_numero_bon
                detail.numero_bon_avance = generer_numero_bon('avance')

            detail.save()

        return JsonResponse({
            'success': True,
            'message': 'Avance traitée avec succès',
            'numero_bon': detail.numero_bon_avance,
            'detail': {
                'id': str(detail.id),
                'quantity': float(detail.quantity),
                'pu': float(detail.pu),
                'montant': float(detail.montant),
                'fournisseur': detail.fournisseur.nom_fournisseur if detail.fournisseur else None,
                'utilise': detail.utilise
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def traiter_paiement_forfaitaire(request, detail_id):
    """
    Traiter un paiement forfaitaire : collecter le paiement
    """
    try:
        detail = get_object_or_404(PlanningDetail, id=detail_id)

        data = json.loads(request.body)

        with transaction.atomic():
            # Mettre à jour la quantité si fournie
            if 'quantite' in data:
                quantite = Decimal(str(data['quantite']))
                detail.quantity = quantite

                # Recalculer le montant si PU existe
                if detail.pu:
                    detail.montant = detail.quantity * detail.pu

            # Mettre à jour le montant collecté si fourni (priorité au montant calculé ci-dessus)
            if 'montant_collecte' in data:
                montant_collecte = Decimal(str(data['montant_collecte']))
                detail.montant = montant_collecte

            # Mettre à jour le nom de l'abonné du point d'eau si fourni
            if 'nom_abonne' in data and data['nom_abonne'] and detail.point_eau:
                detail.point_eau.nomabonne = data['nom_abonne']
                detail.point_eau.save()

            # Marquer comme utilisé
            detail.utilise = True
            detail.date_utilisation = timezone.now()

            # Générer un numéro de facture si pas déjà fait
            if not detail.numero_facture:
                from .utils import generer_numero_bon
                detail.numero_facture = generer_numero_bon('facture')

            detail.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement collecté avec succès',
            'numero_facture': detail.numero_facture,
            'detail': {
                'id': str(detail.id),
                'montant': float(detail.montant),
                'utilise': detail.utilise,
                'point_eau': (detail.point_eau.idxls or detail.point_eau.code_point_eau or str(detail.point_eau.id)) if detail.point_eau else None,
                'nom_abonne': detail.point_eau.nomabonne if detail.point_eau else None
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def generer_facture_ticket(request):
    """
    Générer une facture au format ticket de caisse
    Pour plusieurs détails de planning avec le même fournisseur
    """
    detail_ids = request.GET.getlist('detail_ids[]')

    if not detail_ids:
        return HttpResponse('Aucun détail sélectionné', status=400)

    details = PlanningDetail.objects.filter(
        id__in=detail_ids
    ).select_related(
        'designation', 'fournisseur', 'planning__ouvrage'
    )

    # Vérifier que tous les détails ont le même fournisseur
    fournisseurs = set(d.fournisseur for d in details if d.fournisseur)
    if len(fournisseurs) > 1:
        return HttpResponse('Les détails doivent avoir le même fournisseur', status=400)

    fournisseur = fournisseurs.pop() if fournisseurs else None

    # Récupérer l'organisation
    organisation = Organisation.objects.first()  # Ou selon la base du planning

    # Calculer le total
    total = sum(d.montant for d in details)

    context = {
        'fournisseur': fournisseur,
        'organisation': organisation,
        'details': details,
        'total': total,
        'date': timezone.now(),
        'numero_facture': f"FACT-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    }

    # Marquer les factures comme imprimées
    details.update(facture_imprimee=True)

    return render(request, 'planning/facture_ticket.html', context)


@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def rechercher_fournisseurs(request):
    """
    Rechercher des fournisseurs par nom, contact ou adresse
    Accepte GET (autocomplétion) et POST (recherche avancée)
    """
    try:
        # Supporter GET et POST
        if request.method == 'GET':
            query = request.GET.get('q', '').strip()
            ouvrage_id = request.GET.get('ouvrage_id')
        else:
            data = json.loads(request.body)
            query = data.get('query', '').strip()
            ouvrage_id = data.get('ouvrage_id')

        fournisseurs_qs = Fournisseur.objects.all()

        if query:
            from django.db.models import Q
            fournisseurs_qs = fournisseurs_qs.filter(
                Q(nom_fournisseur__icontains=query) |
                Q(telephone__icontains=query) |
                Q(adresse__icontains=query)  # Champ texte libre de l'adresse
            )

        # Filtrer par proximité de l'ouvrage si fourni
        if ouvrage_id:
            from apps.organization.models import Ouvrage
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
            villages_ouvrage = Village.objects.filter(
                parcelles__points_eau__ouvrage=ouvrage
            ).distinct()
            fournisseurs_qs = fournisseurs_qs.filter(
                adresse__village__in=villages_ouvrage
            )

        fournisseurs = fournisseurs_qs[:20]

        results = []
        for f in fournisseurs:
            try:
                # Utiliser le champ texte adresse directement
                adresse_str = f.adresse if f.adresse else 'N/A'

                results.append({
                    'id': str(f.id),
                    'nom': f.nom_fournisseur,
                    'telephone': f.telephone if f.telephone else '',
                    'adresse': adresse_str,
                    'nif': f.nif if hasattr(f, 'nif') and f.nif else '',
                    'stat': f.stat if hasattr(f, 'stat') and f.stat else '',
                    'display': f"{f.nom_fournisseur} - {f.telephone or 'Pas de telephone'}"
                })
            except Exception as field_error:
                # Si erreur sur un fournisseur, continuer avec les autres
                print(f"Erreur fournisseur {f.id}: {field_error}")
                continue

        return JsonResponse({
            'success': True,
            'fournisseurs': results
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["GET"])
def api_comptes_par_designation(request):
    """
    API pour récupérer les comptes autorisés pour une désignation
    Utilisé pour filtrer la liste déroulante des comptes dans le modal avances/paiements
    """
    try:
        designation_id = request.GET.get('designation_id', '')

        if not designation_id:
            return JsonResponse({
                'success': False,
                'error': 'ID de désignation manquant'
            }, status=400)

        # Récupérer la désignation
        try:
            designation = Designation.objects.get(id=designation_id)
        except Designation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Désignation introuvable: {designation_id}'
            }, status=404)

        # Récupérer les comptes liés via DesignationCompte
        comptes_liaison = DesignationCompte.objects.filter(
            designation=designation,
            is_active=True
        ).select_related('compte')

        comptes = []
        for liaison in comptes_liaison:
            comptes.append({
                'id': str(liaison.compte.id),
                'nom_compte': liaison.compte.nom_compte,
                'numero_compte': liaison.compte.numero_compte if hasattr(liaison.compte, 'numero_compte') else '',
                'display': f"{liaison.compte.numero_compte} - {liaison.compte.nom_compte}" if hasattr(liaison.compte, 'numero_compte') else liaison.compte.nom_compte
            })

        return JsonResponse({
            'success': True,
            'comptes': comptes,
            'designation': {
                'id': str(designation.id),
                'nom': designation.nom
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
