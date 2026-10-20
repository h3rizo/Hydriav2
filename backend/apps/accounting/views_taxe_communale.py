from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import datetime
from apps.accounting.models import BaseDiameX
from apps.organization.models import Base, Compte, Ouvrage, Organisation
from apps.billing.models import PointEau
from apps.geography.models import Region, District, Commune
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
from apps.employees.permissions import filter_queryset_by_permissions, is_visiteur
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
    get_user_organisation,
)
from collections import defaultdict
import logging
import json
from django.http import JsonResponse
from decimal import Decimal
from apps.accounting.models import BaseDiameX, RemboursementCommune, InfoPaiementTaxeCommune, ImputationRemboursementTaxeCommune

logger = logging.getLogger(__name__)


def _to_float_amount(value):
    """Normalize DiameX amounts before mixing them with float-based tax rates."""
    if value is None:
        return 0.0
    return float(value)

def _get_allowed_organisation_ids(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if getattr(user, 'is_superuser', False) or is_visiteur(user):
        return None

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return None
    return [str(_id) for _id in gestionnaire_ids]


def _get_default_organisation_id(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    if getattr(user, 'is_superuser', False) or is_visiteur(user):
        return ''

    organisation = get_user_organisation(user)
    if not organisation:
        return ''

    if organisation.type_organisation == Organisation.TYPE_GESTIONNAIRE:
        return str(organisation.id)

    if organisation.type_organisation == Organisation.TYPE_PARTENAIRE:
        first_gestionnaire = _get_organisations_for_filter(user).first()
        return str(first_gestionnaire.id) if first_gestionnaire else ''

    return ''


def _resolve_organisation_filter(user, requested_organisation_id, parameter_present=False):
    requested = (requested_organisation_id or '').strip()
    if requested == 'all':
        requested = ''

    allowed_ids = _get_allowed_organisation_ids(user)
    default_organisation_id = _get_default_organisation_id(user)

    if not parameter_present:
        return default_organisation_id

    if allowed_ids is None:
        return requested

    if requested and requested not in allowed_ids:
        return default_organisation_id

    return requested


def _get_organisations_for_filter(user):
    allowed_organisation_ids = _get_allowed_organisation_ids(user)

    if getattr(user, 'is_superuser', False) or is_visiteur(user):
        return Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
    if allowed_organisation_ids is None:
        return Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')
    if allowed_organisation_ids:
        return Organisation.objects.filter(
            id__in=allowed_organisation_ids,
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        ).order_by('nom_organisation')

    return Organisation.objects.none()


def _get_dashboard_ouvrages_scope(user, region_id=None, district_id=None, commune_ids=None, organisation_id=None):
    """
    Reprend la base de comptage du dashboard principal:
    - permissions utilisateur
    - uniquement les ouvrages avec au moins un point d'eau
    - exclusion des ouvrages suspendus/potentiels
    - filtre organisation identique au dashboard
    - filtres géographiques optionnels
    """
    ouvrages_qs = filter_queryset_by_permissions(Ouvrage.objects.all(), user).filter(
        pointeau__isnull=False
    ).exclude(
        Q(type_ouvrage__nom_type_ouvrage__icontains='suspend') |
        Q(type_ouvrage__nom_type_ouvrage__icontains='potentiel')
    ).distinct()

    if organisation_id and organisation_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(
            modalites_gestion__statut='actif',
            modalites_gestion__gestionnaire_id=organisation_id,
            modalites_gestion__date_fin__isnull=True
        )

    if region_id:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_ids:
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune_id__in=commune_ids
        )

    ouvrages_qs = ouvrages_qs.distinct()

    # CRITICAL: Scope "Base" - Chaque personne voit les ouvrages de sa base
    if not user.is_superuser:
        from apps.employees.permissions import is_directeur_poste
        if not is_directeur_poste(user):
            employe = getattr(user, 'employe', None)
            if employe and employe.base_id:
                from apps.organization.scoping import get_same_base_active_employe_ids
                from apps.employees.models import EmployeOuvrages
                
                # Récupérer tous les employés de la même base
                all_base_employe_ids = get_same_base_active_employe_ids(employe)
                
                # Récupérer les IDs des ouvrages dont ces employés sont responsables
                allowed_ids = set(
                    EmployeOuvrages.objects.filter(
                        employe_id__in=all_base_employe_ids
                    ).filter(
                        Q(date_fin__isnull=True) | Q(date_fin__gte=datetime.now())
                    ).values_list('ouvrage_id', flat=True)
                )
                
                # Filtrer le queryset original par ces IDs
                ouvrages_qs = ouvrages_qs.filter(id__in=allowed_ids)
            else:
                # Si pas d'employé ou pas de base, on applique le scope standard (souvent vide ou restreint)
                scoped_ids = apply_user_responsable_ouvrage_scope(
                    set(ouvrages_qs.values_list('id', flat=True)),
                    user,
                )
                if scoped_ids is not None:
                    ouvrages_qs = ouvrages_qs.filter(id__in=scoped_ids)

    return ouvrages_qs.distinct()


def _get_diamex_scope_for_user(user):
    """
    Scope DiameX pour les workflows fiscaux:
    - superuser: tout
    - utilisateur standard: organisation (imported_by) + fallback prog DiameX
    - fallback final: lignes importees par l'employe
    """
    qs = BaseDiameX.objects.all()

    if getattr(user, 'is_superuser', False):
        return qs

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    employe = getattr(user, 'employe', None)

    if gestionnaire_ids:
        allowed_progs = list(
            Base.objects.filter(organisation_id__in=gestionnaire_ids)
            .exclude(prog_diamex__isnull=True)
            .exclude(prog_diamex='')
            .values_list('prog_diamex', flat=True)
            .distinct()
        )

        scope_q = Q(imported_by__base__organisation_id__in=gestionnaire_ids)
        if allowed_progs:
            scope_q |= Q(prog__in=allowed_progs)
        return qs.filter(scope_q).distinct()

    if employe:
        return qs.filter(imported_by=employe)

    return qs.none()

def get_commune_from_ouvrage_or_pe(
    ouvrage_obj,
    point_eau_obj=None,
    point_eau_idxls=None,
    ouvrage_point_map=None,
    ouvrage_idxls_map=None,
):
    """
    Tente de retrouver la commune associée à un ouvrage ou un point d'eau.
    Stratégie:
    1. Si PointEau fourni, remonter via Parcelle -> Village -> Fokontany -> Commune
    2. Si Ouvrage fourni, chercher un PointEau rattaché et faire de même
    """
    pe = point_eau_obj
    
    # Si pas de PE mais qu'on a un IDxls et un Ouvrage, essayer de le trouver
    if not pe and ouvrage_obj and point_eau_idxls:
        if ouvrage_idxls_map is not None:
            pe = ouvrage_idxls_map.get((str(ouvrage_obj.id), str(point_eau_idxls)))
        else:
            pe = PointEau.objects.filter(ouvrage=ouvrage_obj, idxls=point_eau_idxls).first()
        
    # Si toujours pas de PE mais Ouvrage, prendre le premier PE de cet ouvrage (approximation géographique)
    if not pe and ouvrage_obj:
        if ouvrage_point_map is not None:
            pe = ouvrage_point_map.get(str(ouvrage_obj.id))
        else:
            pe = PointEau.objects.filter(ouvrage=ouvrage_obj).first()
        
    if pe and pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany and pe.parcelle.village.fokontany.commune:
        return pe.parcelle.village.fokontany.commune
        
    return None


def _build_taxe_communale_scope_context(
    user,
    annee,
    organisation_filter='',
    region_id=None,
    district_id=None,
    commune_ids=None,
):
    ouvrages_scope = _get_dashboard_ouvrages_scope(
        user,
        region_id=region_id,
        district_id=district_id,
        commune_ids=commune_ids,
        organisation_id=organisation_filter,
    )
    allowed_ouvrage_ids = list(ouvrages_scope.values_list('id', flat=True))
    allowed_ouvrage_ids_str = {str(x) for x in allowed_ouvrage_ids}

    points_ouvrages_scope = PointEau.objects.filter(
        ouvrage_id__in=allowed_ouvrage_ids,
        parcelle__village__fokontany__commune__isnull=False
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune',
        'parcelle__village__fokontany__commune__district',
        'parcelle__village__fokontany__commune__district__region',
    ).order_by(
        'parcelle__village__fokontany__commune__nom_commune',
        'ouvrage__nom_ouvrage',
        'id',
    )

    description_scope_hints = set()
    ouvrage_point_map = {}
    ouvrage_idxls_map = {}
    for point in points_ouvrages_scope:
        if point.ouvrage and point.ouvrage.nom_ouvrage:
            description_scope_hints.add(point.ouvrage.nom_ouvrage.strip())
        if point.idxls:
            description_scope_hints.add(str(point.idxls).strip())
        commune_obj = getattr(getattr(getattr(point.parcelle, 'village', None), 'fokontany', None), 'commune', None)
        if commune_obj and commune_obj.nom_commune:
            description_scope_hints.add(commune_obj.nom_commune.strip())
        if point.ouvrage_id and str(point.ouvrage_id) not in ouvrage_point_map:
            ouvrage_point_map[str(point.ouvrage_id)] = point
        if point.ouvrage_id and point.idxls:
            ouvrage_idxls_map[(str(point.ouvrage_id), str(point.idxls))] = point

    entries = _get_diamex_scope_for_user(user).filter(
        compte_code__in=['707401', '748411', '761000'],
        date_rec__isnull=False,
        date_rec__year=annee
    )

    if organisation_filter:
        allowed_progs = Base.objects.filter(
            organisation_id=organisation_filter
        ).exclude(
            prog_diamex__isnull=True
        ).exclude(
            prog_diamex=''
        ).values_list('prog_diamex', flat=True)
        entries = entries.filter(
            Q(imported_by__base__organisation_id=organisation_filter) |
            Q(prog__in=list(allowed_progs))
        ).distinct()

    if (region_id or district_id or commune_ids) and description_scope_hints:
        hint_values = [hint for hint in description_scope_hints if hint and len(hint) >= 3][:80]
        if hint_values:
            description_scope_q = Q()
            for hint in hint_values:
                description_scope_q |= Q(description__icontains=hint)
            entries = entries.filter(description_scope_q)

    return {
        'entries': entries.order_by('date_rec'),
        'allowed_ouvrage_ids_str': allowed_ouvrage_ids_str,
        'ouvrage_point_map': ouvrage_point_map,
        'ouvrage_idxls_map': ouvrage_idxls_map,
    }


def _compute_commune_taxe_brute_for_year(commune_obj, scope_context):
    if not commune_obj:
        return 0.0

    total_taxe = 0.0
    for entry in scope_context['entries']:
        montant = float(entry.montant_in or 0)
        if montant <= 0:
            continue

        if entry.compte_code == '761000':
            description_lower = (entry.description or '').lower()
            if 'réclamation' not in description_lower and 'reclamation' not in description_lower:
                continue

        segments = []
        if entry.compte_code == '707401' and entry.description and ';' in entry.description:
            try:
                sub_segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in
                )
                for seg in sub_segments or []:
                    segments.append({
                        'montant': _to_float_amount(seg.get('montant')),
                        'extraction': seg['extraction'],
                    })
            except Exception as e:
                logger.error(f"Erreur division multi {entry.id}: {e}")

        if not segments:
            segments.append({
                'montant': montant,
                'extraction': extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code),
            })

        for seg in segments:
            ext = seg['extraction']
            ouvrage_obj = ext.get('ouvrage_obj')
            point_eau_obj = ext.get('point_eau_obj')
            point_eau_idxls = ext.get('point_eau_idxls')

            if ouvrage_obj and str(ouvrage_obj.id) not in scope_context['allowed_ouvrage_ids_str']:
                continue
            if point_eau_obj and point_eau_obj.ouvrage_id and str(point_eau_obj.ouvrage_id) not in scope_context['allowed_ouvrage_ids_str']:
                continue
            if not ouvrage_obj and point_eau_obj and point_eau_obj.ouvrage_id:
                ouvrage_obj = point_eau_obj.ouvrage

            commune = get_commune_from_ouvrage_or_pe(
                ouvrage_obj,
                point_eau_obj,
                point_eau_idxls,
                ouvrage_point_map=scope_context['ouvrage_point_map'],
                ouvrage_idxls_map=scope_context['ouvrage_idxls_map'],
            )
            if not commune or commune.id != commune_obj.id:
                continue

            if entry.compte_code in ['707401', '748411']:
                total_taxe += seg['montant'] * 0.07
            elif entry.compte_code == '761000':
                total_taxe += seg['montant'] * 0.50

    return float(total_taxe)

@login_required
def etat_taxes_communales(request):
    """
    Génère l'état des taxes communales à payer.
    Comptes concernés:
    - 707401 (Recettes vente d'eau par bidon / volume) -> 7%
    - 748411 (Recettes forfaitaires) -> 7%
    - 761000 (Recettes exceptionnelles / Divers) -> 50%

    CRITICAL: Pour le compte 761000, seules les transactions dont la description
    contient le mot "réclamation" (avec ou sans accent, insensible à la casse) sont
    prises en compte dans le calcul des taxes. Les autres transactions de ce compte
    sont ignorées.
    """
    if request.method == 'POST' and request.headers.get('Content-Type') == 'application/json':
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'add_remboursement':
            try:
                commune_id = data.get('commune_id')
                date_remb = data.get('date')
                designation = data.get('designation')
                montant = Decimal(str(data.get('montant', 0)))
                if montant > 0:
                    montant = -montant
                annee_remb = int(data.get('annee'))
                
                RemboursementCommune.objects.create(
                    commune_id=commune_id,
                    date_remboursement=date_remb,
                    designation=designation,
                    montant=montant,
                    annee=annee_remb,
                    created_by=getattr(request.user, 'employe', None)
                )
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})

        if action == 'delete_remboursement':
            try:
                remb_id = data.get('remboursement_id')
                RemboursementCommune.objects.filter(id=remb_id).delete()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})

        if action == 'update_info_paiement':
            try:
                commune_id = data.get('commune_id')
                mode = data.get('mode_paiement')
                num = data.get('numero_compte')
                org_id = _get_default_organisation_id(request.user)

                InfoPaiementTaxeCommune.objects.update_or_create(
                    commune_id=commune_id,
                    organisation_id=org_id if org_id else None,
                    defaults={
                        'mode_paiement': mode,
                        'numero_compte': num
                    }
                )
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})

        if action == 'update_imputation_remboursement':
            try:
                commune_id = data.get('commune_id')
                montant_impute = abs(Decimal(str(data.get('montant_impute', 0) or 0)))
                annee_imputation = int(data.get('annee', datetime.now().year))
                org_id = _get_default_organisation_id(request.user)

                ImputationRemboursementTaxeCommune.objects.update_or_create(
                    commune_id=commune_id,
                    organisation_id=org_id if org_id else None,
                    annee=annee_imputation,
                    defaults={
                        'montant_impute': montant_impute
                    }
                )
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})

    # Filtres de date (par défaut année courante)
    annee = request.GET.get('annee', datetime.now().year)
    try:
        annee = int(annee)
    except ValueError:
        annee = datetime.now().year
    
    # Filtres géographiques
    region_id = request.GET.get('region_id')
    district_id = request.GET.get('district_id')
    commune_ids = request.GET.getlist('commune_id')  # Pour multi-sélection
    organisation_filter = _get_default_organisation_id(request.user)

    ouvrages_scope_filters = _get_dashboard_ouvrages_scope(
        request.user,
        organisation_id=organisation_filter,
    )
    points_scope = PointEau.objects.filter(ouvrage__in=ouvrages_scope_filters)
    region_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district__region_id',
        flat=True
    ).distinct()
    district_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district_id',
        flat=True
    ).distinct()
    commune_ids_scope = points_scope.values_list(
        'parcelle__village__fokontany__commune_id',
        flat=True
    ).distinct()

    all_regions = Region.objects.filter(id__in=region_ids).order_by('nom_region')
    if region_id:
        all_districts = District.objects.filter(
            region_id=region_id,
            id__in=district_ids
        ).order_by('nom_district')
    else:
        all_districts = District.objects.filter(id__in=district_ids).order_by('nom_district')

    if district_id:
        all_communes = Commune.objects.filter(
            district_id=district_id,
            id__in=commune_ids_scope
        ).order_by('nom_commune')
    elif region_id:
        all_communes = Commune.objects.filter(
            district__region_id=region_id,
            id__in=commune_ids_scope
        ).order_by('nom_commune')
    else:
        all_communes = Commune.objects.filter(id__in=commune_ids_scope).order_by('nom_commune')

    ouvrages_scope = _get_dashboard_ouvrages_scope(
        request.user,
        region_id=region_id,
        district_id=district_id,
        commune_ids=commune_ids,
        organisation_id=organisation_filter,
    )
    allowed_ouvrage_ids = list(ouvrages_scope.values_list('id', flat=True))
    allowed_ouvrage_ids_str = {str(x) for x in allowed_ouvrage_ids}
        
    # Comptes cibles
    comptes_7_pourcent = ['707401', '748411']
    comptes_50_pourcent = ['761000']
    tous_comptes = comptes_7_pourcent + comptes_50_pourcent
    
    # Récupérer les transactions (filtrées par scope utilisateur/organisation)
    entries = _get_diamex_scope_for_user(request.user).filter(
        compte_code__in=tous_comptes,
        date_rec__isnull=False,
        date_rec__year=annee
    )
    
    # Appliquer le filtre d'organisation si sélectionné
    if organisation_filter:
        allowed_progs = Base.objects.filter(organisation_id=organisation_filter).exclude(prog_diamex__isnull=True).exclude(prog_diamex='').values_list('prog_diamex', flat=True)
        entries = entries.filter(
            Q(imported_by__base__organisation_id=organisation_filter) |
            Q(prog__in=list(allowed_progs))
        ).distinct()
        
    entries = entries.order_by('date_rec')
    
    # Structure de données pour le rapport
    rapport = defaultdict(lambda: {
        'commune': None, 
        'ouvrages': defaultdict(lambda: {
            'ouvrage_id': None,
            'nom_ouvrage': '',
            'comptes': {},  # Structure: { '707401': { 'code':..., 'montant':..., 'taxe':... } }
            'details': []
        }),
        'total_taxe': 0
    })

    # Précharger les ouvrages du périmètre dashboard pour afficher aussi les ouvrages sans paiement.
    points_ouvrages_scope = PointEau.objects.filter(
        ouvrage_id__in=allowed_ouvrage_ids,
        parcelle__village__fokontany__commune__isnull=False
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune',
        'parcelle__village__fokontany__commune__district',
        'parcelle__village__fokontany__commune__district__region',
    ).order_by(
        'parcelle__village__fokontany__commune__nom_commune',
        'ouvrage__nom_ouvrage',
        'id',
    )

    # Réduire fortement le nombre d'écritures à parser quand un filtre géographique est actif.
    # On construit des indices textuels simples depuis le périmètre sélectionné.
    description_scope_hints = set()
    for point in points_ouvrages_scope:
        if point.ouvrage and point.ouvrage.nom_ouvrage:
            description_scope_hints.add(point.ouvrage.nom_ouvrage.strip())
        if point.idxls:
            description_scope_hints.add(str(point.idxls).strip())
        commune_obj = getattr(getattr(getattr(point.parcelle, 'village', None), 'fokontany', None), 'commune', None)
        if commune_obj and commune_obj.nom_commune:
            description_scope_hints.add(commune_obj.nom_commune.strip())

    if (region_id or district_id or commune_ids) and description_scope_hints:
        hint_values = [hint for hint in description_scope_hints if hint and len(hint) >= 3][:80]
        if hint_values:
            description_scope_q = Q()
            for hint in hint_values:
                description_scope_q |= Q(description__icontains=hint)
            entries = entries.filter(description_scope_q)

    seen_commune_ouvrage_pairs = set()
    ouvrages_uniques_scope = set()
    ouvrage_point_map = {}
    ouvrage_idxls_map = {}
    for point in points_ouvrages_scope:
        if not point.ouvrage_id or not point.parcelle_id:
            continue
        village = getattr(point.parcelle, 'village', None)
        fokontany = getattr(village, 'fokontany', None)
        commune = getattr(fokontany, 'commune', None)
        if not commune:
            continue

        commune_key = str(commune.id)
        ouvrage_key = f"ouvrage:{point.ouvrage_id}"
        pair_key = (commune_key, ouvrage_key)
        ouvrage_id_str = str(point.ouvrage_id)
        if ouvrage_id_str not in ouvrage_point_map:
            ouvrage_point_map[ouvrage_id_str] = point
        if point.idxls:
            ouvrage_idxls_map[(ouvrage_id_str, str(point.idxls))] = point
        if pair_key in seen_commune_ouvrage_pairs:
            continue

        seen_commune_ouvrage_pairs.add(pair_key)
        ouvrages_uniques_scope.add(str(point.ouvrage_id))

        rap_comm = rapport[commune_key]
        if not rap_comm['commune']:
            rap_comm['commune'] = commune

        ouvrage_data = rap_comm['ouvrages'][ouvrage_key]
        ouvrage_data['ouvrage_id'] = str(point.ouvrage_id)
        ouvrage_data['nom_ouvrage'] = point.ouvrage.nom_ouvrage if point.ouvrage else 'Inconnu'

    yearly_scope_cache = {
        annee: {
            'entries': entries,
            'allowed_ouvrage_ids_str': allowed_ouvrage_ids_str,
            'ouvrage_point_map': ouvrage_point_map,
            'ouvrage_idxls_map': ouvrage_idxls_map,
        }
    }
    
    entries_inconnues = [] # Pour ce qui n'a pas de commune identifiée
    
    for entry in entries:
        montant = float(entry.montant_in or 0)
        if montant <= 0:
            continue

        if not entry.date_rec or entry.date_rec.year != annee:
            continue

        # CRITICAL: Pour le compte 761000, ne prendre que les lignes avec "réclamation" dans la description
        if entry.compte_code == '761000':
            description_lower = (entry.description or '').lower()
            if 'réclamation' not in description_lower and 'reclamation' not in description_lower:
                continue
            
        segments = []
        is_volume_multi = False
        
        if entry.compte_code == '707401' and entry.description and ';' in entry.description:
            try:
                sub_segments = diviser_paiement_volume_multi(
                    entry.description, 
                    entry.compte_code, 
                    entry.montant_in
                )
                if sub_segments:
                    is_volume_multi = True
                    for seg in sub_segments:
                        extraction = seg['extraction']
                        segments.append({
                            'montant': _to_float_amount(seg.get('montant')),
                            'extraction': extraction,
                            'description': seg['description_partielle']
                        })
            except Exception as e:
                logger.error(f"Erreur division multi {entry.id}: {e}")
        
        if not is_volume_multi:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
            segments.append({
                'montant': montant,
                'extraction': extraction,
                'description': entry.description
            })
            
        for seg in segments:
            ext = seg['extraction']
            montant_seg = seg['montant']
            desc_seg = seg['description']
            
            ouvrage_obj = ext.get('ouvrage_obj')
            ouvrage_nom = ext.get('ouvrage_nom') or "Inconnu"
            if ouvrage_obj:
                if str(ouvrage_obj.id) not in allowed_ouvrage_ids_str:
                    continue
                ouvrage_nom = ouvrage_obj.nom_ouvrage
                
            point_eau_obj = ext.get('point_eau_obj')
            point_eau_idxls = ext.get('point_eau_idxls')

            if point_eau_obj and point_eau_obj.ouvrage_id and str(point_eau_obj.ouvrage_id) not in allowed_ouvrage_ids_str:
                continue
            if not ouvrage_obj and point_eau_obj and point_eau_obj.ouvrage_id:
                ouvrage_obj = point_eau_obj.ouvrage
                ouvrage_nom = ouvrage_obj.nom_ouvrage if ouvrage_obj else ouvrage_nom
            
            commune = get_commune_from_ouvrage_or_pe(
                ouvrage_obj,
                point_eau_obj,
                point_eau_idxls,
                ouvrage_point_map=ouvrage_point_map,
                ouvrage_idxls_map=ouvrage_idxls_map,
            )
            
            taux = 0
            is_7pc = entry.compte_code in comptes_7_pourcent
            is_50pc = entry.compte_code in comptes_50_pourcent
            
            taxe = 0
            if is_7pc:
                taux = 0.07
                taxe = montant_seg * taux
            elif is_50pc:
                taux = 0.50
                taxe = montant_seg * taux
                
            entry_detail = {
                'date': entry.date_rec.strftime('%d/%m/%Y'),
                'description': desc_seg,
                'montant': montant_seg,
                'compte': entry.compte_code,
                'taxe': taxe,
                'taux_str': '7%' if is_7pc else '50%' if is_50pc else '0%'
            }

            if commune:
                commune_key = str(commune.id)
                rap_comm = rapport[commune_key]
                if not rap_comm['commune']:
                    rap_comm['commune'] = commune

                ouvrage_key = f"ouvrage:{ouvrage_obj.id}" if ouvrage_obj else f"nom:{ouvrage_nom}"
                ouvrage_data = rap_comm['ouvrages'][ouvrage_key]
                if not ouvrage_data['nom_ouvrage']:
                    ouvrage_data['nom_ouvrage'] = ouvrage_nom
                if ouvrage_obj and not ouvrage_data['ouvrage_id']:
                    ouvrage_data['ouvrage_id'] = str(ouvrage_obj.id)
                
                compte_code = entry.compte_code
                if compte_code not in ouvrage_data['comptes']:
                    labels = {
                        '707401': "Vente eau (Volume)",
                        '748411': "Forfait",
                        '761000': "Divers"
                    }
                    ouvrage_data['comptes'][compte_code] = {
                        'code': compte_code,
                        'label': labels.get(compte_code, f"Compte {compte_code}"),
                        'montant': 0,
                        'taxe': 0,
                        'taux': taux,
                        'taux_str': f"{int(taux*100)}%",
                        'details': []
                    }
                
                acc_data = ouvrage_data['comptes'][compte_code]
                acc_data['montant'] += montant_seg
                acc_data['taxe'] += taxe
                acc_data['details'].append(entry_detail)
                    
                rap_comm['total_taxe'] += taxe
            else:
                entries_inconnues.append({
                    'ouvrage_nom': ouvrage_nom,
                    'commune': None,
                    **entry_detail
                })

    commune_id_filter = request.GET.get('print_commune_id')
    rapport_list = []
    
    sorted_communes = sorted(rapport.keys(), key=lambda k: rapport[k]['commune'].nom_commune if rapport[k]['commune'] else '')
    
    for commune_key in sorted_communes:
        commune_data = rapport[commune_key]
        commune_obj = commune_data['commune']
        
        if not commune_obj and commune_id_filter:
            continue
            
        if commune_id_filter and commune_key != str(commune_id_filter):
            continue
        if region_id and commune_obj and str(commune_obj.district.region_id) != str(region_id):
            continue
        if district_id and commune_obj and str(commune_obj.district_id) != str(district_id):
            continue
        if commune_ids and commune_obj and str(commune_obj.id) not in commune_ids:
            continue

        ouvrages_dict = {}
        sorted_ouvrages = sorted(
            commune_data['ouvrages'].items(),
            key=lambda item: (
                (item[1].get('nom_ouvrage') or '').lower(),
                item[0],
            )
        )
        for ouvrage_key, data_ouv in sorted_ouvrages:
            comptes_dict = {}
            for code_c, data_c in sorted(data_ouv['comptes'].items()):
                data_c['details_json'] = json.dumps(data_c['details'])
                comptes_dict[code_c] = data_c

            ouvrage_dict = dict(data_ouv)
            ouvrage_dict['comptes'] = comptes_dict
            ouvrages_dict[ouvrage_key] = ouvrage_dict
            
        total_taxe_raw = commune_data['total_taxe']
        
        # Soustraire les remboursements
        remboursements = RemboursementCommune.objects.filter(
            commune=commune_obj,
            annee=annee
        )
        total_remboursements = sum(float(r.montant) for r in remboursements)
        remboursements_cumules = RemboursementCommune.objects.filter(
            commune=commune_obj,
            annee__lte=annee
        ).order_by('annee', 'date_remboursement', 'created_at')
        total_remboursements_avant = sum(float(r.montant) for r in remboursements_cumules if r.annee < annee)
        total_remboursements_cumules = sum(float(r.montant) for r in remboursements_cumules)

        total_taxes_brutes_avant = 0.0
        for annee_historique in sorted({r.annee for r in remboursements_cumules if r.annee < annee}):
            if annee_historique not in yearly_scope_cache:
                yearly_scope_cache[annee_historique] = _build_taxe_communale_scope_context(
                    request.user,
                    annee_historique,
                    organisation_filter=organisation_filter,
                    region_id=region_id,
                    district_id=district_id,
                    commune_ids=commune_ids,
                )
            total_taxes_brutes_avant += _compute_commune_taxe_brute_for_year(
                commune_obj,
                yearly_scope_cache[annee_historique],
            )

        # Infos paiement (désormais permanent par commune)
        info_paiement = InfoPaiementTaxeCommune.objects.filter(
            commune=commune_obj,
            organisation_id=organisation_filter if organisation_filter else None
        ).first()
        imputation_annuelle = ImputationRemboursementTaxeCommune.objects.filter(
            commune=commune_obj,
            organisation_id=organisation_filter if organisation_filter else None,
            annee=annee
        ).first()
        
        # Convention de signe:
        # - montant negatif => Hydria doit encore ce montant a la commune
        # - montant positif => regularisation en sens inverse
        solde_net_reporte_avant_annee = total_remboursements_avant + total_taxes_brutes_avant
        solde_reporte_avant_annee = abs(min(0, solde_net_reporte_avant_annee))
        solde_net_avant_imputation = solde_net_reporte_avant_annee + total_remboursements
        total_disponible_a_rembourser = abs(min(0, solde_net_avant_imputation))
        if imputation_annuelle:
            montant_imputation_saisi = max(0, float(imputation_annuelle.montant_impute))
            montant_rembourse_cette_annee = min(total_taxe_raw, total_disponible_a_rembourser, montant_imputation_saisi)
        else:
            montant_imputation_saisi = total_disponible_a_rembourser
            montant_rembourse_cette_annee = min(total_taxe_raw, total_disponible_a_rembourser)

        montant_rembourse_reporte = max(0, total_disponible_a_rembourser - montant_rembourse_cette_annee)
        total_taxe_apres_remb = max(0, total_taxe_raw - montant_rembourse_cette_annee)
        total_taxe_rounded = round(total_taxe_apres_remb / 100) * 100
        
        rapport_list.append({
            'commune': commune_obj,
            'ouvrages': ouvrages_dict,
            'remboursements': remboursements,
            'total_remboursements': total_remboursements,
            'total_remboursements_avant': total_remboursements_avant,
            'total_remboursements_cumules': total_remboursements_cumules,
            'total_taxes_brutes_avant': total_taxes_brutes_avant,
            'solde_net_reporte_avant_annee': solde_net_reporte_avant_annee,
            'solde_net_avant_imputation': solde_net_avant_imputation,
            'solde_reporte_avant_annee': solde_reporte_avant_annee,
            'total_disponible_a_rembourser': total_disponible_a_rembourser,
            'imputation_annuelle': imputation_annuelle,
            'montant_imputation_saisi': montant_imputation_saisi,
            'montant_rembourse_cette_annee': montant_rembourse_cette_annee,
            'montant_rembourse_reporte': montant_rembourse_reporte,
            'total_taxe': total_taxe_rounded,
            'total_taxe_brute': total_taxe_raw,
            'total_taxe_raw': total_taxe_apres_remb,
            'nb_ouvrages': len(ouvrages_dict),
            'info_paiement': info_paiement,
        })
    
    chart_labels = [r['commune'].nom_commune if r['commune'] else 'Inconnu' for r in rapport_list]
    chart_taxes = [int(r['total_taxe']) for r in rapport_list]
    chart_ouvrages = [r['nb_ouvrages'] for r in rapport_list]
    
    total_ouvrages = len(ouvrages_uniques_scope)

    context = {
        'annee': annee,
        'rapport': rapport_list,
        'inconnus': entries_inconnues if not commune_id_filter and not commune_ids else [],
        'total_general_taxe': sum(r['total_taxe'] for r in rapport_list),
        'total_ouvrages': total_ouvrages,
        'all_regions': all_regions,
        'all_districts': all_districts,
        'all_communes': all_communes,
        'selected_organisation_id': organisation_filter,
        'selected_region_id': region_id,
        'selected_district_id': district_id,
        'selected_commune_ids': commune_ids,
        'chart_labels': chart_labels,
        'chart_taxes': chart_taxes,
        'chart_ouvrages': chart_ouvrages,
    }

    if request.GET.get('print'):
        return render(request, 'accounting/facture_taxe_communale_print.html', context)
        
    return render(request, 'accounting/etat_taxe_communale.html', context)


@login_required
def etat_impot_synthetique(request):
    """
    Genere l'etat de l'impot synthetique a payer.
    Regle metier:
    - Paiement annuel
    - 5% des recettes (montant_in) des comptes:
      * 707401 : Vente eau au volume
      * 707201 : Vente pieces de rechange
      * 707101 : Vente pieces de rechange
    """

    # Filtres de date (par defaut annee courante)
    annee = request.GET.get('annee', datetime.now().year)
    try:
        annee = int(annee)
    except ValueError:
        annee = datetime.now().year

    comptes_cibles = ['707401', '707201', '707101']
    compte_labels = {
        '707401': 'Vente eau (volume)',
        '707201': 'Vente pieces de rechange',
        '707101': 'Vente pieces de rechange',
    }

    # L'impot synthetique est ancre sur date_rec (date de paiement comptable)
    entries = _get_diamex_scope_for_user(request.user).filter(
        compte_code__in=comptes_cibles,
        date_rec__isnull=False,
        date_rec__year=annee
    ).order_by('date_rec', 'id')

    comptes_map = {
        code: {
            'code': code,
            'label': compte_labels.get(code, f'Compte {code}'),
            'montant': 0.0,
            'impot': 0.0,
            'taux': 0.05,
            'taux_str': '5%',
            'details': [],
            'nb_transactions': 0,
        }
        for code in comptes_cibles
    }

    for entry in entries:
        montant = float(entry.montant_in or 0)
        if montant <= 0:
            continue

        if not entry.date_rec or entry.date_rec.year != annee:
            continue

        compte = comptes_map.get(entry.compte_code)
        if not compte:
            continue

        impot = montant * 0.05
        detail = {
            'date': entry.date_rec.strftime('%d/%m/%Y'),
            'description': entry.description or '',
            'montant': montant,
            'impot': impot,
        }
        compte['montant'] += montant
        compte['impot'] += impot
        compte['nb_transactions'] += 1
        compte['details'].append(detail)

    comptes = []
    for code in comptes_cibles:
        compte = comptes_map[code]
        if compte['nb_transactions'] == 0:
            continue
        compte['details_json'] = json.dumps(compte['details'])
        comptes.append(compte)

    total_recettes = sum(c['montant'] for c in comptes)
    total_general_impot_raw = sum(c['impot'] for c in comptes)
    total_general_impot = round(total_general_impot_raw / 100) * 100

    chart_labels = [f"{c['code']} - {c['label']}" for c in comptes]
    chart_impots = [int(round(c['impot'])) for c in comptes]

    context = {
        'annee': annee,
        'comptes': comptes,
        'total_recettes': total_recettes,
        'total_general_impot': total_general_impot,
        'total_general_impot_raw': total_general_impot_raw,
        'total_transactions': sum(c['nb_transactions'] for c in comptes),
        'chart_labels': chart_labels,
        'chart_impots': chart_impots,
    }

    if request.GET.get('print'):
        return render(request, 'accounting/facture_impot_synthetique_print.html', context)

    return render(request, 'accounting/etat_impot_synthetique.html', context)








