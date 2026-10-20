from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import Count, Q
from django.apps import apps as django_apps
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import TypeDesignation, Designation, DesignationCompte, DesignationTypeActivite, TypeActivite
from .models import BonLivraison, PlanningDetail
from apps.organization.models import Compte
import json
import uuid
from decimal import Decimal


def _sync_designation_legacy_flags(designation):
    """Conserver les anciens flags alignes avec type_avance_caissiere."""
    type_avance = (designation.type_avance_caissiere or '').strip()
    designation.concerne_avance = type_avance == 'Avance'
    designation.concerne_livraison = type_avance == 'Bon de livraison'


def _safe_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    return Decimal(str(value))


def _merge_designation_comptes(source_designation, target_designation):
    for source_link in DesignationCompte.objects.filter(designation=source_designation).select_related('compte'):
        target_link = DesignationCompte.objects.filter(
            designation=target_designation,
            compte=source_link.compte
        ).first()
        if target_link:
            updated_fields = []
            if source_link.is_active and not target_link.is_active:
                target_link.is_active = True
                updated_fields.append('is_active')
            if (not target_link.notes) and source_link.notes:
                target_link.notes = source_link.notes
                updated_fields.append('notes')
            if updated_fields:
                target_link.save(update_fields=updated_fields)
            source_link.delete()
            continue

        source_link.designation = target_designation
        source_link.save(update_fields=['designation'])


def _merge_designation_type_activites(source_designation, target_designation):
    for source_link in DesignationTypeActivite.objects.filter(designation=source_designation).select_related('type_activite'):
        target_link = DesignationTypeActivite.objects.filter(
            designation=target_designation,
            type_activite=source_link.type_activite
        ).first()
        if target_link:
            updated_fields = []
            if hasattr(source_link, 'is_active') and hasattr(target_link, 'is_active') and source_link.is_active and not target_link.is_active:
                target_link.is_active = True
                updated_fields.append('is_active')
            if hasattr(source_link, 'notes') and hasattr(target_link, 'notes') and (not target_link.notes) and source_link.notes:
                target_link.notes = source_link.notes
                updated_fields.append('notes')
            if updated_fields:
                target_link.save(update_fields=updated_fields)
            source_link.delete()
            continue

        source_link.designation = target_designation
        source_link.save(update_fields=['designation'])


def _merge_stocks(source_designation, target_designation):
    Stock = django_apps.get_model('inventory', 'Stock')
    for source_stock in Stock.objects.filter(designation=source_designation).select_related('base', 'utilisateur'):
        target_stock = Stock.objects.filter(
            designation=target_designation,
            base=source_stock.base
        ).first()
        if target_stock:
            target_stock.current_quantity = _safe_decimal(target_stock.current_quantity) + _safe_decimal(source_stock.current_quantity)
            target_stock.reserved_quantity = _safe_decimal(target_stock.reserved_quantity) + _safe_decimal(source_stock.reserved_quantity)
            if not target_stock.inventory_date and source_stock.inventory_date:
                target_stock.inventory_date = source_stock.inventory_date
            if source_stock.inventory_date and target_stock.inventory_date and source_stock.inventory_date > target_stock.inventory_date:
                target_stock.inventory_date = source_stock.inventory_date
            if source_stock.rapproche:
                target_stock.rapproche = True
            if (target_stock.etat in (None, '', 'bon')) and source_stock.etat:
                target_stock.etat = source_stock.etat
            if not target_stock.utilisateur_id and source_stock.utilisateur_id:
                target_stock.utilisateur = source_stock.utilisateur
            if not target_stock.photo and source_stock.photo:
                target_stock.photo = source_stock.photo
            target_stock.save()
            source_stock.delete()
            continue

        source_stock.designation = target_designation
        source_stock.save(update_fields=['designation'])


def _merge_demande_devis_items(source_designation, target_designation):
    DemandeDevisItem = django_apps.get_model('inventory', 'DemandeDevisItem')
    numeric_fields = [
        'besoin_retenu',
        'bons_attente',
        'stock_precedent',
        'achats_effectues',
        'estimation_historique',
        'stock_actuel',
        'quantite_a_commander',
        'quantite_finale',
    ]
    integer_fields = ['nb_lignes_bl']
    for source_item in DemandeDevisItem.objects.filter(designation=source_designation).select_related('demande_devis'):
        target_item = DemandeDevisItem.objects.filter(
            demande_devis=source_item.demande_devis,
            designation=target_designation
        ).first()
        if target_item:
            for field_name in numeric_fields:
                setattr(
                    target_item,
                    field_name,
                    _safe_decimal(getattr(target_item, field_name)) + _safe_decimal(getattr(source_item, field_name))
                )
            for field_name in integer_fields:
                setattr(
                    target_item,
                    field_name,
                    int(getattr(target_item, field_name) or 0) + int(getattr(source_item, field_name) or 0)
                )
            if not target_item.source_calcul and source_item.source_calcul:
                target_item.source_calcul = source_item.source_calcul
            if not target_item.prix_unitaire_estime and source_item.prix_unitaire_estime:
                target_item.prix_unitaire_estime = source_item.prix_unitaire_estime
            target_item.save()
            source_item.delete()
            continue

        source_item.designation = target_designation
        source_item.save(update_fields=['designation'])


def _reassign_remaining_designation_relations(source_designation, target_designation):
    special_models = {
        ('planning', 'DesignationCompte'),
        ('planning', 'DesignationTypeActivite'),
        ('inventory', 'Stock'),
        ('inventory', 'DemandeDevisItem'),
    }
    source_model = Designation

    for model in django_apps.get_models():
        if (model._meta.app_label, model.__name__) in special_models:
            continue

        for field in model._meta.get_fields():
            if not getattr(field, 'concrete', False):
                continue
            if not getattr(field, 'is_relation', False):
                continue
            remote_field = getattr(field, 'remote_field', None)
            if not remote_field or remote_field.model is not source_model:
                continue
            if field.many_to_many:
                continue

            model.objects.filter(**{field.name: source_designation}).update(**{field.name: target_designation})


def _merge_designations(source_designation, target_designation):
    with transaction.atomic():
        _merge_designation_comptes(source_designation, target_designation)
        _merge_designation_type_activites(source_designation, target_designation)
        _merge_stocks(source_designation, target_designation)
        _merge_demande_devis_items(source_designation, target_designation)
        _reassign_remaining_designation_relations(source_designation, target_designation)
        source_designation.delete()


# ===== VUES TABLEAUX (Style organisation/géographie) =====

def type_designation_table(request):
    """Page tableau avec cascade pour les types de désignations"""
    user_poste_nom = (
        getattr(getattr(getattr(request.user, 'employe', None), 'poste', None), 'nom_poste', '')
        or ''
    ).strip().lower()
    context = {
        'title': 'Gestion des Types de Désignations',
        'is_directeur_poste': bool(
            getattr(request.user, 'is_superuser', False) or user_poste_nom == 'directeur'
        ),
    }
    return render(request, 'planning/crud/type_designation_table.html', context)


def designation_consolidated(request):
    """Vue consolidee pour rechercher rapidement des designations."""
    q = (request.GET.get('q') or '').strip()
    type_id = (request.GET.get('type_id') or '').strip()
    statut = (request.GET.get('statut') or '').strip()
    avance_only = (request.GET.get('avance') or '').strip() in {'1', 'true', 'on'}
    avance_value = 'Avance'

    designations_qs = Designation.objects.select_related('type_designation').annotate(
        comptes_count=Count('comptes', distinct=True)
    ).order_by('type_designation__nom', 'nom')

    if q:
        designations_qs = designations_qs.filter(
            Q(nom__icontains=q)
            | Q(description__icontains=q)
            | Q(code_materiel__icontains=q)
            | Q(type_designation__nom__icontains=q)
        )

    selected_type = None
    if type_id:
        try:
            uuid.UUID(type_id)
            designations_qs = designations_qs.filter(type_designation_id=type_id)
            selected_type = TypeDesignation.objects.filter(id=type_id).first()
        except (ValueError, TypeError):
            type_id = ''

    if statut == 'actif':
        designations_qs = designations_qs.filter(actif=True)
    elif statut == 'inactif':
        designations_qs = designations_qs.filter(actif=False)

    if avance_only:
        designations_qs = designations_qs.filter(type_avance_caissiere=avance_value)

    total_designations = designations_qs.count()
    total_actives = designations_qs.filter(actif=True).count()
    total_inactives = total_designations - total_actives
    total_types = designations_qs.values('type_designation_id').distinct().count()

    paginator = Paginator(designations_qs, 80)
    page_obj = paginator.get_page(request.GET.get('page'))

    query_without_page = request.GET.copy()
    query_without_page.pop('page', None)

    context = {
        'title': 'Designations consolidees',
        'types_designations': TypeDesignation.objects.all().order_by('nom'),
        'page_obj': page_obj,
        'selected_type': selected_type,
        'filters': {
            'q': q,
            'type_id': type_id,
            'statut': statut,
            'avance': avance_only,
        },
        'avance_value': avance_value,
        'stats': {
            'total': total_designations,
            'actives': total_actives,
            'inactives': total_inactives,
            'types': total_types,
        },
        'query_string': query_without_page.urlencode(),
    }
    return render(request, 'planning/crud/designation_consolidated.html', context)


# ===== CRUD TypeDesignation =====

def type_designation_list(request):
    """Liste des types de désignations"""
    types_designations = TypeDesignation.objects.all().order_by('nom')
    context = {
        'types_designations': types_designations,
        'title': 'Types de Désignations'
    }
    return render(request, 'planning/crud/type_designation_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def type_designation_api(request):
    """API pour récupérer les types de désignations"""
    types = TypeDesignation.objects.all().order_by('nom')
    data = []
    for type_desig in types:
        data.append({
            'id': str(type_desig.id),
            'nom': type_desig.nom,
            'description': type_desig.description,
            'is_active': type_desig.is_active,
            'created_at': type_desig.created_at.isoformat() if type_desig.created_at else None,
            'designations_count': type_desig.designations.count()
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def type_designation_detail(request, type_id):
    """API pour récupérer un type de désignation spécifique"""
    try:
        type_designation = get_object_or_404(TypeDesignation, id=type_id)
        data = {
            'id': str(type_designation.id),
            'nom': type_designation.nom,
            'description': type_designation.description or '',
            'is_active': type_designation.is_active,
            'created_at': type_designation.created_at.isoformat() if type_designation.created_at else None
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def type_designation_create(request):
    """Créer un nouveau type de désignation"""
    try:
        data = json.loads(request.body)
        type_designation = TypeDesignation.objects.create(
            nom=data.get('nom', '').strip(),
            description=data.get('description', '').strip(),
            is_active=data.get('is_active', True)
        )
        return JsonResponse({
            'success': True,
            'message': 'Type de désignation créé avec succès',
            'data': {
                'id': str(type_designation.id),
                'nom': type_designation.nom
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def type_designation_update(request, type_id):
    """Modifier un type de désignation"""
    try:
        type_designation = get_object_or_404(TypeDesignation, id=type_id)
        data = json.loads(request.body)
        type_designation.nom = data.get('nom', type_designation.nom).strip()
        type_designation.description = data.get('description', type_designation.description or '').strip()
        type_designation.is_active = data.get('is_active', type_designation.is_active)
        type_designation.save()

        return JsonResponse({
            'success': True,
            'message': 'Type de désignation modifié avec succès',
            'data': {
                'id': str(type_designation.id),
                'nom': type_designation.nom
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def type_designation_delete(request, type_id):
    """Supprimer un type de désignation"""
    try:
        type_designation = get_object_or_404(TypeDesignation, id=type_id)

        # Vérifier s'il y a des désignations liées
        designations_count = type_designation.designations.count()
        if designations_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Impossible de supprimer: {designations_count} désignation(s) sont liées à ce type'
            }, status=400)

        type_designation.delete()
        return JsonResponse({
            'success': True,
            'message': 'Type de désignation supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


# ===== CRUD Designation =====

def designation_list(request, type_designation_id=None):
    """Liste des désignations (optionnellement filtrées par type)"""
    if type_designation_id:
        type_designation = get_object_or_404(TypeDesignation, id=type_designation_id)
        designations = Designation.objects.filter(type_designation=type_designation).order_by('nom')
        context = {
            'designations': designations,
            'type_designation': type_designation,
            'title': f'Désignations - {type_designation.nom}'
        }
    else:
        designations = Designation.objects.all().order_by('type_designation__nom', 'nom')
        context = {
            'designations': designations,
            'title': 'Toutes les Désignations'
        }
    return render(request, 'planning/crud/designation_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_api(request, type_designation_id=None):
    """API pour récupérer les désignations"""
    base_queryset = Designation.objects.select_related(
        'type_designation',
        'poste_acheteur',
        'photo_specimen',
    ).annotate(
        comptes_count_value=Count('comptes')
    )
    if type_designation_id:
        designations = base_queryset.filter(type_designation_id=type_designation_id).order_by('nom')
    else:
        designations = base_queryset.order_by('type_designation__nom', 'nom')

    data = []
    for designation in designations:
        # Gérer les relations orphelines
        try:
            type_designation_id = str(designation.type_designation.id) if designation.type_designation else None
            type_designation_nom = designation.type_designation.nom if designation.type_designation else 'Type supprimé'
        except:
            type_designation_id = None
            type_designation_nom = 'Type supprimé'

        # Récupérer l'URL de la photo specimen si elle existe
        photo_specimen_url = None
        if designation.photo_specimen:
            photo_specimen_url = designation.photo_specimen.get_download_url()

        data.append({
            'id': designation.id,
            'nom': designation.nom,
            'description': designation.description,
            'type_designation_id': type_designation_id,
            'type_designation_nom': type_designation_nom,
            'type_designation_chantier': designation.type_designation_chantier or '',
            'prix_unitaire': float(designation.prix_unitaire) if designation.prix_unitaire else None,
            'unite': designation.unite,
            'nature_stock': designation.nature_stock or 'consommable',
            'type_avance_caissiere': designation.type_avance_caissiere or '',
            'actif': designation.actif,
            'poids_unitaire': float(designation.poids_unitaire) if designation.poids_unitaire else None,
            'seuil_minimum': float(designation.seuil_minimum) if designation.seuil_minimum else None,
            'code_materiel': designation.code_materiel or '',
            'prestation': designation.prestation,
            'date_prix': designation.date_prix.isoformat() if designation.date_prix else '',
            'poste_acheteur_id': str(designation.poste_acheteur.id) if designation.poste_acheteur else '',
            'poste_acheteur_nom': designation.poste_acheteur.nom_poste if designation.poste_acheteur else '',
            'comptes_count': designation.comptes_count_value,
            'photo_specimen_url': photo_specimen_url
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_detail(request, designation_id):
    """API pour récupérer une désignation spécifique"""
    try:
        designation = get_object_or_404(Designation, id=designation_id)
        data = {
            'id': designation.id,
            'nom': designation.nom,
            'description': designation.description or '',
            'type_designation_id': str(designation.type_designation.id),
            'type_designation_nom': designation.type_designation.nom,
            'prix_unitaire': float(designation.prix_unitaire) if designation.prix_unitaire else None,
            'unite': designation.unite or '',
            'concerne_livraison': designation.concerne_livraison,
            'concerne_avance': designation.concerne_avance,
            'actif': designation.actif,
            # Nouveaux champs
            'poids_unitaire': float(designation.poids_unitaire) if designation.poids_unitaire else None,
            'seuil_minimum': float(designation.seuil_minimum) if designation.seuil_minimum else None,
            'nature_stock': designation.nature_stock or 'consommable',
            'type_avance_caissiere': designation.type_avance_caissiere or '',
            'type_designation_chantier': designation.type_designation_chantier or '',
            'code_materiel': designation.code_materiel or '',
            'prestation': designation.prestation,
            'date_prix': designation.date_prix.isoformat() if designation.date_prix else '',
            'poste_acheteur_id': str(designation.poste_acheteur.id) if designation.poste_acheteur else '',
            'poste_acheteur_nom': designation.poste_acheteur.nom_poste if designation.poste_acheteur else '',
            'photo_specimen_url': designation.photo_specimen.get_download_url() if designation.photo_specimen else None
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def designation_create(request):
    """Créer une nouvelle désignation"""
    try:
        # Support both JSON and FormData (for file uploads)
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.POST
            photo_file = request.FILES.get('photo_specimen')
        else:
            data = json.loads(request.body)
            photo_file = None

        type_designation = get_object_or_404(TypeDesignation, id=data.get('type_designation'))

        # Gestion du poste acheteur
        poste_acheteur = None
        if data.get('poste_acheteur_id'):
            from apps.employees.models import Poste
            poste_acheteur = get_object_or_404(Poste, id=data.get('poste_acheteur_id'))

        # Gestion de la date prix
        date_prix = None
        if data.get('date_prix'):
            from datetime import datetime
            try:
                date_prix = datetime.strptime(data.get('date_prix'), '%Y-%m-%d').date()
            except ValueError:
                pass

        # Gérer l'upload de photo si présente
        photo_specimen_obj = None
        if photo_file:
            from apps.filemanager.models import FileUpload
            # Créer un FileUpload simple (sans Supabase pour l'instant)
            photo_specimen_obj = FileUpload.objects.create(
                filename=photo_file.name,
                original_filename=photo_file.name,
                file_size=photo_file.size,
                content_type=photo_file.content_type,
                supabase_path=f"designations/{photo_file.name}",  # Path temporaire
                uploaded_by=request.user
            )

        # Gérer actif comme boolean depuis FormData
        actif_value = data.get('actif')
        if isinstance(actif_value, str):
            actif = actif_value.lower() in ('true', '1', 'on')
        else:
            actif = bool(actif_value) if actif_value is not None else True

        designation = Designation.objects.create(
            nom=data.get('nom', '').strip(),
            description=data.get('description', '').strip(),
            type_designation=type_designation,
            prix_unitaire=data.get('prix_unitaire') if data.get('prix_unitaire') else None,
            unite=data.get('unite', '').strip() if data.get('unite') else None,
            actif=actif,
            # Nouveaux champs
            poids_unitaire=data.get('poids_unitaire') if data.get('poids_unitaire') else None,
            seuil_minimum=data.get('seuil_minimum') if data.get('seuil_minimum') else None,
            nature_stock=data.get('nature_stock') if data.get('nature_stock') else 'consommable',
            type_avance_caissiere=data.get('type_avance_caissiere') if data.get('type_avance_caissiere') else None,
            type_designation_chantier=data.get('type_designation_chantier') if data.get('type_designation_chantier') else None,
            code_materiel=data.get('code_materiel', '').strip() if data.get('code_materiel') else None,
            prestation=data.get('prestation', False),
            date_prix=date_prix,
            poste_acheteur=poste_acheteur,
            photo_specimen=photo_specimen_obj
        )
        _sync_designation_legacy_flags(designation)
        designation.save(update_fields=['concerne_avance', 'concerne_livraison'])

        return JsonResponse({
            'success': True,
            'message': 'Désignation créée avec succès',
            'data': {
                'id': designation.id,
                'nom': designation.nom,
                'type_designation_nom': type_designation.nom
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT", "POST"])  # Support POST for FormData
def designation_update(request, designation_id):
    """Modifier une désignation"""
    try:
        designation = get_object_or_404(Designation, id=designation_id)

        # Support both JSON and FormData (for file uploads)
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.POST
            photo_file = request.FILES.get('photo_specimen')
        else:
            data = json.loads(request.body)
            photo_file = None

        type_designation_value = data.get('type_designation_id') or data.get('type_designation')
        if type_designation_value:
            type_designation = get_object_or_404(TypeDesignation, id=type_designation_value)
            designation.type_designation = type_designation

        # Gérer les champs texte avec strip() sûr
        nom_value = data.get('nom', designation.nom)
        designation.nom = nom_value.strip() if nom_value else designation.nom

        description_value = data.get('description', designation.description)
        designation.description = description_value.strip() if description_value else ''

        if 'prix_unitaire' in data:
            prix_unitaire_value = data.get('prix_unitaire')
            designation.prix_unitaire = prix_unitaire_value if prix_unitaire_value not in (None, '') else None

        unite_value = data.get('unite', designation.unite)
        designation.unite = unite_value.strip() if unite_value else None

        # Gérer actif comme boolean depuis FormData
        if 'actif' in data:
            actif_value = data.get('actif')
            if isinstance(actif_value, str):
                designation.actif = actif_value.lower() in ('true', '1', 'on')
            else:
                designation.actif = bool(actif_value)

        # Gérer l'upload de photo si présente
        if photo_file:
            from apps.filemanager.models import FileUpload
            # Créer un FileUpload simple (sans Supabase pour l'instant)
            photo_specimen_obj = FileUpload.objects.create(
                filename=photo_file.name,
                original_filename=photo_file.name,
                file_size=photo_file.size,
                content_type=photo_file.content_type,
                supabase_path=f"designations/{photo_file.name}",  # Path temporaire
                uploaded_by=request.user
            )
            designation.photo_specimen = photo_specimen_obj

        # Mise à jour des nouveaux champs
        if 'poids_unitaire' in data:
            designation.poids_unitaire = data.get('poids_unitaire') if data.get('poids_unitaire') else None
        if 'seuil_minimum' in data:
            designation.seuil_minimum = data.get('seuil_minimum') if data.get('seuil_minimum') else None
        if 'nature_stock' in data:
            designation.nature_stock = data.get('nature_stock') if data.get('nature_stock') else 'consommable'
        if 'type_avance_caissiere' in data:
            designation.type_avance_caissiere = data.get('type_avance_caissiere') if data.get('type_avance_caissiere') else None
        if 'type_designation_chantier' in data:
            designation.type_designation_chantier = data.get('type_designation_chantier') if data.get('type_designation_chantier') else None
        if 'code_materiel' in data:
            designation.code_materiel = data.get('code_materiel', '').strip() if data.get('code_materiel') else None
        if 'prestation' in data:
            designation.prestation = data.get('prestation', False)
        if 'date_prix' in data:
            if data.get('date_prix'):
                from datetime import datetime
                try:
                    designation.date_prix = datetime.strptime(data.get('date_prix'), '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                designation.date_prix = None
        if 'poste_acheteur_id' in data:
            if data.get('poste_acheteur_id'):
                from apps.employees.models import Poste
                designation.poste_acheteur = get_object_or_404(Poste, id=data.get('poste_acheteur_id'))
            else:
                designation.poste_acheteur = None

        _sync_designation_legacy_flags(designation)
        designation.save()

        return JsonResponse({
            'success': True,
            'message': 'Désignation modifiée avec succès',
            'data': {
                'id': designation.id,
                'nom': designation.nom,
                'type_designation_nom': designation.type_designation.nom if designation.type_designation else 'N/A'
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def designation_delete(request, designation_id):
    """Supprimer une désignation"""
    try:
        designation = get_object_or_404(Designation, id=designation_id)

        # Vérifier s'il y a des comptes de désignation liés
        comptes_count = designation.comptes.count()
        if comptes_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Impossible de supprimer: {comptes_count} compte(s) sont liés'
            }, status=400)

        designation.delete()
        return JsonResponse({
            'success': True,
            'message': 'Désignation supprimée avec succès'
        })
    except ProtectedError:
        return JsonResponse({
            'success': False,
            'message': (
                "Suppression impossible: cette désignation est utilisée par des "
                "enregistrements protégés (par exemple BonLivraison ou PlanningDetail). "
                "Supprimez d'abord ces références."
            )
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_delete_info(request, designation_id):
    """Retourne les références qui empêchent la suppression d'une désignation."""
    designation = get_object_or_404(Designation, id=designation_id)

    comptes = list(
        designation.comptes.select_related('compte').order_by('compte__nom_compte')[:10]
    )
    planning_details = list(
        PlanningDetail.objects.filter(designation=designation).select_related('planning').order_by('-id')[:10]
    )
    bons = list(
        BonLivraison.objects.filter(designation=designation).select_related('planning').order_by('-id')[:10]
    )

    return Response({
        'id': str(designation.id),
        'nom': designation.nom,
        'counts': {
            'comptes': designation.comptes.count(),
            'planning_details': PlanningDetail.objects.filter(designation=designation).count(),
            'bons_livraison': BonLivraison.objects.filter(designation=designation).count(),
        },
        'blockers': {
            'comptes': [
                {
                    'id': str(item.id),
                    'compte': item.compte.nom_compte,
                    'code': item.compte.compte,
                } for item in comptes
            ],
            'planning_details': [
                {
                    'id': str(item.id),
                    'planning_id': str(item.planning_id) if item.planning_id else '',
                } for item in planning_details
            ],
            'bons_livraison': [
                {
                    'id': str(item.id),
                    'planning_id': str(item.planning_id) if item.planning_id else '',
                } for item in bons
            ],
        }
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def designation_merge(request, designation_id):
    """Fusionner une designation source dans une designation cible."""
    source_designation = get_object_or_404(Designation, id=designation_id)
    target_designation_id = request.data.get('target_designation_id') or request.POST.get('target_designation_id')

    if not target_designation_id:
        return Response({
            'success': False,
            'message': 'target_designation_id est obligatoire.'
        }, status=400)

    target_designation = get_object_or_404(Designation, id=target_designation_id)

    if str(source_designation.id) == str(target_designation.id):
        return Response({
            'success': False,
            'message': 'La désignation source et la cible doivent être différentes.'
        }, status=400)

    try:
        source_name = source_designation.nom
        target_name = target_designation.nom
        _merge_designations(source_designation, target_designation)
    except Exception as exc:
        return Response({
            'success': False,
            'message': f'Erreur lors de la fusion: {exc}'
        }, status=400)

    return Response({
        'success': True,
        'message': f'Désignation "{source_name}" fusionnée dans "{target_name}".',
        'data': {
            'target_designation_id': str(target_designation.id),
            'target_designation_nom': target_designation.nom,
        }
    })


# ===== CRUD DesignationCompte =====

def designation_compte_list(request, designation_id=None):
    """Liste des liaisons désignation-compte (optionnellement filtrées par désignation)"""
    if designation_id:
        designation = get_object_or_404(Designation, id=designation_id)
        liaisons = DesignationCompte.objects.filter(designation=designation).select_related('compte').order_by('compte__nom_compte')
        context = {
            'liaisons': liaisons,
            'designation': designation,
            'title': f'Comptes liés à - {designation.nom}'
        }
    else:
        liaisons = DesignationCompte.objects.all().select_related('designation', 'compte').order_by('designation__nom', 'compte__nom_compte')
        context = {
            'liaisons': liaisons,
            'title': 'Toutes les Liaisons Désignation-Comptes'
        }
    return render(request, 'planning/crud/designation_compte_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_compte_api(request, designation_id=None):
    """API pour récupérer les liaisons désignation-compte"""
    if designation_id:
        liaisons = DesignationCompte.objects.filter(designation_id=designation_id).select_related('compte', 'designation').order_by('compte__nom_compte')
    else:
        liaisons = DesignationCompte.objects.all().select_related('designation', 'compte').order_by('designation__nom', 'compte__nom_compte')

    data = []
    for liaison in liaisons:
        data.append({
            'id': str(liaison.id),
            'compte_id': str(liaison.compte.id),
            'compte_nom': liaison.compte.nom_compte,
            'compte_code': liaison.compte.compte,
            'designation_id': liaison.designation.id,
            'designation_nom': liaison.designation.nom,
            'type_designation_nom': liaison.designation.type_designation.nom if liaison.designation.type_designation else 'N/A',
            'notes': liaison.notes or '',
            'is_active': liaison.is_active
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_compte_detail(request, compte_id):
    """API pour récupérer une liaison désignation-compte spécifique"""
    try:
        liaison = get_object_or_404(DesignationCompte, id=compte_id)
        data = {
            'id': str(liaison.id),
            'compte_id': str(liaison.compte.id),
            'compte_nom': liaison.compte.nom_compte,
            'compte_code': liaison.compte.compte,
            'designation_id': liaison.designation.id,
            'designation_nom': liaison.designation.nom,
            'type_designation_nom': liaison.designation.type_designation.nom if liaison.designation.type_designation else 'N/A',
            'notes': liaison.notes or '',
            'is_active': liaison.is_active
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def designation_compte_create(request):
    """Créer une nouvelle liaison désignation-compte"""
    try:
        data = json.loads(request.body)
        designation = get_object_or_404(Designation, id=data.get('designation_id'))
        compte = get_object_or_404(Compte, id=data.get('compte_id'))

        # Vérifier si la liaison existe déjà
        if DesignationCompte.objects.filter(designation=designation, compte=compte).exists():
            return JsonResponse({
                'success': False,
                'message': 'Une liaison entre cette désignation et ce compte existe déjà'
            }, status=400)

        liaison = DesignationCompte.objects.create(
            designation=designation,
            compte=compte,
            notes=data.get('notes', '').strip(),
            is_active=data.get('is_active', True)
        )

        return JsonResponse({
            'success': True,
            'message': 'Liaison désignation-compte créée avec succès',
            'data': {
                'id': str(liaison.id),
                'compte_nom': compte.nom_compte,
                'designation_nom': designation.nom
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def designation_compte_update(request, compte_id):
    """Modifier une liaison désignation-compte"""
    try:
        liaison = get_object_or_404(DesignationCompte, id=compte_id)
        data = json.loads(request.body)

        # Vérifier si on change le compte et que la nouvelle liaison n'existe pas déjà
        new_compte_id = data.get('compte_id')
        if new_compte_id and str(liaison.compte.id) != new_compte_id:
            new_compte = get_object_or_404(Compte, id=new_compte_id)
            if DesignationCompte.objects.filter(
                designation=liaison.designation,
                compte=new_compte
            ).exclude(id=liaison.id).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Une liaison avec ce compte existe déjà'
                }, status=400)
            liaison.compte = new_compte

        liaison.notes = data.get('notes', liaison.notes or '').strip()
        liaison.is_active = data.get('is_active', liaison.is_active)
        liaison.save()

        return JsonResponse({
            'success': True,
            'message': 'Liaison modifiée avec succès',
            'data': {
                'id': str(liaison.id),
                'compte_nom': liaison.compte.nom_compte
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def designation_compte_delete(request, compte_id):
    """Supprimer une liaison désignation-compte"""
    try:
        liaison = get_object_or_404(DesignationCompte, id=compte_id)
        compte_nom = liaison.compte.nom_compte
        liaison.delete()
        return JsonResponse({
            'success': True,
            'message': f'Liaison avec "{compte_nom}" supprimée avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def comptes_disponibles_api(request):
    """API pour récupérer tous les comptes disponibles pour liaison avec désignations"""
    try:
        comptes = Compte.objects.all().order_by('nom_compte')
        data = []
        for compte in comptes:
            data.append({
                'id': str(compte.id),
                'nom_compte': compte.nom_compte,
                'compte': compte.compte,
                'detail': compte.detail or '',
                'achat': compte.achat
            })
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des comptes: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def postes_disponibles_api(request):
    """API pour récupérer tous les postes disponibles pour les désignations"""
    try:
        from apps.employees.models import Poste
        postes = Poste.objects.all().select_related('organisation').order_by('ordre_affichage', 'nom_poste')
        data = []
        for poste in postes:
            data.append({
                'id': str(poste.id),
                'nom_poste': poste.nom_poste,
                'organisation_nom': poste.organisation.nom_organisation if poste.organisation else '',
                'tarif_indemnite': float(poste.tarif_indemnite) if poste.tarif_indemnite else 0
            })
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des postes: {str(e)}'
        }, status=400)


# ===== VUES CRUD DESIGNATION-TYPE-ACTIVITE =====

@api_view(['GET'])
@permission_classes([AllowAny])
def designation_types_activites_list(request, designation_id):
    """Lister les types d'activités pour une désignation"""
    try:
        designation = get_object_or_404(Designation, id=designation_id)
        liaisons = DesignationTypeActivite.objects.filter(designation=designation).select_related('type_activite')

        data = []
        for liaison in liaisons:
            data.append({
                'id': str(liaison.id),
                'type_activite_id': str(liaison.type_activite.id),
                'type_activite_nom': liaison.type_activite.nomtype,
                'is_active': liaison.is_active,
                'notes': liaison.notes or '',
                'created_at': liaison.created_at.strftime('%d/%m/%Y %H:%M') if liaison.created_at else ''
            })

        return Response({
            'designation_nom': designation.nom,
            'types_activites': data
        })
    except Exception as e:
        return Response({
            'error': f'Erreur lors du chargement: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def types_activites_disponibles(request):
    """Lister tous les types d'activités disponibles"""
    try:
        types = TypeActivite.objects.all().order_by('nomtype')
        data = []
        for type_activite in types:
            data.append({
                'id': str(type_activite.id),
                'nom': type_activite.nomtype
            })
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors du chargement: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def designation_type_activite_create(request):
    """Créer une liaison désignation-type activité"""
    try:
        data = json.loads(request.body)
        designation = get_object_or_404(Designation, id=data.get('designation_id'))
        type_activite = get_object_or_404(TypeActivite, id=data.get('type_activite_id'))

        # Vérifier si la liaison existe déjà
        if DesignationTypeActivite.objects.filter(designation=designation, type_activite=type_activite).exists():
            return JsonResponse({
                'success': False,
                'message': 'Cette liaison existe déjà'
            }, status=400)

        liaison = DesignationTypeActivite.objects.create(
            designation=designation,
            type_activite=type_activite,
            notes=data.get('notes', '').strip(),
            is_active=data.get('is_active', True)
        )

        return JsonResponse({
            'success': True,
            'message': 'Liaison créée avec succès',
            'data': {
                'id': str(liaison.id),
                'type_activite_nom': liaison.type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def designation_type_activite_detail(request, liaison_id):
    """Récupérer les détails d'une liaison désignation-type activité"""
    try:
        liaison = get_object_or_404(DesignationTypeActivite, id=liaison_id)
        data = {
            'id': str(liaison.id),
            'designation_id': liaison.designation.id,
            'designation_nom': liaison.designation.nom,
            'type_activite_id': str(liaison.type_activite.id),
            'type_activite_nom': liaison.type_activite.nomtype,
            'notes': liaison.notes or '',
            'is_active': liaison.is_active
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors du chargement: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def designation_type_activite_update(request, liaison_id):
    """Modifier une liaison désignation-type activité"""
    try:
        liaison = get_object_or_404(DesignationTypeActivite, id=liaison_id)
        data = json.loads(request.body)

        # Vérifier si on change le type d'activité et que la nouvelle liaison n'existe pas déjà
        new_type_activite_id = data.get('type_activite_id')
        if new_type_activite_id and str(liaison.type_activite.id) != new_type_activite_id:
            new_type_activite = get_object_or_404(TypeActivite, id=new_type_activite_id)
            if DesignationTypeActivite.objects.filter(
                designation=liaison.designation,
                type_activite=new_type_activite
            ).exclude(id=liaison.id).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Une liaison avec ce type d\'activité existe déjà'
                }, status=400)
            liaison.type_activite = new_type_activite

        liaison.notes = data.get('notes', liaison.notes or '').strip()
        liaison.is_active = data.get('is_active', liaison.is_active)
        liaison.save()

        return JsonResponse({
            'success': True,
            'message': 'Liaison modifiée avec succès',
            'data': {
                'id': str(liaison.id),
                'type_activite_nom': liaison.type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def designation_type_activite_delete(request, liaison_id):
    """Supprimer une liaison désignation-type activité"""
    try:
        liaison = get_object_or_404(DesignationTypeActivite, id=liaison_id)
        type_activite_nom = liaison.type_activite.nomtype
        liaison.delete()
        return JsonResponse({
            'success': True,
            'message': f'Liaison avec "{type_activite_nom}" supprimée avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)
