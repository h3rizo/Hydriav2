"""Vues et APIs pour le workflow des cartes sociales"""
from collections import defaultdict
from datetime import datetime

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Sum, Count, Q, Prefetch
from django.utils import timezone
from decimal import Decimal
import json
import uuid

from apps.infrastructure.models import CarteSociale
from apps.billing.models import ConsoCarteSociale, PointEau, ModaliteGestion
from apps.accounting.models import DiameXTemporaire
from apps.organization.models import Ouvrage, Organisation
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    modalites_qs = ModaliteGestion.objects.filter(date_fin__isnull=True)
    if not getattr(user, 'is_superuser', False):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return []
        else:
            modalites_qs = modalites_qs.filter(gestionnaire_id__in=gestionnaire_ids)

    ouvrage_ids = set(
        modalites_qs.exclude(ouvrage_id__isnull=True)
        .values_list('ouvrage_id', flat=True)
        .distinct()
    )
    scoped_ids = apply_user_responsable_ouvrage_scope(ouvrage_ids, user)
    return list(ouvrage_ids if scoped_ids is None else scoped_ids)


def _get_active_modalite_by_ouvrage_ids(ouvrage_ids):
    modalites = (
        ModaliteGestion.objects.filter(
            date_fin__isnull=True,
            ouvrage_id__in=ouvrage_ids
        )
        .select_related('gestionnaire')
        .order_by('ouvrage_id', '-date_debut', '-created_at')
    )
    mapping = {}
    for m in modalites:
        key = str(m.ouvrage_id)
        if key not in mapping:
            mapping[key] = m
    return mapping


def _get_carte_sociale_tarif(carte):
    ouvrage = getattr(carte, 'ouvrage', None)
    if not ouvrage:
        ouvrage = getattr(carte, 'carte_sociale', None)
        ouvrage = getattr(ouvrage, 'ouvrage', None)

    if not ouvrage:
        return Decimal('0')

    modalite = ouvrage.modalites_gestion.filter(date_fin__isnull=True).select_related('gestionnaire').first()
    gestionnaire = getattr(modalite, 'gestionnaire', None)
    tarif = getattr(gestionnaire, 'tarif_carte_sociale', None)
    return Decimal(str(tarif or 0))


def _build_conso_temp_reference(line_id):
    return f"TEMP-CS-{line_id}"


@login_required
def cartes_sociales_workflow(request):
    """Page principale du workflow des cartes sociales"""
    from apps.billing.models import Releve

    # Filtrer les ouvrages qui ont des points d'eau avec des relevés
    # 1. Récupérer les IDs des points d'eau qui ont des relevés
    points_eau_avec_releves = Releve.objects.values_list('point_eau_id', flat=True).distinct()

    # 2. Récupérer les IDs des ouvrages liés à ces points d'eau
    ouvrages_ids = PointEau.objects.filter(
        id__in=points_eau_avec_releves
    ).values_list('ouvrage_id', flat=True).distinct()

    # 3. Filtrer les ouvrages avec leurs modalités actives
    allowed_ouvrage_ids = set(str(x) for x in _get_allowed_ouvrage_ids(request.user))
    ouvrages_ids = [oid for oid in ouvrages_ids if str(oid) in allowed_ouvrage_ids]
    ouvrages = Ouvrage.objects.filter(
        id__in=ouvrages_ids
    ).prefetch_related(
        Prefetch(
            'modalites_gestion',
            queryset=ModaliteGestion.objects.filter(date_fin__isnull=True).select_related('gestionnaire')
        )
    ).order_by('nom_ouvrage')

    context = {
        'title': 'Cartes Sociales - Workflow',
        'ouvrages': ouvrages,
    }
    return render(request, 'billing/cartes_sociales_workflow.html', context)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_cartes_list(request):
    """API pour récupérer la liste des cartes sociales par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')

        if not ouvrage_id:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage ID requis'
            }, status=400)

        # Récupérer l'ouvrage
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id, id__in=allowed_ouvrage_ids)

        # Récupérer la modalité active pour l'ouvrage (avec organisation)
        modalite = ModaliteGestion.objects.filter(
            ouvrage=ouvrage,
            date_fin__isnull=True
        ).select_related('gestionnaire').first()

        # Récupérer toutes les cartes sociales actives de cet ouvrage
        cartes = CarteSociale.objects.filter(
            ouvrage=ouvrage,
            statut='active'
        ).select_related(
            'point_eau__type_point_eau'
        ).order_by('point_eau__nomabonne', 'numero_carte')

        # Grouper par point d'eau
        points_eau_data = {}
        for carte in cartes:
            pe = carte.point_eau
            if not pe:
                continue

            pe_id = str(pe.id)
            if pe_id not in points_eau_data:
                points_eau_data[pe_id] = {
                    'id': pe_id,
                    'nom': pe.nomabonne or 'Sans nom',
                    'type': pe.type_point_eau.nom_type if pe.type_point_eau else 'Non défini',
                    'cartes': []
                }

            points_eau_data[pe_id]['cartes'].append({
                'id': str(carte.id),
                'numero': carte.numero_carte,
                'beneficiaire': carte.nom_beneficiaire,
                'date_creation': carte.date_creation.isoformat() if carte.date_creation else None,
                'date_expiration': carte.date_expiration.isoformat() if carte.date_expiration else None,
                'nombre_habitants': carte.nombre_habitants or 0,
            })

        # Récupérer le tarif carte sociale de l'organisation (via modalité)
        tarif = None
        organisation_nom = None
        organisation_logo = None
        if modalite and modalite.gestionnaire:
            tarif = float(modalite.gestionnaire.tarif_carte_sociale) if modalite.gestionnaire.tarif_carte_sociale else None
            organisation_nom = modalite.gestionnaire.nom_organisation
            if modalite.gestionnaire.logo:
                organisation_logo = request.build_absolute_uri(modalite.gestionnaire.logo.url)

        return JsonResponse({
            'success': True,
            'ouvrage': {
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage,
                'organisation': organisation_nom,
                'organisation_logo': organisation_logo,
            },
            'tarif_carte_sociale': tarif,
            'points_eau': list(points_eau_data.values())
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_carte(request):
    """API pour supprimer logiquement une carte sociale sans toucher au beneficiaire."""
    try:
        data = json.loads(request.body or '{}')
        carte_id = data.get('carte_id')

        if not carte_id:
            return JsonResponse({
                'success': False,
                'error': 'Carte ID requis'
            }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not allowed_ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun ouvrage autorise'
            }, status=403)

        carte = get_object_or_404(
            CarteSociale,
            pk=carte_id,
            ouvrage_id__in=allowed_ouvrage_ids
        )

        if carte.statut != 'active':
            return JsonResponse({
                'success': False,
                'error': 'Cette carte n est plus active'
            }, status=400)

        carte.statut = 'annulee'
        carte.save(update_fields=['statut', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': f'Carte sociale {carte.numero_carte} supprimee'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_imprimer_ticket(request):
    """API pour générer un ticket et créer une ligne dans conso_cartes_sociales
    Accepte soit une seule carte, soit un tableau de cartes"""
    try:
        data = json.loads(request.body)
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not allowed_ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun ouvrage autorise'
            }, status=403)

        # Vérifier si c'est une impression multiple
        cartes_data = data.get('cartes')

        if cartes_data:
            # Impression multiple
            consos_creees = []

            for carte_info in cartes_data:
                carte_id = carte_info.get('carte_id')
                date_facture = carte_info.get('date')

                if not all([carte_id, date_facture]):
                    continue

                # Récupérer la carte sociale
                carte = CarteSociale.objects.select_related('ouvrage', 'point_eau').filter(
                    pk=carte_id,
                    ouvrage_id__in=allowed_ouvrage_ids
                ).first()
                if not carte:
                    continue

                # VALIDATION: Vérifier qu'il n'existe pas déjà une carte pour ce mois
                # Parse date string to date object if needed
                if isinstance(date_facture, str):
                    from datetime import datetime
                    date_obj = datetime.strptime(date_facture, '%Y-%m-%d').date()
                else:
                    date_obj = date_facture

                # Check for existing consumption in same month
                existing_conso = ConsoCarteSociale.objects.filter(
                    carte_sociale=carte,
                    date__year=date_obj.year,
                    date__month=date_obj.month
                ).exists()

                if existing_conso:
                    # Skip this card - already has a consumption record this month
                    continue

                # Créer la ligne de consommation
                conso = ConsoCarteSociale.objects.create(
                    carte_sociale=carte,
                    date=date_facture,
                    montant_paye=_get_carte_sociale_tarif(carte),
                    quantite_bidons=30,
                )
                consos_creees.append(str(conso.id))

            return JsonResponse({
                'success': True,
                'message': f'{len(consos_creees)} ticket(s) imprimé(s) et ligne(s) de consommation créée(s)',
                'nb_created': len(consos_creees),
                'consos_ids': consos_creees
            })

        else:
            # Impression simple (existante)
            carte_id = data.get('carte_id')
            date_facture = data.get('date_facture') or data.get('date')

            if not all([carte_id, date_facture]):
                return JsonResponse({
                    'success': False,
                    'error': 'Paramètres manquants (carte_id, montant, date_facture)'
                }, status=400)

            # Récupérer la carte sociale avec l'ouvrage
            carte = get_object_or_404(
                CarteSociale.objects.select_related('ouvrage', 'point_eau'),
                pk=carte_id,
                ouvrage_id__in=allowed_ouvrage_ids
            )

            # Récupérer l'organisation via la modalité de gestion
            organisation_nom = 'Non définie'
            organisation_logo = None
            if carte.ouvrage:
                modalite = carte.ouvrage.modalites_gestion.filter(date_fin__isnull=True).select_related('gestionnaire').first()
                if modalite and modalite.gestionnaire:
                    organisation_nom = modalite.gestionnaire.nom_organisation
                    if modalite.gestionnaire.logo:
                        organisation_logo = request.build_absolute_uri(modalite.gestionnaire.logo.url)

            # VALIDATION: Vérifier qu'il n'existe pas déjà une carte pour ce mois
            # Parse date string to date object if needed
            if isinstance(date_facture, str):
                from datetime import datetime
                date_obj = datetime.strptime(date_facture, '%Y-%m-%d').date()
            else:
                date_obj = date_facture

            # Check for existing consumption in same month
            existing_conso = ConsoCarteSociale.objects.filter(
                carte_sociale=carte,
                date__year=date_obj.year,
                date__month=date_obj.month
            ).first()

            if existing_conso:
                # Return error - card already has a consumption record this month
                return JsonResponse({
                    'success': False,
                    'error': f'Une carte sociale existe déjà pour {carte.nom_beneficiaire} ce mois-ci (le {existing_conso.date.strftime("%d/%m/%Y")})'
                }, status=400)

            # Créer la ligne de consommation
            conso = ConsoCarteSociale.objects.create(
                carte_sociale=carte,
                date=date_facture,
                montant_paye=_get_carte_sociale_tarif(carte),
                quantite_bidons=30,  # 30 cases par défaut
                # volume_total sera calculé automatiquement par le save()
            )

            return JsonResponse({
                'success': True,
                'message': 'Ticket imprimé et ligne de consommation créée',
                'conso_id': str(conso.id),
                'volume_total': conso.volume_total,
                'ticket_data': {
                    'numero_carte': carte.numero_carte,
                    'beneficiaire': carte.nom_beneficiaire,
                    'point_eau': carte.point_eau.nomabonne if carte.point_eau else 'Non défini',
                    'ouvrage': carte.ouvrage.nom_ouvrage if carte.ouvrage else 'Non défini',
                    'organisation': organisation_nom,
                    'organisation_logo': organisation_logo,
                    'montant': float(_get_carte_sociale_tarif(carte)),
                    'date': date_facture,
                    'nb_bidons': 30,
                }
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def cartes_sociales_encaissement(request):
    """Page d'encaissement des cartes sociales (similaire à /facturation/encaissement/)."""
    today = timezone.localdate()
    context = {
        'title': 'Encaissement Cartes Sociales',
        'today': today,
    }
    return render(request, 'billing/cartes_sociales_encaissement.html', context)


@login_required
@require_http_methods(["GET"])
def api_consos_a_encaisser(request):
    """API pour récupérer les consommations de cartes sociales à encaisser."""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        mois = request.GET.get('mois')

        consos = ConsoCarteSociale.objects.filter(
            numeroDiameX__isnull=True,
            date__isnull=False,
            montant_paye__isnull=False
        ).select_related(
            'carte_sociale__ouvrage',
            'carte_sociale__point_eau'
        )
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not allowed_ouvrage_ids:
            consos = consos.none()
        else:
            consos = consos.filter(carte_sociale__ouvrage_id__in=allowed_ouvrage_ids)

        if ouvrage_id and ouvrage_id != 'all':
            if str(ouvrage_id) not in {str(x) for x in allowed_ouvrage_ids}:
                return JsonResponse({
                    'success': False,
                    'error': 'Ouvrage non autorise'
                }, status=403)
            consos = consos.filter(carte_sociale__ouvrage_id=ouvrage_id)

        if mois:
            try:
                year_str, month_str = mois.split('-')
                consos = consos.filter(date__year=int(year_str), date__month=int(month_str))
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Format de mois invalide'
                }, status=400)

        consos = list(
            consos.order_by(
                'date',
                'carte_sociale__ouvrage__nom_ouvrage',
                'carte_sociale__point_eau__parcelle__reference_parcelle',
                'carte_sociale__point_eau__nomabonne',
                'carte_sociale__numero_carte'
            )[:500]
        )

        consos_data = []
        total = Decimal('0')
        for conso in consos:
            tarif_unique = _get_carte_sociale_tarif(conso)
            total += tarif_unique
            point_eau = conso.carte_sociale.point_eau
            ouvrage = conso.carte_sociale.ouvrage
            parcelle = point_eau.parcelle.reference_parcelle if point_eau and point_eau.parcelle else None
            village = point_eau.parcelle.village.nom_village if point_eau and point_eau.parcelle and point_eau.parcelle.village else None

            consos_data.append({
                'id': str(conso.id),
                'numero_carte': conso.carte_sociale.numero_carte,
                'beneficiaire': conso.carte_sociale.nom_beneficiaire,
                'point_eau': point_eau.nomabonne if point_eau else 'N/A',
                'idxls': point_eau.idxls if point_eau else None,
                'ouvrage': ouvrage.nom_ouvrage if ouvrage else 'N/A',
                'ouvrage_id': str(ouvrage.id) if ouvrage else None,
                'parcelle': parcelle,
                'village': village,
                'annee_mois': conso.date.strftime('%Y-%m') if conso.date else None,
                'mois_annee_display': conso.date.strftime('%B %Y').capitalize() if conso.date else None,
                'date': conso.date.isoformat(),
                'date_display': conso.date.strftime('%d/%m/%Y') if conso.date else None,
                'montant': float(tarif_unique),
                'quantite_bidons': conso.quantite_bidons,
                'volume_total': conso.volume_total,
            })

        return JsonResponse({
            'success': True,
            'consos': consos_data,
            'count': len(consos_data),
            'montant_total': float(total)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_liste_ouvrages_cartes_sociales(request):
    """Liste des ouvrages ayant des consommations de cartes sociales à encaisser."""
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not allowed_ouvrage_ids:
            return JsonResponse({'success': True, 'ouvrages': []})

        ouvrages_ids = ConsoCarteSociale.objects.filter(
            numeroDiameX__isnull=True,
            date__isnull=False,
            montant_paye__isnull=False,
            carte_sociale__ouvrage_id__in=allowed_ouvrage_ids
        ).values_list('carte_sociale__ouvrage_id', flat=True).distinct()

        ouvrages = Ouvrage.objects.filter(
            id__in=[oid for oid in ouvrages_ids if oid is not None]
        ).order_by('nom_ouvrage')

        return JsonResponse({
            'success': True,
            'ouvrages': [{'id': str(ouvrage.id), 'nom': ouvrage.nom_ouvrage} for ouvrage in ouvrages]
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_valider_encaissement_cartes_sociales(request):
    """Valide un encaissement groupé de cartes sociales et crée les lignes DiameXTemporaire."""
    try:
        data = json.loads(request.body or '{}')
        consos_ids = data.get('consos_ids', [])
        date_encaissement_str = data.get('date_encaissement')
        journal_code = data.get('journal_code', '00PERS')

        if not consos_ids:
            return JsonResponse({'success': False, 'error': 'Aucune carte sociale selectionnee'}, status=400)

        if not date_encaissement_str:
            return JsonResponse({'success': False, 'error': "Date d'encaissement requise"}, status=400)

        date_encaissement = datetime.strptime(date_encaissement_str, '%Y-%m-%d').date()
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        with transaction.atomic():
            consos = ConsoCarteSociale.objects.filter(
                id__in=consos_ids,
                numeroDiameX__isnull=True,
                date__isnull=False,
                montant_paye__isnull=False,
                carte_sociale__ouvrage_id__in=allowed_ouvrage_ids
            ).select_related('carte_sociale__ouvrage', 'carte_sociale__point_eau')

            if not consos.exists():
                return JsonResponse({'success': False, 'error': 'Aucune consommation valide trouvee'}, status=400)

            employe = getattr(request.user, 'employe', None)
            volet = getattr(getattr(employe, 'base', None), 'volet', None)
            prog = getattr(getattr(employe, 'base', None), 'prog_diamex', None) or getattr(getattr(employe, 'base', None), 'nom_base', None)
            pers = employe.nom if employe and journal_code == '00PERS' else None
            if pers and len(pers) > 50:
                pers = pers[:50]
            activ_value = str(volet)[:50] if volet else None
            prog_value = str(prog)[:50] if prog else None

            regroupements = {}
            for conso in consos:
                ouvrage = conso.carte_sociale.ouvrage
                if not ouvrage or not conso.date:
                    continue

                mois_key = conso.date.strftime('%Y-%m')
                cle = f"{ouvrage.id}_{mois_key}"
                if cle not in regroupements:
                    regroupements[cle] = {
                        'ouvrage': ouvrage,
                        'mois_display': conso.date.strftime('%B %Y'),
                        'consos': [],
                        'montant_total': Decimal('0')
                    }
                montant = _get_carte_sociale_tarif(conso)
                regroupements[cle]['consos'].append(conso)
                regroupements[cle]['montant_total'] += montant

            lignes_creees = []
            consos_ids_traites = []
            for groupe in regroupements.values():
                montant_total = groupe['montant_total']
                montant_formatte = f"{int(montant_total):,}".replace(',', ' ')
                description = f"_Encaissement cartes sociales_{groupe['ouvrage'].nom_ouvrage}_{groupe['mois_display']}_{montant_formatte} Ar"

                ligne = DiameXTemporaire.objects.create(
                    type_transaction='recette',
                    journal_code=journal_code[:50] if journal_code else None,
                    date_rec=date_encaissement,
                    description=description[:255],
                    montant_in=float(montant_total),
                    montant_out=0,
                    compte_code='701003',
                    pers=pers,
                    activ=activ_value,
                    prog=prog_value,
                    info='hydria encaissement cartes sociales',
                    statut='en_attente',
                    created_by=employe
                )

                reference_temp = _build_conso_temp_reference(ligne.id)
                for conso in groupe['consos']:
                    conso.numeroDiameX = reference_temp
                    conso.baseDiameX = 'TEMP'
                    conso.save(update_fields=['numeroDiameX', 'baseDiameX', 'updated_at'])
                    consos_ids_traites.append(str(conso.id))

                lignes_creees.append({
                    'id': ligne.id,
                    'description': description,
                    'montant': float(montant_total),
                    'nb_consos': len(groupe['consos'])
                })

        return JsonResponse({
            'success': True,
            'message': f'{len(lignes_creees)} ligne(s) DiameX creee(s)',
            'lignes': lignes_creees,
            'nb_consos_traitees': len(consos_ids_traites),
            'consos_ids': consos_ids_traites
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Format JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_derniers_encaissements_cartes_sociales(request):
    """Recupere les derniers encaissements de cartes sociales des 7 derniers jours."""
    try:
        page = max(int(request.GET.get('page', 1) or 1), 1)
        page_size = 5
        date_limite = timezone.now() - timezone.timedelta(days=7)
        lignes_diamex = DiameXTemporaire.objects.filter(
            type_transaction='recette',
            info='hydria encaissement cartes sociales',
            created_at__gte=date_limite
        ).order_by('-date_rec', '-created_at')[:50]

        encaissements = []
        for ligne in lignes_diamex:
            reference_temp = _build_conso_temp_reference(ligne.id)
            consos = ConsoCarteSociale.objects.filter(
                numeroDiameX=reference_temp
            ).select_related('carte_sociale__ouvrage', 'carte_sociale__point_eau')

            if not consos.exists():
                continue

            encaissements.append({
                'date_encaissement': ligne.date_rec.strftime('%Y-%m-%d') if ligne.date_rec else None,
                'date_encaissement_display': ligne.date_rec.strftime('%d/%m/%Y') if ligne.date_rec else None,
                'description': ligne.description,
                'journal': ligne.journal_code,
                'montant_total': float(ligne.montant_in or 0),
                'nb_consos': consos.count(),
                'consos': [{
                    'numero_carte': conso.carte_sociale.numero_carte,
                    'beneficiaire': conso.carte_sociale.nom_beneficiaire,
                    'point_eau': conso.carte_sociale.point_eau.nomabonne if conso.carte_sociale.point_eau else 'N/A',
                    'idxls': conso.carte_sociale.point_eau.idxls if conso.carte_sociale.point_eau else None,
                    'ouvrage': conso.carte_sociale.ouvrage.nom_ouvrage if conso.carte_sociale.ouvrage else 'N/A',
                    'parcelle': conso.carte_sociale.point_eau.parcelle.reference_parcelle if conso.carte_sociale.point_eau and conso.carte_sociale.point_eau.parcelle else None,
                    'montant': float(_get_carte_sociale_tarif(conso)),
                } for conso in consos[:5]]
            })

        total_items = len(encaissements)
        total_pages = max((total_items + page_size - 1) // page_size, 1)
        if page > total_pages:
            page = total_pages
        start = (page - 1) * page_size
        end = start + page_size

        return JsonResponse({
            'success': True,
            'encaissements': encaissements[start:end],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_items': total_items,
                'total_pages': total_pages,
                'has_previous': page > 1,
                'has_next': page < total_pages,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_export_diamex(request):
    """Compatibilite avec l'ancien bouton d'export."""
    return api_valider_encaissement_cartes_sociales(request)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_sync_diamex(request):
    """API pour synchroniser les IDs DiameX vers les consommations."""
    try:
        data = json.loads(request.body)
        ligne_temp_id = data.get('ligne_temp_id')
        numero_diamex = data.get('numero_diamex')
        base_diamex = data.get('base_diamex')

        if not all([ligne_temp_id, numero_diamex]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        ligne_temp = get_object_or_404(DiameXTemporaire, pk=ligne_temp_id)
        reference_temp = _build_conso_temp_reference(ligne_temp.id)

        conso_qs = ConsoCarteSociale.objects.filter(numeroDiameX=reference_temp)
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not request.user.is_superuser:
            conso_qs = conso_qs.filter(carte_sociale__ouvrage_id__in=allowed_ouvrage_ids)

        nb_updated = conso_qs.update(
            numeroDiameX=str(numero_diamex),
            baseDiameX=base_diamex
        )

        ligne_temp.id_diamex = str(numero_diamex)
        ligne_temp.statut = 'exporte'
        ligne_temp.save(update_fields=['id_diamex', 'statut'])

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} consommation(s) synchronisee(s) avec DiameX',
            'nb_updated': nb_updated
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_export_consos_excel(request):
    """API pour exporter les consommations de cartes sociales en Excel"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from django.http import HttpResponse
        from datetime import datetime

        # Filtres
        ouvrage_id = request.GET.get('ouvrage_id')
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')

        # Base queryset
        consos = ConsoCarteSociale.objects.filter(
            date__isnull=False,
            montant_paye__isnull=False
        ).select_related(
            'carte_sociale__ouvrage',
            'carte_sociale__point_eau'
        )
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not allowed_ouvrage_ids:
            consos = consos.none()
        else:
            consos = consos.filter(carte_sociale__ouvrage_id__in=allowed_ouvrage_ids)

        # Appliquer les filtres
        if ouvrage_id and ouvrage_id != 'all':
            if str(ouvrage_id) not in {str(x) for x in allowed_ouvrage_ids}:
                return JsonResponse({
                    'success': False,
                    'error': 'Ouvrage non autorise'
                }, status=403)
            consos = consos.filter(carte_sociale__ouvrage_id=ouvrage_id)
        if date_debut:
            consos = consos.filter(date__gte=date_debut)
        if date_fin:
            consos = consos.filter(date__lte=date_fin)

        # Créer le workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Consommations Cartes Sociales"

        # Styles
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Conso', 'Ouvrage', 'Point d\'Eau', 'N° Carte', 'Bénéficiaire',
            'Date', 'Quantité Bidons', 'Volume Total', 'Montant Payé',
            'Numero DiameX', 'Base DiameX', 'Créé le'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        # Données
        for row_num, conso in enumerate(consos, 2):
            ws.cell(row=row_num, column=1, value=str(conso.id)).border = border
            ws.cell(row=row_num, column=2, value=conso.carte_sociale.ouvrage.nom_ouvrage if conso.carte_sociale.ouvrage else 'N/A').border = border
            ws.cell(row=row_num, column=3, value=conso.carte_sociale.point_eau.nomabonne if conso.carte_sociale.point_eau else 'N/A').border = border
            ws.cell(row=row_num, column=4, value=conso.carte_sociale.numero_carte).border = border
            ws.cell(row=row_num, column=5, value=conso.carte_sociale.nom_beneficiaire).border = border
            ws.cell(row=row_num, column=6, value=conso.date.strftime('%Y-%m-%d') if conso.date else '').border = border
            ws.cell(row=row_num, column=7, value=conso.quantite_bidons or 0).border = border
            ws.cell(row=row_num, column=8, value=float(conso.volume_total) if conso.volume_total else 0).border = border
            ws.cell(row=row_num, column=9, value=float(conso.montant_paye) if conso.montant_paye else 0).border = border
            ws.cell(row=row_num, column=10, value=conso.numeroDiameX or '').border = border
            ws.cell(row=row_num, column=11, value=conso.baseDiameX or '').border = border
            ws.cell(row=row_num, column=12, value=conso.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(conso, 'created_at') and conso.created_at else '').border = border

        # Ajuster les largeurs de colonnes
        ws.column_dimensions['A'].width = 38
        ws.column_dimensions['B'].width = 25
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 15
        ws.column_dimensions['H'].width = 15
        ws.column_dimensions['I'].width = 15
        ws.column_dimensions['J'].width = 15
        ws.column_dimensions['K'].width = 15
        ws.column_dimensions['L'].width = 18

        # Générer le fichier
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"consommations_cartes_sociales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        wb.save(response)
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_template_consos_excel(request):
    """API pour télécharger le template Excel d'import des consommations"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from django.http import HttpResponse
        from datetime import datetime

        wb = Workbook()
        ws = wb.active
        ws.title = "Template Import Consos"

        # Styles
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        example_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Carte Sociale*', 'Date (DD/MM/YYYY)*', 'Quantité Bidons*',
            'Montant Payé (Ar)', 'Numero DiameX', 'Base DiameX'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        # Exemples
        examples = [
            ['12345678-1234-1234-1234-123456789012', '09/11/2025', 30, 3000, '', ''],
            ['87654321-4321-4321-4321-210987654321', '10/11/2025', 30, 3000, '', ''],
        ]

        for row_num, example in enumerate(examples, 2):
            for col_num, value in enumerate(example, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.fill = example_fill
                cell.border = border

        # Instructions
        ws.cell(row=5, column=1, value="INSTRUCTIONS:").font = Font(bold=True, size=12)
        ws.cell(row=6, column=1, value="1. Les colonnes avec * sont obligatoires")
        ws.cell(row=7, column=1, value="2. ID Carte Sociale: UUID de la carte sociale (voir dans l'application)")
        ws.cell(row=8, column=1, value="3. Date: Format DD/MM/YYYY obligatoire")
        ws.cell(row=9, column=1, value="4. Quantité Bidons: Nombre entier (généralement 30)")
        ws.cell(row=10, column=1, value="5. Montant Payé: Optionnel - peut être vide (sera calculé ultérieurement)")
        ws.cell(row=11, column=1, value="6. Numero DiameX et Base DiameX sont optionnels (peuvent être vides)")
        ws.cell(row=12, column=1, value="7. Supprimez les lignes d'exemple avant import")

        # Ajuster les largeurs
        ws.column_dimensions['A'].width = 40
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 18
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 15

        # Générer le fichier
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"template_import_consos_cartes_sociales.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        wb.save(response)
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_import_consos_excel(request):
    """API pour importer les consommations depuis Excel"""
    try:
        from openpyxl import load_workbook
        from datetime import datetime

        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Aucun fichier fourni'
            }, status=400)

        excel_file = request.FILES['file']

        # Charger le workbook
        wb = load_workbook(excel_file)
        ws = wb.active
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        allowed_ouvrage_ids_str = {str(x) for x in allowed_ouvrage_ids}

        nb_imported = 0
        errors = []

        # Parcourir les lignes (en sautant l'en-tête)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                # Extraire les valeurs
                carte_sociale_id = row[0]
                date_str = row[1]
                quantite_bidons = row[2]
                montant_paye = row[3]
                numero_diamex = row[4] if len(row) > 4 else None
                base_diamex = row[5] if len(row) > 5 else None

                # Validation des champs obligatoires (montant_paye optionnel)
                if not all([carte_sociale_id, date_str, quantite_bidons is not None]):
                    errors.append(f"Ligne {row_num}: Champs obligatoires manquants (ID Carte, Date, Quantité)")
                    continue

                # Convertir la date
                if isinstance(date_str, datetime):
                    date_obj = date_str.date()
                else:
                    # Essayer d'abord DD/MM/YYYY puis YYYY-MM-DD
                    date_obj = None
                    for date_format in ['%d/%m/%Y', '%Y-%m-%d']:
                        try:
                            date_obj = datetime.strptime(str(date_str), date_format).date()
                            break
                        except ValueError:
                            continue

                    if date_obj is None:
                        errors.append(f"Ligne {row_num}: Format de date invalide (attendu: DD/MM/YYYY ou YYYY-MM-DD)")
                        continue

                # Vérifier que la carte existe
                try:
                    carte = CarteSociale.objects.get(id=carte_sociale_id)
                except CarteSociale.DoesNotExist:
                    errors.append(f"Ligne {row_num}: Carte sociale {carte_sociale_id} introuvable")
                    continue
                if str(carte.ouvrage_id) not in allowed_ouvrage_ids_str:
                    errors.append(f"Ligne {row_num}: Carte sociale {carte_sociale_id} non autorisee pour votre organisation")
                    continue

                # Convertir montant_paye (peut être NULL)
                montant_paye_decimal = None
                if montant_paye is not None and str(montant_paye).strip():
                    try:
                        montant_paye_decimal = Decimal(str(montant_paye))
                    except (ValueError, TypeError):
                        pass  # Reste None si conversion échoue

                # Créer la consommation
                ConsoCarteSociale.objects.create(
                    carte_sociale=carte,
                    date=date_obj,
                    quantite_bidons=int(quantite_bidons),
                    montant_paye=montant_paye_decimal,
                    numeroDiameX=str(numero_diamex) if numero_diamex else None,
                    baseDiameX=str(base_diamex) if base_diamex else None
                )

                nb_imported += 1

            except Exception as e:
                errors.append(f"Ligne {row_num}: {str(e)}")
                continue

        return JsonResponse({
            'success': True,
            'nb_imported': nb_imported,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

