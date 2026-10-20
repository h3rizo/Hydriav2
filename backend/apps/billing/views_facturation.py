"""
Workflow de facturation des relevés volumétriques
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
import io

from apps.billing.models import (
    Releve, PointEau, TarifVolumetrique, TypePointEau, ModaliteGestion, ConsoCarteSociale, FraisTransfertMvola
)
from apps.billing.services_compteurs_abonnes import serialize_segments
from apps.ouvrages.models import TarifVolumetriqueTranche
from apps.organization.models import Ouvrage, Organisation, Base
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)
from apps.employees.models import Employe, EmployeOuvrages
from apps.geography.models import Commune


def _build_facture_qr_payload(releve, annee_facture=None, mois_facture=None):
    releve_id = str(getattr(releve, 'id', '') or '')
    numero_facture = getattr(releve, 'numero_facture', '') or ''
    ouvrage_id = str(getattr(getattr(releve, 'point_eau', None), 'ouvrage_id', '') or '')

    if annee_facture is None or mois_facture is None:
        date_releve = getattr(releve, 'datereleve', None)
        if date_releve:
            mois_facture = date_releve.month + 1
            annee_facture = date_releve.year
            if mois_facture == 13:
                mois_facture = 1
                annee_facture += 1

    annee_mois = ''
    if annee_facture and mois_facture:
        annee_mois = f'{annee_facture:04d}-{mois_facture:02d}'

    return f'HYDRIA|FACTURE|{releve_id}|{numero_facture}|{annee_mois}|{ouvrage_id}'


def _is_directeur_user(user):
    if not user or not user.is_authenticated:
        return False

    employe = getattr(user, 'employe', None)
    if employe and hasattr(employe, 'is_directeur') and employe.is_directeur:
        return True
    return user.groups.filter(name='Directeur').exists()


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    """
    Ouvrages autorisés en facturation volumétrique:
    via ModaliteGestion active (date_fin IS NULL) + type volume/mixte,
    cloisonnés par organisation (gestionnaire) sauf directeur/superuser.
    """
    modalites = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    )

    if not (getattr(user, 'is_superuser', False) or _is_directeur_user(user)):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return modalites.none().values_list('ouvrage_id', flat=True)
        else:
            modalites = modalites.filter(gestionnaire_id__in=gestionnaire_ids)

    ouvrage_ids = set(
        modalites.exclude(ouvrage_id__isnull=True).values_list('ouvrage_id', flat=True).distinct()
    )
    scoped_ids = apply_user_responsable_ouvrage_scope(ouvrage_ids, user)
    return list(ouvrage_ids if scoped_ids is None else scoped_ids)


def _get_directeur_phone_for_organisation(organisation_id):
    if not organisation_id:
        return ''

    directeur = Employe.objects.filter(
        base__organisation_id=organisation_id,
        poste__nom_poste__icontains='directeur',
        date_debauchage__isnull=True
    ).exclude(
        telephone__isnull=True
    ).exclude(
        telephone__exact=''
    ).select_related('poste').order_by('poste__ordre_affichage', 'poste__nom_poste', 'nom', 'prenom').first()

    return directeur.telephone if directeur else ''


def _get_first_attr(obj, *attr_names, default=''):
    if not obj:
        return default

    for attr_name in attr_names:
        value = getattr(obj, attr_name, None)
        if value not in (None, ''):
            return value

    return default


def _get_ouvrage_responsable_contact(ouvrage_id, reference_date=None):
    if not ouvrage_id:
        return {'nom': '', 'telephone': ''}

    target_date = reference_date or timezone.now().date()
    relations = list(
        EmployeOuvrages.objects.filter(
            ouvrage_id=ouvrage_id,
            date_debut__lte=target_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=target_date)
        ).select_related('employe', 'employe__poste')
    )

    if not relations:
        return {'nom': '', 'telephone': ''}

    def _relation_priority(relation):
        poste_nom = ((getattr(relation.employe.poste, 'nom_poste', '') or '').lower())
        if 'recouvrement' in poste_nom:
            role_priority = 0
        elif 'maintenance' in poste_nom or 'entretien' in poste_nom:
            role_priority = 1
        else:
            role_priority = 2

        return (
            role_priority,
            0 if relation.est_responsable_principal else 1,
            relation.date_debut or target_date,
        )

    best_relation = sorted(relations, key=_relation_priority)[0]
    employe = best_relation.employe
    return {
        'nom': employe.nom_affichage if employe else '',
        'telephone': getattr(employe, 'telephone', '') or '',
    }


@login_required
def workflow_facturation(request):
    """Page principale du workflow de facturation"""

    # Récupérer les ouvrages avec modalité volumétrique
    ouvrages_volumetriques_ids = _get_allowed_ouvrage_ids(request.user)

    ouvrages = Ouvrage.objects.filter(
        id__in=ouvrages_volumetriques_ids
    ).order_by('nom_ouvrage')

    organisation_id = _get_user_organisation_id(request.user)
    directeur_telephone = _get_directeur_phone_for_organisation(organisation_id)
    organisation = Organisation.objects.filter(id=organisation_id).first() if organisation_id else None
    organisation_logo_url = ''
    if organisation and getattr(organisation, 'logo', None):
        try:
            organisation_logo_url = request.build_absolute_uri(organisation.logo.url)
        except Exception:
            organisation_logo_url = ''

    organisation_nom = _get_first_attr(
        organisation,
        'nom_organisation',
        'nom',
        'organisation',
        'designation',
        default=str(organisation) if organisation else 'HYDRIA'
    )
    organisation_nif = _get_first_attr(organisation, 'nif', 'NIF', default='')
    organisation_stat = _get_first_attr(organisation, 'stat', 'STAT', default='')
    organisation_adresse = _get_first_attr(
        organisation,
        'adresse1',
        'adresse',
        'address',
        default=''
    )

    context = {
        'title': 'Facturation des Relevés',
        'ouvrages': ouvrages,
        'directeur_telephone': directeur_telephone,
        'organisation_nom': organisation_nom,
        'organisation_nif': organisation_nif,
        'organisation_stat': organisation_stat,
        'organisation_adresse': organisation_adresse,
        'organisation_logo_url': organisation_logo_url,
    }

    return render(request, 'billing/workflow_facturation.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_factures(request):
    """
    API pour calculer les montants des relevés
    Entrée: ouvrage_id, mois_facture (format: YYYY-MM)
    Sortie: Liste des relevés avec montants calculés
    """
    try:
        data = json.loads(request.body) if request.body else {}
        ouvrage_id = data.get('ouvrage_id')
        mois_facture = data.get('mois_facture')  # Format: YYYY-MM

        if not ouvrage_id or not mois_facture:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        # Parser le mois de facture
        try:
            annee, mois = map(int, mois_facture.split('-'))
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Format de mois invalide (attendu: YYYY-MM)'
            }, status=400)

        # Calculer le mois de relevé (mois précédent le mois de facture)
        mois_releve = mois - 1
        annee_releve = annee
        if mois_releve == 0:
            mois_releve = 12
            annee_releve -= 1

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non autorisé'
            }, status=403)

        # Récupérer TOUS les relevés de l'ouvrage pour le mois de relevé
        # Permet de consulter et réimprimer les factures déjà enregistrées
        releves = Releve.objects.filter(
            point_eau__ouvrage_id=ouvrage_id,
            datereleve__year=annee_releve,
            datereleve__month=mois_releve
        ).select_related(
            'point_eau',
            'point_eau__type_point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle'
        )

        if not releves.exists():
            return JsonResponse({
                'success': True,
                'message': 'Aucun relevé sans montant trouvé pour cette période',
                'nb_releves': 0,
                'releves': []
            })

        responsable_contact = _get_ouvrage_responsable_contact(ouvrage_id)

        # Calculer les montants pour chaque relevé
        releves_calcules = []
        nb_success = 0
        nb_errors = 0
        errors = []

        for releve in releves:
            try:
                resultat = calculer_montant_releve(releve)

                if resultat['success']:
                    # Récupérer l'historique des factures impayées pour ce point d'eau
                    # MODIFICATION: On affiche toutes les factures non payées (avec montant calculé), pas seulement les imprimées
                    # IMPORTANT: On ignore les factures avant 2025 (ancienne comptabilité)
                    factures_impayees = Releve.objects.filter(
                        point_eau=releve.point_eau,
                        montant__isnull=False,  # Facture calculée
                        numeroDiameX__isnull=True,  # Pas encore payée
                        datereleve__lt=releve.datereleve,  # Avant le relevé actuel
                        datereleve__year__gte=2025  # Seulement à partir de 2025
                    ).order_by('datereleve').values(
                        'datereleve', 'ancienindex', 'nouvelindex',
                        'volume_facture', 'montant'
                    )

                    # Calculer le total des impayés
                    total_impaye = sum(f['montant'] for f in factures_impayees if f['montant'])

                    releves_calcules.append({
                        'releve_id': str(releve.id),
                        'ouvrage_nom': releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau and releve.point_eau.ouvrage else '',
                        'responsable_ouvrage_nom': responsable_contact['nom'],
                        'responsable_ouvrage_telephone': responsable_contact['telephone'],
                        'numero_facture': releve.numero_facture or '',
                        'point_eau': releve.point_eau.code_point_eau or releve.point_eau.nomabonne,
                        'abonne': releve.abonne or 'N/A',
                        'idxls': releve.point_eau.idxls or '',
                        'ancienindex': float(releve.ancienindex) if releve.ancienindex is not None else None,
                        'nouvelindex': float(releve.nouvelindex) if releve.nouvelindex is not None else None,
                        'parcelle': releve.point_eau.parcelle.reference_parcelle if releve.point_eau.parcelle else 'N/A',
                        'type_point_eau': releve.point_eau.type_point_eau.nom_type if releve.point_eau.type_point_eau else 'N/A',
                        'est_institutionnel': bool(releve.point_eau.estbranchementinstitutionnel),
                        'volume_facture': float(releve.volume_facture or 0),
                        'montant_calcule': resultat['montant_total'],
                        'montant_enregistre': float(releve.montant) if releve.montant else 0,
                        'facture_imprimee': releve.facture_imprimee or False,
                        'paye': bool(releve.numeroDiameX and str(releve.numeroDiameX).strip()),
                         'detail_calcul': resultat['detail'],
                         'segments_compteur': serialize_segments(releve),
                         'factures_impayees': list(factures_impayees),
                         'total_impaye': float(total_impaye),
                         'qr_payload': _build_facture_qr_payload(releve, annee, mois),
                         'success': True
                     })
                    nb_success += 1
                else:
                    errors.append({
                        'releve_id': str(releve.id),
                        'point_eau': releve.point_eau.code_point_eau or releve.point_eau.nomabonne,
                        'error': resultat['error']
                    })
                    nb_errors += 1

            except Exception as e:
                errors.append({
                    'releve_id': str(releve.id),
                    'point_eau': releve.point_eau.code_point_eau or 'N/A',
                    'error': str(e)
                })
                nb_errors += 1

        return JsonResponse({
            'success': True,
            'message': f'{nb_success} relevés calculés, {nb_errors} erreurs',
            'nb_releves': len(releves_calcules),
            'releves': releves_calcules,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _volume_propre(valeur):
    """Volume en m³ ramené à 3 décimales (supprime le bruit des flottants)."""
    from decimal import ROUND_HALF_UP
    return Decimal(str(valeur or 0)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def calculer_montant_releve(releve, volume_carte_sociale=None):
    """
    Calcule le montant d'un relevé selon les tarifs volumétriques

    Logique:
    1. Prix d'abonnement (fixe)
    2. Volume minimum facturé
    3. Calcul par tranches sur le volume_facture

    ``volume_carte_sociale`` : volume (m³) des cartes sociales d'un relevé pas
    encore enregistré (calcul avant impression terrain). Sans lui, le volume
    est relu depuis ConsoCarteSociale, donc nul pour un relevé temporaire.

    Returns:
        dict avec 'success', 'montant_total', 'detail', 'error'
    """
    try:
        point_eau = releve.point_eau
        ouvrage = point_eau.ouvrage
        type_point_eau = point_eau.type_point_eau

        # Recalculer les volumes à partir des détails réels du relevé.
        # On ne doit pas afficher un ancien volume de carte sociale si aucune
        # consommation carte sociale n'est effectivement liée à ce relevé.
        # Les volumes sont des FloatField : 30.76 peut revenir en 30.76000000000002.
        # Sans nettoyage, ce bruit fait passer un montant exact multiple de 100 Ar
        # à la centaine suivante à l'arrondi supérieur (+100 Ar à tort).
        volume_consomme_decimal = _volume_propre(releve.consommation)
        volume_non_facture_decimal = _volume_propre(releve.volume_non_facture)
        if volume_carte_sociale is not None:
            volume_carte_sociale_decimal = _volume_propre(volume_carte_sociale)
        else:
            volume_carte_sociale_decimal = _volume_propre(
                ConsoCarteSociale.objects.filter(
                    releve=releve,
                    carte_sociale__point_eau_id=releve.point_eau_id,
                    carte_sociale__statut='active',
                ).aggregate(
                    total=Sum('volume_total')
                )['total']
            )
        volume_facture_decimal = max(
            Decimal('0'),
            volume_consomme_decimal - volume_carte_sociale_decimal - volume_non_facture_decimal
        )

        volume_consomme = float(volume_consomme_decimal)
        volume_carte_sociale = float(volume_carte_sociale_decimal)
        volume_non_facture = float(volume_non_facture_decimal)
        volume_facture = float(volume_facture_decimal)

        # Récupérer le tarif actif pour cet ouvrage et type de point d'eau
        tarifs_actifs = TarifVolumetrique.objects.filter(
            ouvrage=ouvrage,
            type_point_eau=type_point_eau,
            datefintarif__isnull=True,  # Tarif actif
            actif=True
        )
        # Branchement institutionnel : tarif dédié s'il existe (ex-« BI volume »), sinon tarif
        # ordinaire du type. Un point ordinaire n'utilise jamais le tarif institutionnel.
        est_institutionnel = bool(point_eau.estbranchementinstitutionnel)
        tarif = None
        if est_institutionnel:
            tarif = tarifs_actifs.filter(institutionnel=True).first()
        if tarif is None:
            tarif = tarifs_actifs.filter(institutionnel=False).first()

        if not tarif:
            return {
                'success': False,
                'error': f'Aucun tarif actif trouvé pour {type_point_eau.nom_type if type_point_eau else "ce type"}'
                         f'{" (branchement institutionnel)" if est_institutionnel else ""}'
            }

        # 1. Prix d'abonnement
        montant_abonnement = Decimal(str(tarif.prixabonnement))

        # 2. Vérifier le volume minimum
        volume_minimum_decimal = Decimal(str(tarif.volume_minimum_facture or 0))
        if volume_facture_decimal <= 0:
            volume_a_facturer_decimal = volume_minimum_decimal if volume_minimum_decimal > 0 else Decimal('0')
        else:
            volume_a_facturer_decimal = max(volume_facture_decimal, volume_minimum_decimal)

        volume_minimum = float(volume_minimum_decimal)
        volume_a_facturer = float(volume_a_facturer_decimal)

        # 3. Récupérer les tranches de tarif (ordonnées par tranchesuperieur)
        tranches = TarifVolumetriqueTranche.objects.filter(
            tarifvolumetrique=tarif
        ).order_by('tranchesuperieur')

        if volume_a_facturer_decimal > 0 and not tranches.exists():
            return {
                'success': False,
                'error': 'Aucune tranche de tarif configurée'
            }

        # 4. Calculer le montant par tranches
        montant_volume = Decimal('0')
        volume_restant = volume_a_facturer_decimal
        detail_tranches = []

        tranche_inferieure = 0  # En m³

        # La dernière tranche définie pour ce tarif sert de palier "illimité" :
        # sa borne supérieure ne représente pas une consommation réellement atteignable,
        # elle ne doit donc jamais être affichée sur la facture.
        derniere_tranche_id = tranches.last().id if tranches.exists() else None

        for tranche in tranches:
            # tranchesuperieur est déjà en m³ (pas de conversion nécessaire)
            tranche_superieure_m3 = Decimal(str(tranche.tranchesuperieur))
            tarif_par_m3 = Decimal(str(tranche.tarif))

            # Calculer le volume dans cette tranche
            volume_dans_tranche = min(
                volume_restant,
                tranche_superieure_m3 - Decimal(str(tranche_inferieure))
            )

            if volume_dans_tranche > 0:
                montant_tranche = volume_dans_tranche * tarif_par_m3
                montant_volume += montant_tranche

                if tranche.id == derniere_tranche_id:
                    label_tranche = f"> {tranche_inferieure} m³"
                else:
                    label_tranche = f"{tranche_inferieure} - {tranche_superieure_m3} m³"

                detail_tranches.append({
                    'tranche': label_tranche,
                    'volume': float(volume_dans_tranche),
                    'tarif_unitaire': float(tarif_par_m3),
                    'montant': float(montant_tranche)
                })

                volume_restant -= volume_dans_tranche
                tranche_inferieure = float(tranche_superieure_m3)

            # Si tout le volume est consommé, arrêter
            if volume_restant <= 0:
                break

        # Si du volume reste après toutes les tranches, le facturer au dernier tarif
        if volume_restant > 0 and tranches.exists():
            dernier_tarif = Decimal(str(tranches.last().tarif))
            montant_supplementaire = volume_restant * dernier_tarif
            montant_volume += montant_supplementaire

            detail_tranches.append({
                'tranche': f"> {tranche_inferieure} m³",
                'volume': float(volume_restant),
                'tarif_unitaire': float(dernier_tarif),
                'montant': float(montant_supplementaire)
            })

        # 5. Montant total HT
        montant_ht = montant_abonnement + montant_volume

        # 6. Taxe communale 7% (INDICATIF - non ajouté au total)
        taxe_communale = montant_ht * Decimal('0.07')

        # 7. Arrondir le montant HT à 100 Ar près (arrondi au supérieur)
        import math
        montant_arrondi = Decimal(math.ceil(float(montant_ht) / 100) * 100)

        # 8. Montant total = montant arrondi (taxe communale indicative uniquement)
        montant_total = montant_arrondi

        # 9. Frais de transfert MVola applicable au montant à payer (indicatif uniquement)
        frais_mvola = FraisTransfertMvola.calculer_frais(montant_total)

        return {
            'success': True,
            'montant_total': float(montant_total),
            'detail': {
                'abonnement': float(montant_abonnement),
                'volume_consomme': volume_consomme,
                'volume_carte_sociale': volume_carte_sociale,
                'volume_non_facture': volume_non_facture,
                'volume_facture': volume_facture,
                'volume_minimum': volume_minimum,
                'volume_calcule': volume_a_facturer,
                'tranches': detail_tranches,
                'montant_volume': float(montant_volume),
                'montant_ht': float(montant_ht),
                'taxe_communale': float(taxe_communale),  # Indicatif uniquement
                'montant_arrondi': float(montant_arrondi),
                'montant_ttc': float(montant_total),  # = montant arrondi sans taxe
                'frais_mvola': float(frais_mvola) if frais_mvola is not None else None  # Indicatif uniquement
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Erreur de calcul: {str(e)}'
        }


@csrf_exempt
@require_http_methods(["POST"])
def api_valider_factures(request):
    """
    Enregistre les montants calculés dans la base de données
    """
    try:
        data = json.loads(request.body) if request.body else {}
        releves_data = data.get('releves', [])

        if not releves_data:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé à valider'
            }, status=400)

        nb_success = 0
        errors = []

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        for releve_data in releves_data:
            try:
                releve_id = releve_data.get('releve_id')
                montant = releve_data.get('montant_calcule')

                releve = Releve.objects.get(
                    id=releve_id,
                    point_eau__ouvrage_id__in=allowed_ouvrage_ids
                )
                releve.montant = Decimal(str(montant))
                releve.save()

                nb_success += 1

            except Releve.DoesNotExist:
                errors.append({
                    'releve_id': releve_id,
                    'error': 'Relevé introuvable ou non autorisé'
                })
            except Exception as e:
                errors.append({
                    'releve_id': releve_id,
                    'error': str(e)
                })

        return JsonResponse({
            'success': True,
            'message': f'{nb_success} relevés enregistrés',
            'nb_success': nb_success,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_marquer_factures_imprimees(request):
    """API pour marquer les factures comme imprimées"""
    try:
        data = json.loads(request.body)
        releves_ids = data.get('releves_ids', [])

        if not releves_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé fourni'
            }, status=400)

        # L'impression vaut validation : le montant est enregistré en même temps
        # que la facture est marquée imprimée (les utilisateurs oubliaient le
        # bouton « Enregistrer »). Tant qu'une facture n'est pas imprimée, elle
        # reste recalculable. Le montant est recalculé ici côté serveur, avec la
        # même fonction que l'écran, plutôt que repris du navigateur.
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        releves = Releve.objects.filter(
            id__in=releves_ids,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids,
        ).select_related(
            'point_eau', 'point_eau__type_point_eau', 'point_eau__ouvrage'
        )

        nb_updated = 0
        nb_montants = 0
        errors = []
        for releve in releves:
            deja_validee = releve.facture_imprimee and releve.montant
            if deja_validee:
                continue  # facture déjà imprimée et enregistrée : on n'y touche plus

            resultat = calculer_montant_releve(releve)
            if not resultat['success']:
                errors.append({'releve_id': str(releve.id), 'error': resultat['error']})
                continue

            releve.montant = Decimal(str(resultat['montant_total']))
            nb_montants += 1
            if not releve.facture_imprimee:
                releve.facture_imprimee = True
                releve.date_impression = timezone.now()
                nb_updated += 1
            releve.save()

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} facture(s) marquée(s) comme imprimée(s), '
                       f'{nb_montants} montant(s) enregistré(s)',
            'nb_updated': nb_updated,
            'nb_montants': nb_montants,
            'errors': errors,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
