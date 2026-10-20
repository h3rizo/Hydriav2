from django.http import JsonResponse
from django.db.models import Q
from apps.planning.models import Planning, Designation
from apps.employees.models import Employe
from apps.usagers.models import RepresentantUsager, Autorite, TiersParticipant
from apps.billing.models import Fournisseur, PointEau, ModaliteGestion
from apps.geography.models import Village, Commune
from apps.organization.models import Ouvrage
from apps.infrastructure.models import EquipementConstitutif, CarteSociale
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from apps.employees.permissions import filter_queryset_by_permissions
from apps.core.search_mobile_formatting import has_coordinates, point_type_pictogram

@login_required
def search_api_evolved(request):
    """API de recherche globale evoluee pour supporter la pagination et le filtrage par types"""
    query = request.GET.get('q', '').strip()
    
    # Types filtering
    types_param = request.GET.get('types', '')
    requested_types = [t.strip() for t in types_param.split(',')] if types_param else []
    
    # Pagination
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(50, max(1, int(request.GET.get('page_size', 20))))
    except ValueError:
        page = 1
        page_size = 20

    if not query or len(query) < 2:
        return JsonResponse({
            'success': True,
            'results': [],
            'total': 0,
            'totals_by_type': {},
            'message': 'Veuillez saisir au moins 2 caracteres',
            'has_next': False,
            'page': page,
            'page_size': page_size
        })

    all_querysets = {}
    accessible_works = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    accessible_work_ids = accessible_works.values_list('id', flat=True)
    accessible_points = PointEau.objects.filter(ouvrage_id__in=accessible_work_ids)
    accessible_equipment = EquipementConstitutif.objects.filter(ouvrage_id__in=accessible_work_ids)
    accessible_village_ids = accessible_points.values_list('parcelle__village_id', flat=True)
    accessible_commune_ids = accessible_points.values_list(
        'parcelle__village__fokontany__commune_id', flat=True,
    )
    accessible_employees = Employe.objects.all()
    connected_employee = getattr(request.user, 'employe', None)
    organisation_id = getattr(getattr(getattr(connected_employee, 'base', None), 'organisation', None), 'id', None)
    if organisation_id:
        accessible_employees = accessible_employees.filter(base__organisation_id=organisation_id)
    
    if not requested_types or 'planning' in requested_types:
        all_querysets['planning'] = Planning.objects.filter(
            ouvrage_id__in=accessible_work_ids,
        ).select_related(
            'employe', 'ouvrage', 'type_activite', 'fiche_poste'
        ).filter(
            Q(remarque__icontains=query) |
            Q(employe__nom__icontains=query) |
            Q(employe__prenom__icontains=query) |
            Q(employe__surnom__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(type_activite__nomtype__icontains=query) |
            Q(fiche_poste__tache__icontains=query)
        )
        
    if not requested_types or 'employe' in requested_types:
        all_querysets['employe'] = accessible_employees.select_related('poste').filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(surnom__icontains=query) |
            Q(mail__icontains=query) |
            Q(telephone__icontains=query)
        )
        
    if not requested_types or 'representant' in requested_types:
        all_querysets['representant'] = RepresentantUsager.objects.select_related(
            'village__fokontany__commune'
        ).filter(
            Q(nom__icontains=query) |
            Q(contact__icontains=query) |
            Q(village__nom_village__icontains=query)
        )
        
    if not requested_types or 'autorite' in requested_types:
        all_querysets['autorite'] = Autorite.objects.select_related(
            'fokontany', 'commune', 'district', 'region'
        ).filter(
            Q(nom__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )
        
    if not requested_types or 'tiers' in requested_types:
        all_querysets['tiers'] = TiersParticipant.objects.filter(
            Q(nom__icontains=query) |
            Q(organisme__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )
        
    if not requested_types or 'fournisseur' in requested_types:
        all_querysets['fournisseur'] = Fournisseur.objects.filter(
            Q(nom_fournisseur__icontains=query) |
            Q(telephone__icontains=query) |
            Q(email__icontains=query) |
            Q(numero_nif__icontains=query) |
            Q(code_tiers__icontains=query)
        )
        
    if not requested_types or 'village' in requested_types:
        all_querysets['village'] = Village.objects.filter(
            id__in=accessible_village_ids,
        ).select_related(
            'fokontany__commune__district__region'
        ).filter(
            Q(nom_village__icontains=query) |
            Q(fokontany__nom_fokontany__icontains=query) |
            Q(fokontany__commune__nom_commune__icontains=query)
        )
        
    if not requested_types or 'commune' in requested_types:
        all_querysets['commune'] = Commune.objects.filter(
            id__in=accessible_commune_ids,
        ).select_related('district__region').filter(
            Q(nom_commune__icontains=query) |
            Q(district__nom_district__icontains=query)
        )

    if not requested_types or 'ouvrage' in requested_types:
        all_querysets['ouvrage'] = accessible_works.select_related('type_ouvrage').filter(
            Q(nom_ouvrage__icontains=query) |
            Q(type_ouvrage__nom_type_ouvrage__icontains=query) |
            Q(pointeau__parcelle__village__nom_village__icontains=query) |
            Q(pointeau__parcelle__village__fokontany__nom_fokontany__icontains=query) |
            Q(pointeau__parcelle__village__fokontany__commune__nom_commune__icontains=query)
        ).distinct()

    if not requested_types or 'point_eau' in requested_types:
        all_querysets['point_eau'] = accessible_points.select_related('ouvrage', 'type_point_eau', 'parcelle__village').filter(
            Q(code_point_eau__icontains=query) |
            Q(nomabonne__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(parcelle__village__nom_village__icontains=query)
        )

    if not requested_types or 'equipement' in requested_types:
        all_querysets['equipement'] = accessible_equipment.select_related('ouvrage', 'type_equipement').filter(
            Q(nom__icontains=query) |
            Q(code_equipement__icontains=query) |
            Q(type_equipement__nom_type__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query)
        )

    if not requested_types or 'designation' in requested_types:
        all_querysets['designation'] = Designation.objects.select_related('type_designation').filter(
            Q(nom__icontains=query) |
            Q(type_designation__nom__icontains=query)
        )

    if not requested_types or 'modalite' in requested_types:
        all_querysets['modalite'] = ModaliteGestion.objects.filter(
            ouvrage_id__in=accessible_work_ids,
        ).filter(
            Q(type_gestion__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query)
        )

    if not requested_types or 'carte_sociale' in requested_types:
        all_querysets['carte_sociale'] = CarteSociale.objects.filter(
            ouvrage_id__in=accessible_work_ids,
        ).select_related('ouvrage', 'point_eau').filter(
            Q(numero_carte__icontains=query) |
            Q(nom_beneficiaire__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(point_eau__nomabonne__icontains=query)
        )
    
    totals_by_type = {}
    total_general = 0
    
    for t, qs in all_querysets.items():
        try:
            if not qs.ordered:
                qs = qs.order_by('pk')
                all_querysets[t] = qs
            count = qs.count()
            totals_by_type[t] = count
            total_general += count
        except Exception:
            totals_by_type[t] = 0

    # Mode « par type » (page Recherche web) : page_size resultats DE CHAQUE type par page,
    # pour que les types suivants (villages, ouvrages...) ne soient pas masques par le
    # premier type qui remplit toute la page (souvent les plannings).
    if request.GET.get('per_type') in ('1', 'true', 'oui'):
        offset = (page - 1) * page_size
        results = []
        for type_name, qs in all_querysets.items():
            if totals_by_type.get(type_name, 0) <= offset:
                continue
            try:
                results.extend(_serialize_search_item(item, type_name) for item in qs[offset:offset + page_size])
            except Exception:
                pass
        return JsonResponse({
            'success': True,
            'results': results,
            'total': total_general,
            'totals_by_type': totals_by_type,
            'page': page,
            'page_size': page_size,
            'has_next': any(n > page * page_size for n in totals_by_type.values()),
        })

    results = []
    offset = (page - 1) * page_size
    limit = page_size
    
    current_offset = 0
    
    for type_name, qs in all_querysets.items():
        type_count = totals_by_type[type_name]
        
        if current_offset + type_count <= offset:
            current_offset += type_count
            continue
            
        start_idx = max(0, offset - current_offset)
        end_idx = start_idx + limit
        
        try:
            items = qs[start_idx:end_idx]
            
            for item in items:
                results.append(_serialize_search_item(item, type_name))
                
            limit -= len(items)
        except Exception as e:
            pass
            
        current_offset += type_count
        
        if limit <= 0:
            break

    has_next = (page * page_size) < total_general

    return JsonResponse({
        'success': True,
        'results': results,
        'total': total_general,
        'totals_by_type': totals_by_type,
        'page': page,
        'page_size': page_size,
        'has_next': has_next
    })

def _serialize_search_item(item, type_name):
    # Serialisation similaire au Web mais allegee pour l'API Android/Web unifiee
    result = {
        'id': str(item.id),
        'type': type_name,
        'type_display': type_name.capitalize(),
        'title': str(item),
        'subtitle': '-',
        'badge': '',
        'badge_class': '',
        'icon': 'fa-circle',
        'url': f'/recherche/details/{type_name}/{item.id}/',
        'photo_url': None
    }
    
    if type_name == 'planning':
        result['title'] = f"Planning {item.date.strftime('%d/%m/%Y') if item.date else 'Sans date'}"
        result['subtitle'] = f"{item.employe.nom_affichage if item.employe else 'Sans employe'} - {item.ouvrage.nom_ouvrage if item.ouvrage else 'Sans ouvrage'}"
        result['badge'] = 'Valide' if getattr(item, 'estvalide', False) else 'En attente'
        result['badge_class'] = 'success' if getattr(item, 'estvalide', False) else 'warning'
        result['icon'] = 'fa-calendar-alt'
        result['type_display'] = 'Planning'
    
    elif type_name == 'employe':
        est_actif = getattr(item, 'date_debauchage', None) is None
        result['title'] = item.nom_affichage
        result['subtitle'] = f"{item.poste.nom_poste if getattr(item, 'poste', None) else 'Poste inconnu'} - {'Actif' if est_actif else 'Inactif'}"
        result['badge'] = 'Actif' if est_actif else 'Inactif'
        result['badge_class'] = 'success' if est_actif else 'error'
        result['icon'] = 'fa-user'
        result['type_display'] = 'Employe'
        if getattr(item, 'signature', None) and isinstance(item.signature, list) and len(item.signature) > 0:
            first_photo = item.signature[0]
            if isinstance(first_photo, dict) and 'data' in first_photo:
                result['photo_url'] = first_photo['data']
                
    elif type_name == 'representant':
        village_nom = item.village.nom_village if getattr(item, 'village', None) else 'Village inconnu'
        result['title'] = item.nom or 'Sans nom'
        result['subtitle'] = f"{village_nom} - {item.contact or 'Pas de contact'}"
        result['badge'] = 'Actif' if getattr(item, 'est_actif', False) else 'Inactif'
        result['badge_class'] = 'success' if getattr(item, 'est_actif', False) else 'error'
        result['icon'] = 'fa-user-tie'
        result['type_display'] = 'Representante'
        
    elif type_name == 'autorite':
        zone = getattr(item, 'zone_affichee', 'Zone non precisee')
        type_display = item.get_type_autorite_display() if hasattr(item, 'get_type_autorite_display') else 'Autorite'
        result['title'] = item.nom
        result['subtitle'] = f"{type_display} - {zone}"
        result['badge'] = 'Actif' if getattr(item, 'actif', False) else 'Inactif'
        result['badge_class'] = 'success' if getattr(item, 'actif', False) else 'error'
        result['icon'] = 'fa-landmark'
        result['type_display'] = 'Autorite'
        
    elif type_name == 'tiers':
        type_display = item.get_type_tiers_display() if hasattr(item, 'get_type_tiers_display') else 'Tiers'
        result['title'] = item.nom
        result['subtitle'] = f"{type_display}" + (f" - {item.organisme}" if getattr(item, 'organisme', None) else '')
        result['badge'] = 'Actif' if getattr(item, 'actif', False) else 'Inactif'
        result['badge_class'] = 'success' if getattr(item, 'actif', False) else 'error'
        result['icon'] = 'fa-handshake'
        result['type_display'] = 'Tiers'
        
    elif type_name == 'fournisseur':
        type_display = item.get_type_fournisseur_display() if hasattr(item, 'get_type_fournisseur_display') else 'Fournisseur'
        result['title'] = item.nom_fournisseur
        result['subtitle'] = f"{type_display} - {item.telephone or 'Pas de contact'}"
        result['badge'] = 'Actif' if getattr(item, 'actif', False) else 'Inactif'
        result['badge_class'] = 'success' if getattr(item, 'actif', False) else 'error'
        result['icon'] = 'fa-truck'
        result['type_display'] = 'Fournisseur'
        
    elif type_name == 'village':
        fokontany = getattr(getattr(item, 'fokontany', None), 'nom_fokontany', None)
        commune = getattr(getattr(getattr(item, 'fokontany', None), 'commune', None), 'nom_commune', None)
        result['title'] = item.nom_village
        result['subtitle'] = f"{fokontany or ''} - {commune or ''}"
        result['badge'] = 'Village'
        result['badge_class'] = 'info'
        result['icon'] = 'fa-home'
        result['type_display'] = 'Village'
        
    elif type_name == 'commune':
        district = getattr(getattr(item, 'district', None), 'nom_district', None)
        region = getattr(getattr(getattr(item, 'district', None), 'region', None), 'nom_region', None)
        result['title'] = item.nom_commune
        result['subtitle'] = f"{district or ''} - {region or ''}"
        result['badge'] = 'Commune'
        result['badge_class'] = 'secondary'
        result['icon'] = 'fa-map-marker-alt'
        result['type_display'] = 'Commune'
        
    elif type_name == 'ouvrage':
        type_ouvrage = getattr(getattr(item, 'type_ouvrage', None), 'nom_type_ouvrage', None)
        result['title'] = item.nom_ouvrage
        result['subtitle'] = f"{type_ouvrage or 'Type inconnu'}"
        result['badge'] = 'Ouvrage'
        result['badge_class'] = 'primary'
        result['icon'] = 'fa-water'
        result['type_display'] = 'Ouvrage'
        try:
            point_with_photo = item.pointeau_set.filter(photos__isnull=False).first()
            if point_with_photo and point_with_photo.photos:
                result['photo_url'] = point_with_photo.photos.get_download_url()
        except Exception:
            pass
                
    elif type_name == 'point_eau':
        type_point = getattr(getattr(item, 'type_point_eau', None), 'nom_type', None)
        result['title'] = f"IDXls: {item.idxls or 'Non renseigné'} · {item.nomabonne or 'Abonné non renseigné'}"
        result['subtitle'] = (
            f"{point_type_pictogram(type_point)} {type_point or 'Type non renseigné'}"
            f" · Coordonnées: {'Oui' if has_coordinates(item) else 'Non'}"
        )
        result['badge'] = 'Point d\'eau'
        result['badge_class'] = 'info'
        result['icon'] = 'fa-faucet'
        result['type_display'] = 'Point d\'eau'

    elif type_name == 'equipement':
        type_equip = getattr(getattr(item, 'type_equipement', None), 'nom_type', None)
        result['title'] = item.nom or 'Equipement sans nom'
        result['subtitle'] = (
            f"{type_equip or 'Type non renseigné'}"
            f" · Coordonnées: {'Oui' if has_coordinates(item) else 'Non'}"
        )
        result['badge'] = 'Equipement'
        result['badge_class'] = 'secondary'
        result['icon'] = 'fa-tools'
        result['type_display'] = 'Equipement'
        
    elif type_name == 'designation':
        type_desig = getattr(getattr(item, 'type_designation', None), 'nom', None)
        result['title'] = item.nom
        result['subtitle'] = f"{type_desig or 'Type inconnu'}"
        result['badge'] = 'Designation'
        result['badge_class'] = 'warning'
        result['icon'] = 'fa-tag'
        result['type_display'] = 'Designation'
        try:
            if item.photo_specimen:
                result['photo_url'] = item.photo_specimen.get_download_url()
        except Exception:
            pass
                
    elif type_name == 'modalite':
        result['title'] = item.get_type_gestion_display()
        result['subtitle'] = item.ouvrage.nom_ouvrage if item.ouvrage_id else 'Sans ouvrage'
        result['badge'] = 'Modalite'
        result['badge_class'] = 'dark'
        result['icon'] = 'fa-cog'
        result['type_display'] = 'Modalite'
        
    elif type_name == 'carte_sociale':
        ouvrage = getattr(getattr(item, 'ouvrage', None), 'nom_ouvrage', None)
        statut_display = {
            'active': 'Active',
            'suspendue': 'Suspendue',
            'expiree': 'Expiree',
            'annulee': 'Annulee'
        }.get(getattr(item, 'statut', ''), getattr(item, 'statut', ''))
        
        statut_badge = {
            'active': 'success',
            'suspendue': 'warning',
            'expiree': 'error',
            'annulee': 'error'
        }.get(getattr(item, 'statut', ''), 'info')
        
        result['title'] = f"Carte {item.numero_carte or 'sans numero'} - {item.nom_beneficiaire}"
        result['subtitle'] = f"{ouvrage or 'Ouvrage inconnu'} - {statut_display}"
        result['badge'] = 'Carte Sociale'
        result['badge_class'] = statut_badge
        result['icon'] = 'fa-id-card'
        result['type_display'] = 'Carte Sociale'

    return result
