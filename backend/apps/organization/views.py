from django.shortcuts import render, get_object_or_404, redirect
from apps.billing.tarifs_forfaitaires import champs_tarif_depuis_post
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction, IntegrityError
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.db.models import Count
import json
import re
from .models import (
    Organisation,
    PartenaireGestionnaireAffectation,
    TypeOuvrage,
    Ouvrage,
    OuvrageDossierTechnique,
    OuvrageDossierTechniqueChecklist,
    Base,
    Magasin,
    Journal,
    Compte,
    CompteTable,
)
from .forms import OrganisationForm, TypeOuvrageForm, OuvrageForm, BaseForm, MagasinForm, JournalForm, CompteForm
from .scoping import (
    apply_user_responsable_ouvrage_scope,
    get_active_employee_ouvrage_ids,
    get_employe_ids_with_responsible_ouvrage_scope,
    get_default_gestionnaire_filter_value,
    get_gestionnaire_organisations_queryset,
    get_user_organisation,
    get_user_accessible_gestionnaire_ids,
)
from apps.employees.models import Poste
from apps.employees.forms import PosteForm
from apps.employees.permissions import employe_required, filter_queryset_by_permissions, get_user_poste_name
# Import des modèles infrastructure pour les équipements
from apps.infrastructure.models import TypeEquipement, EquipementConstitutif, LiaisonHydraulique
from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau, PointDeControle, PointDeControleComposant
from apps.billing.models import PointEau, TypePointEau, ModaliteGestion, CompteurTete
from datetime import datetime
from django.utils import timezone

DOSSIER_TECHNIQUE_DOCUMENTS = (
    ('plan_reseau', 'Plan de réseau'),
    ('fiche_technique', "Fiche technique de l’ouvrage"),
    ('profils', 'Profils entre les équipements et points d’eau'),
    ('dimensionnement_citernes', 'Dimensionnement des citernes'),
    ('devis_materiaux', 'Devis des matériaux'),
    ('devis_main_oeuvre', 'Devis de main-d’œuvre'),
)

UUID_PATTERN = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
POINT_EAU_SUFFIX_PATTERN = r"\s*-\s*Point d['’]?\s*eau\b.*$"


def _ouvrage_entity_map_data(ouvrage, entities, entity_kind, avec_contours=False):
    """Construit une carte commune équipements, points d'eau et villages desservis."""
    markers = []
    map_liaisons = []

    if entity_kind == 'equipement':
        equipements = entities
        points_eau = PointEau.objects.filter(ouvrage=ouvrage).select_related(
            'type_point_eau', 'parcelle__village__fokontany__commune'
        ) if ouvrage else PointEau.objects.none()
    else:
        points_eau = entities
        equipements = EquipementConstitutif.objects.filter(ouvrage=ouvrage).select_related(
            'type_equipement'
        ) if ouvrage else EquipementConstitutif.objects.none()

    for entity in equipements:
        latitude = getattr(entity, 'latitude', None)
        longitude = getattr(entity, 'longitude', None)
        if latitude is None or longitude is None:
            continue
        type_nom = getattr(getattr(entity, 'type_equipement', None), 'nom_type', '') or ''
        markers.append({
            'id': str(entity.pk),
            'latitude': float(latitude),
            'longitude': float(longitude),
            'label': getattr(entity, 'nom', '') or 'Équipement sans nom',
            'detail': type_nom or 'Équipement',
            'type_equipement': type_nom,
            'kind': 'equipement',
        })

    for point in points_eau:
        if point.latitude is None or point.longitude is None:
            continue
        type_nom = getattr(getattr(point, 'type_point_eau', None), 'nom_type', '') or ''
        markers.append({
            'id': str(point.pk),
            'latitude': float(point.latitude),
            'longitude': float(point.longitude),
            'label': point.nomabonne or point.code_point_eau or "Point d'eau",
            'detail': point.code_point_eau or type_nom or "Point d'eau",
            'idxls': point.idxls or '',
            'kind': 'point_eau',
        })

    # Une liaison n'est cartographiable que si ses deux extrémités figurent
    # sur la carte et disposent donc toutes les deux de coordonnées GPS.
    marker_lookup = {
        (item['kind'], item['id']): item
        for item in markers
        if item['kind'] in {'equipement', 'point_eau'}
    }
    if ouvrage:
        liaisons = LiaisonHydraulique.objects.filter(
            ouvrage=ouvrage,
            actif=True,
        ).select_related(
            'amont_equipement', 'amont_compteur_tete', 'amont_point_eau',
            'aval_equipement', 'aval_compteur_tete', 'aval_point_eau',
        )
        for liaison in liaisons:
            amont_key = (liaison.get_amont_type(), str(getattr(liaison.get_amont_node(), 'pk', '')))
            aval_key = (liaison.get_aval_type(), str(getattr(liaison.get_aval_node(), 'pk', '')))
            amont_marker = marker_lookup.get(amont_key)
            aval_marker = marker_lookup.get(aval_key)
            if not amont_marker or not aval_marker:
                continue
            map_liaisons.append({
                'id': str(liaison.pk),
                'from': {
                    'latitude': amont_marker['latitude'],
                    'longitude': amont_marker['longitude'],
                    'label': amont_marker['label'],
                    'kind': amont_marker['kind'],
                },
                'to': {
                    'latitude': aval_marker['latitude'],
                    'longitude': aval_marker['longitude'],
                    'label': aval_marker['label'],
                    'kind': aval_marker['kind'],
                },
            })

    seen_villages = set()
    communes_desservies = []
    for point in points_eau:
        parcelle = getattr(point, 'parcelle', None)
        village = getattr(parcelle, 'village', None) if parcelle else None
        if not village or village.pk in seen_villages:
            continue
        if village.latitude is None or village.longitude is None:
            continue
        seen_villages.add(village.pk)
        commune = getattr(getattr(village, 'fokontany', None), 'commune', None)
        communes_desservies.append(commune)
        markers.append({
            'id': str(village.pk),
            'latitude': float(village.latitude),
            'longitude': float(village.longitude),
            'label': village.nom_village or 'Village sans nom',
            'detail': getattr(commune, 'nom_commune', '') or 'Village desservi',
            'kind': 'village',
        })

    counts = {
        'equipements': sum(item['kind'] == 'equipement' for item in markers),
        'points_eau': sum(item['kind'] == 'point_eau' for item in markers),
        'villages': sum(item['kind'] == 'village' for item in markers),
        'liaisons': len(map_liaisons),
    }
    donnees = {
        'markers': markers,
        'liaisons': map_liaisons,
        'source': 'mixed',
        'fallback': False,
        'counts': counts,
    }
    if avec_contours:
        # Contours des communes desservies (importés des shapefiles) ; la carte reste utilisable sans eux.
        try:
            from apps.geography.services.contours_communes import contours_communes_de
            donnees['contours'] = {'type': 'FeatureCollection', 'features': contours_communes_de(communes_desservies)}
        except Exception:
            donnees['contours'] = {'type': 'FeatureCollection', 'features': []}
    return donnees


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_map_coordinate_assign(request, ouvrage_id):
    """Affecte une position choisie sur la carte à une entité existante."""
    import math

    ouvrage = get_object_or_404(
        filter_queryset_by_permissions(Ouvrage.objects.all(), request.user),
        pk=ouvrage_id,
    )
    try:
        payload = json.loads(request.body or '{}')
        entity_type = str(payload.get('entity_type') or '').strip()
        entity_id = str(payload.get('entity_id') or '').strip()
        latitude = float(str(payload.get('latitude')).replace(',', '.'))
        longitude = float(str(payload.get('longitude')).replace(',', '.'))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Données de position invalides.'}, status=400)

    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        return JsonResponse({'success': False, 'error': 'La latitude doit être comprise entre -90 et 90.'}, status=400)
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        return JsonResponse({'success': False, 'error': 'La longitude doit être comprise entre -180 et 180.'}, status=400)

    if entity_type == 'point_eau':
        entity = get_object_or_404(
            filter_queryset_by_permissions(
                PointEau.objects.filter(ouvrage=ouvrage), request.user
            ),
            pk=entity_id,
        )
        label = entity.nomabonne or entity.code_point_eau or "Point d'eau"
    elif entity_type == 'equipement':
        entity = get_object_or_404(
            EquipementConstitutif.objects.filter(ouvrage=ouvrage),
            pk=entity_id,
        )
        label = entity.nom or entity.code_equipement or 'Équipement'
    else:
        return JsonResponse({'success': False, 'error': "Type d'entité invalide."}, status=400)

    entity.latitude = latitude
    entity.longitude = longitude
    entity.save(update_fields=['latitude', 'longitude'])
    stored = entity.__class__.objects.filter(pk=entity.pk).values('latitude', 'longitude').first()
    if (
        not stored
        or stored['latitude'] is None
        or stored['longitude'] is None
        or abs(float(stored['latitude']) - latitude) >= 1e-8
        or abs(float(stored['longitude']) - longitude) >= 1e-8
    ):
        return JsonResponse(
            {'success': False, 'error': "La vérification en base après l'enregistrement a échoué."},
            status=500,
        )

    return JsonResponse({
        'success': True,
        'message': f'Position enregistrée et vérifiée pour {label}.',
        'entity': {
            'id': str(entity.pk),
            'type': entity_type,
            'label': label,
            'latitude': float(stored['latitude']),
            'longitude': float(stored['longitude']),
        },
    })


def user_is_director(user):
    if not user.is_authenticated:
        return False
    employe = getattr(user, 'employe', None)
    if not employe or not hasattr(employe, 'poste') or not employe.poste:
        return False
    poste_nom = getattr(employe.poste, 'nom_poste', '') or ''
    return poste_nom.strip().lower() == 'directeur'


def _normalize_supplier_key(value):
    normalized = re.sub(r'[^a-z0-9]+', ' ', str(value or '').strip().lower())
    return ' '.join(normalized.split())


def _build_fournisseur_duplicate_groups(fournisseurs):
    groups = {}
    for fournisseur in fournisseurs:
        key = _normalize_supplier_key(fournisseur.nom_fournisseur)
        if not key:
            continue
        groups.setdefault(key, []).append(fournisseur)

    duplicates = []
    for items in groups.values():
        if len(items) < 2:
            continue
        duplicates.append({
            'label': items[0].nom_fournisseur,
            'items': items,
        })

    duplicates.sort(key=lambda item: item['label'].lower())
    return duplicates


def _ensure_director_json(request):
    if user_is_director(request.user):
        return None
    return JsonResponse({
        'success': False,
        'message': 'Acces reserve au directeur.',
    }, status=403)


def _merge_supplier_values(target, source):
    simple_fields = [
        'telephone',
        'email',
        'adresse_relation',
        'adresse_fournisseur',
        'adresse',
        'code_postal',
        'type_fournisseur',
        'nif_ou_isi',
        'numero_nif',
        'numero_stat',
        'cin',
        'date_cin',
        'lieu_cin',
        'autre_information',
    ]

    update_fields = []
    for field_name in simple_fields:
        source_value = getattr(source, field_name, None)
        target_value = getattr(target, field_name, None)
        if target_value in (None, '', False) and source_value not in (None, '', False):
            setattr(target, field_name, source_value)
            update_fields.append(field_name)

    boolean_fields = ['tacheron', 'devis', 'prestation', 'actif']
    for field_name in boolean_fields:
        merged_value = bool(getattr(target, field_name)) or bool(getattr(source, field_name))
        if getattr(target, field_name) != merged_value:
            setattr(target, field_name, merged_value)
            update_fields.append(field_name)

    if update_fields:
        target.save(update_fields=sorted(set(update_fields + ['updated_at'])))


def _reassign_fournisseur_relations(source, target):
    reassigned = {}
    for relation in source._meta.related_objects:
        if relation.many_to_many:
            continue
        if relation.related_model.__name__ == 'FournisseurFusionInstruction':
            continue

        field = getattr(relation, 'field', None)
        if field is None or not hasattr(field, 'name'):
            continue

        accessor_name = relation.get_accessor_name()
        if not accessor_name:
            continue

        relation_label = relation.related_model._meta.verbose_name_plural.title()

        if relation.one_to_one:
            try:
                related_obj = getattr(source, accessor_name)
            except relation.related_model.DoesNotExist:
                continue
            if related_obj and getattr(related_obj, f'{field.name}_id', None) != target.pk:
                setattr(related_obj, field.name, target)
                related_obj.save(update_fields=[field.name])
                reassigned[relation_label] = reassigned.get(relation_label, 0) + 1
            continue

        manager = getattr(source, accessor_name, None)
        if manager is None or not hasattr(manager, 'all'):
            continue

        qs = manager.all()
        count = qs.count()
        if not count:
            continue

        qs.update(**{field.name: target})
        reassigned[relation_label] = reassigned.get(relation_label, 0) + count

    return reassigned


def _build_diamex_instruction_text(source, target, affected_count):
    source_idxls = source.idxls if source.idxls is not None else '?'
    target_idxls = target.idxls if target.idxls is not None else '?'
    return (
        f"Fusion fournisseur effectuee: '{source.nom_fournisseur}' ({source_idxls}) vers "
        f"'{target.nom_fournisseur}' ({target_idxls}). "
        f"Verifier et corriger dans les bases DiameX les lignes de comptabilite dont le champ "
        f"fournisseur/code vaut {source_idxls} pour le remplacer par {target_idxls}. "
        f"Lignes reperees dans Hydria: {affected_count}."
    )


def _normalize_cascade_form_data(item_type, source_data):
    data = source_data.copy()
    name_value = (data.get('name') or '').strip()

    name_field_map = {
        'organisation': 'nom_organisation',
        'base': 'nom_base',
        'magasin': 'nom_magasin',
        'journal': 'nom_journal',
        'compte': 'nom_compte',
        'poste': 'nom_poste',
    }

    target_name_field = name_field_map.get(item_type)
    if target_name_field and name_value and not data.get(target_name_field):
        data[target_name_field] = name_value

    if item_type == 'base':
        if 'ouvrage_correspondant_id' in data and not data.get('ouvrage_correspondant'):
            data['ouvrage_correspondant'] = data.get('ouvrage_correspondant_id') or ''
        if 'base_telephone' in data and not data.get('telephone'):
            data['telephone'] = data.get('base_telephone') or ''

    return data


def _get_allowed_ouvrages_for_user(user):
    """
    Cloisonnement des ouvrages via la table ModaliteGestion:
    - Modalite active uniquement (date_fin IS NULL)
    - Ouvrages dont le gestionnaire = organisation de l'utilisateur
    - Superuser: tous les ouvrages
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return Ouvrage.objects.none()

    if getattr(user, 'is_superuser', False):
        return Ouvrage.objects.all()

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return Ouvrage.objects.all()
    if not gestionnaire_ids:
        return Ouvrage.objects.none()

    ouvrages_ids = set(
        ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        gestionnaire_id__in=gestionnaire_ids,
        modalitepaiement__in=['au_volume', 'mixte']
    ).exclude(
        ouvrage_id__isnull=True
        ).values_list('ouvrage_id', flat=True).distinct()
    )

    scoped_ids = apply_user_responsable_ouvrage_scope(ouvrages_ids, user)
    allowed_ids = ouvrages_ids if scoped_ids is None else scoped_ids

    return Ouvrage.objects.filter(
        id__in=allowed_ids
    ).filter(
        models.Q(type_ouvrage__nom_type_ouvrage__iexact='AEPG') |
        models.Q(type_ouvrage__nom_type_ouvrage__iexact='AEPG extension')
    )


def _get_ouvrage_detail_filter_queryset(user):
    ouvrages = filter_queryset_by_permissions(
        Ouvrage.objects.filter(
            type_ouvrage__nom_type_ouvrage__iexact='AEPG'
        ).select_related('type_ouvrage', 'ouvrage_source'),
        user,
    ).order_by('nom_ouvrage')

    scoped_ids = apply_user_responsable_ouvrage_scope(
        set(ouvrages.values_list('id', flat=True)),
        user,
    )
    if scoped_ids is None:
        return ouvrages
    return ouvrages.filter(id__in=scoped_ids)


def _build_ouvrage_detail_grouped_options(ouvrages):
    ouvrages_list = list(ouvrages)
    if not ouvrages_list:
        return []

    ouvrage_ids = [item.pk for item in ouvrages_list]
    location_map = {}

    points_eau = (
        PointEau.objects.filter(ouvrage_id__in=ouvrage_ids)
        .select_related('ouvrage', 'parcelle__village__fokontany__commune__district__region')
        .exclude(ouvrage_id__isnull=True)
        .order_by('ouvrage__nom_ouvrage', 'nomabonne', 'code_point_eau')
    )

    for point_eau in points_eau:
        ouvrage_id = getattr(point_eau, 'ouvrage_id', None)
        if not ouvrage_id or ouvrage_id in location_map:
            continue

        parcelle = getattr(point_eau, 'parcelle', None)
        village = getattr(parcelle, 'village', None) if parcelle else None
        fokontany = getattr(village, 'fokontany', None) if village else None
        commune = getattr(fokontany, 'commune', None) if fokontany else None
        district = getattr(commune, 'district', None) if commune else None
        region = getattr(district, 'region', None) if district else None

        location_map[ouvrage_id] = (
            (getattr(region, 'nom_region', '') or '').strip() or 'Region non definie',
            (getattr(district, 'nom_district', '') or '').strip() or 'District non defini',
            (getattr(commune, 'nom_commune', '') or '').strip() or 'Commune non definie',
        )

    grouped = {}
    for ouvrage in ouvrages_list:
        region_nom, district_nom, commune_nom = location_map.get(
            ouvrage.pk,
            ('Region non definie', 'District non defini', 'Commune non definie'),
        )
        group_key = (region_nom, district_nom, commune_nom)
        grouped.setdefault(group_key, []).append(ouvrage)

    grouped_options = []
    for group_key in sorted(grouped.keys(), key=lambda item: tuple(part.lower() for part in item)):
        region_nom, district_nom, commune_nom = group_key
        grouped_options.append({
            'label': f"{region_nom} / {district_nom} / {commune_nom}",
            'region_nom': region_nom,
            'district_nom': district_nom,
            'commune_nom': commune_nom,
            'ouvrages': sorted(
                grouped[group_key],
                key=lambda item: (
                    (item.nom_ouvrage or '').lower(),
                    str(item.pk),
                ),
            ),
        })

    return grouped_options


def _save_ouvrage_dossier_technique_files(ouvrage, uploaded_files):
    created_items = []
    for uploaded_file in uploaded_files or []:
        if not uploaded_file:
            continue
        created_items.append(
            OuvrageDossierTechnique.objects.create(
                ouvrage=ouvrage,
                fichier=uploaded_file,
                nom_affichage=getattr(uploaded_file, 'name', '') or '',
            )
        )
    return created_items


def _get_organigramme_root_ouvrage(ouvrage):
    return getattr(ouvrage, 'ouvrage_source_effectif', None) or ouvrage


def _get_organigramme_scope_ouvrage_ids(ouvrage):
    if not ouvrage:
        return set()

    root_ouvrage = _get_organigramme_root_ouvrage(ouvrage)
    return set(
        Ouvrage.objects.filter(
            models.Q(pk=root_ouvrage.pk) |
            models.Q(ouvrage_source_id=root_ouvrage.pk)
        ).values_list('id', flat=True)
    )


ORGANIGRAM_NODE_FIELD_MAP = {
    'equipement': 'equipement',
    'compteur': 'compteur_tete',
    'point_eau': 'point_eau',
}

ORGANIGRAMME_SELECT_RELATED = (
    'amont_equipement',
    'amont_compteur_tete',
    'amont_point_eau',
    'aval_equipement',
    'aval_compteur_tete',
    'aval_point_eau',
)


def _get_organigramme_candidates(ouvrage):
    if not ouvrage:
        return {
            'equipements': EquipementConstitutif.objects.none(),
            'compteurs': CompteurTete.objects.none(),
            'points_eau': PointEau.objects.none(),
        }

    scope_ouvrage_ids = _get_organigramme_scope_ouvrage_ids(ouvrage)

    return {
        'equipements': EquipementConstitutif.objects.filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).select_related('type_equipement', 'ouvrage', 'photo_reference').order_by('ouvrage__nom_ouvrage', 'nom'),
        'compteurs': CompteurTete.objects.filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).select_related('ouvrage').order_by('ouvrage__nom_ouvrage', 'numerocompteur'),
        'points_eau': PointEau.objects.filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).select_related(
            'type_point_eau', 'ouvrage',
            'parcelle__village__fokontany__commune__district__region',
        ).order_by('ouvrage__nom_ouvrage', 'nomabonne'),
    }


def _get_organigram_field_suffix(node_type):
    return ORGANIGRAM_NODE_FIELD_MAP[node_type]


def _build_organigram_node_value(node_type, node):
    return f"{node_type}:{node.pk}"


def _build_organigram_node_label(node_type, node):
    if node_type == 'equipement':
        return node.nom or f"Equipement {node.pk}"
    if node_type == 'compteur':
        numero = node.numerocompteur or f"Compteur {node.pk}"
        if node.marque:
            return f"{numero} - {node.marque}"
        return numero

    def _clean_point_label(value):
        text = str(value or '').strip()
        if not text:
            return ''
        prefix = re.sub(POINT_EAU_SUFFIX_PATTERN, '', text, flags=re.IGNORECASE).strip()
        if prefix and prefix != text:
            text = prefix
        text = re.sub(rf"\s*-\s*Point d['’]?eau\s+{UUID_PATTERN}\b", '', text, flags=re.IGNORECASE)
        text = re.sub(rf"\bPoint d['’]?eau\s+{UUID_PATTERN}\b", '', text, flags=re.IGNORECASE)
        text = re.sub(r"\bPoint d['’]?\s*eau\b", '', text, flags=re.IGNORECASE)
        text = re.sub(rf"\b{UUID_PATTERN}\b", '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip(" -_")

    code = _clean_point_label(getattr(node, 'code_point_eau', None))
    nom = _clean_point_label(getattr(node, 'nomabonne', None))

    if code and nom and code.casefold() != nom.casefold():
        return f"{code} - {nom}"
    if code or nom:
        return code or nom

    type_point_eau = getattr(node, 'type_point_eau', None)
    type_label = _clean_point_label(getattr(type_point_eau, 'nom_type', None))
    return type_label or "Point d'eau"


def _build_organigram_node_display_label(node_type, node, include_ouvrage=False):
    label = _build_organigram_node_label(node_type, node)
    if include_ouvrage and getattr(node, 'ouvrage', None):
        return f"{label} [{node.ouvrage.nom_ouvrage}]"
    return label


def _extract_first_photo_payload(photos):
    if not photos or not isinstance(photos, list):
        return None
    first_photo = photos[0]
    if isinstance(first_photo, dict):
        return first_photo
    if isinstance(first_photo, str):
        return {'data': first_photo}
    return None


def _extract_photo_preview_url(photo_payload):
    if not photo_payload:
        return ''

    url_value = photo_payload.get('url') if isinstance(photo_payload, dict) else ''
    if url_value:
        return str(url_value)

    data_value = photo_payload.get('data') if isinstance(photo_payload, dict) else ''
    if data_value:
        data_value = str(data_value).strip()
        # La signature Base64 JPEG commence par un slash et doit donc etre
        # detectee avant les vrais chemins absolus commençant par « / ».
        if data_value.startswith('/9j/'):
            return f'data:image/jpeg;base64,{data_value}'
        if data_value.startswith(('data:', 'http://', 'https://', '/', 'blob:')):
            return data_value

        # Certaines anciennes photos ont ete enregistrees comme Base64 brut.
        # Sans prefixe, le navigateur l'interprete comme une URL relative.
        content_type = (
            photo_payload.get('type')
            or photo_payload.get('content_type')
            or 'image/jpeg'
        )
        return f'data:{content_type};base64,{data_value}'

    return ''


def _extract_photo_urls(photos):
    if not isinstance(photos, list):
        return []
    urls = []
    for photo in photos:
        payload = photo if isinstance(photo, dict) else {'data': photo} if isinstance(photo, str) else None
        url = _extract_photo_preview_url(payload)
        if url:
            urls.append(url)
    return urls


def _get_organigram_node_photo_url(node_type, node):
    if node_type == 'equipement':
        photo_reference = getattr(node, 'photo_reference', None)
        if photo_reference:
            try:
                return photo_reference.get_download_url()
            except Exception:
                pass
        return _extract_photo_preview_url(_extract_first_photo_payload(getattr(node, 'photos', None)))

    if node_type == 'point_eau':
        return _extract_photo_preview_url(_extract_first_photo_payload(getattr(node, 'photos', None)))

    return ''


def _get_organigram_node_photo_count(node_type, node):
    if node_type == 'equipement':
        photos = getattr(node, 'photos', None)
        if isinstance(photos, list) and photos:
            return len(photos)
        return 1 if getattr(node, 'photo_reference_id', None) else 0

    if node_type == 'point_eau':
        photos = getattr(node, 'photos', None)
        if isinstance(photos, list):
            return len(photos)
        return 0

    return 0


def _parse_organigram_node_token(raw_value):
    value = (raw_value or '').strip()
    if not value or ':' not in value:
        return None, None

    node_type, node_id = value.split(':', 1)
    node_type = node_type.strip()
    node_id = node_id.strip()

    if node_type not in ORGANIGRAM_NODE_FIELD_MAP or not node_id:
        return None, None
    return node_type, node_id


def _resolve_organigram_node(ouvrage, raw_value, allow_point=True):
    node_type, node_id = _parse_organigram_node_token(raw_value)
    if not node_type:
        return None, None

    scope_ouvrage_ids = _get_organigramme_scope_ouvrage_ids(ouvrage)

    if node_type == 'equipement':
        node = EquipementConstitutif.objects.select_related('ouvrage').filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).get(pk=node_id)
    elif node_type == 'compteur':
        node = CompteurTete.objects.select_related('ouvrage').filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).get(pk=node_id)
    else:
        node = PointEau.objects.select_related('ouvrage').filter(
            ouvrage_id__in=scope_ouvrage_ids
        ).get(pk=node_id)

    return node_type, node


def _get_liaison_queryset():
    return LiaisonHydraulique.objects.select_related(*ORGANIGRAMME_SELECT_RELATED)


def _get_inbound_liaison(node_type, node):
    suffix = _get_organigram_field_suffix(node_type)
    return _get_liaison_queryset().filter(
        **{f'aval_{suffix}': node},
        actif=True,
    ).order_by('ordre', 'created_at').first()


def _get_outbound_liaisons(node_type, node):
    suffix = _get_organigram_field_suffix(node_type)
    return _get_liaison_queryset().filter(
        **{f'amont_{suffix}': node},
        actif=True,
    ).order_by('ordre', 'created_at')


def _replace_inbound_liaison(ouvrage, target_type, target_node, source_type=None, source_node=None):
    target_suffix = _get_organigram_field_suffix(target_type)
    LiaisonHydraulique.objects.filter(**{f'aval_{target_suffix}': target_node}).delete()

    if not source_type or source_node is None:
        return

    source_suffix = _get_organigram_field_suffix(source_type)
    liaison = LiaisonHydraulique(
        ouvrage=ouvrage,
        **{
            f'amont_{source_suffix}': source_node,
            f'aval_{target_suffix}': target_node,
        }
    )
    liaison.full_clean()
    liaison.save()


def _replace_outbound_liaisons(ouvrage, source_type, source_node, raw_targets):
    source_suffix = _get_organigram_field_suffix(source_type)
    LiaisonHydraulique.objects.filter(**{f'amont_{source_suffix}': source_node}).delete()

    ordered_targets = []
    for raw_target in raw_targets:
        value = (raw_target or '').strip()
        if value and value not in ordered_targets:
            ordered_targets.append(value)

    for index, raw_target in enumerate(ordered_targets):
        target_type, target_node = _resolve_organigram_node(ouvrage, raw_target, allow_point=True)
        if not target_type or target_node is None:
            continue

        target_suffix = _get_organigram_field_suffix(target_type)
        liaison = LiaisonHydraulique(
            ouvrage=ouvrage,
            ordre=index,
            **{
                f'amont_{source_suffix}': source_node,
                f'aval_{target_suffix}': target_node,
            }
        )
        liaison.full_clean()
        liaison.save()


def _get_point_amont_token(point):
    liaison = _get_inbound_liaison('point_eau', point)
    if liaison:
        amont_type = liaison.get_amont_type()
        amont_node = liaison.get_amont_node()
        if amont_type and amont_node:
            return _build_organigram_node_value(amont_type, amont_node)

    if point.compteur_tete_id:
        return _build_organigram_node_value('compteur', point.compteur_tete)

    return ''


def _get_node_organigram_payload(node_type, node):
    inbound = _get_inbound_liaison(node_type, node)
    outbound = _get_outbound_liaisons(node_type, node)

    amont_node = inbound.get_amont_node() if inbound else None
    amont_type = inbound.get_amont_type() if inbound else None

    return {
        'amont_node': _build_organigram_node_value(amont_type, amont_node) if amont_type and amont_node else '',
        'amont_label': _build_organigram_node_label(amont_type, amont_node) if amont_type and amont_node else '',
        'aval_nodes': [
            _build_organigram_node_value(liaison.get_aval_type(), liaison.get_aval_node())
            for liaison in outbound
            if liaison.get_aval_type() and liaison.get_aval_node()
        ],
    }

def organization_list(request):
    """Page principale pour la gestion des organisations"""
    organisations = Organisation.objects.all().order_by('nom_organisation')
    est_directeur = user_is_director(request.user)
    return render(request, 'organization/organization_list.html', {
        'organisations': organisations,
        'title': 'Gestion des Organisations',
        'est_directeur': est_directeur,
    })


# CRUD pour les Organisations
def organisation_list(request):
    organisations = Organisation.objects.all().order_by('nom_organisation')
    est_directeur = user_is_director(request.user)
    return render(request, 'organization/organization_list.html', {
        'organisations': organisations,
        'title': 'Gestion en Cascade - Organisations',
        'est_directeur': est_directeur,
    })


def organisation_create(request):
    if request.method == 'POST':
        form = OrganisationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Organisation créée avec succès!')
            return redirect('organization:organisation_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = OrganisationForm()

    return render(request, 'organization/organisation_form.html', {
        'form': form,
        'title': 'Nouvelle Organisation'
    })


def organisation_detail(request, pk):
    organisation = get_object_or_404(Organisation, pk=pk)
    ouvrages = organisation.ouvrages.all().order_by('nom_ouvrage')
    bases = organisation.bases.all().order_by('nom_base')
    return render(request, 'organization/organisation_detail.html', {
        'organisation': organisation,
        'ouvrages': ouvrages,
        'bases': bases,
        'title': f'Organisation {organisation.nom_organisation}'
    })


def organisation_update(request, pk):
    organisation = get_object_or_404(Organisation, pk=pk)
    if request.method == 'POST':
        form = OrganisationForm(request.POST, request.FILES, instance=organisation)
        if form.is_valid():
            form.save()
            messages.success(request, 'Organisation modifiée avec succès!')
            return redirect('organization:organisation_detail', pk=pk)
    else:
        form = OrganisationForm(instance=organisation)

    return render(request, 'organization/organisation_form.html', {
        'form': form,
        'organisation': organisation,
        'title': 'Modifier Organisation'
    })


def organisation_delete(request, pk):
    organisation = get_object_or_404(Organisation, pk=pk)
    if request.method == 'POST':
        organisation.delete()
        messages.success(request, 'Organisation supprimée avec succès!')
        return redirect('organization:organisation_list')
    return render(request, 'organization/organisation_confirm_delete.html', {
        'organisation': organisation,
        'title': 'Supprimer Organisation'
    })


def partenaire_gestionnaire_affectations(request):
    """Gestion des affectations Partenaire -> Gestionnaire."""
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'create':
                partenaire_id = request.POST.get('partenaire_id')
                gestionnaire_id = request.POST.get('gestionnaire_id')
                affectation = PartenaireGestionnaireAffectation.objects.create(
                    partenaire_id=partenaire_id,
                    gestionnaire_id=gestionnaire_id,
                )
                messages.success(
                    request,
                    f'Affectation créée: {affectation.partenaire.nom_organisation} -> {affectation.gestionnaire.nom_organisation}.'
                )
            elif action == 'delete':
                affectation_id = request.POST.get('affectation_id')
                affectation = get_object_or_404(PartenaireGestionnaireAffectation, pk=affectation_id)
                label = f'{affectation.partenaire.nom_organisation} -> {affectation.gestionnaire.nom_organisation}'
                affectation.delete()
                messages.success(request, f'Affectation supprimée: {label}.')
        except Exception as exc:
            messages.error(request, f'Erreur sur l\'affectation: {exc}')
        return redirect('organization:partenaire_gestionnaire_affectations')

    est_directeur = user_is_director(request.user)
    types_point_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')
    partenaires = Organisation.objects.filter(
        type_organisation=Organisation.TYPE_PARTENAIRE
    ).order_by('nom_organisation')
    gestionnaires = get_gestionnaire_organisations_queryset()
    affectations = PartenaireGestionnaireAffectation.objects.select_related(
        'partenaire',
        'gestionnaire'
    ).order_by('partenaire__nom_organisation', 'gestionnaire__nom_organisation')

    return render(request, 'organization/partenaire_gestionnaire_affectations.html', {
        'title': 'Affectations Partenaires/Gestionnaires',
        'est_directeur': est_directeur,
        'partenaires': partenaires,
        'gestionnaires': gestionnaires,
        'affectations': affectations,
    })


# CRUD pour les Types d'ouvrages
def type_ouvrage_list(request):
    types = TypeOuvrage.objects.all().order_by('nom_type_ouvrage')
    return render(request, 'organization/type_ouvrage_list.html', {
        'types': types,
        'title': 'Types d\'Ouvrages'
    })


def type_ouvrage_create(request):
    if request.method == 'POST':
        form = TypeOuvrageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Type d\'ouvrage créé avec succès!')
            return redirect('organization:type_ouvrage_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = TypeOuvrageForm()

    return render(request, 'organization/type_ouvrage_form.html', {
        'form': form,
        'title': 'Nouveau Type d\'Ouvrage'
    })


def type_ouvrage_detail(request, pk):
    type_ouvrage = get_object_or_404(TypeOuvrage, pk=pk)
    ouvrages = type_ouvrage.ouvrages.all().order_by('nom_ouvrage')
    return render(request, 'organization/type_ouvrage_detail.html', {
        'type_ouvrage': type_ouvrage,
        'ouvrages': ouvrages,
        'title': f'Type {type_ouvrage.nom_type_ouvrage}'
    })


def type_ouvrage_update(request, pk):
    type_ouvrage = get_object_or_404(TypeOuvrage, pk=pk)
    if request.method == 'POST':
        form = TypeOuvrageForm(request.POST, instance=type_ouvrage)
        if form.is_valid():
            form.save()
            messages.success(request, 'Type d\'ouvrage modifié avec succès!')
            return redirect('organization:type_ouvrage_detail', pk=pk)
    else:
        form = TypeOuvrageForm(instance=type_ouvrage)

    return render(request, 'organization/type_ouvrage_form.html', {
        'form': form,
        'type_ouvrage': type_ouvrage,
        'title': 'Modifier Type d\'Ouvrage'
    })


def type_ouvrage_delete(request, pk):
    type_ouvrage = get_object_or_404(TypeOuvrage, pk=pk)
    if request.method == 'POST':
        type_ouvrage.delete()
        messages.success(request, 'Type d\'ouvrage supprimé avec succès!')
        return redirect('organization:type_ouvrage_list')
    return render(request, 'organization/type_ouvrage_confirm_delete.html', {
        'type_ouvrage': type_ouvrage,
        'title': 'Supprimer Type d\'Ouvrage'
    })


# CRUD pour les Types d'Équipements
def type_equipement_list(request):
    """Liste des types d'équipements"""
    from apps.infrastructure.models import TypeEquipement
    from django.db.models import Count

    types_equipements = TypeEquipement.objects.annotate(
        equipements_count=Count('equipements')
    ).order_by('nom_type')

    return render(request, 'organization/type_equipement_list.html', {
        'types_equipements': types_equipements,
        'title': 'Types d\'Équipements'
    })


def type_equipement_create(request):
    """Créer un nouveau type d'équipement"""
    from apps.infrastructure.models import TypeEquipement

    if request.method == 'POST':
        nom_type = request.POST.get('nom_type', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if nom_type:
            try:
                type_equipement = TypeEquipement.objects.create(
                    nom_type=nom_type,
                    description=description,
                    is_active=is_active
                )
                messages.success(request, f'Type d\'équipement "{nom_type}" créé avec succès!')
                return redirect('organization:type_equipement_detail', pk=type_equipement.pk)
            except Exception as e:
                if 'unique constraint' in str(e).lower():
                    messages.error(request, f'Un type d\'équipement avec le nom "{nom_type}" existe déjà.')
                else:
                    messages.error(request, f'Erreur lors de la création : {str(e)}')
        else:
            messages.error(request, 'Le nom du type d\'équipement est obligatoire.')

    return render(request, 'organization/type_equipement_form.html', {
        'title': 'Nouveau Type d\'Équipement'
    })


def type_equipement_detail(request, pk):
    """Détail d'un type d'équipement"""
    from apps.infrastructure.models import TypeEquipement

    type_equipement = get_object_or_404(TypeEquipement, pk=pk)
    equipements = type_equipement.equipements.select_related('ouvrage').all()

    return render(request, 'organization/type_equipement_detail.html', {
        'type_equipement': type_equipement,
        'equipements': equipements,
        'title': f'Type d\'Équipement: {type_equipement.nom_type}'
    })


def type_equipement_update(request, pk):
    """Modifier un type d'équipement"""
    from apps.infrastructure.models import TypeEquipement

    type_equipement = get_object_or_404(TypeEquipement, pk=pk)

    if request.method == 'POST':
        nom_type = request.POST.get('nom_type', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if nom_type:
            try:
                type_equipement.nom_type = nom_type
                type_equipement.description = description
                type_equipement.is_active = is_active
                type_equipement.save()

                messages.success(request, f'Type d\'équipement "{nom_type}" modifié avec succès!')
                return redirect('organization:type_equipement_detail', pk=pk)
            except Exception as e:
                if 'unique constraint' in str(e).lower():
                    messages.error(request, f'Un type d\'équipement avec le nom "{nom_type}" existe déjà.')
                else:
                    messages.error(request, f'Erreur lors de la modification : {str(e)}')
        else:
            messages.error(request, 'Le nom du type d\'équipement est obligatoire.')

    return render(request, 'organization/type_equipement_form.html', {
        'type_equipement': type_equipement,
        'title': 'Modifier Type d\'Équipement'
    })


def type_equipement_delete(request, pk):
    """Supprimer un type d'équipement"""
    from apps.infrastructure.models import TypeEquipement

    type_equipement = get_object_or_404(TypeEquipement, pk=pk)
    equipements_count = type_equipement.equipements.count()

    if request.method == 'POST':
        if equipements_count > 0:
            messages.error(request, f'Impossible de supprimer ce type d\'équipement car {equipements_count} équipement(s) l\'utilise(nt).')
            return redirect('organization:type_equipement_detail', pk=pk)

        nom_type = type_equipement.nom_type
        type_equipement.delete()
        messages.success(request, f'Type d\'équipement "{nom_type}" supprimé avec succès!')
        return redirect('organization:type_equipement_list')

    return render(request, 'organization/type_equipement_confirm_delete.html', {
        'type_equipement': type_equipement,
        'equipements_count': equipements_count,
        'title': 'Supprimer Type d\'Équipement'
    })


# CRUD pour les Ouvrages
@employe_required
def ouvrage_list(request):
    from apps.billing.models import PointEau, CompteurTete, Fournisseur, TarifVolumetrique, ModaliteGestion
    from apps.infrastructure.models import EquipementConstitutif, Adresse, CarteSociale
    from apps.geography.models import Region, District, Commune
    from apps.employees.models import Employe
    from apps.billing.points_eau_statut import q_abandonne, q_actif, q_coupe, q_sans_date
    from django.db.models import Count, Q
    from django.core.paginator import Paginator

    # Filtrer les ouvrages selon les permissions de l'employé
    from django.db.models import Subquery, OuterRef

    # Récupérer l'organisation gestionnaire depuis la modalité active
    modalite_active_subquery = ModaliteGestion.objects.filter(
        ouvrage=OuterRef('pk'),
        statut='actif'
    ).values('gestionnaire__nom_organisation')[:1]

    modalite_active_id_subquery = ModaliteGestion.objects.filter(
        ouvrage=OuterRef('pk'),
        statut='actif'
    ).values('gestionnaire_id')[:1]

    ouvrages_sources_base = Ouvrage.objects.filter(
        Q(type_ouvrage__nom_type_ouvrage__iexact='AEPG')
    )
    if not (request.user.is_superuser or user_is_director(request.user)):
        ouvrages_sources_base = filter_queryset_by_permissions(
            ouvrages_sources_base,
            request.user,
        )
    ouvrages_sources = ouvrages_sources_base.select_related(
        'type_ouvrage'
    ).order_by('nom_ouvrage')

    # Appliquer le filtre de permissions AVANT les annotations.
    #
    # Important : ne pas annoter ce queryset ici. Cette liste est paginee et
    # Django execute d'abord un COUNT(*) pour connaitre le nombre de pages.
    # Les nombreux Count() sur les relations (points d'eau, equipements,
    # tarifs, modalites, etc.) transformaient ce COUNT en une aggregation
    # couteuse sur tout le parc et pouvaient conduire a un Gateway Timeout.
    # Les annotations d'affichage sont faites uniquement pour les 50 lignes de
    # la page courante, apres la pagination.
    ouvrages = Ouvrage.objects.all()
    if not (request.user.is_superuser or user_is_director(request.user)):
        ouvrages = filter_queryset_by_permissions(ouvrages, request.user)
    ouvrages = ouvrages.select_related('type_ouvrage').order_by('nom_ouvrage')

    # Appliquer les filtres depuis la requête GET
    search_query = request.GET.get('search', '').strip()
    type_filter = request.GET.get('type', '')
    organisation_filter = request.GET.get('organisation', '')
    responsible_employee_filter = request.GET.get('responsible_employee', '').strip()
    region_filter = request.GET.get('region', '').strip()
    district_filter = request.GET.get('district', '').strip()
    commune_filter = request.GET.get('commune', '').strip()
    responsibility_reference_date = timezone.localdate()
    eligible_responsible_employee_ids = get_employe_ids_with_responsible_ouvrage_scope(
        responsibility_reference_date
    )

    # Filtres par présence de données
    has_points_eau = request.GET.get('has_points_eau')
    has_compteurs = request.GET.get('has_compteurs')
    has_equipements = request.GET.get('has_equipements')
    has_tarifs = request.GET.get('has_tarifs')
    has_modalites = request.GET.get('has_modalites')
    has_adresses = request.GET.get('has_adresses')
    has_cartes_sociales = request.GET.get('has_cartes_sociales')

    # Filtre saisonnier
    saisonnier_filter = request.GET.get('saisonnier')
    fonctionnalite_filter = request.GET.get('fonctionnalite', '').strip()
    if fonctionnalite_filter not in ('fonctionnel', 'non_fonctionnel'):
        fonctionnalite_filter = ''

    if search_query:
        ouvrages = ouvrages.filter(
            Q(nom_ouvrage__icontains=search_query) |
            Q(type_ouvrage__nom_type_ouvrage__icontains=search_query)
        )

    if type_filter and type_filter != 'all':
        ouvrages = ouvrages.filter(type_ouvrage_id=type_filter)

    # Filtrer par organisation (via modalités actives)
    if organisation_filter and organisation_filter != 'all':
        ouvrages = ouvrages.filter(
            modalites_gestion__statut='actif',
            modalites_gestion__gestionnaire_id=organisation_filter
        ).distinct()

    # Un responsable selectionne couvre ses propres ouvrages et ceux de toute
    # sa hierarchie descendante active. Le queryset reste deja borne par les
    # permissions de l'utilisateur connecte.
    if responsible_employee_filter and responsible_employee_filter != 'all':
        try:
            selected_employee = Employe.objects.filter(
                pk=responsible_employee_filter,
                date_debauchage__isnull=True,
                pk__in=eligible_responsible_employee_ids,
            ).first()
        except (TypeError, ValueError, ValidationError):
            selected_employee = None
        if selected_employee:
            responsible_ouvrage_ids = get_active_employee_ouvrage_ids(
                selected_employee.pk,
                responsibility_reference_date,
            )
            ouvrages = ouvrages.filter(pk__in=responsible_ouvrage_ids)
        else:
            ouvrages = ouvrages.none()

    # Les choix geographiques sont eux-memes limites aux ouvrages accessibles
    # et, le cas echeant, au perimetre du responsable choisi.
    # L'ordre d'affichage n'est pas utile dans les sous-requetes de
    # geographie ; le retirer evite un tri superflu dans chaque SELECT IN.
    geography_scope_ids = ouvrages.order_by().values_list('pk', flat=True)
    regions = Region.objects.filter(
        districts__communes__fokontanys__villages__parcelles__pointeau__ouvrage_id__in=geography_scope_ids
    ).distinct().order_by('nom_region')
    if region_filter and region_filter != 'all':
        try:
            if not regions.filter(pk=region_filter).exists():
                region_filter = 'all'
        except (TypeError, ValueError, ValidationError):
            region_filter = 'all'
    districts = District.objects.filter(
        communes__fokontanys__villages__parcelles__pointeau__ouvrage_id__in=geography_scope_ids
    )
    if region_filter and region_filter != 'all':
        districts = districts.filter(region_id=region_filter)
    districts = districts.distinct().order_by('nom_district')
    if district_filter and district_filter != 'all':
        try:
            if not districts.filter(pk=district_filter).exists():
                district_filter = 'all'
        except (TypeError, ValueError, ValidationError):
            district_filter = 'all'
    communes = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage_id__in=geography_scope_ids
    )
    if district_filter and district_filter != 'all':
        communes = communes.filter(district_id=district_filter)
    elif region_filter and region_filter != 'all':
        communes = communes.filter(district__region_id=region_filter)
    communes = communes.distinct().order_by('nom_commune')
    if commune_filter and commune_filter != 'all':
        try:
            if not communes.filter(pk=commune_filter).exists():
                commune_filter = 'all'
        except (TypeError, ValueError, ValidationError):
            commune_filter = 'all'

    if region_filter and region_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_filter
        ).distinct()
    if district_filter and district_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_filter
        ).distinct()
    if commune_filter and commune_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_filter
        ).distinct()

    # Filtrer par présence de données associées
    if has_points_eau:
        ouvrages = ouvrages.filter(q_actif('pointeau__')).distinct()

    if has_compteurs:
        ouvrages = ouvrages.filter(compteurs_tete__isnull=False).distinct()

    if has_equipements:
        ouvrages = ouvrages.filter(equipements_constitutifs__isnull=False).distinct()

    if has_adresses:
        ouvrages = ouvrages.filter(adresses_infra__isnull=False).distinct()

    if has_tarifs:
        ouvrages = ouvrages.filter(tarifs_volumetriques__datefintarif__isnull=True).distinct()

    if has_modalites:
        ouvrages = ouvrages.filter(modalites_gestion__statut='actif').distinct()

    if has_cartes_sociales:
        ouvrages = ouvrages.filter(cartes_sociales_infra__isnull=False).distinct()

    # Filtre saisonnier
    if saisonnier_filter == 'true':
        ouvrages = ouvrages.filter(saisonnier=True)
    elif saisonnier_filter == 'false':
        ouvrages = ouvrages.filter(saisonnier=False)

    # Un ouvrage est non fonctionnel s'il est marque manuellement comme tel
    # ou s'il a un chantier actif (la regle est partagee avec le service
    # services_fonctionnalite). Ce filtre SQL evite de charger tous les
    # ouvrages en Python uniquement pour connaitre leur statut.
    if fonctionnalite_filter:
        from apps.chantiers.models_workflow import ChantierWorkflow
        from .services_fonctionnalite import CHANTIER_STATUTS_ACTIFS

        ouvrages_non_fonctionnels = ChantierWorkflow.objects.filter(
            statut__in=CHANTIER_STATUTS_ACTIFS,
        ).values('ouvrage_id')
        non_fonctionnel_q = (
            Q(marque_non_fonctionnel=True)
            | Q(pk__in=ouvrages_non_fonctionnels)
        )
        if fonctionnalite_filter == 'non_fonctionnel':
            ouvrages = ouvrages.filter(non_fonctionnel_q)
        else:
            ouvrages = ouvrages.exclude(non_fonctionnel_q)

    # ✅ Filtre pour masquer les ouvrages inexistants (activé par défaut : True si le
    # paramètre n'est pas présent dans l'URL, sinon respecte le choix explicite '0'/'1')
    hide_inexistants_param = request.GET.get('hide_inexistants')
    if hide_inexistants_param is None:
        hide_inexistants = True
    else:
        hide_inexistants = hide_inexistants_param not in ('0', '', 'false', 'False')
    if hide_inexistants:
        ouvrages = ouvrages.filter(type_ouvrage__existe=True)

    # Alerte debit de source (calcul partage avec /plannings/debits-source/)
    debit_filter = request.GET.get('debit', '').strip()
    if debit_filter == 'critique':
        from apps.planning.services_debit_critique import ids_ouvrages_par_niveau
        ouvrages = ouvrages.filter(pk__in=ids_ouvrages_par_niveau('critique'))

    # Pagination sur le queryset leger. Les donnees relationnelles sont
    # annotees juste apres, pour les seules lignes visibles.
    paginator = Paginator(ouvrages, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    page_ouvrage_ids = list(page_obj.object_list.values_list('id', flat=True))
    if page_ouvrage_ids:
        ouvrages_page_by_id = {
            ouvrage.id: ouvrage
            for ouvrage in Ouvrage.objects.filter(id__in=page_ouvrage_ids).select_related(
                'type_ouvrage'
            ).prefetch_related('dossiers_techniques').annotate(
                # Points d'eau existants = actifs ; coupes et sans date
                # comptes a part.
                nb_points_eau=Count('pointeau', filter=q_actif('pointeau__'), distinct=True),
                nb_points_eau_coupes=Count('pointeau', filter=q_coupe('pointeau__'), distinct=True),
                nb_points_eau_abandonnes=Count('pointeau', filter=q_abandonne('pointeau__'), distinct=True),
                nb_points_eau_sans_date=Count('pointeau', filter=q_sans_date('pointeau__'), distinct=True),
                nb_compteurs_tete=Count('compteurs_tete', distinct=True),
                nb_tarifs=Count('tarifs_volumetriques', filter=Q(tarifs_volumetriques__datefintarif__isnull=True), distinct=True),
                nb_modalites=Count('modalites_gestion', filter=Q(modalites_gestion__statut='actif'), distinct=True),
                nb_equipements=Count('equipements_constitutifs', distinct=True),
                nb_adresses=Count('adresses_infra', distinct=True),
                nb_dossiers_techniques=Count('dossiers_techniques', distinct=True),
                gestionnaire_actif_nom=Subquery(modalite_active_subquery),
                gestionnaire_actif_id=Subquery(modalite_active_id_subquery),
            )
        }
        # Restituer l'ordre etabli par le paginator (nom d'ouvrage).
        page_obj.object_list = [
            ouvrages_page_by_id[ouvrage_id]
            for ouvrage_id in page_ouvrage_ids
            if ouvrage_id in ouvrages_page_by_id
        ]

    # Note: equipements sont maintenant liés à organization.Ouvrage (related_name='equipements_constitutifs')
    # adresses et cartes_sociales restent liés à infrastructure.Ouvrage uniquement

    # Compter uniquement les ouvrages avec des points d'eau actifs (branchés, non coupés)
    ouvrages_avec_pointeau = Ouvrage.objects.filter(q_actif('pointeau__')).distinct().count()

    # Ajouter les données nécessaires pour les modales
    # Utiliser les types d'ouvrages de l'app organization (même table que celle utilisée par la FK)
    types_ouvrages = TypeOuvrage.objects.all().order_by('nom_type_ouvrage')
    organisations = Organisation.objects.all().order_by('nom_organisation')
    active_employees = Employe.objects.filter(
        date_debauchage__isnull=True,
        pk__in=eligible_responsible_employee_ids,
    ).select_related('poste', 'base').order_by(
        'base__nom_base', 'poste__nom_poste', 'nom_employe'
    )
    employee_groups = []
    for employee in active_employees:
        base_label = getattr(employee.base, 'nom_base', None) or 'Base non definie'
        poste_label = getattr(employee.poste, 'nom_poste', None) or 'Poste non defini'
        if not employee_groups or employee_groups[-1]['label'] != base_label:
            employee_groups.append({'label': base_label, 'postes': []})
        postes = employee_groups[-1]['postes']
        if not postes or postes[-1]['label'] != poste_label:
            postes.append({'label': poste_label, 'employees': []})
        postes[-1]['employees'].append(employee)
    adresses = Adresse.objects.all().order_by('nomadresse')

    # Compteurs filtrés selon les critères appliqués
    # Appliquer tous les filtres actifs pour les compteurs
    # La liste est reutilisee par les compteurs et le bandeau debit. La
    # materialiser une seule fois evite de rejouer le queryset filtre (et ses
    # jointures geographiques) dans chacun des compteurs.
    ouvrages_filtres_ids = list(ouvrages.values_list('id', flat=True))

    ouvrages_avec_dossier_technique = Ouvrage.objects.filter(
        id__in=ouvrages_filtres_ids,
        dossiers_techniques__isnull=False,
    ).distinct().count()
    ouvrages_aepg = Ouvrage.objects.filter(
        id__in=ouvrages_filtres_ids,
        type_ouvrage__nom_type_ouvrage__iexact='AEPG',
    )
    ouvrages_aepg_total = ouvrages_aepg.count()
    ouvrages_aepg_avec_dossier_technique = ouvrages_aepg.filter(
        dossiers_techniques__isnull=False,
    ).distinct().count()
    pourcentage_aepg_avec_dossier_technique = (
        round((ouvrages_aepg_avec_dossier_technique / ouvrages_aepg_total) * 100)
        if ouvrages_aepg_total
        else 0
    )

    from apps.billing.points_eau_statut import compter_statuts
    points_eau_statuts = compter_statuts(PointEau.objects.filter(ouvrage_id__in=ouvrages_filtres_ids))
    stats_counts = {
        'points_eau': points_eau_statuts['actifs'],
        'points_eau_coupes': points_eau_statuts['coupes'],
        'points_eau_abandonnes': points_eau_statuts['abandonnes'],
        'points_eau_sans_date': points_eau_statuts['sans_date'],
        'equipements': EquipementConstitutif.objects.filter(
            ouvrage_id__in=ouvrages_filtres_ids
        ).count(),
        'compteurs_tete': CompteurTete.objects.filter(
            ouvrage_id__in=ouvrages_filtres_ids
        ).count(),
        'adresses': Adresse.objects.filter(
            ouvrage_id__in=ouvrages_filtres_ids
        ).count(),
        'fournisseurs': Fournisseur.objects.filter(actif=True).count(),  # Total global (non filtré)
        'cartes_sociales': CarteSociale.objects.count(),  # Total global (non filtré)
        'tarifs': TarifVolumetrique.objects.filter(
            ouvrage_id__in=ouvrages_filtres_ids,
            datefintarif__isnull=True
        ).count(),
        'modalites': ModaliteGestion.objects.filter(
            ouvrage_id__in=ouvrages_filtres_ids,
            statut='actif'
        ).count(),
        'organisations': Organisation.objects.filter(
            id__in=ModaliteGestion.objects.filter(
                ouvrage_id__in=ouvrages_filtres_ids,
                statut='actif'
            ).values_list('gestionnaire_id', flat=True)
        ).distinct().count(),
        'types_ouvrages': TypeOuvrage.objects.filter(
            id__in=Ouvrage.objects.filter(
                id__in=ouvrages_filtres_ids
            ).values_list('type_ouvrage_id', flat=True)
        ).distinct().count(),
        'saisonniers': Ouvrage.objects.filter(
            q_actif('pointeau__'),  # ouvrages avec points d'eau actifs
            id__in=ouvrages_filtres_ids,
            saisonnier=True,
        ).distinct().count(),
        'non_saisonniers': Ouvrage.objects.filter(
            q_actif('pointeau__'),  # ouvrages avec points d'eau actifs
            id__in=ouvrages_filtres_ids,
            saisonnier=False,
        ).distinct().count(),
        'dossiers_techniques': ouvrages_avec_dossier_technique,
        'aepg_total': ouvrages_aepg_total,
        'aepg_avec_dossier_technique': ouvrages_aepg_avec_dossier_technique,
        'pourcentage_aepg_avec_dossier_technique': pourcentage_aepg_avec_dossier_technique,
    }

    # Compter les ouvrages avec points d'eau parmi les ouvrages filtrés
    ouvrages_avec_pointeau = Ouvrage.objects.filter(
        q_actif('pointeau__'),
        id__in=ouvrages_filtres_ids,
    ).distinct().count()

    # Statut fonctionnel : calcul SQL pour tous les compteurs ; le service
    # detaille n'est appele que pour les 50 ouvrages affiches plus bas.
    from apps.chantiers.models_workflow import ChantierWorkflow
    from .services_fonctionnalite import (
        CHANTIER_STATUTS_ACTIFS,
        get_statuts_fonctionnel_bulk,
    )

    ouvrages_chantier_actif = ChantierWorkflow.objects.filter(
        statut__in=CHANTIER_STATUTS_ACTIFS,
    ).values('ouvrage_id')
    ouvrages_non_fonctionnels_count = Ouvrage.objects.filter(
        id__in=ouvrages_filtres_ids,
    ).filter(
        Q(marque_non_fonctionnel=True) | Q(pk__in=ouvrages_chantier_actif)
    ).count()
    ouvrages_fonctionnels_count = len(ouvrages_filtres_ids) - ouvrages_non_fonctionnels_count
    stats_counts['fonctionnels'] = ouvrages_fonctionnels_count
    stats_counts['non_fonctionnels'] = ouvrages_non_fonctionnels_count

    # Annoter les ouvrages de la page courante avec leur statut fonctionnel
    statuts_fonctionnel_page = get_statuts_fonctionnel_bulk([o.id for o in page_obj.object_list])
    for ouvrage_row in page_obj.object_list:
        ouvrage_row.statut_fonctionnel = statuts_fonctionnel_page.get(ouvrage_row.id)

    est_directeur = user_is_director(request.user)
    ouvrages_sources_data = [
        {
            'id': str(o.id),
            'label': f"{o.nom_ouvrage} ({getattr(getattr(o, 'type_ouvrage', None), 'nom_type_ouvrage', '') or 'Type non défini'})",
        }
        for o in ouvrages_sources
    ]

    debit_query = request.GET.copy()
    debit_query.pop('page', None)
    debit_query['debit'] = 'critique'

    return render(request, 'organization/ouvrage_list.html', {
        'debit_scope_ids': list(ouvrages_filtres_ids),
        'debit_filter': debit_filter,
        'debit_filtre_url': f"?{debit_query.urlencode()}",
        'page_obj': page_obj,
        'ouvrages': page_obj,  # Alias pour compatibilité avec les filtres JS
        'ouvrages_avec_pointeau': ouvrages_avec_pointeau,
        'types_ouvrages': types_ouvrages,
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'active_employees': active_employees,
        'employee_groups': employee_groups,
        'ouvrages_sources': ouvrages_sources,
        'ouvrages_sources_data': ouvrages_sources_data,
        'stats_counts': stats_counts,
        'search_query': search_query,
        'type_filter': type_filter,
        'organisation_filter': organisation_filter,
        'fonctionnalite_filter': fonctionnalite_filter,
        'hide_inexistants': hide_inexistants,
        'title': 'Ouvrages',
        'est_directeur': est_directeur,
    })


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_toggle_fonctionnel(request, ouvrage_id):
    """Bascule la case manuelle 'marqué non fonctionnel' d'un ouvrage.

    Refuse la modification si un chantier actif existe pour cet ouvrage : dans
    ce cas le statut fonctionnel est déterminé par le chantier, pas par la
    case manuelle (voir apps.organization.services_fonctionnalite).
    """
    from .services_fonctionnalite import get_ouvrages_chantier_actif_ids

    ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

    if ouvrage.id in get_ouvrages_chantier_actif_ids([ouvrage.id]):
        return JsonResponse({
            'success': False,
            'error': "Un chantier actif est en cours pour cet ouvrage : le statut est géré automatiquement.",
        }, status=400)

    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    valeur = payload.get('marque_non_fonctionnel')
    if not isinstance(valeur, bool):
        return JsonResponse({'success': False, 'error': "Champ 'marque_non_fonctionnel' (bool) requis."}, status=400)

    ouvrage.marque_non_fonctionnel = valeur
    ouvrage.save(update_fields=['marque_non_fonctionnel'])

    return JsonResponse({'success': True, 'marque_non_fonctionnel': ouvrage.marque_non_fonctionnel})


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_dossier_technique_checklist(request, ouvrage_id):
    """Enregistre un document couvert par le dossier technique d'un AEPG."""
    ouvrage = get_object_or_404(
        filter_queryset_by_permissions(
            Ouvrage.objects.filter(type_ouvrage__nom_type_ouvrage__iexact='AEPG'),
            request.user,
        ),
        pk=ouvrage_id,
    )
    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Données JSON invalides.'}, status=400)

    document = payload.get('document')
    checked = payload.get('checked')
    allowed_fields = {key for key, _label in DOSSIER_TECHNIQUE_DOCUMENTS}
    if document not in allowed_fields or not isinstance(checked, bool):
        return JsonResponse({'success': False, 'error': 'Document ou valeur invalide.'}, status=400)

    checklist, _created = OuvrageDossierTechniqueChecklist.objects.get_or_create(ouvrage=ouvrage)
    setattr(checklist, document, checked)
    checklist.save(update_fields=[document, 'updated_at'])

    values = {key: bool(getattr(checklist, key)) for key, _label in DOSSIER_TECHNIQUE_DOCUMENTS}
    completed = sum(values.values())
    return JsonResponse({
        'success': True,
        'documents': values,
        'completed': completed,
        'total': len(DOSSIER_TECHNIQUE_DOCUMENTS),
        'percentage': round((completed / len(DOSSIER_TECHNIQUE_DOCUMENTS)) * 100),
    })


@employe_required
def ouvrage_suivi_liaisons(request):
    """Suivi de la couverture des liaisons et des dossiers techniques."""
    from django.core.paginator import Paginator
    from apps.geography.models import Region, District, Commune

    extensions_accessibles = filter_queryset_by_permissions(
        Ouvrage.objects.only('id', 'nom_ouvrage', 'ouvrage_source_id'),
        request.user,
    ).order_by('nom_ouvrage')
    ouvrages = filter_queryset_by_permissions(
        Ouvrage.objects.filter(
            type_ouvrage__nom_type_ouvrage__iexact='AEPG'
        ).select_related('type_ouvrage').prefetch_related(
            models.Prefetch(
                'ouvrages_extensions',
                queryset=extensions_accessibles,
                to_attr='extensions_rattachees',
            )
        ),
        request.user,
    ).order_by('nom_ouvrage')
    ouvrages_accessibles_ids = ouvrages.values('pk')
    gestionnaire_ids_accessibles = get_user_accessible_gestionnaire_ids(request.user)
    organisations = get_gestionnaire_organisations_queryset().filter(
        modalites_gerees__date_fin__isnull=True,
        modalites_gerees__ouvrage_id__in=ouvrages_accessibles_ids,
    )
    if gestionnaire_ids_accessibles is not None:
        organisations = organisations.filter(pk__in=gestionnaire_ids_accessibles)
    organisations = organisations.distinct()
    organisation_ids = {str(item) for item in organisations.values_list('pk', flat=True)}
    search_query = request.GET.get('search', '').strip()
    liaison_filter = request.GET.get('liaison', 'all')
    dossier_filter = request.GET.get('dossier', 'all')
    organisation_filter = request.GET.get('organisation')
    if organisation_filter is None:
        organisation_connectee = get_user_organisation(request.user)
        organisation_connectee_id = str(getattr(organisation_connectee, 'pk', '') or '')
        organisation_filter = (
            organisation_connectee_id if organisation_connectee_id in organisation_ids
            else get_default_gestionnaire_filter_value(request.user, gestionnaire_ids_accessibles) or 'all'
        )
    if organisation_filter != 'all' and organisation_filter not in organisation_ids:
        organisation_filter = 'all'
    ouvrages_geographiques_ids = ouvrages_accessibles_ids
    if organisation_filter != 'all':
        ouvrages_geographiques_ids = ModaliteGestion.objects.filter(
            ouvrage_id__in=ouvrages_accessibles_ids,
            gestionnaire_id=organisation_filter,
            date_fin__isnull=True,
        ).values('ouvrage_id')
    regions = Region.objects.filter(
        districts__communes__fokontanys__villages__parcelles__pointeau__ouvrage_id__in=ouvrages_geographiques_ids
    ).distinct().order_by('nom_region')
    region_filter = request.GET.get('region', 'all')
    district_filter = request.GET.get('district', 'all')
    commune_filter = request.GET.get('commune', 'all')

    districts = District.objects.filter(
        communes__fokontanys__villages__parcelles__pointeau__ouvrage_id__in=ouvrages_geographiques_ids
    )
    if region_filter != 'all':
        districts = districts.filter(region_id=region_filter)
    districts = districts.distinct().order_by('nom_district')

    communes = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage_id__in=ouvrages_geographiques_ids
    )
    if district_filter != 'all':
        communes = communes.filter(district_id=district_filter)
    elif region_filter != 'all':
        communes = communes.filter(district__region_id=region_filter)
    communes = communes.distinct().order_by('nom_commune')

    if search_query:
        ouvrages = ouvrages.filter(
            models.Q(nom_ouvrage__icontains=search_query)
            | models.Q(type_ouvrage__nom_type_ouvrage__icontains=search_query)
        )
    if region_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_filter
        )
    if district_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_filter
        )
    if commune_filter != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_filter
        )
    if organisation_filter != 'all':
        ouvrages = ouvrages.filter(
            modalites_gestion__gestionnaire_id=organisation_filter,
            modalites_gestion__date_fin__isnull=True,
        )
    ouvrages = ouvrages.distinct()

    ouvrages_list = list(ouvrages)
    ouvrage_ids = [ouvrage.pk for ouvrage in ouvrages_list]
    equipements_par_ouvrage = {}
    equipement_ids = set()
    for equipement_id, ouvrage_id in EquipementConstitutif.objects.filter(
        ouvrage_id__in=ouvrage_ids
    ).values_list('id', 'ouvrage_id'):
        equipement_ids.add(equipement_id)
        equipements_par_ouvrage.setdefault(ouvrage_id, []).append(equipement_id)

    points_par_ouvrage = {}
    geographies_par_ouvrage = {}
    point_ids = set()
    point_rows = PointEau.objects.filter(
        ouvrage_id__in=ouvrage_ids
    ).values_list(
        'id', 'ouvrage_id',
        'parcelle__village__fokontany__commune_id',
        'parcelle__village__fokontany__commune__nom_commune',
        'parcelle__village__fokontany__commune__district_id',
        'parcelle__village__fokontany__commune__district__nom_district',
        'parcelle__village__fokontany__commune__district__region_id',
        'parcelle__village__fokontany__commune__district__region__nom_region',
    )
    for point_id, ouvrage_id, commune_id, commune_nom, district_id, district_nom, region_id, region_nom in point_rows:
        point_ids.add(point_id)
        points_par_ouvrage.setdefault(ouvrage_id, []).append(point_id)
        if commune_id:
            geographies_par_ouvrage.setdefault(ouvrage_id, {})[commune_id] = {
                'commune_id': str(commune_id),
                'commune': commune_nom,
                'district_id': str(district_id),
                'district': district_nom,
                'region_id': str(region_id),
                'region': region_nom,
            }

    equipements_lies = set()
    points_lies = set()
    if equipement_ids or point_ids:
        liaison_scope = models.Q()
        if equipement_ids:
            liaison_scope |= models.Q(amont_equipement_id__in=equipement_ids)
            liaison_scope |= models.Q(aval_equipement_id__in=equipement_ids)
        if point_ids:
            liaison_scope |= models.Q(amont_point_eau_id__in=point_ids)
            liaison_scope |= models.Q(aval_point_eau_id__in=point_ids)

        liaisons = LiaisonHydraulique.objects.filter(liaison_scope, actif=True).values_list(
            'amont_equipement_id', 'aval_equipement_id',
            'amont_point_eau_id', 'aval_point_eau_id',
        )
        for amont_eq, aval_eq, amont_point, aval_point in liaisons:
            if amont_eq:
                equipements_lies.add(amont_eq)
            if aval_eq:
                equipements_lies.add(aval_eq)
            if amont_point:
                points_lies.add(amont_point)
            if aval_point:
                points_lies.add(aval_point)

    dossiers_par_ouvrage = dict(
        OuvrageDossierTechnique.objects.filter(ouvrage_id__in=ouvrage_ids)
        .values('ouvrage_id').annotate(total=Count('id'))
        .values_list('ouvrage_id', 'total')
    )
    checklists_par_ouvrage = {
        checklist.ouvrage_id: checklist
        for checklist in OuvrageDossierTechniqueChecklist.objects.filter(ouvrage_id__in=ouvrage_ids)
    }
    suivi = []
    for ouvrage in ouvrages_list:
        equipements = equipements_par_ouvrage.get(ouvrage.pk, [])
        points = points_par_ouvrage.get(ouvrage.pk, [])
        equipements_lies_count = sum(item_id in equipements_lies for item_id in equipements)
        points_lies_count = sum(item_id in points_lies for item_id in points)
        equipements_manquants = len(equipements) - equipements_lies_count
        points_manquants = len(points) - points_lies_count
        total_elements = len(equipements) + len(points)
        total_lies = equipements_lies_count + points_lies_count
        if total_elements == 0:
            liaison_status = 'sans_elements'
        elif not equipements_manquants and not points_manquants:
            liaison_status = 'complet'
        else:
            liaison_status = 'a_completer'
        dossier_count = dossiers_par_ouvrage.get(ouvrage.pk, 0)
        checklist = checklists_par_ouvrage.get(ouvrage.pk)
        checklist_items = [
            {
                'key': key,
                'label': label,
                'checked': bool(checklist and getattr(checklist, key)),
            }
            for key, label in DOSSIER_TECHNIQUE_DOCUMENTS
        ]
        checklist_completed = sum(item['checked'] for item in checklist_items)
        extensions = list(getattr(ouvrage, 'extensions_rattachees', []))
        geographies = sorted(
            geographies_par_ouvrage.get(ouvrage.pk, {}).values(),
            key=lambda item: (item['region'].casefold(), item['district'].casefold(), item['commune'].casefold()),
        )
        geographies_filtrees = [
            geo for geo in geographies
            if (region_filter == 'all' or geo['region_id'] == region_filter)
            and (district_filter == 'all' or geo['district_id'] == district_filter)
            and (commune_filter == 'all' or geo['commune_id'] == commune_filter)
        ]
        primary_geo = (geographies_filtrees or geographies or [{
            'region': 'Sans région', 'district': 'Sans district', 'commune': 'Sans commune',
            'region_id': '', 'district_id': '', 'commune_id': '',
        }])[0]
        suivi.append({
            'ouvrage': ouvrage,
            'liaison_status': liaison_status,
            'equipements_total': len(equipements),
            'equipements_lies': equipements_lies_count,
            'equipements_manquants': equipements_manquants,
            'points_total': len(points),
            'points_lies': points_lies_count,
            'points_manquants': points_manquants,
            'total_elements': total_elements,
            'total_lies': total_lies,
            'progression': round((total_lies / total_elements) * 100) if total_elements else 0,
            'dossier_count': dossier_count,
            'has_dossier': dossier_count > 0,
            'dossier_checklist': checklist_items,
            'dossier_documents_completed': checklist_completed,
            'dossier_documents_total': len(DOSSIER_TECHNIQUE_DOCUMENTS),
            'dossier_documents_percentage': round(
                (checklist_completed / len(DOSSIER_TECHNIQUE_DOCUMENTS)) * 100
            ),
            'dossier_documents_complete': checklist_completed == len(DOSSIER_TECHNIQUE_DOCUMENTS),
            'extensions': extensions,
            'geographies': geographies,
            'region': primary_geo['region'],
            'district': primary_geo['district'],
            'commune': primary_geo['commune'],
        })

    stats = {
        'total': len(suivi),
        'ouvrages_rattaches': sum(len(item['extensions']) for item in suivi),
        'complets': sum(item['liaison_status'] == 'complet' for item in suivi),
        'a_completer': sum(item['liaison_status'] == 'a_completer' for item in suivi),
        'sans_elements': sum(item['liaison_status'] == 'sans_elements' for item in suivi),
        'avec_dossier': sum(item['has_dossier'] for item in suivi),
        'sans_dossier': sum(not item['has_dossier'] for item in suivi),
        'dossiers_documentes': sum(item['dossier_documents_complete'] for item in suivi),
        'dossiers_a_documenter': sum(not item['dossier_documents_complete'] for item in suivi),
    }
    if liaison_filter in {'complet', 'a_completer', 'sans_elements'}:
        suivi = [item for item in suivi if item['liaison_status'] == liaison_filter]
    if dossier_filter == 'avec':
        suivi = [item for item in suivi if item['has_dossier']]
    elif dossier_filter == 'sans':
        suivi = [item for item in suivi if not item['has_dossier']]
    elif dossier_filter == 'complet':
        suivi = [item for item in suivi if item['dossier_documents_complete']]
    elif dossier_filter == 'incomplet':
        suivi = [item for item in suivi if not item['dossier_documents_complete']]

    status_order = {'a_completer': 0, 'sans_elements': 1, 'complet': 2}
    suivi.sort(key=lambda item: (
        item['region'].casefold(), item['district'].casefold(), item['commune'].casefold(),
        status_order[item['liaison_status']], item['ouvrage'].nom_ouvrage.casefold(),
    ))
    page_obj = Paginator(suivi, 40).get_page(request.GET.get('page', 1))
    page_groups = []
    for item in page_obj.object_list:
        if not page_groups or page_groups[-1]['name'] != item['region']:
            page_groups.append({'name': item['region'], 'districts': []})
        region_group = page_groups[-1]
        if not region_group['districts'] or region_group['districts'][-1]['name'] != item['district']:
            region_group['districts'].append({'name': item['district'], 'communes': []})
        district_group = region_group['districts'][-1]
        if not district_group['communes'] or district_group['communes'][-1]['name'] != item['commune']:
            district_group['communes'].append({'name': item['commune'], 'items': []})
        district_group['communes'][-1]['items'].append(item)
    preserved_query = request.GET.copy()
    preserved_query.pop('page', None)
    preserved_query.pop('type', None)

    return render(request, 'organization/ouvrage_suivi_liaisons.html', {
        'page_obj': page_obj,
        'stats': stats,
        'page_groups': page_groups,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'organisations': organisations,
        'search_query': search_query,
        'liaison_filter': liaison_filter,
        'dossier_filter': dossier_filter,
        'organisation_filter': organisation_filter,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'preserved_query': preserved_query.urlencode(),
        'title': 'Suivi des liaisons et dossiers techniques',
    })


def ouvrage_create(request):
    if request.method == 'POST':
        form = OuvrageForm(request.POST, request.FILES)
        if form.is_valid():
            ouvrage = form.save()
            _save_ouvrage_dossier_technique_files(
                ouvrage,
                request.FILES.getlist('dossier_technique_files'),
            )

            # Gérer les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Ouvrage créé avec succès!',
                    'id': str(ouvrage.id)
                })

            messages.success(request, 'Ouvrage créé avec succès!')
            return redirect('organization:ouvrage_list')
        else:
            # Gérer les erreurs pour les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)

            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = OuvrageForm()

    return render(request, 'organization/ouvrage_form.html', {
        'form': form,
        'title': 'Nouvel Ouvrage'
    })


@employe_required
def ouvrage_detail_entry(request):
    ouvrages_accessibles = _get_ouvrage_detail_filter_queryset(request.user)

    selected_ouvrage_id = (
        request.GET.get('ouvrage')
        or request.session.get('organization_last_ouvrage_detail_id')
    )

    if selected_ouvrage_id:
        selected_ouvrage = ouvrages_accessibles.filter(pk=selected_ouvrage_id).first()
        if selected_ouvrage:
            request.session['organization_last_ouvrage_detail_id'] = str(selected_ouvrage.pk)
            return redirect('organization:ouvrage_detail', pk=selected_ouvrage.pk)

    fallback_ouvrage = ouvrages_accessibles.first()
    if fallback_ouvrage:
        request.session['organization_last_ouvrage_detail_id'] = str(fallback_ouvrage.pk)
        return redirect('organization:ouvrage_detail', pk=fallback_ouvrage.pk)

    messages.error(request, "Aucun ouvrage accessible n'est disponible pour cette fiche.")
    return redirect('organization:ouvrage_list')


@employe_required
def ouvrage_detail(request, pk):
    ouvrages = filter_queryset_by_permissions(
        Ouvrage.objects.filter(
            type_ouvrage__nom_type_ouvrage__iexact='AEPG'
        ).select_related('type_ouvrage', 'ouvrage_source'),
        request.user,
    ).order_by('nom_ouvrage')
    ouvrages_accessibles = _get_ouvrage_detail_filter_queryset(request.user)
    ouvrage = get_object_or_404(ouvrages, pk=pk)
    request.session['organization_last_ouvrage_detail_id'] = str(ouvrage.pk)
    bases = ouvrage.bases.all().order_by('nom_base')
    dossiers_techniques = list(ouvrage.dossiers_techniques.all())
    ouvrage_filtre = _get_organigramme_root_ouvrage(ouvrage)
    age_ouvrage = None
    if ouvrage.annee_realisation:
        age_ouvrage = max(timezone.now().year - ouvrage.annee_realisation, 0)
    return render(request, 'organization/ouvrage_detail.html', {
        'ouvrage': ouvrage,
        'bases': bases,
        'dossiers_techniques': dossiers_techniques,
        'ouvrages_accessibles': ouvrages_accessibles,
        'ouvrages_accessibles_grouped': _build_ouvrage_detail_grouped_options(ouvrages_accessibles),
        'ouvrage_filtre_selection_id': str(ouvrage_filtre.pk),
        'age_ouvrage': age_ouvrage,
        'title': f'Ouvrage {ouvrage.nom_ouvrage}'
    })


def ouvrage_update(request, pk):
    ouvrage = get_object_or_404(Ouvrage, pk=pk)
    if request.method == 'POST':
        form = OuvrageForm(request.POST, request.FILES, instance=ouvrage)
        if form.is_valid():
            form.save()
            _save_ouvrage_dossier_technique_files(
                ouvrage,
                request.FILES.getlist('dossier_technique_files'),
            )
            messages.success(request, 'Ouvrage modifié avec succès!')
            # Retour à la page d'origine (liste + filtres). La fiche détail n'existe que pour les
            # ouvrages AEPG : y rediriger un autre type donnerait un « Not found ».
            from django.utils.http import url_has_allowed_host_and_scheme
            next_url = request.POST.get('next') or ''
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            type_nom = (ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else '') or ''
            if type_nom.lower() == 'aepg':
                return redirect('organization:ouvrage_detail', pk=pk)
            return redirect('organization:ouvrage_list')
    else:
        form = OuvrageForm(instance=ouvrage)

    return render(request, 'organization/ouvrage_form.html', {
        'form': form,
        'ouvrage': ouvrage,
        'title': 'Modifier Ouvrage'
    })


@employe_required
@require_http_methods(["POST"])
def ouvrage_dossier_technique_upload(request, pk):
    ouvrage = get_object_or_404(Ouvrage, pk=pk)
    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    if not ouvrages_accessibles.filter(pk=ouvrage.pk).exists():
        messages.error(request, 'Acces refuse au dossier technique.')
        return redirect('organization:ouvrage_list')

    uploaded_files = request.FILES.getlist('dossier_technique_files')
    created_items = _save_ouvrage_dossier_technique_files(ouvrage, uploaded_files)
    if created_items:
        messages.success(request, f'{len(created_items)} fichier(s) ajoute(s) au dossier technique.')
    else:
        messages.error(request, 'Aucun fichier selectionne.')

    if request.POST.get('redirect_to') == 'detail':
        return redirect('organization:ouvrage_detail', pk=ouvrage.pk)
    return redirect('organization:ouvrage_list')


def _normaliser_nom_dossier(texte):
    """Minuscule, sans accents ni ponctuation : 'Ambato (AEPG)' ~ 'ambato aepg'."""
    import unicodedata
    texte = unicodedata.normalize('NFKD', texte or '')
    texte = ''.join(c for c in texte if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', texte).split())


_PREFIXE_COMMUNE = re.compile(r'^(?:cr|cu|commune(?:\s+rurale|\s+urbaine)?)\b\.?\s*', re.I)


def _est_dossier_commune(segment):
    """'CR. Mahambo', 'CR Mahambo', 'CU Toamasina' : le dossier d'une commune."""
    return bool(_PREFIXE_COMMUNE.match((segment or '').strip()))


def _jetons_dossier(texte):
    """Mots utiles d'un nom de dossier : sans année ni code, minuscule, sans accents."""
    return [t for t in _normaliser_nom_dossier(texte).split() if not any(c.isdigit() for c in t)]


def _sous_sequence(abrev, mot):
    """True si 'mhb' se retrouve dans l'ordre dans 'mahambo' (abréviation de commune)."""
    it = iter(mot)
    return len(abrev) >= 2 and abrev[0] == mot[0] and all(c in it for c in abrev)


def _ratio(a, b):
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def _score_ouvrage(jetons_dossier, jetons_ouvrage):
    """Similarité 0..1 entre le nom d'un dossier local et un nom d'ouvrage (fautes tolérées)."""
    f = [t for t in jetons_dossier if len(t) >= 4]
    o = [t for t in jetons_ouvrage if len(t) >= 4]
    if not f or not o:
        return 0.0
    f_vers_o = sum(max(_ratio(x, y) for y in o) for x in f) / len(f)
    o_vers_f = sum(max(_ratio(y, x) for x in f) for y in o) / len(o)
    return 0.8 * f_vers_o + 0.2 * o_vers_f


def _construire_resolveur(user):
    """Prépare le rapprochement dossiers locaux -> ouvrages ; renvoie resoudre(chemin)."""
    ouvrages = list(
        filter_queryset_by_permissions(Ouvrage.objects.all(), user).only('id', 'nom_ouvrage')
    )
    ids = [o.id for o in ouvrages]
    communes_par_ouvrage = {}
    paires = (
        PointEau.objects.filter(ouvrage_id__in=ids)
        .exclude(parcelle__village__fokontany__commune__nom_commune__isnull=True)
        .values_list('ouvrage_id', 'parcelle__village__fokontany__commune__nom_commune')
        .distinct()
    )
    for ouvrage_id, nom_commune in paires:
        communes_par_ouvrage.setdefault(ouvrage_id, set()).add(nom_commune)

    # Bases (dossier racine choisi) -> ouvrages gérés par les employés de la base
    ouvrages_par_base = {}
    for base_id, nom_base in Base.objects.values_list('id', 'nom_base'):
        ouvrages_par_base[_normaliser_nom_dossier(nom_base)] = (nom_base, base_id)
    ids_par_base = {}
    for ouvrage_id, base_id in (
        ModaliteGestion.objects.filter(date_fin__isnull=True, employe__base__isnull=False, ouvrage_id__in=ids)
        .values_list('ouvrage_id', 'employe__base_id').distinct()
    ):
        ids_par_base.setdefault(base_id, set()).add(ouvrage_id)

    def trouver_base(segments):
        for seg in segments[:2]:
            nom = _normaliser_nom_dossier(seg)
            if not nom or _est_dossier_commune(seg):
                continue
            meilleur = max(ouvrages_par_base, key=lambda b: _ratio(nom, b), default=None)
            if meilleur and _ratio(nom, meilleur) >= 0.85:
                return ouvrages_par_base[meilleur][1]
        return None

    info = {}  # ouvrage -> (jetons du nom, communes brutes, communes normalisées)
    toutes_communes = {}
    for o in ouvrages:
        brutes = communes_par_ouvrage.get(o.id, set())
        normalisees = {_normaliser_nom_dossier(c) for c in brutes}
        for c in brutes:
            toutes_communes[_normaliser_nom_dossier(c)] = c
        info[o.id] = (_jetons_dossier(o.nom_ouvrage), brutes, normalisees)

    def trouver_commune(segment):
        nom = _normaliser_nom_dossier(_PREFIXE_COMMUNE.sub('', segment.strip(), count=1))
        if not nom:
            return None
        meilleur = max(toutes_communes, key=lambda c: _ratio(nom, c), default=None)
        return meilleur if meilleur and _ratio(nom, meilleur) >= 0.85 else None

    cache = {}

    def classer(segment, commune_norm, base_id=None):
        cle = (segment, commune_norm, base_id)
        if cle in cache:
            return cache[cle]
        jetons = _jetons_dossier(segment)
        if commune_norm:
            # Le nom de la commune (ou son abréviation : MHB) n'identifie pas l'ouvrage.
            nom_c = commune_norm.split()[0] if commune_norm else ''
            # (si l'ouvrage porte le nom de la commune, on garde le mot : il est alors le seul indice)
            gardes = [t for t in jetons if _ratio(t, nom_c) < 0.85 and not _sous_sequence(t, nom_c)]
            jetons = gardes if any(len(t) >= 4 for t in gardes) else jetons
        pool = [o for o in ouvrages if commune_norm in info[o.id][2]] if commune_norm else ouvrages
        if commune_norm and not pool:
            pool = ouvrages
        if base_id:
            # La base (dossier racine) réduit les homonymes ; sans résultat, on retombe sur tous les ouvrages.
            pool_base = [o for o in pool if o.id in ids_par_base.get(base_id, ())]
            if pool_base:
                pool = pool_base
        notes = []
        for o in pool:
            jetons_o = info[o.id][0]
            if commune_norm:
                nom_c = commune_norm.split()[0]
                gardes_o = [t for t in jetons_o if _ratio(t, nom_c) < 0.85]
                jetons_o = gardes_o if any(len(t) >= 4 for t in gardes_o) else jetons_o
            notes.append((_score_ouvrage(jetons, jetons_o), o))
        notes.sort(key=lambda x: -x[0])
        cache[cle] = notes[:3]
        return cache[cle]

    def resoudre(chemin):
        segments = [s for s in str(chemin).replace('\\', '/').split('/') if s]
        idx_commune = next((i for i, s in enumerate(segments) if _est_dossier_commune(s)), None)
        commune_norm = trouver_commune(segments[idx_commune]) if idx_commune is not None else None
        base_id = trouver_base(segments)
        # Après un dossier « CR. », le dossier suivant est l'ouvrage ; sinon on teste tous les niveaux.
        if idx_commune is not None:
            segs = segments[idx_commune + 1:idx_commune + 2]
        else:
            # Sans dossier « CR. », on ignore le dossier de la base (premier niveau) pour ne pas le prendre pour un ouvrage
            segs = segments[1:] if (base_id and len(segments) > 1) else segments
        meilleurs = []
        idx_ouvrage = None
        debut_segs = idx_commune + 1 if idx_commune is not None else (1 if (base_id and len(segments) > 1) else 0)
        for decalage, s in enumerate(segs):
            top = classer(s, commune_norm, base_id)
            if base_id and (not top or top[0][0] < 0.6):
                top = classer(s, commune_norm)  # l'ouvrage peut dépendre d'une autre base
            if top and (not meilleurs or top[0][0] > meilleurs[0][0]):
                meilleurs = top
                idx_ouvrage = debut_segs + decalage
        score = meilleurs[0][0] if meilleurs else 0
        ecart = score - meilleurs[1][0] if len(meilleurs) > 1 else 1
        statut = 'ok' if score >= 0.85 and ecart >= 0.04 else ('probable' if score >= 0.6 else 'introuvable')
        # Association automatique : sûre, ou assez proche et nettement devant le suivant (la base et la commune ont réduit le choix)
        auto = statut == 'ok' or (score >= 0.7 and ecart >= 0.1)
        resultat = {
            'dossier': chemin,
            'statut': statut,
            'auto': auto,
            'commune': toutes_communes.get(commune_norm) if commune_norm else None,
            'candidats': [
                {'id': str(o.id), 'nom': o.nom_ouvrage,
                 'commune': ', '.join(sorted(info[o.id][1])), 'score': round(sc, 2)}
                for sc, o in meilleurs if sc >= 0.5
            ],
        }
        return resultat, segments, idx_ouvrage, meilleurs

    return resoudre


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_dossiers_techniques_analyser(request):
    """Associe des dossiers locaux (Base/CR. Commune/2018_Ouvrage_ABR/...) aux ouvrages d'Hydria.

    Reçoit {"dossiers": ["Base/CR. Commune/Ouvrage", ...]} et renvoie, pour chacun,
    le statut ('ok' >= 0.85, 'probable', 'introuvable') et les 3 meilleurs ouvrages candidats.
    Le dossier de commune (préfixe CR) restreint la recherche aux ouvrages de cette commune.
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    resoudre = _construire_resolveur(request.user)
    resultats = [resoudre(chemin)[0] for chemin in payload.get('dossiers', [])[:5000]]
    return JsonResponse({'success': True, 'resultats': resultats})


def _nombres_dossier(texte):
    return {int(n) for n in re.findall(r'\d+', texte or '')}


def _cibles_photos(ouvrage_id, nom_ouvrage, nom_dossier):
    """Équipements et points d'eau d'un ouvrage, classés selon leur ressemblance avec un nom de dossier.

    - équipement : ressemblance du nom (fautes tolérées) ; un numéro différent (Citerne 1 / Citerne 2) pénalise.
    - point d'eau : le numéro du dossier correspond à l'IDXLS (ex. « PE 12 », « 12 Rakoto »).
    """
    mots_ouvrage = set(_jetons_dossier(nom_ouvrage))

    def sans_nom_ouvrage(jetons):
        # Le nom de l'ouvrage figure souvent dans le dossier et dans le nom de l'équipement : il n'aide pas à choisir.
        gardes = [t for t in jetons if t not in mots_ouvrage and not any(_ratio(t, m) >= 0.85 for m in mots_ouvrage)]
        return gardes if any(len(t) >= 4 for t in gardes) else jetons

    jetons = sans_nom_ouvrage(_jetons_dossier(nom_dossier))
    nombres = _nombres_dossier(nom_dossier)
    candidats = []
    meilleur_nom_equipement = 0.0

    for eq in EquipementConstitutif.objects.filter(ouvrage_id=ouvrage_id).only('id', 'nom'):
        base = _score_ouvrage(jetons, sans_nom_ouvrage(_jetons_dossier(eq.nom)))
        meilleur_nom_equipement = max(meilleur_nom_equipement, base)
        nombres_eq = _nombres_dossier(eq.nom)
        score = base
        if base and nombres and nombres_eq:
            score += 0.1 if nombres == nombres_eq else -0.3
        candidats.append({'type': 'equipement', 'id': str(eq.id), 'nom': eq.nom, 'score': max(0.0, min(1.0, score))})

    # Un nom d'équipement qui ressemble beaucoup au dossier prime sur une coïncidence de numéro.
    score_numero = 0.9 if meilleur_nom_equipement < 0.8 else 0.6
    for pe in PointEau.objects.filter(ouvrage_id=ouvrage_id).only('id', 'nomabonne', 'idxls'):
        if nombres and nombres & _nombres_dossier(pe.idxls):
            score = score_numero
        else:
            score = 0.8 * _score_ouvrage(jetons, _jetons_dossier(pe.nomabonne))
        libelle = f"IDXLS {pe.idxls or '?'} — {pe.nomabonne}"
        candidats.append({'type': 'pointeau', 'id': str(pe.id), 'nom': libelle, 'score': score})

    candidats = [c for c in candidats if c['score'] >= 0.4]
    candidats.sort(key=lambda c: -c['score'])
    for c in candidats:
        c['score'] = round(c['score'], 2)
    return candidats[:6]


def _catalogue_cibles_photos(ouvrage_id):
    """TOUS les équipements et points d'eau d'un ouvrage (choix manuel quand le rapprochement échoue)."""
    equipements = [
        {'type': 'equipement', 'id': str(e.id), 'nom': e.nom}
        for e in EquipementConstitutif.objects.filter(ouvrage_id=ouvrage_id).only('id', 'nom').order_by('nom')
    ]
    points = list(PointEau.objects.filter(ouvrage_id=ouvrage_id).only('id', 'nomabonne', 'idxls'))

    def cle_idxls(pe):
        nombres = sorted(_nombres_dossier(pe.idxls))
        return (nombres[0] if nombres else 10 ** 9, pe.idxls or '')

    points.sort(key=cle_idxls)
    return equipements + [
        {'type': 'pointeau', 'id': str(pe.id), 'nom': f"IDXLS {pe.idxls or '?'} — {pe.nomabonne}"}
        for pe in points
    ]


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_photos_lot_analyser(request):
    """Associe des dossiers de photos (Base/CR. Commune/Ouvrage/Équipement ou IDXLS/...) à leurs cibles.

    Reçoit {"dossiers": [...]} ; renvoie, pour chaque dossier, les ouvrages candidats et, pour chacun,
    les équipements / points d'eau candidats (dossier situé juste après celui de l'ouvrage).
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    resoudre = _construire_resolveur(request.user)
    cache_cibles = {}
    resultats = []
    for chemin in payload.get('dossiers', [])[:5000]:
        resultat, segments, idx_ouvrage, _meilleurs = resoudre(chemin)
        nom_cible = segments[idx_ouvrage + 1] if idx_ouvrage is not None and idx_ouvrage + 1 < len(segments) else None
        resultat['cible_dossier'] = nom_cible
        for cand in resultat['candidats']:
            cle = (cand['id'], nom_cible)
            if cle not in cache_cibles:
                cache_cibles[cle] = _cibles_photos(cand['id'], cand['nom'], nom_cible) if nom_cible else []
            cand['cibles'] = cache_cibles[cle]
        # Cible automatique : même règle de sûreté que pour les ouvrages
        resultat['cible_auto'] = None
        if resultat['auto'] and resultat['candidats']:
            cibles = resultat['candidats'][0]['cibles']
            if cibles:
                score = cibles[0]['score']
                ecart = score - cibles[1]['score'] if len(cibles) > 1 else 1
                if (score >= 0.85 and ecart >= 0.04) or (score >= 0.7 and ecart >= 0.1):
                    resultat['cible_auto'] = {'type': cibles[0]['type'], 'id': cibles[0]['id']}
        resultats.append(resultat)

    # Liste complète des cibles de chaque ouvrage candidat, pour le choix manuel
    catalogue = {}
    for resultat in resultats:
        for cand in resultat['candidats']:
            if cand['id'] not in catalogue:
                catalogue[cand['id']] = _catalogue_cibles_photos(cand['id'])
    return JsonResponse({'success': True, 'resultats': resultats, 'catalogue': catalogue})


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_photo_lot_import(request):
    """Ajoute UNE photo à un équipement ou à un point d'eau (import en lot, JSON).

    Champs : cible_type ('equipement' | 'pointeau'), cible_id, fichier, taille_origine (octets du fichier d'origine).
    Une photo de même nom et de même taille d'origine déjà présente est ignorée.
    """
    import os
    import uuid
    from django.core.files.storage import default_storage

    cible_type = request.POST.get('cible_type')
    modele = {'equipement': EquipementConstitutif, 'pointeau': PointEau}.get(cible_type)
    fichier = request.FILES.get('fichier')
    if not modele or not fichier:
        return JsonResponse({'success': False, 'error': 'Cible ou fichier manquant'}, status=400)
    extension = os.path.splitext(fichier.name or '')[1].lower()
    est_image = (fichier.content_type or '').startswith('image/') or extension in {
        '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic', '.heif'}
    if not est_image:
        return JsonResponse({'success': False, 'error': "Ce n'est pas une image"}, status=400)
    if fichier.size > 10 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'Image trop lourde (10 Mo max)'}, status=413)

    try:
        with transaction.atomic():
            cible = modele.objects.select_for_update().get(pk=request.POST.get('cible_id'))
            accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
            if not accessibles.filter(pk=cible.ouvrage_id).exists():
                return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

            photos = list(cible.photos or [])
            taille_origine = request.POST.get('taille_origine') or str(fichier.size)
            if any(p.get('original_name') == fichier.name and str(p.get('original_size')) == taille_origine
                   for p in photos if isinstance(p, dict)):
                return JsonResponse({'success': True, 'ignore': True})

            dossier = 'equipements' if cible_type == 'equipement' else 'points_eau'
            nom_fichier = f"{uuid.uuid4()}{os.path.splitext(fichier.name)[1]}"
            employe = getattr(request.user, 'employe', None)

            # `updated_by` n'a pas le même type selon le modèle : Employe pour un point d'eau, User pour un équipement.
            # On prépare l'auteur AVANT d'écrire le fichier, pour ne jamais laisser de fichier orphelin.
            champs = ['photos']
            auteur = None
            if any(f.name == 'updated_by' for f in modele._meta.fields):
                type_auteur = modele._meta.get_field('updated_by').related_model
                auteur = employe if isinstance(employe, type_auteur) else (
                    request.user if isinstance(request.user, type_auteur) else None)
                if auteur is not None:
                    champs.append('updated_by')

            chemin = default_storage.save(os.path.join('photos', dossier, str(cible.pk), nom_fichier), fichier)
            photos.append({
                'url': default_storage.url(chemin),
                'filename': nom_fichier,
                'size': fichier.size,
                'uploaded_at': str(uuid.uuid1().time),
                'original_name': fichier.name,
                'original_size': taille_origine,
                'source': 'import_lot',
                'uploaded_by': (employe.surnom if employe and employe.surnom else request.user.get_username()),
            })
            cible.photos = photos
            if auteur is not None:
                cible.updated_by = auteur
            try:
                cible.save(update_fields=champs)  # déclenche le journal des contributions
            except Exception:
                default_storage.delete(chemin)   # pas de fichier orphelin si l'enregistrement échoue
                raise
    except modele.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Cible introuvable'}, status=404)
    return JsonResponse({'success': True, 'ignore': False, 'total_photos': len(photos)})


@employe_required
@require_http_methods(["POST"])
def api_ouvrage_dossier_technique_import_fichier(request, pk):
    """Ajoute UN fichier au dossier technique d'un ouvrage (import par dossier, JSON).

    Ignore le fichier si un fichier de même nom existe déjà pour cet ouvrage.
    """
    ouvrage = get_object_or_404(Ouvrage, pk=pk)
    if not filter_queryset_by_permissions(Ouvrage.objects.all(), request.user).filter(pk=ouvrage.pk).exists():
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

    fichier = request.FILES.get('fichier')
    if not fichier:
        return JsonResponse({'success': False, 'error': 'Aucun fichier'}, status=400)

    nom = fichier.name
    if OuvrageDossierTechnique.objects.filter(ouvrage=ouvrage, nom_affichage=nom).exists():
        return JsonResponse({'success': True, 'ignore': True, 'raison': 'déjà présent'})

    _save_ouvrage_dossier_technique_files(ouvrage, [fichier])
    return JsonResponse({'success': True, 'ignore': False})


@login_required
@require_http_methods(["GET"])
@xframe_options_sameorigin
def ouvrage_dossier_technique_preview(request, dossier_id):
    """Affiche un fichier du dossier technique sans forcer son téléchargement."""
    import csv
    import io
    import mimetypes
    import os
    import zipfile
    import xml.etree.ElementTree as ET
    from django.http import FileResponse, Http404

    dossier = get_object_or_404(
        OuvrageDossierTechnique.objects.select_related('ouvrage'),
        pk=dossier_id,
    )
    client_ouvrage_id = None
    try:
        client_ouvrage_id = request.user.client.ouvrage_id
    except Exception:
        pass
    has_employee_access = filter_queryset_by_permissions(
        Ouvrage.objects.all(), request.user
    ).filter(pk=dossier.ouvrage_id).exists()
    if not has_employee_access and client_ouvrage_id != dossier.ouvrage_id:
        raise Http404("Fichier introuvable ou accès refusé.")

    if not dossier.fichier:
        raise Http404('Fichier absent.')

    filename = dossier.display_name or os.path.basename(dossier.fichier.name)
    extension = os.path.splitext(filename)[1].lower()

    if extension in {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}:
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        response = FileResponse(
            dossier.fichier.open('rb'),
            as_attachment=False,
            filename=os.path.basename(filename),
            content_type=content_type,
        )
        return response

    preview_context = {
        'dossier': dossier,
        'filename': filename,
        'preview_type': extension.lstrip('.').upper(),
        'paragraphs': [],
        'table_rows': [],
        'truncated': False,
    }

    try:
        if extension == '.docx':
            with dossier.fichier.open('rb') as source, zipfile.ZipFile(source) as archive:
                document_xml = archive.read('word/document.xml')
            root = ET.fromstring(document_xml)
            namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for paragraph in root.findall('.//w:p', namespace):
                text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace)).strip()
                if text:
                    paragraphs.append(text)
                if len(paragraphs) >= 500:
                    preview_context['truncated'] = True
                    break
            preview_context['paragraphs'] = paragraphs

        elif extension == '.xlsx':
            from openpyxl import load_workbook
            with dossier.fichier.open('rb') as source:
                workbook = load_workbook(source, read_only=True, data_only=True)
                sheet = workbook.active
                rows = []
                for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    rows.append(['' if value is None else str(value) for value in row[:30]])
                    if row_index >= 200:
                        preview_context['truncated'] = True
                        break
                preview_context['table_rows'] = rows
                preview_context['sheet_name'] = sheet.title
                workbook.close()

        elif extension in {'.csv', '.txt'}:
            with dossier.fichier.open('rb') as source:
                raw = source.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raw = raw[:1024 * 1024]
                preview_context['truncated'] = True
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode('cp1252', errors='replace')
            if extension == '.csv':
                preview_context['table_rows'] = [row[:30] for row in list(csv.reader(io.StringIO(text)))[:500]]
            else:
                lines = text.splitlines()
                preview_context['paragraphs'] = lines[:2000]
                preview_context['truncated'] = preview_context['truncated'] or len(lines) > 2000
        else:
            raise Http404("Ce format ne dispose pas d'un aperçu intégré.")
    except Http404:
        raise
    except Exception as exc:
        preview_context['preview_error'] = f'Impossible de générer l’aperçu : {exc}'

    return render(request, 'organization/dossier_technique_preview.html', preview_context)


@employe_required
@require_http_methods(["POST"])
def ouvrage_dossier_technique_delete(request, dossier_id):
    dossier = get_object_or_404(
        OuvrageDossierTechnique.objects.select_related('ouvrage'),
        pk=dossier_id,
    )
    ouvrage = dossier.ouvrage
    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    if not ouvrages_accessibles.filter(pk=ouvrage.pk).exists():
        messages.error(request, 'Acces refuse au dossier technique.')
        return redirect('organization:ouvrage_list')

    if dossier.fichier:
        dossier.fichier.delete(save=False)
    dossier.delete()
    messages.success(request, 'Fichier du dossier technique supprime.')

    if request.POST.get('redirect_to') == 'detail':
        return redirect('organization:ouvrage_detail', pk=ouvrage.pk)
    return redirect('organization:ouvrage_list')


def ouvrage_delete(request, pk):
    ouvrage = get_object_or_404(Ouvrage, pk=pk)
    if request.method == 'POST':
        ouvrage.delete()
        messages.success(request, 'Ouvrage supprimé avec succès!')
        return redirect('organization:ouvrage_list')
    return render(request, 'organization/ouvrage_confirm_delete.html', {
        'ouvrage': ouvrage,
        'title': 'Supprimer Ouvrage'
    })


# ==========================================
# VUES CRUD POUR LES DONNÉES LIÉES AUX OUVRAGES
# ==========================================

@xframe_options_sameorigin
@employe_required
def points_eau_list(request, ouvrage_id=None):
    """Liste des points d'eau avec sélection d'ouvrage - Filtrée selon permissions"""
    from apps.billing.models import PointEau, TypePointEau

    # Récupérer les ouvrages accessibles selon les permissions
    ouvrages_org = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user).order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage_org = None

    if ouvrage_id:
        # Vérifier que l'ouvrage est accessible
        selected_ouvrage_org = get_object_or_404(ouvrages_org, pk=ouvrage_id)
    elif ouvrages_org.exists():
        selected_ouvrage_org = ouvrages_org.first()

    # Récupérer les points d'eau accessibles
    from django.db.models import Case, When, Value, IntegerField
    from django.db.models.functions import Cast
    point_eau_select_related = (
        'compteur_tete',
        'type_point_eau',
        'ouvrage',
        'parcelle__village__fokontany__commune',
    )

    from apps.billing.points_eau_statut import compter_statuts, q_abandonne, q_actif, statut_expression
    # Actifs d'abord, puis coupés, abandonnés, puis sans date de branchement (mis à part)
    statut_rang = Case(
        When(datebranchement__isnull=True, then=Value(3)),
        When(q_abandonne(), then=Value(2)),
        When(datearretbranchement__isnull=False, then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )

    if selected_ouvrage_org:
        points_eau = PointEau.objects.filter(ouvrage=selected_ouvrage_org).select_related(
            *point_eau_select_related
        ).annotate(
            idxls_numeric=Case(
                When(idxls='', then=Value(999999)),
                When(idxls__isnull=True, then=Value(999999)),
                default=Cast('idxls', IntegerField())
            ),
            statut_branchement=statut_expression(),
            statut_rang=statut_rang,
        ).order_by('statut_rang', 'idxls_numeric', 'nomabonne')
    else:
        # Afficher les points d'eau des ouvrages accessibles
        points_eau = filter_queryset_by_permissions(
            PointEau.objects.all(), request.user
        ).select_related(*point_eau_select_related).annotate(
            idxls_numeric=Case(
                When(idxls='', then=Value(999999)),
                When(idxls__isnull=True, then=Value(999999)),
                default=Cast('idxls', IntegerField())
            ),
            statut_branchement=statut_expression(),
            statut_rang=statut_rang,
        ).order_by('statut_rang', 'idxls_numeric', 'nomabonne')

    for point in points_eau:
        point.photo_urls = _extract_photo_urls(getattr(point, 'photos', None))
        point.photo_preview_url = point.photo_urls[0] if point.photo_urls else ''
        point.photos_count = len(point.photo_urls)

        parcelle = point.parcelle
        if not parcelle:
            point.parcelle_display = 'Non renseignee'
            continue

        village = ''
        commune = ''

        if parcelle.village:
            village = parcelle.village.nom_village or ''
            if parcelle.village.fokontany and parcelle.village.fokontany.commune:
                commune = parcelle.village.fokontany.commune.nom_commune or ''

        location_parts = [part for part in [village, commune] if part]
        location_suffix = f" ({', '.join(location_parts)})" if location_parts else ''
        point.parcelle_display = f"{parcelle.reference_parcelle or 'Non renseignee'}{location_suffix}"

    organigramme_candidates = _get_organigramme_candidates(selected_ouvrage_org)

    # Types de points d'eau pour les formulaires
    types_points_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')

    # Compteurs disponibles pour l'ouvrage sélectionné
    compteurs_disponibles = organigramme_candidates['compteurs']

    # Parcelles disponibles
    from apps.geography.models import Parcelle
    parcelles_disponibles = Parcelle.objects.all().select_related(
        'village__fokontany__commune__district__region'
    ).order_by('village__nom_village', 'reference_parcelle')

    # Calcul des statistiques par type de point d'eau
    from django.db.models import Count
    # Seuls les points actifs comptent comme points d'eau existants ;
    # coupés et sans date de branchement sont comptés à part.
    stats_par_type = {}
    stats_par_type_abonne = {}
    statuts_counts = compter_statuts(points_eau)
    points_eau_actifs_qs = points_eau.filter(q_actif())
    if statuts_counts['actifs']:
        stats_types = points_eau_actifs_qs.order_by().values('type_point_eau__nom_type').annotate(
            count=Count('id')
        ).order_by('-count')

        for stat in stats_types:
            type_nom = stat['type_point_eau__nom_type'] or 'Non défini'
            stats_par_type[type_nom] = stat['count']

        # Détail par type d'abonné (particulier / boutique) pour les kiosques uniquement
        libelles_abonne = {'particulier': 'Particuliers', 'boutique': 'Boutiques'}
        for stat in points_eau_actifs_qs.filter(
            type_point_eau__nom_type__iexact='kiosque'
        ).order_by().values('type_point_eau__nom_type', 'typeabonne').annotate(count=Count('id')):
            type_nom = stat['type_point_eau__nom_type'] or 'Non défini'
            abonne = (stat['typeabonne'] or '').strip().lower()
            stats_par_type_abonne.setdefault(type_nom, []).append({
                'libelle': libelles_abonne.get(abonne, 'Non renseigné'),
                'count': stat['count'],
                'rang': 0 if abonne == 'particulier' else (1 if abonne == 'boutique' else 2),
            })
        for sous in stats_par_type_abonne.values():
            sous.sort(key=lambda s: s['rang'])

        # Branchements institutionnels (BP, BF, PMH) : sous-ligne « Inst. » par type
        for stat in points_eau_actifs_qs.filter(
            estbranchementinstitutionnel=True
        ).order_by().values('type_point_eau__nom_type').annotate(count=Count('id')):
            type_nom = stat['type_point_eau__nom_type'] or 'Non défini'
            stats_par_type_abonne.setdefault(type_nom, []).append({
                'libelle': 'Inst.',
                'count': stat['count'],
                'rang': 3,
            })

        points_avec_compteur = points_eau_actifs_qs.filter(compteur_tete__isnull=False).count()
    else:
        points_avec_compteur = 0

    poste_nom = get_user_poste_name(request.user)
    is_directeur = request.user.is_superuser or poste_nom == 'Directeur'
    ouvrage_map_data = _ouvrage_entity_map_data(selected_ouvrage_org, points_eau, 'point_eau')

    # Liste prête pour la tuile « Types » : chaque type avec son éventuel détail par type d'abonné
    stats_types_detail = [
        {'nom': type_nom, 'count': count, 'sous': stats_par_type_abonne.get(type_nom, [])}
        for type_nom, count in stats_par_type.items()
    ]

    return render(request, 'organization/points_eau_list.html', {
        'stats_types_detail': stats_types_detail,
        'points_eau': points_eau,
        'ouvrages': ouvrages_org,
        'selected_ouvrage': selected_ouvrage_org,
        'types_points_eau': types_points_eau,
        'compteurs_disponibles': compteurs_disponibles,
        'organigramme_equipements': organigramme_candidates['equipements'],
        'organigramme_compteurs': organigramme_candidates['compteurs'],
        'parcelles_disponibles': parcelles_disponibles,
        'stats_par_type': stats_par_type,
        'points_avec_compteur': points_avec_compteur,
        'points_eau_actifs_count': statuts_counts['actifs'],
        'points_eau_coupes_count': statuts_counts['coupes'],
        'points_eau_abandonnes_count': statuts_counts['abandonnes'],
        'points_eau_sans_date_count': statuts_counts['sans_date'],
        'is_directeur': is_directeur,
        'ouvrage_map_data': ouvrage_map_data,
        'title': 'Gestion des Points d\'eau'
    })


def points_eau_create(request, ouvrage_id):
    """Créer un nouveau point d'eau"""
    from apps.billing.models import PointEau, TypePointEau, CompteurTete
    from django.http import JsonResponse

    ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire - Informations de base
            code_point_eau = request.POST.get('code_point_eau', '').strip()
            nomabonne = request.POST.get('nomabonne')
            numeroteleph = request.POST.get('numeroteleph', '')
            contactabonne = request.POST.get('contactabonne', '')
            typeabonne = request.POST.get('typeabonne', '')
            type_point_eau_id = request.POST.get('type_point_eau')
            amont_node_value = request.POST.get('amont_node', '').strip()
            parcelle_id = request.POST.get('parcelle')
            datebranchement_str = request.POST.get('datebranchement')
            datearretbranchement_str = request.POST.get('datearretbranchement')
            tarifforfaitaire = request.POST.get('tarifforfaitaire')
            estbranchementinstitutionnel = request.POST.get('estbranchementinstitutionnel') == 'on'

            legacy_compteur_id = request.POST.get('compteur_tete')
            if not amont_node_value and legacy_compteur_id:
                amont_node_value = f'compteur:{legacy_compteur_id}'

            amont_type, amont_node = _resolve_organigram_node(
                ouvrage,
                amont_node_value,
                allow_point=True,
            ) if amont_node_value else (None, None)
            compteur_tete_id = str(amont_node.pk) if amont_type == 'compteur' else None

            # Convertir les dates de branchement en datetime
            from django.utils.dateparse import parse_date
            datebranchement = None
            datearretbranchement = None
            if datebranchement_str:
                date_obj = parse_date(datebranchement_str)
                if date_obj:
                    datebranchement = datetime.combine(date_obj, datetime.min.time())
            if datearretbranchement_str:
                date_obj = parse_date(datearretbranchement_str)
                if date_obj:
                    datearretbranchement = datetime.combine(date_obj, datetime.min.time())

            # Champs consommateurs
            nombre_consommateurs = request.POST.get('nombre_consommateurs')
            nombre_menages_consommateurs = request.POST.get('nombre_menages_consommateurs')
            idxls = request.POST.get('idxls', '')

            # Champs DiameX et paiements
            numerodiamexdemande = request.POST.get('numerodiamexdemande')
            numerodiamexdevis = request.POST.get('numerodiamexdevis')
            basediamexdemande = request.POST.get('basediamexdemande')
            basediamexdevis = request.POST.get('basediamexdevis')
            datepaiementdemande_str = request.POST.get('datepaiementdemande')
            datepaiementdevis_str = request.POST.get('datepaiementdevis')
            montantdemandepaye = request.POST.get('montantdemandepaye')
            montantdevispaye = request.POST.get('montantdevispaye')

            # Convertir les dates de paiement en datetime
            from django.utils.dateparse import parse_date
            datepaiementdemande = None
            datepaiementdevis = None
            if datepaiementdemande_str:
                date_obj = parse_date(datepaiementdemande_str)
                if date_obj:
                    datepaiementdemande = datetime.combine(date_obj, datetime.min.time())
            if datepaiementdevis_str:
                date_obj = parse_date(datepaiementdevis_str)
                if date_obj:
                    datepaiementdevis = datetime.combine(date_obj, datetime.min.time())

            # Coordonnées GPS
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')

            # Photos (JSON)
            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                photos = json.loads(photos_json) if photos_json else []
            except json.JSONDecodeError:
                photos = []

            # Besoin en clôture
            besoin_en_cloture = request.POST.get('besoin_en_cloture') == 'on'

            # Créer le point d'eau avec tous les champs
            point = PointEau.objects.create(
                code_point_eau=code_point_eau or None,
                nomabonne=nomabonne,
                numeroteleph=numeroteleph,
                contactabonne=contactabonne,
                typeabonne=typeabonne,
                ouvrage=ouvrage,
                type_point_eau_id=type_point_eau_id if type_point_eau_id else None,
                compteur_tete_id=compteur_tete_id if compteur_tete_id else None,
                parcelle_id=parcelle_id if parcelle_id else None,
                datebranchement=datebranchement,
                datearretbranchement=datearretbranchement,
                **champs_tarif_depuis_post(request.POST),
                estbranchementinstitutionnel=estbranchementinstitutionnel,
                # Champs consommateurs
                nombre_consommateurs=int(nombre_consommateurs) if nombre_consommateurs else None,
                nombre_menages_consommateurs=int(nombre_menages_consommateurs) if nombre_menages_consommateurs else None,
                idxls=idxls,
                # Champs DiameX et paiements
                numerodiamexdemande=int(numerodiamexdemande) if numerodiamexdemande else None,
                numerodiamexdevis=int(numerodiamexdevis) if numerodiamexdevis else None,
                basediamexdemande=basediamexdemande if basediamexdemande else None,
                basediamexdevis=basediamexdevis if basediamexdevis else None,
                datepaiementdemande=datepaiementdemande,
                datepaiementdevis=datepaiementdevis,
                montantdemandepaye=float(montantdemandepaye) if montantdemandepaye else None,
                montantdevispaye=float(montantdevispaye) if montantdevispaye else None,
                # Coordonnées GPS
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                # Photos
                photos=photos,
                # Besoin en clôture
                besoin_en_cloture=besoin_en_cloture,
            )

            return JsonResponse({
                'success': True,
                'message': f'Point d\'eau "{nomabonne}" créé avec succès',
                'redirect': f'/organisations/points-eau/{ouvrage_id}/'
            })

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Erreur lors de la création du point d'eau : {error_details}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def points_eau_edit(request, point_id):
    """Modifier un point d'eau"""
    from apps.billing.models import PointEau, TypePointEau, CompteurTete
    from django.http import JsonResponse

    point = get_object_or_404(PointEau, pk=point_id)

    if request.method == 'POST':
        try:
            # Mettre à jour les informations de base
            code_point_eau = request.POST.get('code_point_eau', '').strip()
            point.code_point_eau = code_point_eau or None
            point.nomabonne = request.POST.get('nomabonne')
            point.numeroteleph = request.POST.get('numeroteleph', '')
            point.contactabonne = request.POST.get('contactabonne', '')
            point.typeabonne = request.POST.get('typeabonne', '')

            type_point_eau_id = request.POST.get('type_point_eau')
            point.type_point_eau_id = type_point_eau_id if type_point_eau_id else None

            compteur_tete_id = request.POST.get('compteur_tete')
            point.compteur_tete_id = compteur_tete_id if compteur_tete_id else None

            parcelle_id = request.POST.get('parcelle')
            point.parcelle_id = parcelle_id if parcelle_id else None

            # Convertir les dates de branchement
            from django.utils.dateparse import parse_date
            datebranchement_str = request.POST.get('datebranchement')
            if datebranchement_str:
                date_obj = parse_date(datebranchement_str)
                point.datebranchement = datetime.combine(date_obj, datetime.min.time()) if date_obj else None
            else:
                point.datebranchement = None

            # datearretbranchement n'est PAS modifiable ici : le champ du modal est
            # disabled (donc absent du POST) et la date est gérée par le workflow
            # de coupure / remise en eau. Ne pas l'écraser.

            tarifforfaitaire = request.POST.get('tarifforfaitaire')
            for _champ, _valeur in champs_tarif_depuis_post(request.POST).items():
                setattr(point, _champ, _valeur)

            point.estbranchementinstitutionnel = request.POST.get('estbranchementinstitutionnel') == 'on'

            # Champs consommateurs
            nombre_consommateurs = request.POST.get('nombre_consommateurs')
            point.nombre_consommateurs = int(nombre_consommateurs) if nombre_consommateurs else None

            nombre_menages_consommateurs = request.POST.get('nombre_menages_consommateurs')
            point.nombre_menages_consommateurs = int(nombre_menages_consommateurs) if nombre_menages_consommateurs else None

            point.idxls = request.POST.get('idxls', '')

            # Champs DiameX et paiements
            numerodiamexdemande = request.POST.get('numerodiamexdemande')
            point.numerodiamexdemande = int(numerodiamexdemande) if numerodiamexdemande else None

            numerodiamexdevis = request.POST.get('numerodiamexdevis')
            point.numerodiamexdevis = int(numerodiamexdevis) if numerodiamexdevis else None

            basediamexdemande = request.POST.get('basediamexdemande')
            point.basediamexdemande = basediamexdemande if basediamexdemande else None

            basediamexdevis = request.POST.get('basediamexdevis')
            point.basediamexdevis = basediamexdevis if basediamexdevis else None

            # Convertir les dates de paiement
            datepaiementdemande_str = request.POST.get('datepaiementdemande')
            if datepaiementdemande_str:
                date_obj = parse_date(datepaiementdemande_str)
                point.datepaiementdemande = datetime.combine(date_obj, datetime.min.time()) if date_obj else None
            else:
                point.datepaiementdemande = None

            datepaiementdevis_str = request.POST.get('datepaiementdevis')
            if datepaiementdevis_str:
                date_obj = parse_date(datepaiementdevis_str)
                point.datepaiementdevis = datetime.combine(date_obj, datetime.min.time()) if date_obj else None
            else:
                point.datepaiementdevis = None

            montantdemandepaye = request.POST.get('montantdemandepaye')
            point.montantdemandepaye = float(montantdemandepaye) if montantdemandepaye else None

            montantdevispaye = request.POST.get('montantdevispaye')
            point.montantdevispaye = float(montantdevispaye) if montantdevispaye else None

            # Coordonnées GPS
            latitude = request.POST.get('latitude')
            point.latitude = float(latitude) if latitude else None

            longitude = request.POST.get('longitude')
            point.longitude = float(longitude) if longitude else None

            # Photos (JSON)
            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                point.photos = json.loads(photos_json) if photos_json else []
            except json.JSONDecodeError:
                point.photos = point.photos  # Garder les photos existantes en cas d'erreur

            # Besoin en clôture
            point.besoin_en_cloture = request.POST.get('besoin_en_cloture') == 'on'

            point.save()

            return JsonResponse({
                'success': True,
                'message': f'Point d\'eau "{point.nomabonne}" modifié avec succès',
                'redirect': f'/organisations/points-eau/{point.ouvrage.pk}/'
            })

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR in points_eau_edit: {error_details}")  # Log serveur
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}',
                'error_details': error_details
            }, status=500)

    elif request.method == 'GET':
        # Retourner les données du point d'eau en JSON pour remplir le formulaire
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(point.pk),
                'code_point_eau': point.code_point_eau or '',
                'nomabonne': point.nomabonne or '',
                'numeroteleph': point.numeroteleph or '',
                'contactabonne': point.contactabonne or '',
                'typeabonne': point.typeabonne or '',
                'type_point_eau': str(point.type_point_eau.pk) if point.type_point_eau else '',
                'compteur_tete': str(point.compteur_tete.pk) if point.compteur_tete else '',
                'parcelle': str(point.parcelle.pk) if point.parcelle else '',
                'datebranchement': point.datebranchement.strftime('%Y-%m-%d') if point.datebranchement else '',
                'datearretbranchement': point.datearretbranchement.strftime('%Y-%m-%d') if point.datearretbranchement else '',
                'tarifforfaitaire': str(point.tarifforfaitaire) if point.tarifforfaitaire else '',
                'pourcentage_tarif': format(point.pourcentage_tarif.normalize(), 'f') if point.pourcentage_tarif is not None else '',
                'estbranchementinstitutionnel': point.estbranchementinstitutionnel,
                # Champs consommateurs
                'nombre_consommateurs': str(point.nombre_consommateurs) if point.nombre_consommateurs else '',
                'nombre_menages_consommateurs': str(point.nombre_menages_consommateurs) if point.nombre_menages_consommateurs else '',
                'idxls': point.idxls or '',
                # Champs DiameX et paiements
                'numerodiamexdemande': str(point.numerodiamexdemande) if point.numerodiamexdemande else '',
                'numerodiamexdevis': str(point.numerodiamexdevis) if point.numerodiamexdevis else '',
                'basediamexdemande': str(point.basediamexdemande) if point.basediamexdemande else '',
                'basediamexdevis': str(point.basediamexdevis) if point.basediamexdevis else '',
                'datepaiementdemande': point.datepaiementdemande.strftime('%Y-%m-%d') if point.datepaiementdemande else '',
                'datepaiementdevis': point.datepaiementdevis.strftime('%Y-%m-%d') if point.datepaiementdevis else '',
                'montantdemandepaye': str(point.montantdemandepaye) if point.montantdemandepaye else '',
                'montantdevispaye': str(point.montantdevispaye) if point.montantdevispaye else '',
                # Coordonnées GPS
                'latitude': float(point.latitude) if point.latitude is not None else None,
                'longitude': float(point.longitude) if point.longitude is not None else None,
                # Photos
                'photos': point.photos if point.photos else [],
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def points_eau_delete(request, point_id):
    """Supprimer un point d'eau"""
    from apps.billing.models import PointEau
    from django.http import JsonResponse

    if request.method == 'POST':
        poste_nom = get_user_poste_name(request.user)
        if not request.user.is_superuser and poste_nom != 'Directeur':
            return JsonResponse({
                'success': False,
                'message': 'Accès refusé: seuls les Directeurs peuvent supprimer des points d\'eau.'
            }, status=403)

        try:
            point = get_object_or_404(PointEau, pk=point_id)
            ouvrage_id = point.ouvrage.pk
            nom_point = point.nomabonne
            point.delete()

            return JsonResponse({
                'success': True,
                'message': f'Point d\'eau "{nom_point}" supprimé avec succès',
                'redirect': f'/organisations/points-eau/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def point_eau_map(request, point_id):
    """Affichage de la carte interactive pour un point d'eau"""
    from apps.billing.models import PointEau

    point_eau = get_object_or_404(PointEau, pk=point_id)

    # Vérifier que le point d'eau a des coordonnées
    if not point_eau.latitude or not point_eau.longitude:
        messages.warning(request, 'Ce point d\'eau n\'a pas de coordonnées GPS définies.')
        if point_eau.ouvrage:
            return redirect('organization:points_eau_list_ouvrage', ouvrage_id=point_eau.ouvrage.pk)
        else:
            messages.error(request, 'Ce point d\'eau n\'est associé à aucun ouvrage.')
            return redirect('organization:points_eau_list')

    return render(request, 'organization/point_eau_map.html', {
        'point_eau': point_eau,
        'title': f'Carte - {point_eau.nomabonne}'
    })


def point_eau_map_legacy(request, point_id):
    """Gestion des anciens IDs numériques - redirection vers la vraie vue avec UUID"""
    from apps.billing.models import PointEau
    from django.http import Http404

    # Message d'erreur informatif pour les anciens IDs numériques
    messages.error(request, f'ID numérique "{point_id}" non valide. Les points d\'eau utilisent des UUIDs.')

    # Essayer de trouver un point d'eau avec des coordonnées valides
    try:
        # Chercher un point d'eau avec coordonnées GPS valides
        point_avec_coords = PointEau.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        ).exclude(
            latitude=0,
            longitude=0
        ).first()

        if point_avec_coords:
            messages.info(request, f'Exemple de carte avec le point d\'eau: {point_avec_coords.nomabonne}')
            return redirect('organization:point_eau_map', point_id=point_avec_coords.pk)
        else:
            messages.warning(request, 'Aucun point d\'eau avec coordonnées GPS trouvé dans la base de données.')
            return redirect('organization:points_eau_list')
    except Exception as e:
        messages.error(request, f'Erreur lors de la recherche de points d\'eau: {str(e)}')
        return redirect('organization:points_eau_list')


@xframe_options_sameorigin
@employe_required
def equipements_list(request, ouvrage_id=None):
    """Liste des équipements avec sélection d'ouvrage - Filtrée selon permissions"""
    from apps.infrastructure.models import EquipementConstitutif
    from django.db.models import Count

    # Récupérer les ouvrages accessibles selon les permissions
    ouvrages_org = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user).order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage_org = None

    if ouvrage_id:
        # Vérifier que l'ouvrage est accessible
        selected_ouvrage_org = get_object_or_404(ouvrages_org, pk=ouvrage_id)
    elif ouvrages_org.exists():
        selected_ouvrage_org = ouvrages_org.first()

    # Pour l'instant, utiliser les équipements d'infrastructure (à migrer plus tard)
    # Trouver l'ouvrage infrastructure correspondant par nom
    equipements = []
    stats_par_type = {}
    stats_par_statut = {}
    equipements_geolocalisés = 0

    if selected_ouvrage_org:
        try:
            equipements = EquipementConstitutif.objects.filter(
                ouvrage=selected_ouvrage_org
            ).select_related('type_equipement').order_by('nom')

            # Calcul des statistiques par type d'équipement
            if equipements:
                stats_types = equipements.values('type_equipement__nom_type').annotate(
                    count=Count('id')
                ).order_by('-count')

                for stat in stats_types:
                    type_nom = stat['type_equipement__nom_type'] or 'Non défini'
                    stats_par_type[type_nom] = stat['count']

                # Calcul des statistiques par statut
                stats_statuts = equipements.values('statut').annotate(
                    count=Count('id')
                )

                for stat in stats_statuts:
                    statut = stat['statut'] or 'Non défini'
                    stats_par_statut[statut] = stat['count']

                # Calcul du nombre d'équipements géolocalisés
                equipements_geolocalisés = equipements.exclude(
                    latitude__isnull=True
                ).exclude(
                    longitude__isnull=True
                ).count()

        except Exception:
            # Si pas d'équipements trouvés, laisser vide
            pass

    for equipement in equipements:
        equipement.photo_urls = _extract_photo_urls(getattr(equipement, 'photos', None))

    organigramme_candidates = _get_organigramme_candidates(selected_ouvrage_org)
    types_equipements = TypeEquipement.objects.filter(is_active=True).order_by('nom_type')
    ouvrage_map_data = _ouvrage_entity_map_data(selected_ouvrage_org, equipements, 'equipement')

    return render(request, 'organization/equipements_list.html', {
        'equipements': equipements,
        'ouvrages': ouvrages_org,
        'selected_ouvrage': selected_ouvrage_org,
        'types_equipements': types_equipements,
        'organigramme_equipements': organigramme_candidates['equipements'],
        'organigramme_compteurs': organigramme_candidates['compteurs'],
        'organigramme_points_eau': organigramme_candidates['points_eau'],
        'stats_par_type': stats_par_type,
        'stats_par_statut': stats_par_statut,
        'ouvrage_map_data': ouvrage_map_data,
        'equipements_geolocalisés': equipements_geolocalisés,
        'title': 'Gestion des Équipements'
    })


def equipements_create(request, ouvrage_id):
    """Créer un nouvel équipement"""
    from apps.infrastructure.models import EquipementConstitutif
    from django.http import JsonResponse

    ouvrage_org = get_object_or_404(Ouvrage, pk=ouvrage_id)

    if request.method == 'POST':
        try:

            # Récupérer les données du formulaire
            nom = request.POST.get('nom')
            type_equipement_id = request.POST.get('type_equipement')
            code_equipement = request.POST.get('code_equipement')
            statut = request.POST.get('statut', 'operationnel')
            description = request.POST.get('description', '')
            date_installation = request.POST.get('date_installation')
            derniere_maintenance = request.POST.get('derniere_maintenance')

            # Nouveaux champs
            nombre_nettoyages = request.POST.get('nombre_nettoyages_annuels')
            temps_acces = request.POST.get('temps_acces_heures')
            point_depart = request.POST.get('point_depart', '')
            longueur = request.POST.get('longueur_perimetre')
            duree = request.POST.get('duree_nettoyage')
            distance_materiaux = request.POST.get('distance_materiaux_locaux', '')
            haie_vive = request.POST.get('haie_vive_cultivable') == 'on'
            boite_vanne = request.POST.get('boite_a_vanne') == 'on'
            boite_vanne_utile = request.POST.get('boite_a_vanne_utile') == 'on'
            vanne_flotteur_val = request.POST.get('vanne_flotteur') == 'on'
            est_dans_village = request.POST.get('est_dans_village') == 'on'

            # Coordonnées GPS
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')

            # Photos (JSON)
            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                photos = json.loads(photos_json) if photos_json and photos_json.strip() else []
            except json.JSONDecodeError:
                photos = []

            # S'assurer que photos est None si vide (pour JSONField)
            if not photos:
                photos = None

            # Gérer le type d'équipement (ForeignKey)
            type_equipement = None
            if type_equipement_id:
                from apps.infrastructure.models import TypeEquipement
                type_equipement = TypeEquipement.objects.get(pk=type_equipement_id)

            # Créer l'équipement
            equipement = EquipementConstitutif.objects.create(
                nom=nom,
                type_equipement=type_equipement,
                code_equipement=code_equipement if code_equipement else None,
                statut=statut,
                description=description,
                ouvrage=ouvrage_org,
                date_installation=date_installation if date_installation else None,
                derniere_maintenance=derniere_maintenance if derniere_maintenance else None,
                nombre_nettoyages_annuels=int(nombre_nettoyages) if nombre_nettoyages else None,
                temps_acces_heures=float(temps_acces) if temps_acces else None,
                point_depart=point_depart,
                longueur_perimetre=int(longueur) if longueur else None,
                duree_nettoyage=float(duree) if duree else None,
                distance_materiaux_locaux=distance_materiaux if distance_materiaux else None,
                haie_vive_cultivable=haie_vive,
                boite_a_vanne=boite_vanne,
                boite_a_vanne_utile=boite_vanne_utile,
                vanne_flotteur=vanne_flotteur_val,
                est_dans_village=est_dans_village,
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                photos=photos,
            )

            return JsonResponse({
                'success': True,
                'message': f'Équipement "{nom}" créé avec succès',
                'redirect': f'/organisations/equipements/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def equipements_edit(request, equipement_id):
    """Modifier un équipement"""
    from apps.infrastructure.models import EquipementConstitutif
    from django.http import JsonResponse

    equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)

    if request.method == 'POST':
        try:
            # Mettre à jour les données
            equipement.nom = request.POST.get('nom')

            # Gérer le type d'équipement (ForeignKey)
            type_equipement_id = request.POST.get('type_equipement')
            if type_equipement_id:
                from apps.infrastructure.models import TypeEquipement
                equipement.type_equipement = TypeEquipement.objects.get(pk=type_equipement_id)
            else:
                equipement.type_equipement = None

            # Convertir les chaînes vides en NULL pour respecter la contrainte unique
            code_equipement = request.POST.get('code_equipement', '').strip()
            equipement.code_equipement = code_equipement if code_equipement else None
            equipement.statut = request.POST.get('statut', 'operationnel')
            equipement.description = request.POST.get('description', '')

            date_installation = request.POST.get('date_installation')
            equipement.date_installation = date_installation if date_installation else None

            derniere_maintenance = request.POST.get('derniere_maintenance')
            equipement.derniere_maintenance = derniere_maintenance if derniere_maintenance else None

            # Nouveaux champs numériques
            nombre_nettoyages = request.POST.get('nombre_nettoyages_annuels')
            equipement.nombre_nettoyages_annuels = int(nombre_nettoyages) if nombre_nettoyages else None

            temps_acces = request.POST.get('temps_acces_heures')
            equipement.temps_acces_heures = float(temps_acces) if temps_acces else None

            equipement.point_depart = request.POST.get('point_depart', '')

            longueur = request.POST.get('longueur_perimetre')
            equipement.longueur_perimetre = int(longueur) if longueur else None

            duree = request.POST.get('duree_nettoyage')
            equipement.duree_nettoyage = float(duree) if duree else None

            equipement.distance_materiaux_locaux = request.POST.get('distance_materiaux_locaux', '')

            # Nouveaux champs booléens
            equipement.haie_vive_cultivable = request.POST.get('haie_vive_cultivable') == 'on'
            equipement.boite_a_vanne = request.POST.get('boite_a_vanne') == 'on'
            equipement.boite_a_vanne_utile = request.POST.get('boite_a_vanne_utile') == 'on'
            equipement.vanne_flotteur = request.POST.get('vanne_flotteur') == 'on'
            equipement.est_dans_village = request.POST.get('est_dans_village') == 'on'

            # Coordonnées GPS
            latitude = request.POST.get('latitude')
            equipement.latitude = float(latitude) if latitude else None

            longitude = request.POST.get('longitude')
            equipement.longitude = float(longitude) if longitude else None

            # Photos (JSON)
            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                equipement.photos = json.loads(photos_json) if photos_json else []
            except json.JSONDecodeError:
                equipement.photos = equipement.photos  # Garder les photos existantes en cas d'erreur

            equipement.save()

            # Trouver l'ouvrage org correspondant pour la redirection
            try:
                ouvrage_org = Ouvrage.objects.get(nom_ouvrage=equipement.ouvrage.nom_ouvrage)
                ouvrage_id = ouvrage_org.pk
            except Ouvrage.DoesNotExist:
                ouvrage_id = 'unknown'

            return JsonResponse({
                'success': True,
                'message': f'Équipement "{equipement.nom}" modifié avec succès',
                'redirect': f'/organisations/equipements/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        # Retourner les données de l'équipement en JSON
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(equipement.pk),
                'nom': equipement.nom or '',
                'type_equipement': str(equipement.type_equipement.pk) if equipement.type_equipement else '',
                'code_equipement': equipement.code_equipement or '',
                'statut': equipement.statut or 'operationnel',
                'description': equipement.description or '',
                'date_installation': equipement.date_installation.strftime('%Y-%m-%d') if equipement.date_installation else '',
                'derniere_maintenance': equipement.derniere_maintenance.strftime('%Y-%m-%d') if equipement.derniere_maintenance else '',
                'nombre_nettoyages_annuels': equipement.nombre_nettoyages_annuels or '',
                'temps_acces_heures': equipement.temps_acces_heures or '',
                'point_depart': equipement.point_depart or '',
                'longueur_perimetre': equipement.longueur_perimetre or '',
                'duree_nettoyage': equipement.duree_nettoyage or '',
                'distance_materiaux_locaux': equipement.distance_materiaux_locaux or '',
                'haie_vive_cultivable': equipement.haie_vive_cultivable or False,
                'boite_a_vanne': equipement.boite_a_vanne or False,
                'boite_a_vanne_utile': equipement.boite_a_vanne_utile or False,
                'vanne_flotteur': equipement.vanne_flotteur or False,
                'latitude': str(equipement.latitude) if equipement.latitude else '',
                'longitude': str(equipement.longitude) if equipement.longitude else '',
                'photos': equipement.photos if equipement.photos else [],
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def _blocages_suppression(request, objets_proteges, limite=50):
    """Décrit les objets qui empêchent une suppression (clés étrangères protégées), avec un lien pour les corriger."""
    from django.urls import NoReverseMatch, reverse

    blocages = []
    for obj in list(objets_proteges)[:limite]:
        meta = obj._meta
        lien, lien_libelle = None, ''
        # Les résultats de contrôle d'une visite se consultent sur la fiche de la visite (tous les utilisateurs)
        visite_id = getattr(obj, 'visite_id', None)
        if visite_id:
            # (le nom de route 'visite-detail' existe aussi pour l'API : on écrit le chemin de la fiche HTML)
            lien, lien_libelle = f'/inspections/visite/{visite_id}/', 'Voir la visite'
        # L'administration permet de modifier (changer d'équipement) ou de supprimer l'élément
        if request.user.is_staff:
            try:
                lien = reverse(f'admin:{meta.app_label}_{meta.model_name}_change', args=[obj.pk])
                lien_libelle = 'Corriger (administration)'
            except NoReverseMatch:
                pass
        blocages.append({
            'modele': str(meta.verbose_name),
            'libelle': str(obj),
            'lien': lien,
            'lien_libelle': lien_libelle,
        })
    return blocages


def equipements_delete(request, equipement_id):
    """Supprimer un équipement"""
    from apps.infrastructure.models import EquipementConstitutif
    from django.http import JsonResponse

    if request.method == 'POST':
        try:
            equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)
            nom_equipement = equipement.nom

            # Trouver l'ouvrage org correspondant pour la redirection
            try:
                ouvrage_org = Ouvrage.objects.get(nom_ouvrage=equipement.ouvrage.nom_ouvrage)
                ouvrage_id = ouvrage_org.pk
            except Ouvrage.DoesNotExist:
                ouvrage_id = 'unknown'

            equipement.delete()

            return JsonResponse({
                'success': True,
                'message': f'Équipement "{nom_equipement}" supprimé avec succès',
                'redirect': f'/organisations/equipements/{ouvrage_id}/'
            })

        except ProtectedError as e:
            # Équipement encore utilisé ailleurs (ex. résultats de contrôle) : on liste ce qui bloque
            return JsonResponse({
                'success': False,
                'protege': True,
                'message': "Cet équipement est encore utilisé ailleurs et ne peut pas être supprimé tant que ces éléments existent.",
                'total': len(e.protected_objects),
                'blocages': _blocages_suppression(request, e.protected_objects),
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def compteurs_list(request, ouvrage_id=None):
    """Liste des compteurs avec selection d'ouvrage"""
    from django.utils import timezone
    from django.db.models import Sum, FloatField
    from django.db.models.functions import Coalesce
    from apps.billing.models import CompteurTete, Releve, ReleveCompteurTete

    # Recuperer uniquement les ouvrages autorises pour le menu deroulant
    ouvrages = _get_allowed_ouvrages_for_user(request.user).order_by('nom_ouvrage')

    # Determiner l'ouvrage selectionne
    selected_ouvrage = None
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(ouvrages, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Recuperer les compteurs de l'ouvrage selectionne
    compteurs = []
    if selected_ouvrage:
        compteurs = CompteurTete.objects.filter(
            ouvrage=selected_ouvrage
        ).order_by('numerocompteur')

        today = timezone.localdate()
        for compteur in compteurs:
            dernier_releve_tete = compteur.releves_compteur_tete.order_by('-date_releve', '-created_at').first()
            compteur.dernier_releve_tete = dernier_releve_tete
            compteur.index_courant_display = (
                dernier_releve_tete.nouvel_index if dernier_releve_tete else compteur.index_initial
            )
            points_lies = list(
                compteur.pointeau_set.filter(
                    datebranchement__isnull=False
                ).order_by('nomabonne')
            )
            compteur.points_eau_lies = points_lies
            compteur.points_eau_count = len(points_lies)

            volume_aval = Releve.objects.filter(
                point_eau__compteur_tete=compteur,
                datereleve__year=today.year,
                datereleve__month=today.month
            ).aggregate(
                total=Sum(
                    Coalesce('volume_facture', 'consommation', output_field=FloatField())
                )
            )['total'] or 0
            compteur.volume_aval_mois_courant = volume_aval

    organigramme_candidates = _get_organigramme_candidates(selected_ouvrage)
    est_directeur = user_is_director(request.user)

    return render(request, 'organization/compteurs_list.html', {
        'compteurs': compteurs,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'organigramme_equipements': organigramme_candidates['equipements'],
        'organigramme_compteurs': organigramme_candidates['compteurs'],
        'organigramme_points_eau': organigramme_candidates['points_eau'],
        'title': 'Gestion des Compteurs',
        'is_directeur': est_directeur,
        'est_directeur': est_directeur,
    })

def tarifs_list(request, ouvrage_id=None):
    """Liste des tarifs avec tranches en cascade"""
    from apps.billing.models import TarifVolumetrique, TypePointEau
    from apps.ouvrages.models import TarifVolumetriqueTranche

    # Récupérer tous les ouvrages pour le menu déroulant
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage = None
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Récupérer les tarifs de l'ouvrage sélectionné avec leurs tranches
    tarifs = []
    if selected_ouvrage:
        tarifs = TarifVolumetrique.objects.filter(
            ouvrage=selected_ouvrage
        ).prefetch_related('tranches_volumetriques').order_by('-datedebuttarif')

    types_point_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')
    est_directeur = user_is_director(request.user)

    return render(request, 'organization/tarifs_list.html', {
        'tarifs': tarifs,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'types_point_eau': types_point_eau,
        'title': 'Gestion des Tarifs Volumétriques',
        'est_directeur': est_directeur,
        'is_directeur': est_directeur,
    })


def modalites_gestion_list(request, ouvrage_id=None):
    """Liste des modalités de gestion"""
    from apps.billing.models import ModaliteGestion

    # Récupérer tous les ouvrages pour le menu déroulant
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage = None
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Récupérer les modalités de gestion avec les relations
    modalites = []
    if selected_ouvrage:
        modalites = ModaliteGestion.objects.filter(
            ouvrage=selected_ouvrage
        ).exclude(
            type_gestion='pas_de_gestion'
        ).select_related('gestionnaire', 'employe').order_by('-date_debut')

    # Récupérer les organisations et employés pour les dropdowns
    organisations = get_gestionnaire_organisations_queryset()

    est_directeur = user_is_director(request.user)

    return render(request, 'organization/modalites_gestion_list.html', {
        'modalites': modalites,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'organisations': organisations,
        'title': 'Gestion des Modalités de Gestion',
        'est_directeur': est_directeur,
        'is_directeur': est_directeur,
    })


def fournisseurs_list(request, ouvrage_id=None):
    """Liste des fournisseurs"""
    from apps.billing.models import Fournisseur, FournisseurFusionInstruction

    # Récupérer tous les ouvrages pour le menu déroulant
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage = None
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Pour les fournisseurs, ils ne sont pas liés directement aux ouvrages
    # mais on garde la navigation cohérente
    fournisseurs = Fournisseur.objects.all().order_by('nom_fournisseur')
    duplicate_groups = _build_fournisseur_duplicate_groups(fournisseurs)
    merge_instructions = FournisseurFusionInstruction.objects.select_related(
        'source_fournisseur',
        'target_fournisseur',
    ).all()

    est_directeur = user_is_director(request.user)

    return render(request, 'organization/fournisseurs_list.html', {
        'fournisseurs': fournisseurs,
        'duplicate_groups': duplicate_groups,
        'merge_instructions': merge_instructions,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'title': 'Gestion des Fournisseurs',
        'est_directeur': est_directeur,
    })


@login_required
@require_http_methods(["GET"])
def api_point_eau_diamex_extractions(request, point_id):
    """Proxy same-origin vers les propositions DiameX du point d'eau."""
    from apps.accounting.views_verification_ouvrages import api_extractions_point_eau

    return api_extractions_point_eau(request, point_id)


def adresses_list(request, ouvrage_id=None):
    """Liste des adresses"""
    from apps.infrastructure.models import Adresse

    # Récupérer tous les ouvrages pour le menu déroulant
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage = None
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Récupérer les adresses de l'ouvrage sélectionné
    adresses = []
    if selected_ouvrage:
        adresses = Adresse.objects.filter(
            ouvrage=selected_ouvrage
        ).order_by('nomadresse')

    est_directeur = user_is_director(request.user)

    return render(request, 'organization/adresses_list.html', {
        'adresses': adresses,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'title': 'Gestion des Adresses',
        'est_directeur': est_directeur,
    })


def cartes_sociales_list(request, ouvrage_id=None):
    """Liste des cartes sociales avec suivi des paiements mensuels"""
    from apps.infrastructure.models import CarteSociale
    from apps.billing.models import PointEau, Releve
    from django.utils import timezone
    from datetime import datetime
    import pytz

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Année sélectionnée (par défaut année courante)
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))

    # Récupérer tous les ouvrages pour le menu déroulant
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Déterminer l'ouvrage sélectionné
    selected_ouvrage = None
    points_eau = []
    if ouvrage_id:
        selected_ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
    elif ouvrages.exists():
        selected_ouvrage = ouvrages.first()

    # Récupérer les points d'eau de l'ouvrage
    if selected_ouvrage:
        points_eau = PointEau.objects.filter(ouvrage=selected_ouvrage).order_by('nomabonne')

    # Récupérer les cartes sociales de l'ouvrage sélectionné avec données de paiements
    cartes_data = []
    if selected_ouvrage:
        # CarteSociale a une relation directe avec Ouvrage
        cartes = CarteSociale.objects.filter(
            ouvrage=selected_ouvrage
        ).select_related('point_eau').order_by('point_eau__nomabonne', '-date_creation')

        # Pour chaque carte, récupérer les paiements mensuels
        for carte in cartes:
            # Initialiser les paiements par mois
            paiements_par_mois = {i: {'paye': False, 'releve_id': None} for i in range(1, 13)}

            # Si la carte a un point d'eau, chercher les relevés
            if carte.point_eau:
                # Récupérer tous les relevés du point d'eau pour l'année sélectionnée
                releves = Releve.objects.filter(
                    point_eau=carte.point_eau
                ).order_by('datereleve')

                for releve in releves:
                    if releve.datereleve:
                        # Conversion timezone
                        if hasattr(releve.datereleve, 'tzinfo'):
                            date_aware = releve.datereleve if releve.datereleve.tzinfo else timezone.make_aware(releve.datereleve)
                            date_madagascar = date_aware.astimezone(tz_madagascar)
                            annee = date_madagascar.year
                            mois = date_madagascar.month
                        else:
                            annee = releve.datereleve.year
                            mois = releve.datereleve.month

                        if annee == int(annee_filter):
                            # Vérifier si payé (numeroDiameX renseigné)
                            est_paye = releve.numeroDiameX and releve.numeroDiameX.strip() != ''
                            paiements_par_mois[mois] = {
                                'paye': est_paye,
                                'releve_id': releve.id
                            }

            # Compter payés/non payés pour cette carte
            nb_payes = sum(1 for m in range(1, 13) if paiements_par_mois[m]['paye'])
            nb_releves = sum(1 for m in range(1, 13) if paiements_par_mois[m]['releve_id'] is not None)
            nb_non_payes = nb_releves - nb_payes

            cartes_data.append({
                'carte': carte,
                'paiements_par_mois': paiements_par_mois,
                'nb_payes': nb_payes,
                'nb_non_payes': nb_non_payes,
                'nb_releves': nb_releves
            })

    est_directeur = user_is_director(request.user)

    return render(request, 'organization/cartes_sociales_list.html', {
        'cartes_data': cartes_data,
        'ouvrages': ouvrages,
        'selected_ouvrage': selected_ouvrage,
        'points_eau': points_eau,
        'annee_filter': annee_filter,
        'title': 'Gestion des Cartes Sociales',
        'est_directeur': est_directeur,
    })


def compteurs_create(request, ouvrage_id):
    """Créer un nouveau compteur pour un ouvrage"""
    from apps.billing.models import CompteurTete

    if request.method == 'POST':
        try:
            ouvrage = get_object_or_404(_get_allowed_ouvrages_for_user(request.user), pk=ouvrage_id)

            compteur = CompteurTete.objects.create(
                ouvrage=ouvrage,
                numerocompteur=request.POST.get('numerocompteur'),
                marque=request.POST.get('marque') or None,
                modele=request.POST.get('modele') or None,
                date_installation=request.POST.get('date_installation') or None,
                index_initial=request.POST.get('index_initial', 0),
                statut=request.POST.get('statut', 'operationnel')
            )

            return JsonResponse({
                'success': True,
                'message': f'Compteur "{compteur.numerocompteur}" créé avec succès',
                'redirect': f'/organisations/compteurs/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def compteurs_edit(request, compteur_id):
    """Modifier un compteur"""
    from apps.billing.models import CompteurTete

    allowed_ouvrages = _get_allowed_ouvrages_for_user(request.user)
    compteur = get_object_or_404(CompteurTete.objects.filter(ouvrage__in=allowed_ouvrages), pk=compteur_id)

    if request.method == 'POST':
        try:
            compteur.numerocompteur = request.POST.get('numerocompteur')
            compteur.marque = request.POST.get('marque') or None
            compteur.modele = request.POST.get('modele') or None
            compteur.date_installation = request.POST.get('date_installation') or None
            compteur.index_initial = request.POST.get('index_initial', 0)
            compteur.statut = request.POST.get('statut', 'operationnel')
            compteur.save()

            return JsonResponse({
                'success': True,
                'message': f'Compteur "{compteur.numerocompteur}" modifié avec succès',
                'redirect': f'/organisations/compteurs/{compteur.ouvrage.pk}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(compteur.pk),
                'numerocompteur': compteur.numerocompteur or '',
                'marque': compteur.marque or '',
                'modele': compteur.modele or '',
                'date_installation': compteur.date_installation.strftime('%Y-%m-%d') if compteur.date_installation else '',
                'index_initial': str(compteur.index_initial),
                'statut': compteur.statut,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def compteurs_delete(request, compteur_id):
    """Supprimer un compteur"""
    from apps.billing.models import CompteurTete

    if request.method == 'POST':
        try:
            allowed_ouvrages = _get_allowed_ouvrages_for_user(request.user)
            compteur = get_object_or_404(CompteurTete.objects.filter(ouvrage__in=allowed_ouvrages), pk=compteur_id)
            ouvrage_id = compteur.ouvrage.pk
            numero = compteur.numerocompteur
            compteur.delete()

            return JsonResponse({
                'success': True,
                'message': f'Compteur "{numero}" supprimé avec succès',
                'redirect': f'/organisations/compteurs/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

def compteurs_saisir_releve(request, compteur_id):
    """Saisir un releve de compteur de tete et comparer avec les points d'eau aval."""
    from decimal import Decimal, InvalidOperation
    from datetime import datetime
    from django.db import IntegrityError, transaction
    from apps.billing.models import CompteurTete, ReleveCompteurTete
    from .views_compteurs_releves import _build_snapshot, _resequence_releves, _validate_gap_explanation

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Methode non autorisee'})

    try:
        allowed_ouvrages = _get_allowed_ouvrages_for_user(request.user)
        compteur = get_object_or_404(
            CompteurTete.objects.filter(ouvrage__in=allowed_ouvrages),
            pk=compteur_id
        )

        date_releve_str = (request.POST.get('date_releve') or '').strip()
        nouvel_index_str = (request.POST.get('nouvel_index') or '').strip()

        if not date_releve_str or not nouvel_index_str:
            return JsonResponse({
                'success': False,
                'message': 'La date et le nouvel index sont obligatoires.'
            })

        try:
            date_releve = datetime.strptime(date_releve_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'Format de date invalide.'
            })

        try:
            nouvel_index = Decimal(nouvel_index_str.replace(',', '.'))
        except InvalidOperation:
            return JsonResponse({
                'success': False,
                'message': 'Nouvel index invalide.'
            })

        snapshot = _build_snapshot(compteur, date_releve, nouvel_index)
        explication_ecart = _validate_gap_explanation(snapshot['ecart_volume'], request.POST.get('explication_ecart'))

        with transaction.atomic():
            releve_tete = ReleveCompteurTete.objects.create(
                compteur_tete=compteur,
                date_releve=date_releve,
                ancien_index=snapshot['ancien_index'],
                nouvel_index=nouvel_index,
                volume_tete=snapshot['volume_tete'],
                volume_aval=snapshot['volume_aval'],
                ecart_volume=snapshot['ecart_volume'],
                nb_points_eau_aval=snapshot['nb_points_eau_aval'],
                explication_ecart=explication_ecart,
            )
            _resequence_releves(compteur)
            releve_tete.refresh_from_db()

        volume_tete = releve_tete.volume_tete
        volume_aval = releve_tete.volume_aval
        ecart = releve_tete.ecart_volume
        points_data = snapshot['points_details']
        taux_couverture = None
        if volume_tete > 0:
            taux_couverture = float((volume_aval / volume_tete) * Decimal('100'))

        return JsonResponse({
            'success': True,
            'message': f'Releve enregistre pour {compteur.numerocompteur}.',
            'data': {
                'releve_id': str(releve_tete.id),
                'compteur': compteur.numerocompteur,
                'mois': date_releve.month,
                'annee': date_releve.year,
                'ancien_index': float(releve_tete.ancien_index),
                'nouvel_index': float(releve_tete.nouvel_index),
                'volume_tete': float(volume_tete),
                'volume_aval': float(volume_aval),
                'ecart': float(ecart),
                'taux_couverture': round(taux_couverture, 2) if taux_couverture is not None else None,
                'points_eau_count': releve_tete.nb_points_eau_aval,
                'points_eau': points_data,
            }
        })
    except IntegrityError:
        return JsonResponse({
            'success': False,
            'message': 'Un releve existe deja pour ce compteur a cette date.'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la saisie du releve : {str(e)}'
        })

def fournisseurs_create(request):
    """Créer un nouveau fournisseur"""
    from apps.billing.models import Fournisseur

    if request.method == 'POST':
        try:
            fournisseur = Fournisseur.objects.create(
                idxls=int(request.POST.get('idxls')) if request.POST.get('idxls') else None,
                nom_fournisseur=request.POST.get('nom_fournisseur'),
                telephone=request.POST.get('telephone') or None,
                email=request.POST.get('email') or None,
                adresse=request.POST.get('adresse') or None,
                type_fournisseur=request.POST.get('type_fournisseur', 'equipement'),
                numero_nif=request.POST.get('numero_nif') or None,
                numero_stat=request.POST.get('numero_stat') or None,
                actif=request.POST.get('actif', 'true').lower() == 'true'
            )

            return JsonResponse({
                'success': True,
                'message': f'Fournisseur "{fournisseur.nom_fournisseur}" créé avec succès',
                'redirect': '/organisations/fournisseurs/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def fournisseurs_edit(request, fournisseur_id):
    """Modifier un fournisseur"""
    from apps.billing.models import Fournisseur

    fournisseur = get_object_or_404(Fournisseur, pk=fournisseur_id)

    if request.method == 'POST':
        try:
            fournisseur.idxls = int(request.POST.get('idxls')) if request.POST.get('idxls') else None
            fournisseur.nom_fournisseur = request.POST.get('nom_fournisseur')
            fournisseur.telephone = request.POST.get('telephone') or None
            fournisseur.email = request.POST.get('email') or None
            fournisseur.adresse = request.POST.get('adresse') or None
            fournisseur.type_fournisseur = request.POST.get('type_fournisseur', 'equipement')
            fournisseur.numero_nif = request.POST.get('numero_nif') or None
            fournisseur.numero_stat = request.POST.get('numero_stat') or None
            fournisseur.actif = request.POST.get('actif', 'true').lower() == 'true'
            fournisseur.save()

            return JsonResponse({
                'success': True,
                'message': f'Fournisseur "{fournisseur.nom_fournisseur}" modifié avec succès',
                'redirect': '/organisations/fournisseurs/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(fournisseur.pk),
                'idxls': fournisseur.idxls or '',
                'nom_fournisseur': fournisseur.nom_fournisseur or '',
                'telephone': fournisseur.telephone or '',
                'email': fournisseur.email or '',
                'adresse': fournisseur.adresse or '',
                'type_fournisseur': fournisseur.type_fournisseur,
                'numero_nif': fournisseur.numero_nif or '',
                'numero_stat': fournisseur.numero_stat or '',
                'actif': fournisseur.actif,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@employe_required
def fournisseurs_merge(request):
    """Fusionner un fournisseur doublon vers un fournisseur conserve."""
    director_error = _ensure_director_json(request)
    if director_error:
        return director_error

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Methode non autorisee'})

    from apps.accounting.models import BaseDiameX
    from apps.billing.models import Fournisseur, FournisseurFusionInstruction

    source_id = request.POST.get('source_fournisseur_id')
    target_id = request.POST.get('target_fournisseur_id')

    if not source_id or not target_id:
        return JsonResponse({'success': False, 'message': 'Source et cible sont obligatoires.'}, status=400)
    if source_id == target_id:
        return JsonResponse({'success': False, 'message': 'La source et la cible doivent etre differentes.'}, status=400)

    source = get_object_or_404(Fournisseur, pk=source_id)
    target = get_object_or_404(Fournisseur, pk=target_id)

    with transaction.atomic():
        _merge_supplier_values(target, source)
        reassigned = _reassign_fournisseur_relations(source, target)

        instruction = None
        if source.idxls is not None and target.idxls is not None and source.idxls != target.idxls:
            affected_count = BaseDiameX.objects.filter(
                fournisseur__iexact=str(source.idxls)
            ).count()
            instruction = FournisseurFusionInstruction.objects.create(
                source_fournisseur=source,
                target_fournisseur=target,
                ancien_idxls=source.idxls,
                nouvel_idxls=target.idxls,
                lignes_diamex_a_corriger=affected_count,
                note=_build_diamex_instruction_text(source, target, affected_count),
            )

        source_nom = source.nom_fournisseur
        target_nom = target.nom_fournisseur
        source.delete()

    summary_parts = [
        f'Fournisseur "{source_nom}" fusionne vers "{target_nom}".',
    ]
    if reassigned:
        details = ', '.join(f'{label}: {count}' for label, count in sorted(reassigned.items()))
        summary_parts.append(f'References reaffectees -> {details}.')
    if instruction:
        summary_parts.append('Instruction DiameX creee pour correction manuelle des lignes comptables.')

    return JsonResponse({
        'success': True,
        'message': ' '.join(summary_parts),
        'redirect': '/organisations/fournisseurs/',
    })


@employe_required
def fournisseurs_instruction_update(request, instruction_id):
    """Mettre a jour le statut/commentaire d'une instruction de correction DiameX."""
    director_error = _ensure_director_json(request)
    if director_error:
        return director_error

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Methode non autorisee'})

    from apps.billing.models import FournisseurFusionInstruction

    instruction = get_object_or_404(FournisseurFusionInstruction, pk=instruction_id)
    statut = request.POST.get('statut', '').strip()
    commentaire_admin = request.POST.get('commentaire_admin', '').strip()

    if statut not in {
        FournisseurFusionInstruction.STATUS_PENDING,
        FournisseurFusionInstruction.STATUS_DONE,
    }:
        return JsonResponse({'success': False, 'message': 'Statut invalide.'}, status=400)

    instruction.statut = statut
    instruction.commentaire_admin = commentaire_admin
    instruction.done_at = timezone.now() if statut == FournisseurFusionInstruction.STATUS_DONE else None
    instruction.save(update_fields=['statut', 'commentaire_admin', 'done_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'message': 'Instruction mise a jour.',
        'redirect': '/organisations/fournisseurs/',
    })


def fournisseurs_delete(request, fournisseur_id):
    """Supprimer un fournisseur"""
    from apps.billing.models import Fournisseur

    if request.method == 'POST':
        try:
            fournisseur = get_object_or_404(Fournisseur, pk=fournisseur_id)
            nom = fournisseur.nom_fournisseur
            fournisseur.delete()

            return JsonResponse({
                'success': True,
                'message': f'Fournisseur "{nom}" supprimé avec succès',
                'redirect': '/organisations/fournisseurs/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def adresses_create(request, ouvrage_id):
    """Créer une nouvelle adresse pour un ouvrage"""
    from apps.infrastructure.models import Adresse

    if request.method == 'POST':
        try:
            ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

            adresse = Adresse.objects.create(
                ouvrage=ouvrage,
                nomadresse=request.POST.get('nomadresse'),
                adresse_complete=request.POST.get('adresse_complete') or None,
                latitude=request.POST.get('latitude') or None,
                longitude=request.POST.get('longitude') or None,
                type_adresse=request.POST.get('type_adresse', 'principale'),
                is_active=request.POST.get('is_active', 'true').lower() == 'true'
            )

            return JsonResponse({
                'success': True,
                'message': f'Adresse "{adresse.nomadresse}" créée avec succès',
                'redirect': f'/organisations/adresses/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def adresses_edit(request, adresse_id):
    """Modifier une adresse"""
    from apps.infrastructure.models import Adresse

    adresse = get_object_or_404(Adresse, pk=adresse_id)

    if request.method == 'POST':
        try:
            adresse.nomadresse = request.POST.get('nomadresse')
            adresse.adresse_complete = request.POST.get('adresse_complete') or None
            adresse.latitude = request.POST.get('latitude') or None
            adresse.longitude = request.POST.get('longitude') or None
            adresse.type_adresse = request.POST.get('type_adresse', 'principale')
            adresse.is_active = request.POST.get('is_active', 'true').lower() == 'true'
            adresse.save()

            return JsonResponse({
                'success': True,
                'message': f'Adresse "{adresse.nomadresse}" modifiée avec succès',
                'redirect': f'/organisations/adresses/{adresse.ouvrage.pk}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(adresse.pk),
                'nomadresse': adresse.nomadresse or '',
                'adresse_complete': adresse.adresse_complete or '',
                'latitude': str(adresse.latitude) if adresse.latitude else '',
                'longitude': str(adresse.longitude) if adresse.longitude else '',
                'type_adresse': adresse.type_adresse,
                'is_active': adresse.is_active,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def adresses_delete(request, adresse_id):
    """Supprimer une adresse"""
    from apps.infrastructure.models import Adresse

    if request.method == 'POST':
        try:
            adresse = get_object_or_404(Adresse, pk=adresse_id)
            ouvrage_id = adresse.ouvrage.pk
            nom = adresse.nomadresse
            adresse.delete()

            return JsonResponse({
                'success': True,
                'message': f'Adresse "{nom}" supprimée avec succès',
                'redirect': f'/organisations/adresses/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def cartes_sociales_create(request, ouvrage_id):
    """Créer une nouvelle carte sociale"""
    from apps.infrastructure.models import CarteSociale
    from apps.billing.models import PointEau
    from datetime import date

    if request.method == 'POST':
        try:
            ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

            # Récupérer le point d'eau
            point_eau_id = request.POST.get('point_eau_id')
            point_eau = get_object_or_404(PointEau, pk=point_eau_id) if point_eau_id else None

            # Calculer le statut automatiquement
            date_expiration = request.POST.get('date_expiration') or None
            if date_expiration:
                date_exp = date.fromisoformat(date_expiration)
                statut = 'active' if date_exp >= date.today() else 'expiree'
            else:
                statut = 'active'

            carte = CarteSociale.objects.create(
                ouvrage=ouvrage,
                numero_carte=request.POST.get('numero_carte'),
                nom_beneficiaire=request.POST.get('nom_beneficiaire'),
                point_eau=point_eau,
                date_expiration=date_expiration,
                statut=statut,
                observations=request.POST.get('observations') or None
            )

            return JsonResponse({
                'success': True,
                'message': f'Carte sociale "{carte.numero_carte}" créée avec succès',
                'redirect': f'/organisations/cartes-sociales/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def cartes_sociales_edit(request, carte_id):
    """Modifier une carte sociale"""
    from apps.infrastructure.models import CarteSociale
    from apps.billing.models import PointEau
    from datetime import date

    carte = get_object_or_404(CarteSociale, pk=carte_id)

    if request.method == 'POST':
        try:
            # Récupérer le point d'eau
            point_eau_id = request.POST.get('point_eau_id')
            point_eau = get_object_or_404(PointEau, pk=point_eau_id) if point_eau_id else None

            # Calculer le statut automatiquement
            date_expiration = request.POST.get('date_expiration') or None
            if date_expiration:
                date_exp = date.fromisoformat(date_expiration)
                statut = 'active' if date_exp >= date.today() else 'expiree'
            else:
                statut = 'active'

            carte.numero_carte = request.POST.get('numero_carte')
            carte.nom_beneficiaire = request.POST.get('nom_beneficiaire')
            carte.point_eau = point_eau
            carte.date_expiration = date_expiration
            carte.statut = statut
            carte.observations = request.POST.get('observations') or None
            carte.save()

            return JsonResponse({
                'success': True,
                'message': f'Carte sociale "{carte.numero_carte}" modifiée avec succès',
                'redirect': f'/organisations/cartes-sociales/{carte.ouvrage.pk}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(carte.pk),
                'numero_carte': carte.numero_carte or '',
                'nom_beneficiaire': carte.nom_beneficiaire or '',
                'point_eau_id': str(carte.point_eau.pk) if carte.point_eau else '',
                'date_expiration': carte.date_expiration.strftime('%Y-%m-%d') if carte.date_expiration else '',
                'observations': carte.observations or '',
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def cartes_sociales_delete(request, carte_id):
    """Supprimer une carte sociale"""
    from apps.infrastructure.models import CarteSociale

    if request.method == 'POST':
        try:
            carte = get_object_or_404(CarteSociale, pk=carte_id)
            ouvrage_id = carte.ouvrage.pk
            numero = carte.numero_carte
            carte.delete()

            return JsonResponse({
                'success': True,
                'message': f'Carte sociale "{numero}" supprimée avec succès',
                'redirect': f'/organisations/cartes-sociales/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def modalites_gestion_create(request, ouvrage_id):
    """Créer une nouvelle modalité de gestion"""
    from apps.billing.models import ModaliteGestion

    if request.method == 'POST':
        try:
            ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

            # Récupérer les IDs et convertir en objets
            type_gestion = request.POST.get('type_gestion')
            if type_gestion == 'pas_de_gestion':
                return JsonResponse({
                    'success': False,
                    'message': 'Le type "Pas de gestion" ne doit plus etre saisi comme modalite. Laissez simplement l\'ouvrage sans ligne de gestion.'
                })

            gestionnaire_id = request.POST.get('gestionnaire_id') or None
            employe_id = request.POST.get('employe_id') or None
            date_fin = request.POST.get('date_fin') or None
            explication_fin = (request.POST.get('explication_fin') or '').strip() or None

            modalite = ModaliteGestion.objects.create(
                ouvrage=ouvrage,
                type_gestion=type_gestion,
                gestionnaire_id=gestionnaire_id,
                employe_id=employe_id,
                date_debut=request.POST.get('date_debut'),
                date_fin=date_fin,
                explication_fin=explication_fin if date_fin else None,
                modalitepaiement=request.POST.get('modalitepaiement') or None
            )

            gestionnaire_nom = modalite.gestionnaire.nom_organisation if modalite.gestionnaire else 'Non spécifié'
            return JsonResponse({
                'success': True,
                'message': f'Modalité de gestion "{gestionnaire_nom}" créée avec succès',
                'redirect': f'/organisations/modalites-gestion/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def modalites_gestion_edit(request, modalite_id):
    """Modifier une modalité de gestion"""
    from apps.billing.models import ModaliteGestion

    modalite = get_object_or_404(ModaliteGestion, pk=modalite_id)

    if request.method == 'POST':
        import logging
        logger = logging.getLogger(__name__)
        try:
            from django.utils.dateparse import parse_date
            import datetime as dt

            def _parse_date_value(value, field_name):
                if value in (None, ''):
                    return None
                if isinstance(value, dt.datetime):
                    return value.date()
                if isinstance(value, dt.date):
                    return value
                if not isinstance(value, str):
                    value = str(value)

                parsed = parse_date(value)
                if parsed:
                    return parsed

                for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
                    try:
                        return dt.datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue

                raise ValueError(f"Date invalide pour {field_name}: {value}")

            type_gestion = request.POST.get('type_gestion')
            if type_gestion == 'pas_de_gestion':
                return JsonResponse({
                    'success': False,
                    'message': 'Le type "Pas de gestion" ne doit plus etre saisi comme modalite. Supprimez simplement la ligne si l\'ouvrage n\'a plus de gestion.'
                })

            modalite.type_gestion = type_gestion
            modalite.gestionnaire_id = request.POST.get('gestionnaire_id') or None
            if 'employe_id' in request.POST:
                modalite.employe_id = request.POST.get('employe_id') or None
            
            date_debut_str = request.POST.get('date_debut')
            modalite.date_debut = _parse_date_value(date_debut_str, 'date_debut')
            if modalite.date_debut is None:
                raise ValueError("date_debut est obligatoire")

            date_fin_str = request.POST.get('date_fin')
            modalite.date_fin = _parse_date_value(date_fin_str, 'date_fin')

            modalite.modalitepaiement = request.POST.get('modalitepaiement') or None
            modalite.explication_fin = ((request.POST.get('explication_fin') or '').strip() or None) if modalite.date_fin else None
            modalite.save()

            gestionnaire_nom = modalite.gestionnaire.nom_organisation if modalite.gestionnaire else 'Non spécifié'
            return JsonResponse({
                'success': True,
                'message': f'Modalité de gestion "{gestionnaire_nom}" modifiée avec succès',
                'redirect': f'/organisations/modalites-gestion/{modalite.ouvrage.pk}/'
            })

        except Exception as e:
            import traceback
            from django.conf import settings

            logger.exception("Erreur modification modalite gestion", extra={
                'modalite_id': str(modalite_id),
                'date_debut': request.POST.get('date_debut'),
                'date_fin': request.POST.get('date_fin'),
            })

            response = {
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            }
            if settings.DEBUG:
                response['debug'] = {
                    'traceback': traceback.format_exc(),
                    'date_debut_raw': request.POST.get('date_debut'),
                    'date_fin_raw': request.POST.get('date_fin'),
                    'date_debut_value': str(modalite.date_debut),
                    'date_fin_value': str(modalite.date_fin),
                    'date_debut_type': type(modalite.date_debut).__name__,
                    'date_fin_type': type(modalite.date_fin).__name__,
                }
            return JsonResponse(response)

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(modalite.pk),
                'type_gestion': modalite.type_gestion,
                'gestionnaire_id': str(modalite.gestionnaire.id) if modalite.gestionnaire else '',
                'gestionnaire_nom': modalite.gestionnaire.nom_organisation if modalite.gestionnaire else '',
                'employe_id': str(modalite.employe.id) if modalite.employe else '',
                'employe_surnom': modalite.employe.surnom if modalite.employe else '',
                'date_debut': modalite.date_debut.strftime('%Y-%m-%d') if modalite.date_debut else '',
                'date_fin': modalite.date_fin.strftime('%Y-%m-%d') if modalite.date_fin else '',
                'explication_fin': modalite.explication_fin or '',
                'modalitepaiement': modalite.modalitepaiement or '',
                'statut': modalite.statut,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def modalites_gestion_delete(request, modalite_id):
    """Supprimer une modalité de gestion"""
    from apps.billing.models import ModaliteGestion

    if request.method == 'POST':
        try:
            modalite = get_object_or_404(ModaliteGestion, pk=modalite_id)
            ouvrage_id = modalite.ouvrage.pk
            gestionnaire_nom = modalite.gestionnaire.nom_organisation if modalite.gestionnaire else 'Non spécifié'
            modalite.delete()

            return JsonResponse({
                'success': True,
                'message': f'Modalité de gestion "{gestionnaire_nom}" supprimée avec succès',
                'redirect': f'/organisations/modalites-gestion/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_create(request, ouvrage_id):
    """Créer un nouveau tarif volumétrique"""
    from apps.billing.models import TarifVolumetrique

    if request.method == 'POST':
        try:
            ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

            # Déterminer si le tarif est actif : actif SI date fin est vide/None
            datefintarif = request.POST.get('datefintarif') or None
            actif = datefintarif is None

            tarif = TarifVolumetrique.objects.create(
                ouvrage=ouvrage,
                type_point_eau_id=request.POST.get('type_point_eau') or None,
                datedebuttarif=request.POST.get('datedebuttarif'),
                datefintarif=datefintarif,
                prixabonnement=request.POST.get('prixabonnement', 0),
                volume_minimum_facture=request.POST.get('volume_minimum_facture') or None,
                institutionnel=request.POST.get('institutionnel') in ('on', 'true', '1'),
                actif=actif
            )

            return JsonResponse({
                'success': True,
                'message': f'Tarif créé avec succès (début: {tarif.datedebuttarif})',
                'redirect': f'/organisations/tarifs/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_edit(request, tarif_id):
    """Modifier un tarif volumétrique"""
    from apps.billing.models import TarifVolumetrique

    tarif = get_object_or_404(TarifVolumetrique, pk=tarif_id)

    if request.method == 'POST':
        try:
            # Déterminer si le tarif est actif : actif SI date fin est vide/None
            datefintarif = request.POST.get('datefintarif') or None
            actif = datefintarif is None

            tarif.datedebuttarif = request.POST.get('datedebuttarif')
            tarif.datefintarif = datefintarif
            tarif.prixabonnement = request.POST.get('prixabonnement', 0)
            tarif.type_point_eau_id = request.POST.get('type_point_eau') or None
            tarif.volume_minimum_facture = request.POST.get('volume_minimum_facture') or None
            tarif.institutionnel = request.POST.get('institutionnel') in ('on', 'true', '1')
            tarif.actif = actif
            tarif.save()

            return JsonResponse({
                'success': True,
                'message': f'Tarif modifié avec succès',
                'redirect': f'/organisations/tarifs/{tarif.ouvrage.pk}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(tarif.pk),
                'datedebuttarif': tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else '',
                'datefintarif': tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else '',
                'prixabonnement': str(tarif.prixabonnement),
                'type_point_eau': str(tarif.type_point_eau_id) if tarif.type_point_eau_id else '',
                'volume_minimum_facture': str(tarif.volume_minimum_facture) if tarif.volume_minimum_facture is not None else '',
                'institutionnel': tarif.institutionnel,
                'actif': tarif.actif,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_delete(request, tarif_id):
    """Supprimer un tarif volumétrique"""
    from apps.billing.models import TarifVolumetrique

    if request.method == 'POST':
        try:
            tarif = get_object_or_404(TarifVolumetrique, pk=tarif_id)
            ouvrage_id = tarif.ouvrage.pk
            date_debut = tarif.datedebuttarif
            tarif.delete()

            return JsonResponse({
                'success': True,
                'message': f'Tarif (début: {date_debut}) supprimé avec succès',
                'redirect': f'/organisations/tarifs/{ouvrage_id}/'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_tranches_list(request, tarif_id):
    """Lister les tranches volumétriques d'un tarif"""
    from apps.ouvrages.models import TarifVolumetriqueTranche

    try:
        tranches = TarifVolumetriqueTranche.objects.filter(
            tarifvolumetrique_id=tarif_id
        ).order_by('tranchesuperieur')

        tranches_data = [{
            'id': str(tranche.id),
            'tranchesuperieur': tranche.tranchesuperieur,
            'tarif': tranche.tarif
        } for tranche in tranches]

        return JsonResponse({
            'success': True,
            'tranches': tranches_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur : {str(e)}'
        })


def tarifs_tranches_create(request, tarif_id):
    """Créer une nouvelle tranche volumétrique"""
    from apps.billing.models import TarifVolumetrique
    from apps.ouvrages.models import TarifVolumetriqueTranche

    if request.method == 'POST':
        try:
            tarif = get_object_or_404(TarifVolumetrique, pk=tarif_id)

            tranche = TarifVolumetriqueTranche.objects.create(
                tarifvolumetrique=tarif,
                tranchesuperieur=request.POST.get('tranchesuperieur'),
                tarif=request.POST.get('tarif')
            )

            return JsonResponse({
                'success': True,
                'message': 'Tranche créée avec succès',
                'tranche': {
                    'id': str(tranche.id),
                    'tranchesuperieur': tranche.tranchesuperieur,
                    'tarif': tranche.tarif
                }
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_tranches_edit(request, tranche_id):
    """Modifier une tranche volumétrique"""
    from apps.ouvrages.models import TarifVolumetriqueTranche

    tranche = get_object_or_404(TarifVolumetriqueTranche, pk=tranche_id)

    if request.method == 'POST':
        try:
            tranche.tranchesuperieur = request.POST.get('tranchesuperieur')
            tranche.tarif = request.POST.get('tarif')
            tranche.save()

            return JsonResponse({
                'success': True,
                'message': 'Tranche modifiée avec succès',
                'tranche': {
                    'id': str(tranche.id),
                    'tranchesuperieur': tranche.tranchesuperieur,
                    'tarif': tranche.tarif
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            })

    elif request.method == 'GET':
        return JsonResponse({
            'success': True,
            'tranche': {
                'id': str(tranche.id),
                'tranchesuperieur': tranche.tranchesuperieur,
                'tarif': tranche.tarif
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def tarifs_tranches_delete(request, tranche_id):
    """Supprimer une tranche volumétrique"""
    from apps.ouvrages.models import TarifVolumetriqueTranche

    if request.method == 'POST':
        try:
            tranche = get_object_or_404(TarifVolumetriqueTranche, pk=tranche_id)
            tranche.delete()

            return JsonResponse({
                'success': True,
                'message': 'Tranche supprimée avec succès'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la suppression : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


# CRUD pour les Bases
def base_list(request):
    bases = Base.objects.select_related(
        'organisation', 'ouvrage', 'ouvrage_correspondant'
    ).all().order_by('organisation__nom_organisation', 'nom_base')
    return render(request, 'organization/base_list.html', {
        'bases': bases,
        'title': 'Bases'
    })


def base_create(request):
    if request.method == 'POST':
        form = BaseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Base créée avec succès!')
            return redirect('organization:base_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = BaseForm()

    return render(request, 'organization/base_form.html', {
        'form': form,
        'title': 'Nouvelle Base'
    })


def base_detail(request, pk):
    from apps.employees.models import Employe
    from django.core.paginator import Paginator

    base = get_object_or_404(Base, pk=pk)
    magasins = base.magasins.all().order_by('nom_magasin')
    journaux = base.journaux.all().order_by('nom_journal')

    # Récupérer les employés de cette base avec leurs contrats
    employes_queryset = Employe.objects.filter(base=base).select_related('poste').prefetch_related('contrats').order_by('nom', 'prenom')

    # Pagination des employés (10 par page)
    paginator = Paginator(employes_queryset, 10)
    page_number = request.GET.get('page')
    employes = paginator.get_page(page_number)

    return render(request, 'organization/base_detail.html', {
        'base': base,
        'magasins': magasins,
        'journaux': journaux,
        'employes': employes,
        'title': f'Base {base.nom_base}'
    })


def base_update(request, pk):
    base = get_object_or_404(Base, pk=pk)
    if request.method == 'POST':
        form = BaseForm(request.POST, instance=base)
        if form.is_valid():
            form.save()
            messages.success(request, 'Base modifiée avec succès!')
            return redirect('organization:base_detail', pk=pk)
    else:
        form = BaseForm(instance=base)

    return render(request, 'organization/base_form.html', {
        'form': form,
        'base': base,
        'title': 'Modifier Base'
    })


def base_delete(request, pk):
    base = get_object_or_404(Base, pk=pk)
    if request.method == 'POST':
        base.delete()
        messages.success(request, 'Base supprimée avec succès!')
        return redirect('organization:base_list')
    return render(request, 'organization/base_confirm_delete.html', {
        'base': base,
        'title': 'Supprimer Base'
    })


# Vue pour la page en cascade
def organization_cascade(request):
    """Page en cascade pour la gestion des organisations"""
    return render(request, 'organization/organization_cascade.html', {
        'title': 'Gestion en Cascade - Organisations'
    })



# API ENDPOINTS pour les formulaires en cascade

def api_all_bases(request):
    """API pour charger toutes les bases pour les formulaires"""
    bases = Base.objects.select_related('organisation').all().order_by('organisation__nom_organisation', 'nom_base')

    data = []
    for base in bases:
        data.append({
            'id': str(base.id),
            'nom_base': base.nom_base,
            'telephone': base.telephone or '',
            'organisation': str(base.organisation.id),
            'organisation_nom': base.organisation.nom_organisation,
        })

    return JsonResponse(data, safe=False)


def api_organisations(request):
    """API pour charger toutes les organisations"""
    organisations = Organisation.objects.annotate(
        bases_count=Count('bases', distinct=True),
        comptes_count=Count('comptes', distinct=True),
        postes_count=Count('postes', distinct=True),
        affectations_count=Count('affectations_gestionnaires', distinct=True),
    ).order_by('nom_organisation')

    data = []
    for org in organisations:
        data.append({
            'id': str(org.id),
            'nom_organisation': org.nom_organisation,
            'type_organisation': org.type_organisation,
            'type_organisation_label': org.get_type_organisation_display(),
            'logo': org.logo.url if org.logo else None,
            'telephone': org.telephone,
            'mail': org.mail,
            'adresse1': org.adresse1,
            'adresse2': org.adresse2,
            'code_postal': org.code_postal,
            'localite': org.localite,
            'province': org.province,
            'nif': org.nif,
            'stat': org.stat,
            'numero_cnaps': org.numero_cnaps,
            'tarif_carte_sociale': str(org.tarif_carte_sociale) if org.tarif_carte_sociale else '',
            'tarif_demande': str(org.tarif_demande) if org.tarif_demande else '',
            'tarif_minimum_bp': str(org.tarif_minimum_bp) if org.tarif_minimum_bp else '',
            'tarif_devis_bp': str(org.tarif_devis_bp) if org.tarif_devis_bp else '',
            'tarif_metre_supplementaire': str(org.tarif_metre_supplementaire) if org.tarif_metre_supplementaire else '',
            'plafond_soins_simples': str(org.plafond_soins_simples) if org.plafond_soins_simples else '',
            'plafond_lunettes': str(org.plafond_lunettes) if org.plafond_lunettes else '',
            'bases_count': org.bases_count,
            'comptes_count': org.comptes_count,
            'postes_count': org.postes_count,
            'affectations_count': org.affectations_count,
        })

    return JsonResponse(data, safe=False)


def api_bases(request, organisation_id):
    """API pour charger les bases d'une organisation"""
    bases = Base.objects.filter(
        organisation_id=organisation_id
    ).annotate(
        magasins_count=Count('magasins', distinct=True),
        journaux_count=Count('journaux', distinct=True),
        employes_count=Count('employes', distinct=True)
    ).select_related(
        'ouvrage_correspondant',
        'journal_retour',
        'compte_avance',
        'compte_indemnites',
        'compte_frais_deplacement',
        'compte_demande_bp',
        'compte_facture_volumetrique',
        'compte_conso_carte_sociale'
    ).order_by('nom_base')

    data = []
    for base in bases:
        data.append({
            'id': str(base.id),
            'nom_base': base.nom_base,
            'volet': base.volet,
            'telephone': base.telephone or '',
            'ouvrage_correspondant_id': str(base.ouvrage_correspondant.id) if base.ouvrage_correspondant else None,
            'prog_diamex': base.prog_diamex,
            'journal_retour_id': str(base.journal_retour.id) if base.journal_retour else None,
            'compte_avance_id': str(base.compte_avance.id) if base.compte_avance else None,
            'compte_indemnites_id': str(base.compte_indemnites.id) if base.compte_indemnites else None,
            'compte_frais_deplacement_id': str(base.compte_frais_deplacement.id) if base.compte_frais_deplacement else None,
            'compte_demande_bp_id': str(base.compte_demande_bp.id) if base.compte_demande_bp else None,
            'compte_facture_volumetrique_id': str(base.compte_facture_volumetrique.id) if base.compte_facture_volumetrique else None,
            'compte_conso_carte_sociale_id': str(base.compte_conso_carte_sociale.id) if base.compte_conso_carte_sociale else None,
            'magasins_count': base.magasins_count,
            'journaux_count': base.journaux_count,
            'employes_count': base.employes_count
        })

    return JsonResponse(data, safe=False)


def api_magasins(request, base_id):
    """API pour charger les magasins d'une base"""
    magasins = Magasin.objects.filter(
        base_id=base_id
    ).order_by('nom_magasin')

    data = []
    for magasin in magasins:
        data.append({
            'id': str(magasin.id),
            'nom_magasin': magasin.nom_magasin
        })

    return JsonResponse(data, safe=False)


def api_employes(request, base_id):
    """API pour charger les employés d'une base"""
    from apps.employees.models import Employe

    today = timezone.localdate()
    actifs_only = request.GET.get('actifs_only', 'true').lower() == 'true'

    employes = Employe.objects.filter(
        base_id=base_id
    ).annotate(
        ouvrages_count=Count('ouvrages_responsable', distinct=True)
    ).select_related('poste').order_by('nom_employe')

    if actifs_only:
        employes = employes.filter(
            models.Q(date_debauchage__isnull=True) |
            models.Q(date_debauchage__gte=today)
        )

    data = []
    for employe in employes:
        est_actif = employe.date_debauchage is None or employe.date_debauchage >= today
        data.append({
            'id': str(employe.id),
            'nom': employe.nom_employe,
            'surnom': employe.surnom,
            'poste': employe.poste.nom_poste if employe.poste else None,
            'poste_nom': employe.poste.nom_poste if employe.poste else None,
            'poste_id': str(employe.poste.id) if employe.poste else None,
            'nom_employe': employe.nom_employe,
            'prenom': employe.prenom,
            'date_embauche': employe.date_embauche.strftime('%Y-%m-%d') if employe.date_embauche else None,
            'date_debauchage': employe.date_debauchage.strftime('%Y-%m-%d') if employe.date_debauchage else None,
            'telephone': employe.telephone,
            'mail': employe.mail,
            'numero_cin': employe.numero_cin,
            'numero_cnaps': employe.numero_cnaps,
            'personnes_charge': employe.personnes_charge,
            'salarie': employe.salarie,
            'est_actif': est_actif,
            'ouvrages_count': employe.ouvrages_count
        })

    return JsonResponse(data, safe=False)


def api_employe_ouvrages(request, employe_id):
    """API pour charger les ouvrages responsables d'un employé"""
    from apps.employees.models import EmployeOuvrages
    from datetime import date

    responsabilites = EmployeOuvrages.objects.filter(
        employe_id=employe_id
    ).select_related('ouvrage').order_by('-date_debut')

    data = []
    for resp in responsabilites:
        est_actif = resp.date_fin is None or resp.date_fin >= date.today()

        data.append({
            'id': str(resp.id),
            'ouvrage_id': str(resp.ouvrage.id),
            'ouvrage_nom': resp.ouvrage.nom_ouvrage,
            'date_debut': resp.date_debut.strftime('%Y-%m-%d'),
            'date_fin': resp.date_fin.strftime('%Y-%m-%d') if resp.date_fin else None,
            'est_responsable_principal': resp.est_responsable_principal,
            'recevoir_alertes': resp.recevoir_alertes,
            'notes': resp.notes,
            'est_actif': est_actif
        })

    return JsonResponse(data, safe=False)


def api_employe_ouvrages_detail(request, resp_id):
    """API pour récupérer le détail d'une responsabilité"""
    from apps.employees.models import EmployeOuvrages

    try:
        resp = EmployeOuvrages.objects.select_related('employe', 'ouvrage').get(id=resp_id)

        data = {
            'id': str(resp.id),
            'employe_id': str(resp.employe.id),
            'ouvrage_id': str(resp.ouvrage.id),
            'date_debut': resp.date_debut.strftime('%Y-%m-%d'),
            'date_fin': resp.date_fin.strftime('%Y-%m-%d') if resp.date_fin else None,
            'est_responsable_principal': resp.est_responsable_principal,
            'recevoir_alertes': resp.recevoir_alertes,
            'notes': resp.notes
        }

        return JsonResponse(data)
    except EmployeOuvrages.DoesNotExist:
        return JsonResponse({'error': 'Responsabilité non trouvée'}, status=404)


def api_employe_ouvrages_create(request):
    """API pour créer une nouvelle responsabilité"""
    from apps.employees.models import EmployeOuvrages
    from datetime import datetime

    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    try:
        employe_id = request.POST.get('employe_id')
        ouvrage_id = request.POST.get('ouvrage_id')
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        est_responsable_principal = request.POST.get('est_responsable_principal') == 'on'
        recevoir_alertes = request.POST.get('recevoir_alertes') == 'on'
        notes = request.POST.get('notes')

        # Convertir les dates
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date() if date_fin_str else None

        # Créer la responsabilité
        resp = EmployeOuvrages.objects.create(
            employe_id=employe_id,
            ouvrage_id=ouvrage_id,
            date_debut=date_debut,
            date_fin=date_fin,
            est_responsable_principal=est_responsable_principal,
            recevoir_alertes=recevoir_alertes,
            notes=notes
        )

        return JsonResponse({
            'success': True,
            'id': str(resp.id)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def api_employe_ouvrages_update(request):
    """API pour mettre à jour une responsabilité"""
    from apps.employees.models import EmployeOuvrages
    from datetime import datetime

    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    try:
        resp_id = request.POST.get('id')
        ouvrage_id = request.POST.get('ouvrage_id')
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        est_responsable_principal = request.POST.get('est_responsable_principal') == 'on'
        recevoir_alertes = request.POST.get('recevoir_alertes') == 'on'
        notes = request.POST.get('notes')

        # Récupérer la responsabilité
        resp = EmployeOuvrages.objects.get(id=resp_id)

        # Mettre à jour les champs
        resp.ouvrage_id = ouvrage_id
        resp.date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        resp.date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date() if date_fin_str else None
        resp.est_responsable_principal = est_responsable_principal
        resp.recevoir_alertes = recevoir_alertes
        resp.notes = notes
        resp.save()

        return JsonResponse({
            'success': True,
            'id': str(resp.id)
        })
    except EmployeOuvrages.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Responsabilité non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def api_employe_ouvrages_delete(request):
    """API pour supprimer une responsabilité"""
    from apps.employees.models import EmployeOuvrages

    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    try:
        resp_id = request.POST.get('id')
        resp = EmployeOuvrages.objects.get(id=resp_id)
        resp.delete()

        return JsonResponse({'success': True})
    except EmployeOuvrages.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Responsabilité non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@employe_required
def ouvrage_assistant(request):
    """Assistant guidé de mise en service d'un ouvrage.

    Enchaîne en un seul écran : création/choix de l'ouvrage -> points d'eau ->
    modalité de gestion -> affectation du/des responsable(s). Ne remplace pas les
    pages existantes ; réutilise leurs endpoints.
    """
    gestionnaires = get_gestionnaire_organisations_queryset().order_by('nom_organisation')

    initial_ouvrage_id = request.GET.get('ouvrage') or ''
    if initial_ouvrage_id:
        try:
            if not Ouvrage.objects.filter(pk=initial_ouvrage_id).exists():
                initial_ouvrage_id = ''
        except (ValueError, ValidationError):
            initial_ouvrage_id = ''

    context = {
        'types_ouvrage': TypeOuvrage.objects.all().order_by('nom_type_ouvrage'),
        'gestionnaires': gestionnaires,
        'is_director': user_is_director(request.user),
        'initial_ouvrage_id': initial_ouvrage_id,
        'initial_mode': request.GET.get('mode') or '',
        'title': "Assistant nouvel ouvrage",
    }
    return render(request, 'organization/ouvrage_assistant.html', context)


@employe_required
def api_ouvrage_assistant_context(request, ouvrage_id):
    """État courant d'un ouvrage pour hydrater les étapes 2 à 4 de l'assistant."""
    from apps.billing.models import PointEau, ModaliteGestion
    from apps.employees.models import EmployeOuvrages

    ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

    modalite = (
        ModaliteGestion.objects
        .filter(ouvrage=ouvrage, date_fin__isnull=True)
        .exclude(type_gestion='pas_de_gestion')
        .select_related('gestionnaire', 'employe')
        .order_by('-date_debut')
        .first()
    )
    modalite_data = None
    if modalite:
        modalite_data = {
            'id': str(modalite.id),
            'type_gestion': modalite.type_gestion,
            'type_gestion_display': modalite.get_type_gestion_display(),
            'gestionnaire_id': str(modalite.gestionnaire_id) if modalite.gestionnaire_id else '',
            'gestionnaire_nom': modalite.gestionnaire.nom_organisation if modalite.gestionnaire else '',
            'employe_id': str(modalite.employe_id) if modalite.employe_id else '',
            'modalitepaiement': modalite.modalitepaiement or '',
            'date_debut': modalite.date_debut.strftime('%Y-%m-%d') if modalite.date_debut else '',
        }

    responsables = []
    for rel in (
        EmployeOuvrages.objects
        .filter(ouvrage=ouvrage, date_fin__isnull=True)
        .select_related('employe')
        .order_by('-est_responsable_principal', 'employe__nom')
    ):
        emp = rel.employe
        nom = (getattr(emp, 'surnom', None) or getattr(emp, 'nom', None) or str(emp.pk)) if emp else '-'
        responsables.append({
            'id': str(rel.id),
            'employe_id': str(rel.employe_id) if rel.employe_id else '',
            'employe_nom': nom,
            'est_responsable_principal': rel.est_responsable_principal,
            'date_debut': rel.date_debut.strftime('%Y-%m-%d') if rel.date_debut else '',
        })

    return JsonResponse({
        'success': True,
        'ouvrage': {
            'id': str(ouvrage.id),
            'nom_ouvrage': ouvrage.nom_ouvrage,
            'type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else '',
        },
        'points_eau_count': PointEau.objects.filter(ouvrage=ouvrage).count(),
        'modalite_active': modalite_data,
        'responsables': responsables,
        'is_director': user_is_director(request.user),
    })


def api_all_ouvrages(request):
    """API pour charger tous les ouvrages avec commune (pour autocomplétion)"""
    from apps.billing.models import PointEau

    # Récupérer les ouvrages avec leur premier point d'eau pour avoir la commune
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    data = []
    for ouvrage in ouvrages:
        # Récupérer le premier point d'eau pour obtenir la commune
        premier_pe = PointEau.objects.filter(
            ouvrage=ouvrage
        ).select_related(
            'parcelle__village__fokontany__commune'
        ).first()

        commune_nom = None
        if premier_pe and premier_pe.parcelle:
            village = premier_pe.parcelle.village
            if village and village.fokontany and village.fokontany.commune:
                commune_nom = village.fokontany.commune.nom_commune

        # Format: "Nom Ouvrage (Commune)" ou "Nom Ouvrage" si pas de commune
        label = ouvrage.nom_ouvrage
        if commune_nom:
            label = f"{ouvrage.nom_ouvrage} ({commune_nom})"

        data.append({
            'id': str(ouvrage.id),
            'nom_ouvrage': ouvrage.nom_ouvrage,
            'commune': commune_nom,
            'label': label  # Pour l'affichage dans l'autocomplétion
        })

    return JsonResponse(data, safe=False)


def api_journaux(request, base_id):
    """API pour charger les journaux d'une base"""
    journaux = Journal.objects.filter(
        base_id=base_id
    ).order_by('nom_journal')

    data = []
    for journal in journaux:
        data.append({
            'id': str(journal.id),
            'nom_journal': journal.nom_journal,
            'compte': journal.compte,
            'code': journal.code
        })

    return JsonResponse(data, safe=False)


def api_journaux_by_organisation(request, organisation_id):
    """API pour charger tous les journaux des bases d'une organisation"""
    journaux = Journal.objects.filter(
        base__organisation_id=organisation_id
    ).select_related('base').order_by('nom_journal')

    data = []
    for journal in journaux:
        data.append({
            'id': str(journal.id),
            'nom_journal': journal.nom_journal,
            'compte': journal.compte,
            'code': journal.code,
            'base_nom': journal.base.nom_base
        })

    return JsonResponse(data, safe=False)


def api_comptes(request, organisation_id):
    """API pour charger les comptes d'une organisation"""
    comptes = Compte.objects.filter(
        organisation_id=organisation_id
    ).select_related('nature_declaration').order_by('nom_compte')

    data = []
    for compte in comptes:
        data.append({
            'id': str(compte.id),
            'nom_compte': compte.nom_compte,
            'compte': compte.compte,
            'detail': compte.detail,
            'financement': compte.financement,
            'financement_label': compte.get_financement_display(),
            'a_recouper_hydria_diamex': compte.a_recouper_hydria_diamex,
            'achat': compte.achat,
            'employe_obligatoire': compte.employe_obligatoire,
            'fournisseur_obligatoire': compte.fournisseur_obligatoire,
            'necessite_ouvrage': compte.necessite_ouvrage,
            'nature_declaration_id': str(compte.nature_declaration.id) if compte.nature_declaration else None,
            'nature_declaration_nom': compte.nature_declaration.nom if compte.nature_declaration else None
        })

    return JsonResponse(data, safe=False)


def api_postes(request, organisation_id):
    """API pour charger les postes d'une organisation"""
    postes = Poste.objects.filter(
        organisation_id=organisation_id
    ).order_by('ordre_affichage', 'nom_poste')

    data = []
    for poste in postes:
        data.append({
            'id': str(poste.id),
            'nom_poste': poste.nom_poste,
            'tarif_indemnite': float(poste.tarif_indemnite) if poste.tarif_indemnite else None,
            'prefixe': poste.prefixe,
            'compte_salaire': str(poste.compte_salaire.id) if poste.compte_salaire else None,
            'compte_salaire_nom': poste.compte_salaire.nom_compte if poste.compte_salaire else None,
            'compte_irsa': str(poste.compte_irsa.id) if poste.compte_irsa else None,
            'compte_irsa_nom': poste.compte_irsa.nom_compte if poste.compte_irsa else None,
            'compte_cnaps_fmfp_sante': str(poste.compte_cnaps_fmfp_sante.id) if poste.compte_cnaps_fmfp_sante else None,
            'compte_cnaps_nom': poste.compte_cnaps_fmfp_sante.nom_compte if poste.compte_cnaps_fmfp_sante else None,
            'compte_indemnite': str(poste.compte_indemnite.id) if poste.compte_indemnite else None,
            'compte_indemnite_nom': poste.compte_indemnite.nom_compte if poste.compte_indemnite else None,
        })

    return JsonResponse(data, safe=False)


def api_create(request):
    """API pour créer un nouvel élément"""
    if request.method == 'POST':
        item_type = request.POST.get('type')

        try:
            if item_type == 'organisation':
                data = _normalize_cascade_form_data(item_type, request.POST)
                form = OrganisationForm(data, request.FILES)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'base':
                # Créer la base avec l'organisation parente
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                data['organisation'] = organisation_id

                form = BaseForm(data)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'magasin':
                # Créer le magasin avec la base parente
                base_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                data['base'] = base_id

                form = MagasinForm(data)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'journal':
                # Créer le journal avec la base parente
                base_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                data['base'] = base_id

                form = JournalForm(data)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'compte':
                # Créer le compte avec l'organisation parente
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                data['organisation'] = organisation_id

                form = CompteForm(data)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'poste':
                # Créer le poste avec l'organisation parente
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                data['organisation'] = organisation_id

                form = PosteForm(data)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


def api_update(request):
    """API pour modifier un élément"""
    if request.method == 'POST':
        item_type = request.POST.get('type')
        item_id = request.POST.get('id')

        try:
            if item_type == 'organisation':
                organisation = get_object_or_404(Organisation, pk=item_id)
                data = _normalize_cascade_form_data(item_type, request.POST)
                form = OrganisationForm(data, request.FILES, instance=organisation)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'base':
                base = get_object_or_404(Base, pk=item_id)
                # Assurer que l'organisation parente est définie
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                if organisation_id:
                    data['organisation'] = organisation_id

                form = BaseForm(data, instance=base)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'magasin':
                magasin = get_object_or_404(Magasin, pk=item_id)
                # Gestion automatique de la base pour les magasins
                base_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                if base_id:
                    data['base'] = base_id

                form = MagasinForm(data, instance=magasin)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'journal':
                journal = get_object_or_404(Journal, pk=item_id)
                # Gestion automatique de la base pour les journaux
                base_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                if base_id:
                    data['base'] = base_id

                form = JournalForm(data, instance=journal)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'compte':
                compte = get_object_or_404(Compte, pk=item_id)
                # Gestion automatique de l'organisation pour les comptes
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                if organisation_id:
                    data['organisation'] = organisation_id

                # Si le navigateur n'a pas pu charger les options, le select est
                # désactivé et absent du POST. Préserver alors la valeur existante.
                if 'nature_declaration' not in data:
                    data['nature_declaration'] = str(compte.nature_declaration_id or '')

                # Debug: afficher les données reçues
                print(f"🔍 Backend - Mise à jour compte {compte.nom_compte} (ID: {item_id})")
                print(f"📥 Données POST reçues:")
                for key, value in data.items():
                    print(f"  {key}: {value}")

                form = CompteForm(data, instance=compte)
                if form.is_valid():
                    compte_updated = form.save()
                    print(f"✅ Compte sauvegardé: employe_obligatoire={compte_updated.employe_obligatoire}")
                    return JsonResponse({'success': True})
                else:
                    print(f"❌ Erreurs de validation: {form.errors}")
                    return JsonResponse({'success': False, 'errors': form.errors})

            elif item_type == 'poste':
                poste = get_object_or_404(Poste, pk=item_id)
                # Gestion automatique de l'organisation pour les postes
                organisation_id = request.POST.get('parent_id')
                data = _normalize_cascade_form_data(item_type, request.POST)
                if organisation_id:
                    data['organisation'] = organisation_id

                form = PosteForm(data, instance=poste)
                if form.is_valid():
                    form.save()
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'errors': form.errors})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


def api_delete(request):
    """API pour supprimer un élément"""
    if request.method == 'POST':
        item_type = request.POST.get('type')
        item_id = request.POST.get('id')

        try:
            if item_type == 'organisation':
                organisation = get_object_or_404(Organisation, pk=item_id)
                organisation.delete()
                return JsonResponse({'success': True})

            elif item_type == 'base':
                base = get_object_or_404(Base, pk=item_id)
                base.delete()
                return JsonResponse({'success': True})

            elif item_type == 'magasin':
                magasin = get_object_or_404(Magasin, pk=item_id)
                magasin.delete()
                return JsonResponse({'success': True})

            elif item_type == 'journal':
                journal = get_object_or_404(Journal, pk=item_id)
                journal.delete()
                return JsonResponse({'success': True})

            elif item_type == 'compte':
                compte = get_object_or_404(Compte, pk=item_id)
                compte.delete()
                return JsonResponse({'success': True})

            elif item_type == 'poste':
                poste = get_object_or_404(Poste, pk=item_id)
                poste.delete()
                return JsonResponse({'success': True})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


# ===== GESTION DES POINTS DE CONTRÔLE POUR POINTS D'EAU =====

def point_eau_controles_list(request, point_id):
    """API pour lister les points de contrôle d'un point d'eau"""
    from apps.billing.models import PointEau, PointEauControle
    from apps.inspections.models import PointDeControle

    try:
        point_eau = get_object_or_404(PointEau, pk=point_id)
        controles = PointEauControle.objects.filter(
            point_eau=point_eau,
            actif=True
        ).select_related('point_de_controle').order_by('ordre')

        data = []
        for controle in controles:
            pc = controle.point_de_controle
            data.append({
                'id': str(controle.id),
                'point_de_controle_id': str(pc.id),
                'nom': pc.nom,
                'description': pc.description,
                'type_resultat': pc.get_type_resultat_display(),
                'valeur_min': str(pc.valeur_min) if pc.valeur_min else '',
                'valeur_max': str(pc.valeur_max) if pc.valeur_max else '',
                'unite': pc.unite or '',
                'ordre': controle.ordre,
                'est_obligatoire': controle.est_obligatoire,
                'frequence_jours': controle.frequence_jours,
                'derniere_verification': controle.derniere_verification.strftime('%d/%m/%Y %H:%M') if controle.derniere_verification else 'Jamais',
                'notes': controle.notes,
                'est_en_retard': controle.est_en_retard
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'point_eau_nom': point_eau.nomabonne
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def point_eau_controle_create(request, point_id):
    """Créer un nouveau point de contrôle pour un point d'eau"""
    from apps.billing.models import PointEau, PointEauControle
    from apps.inspections.models import PointDeControle

    if request.method == 'POST':
        try:
            point_eau = get_object_or_404(PointEau, pk=point_id)
            point_de_controle_id = request.POST.get('point_de_controle')

            if not point_de_controle_id:
                return JsonResponse({'success': False, 'error': 'Point de contrôle requis'})

            point_de_controle = get_object_or_404(PointDeControle, pk=point_de_controle_id)

            # Vérifier si ce point de contrôle n'est pas déjà assigné
            if PointEauControle.objects.filter(point_eau=point_eau, point_de_controle=point_de_controle).exists():
                return JsonResponse({'success': False, 'error': 'Ce point de contrôle est déjà assigné à ce point d\'eau'})

            # Déterminer l'ordre suivant
            max_ordre = PointEauControle.objects.filter(point_eau=point_eau).aggregate(
                models.Max('ordre')
            )['ordre__max'] or 0

            controle = PointEauControle.objects.create(
                point_eau=point_eau,
                point_de_controle=point_de_controle,
                ordre=max_ordre + 1,
                est_obligatoire=request.POST.get('est_obligatoire') == 'on',
                frequence_jours=request.POST.get('frequence_jours') or None,
                notes=request.POST.get('notes', '')
            )

            return JsonResponse({
                'success': True,
                'message': 'Point de contrôle ajouté avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    elif request.method == 'GET':
        # Retourner les composants du type de point d'eau disponibles
        from apps.inspections.models import ComposantTypePointEau
        from apps.billing.models import PointEau, PointEauControle

        point_eau = get_object_or_404(PointEau, pk=point_id)

        if not point_eau.type_point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Ce point d\'eau n\'a pas de type défini'
            })

        # Composants déjà assignés comme points de contrôle
        controles_assignes = PointEauControle.objects.filter(
            point_eau=point_eau
        ).values_list('composant_type_point_eau_id', flat=True)

        # Composants du type de point d'eau disponibles (non assignés)
        composants_disponibles = ComposantTypePointEau.objects.filter(
            type_point_eau=point_eau.type_point_eau
        ).exclude(
            id__in=controles_assignes
        ).order_by('ordre_affichage', 'nom_composant')

        composants = []
        for composant in composants_disponibles:
            composants.append({
                'id': str(composant.id),
                'nom_composant': composant.nom_composant,
                'description': composant.description,
                'ordre_affichage': composant.ordre_affichage,
                'est_obligatoire': composant.est_obligatoire
            })

        return JsonResponse({
            'success': True,
            'composants': composants,
            'point_eau_nom': point_eau.nomabonne,
            'type_point_eau': point_eau.type_point_eau.nom_type
        })

    return JsonResponse({'success': False})


def point_eau_controle_edit(request, controle_id):
    """Modifier un point de contrôle d'un point d'eau"""
    from apps.billing.models import PointEauControle

    if request.method == 'POST':
        try:
            controle = get_object_or_404(PointEauControle, pk=controle_id)

            controle.est_obligatoire = request.POST.get('est_obligatoire') == 'on'
            controle.frequence_jours = request.POST.get('frequence_jours') or None
            controle.notes = request.POST.get('notes', '')
            controle.save()

            return JsonResponse({
                'success': True,
                'message': 'Point de contrôle modifié avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    elif request.method == 'GET':
        try:
            controle = get_object_or_404(PointEauControle, pk=controle_id)

            data = {
                'id': str(controle.id),
                'point_de_controle_nom': controle.point_de_controle.nom,
                'point_de_controle_description': controle.point_de_controle.description,
                'est_obligatoire': controle.est_obligatoire,
                'frequence_jours': controle.frequence_jours,
                'notes': controle.notes,
                'ordre': controle.ordre
            }

            return JsonResponse({'success': True, 'data': data})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


def point_eau_controle_delete(request, controle_id):
    """Supprimer un point de contrôle d'un point d'eau"""
    from apps.billing.models import PointEauControle

    if request.method == 'POST':
        try:
            controle = get_object_or_404(PointEauControle, pk=controle_id)
            nom_controle = controle.point_de_controle.nom
            controle.delete()

            return JsonResponse({
                'success': True,
                'message': f'Point de contrôle "{nom_controle}" supprimé avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


# ===== GESTION DES POINTS DE CONTRÔLE POUR ÉQUIPEMENTS =====

def equipement_controles_list(request, equipement_id):
    """API pour lister les points de contrôle d'un équipement"""
    from apps.infrastructure.models import EquipementConstitutif, EquipementControle
    from apps.inspections.models import PointDeControle

    try:
        equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)
        controles = EquipementControle.objects.filter(
            equipement=equipement,
            actif=True
        ).select_related('point_de_controle').order_by('ordre')

        data = []
        for controle in controles:
            pc = controle.point_de_controle
            data.append({
                'id': str(controle.id),
                'point_de_controle_id': str(pc.id),
                'nom': pc.nom,
                'description': pc.description,
                'type_resultat': pc.get_type_resultat_display(),
                'valeur_min': str(pc.valeur_min) if pc.valeur_min else '',
                'valeur_max': str(pc.valeur_max) if pc.valeur_max else '',
                'unite': pc.unite or '',
                'ordre': controle.ordre,
                'est_obligatoire': controle.est_obligatoire,
                'frequence_jours': controle.frequence_jours,
                'derniere_verification': controle.derniere_verification.strftime('%d/%m/%Y %H:%M') if controle.derniere_verification else 'Jamais',
                'notes': controle.notes,
                'est_en_retard': controle.est_en_retard
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'equipement_nom': equipement.nom
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def equipement_controle_create(request, equipement_id):
    """Créer un nouveau point de contrôle pour un équipement"""
    from apps.infrastructure.models import EquipementConstitutif, EquipementControle
    from apps.inspections.models import PointDeControle

    if request.method == 'POST':
        try:
            equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)
            point_de_controle_id = request.POST.get('point_de_controle')

            if not point_de_controle_id:
                return JsonResponse({'success': False, 'error': 'Point de contrôle requis'})

            point_de_controle = get_object_or_404(PointDeControle, pk=point_de_controle_id)

            # Vérifier si ce point de contrôle n'est pas déjà assigné
            if EquipementControle.objects.filter(equipement=equipement, point_de_controle=point_de_controle).exists():
                return JsonResponse({'success': False, 'error': 'Ce point de contrôle est déjà assigné à cet équipement'})

            # Déterminer l'ordre suivant
            max_ordre = EquipementControle.objects.filter(equipement=equipement).aggregate(
                models.Max('ordre')
            )['ordre__max'] or 0

            controle = EquipementControle.objects.create(
                equipement=equipement,
                point_de_controle=point_de_controle,
                ordre=max_ordre + 1,
                est_obligatoire=request.POST.get('est_obligatoire') == 'on',
                frequence_jours=request.POST.get('frequence_jours') or None,
                notes=request.POST.get('notes', '')
            )

            return JsonResponse({
                'success': True,
                'message': 'Point de contrôle ajouté avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    elif request.method == 'GET':
        # Retourner les points de contrôle disponibles
        from apps.inspections.models import PointDeControle
        from apps.infrastructure.models import EquipementConstitutif, EquipementControle

        equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)

        # Points de contrôle déjà assignés
        controles_assignes = EquipementControle.objects.filter(
            equipement=equipement
        ).values_list('point_de_controle_id', flat=True)

        # Points de contrôle disponibles (non assignés)
        points_disponibles = PointDeControle.objects.exclude(
            id__in=controles_assignes
        ).order_by('nom')

        data = []
        for pc in points_disponibles:
            data.append({
                'id': str(pc.id),
                'nom': pc.nom,
                'description': pc.description,
                'type_resultat': pc.get_type_resultat_display(),
                'valeur_min': str(pc.valeur_min) if pc.valeur_min else '',
                'valeur_max': str(pc.valeur_max) if pc.valeur_max else '',
                'unite': pc.unite or ''
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'equipement_nom': equipement.nom
        })

    return JsonResponse({'success': False})


def equipement_controle_edit(request, controle_id):
    """Modifier un point de contrôle d'un équipement"""
    from apps.infrastructure.models import EquipementControle

    if request.method == 'POST':
        try:
            controle = get_object_or_404(EquipementControle, pk=controle_id)

            controle.est_obligatoire = request.POST.get('est_obligatoire') == 'on'
            controle.frequence_jours = request.POST.get('frequence_jours') or None
            controle.notes = request.POST.get('notes', '')
            controle.save()

            return JsonResponse({
                'success': True,
                'message': 'Point de contrôle modifié avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    elif request.method == 'GET':
        try:
            controle = get_object_or_404(EquipementControle, pk=controle_id)

            data = {
                'id': str(controle.id),
                'point_de_controle_nom': controle.point_de_controle.nom,
                'point_de_controle_description': controle.point_de_controle.description,
                'est_obligatoire': controle.est_obligatoire,
                'frequence_jours': controle.frequence_jours,
                'notes': controle.notes,
                'ordre': controle.ordre
            }

            return JsonResponse({'success': True, 'data': data})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


def equipement_controle_delete(request, controle_id):
    """Supprimer un point de contrôle d'un équipement"""
    from apps.infrastructure.models import EquipementControle

    if request.method == 'POST':
        try:
            controle = get_object_or_404(EquipementControle, pk=controle_id)
            nom_controle = controle.point_de_controle.nom
            controle.delete()

            return JsonResponse({
                'success': True,
                'message': f'Point de contrôle "{nom_controle}" supprimé avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False})


# ================================
# VUES CRUD POUR COMPOSANTS DES TYPES D'ÉQUIPEMENTS
# ================================

def composants_type_equipement_list(request, type_pk):
    """Liste des composants d'un type d'équipement."""
    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composants = ComposantTypeEquipement.objects.filter(type_equipement=type_equipement).order_by('ordre_affichage', 'nom_composant')

    return render(request, 'organization/composants_type_equipement_list.html', {
        'type_equipement': type_equipement,
        'composants': composants,
        'title': f'Composants - {type_equipement.nom_type}'
    })


def composant_type_equipement_create(request, type_pk):
    """Créer un nouveau composant pour un type d'équipement."""
    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)

    if request.method == 'POST':
        nom_composant = request.POST.get('nom_composant')
        description = request.POST.get('description', '')
        ordre_affichage = request.POST.get('ordre_affichage', 1)
        est_obligatoire = request.POST.get('est_obligatoire') == 'on'

        if nom_composant:
            ComposantTypeEquipement.objects.create(
                nom_composant=nom_composant,
                description=description,
                type_equipement=type_equipement,
                ordre_affichage=int(ordre_affichage),
                est_obligatoire=est_obligatoire
            )
            messages.success(request, f'Composant "{nom_composant}" créé avec succès.')
            return redirect('organization:composants_type_equipement_list', type_pk=type_pk)
        else:
            messages.error(request, 'Le nom du composant est obligatoire.')

    return render(request, 'organization/composant_type_equipement_form.html', {
        'type_equipement': type_equipement,
        'title': f'Nouveau composant - {type_equipement.nom_type}'
    })


def composant_type_equipement_edit(request, type_pk, composant_pk):
    """Modifier un composant d'un type d'équipement."""
    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk, type_equipement=type_equipement)

    if request.method == 'POST':
        nom_composant = request.POST.get('nom_composant')
        description = request.POST.get('description', '')
        ordre_affichage = request.POST.get('ordre_affichage', 1)
        est_obligatoire = request.POST.get('est_obligatoire') == 'on'

        if nom_composant:
            composant.nom_composant = nom_composant
            composant.description = description
            composant.ordre_affichage = int(ordre_affichage)
            composant.est_obligatoire = est_obligatoire
            composant.save()
            messages.success(request, f'Composant "{nom_composant}" modifié avec succès.')
            return redirect('organization:composants_type_equipement_list', type_pk=type_pk)
        else:
            messages.error(request, 'Le nom du composant est obligatoire.')

    return render(request, 'organization/composant_type_equipement_form.html', {
        'type_equipement': type_equipement,
        'composant': composant,
        'title': f'Modifier: {composant.nom_composant}'
    })


def composant_type_equipement_delete(request, type_pk, composant_pk):
    """Supprimer un composant d'un type d'équipement."""
    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk, type_equipement=type_equipement)

    if request.method == 'POST':
        nom_composant = composant.nom_composant
        composant.delete()
        messages.success(request, f'Composant "{nom_composant}" supprimé avec succès.')
        return redirect('organization:composants_type_equipement_list', type_pk=type_pk)

    return render(request, 'organization/composant_type_equipement_confirm_delete.html', {
        'type_equipement': type_equipement,
        'composant': composant,
        'title': f'Supprimer: {composant.nom_composant}'
    })


# ================================
# API ENDPOINTS POUR GESTION EN CASCADE DES ÉQUIPEMENTS
# ================================

def api_composants_type_equipement_list(request, type_pk):
    """API pour lister les composants d'un type d'équipement."""
    from django.db.models import Count

    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composants = ComposantTypeEquipement.objects.filter(
        type_equipement=type_equipement
    ).annotate(
        points_controle_count=Count('points_controle')
    ).order_by('ordre_affichage', 'nom_composant')

    composants_data = []
    for composant in composants:
        composants_data.append({
            'id': str(composant.id),
            'nom_composant': composant.nom_composant,
            'description': composant.description,
            'ordre_affichage': composant.ordre_affichage,
            'est_obligatoire': composant.est_obligatoire,
            'points_controle_count': composant.points_controle_count
        })

    return JsonResponse({
        'success': True,
        'composants': composants_data
    })


def api_composant_type_equipement_detail(request, type_pk, composant_pk):
    """API pour récupérer les détails d'un composant."""
    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk, type_equipement=type_equipement)

    return JsonResponse({
        'success': True,
        'composant': {
            'id': str(composant.id),
            'nom_composant': composant.nom_composant,
            'description': composant.description,
            'ordre_affichage': composant.ordre_affichage,
            'est_obligatoire': composant.est_obligatoire
        }
    })


def api_composant_type_equipement_create(request, type_pk):
    """API pour créer un nouveau composant."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)

    try:
        nom_composant = request.POST.get('nom_composant')
        description = request.POST.get('description', '')
        ordre_affichage = int(request.POST.get('ordre_affichage', 1))
        est_obligatoire = request.POST.get('est_obligatoire') == 'on'

        if not nom_composant:
            return JsonResponse({'success': False, 'message': 'Le nom du composant est obligatoire'})

        composant = ComposantTypeEquipement.objects.create(
            nom_composant=nom_composant,
            description=description,
            type_equipement=type_equipement,
            ordre_affichage=ordre_affichage,
            est_obligatoire=est_obligatoire
        )

        return JsonResponse({
            'success': True,
            'message': f'Composant "{nom_composant}" créé avec succès',
            'composant_id': str(composant.id)
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


def api_composant_type_equipement_edit(request, type_pk, composant_pk):
    """API pour modifier un composant."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk, type_equipement=type_equipement)

    try:
        nom_composant = request.POST.get('nom_composant')
        description = request.POST.get('description', '')
        ordre_affichage = int(request.POST.get('ordre_affichage', 1))
        est_obligatoire = request.POST.get('est_obligatoire') == 'on'

        if not nom_composant:
            return JsonResponse({'success': False, 'message': 'Le nom du composant est obligatoire'})

        composant.nom_composant = nom_composant
        composant.description = description
        composant.ordre_affichage = ordre_affichage
        composant.est_obligatoire = est_obligatoire
        composant.save()

        return JsonResponse({
            'success': True,
            'message': f'Composant "{nom_composant}" modifié avec succès'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


def api_composant_type_equipement_delete(request, type_pk, composant_pk):
    """API pour supprimer un composant."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    type_equipement = get_object_or_404(TypeEquipement, pk=type_pk)
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk, type_equipement=type_equipement)

    try:
        nom_composant = composant.nom_composant
        composant.delete()

        return JsonResponse({
            'success': True,
            'message': f'Composant "{nom_composant}" supprimé avec succès'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ========================================
# API ENDPOINTS POUR INSPECTION DE COMPOSANTS
# ========================================

def api_point_eau_composants_inspection(request, point_id):
    """API pour récupérer les composants d'inspection d'un point d'eau basés sur son type."""
    try:
        point_eau = get_object_or_404(PointEau, pk=point_id)

        if not point_eau.type_point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Ce point d\'eau n\'a pas de type défini'
            })

        # Récupérer les composants du type de point d'eau
        composants = ComposantTypePointEau.objects.filter(
            type_point_eau=point_eau.type_point_eau
        ).order_by('ordre_affichage', 'nom_composant')

        composants_data = []
        for composant in composants:
            # Simuler les données d'inspection (à remplacer par de vraies données ultérieurement)
            composants_data.append({
                'id': str(composant.id),
                'nom_composant': composant.nom_composant,
                'description': composant.description,
                'ordre_affichage': composant.ordre_affichage,
                'est_obligatoire': composant.est_obligatoire,
                'derniere_inspection': None,  # À implémenter avec les vraies inspections
                'conforme_derniere_inspection': None  # À implémenter avec les vraies inspections
            })

        return JsonResponse({
            'success': True,
            'point_eau_nom': point_eau.nomabonne,
            'type_point_eau': point_eau.type_point_eau.nom_type,
            'composants': composants_data,
            'historique_inspections': []  # À implémenter avec les vraies inspections
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors du chargement des composants: {str(e)}'
        })


def api_inspection_session_create(request, point_id):
    """API pour créer une nouvelle session d'inspection."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

    try:
        point_eau = get_object_or_404(PointEau, pk=point_id)

        date_inspection = request.POST.get('date_inspection')
        notes_generales = request.POST.get('notes_generales', '')

        if not date_inspection:
            return JsonResponse({'success': False, 'error': 'Date d\'inspection requise'})

        # Pour l'instant, juste confirmer la création (à implémenter vraiment plus tard)
        return JsonResponse({
            'success': True,
            'message': 'Session d\'inspection créée avec succès',
            'session_id': 'temp-session-id',  # À remplacer par vraie ID
            'date_inspection': date_inspection,
            'point_eau': point_eau.nomabonne
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la création de la session: {str(e)}'
        })


def api_composant_inspect(request, composant_id):
    """API pour enregistrer l'inspection d'un composant."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

    try:
        # Vérifier que le composant existe
        composant = get_object_or_404(ComposantTypePointEau, pk=composant_id)

        conforme = request.POST.get('conforme') == 'true'
        score_conformite = request.POST.get('score_conformite')
        observations = request.POST.get('observations', '')
        actions_correctives = request.POST.get('actions_correctives', '')
        photos = request.POST.get('photos', '')

        # Pour l'instant, juste confirmer l'enregistrement (à implémenter vraiment plus tard)
        return JsonResponse({
            'success': True,
            'message': f'Inspection du composant "{composant.nom_composant}" enregistrée avec succès',
            'composant': composant.nom_composant,
            'conforme': conforme,
            'score': score_conformite,
            'observations': observations
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de l\'enregistrement de l\'inspection: {str(e)}'
        })


# ============================
# API POINTS DE CONTRÔLE PAR COMPOSANT D'ÉQUIPEMENT
# ============================

def api_points_controle_composant_equipement_list(request, composant_pk):
    """API pour lister les points de contrôle d'un composant d'équipement."""
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk)

    # Récupérer les points de contrôle liés à ce composant
    points_controle_composant = PointDeControleComposant.objects.filter(
        composant_equipement=composant
    ).select_related('point_de_controle').order_by('ordre_affichage')

    points_controle_data = []
    for pcc in points_controle_composant:
        pc = pcc.point_de_controle
        points_controle_data.append({
            'id': str(pcc.id),
            'point_controle_id': str(pc.id),
            'nom': pc.nom,
            'description': pc.description,
            'type_resultat': pc.get_type_resultat_display(),
            'type_resultat_code': pc.type_resultat,
            'valeur_min': str(pc.valeur_min) if pc.valeur_min else None,
            'valeur_max': str(pc.valeur_max) if pc.valeur_max else None,
            'unite': pc.unite,
            'ordre_affichage': pcc.ordre_affichage,
            'est_obligatoire': pcc.est_obligatoire
        })

    return JsonResponse({
        'success': True,
        'points_controle': points_controle_data
    })


def api_point_controle_composant_equipement_create(request, composant_pk):
    """API pour ajouter un point de contrôle à un composant d'équipement."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk)

    try:
        point_controle_id = request.POST.get('point_de_controle')
        ordre_affichage = int(request.POST.get('ordre_affichage', 1))
        est_obligatoire = request.POST.get('est_obligatoire') == 'on'

        if not point_controle_id:
            return JsonResponse({'success': False, 'message': 'Le point de contrôle est obligatoire'})

        point_controle = get_object_or_404(PointDeControle, pk=point_controle_id)

        # Vérifier si ce point de contrôle n'est pas déjà associé
        if PointDeControleComposant.objects.filter(
            composant_equipement=composant,
            point_de_controle=point_controle
        ).exists():
            return JsonResponse({
                'success': False,
                'message': 'Ce point de contrôle est déjà associé à ce composant'
            })

        pcc = PointDeControleComposant.objects.create(
            point_de_controle=point_controle,
            composant_equipement=composant,
            ordre_affichage=ordre_affichage,
            est_obligatoire=est_obligatoire
        )

        return JsonResponse({
            'success': True,
            'message': f'Point de contrôle "{point_controle.nom}" ajouté avec succès',
            'point_controle_composant_id': str(pcc.id)
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


def api_point_controle_composant_equipement_edit(request, composant_pk, point_controle_pk):
    """API pour récupérer ou modifier un point de contrôle d'un composant d'équipement."""
    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk)
    pcc = get_object_or_404(PointDeControleComposant, pk=point_controle_pk, composant_equipement=composant)

    if request.method == 'GET':
        # Retourner les détails du point de contrôle
        return JsonResponse({
            'success': True,
            'point_controle': {
                'id': str(pcc.id),
                'point_controle_id': str(pcc.point_de_controle.id),
                'nom': pcc.point_de_controle.nom,
                'description': pcc.point_de_controle.description,
                'type_resultat': pcc.point_de_controle.type_resultat,
                'valeur_min': float(pcc.point_de_controle.valeur_min) if pcc.point_de_controle.valeur_min else None,
                'valeur_max': float(pcc.point_de_controle.valeur_max) if pcc.point_de_controle.valeur_max else None,
                'unite': pcc.point_de_controle.unite,
                'ordre_affichage': pcc.ordre_affichage,
                'est_obligatoire': pcc.est_obligatoire
            }
        })

    if request.method == 'POST':
        try:
            ordre_affichage = int(request.POST.get('ordre_affichage', 1))
            est_obligatoire = request.POST.get('est_obligatoire') == 'on'

            pcc.ordre_affichage = ordre_affichage
            pcc.est_obligatoire = est_obligatoire
            pcc.save()

            return JsonResponse({
                'success': True,
                'message': f'Point de contrôle "{pcc.point_de_controle.nom}" modifié avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def api_point_controle_composant_equipement_delete(request, composant_pk, point_controle_pk):
    """API pour supprimer un point de contrôle d'un composant d'équipement."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    composant = get_object_or_404(ComposantTypeEquipement, pk=composant_pk)
    pcc = get_object_or_404(PointDeControleComposant, pk=point_controle_pk, composant_equipement=composant)

    try:
        nom_point_controle = pcc.point_de_controle.nom
        pcc.delete()

        return JsonResponse({
            'success': True,
            'message': f'Point de contrôle "{nom_point_controle}" retiré avec succès'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ============================
# API POUR CHARGER TOUS LES POINTS DE CONTRÔLE (pour les sélecteurs)
# ============================

def api_points_controle_list(request):
    """API pour lister tous les points de contrôle disponibles."""
    points_controle = PointDeControle.objects.all().order_by('nom')

    points_controle_data = []
    for pc in points_controle:
        points_controle_data.append({
            'id': str(pc.id),
            'nom': pc.nom,
            'description': pc.description,
            'type_resultat': pc.get_type_resultat_display(),
            'type_resultat_code': pc.type_resultat,
            'valeur_min': str(pc.valeur_min) if pc.valeur_min else None,
            'valeur_max': str(pc.valeur_max) if pc.valeur_max else None,
            'unite': pc.unite
        })

    return JsonResponse({
        'success': True,
        'points_controle': points_controle_data
    })


def api_point_controle_detail(request, point_controle_id):
    """API pour récupérer les détails d'un point de contrôle."""
    point_controle = get_object_or_404(PointDeControle, pk=point_controle_id)

    return JsonResponse({
        'success': True,
        'point_controle': {
            'id': str(point_controle.id),
            'nom': point_controle.nom,
            'description': point_controle.description,
            'type_resultat': point_controle.get_type_resultat_display(),
            'type_resultat_code': point_controle.type_resultat,
            'valeur_min': str(point_controle.valeur_min) if point_controle.valeur_min else None,
            'valeur_max': str(point_controle.valeur_max) if point_controle.valeur_max else None,
            'unite': point_controle.unite
        }
    })


# ============================
# VUE CONSOLIDÉE OUVRAGES AVEC TARIFS
# ============================

def consolidated_ouvrages(request):
    """Page consolidée des ouvrages avec tarifs actifs (Région, District, Commune, Ouvrage, Tarifs, Tranches)"""
    from django.db.models import Q, Count, Prefetch
    from django.core.paginator import Paginator
    from apps.geography.models import Region, District, Commune
    from apps.billing.models import TarifVolumetrique, TarifVolumetrique2, TypePointEau
    from django.utils import timezone

    # Récupération des filtres
    search_query = request.GET.get('search', '').strip()
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    commune_filter = request.GET.get('commune', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    type_point_eau_filter = request.GET.get('type_point_eau', '')

    today = timezone.now().date()

    # Requête de base - Uniquement les tarifs actifs
    tarifs = TarifVolumetrique.objects.filter(
        actif=True,
        datedebuttarif__lte=today
    ).filter(
        Q(datefintarif__isnull=True) | Q(datefintarif__gte=today)
    ).select_related(
        'ouvrage__type_ouvrage',
        'type_point_eau'
    ).prefetch_related(
        'tranches_volumetriques'
    )

    # Appliquer les filtres de permissions
    tarifs = filter_queryset_by_permissions(tarifs, request.user)

    # Récupérer les colonnes de recherche sélectionnées
    search_columns = request.GET.getlist('search_columns')
    if not search_columns:
        search_columns = ['ouvrage', 'commune']

    # Appliquer la recherche sur les colonnes sélectionnées
    if search_query:
        search_filters = Q()
        if 'region' in search_columns:
            # Les ouvrages n'ont pas de lien direct avec la géographie, on filtre via points d'eau
            search_filters |= Q(ouvrage__pointeau__parcelle__village__fokontany__commune__district__region__nom_region__icontains=search_query)
        if 'district' in search_columns:
            search_filters |= Q(ouvrage__pointeau__parcelle__village__fokontany__commune__district__nom_district__icontains=search_query)
        if 'commune' in search_columns:
            search_filters |= Q(ouvrage__pointeau__parcelle__village__fokontany__commune__nom_commune__icontains=search_query)
        if 'ouvrage' in search_columns:
            search_filters |= Q(ouvrage__nom_ouvrage__icontains=search_query)
        if 'type_point_eau' in search_columns:
            search_filters |= Q(type_point_eau__nom_type__icontains=search_query)

        if search_filters:
            tarifs = tarifs.filter(search_filters).distinct()

    # Appliquer les filtres de navigation
    if ouvrage_filter and ouvrage_filter != 'all':
        tarifs = tarifs.filter(ouvrage_id=ouvrage_filter)

    if type_point_eau_filter and type_point_eau_filter != 'all':
        tarifs = tarifs.filter(type_point_eau_id=type_point_eau_filter)

    # Filtres géographiques via les points d'eau
    if region_filter and region_filter != 'all':
        tarifs = tarifs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune__district__region_id=region_filter).distinct()

    if district_filter and district_filter != 'all':
        tarifs = tarifs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune__district_id=district_filter).distinct()

    if commune_filter and commune_filter != 'all':
        tarifs = tarifs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune_id=commune_filter).distinct()

    # Tri
    tarifs = tarifs.order_by('ouvrage__nom_ouvrage', 'type_point_eau__nom_type')

    # Statistiques
    total_tarifs = tarifs.count()
    ouvrages_distincts = tarifs.values('ouvrage').distinct().count()
    types_point_eau_stats = tarifs.values('type_point_eau__nom_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # Pagination
    paginator = Paginator(tarifs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Listes pour les filtres
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')
    ouvrages = Ouvrage.objects.filter(tarifs_volumetriques__actif=True).distinct().order_by('nom_ouvrage')
    types_point_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')

    context = {
        'page_obj': page_obj,
        'tarifs': page_obj,
        'search_query': search_query,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'type_point_eau_filter': type_point_eau_filter,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'types_point_eau': types_point_eau,
        'total_tarifs': total_tarifs,
        'ouvrages_distincts': ouvrages_distincts,
        'search_columns': search_columns,
        'types_point_eau_stats': types_point_eau_stats,
    }

    return render(request, 'organization/consolidated_ouvrages.html', context)


# ============================
# ABAQUE DE FACTURATION EN MALGACHE
# ============================

def abaque_facturation(request):
    """Page de sélection pour générer un abaque de facturation en malgache"""
    from apps.billing.models import TarifVolumetrique, TypePointEau
    from django.utils import timezone
    from django.db.models import Q

    today = timezone.now().date()

    # Récupérer uniquement les ouvrages avec tarifs actifs
    ouvrages_avec_tarifs = Ouvrage.objects.filter(
        tarifs_volumetriques__actif=True,
        tarifs_volumetriques__datedebuttarif__lte=today
    ).filter(
        Q(tarifs_volumetriques__datefintarif__isnull=True) |
        Q(tarifs_volumetriques__datefintarif__gte=today)
    ).distinct().order_by('nom_ouvrage')

    # Appliquer les permissions
    ouvrages_avec_tarifs = filter_queryset_by_permissions(ouvrages_avec_tarifs, request.user)

    types_point_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')

    context = {
        'ouvrages': ouvrages_avec_tarifs,
        'types_point_eau': types_point_eau,
    }

    return render(request, 'organization/abaque_selection.html', context)


@require_http_methods(["GET"])
def api_ouvrage_types_point_eau(request, ouvrage_id):
    """API pour récupérer les types de points d'eau avec tarifs actifs pour un ouvrage"""
    from django.http import JsonResponse
    from apps.billing.models import TarifVolumetrique
    from django.utils import timezone
    from django.db.models import Q

    try:
        ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
        today = timezone.now().date()

        # Récupérer les types de points d'eau avec tarifs actifs pour cet ouvrage
        types_pe = TarifVolumetrique.objects.filter(
            ouvrage=ouvrage,
            actif=True,
            datedebuttarif__lte=today
        ).filter(
            Q(datefintarif__isnull=True) | Q(datefintarif__gte=today)
        ).select_related('type_point_eau').values(
            'type_point_eau__id',
            'type_point_eau__nom_type'
        ).distinct()

        # Formater les résultats
        types_list = [
            {
                'id': str(t['type_point_eau__id']),
                'nom_type': t['type_point_eau__nom_type']
            }
            for t in types_pe
        ]

        return JsonResponse({'types_point_eau': types_list})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def generate_abaque_pdf(request):
    """Génère l'abaque de facturation en PDF (malgache) jusqu'à 15m³"""
    from apps.billing.models import TarifVolumetrique, TarifVolumetrique2
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from django.utils import timezone
    from django.db.models import Q
    import decimal

    ouvrage_id = request.GET.get('ouvrage_id')
    type_point_eau_id = request.GET.get('type_point_eau_id')

    if not ouvrage_id or not type_point_eau_id:
        messages.error(request, 'Veuillez sélectionner un ouvrage et un type de point d\'eau')
        return redirect('organization:abaque_facturation')

    try:
        ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)
        today = timezone.now().date()

        # Récupérer le tarif actif
        tarif = TarifVolumetrique.objects.filter(
            ouvrage=ouvrage,
            type_point_eau_id=type_point_eau_id,
            actif=True,
            datedebuttarif__lte=today
        ).filter(
            Q(datefintarif__isnull=True) | Q(datefintarif__gte=today)
        ).select_related('type_point_eau').prefetch_related(
            'tranches_volumetriques'
        ).first()

        if not tarif:
            messages.error(request, 'Aucun tarif actif trouvé pour cette combinaison')
            return redirect('organization:abaque_facturation')

        # Récupérer l'organisation via la modalité de gestion active
        from apps.billing.models import ModaliteGestion
        from apps.employees.models import Employe

        modalite_active = ModaliteGestion.objects.filter(
            ouvrage=ouvrage,
            statut='actif'
        ).select_related('gestionnaire').first()

        organisation = modalite_active.gestionnaire if modalite_active else None

        # Récupérer le directeur de l'organisation (employé avec poste "Directeur")
        directeur = None
        if organisation:
            employes_actifs = Employe.objects.filter(
                base__organisation=organisation,
                date_debauchage__isnull=True  # Employé actif
            ).select_related('poste')

            # Priorité 1 : Directeur avec signature
            for emp in employes_actifs:
                if emp.poste and emp.poste.nom_poste == "Directeur" and emp.signature:
                    directeur = emp
                    break

            # Priorité 2 : Directeur sans signature
            if not directeur:
                for emp in employes_actifs:
                    if emp.poste and emp.poste.nom_poste == "Directeur":
                        directeur = emp
                        break

            # Priorité 3 : Tout poste de direction avec signature
            if not directeur:
                for emp in employes_actifs:
                    if emp.is_directeur and emp.signature:
                        directeur = emp
                        break

            # Priorité 4 : Tout poste de direction
            if not directeur:
                for emp in employes_actifs:
                    if emp.is_directeur:
                        directeur = emp
                        break

        # Calculer l'abaque de 0 à 15 m³
        abaque_data = []
        tranches_list = list(tarif.tranches_volumetriques.all().order_by('tranchesuperieur'))

        for volume_m3 in range(0, 16):  # 0 à 15 m³
            montant_total = decimal.Decimal(tarif.prixabonnement)
            montant_eau = decimal.Decimal(0)

            # Appliquer le volume minimum facturé
            volume_facture = max(
                decimal.Decimal(volume_m3),
                tarif.volume_minimum_facture or decimal.Decimal(0)
            )

            # Calculer le montant de l'eau selon les tranches progressives
            volume_restant = volume_facture
            tranches_details = []
            current_tranche_index = None
            limite_precedente = decimal.Decimal(0)

            for idx, tranche in enumerate(tranches_list):
                if volume_restant <= 0:
                    break

                # Calculer la taille de cette tranche (limite actuelle - limite précédente)
                limite_tranche = decimal.Decimal(tranche.tranchesuperieur)
                taille_tranche = limite_tranche - limite_precedente

                # Volume effectif dans cette tranche
                volume_tranche = min(volume_restant, taille_tranche)

                # Si le volume consommé n'atteint pas encore cette tranche, on skip
                if volume_facture <= limite_precedente:
                    break

                montant_tranche = volume_tranche * decimal.Decimal(tranche.tarif)
                montant_eau += montant_tranche

                # Déterminer la tranche active pour ce volume
                if volume_facture > 0 and current_tranche_index is None:
                    current_tranche_index = idx

                tranches_details.append({
                    'limite': tranche.tranchesuperieur,
                    'tarif': tranche.tarif,
                    'volume': float(volume_tranche),
                    'montant': float(montant_tranche)
                })

                volume_restant -= volume_tranche
                limite_precedente = limite_tranche

            montant_total += montant_eau

            # Arrondir le montant total à 100 Ar près
            montant_total_arrondi = (montant_total / 100).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP) * 100

            # Déterminer si on change de tranche à ce volume
            changement_tranche = False
            tranche_info = None
            for idx, tranche in enumerate(tranches_list):
                if volume_m3 > 0 and volume_m3 == int(tranche.tranchesuperieur):
                    changement_tranche = True
                    if idx + 1 < len(tranches_list):
                        tranche_info = tranches_list[idx + 1]
                    break

            abaque_data.append({
                'volume_m3': volume_m3,
                'volume_facture': float(volume_facture),
                'montant_abonnement': tarif.prixabonnement,
                'montant_eau': float(montant_eau),
                'montant_total': float(montant_total_arrondi),
                'tranches_details': tranches_details,
                'changement_tranche': changement_tranche,
                'nouvelle_tranche': tranche_info
            })

        context = {
            'ouvrage': ouvrage,
            'tarif': tarif,
            'abaque_data': abaque_data,
            'date_generation': timezone.now(),
            'organisation': organisation,
            'directeur': directeur,
        }

        return render(request, 'organization/abaque_pdf.html', context)

    except Exception as e:
        messages.error(request, f'Erreur lors de la génération de l\'abaque: {str(e)}')
        return redirect('organization:abaque_facturation')


def api_get_point_eau(request, point_eau_id):
    """API pour récupérer les détails d'un point d'eau"""
    try:
        from apps.billing.models import PointEau
        point_eau = PointEau.objects.select_related(
            'ouvrage',
            'type_point_eau',
            'parcelle__village__fokontany__commune'
        ).get(id=point_eau_id)

        data = {
            'id': str(point_eau.id),
            'nomabonne': point_eau.nomabonne or '',
            'code_point_eau': point_eau.code_point_eau or '',
            'idxls': point_eau.idxls or '',
            'tarifforfaitaire': float(point_eau.tarifforfaitaire) if point_eau.tarifforfaitaire else 0,
            'ouvrage': str(point_eau.ouvrage.id) if point_eau.ouvrage else None,
            'ouvrage_nom': point_eau.ouvrage.nom_ouvrage if point_eau.ouvrage else 'N/A',
            'type_point_eau_nom': point_eau.type_point_eau.nom_type if point_eau.type_point_eau else 'N/A',
            'village_nom': point_eau.parcelle.village.nom_village if point_eau.parcelle and point_eau.parcelle.village else 'N/A',
            'commune_nom': point_eau.parcelle.village.fokontany.commune.nom_commune if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune else 'N/A',
        }

        return JsonResponse(data)
    except PointEau.DoesNotExist:
        return JsonResponse({'error': 'Point d\'eau non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================================================
# GESTION DES TABLES AUTORISÉES POUR LES COMPTES
# ============================================================

@require_http_methods(["GET"])
def api_compte_tables(request, compte_id):
    """API pour lister les tables autorisées pour un compte."""
    try:
        compte = Compte.objects.get(id=compte_id)
        tables = CompteTable.objects.filter(compte=compte).order_by('nom_table')

        tables_data = [{
            'id': str(t.id),
            'nom_table': t.nom_table,
            'nom_table_display': t.get_nom_table_display(),
            'actif': t.actif,
            'date_creation': t.date_creation.strftime('%Y-%m-%d %H:%M'),
        } for t in tables]

        return JsonResponse({
            'success': True,
            'tables': tables_data,
            'compte': {
                'id': str(compte.id),
                'nom': compte.nom_compte,
                'numero': compte.compte or ''
            }
        })
    except Compte.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Compte non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_compte_table_create(request, compte_id):
    """API pour créer une relation compte-table."""
    try:
        data = json.loads(request.body)
        compte = Compte.objects.get(id=compte_id)

        nom_table = data.get('nom_table')
        if not nom_table:
            return JsonResponse({'success': False, 'error': 'Table requise'}, status=400)

        # Vérifier si la relation existe déjà
        if CompteTable.objects.filter(compte=compte, nom_table=nom_table).exists():
            return JsonResponse({'success': False, 'error': 'Cette table est déjà autorisée pour ce compte'}, status=400)

        compte_table = CompteTable.objects.create(
            compte=compte,
            nom_table=nom_table,
            actif=data.get('actif', True)
        )

        return JsonResponse({
            'success': True,
            'message': 'Table ajoutée avec succès',
            'compte_table': {
                'id': str(compte_table.id),
                'nom_table': compte_table.nom_table,
                'nom_table_display': compte_table.get_nom_table_display(),
                'actif': compte_table.actif
            }
        })
    except Compte.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Compte non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_compte_table_toggle(request, compte_table_id):
    """API pour activer/désactiver une relation compte-table."""
    try:
        compte_table = CompteTable.objects.get(id=compte_table_id)
        compte_table.actif = not compte_table.actif
        compte_table.save()

        return JsonResponse({
            'success': True,
            'message': f"Table {'activée' if compte_table.actif else 'désactivée'}",
            'actif': compte_table.actif
        })
    except CompteTable.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Relation non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_compte_table_delete(request, compte_table_id):
    """API pour supprimer une relation compte-table."""
    try:
        compte_table = CompteTable.objects.get(id=compte_table_id)
        nom_table_display = compte_table.get_nom_table_display()
        compte_table.delete()

        return JsonResponse({
            'success': True,
            'message': f"Table '{nom_table_display}' retirée"
        })
    except CompteTable.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Relation non trouvée'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _serialize_organigramme_graph_node(node_type, node, include_ouvrage=False):
    subtype_label = ''
    if node_type == 'equipement':
        subtype_label = getattr(getattr(node, 'type_equipement', None), 'nom_type', '') or ''
    elif node_type == 'point_eau':
        subtype_label = getattr(getattr(node, 'type_point_eau', None), 'nom_type', '') or ''
    payload = {
        'id': _build_organigram_node_value(node_type, node),
        'type': node_type,
        'label': _build_organigram_node_display_label(node_type, node, include_ouvrage=include_ouvrage),
        'ouvrage_id': str(getattr(node, 'ouvrage_id', '') or ''),
        'ouvrage_label': getattr(getattr(node, 'ouvrage', None), 'nom_ouvrage', '') or '',
        'photo_url': _get_organigram_node_photo_url(node_type, node),
        'photo_count': _get_organigram_node_photo_count(node_type, node),
        'subtype_label': subtype_label,
    }
    if node_type == 'point_eau':
        parcelle = getattr(node, 'parcelle', None)
        village = getattr(parcelle, 'village', None)
        fokontany = getattr(village, 'fokontany', None)
        commune = getattr(fokontany, 'commune', None)
        district = getattr(commune, 'district', None)
        region = getattr(district, 'region', None)
        payload.update({
            'commune_id': str(getattr(commune, 'pk', '') or ''),
            'commune_label': getattr(commune, 'nom_commune', '') or 'Sans commune',
            'district_id': str(getattr(district, 'pk', '') or ''),
            'district_label': getattr(district, 'nom_district', '') or 'Sans district',
            'region_id': str(getattr(region, 'pk', '') or ''),
            'region_label': getattr(region, 'nom_region', '') or 'Sans region',
        })
    return payload


def _message_doublon_code_point_eau(code, doublon=None):
    """Construit un message d'erreur explicite et actionnable lorsqu'un code de
    point d'eau est déjà utilisé ailleurs. Le code est unique dans TOUTE la base,
    pas seulement au sein d'un ouvrage."""
    from apps.billing.models import PointEau

    if doublon is None and code:
        doublon = (
            PointEau.objects
            .select_related('ouvrage', 'parcelle__village__fokontany__commune')
            .filter(code_point_eau=code)
            .first()
        )

    if doublon is None:
        return (
            f"Le code « {code} » est déjà utilisé par un autre point d'eau "
            "(le code doit être unique dans toute la base).\n\n"
            "Que faire :\n"
            f"• Point d'eau différent → saisissez un autre code (ex. « {code}-2 ») "
            "ou laissez le champ « Code du point d'eau » vide.\n"
            "• Même point d'eau déjà existant → ne le recréez pas, ouvrez-le "
            "depuis sa liste et modifiez-le."
        )

    ouvrage_nom = doublon.ouvrage.nom_ouvrage if doublon.ouvrage else 'sans ouvrage'
    village = commune = None
    parcelle = getattr(doublon, 'parcelle', None)
    if parcelle and parcelle.village:
        village = parcelle.village.nom_village
        try:
            commune = parcelle.village.fokontany.commune.nom_commune
        except AttributeError:
            commune = None
    lieu = ', '.join(part for part in (village, commune) if part)

    localisation = f"ouvrage « {ouvrage_nom} »"
    if lieu:
        localisation += f" ({lieu})"
    abonne = doublon.nomabonne or f"#{doublon.pk}"

    return (
        f"Le code « {code} » est déjà attribué à un autre point d'eau :\n"
        f"    {abonne} — {localisation}.\n\n"
        "Le code d'un point d'eau doit être unique dans TOUTE la base, "
        "pas uniquement dans cet ouvrage (il peut exister plusieurs ouvrages "
        "portant un nom voisin).\n\n"
        "Que faire :\n"
        f"• Si c'est un point d'eau différent : saisissez un autre code "
        f"(ex. « {code}-2 » ou un code propre à cet ouvrage) ou laissez le "
        "champ « Code du point d'eau » vide.\n"
        "• Si c'est le même point d'eau qui existe déjà : ne le recréez pas — "
        "ouvrez la fiche existante ci-dessus et modifiez-la."
    )


TYPES_POINT_EAU_INSTITUTIONNELS = ('bp', 'bf', 'pmh')


def _valider_abonne_et_institutionnel(type_point_eau_id, typeabonne, institutionnel, verifier_institutionnel=True):
    """Retourne un message d'erreur si le type d'abonné / le branchement
    institutionnel sont incompatibles avec le type de point d'eau, sinon None.

    - Type d'abonné : réservé au type Kiosque.
    - Branchement institutionnel : réservé aux types BP, BF ou PMH.
    Sans type de point d'eau renseigné, aucune restriction n'est appliquée.
    """
    if not type_point_eau_id:
        return None
    from apps.billing.models import TypePointEau
    type_pe = TypePointEau.objects.filter(pk=type_point_eau_id).first()
    if not type_pe:
        return None
    nom = (type_pe.nom_type or '').strip().lower()
    if typeabonne and nom != 'kiosque':
        return "Le type d'abonné n'est autorisé que pour un point d'eau de type Kiosque."
    if verifier_institutionnel and institutionnel and nom not in TYPES_POINT_EAU_INSTITUTIONNELS:
        return "Le branchement institutionnel n'est autorisé que pour les types BP, BF ou PMH."
    return None


def points_eau_create(request, ouvrage_id):
    """Créer un nouveau point d'eau avec liaison organigramme éventuelle."""
    from django.http import JsonResponse
    from django.utils.dateparse import parse_date

    ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    try:
        erreur_type = _valider_abonne_et_institutionnel(
            request.POST.get('type_point_eau'),
            request.POST.get('typeabonne', ''),
            request.POST.get('estbranchementinstitutionnel') == 'on',
        )
        if erreur_type:
            return JsonResponse({'success': False, 'message': erreur_type}, status=400)

        code_point_eau = request.POST.get('code_point_eau', '').strip()

        # Le code du point d'eau est unique dans toute la base : vérifier
        # explicitement pour renvoyer un message clair plutôt qu'une erreur 500.
        if code_point_eau:
            doublon = (
                PointEau.objects
                .select_related('ouvrage', 'parcelle__village__fokontany__commune')
                .filter(code_point_eau=code_point_eau)
                .first()
            )
            if doublon:
                return JsonResponse({
                    'success': False,
                    'code_doublon': True,
                    'message': _message_doublon_code_point_eau(code_point_eau, doublon),
                })

        nomabonne = request.POST.get('nomabonne')
        numeroteleph = request.POST.get('numeroteleph', '')
        contactabonne = request.POST.get('contactabonne', '')
        typeabonne = request.POST.get('typeabonne', '')
        type_point_eau_id = request.POST.get('type_point_eau')
        parcelle_id = request.POST.get('parcelle')
        datebranchement_str = request.POST.get('datebranchement')
        datearretbranchement_str = request.POST.get('datearretbranchement')
        tarifforfaitaire = request.POST.get('tarifforfaitaire')
        estbranchementinstitutionnel = request.POST.get('estbranchementinstitutionnel') == 'on'
        besoin_en_cloture = request.POST.get('besoin_en_cloture') == 'on'

        amont_node_value = request.POST.get('amont_node', '').strip()
        legacy_compteur_id = request.POST.get('compteur_tete')
        if not amont_node_value and legacy_compteur_id:
            amont_node_value = f'compteur:{legacy_compteur_id}'

        amont_type, amont_node = _resolve_organigram_node(
            ouvrage,
            amont_node_value,
            allow_point=True,
        ) if amont_node_value else (None, None)

        datebranchement = None
        datearretbranchement = None
        if datebranchement_str:
            date_obj = parse_date(datebranchement_str)
            if date_obj:
                datebranchement = datetime.combine(date_obj, datetime.min.time())
        if datearretbranchement_str:
            date_obj = parse_date(datearretbranchement_str)
            if date_obj:
                datearretbranchement = datetime.combine(date_obj, datetime.min.time())

        nombre_consommateurs = request.POST.get('nombre_consommateurs')
        nombre_menages_consommateurs = request.POST.get('nombre_menages_consommateurs')
        idxls = request.POST.get('idxls', '')

        numerodiamexdemande = request.POST.get('numerodiamexdemande')
        numerodiamexdevis = request.POST.get('numerodiamexdevis')
        basediamexdemande = request.POST.get('basediamexdemande')
        basediamexdevis = request.POST.get('basediamexdevis')
        datepaiementdemande_str = request.POST.get('datepaiementdemande')
        datepaiementdevis_str = request.POST.get('datepaiementdevis')
        montantdemandepaye = request.POST.get('montantdemandepaye')
        montantdevispaye = request.POST.get('montantdevispaye')

        datepaiementdemande = None
        datepaiementdevis = None
        if datepaiementdemande_str:
            date_obj = parse_date(datepaiementdemande_str)
            if date_obj:
                datepaiementdemande = datetime.combine(date_obj, datetime.min.time())
        if datepaiementdevis_str:
            date_obj = parse_date(datepaiementdevis_str)
            if date_obj:
                datepaiementdevis = datetime.combine(date_obj, datetime.min.time())

        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')

        import json
        photos_json = request.POST.get('photos_json', '[]')
        try:
            photos = json.loads(photos_json) if photos_json else []
        except json.JSONDecodeError:
            photos = []

        with transaction.atomic():
            modification_time = timezone.now()
            point = PointEau.objects.create(
                code_point_eau=code_point_eau or None,
                nomabonne=nomabonne,
                numeroteleph=numeroteleph,
                contactabonne=contactabonne,
                typeabonne=typeabonne,
                ouvrage=ouvrage,
                type_point_eau_id=type_point_eau_id if type_point_eau_id else None,
                compteur_tete=amont_node if amont_type == 'compteur' else None,
                parcelle_id=parcelle_id if parcelle_id else None,
                datebranchement=datebranchement,
                datearretbranchement=datearretbranchement,
                **champs_tarif_depuis_post(request.POST),
                estbranchementinstitutionnel=estbranchementinstitutionnel,
                nombre_consommateurs=int(nombre_consommateurs) if nombre_consommateurs else None,
                nombre_menages_consommateurs=int(nombre_menages_consommateurs) if nombre_menages_consommateurs else None,
                idxls=idxls,
                numerodiamexdemande=int(numerodiamexdemande) if numerodiamexdemande else None,
                numerodiamexdevis=int(numerodiamexdevis) if numerodiamexdevis else None,
                basediamexdemande=basediamexdemande if basediamexdemande else None,
                basediamexdevis=basediamexdevis if basediamexdevis else None,
                datepaiementdemande=datepaiementdemande,
                datepaiementdevis=datepaiementdevis,
                montantdemandepaye=float(montantdemandepaye) if montantdemandepaye else None,
                montantdevispaye=float(montantdevispaye) if montantdevispaye else None,
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                photos=photos,
                besoin_en_cloture=besoin_en_cloture,
                createdat=modification_time,
                updatedat=modification_time,
                updated_by=getattr(request.user, 'employe', None),
            )
            _replace_inbound_liaison(ouvrage, 'point_eau', point, amont_type, amont_node)

        return JsonResponse({
            'success': True,
            'message': f'Point d\'eau "{nomabonne}" créé avec succès',
            'redirect': f'/organisations/points-eau/{ouvrage_id}/'
        })
    except IntegrityError:
        return JsonResponse({
            'success': False,
            'code_doublon': True,
            'message': _message_doublon_code_point_eau(code_point_eau),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création : {str(e)}'
        }, status=500)


def points_eau_edit(request, point_id):
    """Modifier un point d'eau avec liaison organigramme éventuelle."""
    from django.http import JsonResponse
    from django.utils.dateparse import parse_date

    point = get_object_or_404(PointEau, pk=point_id)

    if request.method == 'POST':
        try:
            erreur_type = _valider_abonne_et_institutionnel(
                request.POST.get('type_point_eau'),
                request.POST.get('typeabonne', ''),
                request.POST.get('estbranchementinstitutionnel') == 'on',
                # L'édition rapide ne transmet pas ce champ : ne pas le contrôler.
                verifier_institutionnel=request.POST.get('quick_edit') != '1',
            )
            if erreur_type:
                return JsonResponse({'success': False, 'message': erreur_type}, status=400)

            # Le code du point d'eau est unique dans toute la base : vérifier
            # explicitement pour renvoyer un message clair plutôt qu'une erreur 500.
            code_saisi = request.POST.get('code_point_eau', '').strip()
            if code_saisi:
                doublon = (
                    PointEau.objects
                    .select_related('ouvrage', 'parcelle__village__fokontany__commune')
                    .filter(code_point_eau=code_saisi)
                    .exclude(pk=point.pk)
                    .first()
                )
                if doublon:
                    return JsonResponse({
                        'success': False,
                        'code_doublon': True,
                        'message': _message_doublon_code_point_eau(code_saisi, doublon),
                    })

            amont_node_value = request.POST.get('amont_node', '').strip()
            legacy_compteur_id = request.POST.get('compteur_tete')
            if not amont_node_value and legacy_compteur_id:
                amont_node_value = f'compteur:{legacy_compteur_id}'

            amont_type, amont_node = _resolve_organigram_node(
                point.ouvrage,
                amont_node_value,
                allow_point=True,
            ) if amont_node_value else (None, None)

            point.updatedat = timezone.now()
            employe = getattr(request.user, 'employe', None)
            if employe:
                point.updated_by = employe

            # Edition rapide depuis la page des releves : ne modifier que les
            # champs affiches dans la modale afin de preserver les donnees
            # techniques, financieres, GPS et les photos du point d'eau.
            if request.POST.get('quick_edit') == '1':
                point.code_point_eau = request.POST.get('code_point_eau', '').strip() or None
                point.nomabonne = request.POST.get('nomabonne', '').strip()
                point.numeroteleph = request.POST.get('numeroteleph', '').strip()
                point.typeabonne = request.POST.get('typeabonne', '')
                point.type_point_eau_id = request.POST.get('type_point_eau') or None
                point.parcelle_id = request.POST.get('parcelle') or None
                point.idxls = request.POST.get('idxls', '').strip()
                point.compteur_tete = amont_node if amont_type == 'compteur' else None

                datebranchement_str = request.POST.get('datebranchement')
                point.datebranchement = (
                    datetime.combine(parse_date(datebranchement_str), datetime.min.time())
                    if datebranchement_str and parse_date(datebranchement_str)
                    else None
                )

                with transaction.atomic():
                    point.save()
                    _replace_inbound_liaison(point.ouvrage, 'point_eau', point, amont_type, amont_node)

                return JsonResponse({
                    'success': True,
                    'message': f'Point d\'eau "{point.nomabonne}" modifie avec succes',
                })

            point.code_point_eau = request.POST.get('code_point_eau', '').strip() or None
            point.nomabonne = request.POST.get('nomabonne')
            point.numeroteleph = request.POST.get('numeroteleph', '')
            point.contactabonne = request.POST.get('contactabonne', '')
            point.typeabonne = request.POST.get('typeabonne', '')
            point.type_point_eau_id = request.POST.get('type_point_eau') or None
            point.compteur_tete = amont_node if amont_type == 'compteur' else None
            point.parcelle_id = request.POST.get('parcelle') or None

            datebranchement_str = request.POST.get('datebranchement')
            point.datebranchement = datetime.combine(parse_date(datebranchement_str), datetime.min.time()) if datebranchement_str and parse_date(datebranchement_str) else None

            # datearretbranchement géré par le workflow de coupure : ne pas l'écraser
            # (le champ du modal est disabled, donc absent du POST).

            tarifforfaitaire = request.POST.get('tarifforfaitaire')
            for _champ, _valeur in champs_tarif_depuis_post(request.POST).items():
                setattr(point, _champ, _valeur)
            point.estbranchementinstitutionnel = request.POST.get('estbranchementinstitutionnel') == 'on'
            point.besoin_en_cloture = request.POST.get('besoin_en_cloture') == 'on'

            nombre_consommateurs = request.POST.get('nombre_consommateurs')
            point.nombre_consommateurs = int(nombre_consommateurs) if nombre_consommateurs else None
            nombre_menages_consommateurs = request.POST.get('nombre_menages_consommateurs')
            point.nombre_menages_consommateurs = int(nombre_menages_consommateurs) if nombre_menages_consommateurs else None
            point.idxls = request.POST.get('idxls', '')

            numerodiamexdemande = request.POST.get('numerodiamexdemande')
            point.numerodiamexdemande = int(numerodiamexdemande) if numerodiamexdemande else None
            numerodiamexdevis = request.POST.get('numerodiamexdevis')
            point.numerodiamexdevis = int(numerodiamexdevis) if numerodiamexdevis else None
            point.basediamexdemande = request.POST.get('basediamexdemande') or None
            point.basediamexdevis = request.POST.get('basediamexdevis') or None

            datepaiementdemande_str = request.POST.get('datepaiementdemande')
            point.datepaiementdemande = datetime.combine(parse_date(datepaiementdemande_str), datetime.min.time()) if datepaiementdemande_str and parse_date(datepaiementdemande_str) else None
            datepaiementdevis_str = request.POST.get('datepaiementdevis')
            point.datepaiementdevis = datetime.combine(parse_date(datepaiementdevis_str), datetime.min.time()) if datepaiementdevis_str and parse_date(datepaiementdevis_str) else None

            montantdemandepaye = request.POST.get('montantdemandepaye')
            point.montantdemandepaye = float(montantdemandepaye) if montantdemandepaye else None
            montantdevispaye = request.POST.get('montantdevispaye')
            point.montantdevispaye = float(montantdevispaye) if montantdevispaye else None

            latitude = request.POST.get('latitude')
            point.latitude = float(latitude) if latitude else None
            longitude = request.POST.get('longitude')
            point.longitude = float(longitude) if longitude else None

            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                point.photos = json.loads(photos_json) if photos_json else []
            except json.JSONDecodeError:
                pass

            with transaction.atomic():
                point.save()
                _replace_inbound_liaison(point.ouvrage, 'point_eau', point, amont_type, amont_node)

            return JsonResponse({
                'success': True,
                'message': f'Point d\'eau "{point.nomabonne}" modifié avec succès',
                'redirect': f'/organisations/points-eau/{point.ouvrage.pk}/'
            })
        except IntegrityError:
            return JsonResponse({
                'success': False,
                'code_doublon': True,
                'message': _message_doublon_code_point_eau(
                    request.POST.get('code_point_eau', '').strip()
                ),
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            }, status=500)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(point.pk),
                'code_point_eau': point.code_point_eau or '',
                'nomabonne': point.nomabonne or '',
                'numeroteleph': point.numeroteleph or '',
                'contactabonne': point.contactabonne or '',
                'typeabonne': point.typeabonne or '',
                'type_point_eau': str(point.type_point_eau.pk) if point.type_point_eau else '',
                'compteur_tete': str(point.compteur_tete.pk) if point.compteur_tete else '',
                'amont_node': _get_point_amont_token(point),
                'parcelle': str(point.parcelle.pk) if point.parcelle else '',
                'datebranchement': point.datebranchement.strftime('%Y-%m-%d') if point.datebranchement else '',
                'datearretbranchement': point.datearretbranchement.strftime('%Y-%m-%d') if point.datearretbranchement else '',
                'tarifforfaitaire': str(point.tarifforfaitaire) if point.tarifforfaitaire else '',
                'pourcentage_tarif': format(point.pourcentage_tarif.normalize(), 'f') if point.pourcentage_tarif is not None else '',
                'estbranchementinstitutionnel': point.estbranchementinstitutionnel,
                'nombre_consommateurs': str(point.nombre_consommateurs) if point.nombre_consommateurs else '',
                'nombre_menages_consommateurs': str(point.nombre_menages_consommateurs) if point.nombre_menages_consommateurs else '',
                'idxls': point.idxls or '',
                'numerodiamexdemande': str(point.numerodiamexdemande) if point.numerodiamexdemande else '',
                'numerodiamexdevis': str(point.numerodiamexdevis) if point.numerodiamexdevis else '',
                'basediamexdemande': str(point.basediamexdemande) if point.basediamexdemande else '',
                'basediamexdevis': str(point.basediamexdevis) if point.basediamexdevis else '',
                'datepaiementdemande': point.datepaiementdemande.strftime('%Y-%m-%d') if point.datepaiementdemande else '',
                'datepaiementdevis': point.datepaiementdevis.strftime('%Y-%m-%d') if point.datepaiementdevis else '',
                'montantdemandepaye': str(point.montantdemandepaye) if point.montantdemandepaye else '',
                'montantdevispaye': str(point.montantdevispaye) if point.montantdevispaye else '',
                'latitude': float(point.latitude) if point.latitude is not None else None,
                'longitude': float(point.longitude) if point.longitude is not None else None,
                'photos': point.photos if point.photos else [],
                'besoin_en_cloture': point.besoin_en_cloture,
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def _parse_equipement_volume_m3(request, type_equipement):
    """Retourne une capacité uniquement pour les équipements de type citerne."""
    from decimal import Decimal, InvalidOperation

    type_nom = (getattr(type_equipement, 'nom_type', '') or '').strip().lower()
    if type_nom != 'citerne':
        return None

    raw_value = request.POST.get('volume_m3', '').strip().replace(',', '.')
    if not raw_value:
        return None
    try:
        volume = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError('Le volume de la citerne doit être un nombre valide.') from exc
    if volume < 0:
        raise ValueError('Le volume de la citerne ne peut pas être négatif.')
    if volume % Decimal('0.5') != 0:
        raise ValueError('Le volume de la citerne doit être un multiple de 0,5 m³.')
    return volume


@employe_required
def api_ouvrage_equipements(request, ouvrage_id):
    """Liste JSON des equipements d'un ouvrage pour la fiche detail."""
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    ouvrage = get_object_or_404(ouvrages, pk=ouvrage_id)
    equipements = EquipementConstitutif.objects.filter(
        ouvrage=ouvrage
    ).select_related('type_equipement').order_by('nom')

    data = []
    for equipement in equipements:
        statut = equipement.statut or 'operationnel'
        type_nom = getattr(getattr(equipement, 'type_equipement', None), 'nom_type', '') or ''
        data.append({
            'id': str(equipement.pk),
            'nom': equipement.nom or '',
            'description': equipement.description or '',
            'type_equipement': type_nom,
            'type_equipement_display': type_nom or 'Non defini',
            'volume_m3': str(equipement.volume_m3) if equipement.volume_m3 is not None else '',
            'code_equipement': equipement.code_equipement or '',
            'statut': statut,
            'statut_display': equipement.get_statut_display() if hasattr(equipement, 'get_statut_display') else statut,
            'ouvrage_id': str(ouvrage.pk),
            'ouvrage_nom': ouvrage.nom_ouvrage,
        })

    return JsonResponse(data, safe=False)


def api_natures_declaration(request):
    """Liste locale des natures pour éviter la redirection vers compta.hydria.mg."""
    from apps.accounting.models import ConfigDeclarationCommunication

    natures = ConfigDeclarationCommunication.objects.order_by('ordre', 'nom')
    return JsonResponse({
        'success': True,
        'data': [
            {
                'id': str(nature.id),
                'nom': nature.nom,
                'actif': nature.actif,
            }
            for nature in natures
        ],
    })


def equipements_create(request, ouvrage_id):
    """Créer un nouvel équipement avec liaisons hydrauliques."""
    from django.http import JsonResponse

    ouvrage = get_object_or_404(Ouvrage, pk=ouvrage_id)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    try:
        type_equipement = None
        type_equipement_id = request.POST.get('type_equipement')
        if type_equipement_id:
            type_equipement = TypeEquipement.objects.get(pk=type_equipement_id)
        volume_m3 = _parse_equipement_volume_m3(request, type_equipement)

        import json
        photos_json = request.POST.get('photos_json', '[]')
        try:
            photos = json.loads(photos_json) if photos_json and photos_json.strip() else []
        except json.JSONDecodeError:
            photos = []

        if not photos:
            photos = None

        with transaction.atomic():
            equipement = EquipementConstitutif.objects.create(
                nom=request.POST.get('nom'),
                type_equipement=type_equipement,
                volume_m3=volume_m3,
                code_equipement=request.POST.get('code_equipement') or None,
                statut=request.POST.get('statut', 'operationnel'),
                description=request.POST.get('description', ''),
                ouvrage=ouvrage,
                date_installation=request.POST.get('date_installation') or None,
                derniere_maintenance=request.POST.get('derniere_maintenance') or None,
                nombre_nettoyages_annuels=int(request.POST.get('nombre_nettoyages_annuels')) if request.POST.get('nombre_nettoyages_annuels') else None,
                temps_acces_heures=float(request.POST.get('temps_acces_heures')) if request.POST.get('temps_acces_heures') else None,
                point_depart=request.POST.get('point_depart', ''),
                longueur_perimetre=int(request.POST.get('longueur_perimetre')) if request.POST.get('longueur_perimetre') else None,
                duree_nettoyage=float(request.POST.get('duree_nettoyage')) if request.POST.get('duree_nettoyage') else None,
                distance_materiaux_locaux=request.POST.get('distance_materiaux_locaux') or None,
                haie_vive_cultivable=request.POST.get('haie_vive_cultivable') == 'on',
                boite_a_vanne=request.POST.get('boite_a_vanne') == 'on',
                boite_a_vanne_utile=request.POST.get('boite_a_vanne_utile') == 'on',
                vanne_flotteur=request.POST.get('vanne_flotteur') == 'on',
                est_dans_village=request.POST.get('est_dans_village') == 'on',
                latitude=float(request.POST.get('latitude')) if request.POST.get('latitude') else None,
                longitude=float(request.POST.get('longitude')) if request.POST.get('longitude') else None,
                photos=photos,
            )
        return JsonResponse({
            'success': True,
            'message': f'Équipement "{equipement.nom}" créé avec succès',
            'redirect': f'/organisations/equipements/{ouvrage_id}/'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création : {str(e)}'
        }, status=500)


def equipements_edit(request, equipement_id):
    """Modifier un équipement avec liaisons hydrauliques."""
    from django.http import JsonResponse

    equipement = get_object_or_404(EquipementConstitutif, pk=equipement_id)

    if request.method == 'POST':
        try:
            type_equipement_id = request.POST.get('type_equipement')
            equipement.type_equipement = TypeEquipement.objects.get(pk=type_equipement_id) if type_equipement_id else None
            equipement.volume_m3 = _parse_equipement_volume_m3(request, equipement.type_equipement)
            equipement.nom = request.POST.get('nom')
            equipement.code_equipement = request.POST.get('code_equipement', '').strip() or None
            equipement.statut = request.POST.get('statut', 'operationnel')
            equipement.description = request.POST.get('description', '')
            equipement.date_installation = request.POST.get('date_installation') or None
            equipement.derniere_maintenance = request.POST.get('derniere_maintenance') or None
            equipement.nombre_nettoyages_annuels = int(request.POST.get('nombre_nettoyages_annuels')) if request.POST.get('nombre_nettoyages_annuels') else None
            equipement.temps_acces_heures = float(request.POST.get('temps_acces_heures')) if request.POST.get('temps_acces_heures') else None
            equipement.point_depart = request.POST.get('point_depart', '')
            equipement.longueur_perimetre = int(request.POST.get('longueur_perimetre')) if request.POST.get('longueur_perimetre') else None
            equipement.duree_nettoyage = float(request.POST.get('duree_nettoyage')) if request.POST.get('duree_nettoyage') else None
            equipement.distance_materiaux_locaux = request.POST.get('distance_materiaux_locaux', '')
            equipement.haie_vive_cultivable = request.POST.get('haie_vive_cultivable') == 'on'
            equipement.boite_a_vanne = request.POST.get('boite_a_vanne') == 'on'
            equipement.boite_a_vanne_utile = request.POST.get('boite_a_vanne_utile') == 'on'
            equipement.vanne_flotteur = request.POST.get('vanne_flotteur') == 'on'
            equipement.est_dans_village = request.POST.get('est_dans_village') == 'on'
            equipement.latitude = float(request.POST.get('latitude')) if request.POST.get('latitude') else None
            equipement.longitude = float(request.POST.get('longitude')) if request.POST.get('longitude') else None

            import json
            photos_json = request.POST.get('photos_json', '[]')
            try:
                equipement.photos = json.loads(photos_json) if photos_json else []
            except json.JSONDecodeError:
                pass

            with transaction.atomic():
                equipement.save()
            return JsonResponse({
                'success': True,
                'message': f'Équipement "{equipement.nom}" modifié avec succès',
                'redirect': f'/organisations/equipements/{equipement.ouvrage.pk}/'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            }, status=500)

    if request.method == 'GET':
        organigramme_data = _get_node_organigram_payload('equipement', equipement)
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(equipement.pk),
                'nom': equipement.nom or '',
                'type_equipement': str(equipement.type_equipement.pk) if equipement.type_equipement else '',
                'volume_m3': str(equipement.volume_m3) if equipement.volume_m3 is not None else '',
                'code_equipement': equipement.code_equipement or '',
                'statut': equipement.statut or 'operationnel',
                'description': equipement.description or '',
                'date_installation': equipement.date_installation.strftime('%Y-%m-%d') if equipement.date_installation else '',
                'derniere_maintenance': equipement.derniere_maintenance.strftime('%Y-%m-%d') if equipement.derniere_maintenance else '',
                'nombre_nettoyages_annuels': equipement.nombre_nettoyages_annuels or '',
                'temps_acces_heures': equipement.temps_acces_heures or '',
                'point_depart': equipement.point_depart or '',
                'longueur_perimetre': equipement.longueur_perimetre or '',
                'duree_nettoyage': equipement.duree_nettoyage or '',
                'distance_materiaux_locaux': equipement.distance_materiaux_locaux or '',
                'haie_vive_cultivable': equipement.haie_vive_cultivable or False,
                'boite_a_vanne': equipement.boite_a_vanne or False,
                'boite_a_vanne_utile': equipement.boite_a_vanne_utile or False,
                'vanne_flotteur': equipement.vanne_flotteur or False,
                'est_dans_village': equipement.est_dans_village or False,
                'latitude': str(equipement.latitude) if equipement.latitude is not None else '',
                'longitude': str(equipement.longitude) if equipement.longitude is not None else '',
                'photos': equipement.photos if equipement.photos else [],
                'amont_node': organigramme_data['amont_node'],
                'amont_label': organigramme_data['amont_label'],
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def compteurs_create(request, ouvrage_id):
    """Créer un compteur avec liaisons hydrauliques."""
    ouvrage = get_object_or_404(_get_allowed_ouvrages_for_user(request.user), pk=ouvrage_id)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    try:
        with transaction.atomic():
            compteur = CompteurTete.objects.create(
                ouvrage=ouvrage,
                numerocompteur=request.POST.get('numerocompteur'),
                marque=request.POST.get('marque') or None,
                modele=request.POST.get('modele') or None,
                date_installation=request.POST.get('date_installation') or None,
                index_initial=request.POST.get('index_initial', 0),
                statut=request.POST.get('statut', 'operationnel'),
            )
        return JsonResponse({
            'success': True,
            'message': f'Compteur "{compteur.numerocompteur}" créé avec succès',
            'redirect': f'/organisations/compteurs/{ouvrage_id}/'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création : {str(e)}'
        }, status=500)


def compteurs_edit(request, compteur_id):
    """Modifier un compteur avec liaisons hydrauliques."""
    allowed_ouvrages = _get_allowed_ouvrages_for_user(request.user)
    compteur = get_object_or_404(CompteurTete.objects.filter(ouvrage__in=allowed_ouvrages), pk=compteur_id)

    if request.method == 'POST':
        try:
            compteur.numerocompteur = request.POST.get('numerocompteur')
            compteur.marque = request.POST.get('marque') or None
            compteur.modele = request.POST.get('modele') or None
            compteur.date_installation = request.POST.get('date_installation') or None
            compteur.index_initial = request.POST.get('index_initial', 0)
            compteur.statut = request.POST.get('statut', 'operationnel')

            with transaction.atomic():
                compteur.save()
            return JsonResponse({
                'success': True,
                'message': f'Compteur "{compteur.numerocompteur}" modifié avec succès',
                'redirect': f'/organisations/compteurs/{compteur.ouvrage.pk}/'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la modification : {str(e)}'
            }, status=500)

    if request.method == 'GET':
        organigramme_data = _get_node_organigram_payload('compteur', compteur)
        return JsonResponse({
            'success': True,
            'data': {
                'id': str(compteur.pk),
                'numerocompteur': compteur.numerocompteur or '',
                'marque': compteur.marque or '',
                'modele': compteur.modele or '',
                'date_installation': compteur.date_installation.strftime('%Y-%m-%d') if compteur.date_installation else '',
                'index_initial': str(compteur.index_initial),
                'statut': compteur.statut,
                'amont_node': organigramme_data['amont_node'],
                'amont_label': organigramme_data['amont_label'],
            }
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def api_ouvrage_organigramme(request, ouvrage_id):
    """Retourne les noeuds et liaisons de l'organigramme hydraulique d'un ouvrage."""
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    ouvrage = get_object_or_404(ouvrages, pk=ouvrage_id)
    candidates = _get_organigramme_candidates(ouvrage)
    scope_ouvrage_ids = _get_organigramme_scope_ouvrage_ids(ouvrage)
    include_ouvrage = len(scope_ouvrage_ids) > 1

    nodes = []
    edges = []

    for equipement in candidates['equipements']:
        nodes.append(_serialize_organigramme_graph_node('equipement', equipement, include_ouvrage=include_ouvrage))
    for compteur in candidates['compteurs']:
        nodes.append(_serialize_organigramme_graph_node('compteur', compteur, include_ouvrage=include_ouvrage))
    for point in candidates['points_eau']:
        nodes.append(_serialize_organigramme_graph_node('point_eau', point, include_ouvrage=include_ouvrage))

    explicit_edges = set()
    liaisons = _get_liaison_queryset().filter(
        ouvrage_id__in=scope_ouvrage_ids,
        actif=True,
    ).order_by('ordre', 'created_at')
    for liaison in liaisons:
        amont_type = liaison.get_amont_type()
        aval_type = liaison.get_aval_type()
        amont_node = liaison.get_amont_node()
        aval_node = liaison.get_aval_node()
        if not amont_type or not aval_type or not amont_node or not aval_node:
            continue

        source_id = _build_organigram_node_value(amont_type, amont_node)
        target_id = _build_organigram_node_value(aval_type, aval_node)
        explicit_edges.add((source_id, target_id))
        edges.append({
            'id': str(liaison.pk),
            'source': source_id,
            'target': target_id,
            'ordre': liaison.ordre,
            'actif': liaison.actif,
            'implicit': False,
        })

    for point in candidates['points_eau']:
        if point.compteur_tete_id:
            source_id = _build_organigram_node_value('compteur', point.compteur_tete)
            target_id = _build_organigram_node_value('point_eau', point)
            if (source_id, target_id) not in explicit_edges:
                edges.append({
                    'id': f"implicit-{point.compteur_tete_id}-{point.id}",
                    'source': source_id,
                    'target': target_id,
                    'ordre': 0,
                    'actif': True,
                    'implicit': True,
                })

    return JsonResponse({
        'success': True,
        'ouvrage': {
            'id': str(ouvrage.pk),
            'nom': ouvrage.nom_ouvrage,
        },
        'scope_ouvrage_ids': [str(item) for item in scope_ouvrage_ids],
        'nodes': nodes,
        'edges': edges,
    })


@require_http_methods(["POST"])
def api_ouvrage_liaison_create(request, ouvrage_id):
    ouvrages = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
    ouvrage = get_object_or_404(ouvrages, pk=ouvrage_id)
    root_ouvrage = _get_organigramme_root_ouvrage(ouvrage)

    try:
        source_raw = (request.POST.get('source_node') or '').strip()
        target_raw = (request.POST.get('target_node') or '').strip()
        if not source_raw or not target_raw:
            return JsonResponse({'success': False, 'error': 'Les elements amont et aval sont requis.'}, status=400)

        source_type, source_node = _resolve_organigram_node(ouvrage, source_raw, allow_point=True)
        target_type, target_node = _resolve_organigram_node(ouvrage, target_raw, allow_point=True)

        if not source_type or source_node is None or not target_type or target_node is None:
            return JsonResponse({'success': False, 'error': 'Elements invalides.'}, status=400)

        with transaction.atomic():
            _replace_inbound_liaison(root_ouvrage, target_type, target_node, source_type, source_node)
            if target_type == 'point_eau':
                target_node.compteur_tete = source_node if source_type == 'compteur' else None
                target_node.save(update_fields=['compteur_tete'])

        return JsonResponse({'success': True, 'message': 'Liaison enregistree.'})
    except ValidationError as exc:
        message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
        return JsonResponse({'success': False, 'error': message}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@require_http_methods(["POST"])
def api_ouvrage_liaison_delete(request, liaison_id):
    try:
        liaison = _get_liaison_queryset().filter(pk=liaison_id).first()
        if liaison is None:
            return JsonResponse({'success': False, 'error': 'Liaison introuvable.'}, status=404)
        ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
        ouvrages_accessibles_detail = _get_ouvrage_detail_filter_queryset(request.user)
        liaison_root_id = str(getattr(getattr(liaison.ouvrage, 'ouvrage_source_effectif', None), 'pk', liaison.ouvrage_id))
        if not ouvrages_accessibles.filter(pk=liaison.ouvrage_id).exists() and not ouvrages_accessibles_detail.filter(pk=liaison_root_id).exists():
            return JsonResponse({'success': False, 'error': 'Acces refuse.'}, status=403)

        aval_type = liaison.get_aval_type()
        aval_node = liaison.get_aval_node()
        amont_type = liaison.get_amont_type()
        amont_node = liaison.get_amont_node()

        with transaction.atomic():
            liaison.delete()
            if aval_type == 'point_eau' and aval_node and amont_type == 'compteur':
                if aval_node.compteur_tete_id == getattr(amont_node, 'pk', None):
                    aval_node.compteur_tete = None
                    aval_node.save(update_fields=['compteur_tete'])

        return JsonResponse({'success': True, 'message': 'Liaison supprimee.'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

