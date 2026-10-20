"""
Vues pour le workflow de capture et amélioration de la qualité des données
avec géolocalisation et capture photo mobile
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import json
import base64
import binascii
import uuid
from math import radians, cos, sin, asin, sqrt

from .models import Village, Parcelle
from apps.billing.models import PointEau
from apps.organization.models import Ouvrage
from apps.infrastructure.models import EquipementConstitutif
from apps.inspections.models import PointDeControleComposant


def haversine(lon1, lat1, lon2, lat2):
    """
    Calcule la distance en kilomètres entre deux points GPS
    """
    # Convertir en radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # Formule haversine
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    # Rayon de la Terre en km
    r = 6371

    return c * r


def _build_choices(choices):
    return [{'value': value, 'label': label} for value, label in choices]


FIELD_DEFINITIONS = {
    'village': [
        {'field': 'coordonnees_gps', 'label': 'Coordonnées GPS', 'type': 'gps'},
        {
            'field': 'accessibilite',
            'label': 'Accessibilité',
            'type': 'select',
            'attr': 'accessibilite',
            'choices': _build_choices(Village.ACCESSIBILITE_CHOICES),
        },
        {
            'field': 'distance_dernier_point',
            'label': 'Distance depuis le dernier point accessible',
            'type': 'number',
            'attr': 'distance_dernier_point',
            'unite': 'km',
        },
        {
            'field': 'altitude',
            'label': 'Altitude',
            'type': 'number',
            'attr': 'altitude',
            'unite': 'm',
        },
        {
            'field': 'photo_village',
            'label': 'Photo du village',
            'type': 'photo',
            'attr': 'photo',
        },
    ],
    'parcelle': [
        {
            'field': 'photo_parcelle',
            'label': 'Photo de la parcelle',
            'type': 'photo',
            'attr': 'photo',
        },
        {
            'field': 'nombre_habitants',
            'label': "Nombre d'habitants",
            'type': 'number',
            'attr': 'nombre_habitants',
        },
        {
            'field': 'nombre_menages',
            'label': 'Nombre de ménages',
            'type': 'number',
            'attr': 'nombre_menages',
        },
    ],
    'point_eau': [
        {'field': 'coordonnees_gps', 'label': 'Coordonnées GPS', 'type': 'gps'},
        {'field': 'photos', 'label': "Photos du point d'eau", 'type': 'photo', 'attr': 'photos'},
        {'field': 'type_point_eau', 'label': "Type de point d'eau", 'type': 'text', 'attr': 'type_point_eau'},
    ],
    'ouvrage': [
        {'field': 'type_ouvrage', 'label': "Type d'ouvrage", 'type': 'text', 'attr': 'type_ouvrage'},
        {'field': 'photo', 'label': "Photo de l'ouvrage", 'type': 'photo', 'attr': 'photo'},
    ],
    'equipement': [
        {'field': 'coordonnees_gps', 'label': 'Coordonnées GPS', 'type': 'gps'},
        {'field': 'photo', 'label': "Photo de l'équipement", 'type': 'photo', 'attr': 'photos'},
        {'field': 'type_equipement', 'label': "Type d'équipement", 'type': 'text', 'attr': 'type_equipement'},
        {'field': 'statut', 'label': 'Statut', 'type': 'text', 'attr': 'statut'},
    ],
    'point_controle': [
        {'field': 'photo', 'label': 'Photo du point de contrôle', 'type': 'photo', 'attr': 'photo'},
    ],
}


def _evaluate_field(entity, spec):
    field_name = spec['field']
    field_type = spec.get('type', 'text')
    attr_name = spec.get('attr', field_name)

    if field_type == 'gps':
        lat_attr = spec.get('lat_attr', 'latitude')
        lon_attr = spec.get('lon_attr', 'longitude')
        lat = getattr(entity, lat_attr, None)
        lon = getattr(entity, lon_attr, None)
        if lat is not None and lon is not None:
            return None
        return {
            'field_name': field_name,
            'label': spec['label'],
            'type': 'gps',
            'value_lat': float(lat) if lat else None,
            'value_lon': float(lon) if lon else None,
        }

    value = getattr(entity, attr_name, None)
    if field_type == 'number':
        if value is not None:
            return None
    elif field_type in ('select', 'text', 'photo'):
        if value:
            return None
    else:
        if value is not None:
            return None

    result = {
        'field_name': field_name,
        'label': spec['label'],
        'type': field_type,
        'value': None,
    }
    if field_type == 'select' and 'choices' in spec:
        result['choices'] = spec['choices']
    if 'unite' in spec:
        result['unite'] = spec['unite']
    return result


def collect_missing_fields(entity, category):
    fields = {}
    for spec in FIELD_DEFINITIONS.get(category, []):
        missing = _evaluate_field(entity, spec)
        if missing:
            fields[missing['field_name']] = missing
    return fields


def build_inspection_url(item_type, item_id):
    base = reverse('inspections:inspection_amelioree')
    return f"{base}?entity_type={item_type}&entity_id={item_id}"


@login_required
def capture_donnees_home(request):
    """Page principale du workflow de capture de données"""
    return render(request, 'geography/capture_donnees.html')


@require_http_methods(["POST"])
def api_villages_proximite(request):
    """
    API pour trouver les villages à moins de 1km de la position GPS de l'utilisateur
    """
    try:
        data = json.loads(request.body)
        user_lat = Decimal(str(data.get('latitude')))
        user_lon = Decimal(str(data.get('longitude')))

        # Récupérer tous les villages avec coordonnées GPS
        villages = Village.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        ).select_related('fokontany', 'fokontany__commune', 'fokontany__commune__district')

        villages_proches = []

        for village in villages:
            distance = haversine(
                float(user_lon), float(user_lat),
                float(village.longitude), float(village.latitude)
            )

            # Si distance < 1km
            if distance < 1.0:
                villages_proches.append({
                    'id': str(village.id),
                    'nom': village.nom_village,
                    'fokontany': village.fokontany.nom_fokontany if village.fokontany else None,
                    'commune': village.fokontany.commune.nom_commune if village.fokontany and village.fokontany.commune else None,
                    'district': village.fokontany.commune.district.nom_district if village.fokontany and village.fokontany.commune and village.fokontany.commune.district else None,
                    'distance': round(distance * 1000, 0),  # en mètres
                    'latitude': float(village.latitude),
                    'longitude': float(village.longitude),
                })

        # Trier par distance
        villages_proches.sort(key=lambda x: x['distance'])

        return JsonResponse({
            'success': True,
            'villages': villages_proches,
            'count': len(villages_proches)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def api_champs_vides(request):
    """
    API pour récupérer les champs vides d'un village et ses entités liées
    """
    try:
        data = json.loads(request.body)
        village_id = data.get('village_id')

        village = Village.objects.get(id=village_id)

        # Analyser les champs vides du village
        village_champs = collect_missing_fields(village, 'village')

        # Parcelles du village
        parcelles = Parcelle.objects.filter(village=village)
        parcelles_data = []

        for parcelle in parcelles:
            champs_vides = collect_missing_fields(parcelle, 'parcelle')
            if champs_vides:
                parcelles_data.append({
                    'id': str(parcelle.id),
                    'numero': getattr(parcelle, 'numero_parcelle', parcelle.reference_parcelle),
                    'champs_vides': champs_vides
                })

        # Points d'eau du village (via parcelles)
        points_eau = PointEau.objects.filter(parcelle__village=village).select_related('parcelle', 'ouvrage')
        points_eau_data = []

        for pe in points_eau:
            champs_vides = collect_missing_fields(pe, 'point_eau')
            if not champs_vides:
                continue
            parcelle_label = None
            if pe.parcelle:
                parcelle_label = getattr(pe.parcelle, 'numero_parcelle', None)
                if not parcelle_label:
                    parcelle_label = pe.parcelle.reference_parcelle

            pe_lat = getattr(pe, 'latitude', None)
            pe_lon = getattr(pe, 'longitude', None)
            display_name = (
                getattr(pe, 'nom', None)
                or getattr(pe, 'nomabonne', None)
                or (f"IDXLS {pe.idxls}" if pe.idxls else None)
                or "Point d'eau"
            )
            points_eau_data.append({
                'id': str(pe.id),
                'nom': display_name,
                'idxls': pe.idxls,
                'parcelle': parcelle_label,
                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else None,
                'champs_vides': champs_vides,
                'inspection_url': build_inspection_url('point_eau', pe.id),
                'existing_data': {
                    'gps': bool(pe_lat is not None and pe_lon is not None),
                    'photo': bool(getattr(pe, 'photo', None) or getattr(pe, 'photos', None)),
                    'type_point_eau': bool(getattr(pe, 'type_point_eau', None)),
                }
            })

        # Ouvrages du village
        ouvrages = Ouvrage.objects.filter(
            Q(pointeau__parcelle__village=village) |
            Q(pointeau__latitude__isnull=False, pointeau__longitude__isnull=False)
        ).distinct()

        ouvrages_data = []
        for ouvrage in ouvrages:
            champs_vides = collect_missing_fields(ouvrage, 'ouvrage')
            ouvrage_lat = getattr(ouvrage, 'latitude', None)
            ouvrage_lon = getattr(ouvrage, 'longitude', None)
            if champs_vides:
                ouvrages_data.append({
                    'id': str(ouvrage.id),
                    'nom': ouvrage.nom_ouvrage,
                    'type': str(ouvrage.type_ouvrage) if ouvrage.type_ouvrage else None,
                    'champs_vides': champs_vides,
                    'existing_data': {
                        'gps': bool(ouvrage_lat is not None and ouvrage_lon is not None),
                        'photo': bool(getattr(ouvrage, 'photo', None) or getattr(ouvrage, 'photo_ouvrage', None)),
                    }
                })

        # Équipements constitutifs
        equipements = EquipementConstitutif.objects.filter(
            ouvrage__pointeau__parcelle__village=village
        ).select_related('ouvrage').distinct()

        equipements_data = []
        for equip in equipements:
            champs_vides = collect_missing_fields(equip, 'equipement')
            equip_lat = getattr(equip, 'latitude', None)
            equip_lon = getattr(equip, 'longitude', None)
            if not champs_vides:
                continue
            equipements_data.append({
                'id': str(equip.id),
                'nom': equip.nom,
                'type': str(equip.type_equipement) if equip.type_equipement else None,
                'ouvrage': equip.ouvrage.nom_ouvrage if equip.ouvrage else None,
                'champs_vides': champs_vides,
                'inspection_url': build_inspection_url('equipement', equip.id),
                'existing_data': {
                    'gps': bool(equip_lat is not None and equip_lon is not None),
                    'photo': bool(getattr(equip, 'photo', None) or getattr(equip, 'photos', None)),
                }
            })

        # Points de contrôle composants
        points_controle = PointDeControleComposant.objects.filter(
            composant_equipement__type_equipement__equipements__ouvrage__pointeau__parcelle__village=village
        ).select_related(
            'composant_equipement',
            'composant_equipement__type_equipement'
        ).distinct()

        points_controle_data = []
        for pc in points_controle:
            champs_vides = collect_missing_fields(pc, 'point_controle')
            if not champs_vides:
                continue
            points_controle_data.append({
                'id': str(pc.id),
                'nom': getattr(pc.point_de_controle, 'nom', None),
                'equipement': str(pc.composant_equipement) if pc.composant_equipement else None,
                'ouvrage': None,
                'champs_vides': champs_vides
            })

        return JsonResponse({
            'success': True,
            'village': {
                'id': str(village.id),
                'nom': village.nom_village,
                'champs_vides': village_champs,
                'nb_champs_vides': len(village_champs)
            },
            'parcelles': parcelles_data,
            'points_eau': points_eau_data,
            'ouvrages': ouvrages_data,
            'equipements': equipements_data,
            'points_controle': points_controle_data,
            'total_champs_vides': (
                len(village_champs) +
                sum(len(p['champs_vides']) for p in parcelles_data) +
                sum(len(pe['champs_vides']) for pe in points_eau_data) +
                sum(len(o['champs_vides']) for o in ouvrages_data) +
                sum(len(e['champs_vides']) for e in equipements_data) +
                sum(len(pc['champs_vides']) for pc in points_controle_data)
            )
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def api_update_champ(request):
    """
    API pour mettre à jour un champ (texte, GPS ou photo)
    """
    try:
        # Récupérer les données du formulaire
        entity_type = request.POST.get('entity_type')
        entity_id = request.POST.get('entity_id')
        field_name = request.POST.get('field_name')
        field_type = request.POST.get('field_type')

        # Récupérer l'entité
        if entity_type == 'village':
            entity = Village.objects.get(id=entity_id)
        elif entity_type == 'parcelle':
            entity = Parcelle.objects.get(id=entity_id)
        elif entity_type == 'point_eau':
            entity = PointEau.objects.get(id=entity_id)
        elif entity_type == 'ouvrage':
            entity = Ouvrage.objects.get(id=entity_id)
        elif entity_type == 'equipement':
            entity = EquipementConstitutif.objects.get(id=entity_id)
        elif entity_type == 'point_controle':
            entity = PointDeControleComposant.objects.get(id=entity_id)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Type d\'entité invalide'
            }, status=400)

        # Mettre à jour selon le type de champ
        if field_type == 'gps':
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            altitude = request.POST.get('altitude')

            if field_name == 'coordonnees_gps':
                entity.latitude = Decimal(latitude) if latitude else None
                entity.longitude = Decimal(longitude) if longitude else None
                if hasattr(entity, 'altitude') and altitude:
                    entity.altitude = Decimal(altitude)

        elif field_type == 'photo':
            # Photo en base64 depuis la caméra
            photo_data = request.POST.get('photo_data')
            if photo_data:
                try:
                    data_format, imgstr = photo_data.split(';base64,', 1)
                    mime_type = data_format.split(':', 1)[1]
                    image_bytes = base64.b64decode(imgstr, validate=True)
                except (ValueError, TypeError, binascii.Error):
                    return JsonResponse({
                        'success': False,
                        'error': 'Format de photo invalide.'
                    }, status=400)

                # Le nom envoyé par l'interface peut différer du vrai attribut
                # du modèle (ex. « photo » côté UI, « photos » en base).
                field_spec = next((
                    spec for spec in FIELD_DEFINITIONS.get(entity_type, [])
                    if spec['field'] == field_name
                ), None)
                target_field_name = field_spec.get('attr', field_name) if field_spec else field_name

                if not hasattr(entity, target_field_name):
                    return JsonResponse({
                        'success': False,
                        'error': 'Champ photo invalide pour cette entité.'
                    }, status=400)

                model_field = entity._meta.get_field(target_field_name)
                extension = 'jpg' if mime_type == 'image/jpeg' else mime_type.split('/')[-1]
                filename = f'{uuid.uuid4()}.{extension}'

                if isinstance(model_field, models.JSONField):
                    # PointEau.photos et EquipementConstitutif.photos stockent
                    # une liste de dictionnaires, pas des objets fichier Django.
                    existing_photos = getattr(entity, target_field_name) or []
                    if not isinstance(existing_photos, list):
                        existing_photos = [existing_photos]
                    photos = list(existing_photos)
                    photos.append({
                        'id': str(uuid.uuid4()),
                        'name': filename,
                        'data': photo_data,
                        'size': len(image_bytes),
                        'originalSize': len(image_bytes),
                        'type': mime_type,
                        'date': timezone.now().isoformat(),
                    })
                    setattr(entity, target_field_name, photos)
                elif isinstance(model_field, models.FileField):
                    file_field = getattr(entity, target_field_name)
                    if file_field:
                        file_field.delete(save=False)
                    file_field.save(filename, ContentFile(image_bytes), save=False)
                elif isinstance(model_field, models.TextField):
                    # Les photos des villages, parcelles et ouvrages sont des
                    # data URLs stockées directement dans un champ texte.
                    setattr(entity, target_field_name, photo_data)
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'Type de champ photo non pris en charge.'
                    }, status=400)

        elif field_type == 'text' or field_type == 'select' or field_type == 'number':
            value = request.POST.get('value')
            if hasattr(entity, field_name):
                if field_type == 'number':
                    setattr(entity, field_name, Decimal(value) if value else None)
                else:
                    setattr(entity, field_name, value)

        # Sauvegarder
        entity.save()

        return JsonResponse({
            'success': True,
            'message': f'Champ {field_name} mis à jour avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
