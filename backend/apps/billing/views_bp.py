"""
Vues pour la gestion des demandes de branchements privés (BP)
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from datetime import date
from decimal import Decimal
import json

from .bp_branchement_utils import normalize_missing_bp_branchements
from .models import PointEau, TypePointEau
from apps.accounting.models import DiameXTemporaire
from apps.organization.models import Ouvrage
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)
from apps.geography.models import Village
from apps.accounting.models import BaseDiameX
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    from .models import ModaliteGestion

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


def _filter_point_eau_bp_for_user(queryset, user):
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(user)
    if not allowed_ouvrage_ids:
        return queryset.none()
    return queryset.filter(ouvrage_id__in=allowed_ouvrage_ids)


def demandes_bp_list(request):
    """Page de gestion des demandes de branchements privés"""

    # Récupérer tous les points d'eau BP (avec datebranchement vide)
    # et tous les types BP pour le formulaire
    types_bp = TypePointEau.objects.filter(
        Q(nom_type__icontains='privé') | Q(nom_type__icontains='prive') | Q(nom_type__icontains='BP')
    )

    # Récupérer les ouvrages pour le formulaire
    ouvrages = Ouvrage.objects.filter(id__in=_get_allowed_ouvrage_ids(request.user))

    # Récupérer les villages pour le formulaire
    villages = Village.objects.select_related(
        'fokontany__commune__district__region'
    ).all()[:500]  # Limiter pour performance

    context = {
        'types_bp': types_bp,
        'ouvrages': ouvrages,
        'villages': villages,
    }

    return render(request, 'billing/demandes_bp.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_demandes_bp_list(request):
    """API pour recuperer la liste des demandes BP avec filtres"""

    search = request.GET.get('search', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    statut = request.GET.get('statut', 'en_attente')

    demandes = PointEau.objects.filter(
        Q(type_point_eau__nom_type__icontains='BP') |
        Q(type_point_eau__nom_type__icontains='prive')
    ).select_related(
        'type_point_eau',
        'ouvrage',
        'parcelle__village__fokontany__commune'
    )
    demandes = _filter_point_eau_bp_for_user(demandes, request.user)
    normalisations_appliquees = normalize_missing_bp_branchements(demandes)

    if statut == 'en_attente':
        demandes = demandes.filter(datebranchement__isnull=True)
    elif statut == 'branche':
        demandes = demandes.filter(datebranchement__isnull=False)

    if ouvrage_id and ouvrage_id != 'all':
        demandes = demandes.filter(ouvrage_id=ouvrage_id)

    if search:
        demandes = demandes.filter(
            Q(nomabonne__icontains=search) |
            Q(code_point_eau__icontains=search) |
            Q(numeroteleph__icontains=search)
        )

    data = []
    stats = {
        'total': 0,
        'en_attente_paiement_demande': 0,
        'en_attente_paiement_devis': 0,
        'en_attente_branchement': 0,
        'complete': 0
    }

    exports_qs = DiameXTemporaire.objects.filter(statut='en_attente')
    if not request.user.is_superuser:
        organisation_id = _get_user_organisation_id(request.user)
        if not organisation_id:
            exports_qs = exports_qs.none()
        else:
            exports_qs = exports_qs.filter(created_by__base__organisation_id=organisation_id)

    exports_demande = exports_qs.filter(
        description__icontains='Paiement demande BP'
    ).values_list('description', flat=True)
    exports_devis = exports_qs.filter(
        description__icontains='Paiement devis BP'
    ).values_list('description', flat=True)

    abonnes_export_demande = set()
    abonnes_export_devis = set()

    for desc in exports_demande:
        if ' - ' in desc:
            nom_partie = desc.split(' - ')[1]
            if '(' in nom_partie:
                nom_abonne = nom_partie.split('(')[0].strip()
                abonnes_export_demande.add(nom_abonne.lower())

    for desc in exports_devis:
        if ' - ' in desc:
            nom_partie = desc.split(' - ')[1]
            if '(' in nom_partie:
                nom_abonne = nom_partie.split('(')[0].strip()
                abonnes_export_devis.add(nom_abonne.lower())

    for d in demandes:
        if d.datebranchement:
            etape = 'complete'
            stats['complete'] += 1
        elif d.numerodiamexpaiementdevis or d.datepaiementdevis:
            etape = 'en_attente_branchement'
            stats['en_attente_branchement'] += 1
        elif d.numerodiamexdemande or d.datepaiementdemande:
            etape = 'en_attente_paiement_devis'
            stats['en_attente_paiement_devis'] += 1
        else:
            etape = 'en_attente_paiement_demande'
            stats['en_attente_paiement_demande'] += 1

        stats['total'] += 1

        nom_abonne_lower = (d.nomabonne or '').lower()
        a_export_demande_attente = nom_abonne_lower in abonnes_export_demande
        a_export_devis_attente = nom_abonne_lower in abonnes_export_devis

        commune_nom = None
        if d.parcelle and d.parcelle.village and d.parcelle.village.fokontany and d.parcelle.village.fokontany.commune:
            commune_nom = d.parcelle.village.fokontany.commune.nom_commune

        data.append({
            'id': str(d.id),
            'code': d.code_point_eau or '-',
            'nom_abonne': d.nomabonne,
            'telephone': d.numeroteleph or '-',
            'village': d.parcelle.village.nom_village if d.parcelle and d.parcelle.village else '-',
            'commune': commune_nom or 'Sans commune',
            'ouvrage': d.ouvrage.nom_ouvrage if d.ouvrage else '-',
            'montant_demande': float(d.montantdemandepaye) if d.montantdemandepaye else 0,
            'montant_devis': float(d.montantdevispaye) if d.montantdevispaye else 0,
            'numero_diamex_demande': str(d.numerodiamexdemande) if d.numerodiamexdemande else None,
            'base_diamex_demande': d.basediamexdemande or None,
            'date_paiement_demande': d.datepaiementdemande.strftime('%d/%m/%Y') if d.datepaiementdemande else None,
            'numero_diamex_devis': d.numerodiamexpaiementdevis or None,
            'base_diamex_devis': d.basediamexpaiementdevis or None,
            'date_paiement_devis': d.datepaiementdevis.strftime('%d/%m/%Y') if d.datepaiementdevis else None,
            'date_branchement': d.datebranchement.strftime('%d/%m/%Y') if d.datebranchement else None,
            'etape': etape,
            'est_branche': d.datebranchement is not None,
            'export_demande_attente': a_export_demande_attente,
            'export_devis_attente': a_export_devis_attente,
        })

    return JsonResponse({
        'success': True,
        'demandes': data,
        'stats': stats,
        'normalisations_appliquees': normalisations_appliquees,
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_details_pointage_demande_bp(request, point_eau_id):
    """Retourne la demande BP et les lignes comptables 748201 compatibles."""
    try:
        demande = get_object_or_404(
            PointEau.objects.select_related(
                'ouvrage',
                'parcelle__village__fokontany__commune__district__region',
            ),
            id=point_eau_id,
        )

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if allowed_ouvrage_ids and demande.ouvrage_id not in allowed_ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cette demande BP'
            }, status=403)

        ouvrage = demande.ouvrage
        ouvrage_nom = ouvrage.nom_ouvrage if ouvrage else ''

        lignes_qs = BaseDiameX.objects.filter(
            compte_code='748201'
        ).exclude(description__isnull=True).exclude(description='')

        if not request.user.is_superuser:
            organisation_id = _get_user_organisation_id(request.user)
            if not organisation_id:
                lignes_qs = lignes_qs.none()
            else:
                lignes_qs = lignes_qs.filter(
                    prog__in=BaseDiameX.objects.filter(
                        prog__isnull=False
                    ).values_list('prog', flat=True)
                )

        lignes = []
        for entry in lignes_qs:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
            extraction_items = extraction if isinstance(extraction, list) else [extraction]
            matched = False
            extrait_ouvrage_nom = ''
            extrait_ouvrage_id = None
            already_pointed = False
            for item in extraction_items:
                if not isinstance(item, dict):
                    continue
                ouvrage_obj = item.get('ouvrage_obj')
                if ouvrage_obj:
                    extrait_ouvrage_nom = ouvrage_obj.nom_ouvrage
                    extrait_ouvrage_id = str(ouvrage_obj.id)
                    if demande.ouvrage_id and ouvrage_obj.id == demande.ouvrage_id:
                        matched = True
                        break
                elif item.get('ouvrage_nom'):
                    extrait_ouvrage_nom = item.get('ouvrage_nom')

            if ouvrage_nom and extrait_ouvrage_nom:
                if ouvrage_nom.lower() in extrait_ouvrage_nom.lower() or extrait_ouvrage_nom.lower() in ouvrage_nom.lower():
                    matched = True

            numero_diamex = str(entry.id_access).strip() if entry.id_access is not None else ''
            base_diamex = (entry.prog or '').strip()
            if numero_diamex and base_diamex:
                already_pointed = PointEau.objects.filter(
                    numerodiamexdemande=numero_diamex,
                    basediamexdemande=base_diamex,
                ).exclude(id=demande.id).exists()

            if not matched:
                continue

            lignes.append({
                'id': entry.id,
                'id_access': str(entry.id_access) if entry.id_access is not None else '',
                'date_rec': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '-',
                'description': entry.description or '',
                'montant': float(entry.montant_in or 0),
                'prog': entry.prog or '',
                'scan': entry.scan or '',
                'ouvrage_nom': extrait_ouvrage_nom or ouvrage_nom,
                'ouvrage_id': extrait_ouvrage_id,
                'already_pointed': already_pointed,
            })

        lignes.sort(key=lambda x: (x['date_rec'] or '', -x['montant']))

        return JsonResponse({
            'success': True,
            'demande': {
                'id': str(demande.id),
                'code': demande.code_point_eau or '-',
                'nom_abonne': demande.nomabonne or '-',
                'telephone': demande.numeroteleph or '-',
                'ouvrage': ouvrage_nom or '-',
                'village': demande.parcelle.village.nom_village if demande.parcelle and demande.parcelle.village else '-',
                'montant_demande': float(demande.montantdemandepaye or 0),
                'numero_diamex_demande': demande.numerodiamexdemande or None,
                'base_diamex_demande': demande.basediamexdemande or None,
                'date_paiement_demande': demande.datepaiementdemande.strftime('%d/%m/%Y') if demande.datepaiementdemande else None,
            },
            'lignes': lignes,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_pointer_demande_bp(request, point_eau_id):
    """Pointe une ligne comptable 748201 sur une demande BP."""
    try:
        data = json.loads(request.body or '{}')
        ligne_id = data.get('ligne_id')
        if not ligne_id:
            return JsonResponse({
                'success': False,
                'error': 'Ligne comptable manquante'
            }, status=400)

        demande = get_object_or_404(PointEau, id=point_eau_id)
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if allowed_ouvrage_ids and demande.ouvrage_id not in allowed_ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cette demande BP'
            }, status=403)

        try:
            ligne = BaseDiameX.objects.get(id=ligne_id)
        except BaseDiameX.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ligne comptable introuvable'
            }, status=404)

        if (ligne.compte_code or '') != '748201':
            return JsonResponse({
                'success': False,
                'error': 'La ligne selectionnee n\'est pas du compte 748201'
            }, status=400)

        if ligne.id_access is None:
            return JsonResponse({
                'success': False,
                'error': 'ID DiameX introuvable sur la ligne selectionnee'
            }, status=400)
        if not (ligne.prog or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX introuvable sur la ligne selectionnee'
            }, status=400)

        numero_diamex = str(ligne.id_access).strip()
        base_diamex = (ligne.prog or '').strip()
        if PointEau.objects.filter(
            numerodiamexdemande=numero_diamex,
            basediamexdemande=base_diamex,
        ).exclude(id=demande.id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cette ligne comptable est déjà pointée sur une autre demande BP'
            }, status=400)

        extraction = extraire_ouvrage_et_mois_generique(ligne.description or '', ligne.compte_code)
        extraction_items = extraction if isinstance(extraction, list) else [extraction]
        matched = False
        for item in extraction_items:
            if not isinstance(item, dict):
                continue
            ouvrage_obj = item.get('ouvrage_obj')
            if ouvrage_obj and demande.ouvrage_id and ouvrage_obj.id == demande.ouvrage_id:
                matched = True
                break

        if not matched:
            return JsonResponse({
                'success': False,
                'error': 'La ligne comptable ne correspond pas à l\'ouvrage de cette demande'
            }, status=400)

        with transaction.atomic():
            if demande.numerodiamexdemande or demande.basediamexdemande:
                if str(demande.numerodiamexdemande or '').strip() not in ['', numero_diamex] or str(demande.basediamexdemande or '').strip() not in ['', base_diamex]:
                    return JsonResponse({
                        'success': False,
                        'error': 'Cette demande BP est déjà pointée'
                    }, status=400)

            demande.numerodiamexdemande = numero_diamex
            demande.basediamexdemande = base_diamex
            demande.datepaiementdemande = ligne.date_rec or timezone.now().date()
            demande.save(update_fields=['numerodiamexdemande', 'basediamexdemande', 'datepaiementdemande'])

        return JsonResponse({
            'success': True,
            'message': 'Pointage BP appliqué avec succès',
            'numero_diamex': str(ligne.id_access),
            'base_diamex': (ligne.prog or '').strip(),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_bp_create(request):
    """API pour créer une nouvelle demande BP"""

    try:
        data = json.loads(request.body)

        # Récupérer le type BP
        type_bp = TypePointEau.objects.filter(
            Q(nom_type__icontains='privé') | Q(nom_type__icontains='prive')
        ).first()

        if not type_bp:
            return JsonResponse({
                'success': False,
                'error': 'Type BP non trouvé. Veuillez créer un type "Branchement Privé" dans les types de points d\'eau.'
            }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        ouvrage_id = data.get('ouvrage_id')
        if not ouvrage_id or str(ouvrage_id) not in [str(x) for x in allowed_ouvrage_ids]:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non autorise pour votre organisation.'
            }, status=403)

        # Créer le point d'eau
        point_eau = PointEau.objects.create(
            nomabonne=data.get('nom_abonne'),
            numeroteleph=data.get('telephone', ''),
            contactabonne=data.get('telephone', ''),
            ouvrage_id=data.get('ouvrage_id'),
            type_point_eau=type_bp,
            parcelle_id=data.get('parcelle_id') if data.get('parcelle_id') else None,
            typeabonne='particulier',
            montant_demande_bp=data.get('montant_demande', 0),
            latitude=data.get('latitude') if data.get('latitude') else None,
            longitude=data.get('longitude') if data.get('longitude') else None,
            # datebranchement reste NULL (demande en attente)
        )

        return JsonResponse({
            'success': True,
            'message': 'Demande BP créée avec succès',
            'id': str(point_eau.id)
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_bp_update(request, demande_id):
    """API pour mettre à jour une demande BP"""

    try:
        demande = get_object_or_404(_filter_point_eau_bp_for_user(PointEau.objects.all(), request.user), id=demande_id)
        data = json.loads(request.body)

        # Mettre à jour les champs
        demande.nomabonne = data.get('nom_abonne', demande.nomabonne)
        demande.numeroteleph = data.get('telephone', demande.numeroteleph)
        demande.contactabonne = data.get('telephone', demande.contactabonne)
        demande.montant_demande_bp = data.get('montant_demande', demande.montant_demande_bp)
        demande.typeabonne = 'particulier'

        if data.get('latitude'):
            demande.latitude = data.get('latitude')
        if data.get('longitude'):
            demande.longitude = data.get('longitude')

        demande.save()

        return JsonResponse({'success': True, 'message': 'Demande mise à jour'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_bp_exporter(request, demande_id):
    """API pour exporter une demande BP vers DiameXTemporaire (paiement demande ou devis)"""

    try:
        demande = get_object_or_404(_filter_point_eau_bp_for_user(PointEau.objects.all(), request.user), id=demande_id)

        # Récupérer le type d'export depuis le body
        data = json.loads(request.body) if request.body else {}
        type_export = data.get('type_export', 'demande_bp')  # Par défaut: paiement demande

        # Vérifier qu'il y a un montant
        if not demande.montant_demande_bp or demande.montant_demande_bp <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Le montant de la demande doit être supérieur à 0'
            }, status=400)

        # Déterminer le type de ticket et la désignation
        if type_export == 'devis_bp':
            # Export paiement devis (paiement 2)
            if not demande.numerodiamexdemande:
                return JsonResponse({
                    'success': False,
                    'error': 'Le paiement de la demande doit être effectué avant d\'exporter le devis'
                }, status=400)

            if DiameXTemporaire.objects.filter(
                planning_detail__isnull=True,  # Pas de planning detail pour BP
                description__icontains=f"devis BP - {demande.nomabonne}"
            ).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Le devis a déjà été exporté'
                }, status=400)

            numero_ticket = f"BP-DEV-{demande.code_point_eau or str(demande.id)[:8]}"
            description = f"Paiement devis BP - {demande.nomabonne}"
            type_transaction = 'recette'
        else:
            # Export paiement demande (paiement 1)
            if DiameXTemporaire.objects.filter(
                planning_detail__isnull=True,
                description__icontains=f"demande BP - {demande.nomabonne}"
            ).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'La demande a déjà été exportée'
                }, status=400)

            numero_ticket = f"BP-DEM-{demande.code_point_eau or str(demande.id)[:8]}"
            description = f"Paiement demande BP - {demande.nomabonne}"
            type_transaction = 'recette'

        # Créer la ligne dans DiameXTemporaire
        DiameXTemporaire.objects.create(
            rec=int(numero_ticket.split('-')[-1][:8], 36) if numero_ticket else None,  # Convertir en nombre
            type_transaction=type_transaction,
            description=description,
            montant_in=float(demande.montant_demande_bp) if demande.montant_demande_bp else 0,
            montant_out=0,
            date_rec=date.today(),
            statut='en_attente',
            created_by=request.user.employe if hasattr(request.user, 'employe') else None
        )

        message = 'Paiement devis exporté' if type_export == 'devis_bp' else 'Paiement demande exporté'
        return JsonResponse({
            'success': True,
            'message': f'{message} vers la table temporaire DiameX'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["GET"])
def api_lignes_diamex_list(request):
    """API pour lister les lignes en attente dans DiameXTemporaire"""

    lignes = DiameXTemporaire.objects.filter(
        planning_detail__isnull=True,
        description__icontains='BP',
        statut='en_attente'
    )
    if not request.user.is_superuser:
        organisation_id = _get_user_organisation_id(request.user)
        if not organisation_id:
            lignes = lignes.none()
        else:
            lignes = lignes.filter(created_by__base__organisation_id=organisation_id)

    lignes = lignes.order_by('-created_at')[:100]

    data = []
    for ligne in lignes:
        data.append({
            'id': ligne.id,
            'numero_ticket': str(ligne.rec) if ligne.rec else '-',
            'type_ticket': ligne.get_type_transaction_display(),
            'designation': ligne.description,
            'montant': float(ligne.montant_in),
            'date_ticket': ligne.date_rec.strftime('%d/%m/%Y') if ligne.date_rec else '-',
            'nom_abonne': ligne.description.split(' - ')[-1] if ligne.description else '-',
            'statut': ligne.get_statut_display(),
        })

    return JsonResponse({'success': True, 'lignes': data})


