from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import TypeActivite, GroupeTypeActivite, Activite, ActivitePoste, TypeDesignation, Designation, DesignationCompte
import json


def _get_request_organisation(request):
    organisation = None
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        employe = getattr(user, 'employe', None)
        if employe:
            base = getattr(employe, 'base', None)
            organisation = getattr(base, 'organisation', None) if base else None
            if not organisation:
                poste_user = getattr(employe, 'poste', None)
                organisation = getattr(poste_user, 'organisation', None) if poste_user else None
    return organisation


def _scope_activite_poste_queryset_for_request(queryset, request):
    user = getattr(request, 'user', None)
    organisation = _get_request_organisation(request)
    if organisation and not getattr(user, 'is_superuser', False):
        return queryset.filter(poste__organisation=organisation)
    return queryset


def _scope_poste_queryset_for_request(queryset, request):
    user = getattr(request, 'user', None)
    organisation = _get_request_organisation(request)
    if organisation and not getattr(user, 'is_superuser', False):
        return queryset.filter(organisation=organisation)
    return queryset


def _resolve_groupe(value):
    if not value:
        return None
    return GroupeTypeActivite.objects.filter(id=value).first()


# ===== VUES TABLEAUX (Style organisation/géographie) =====

def type_activite_table(request):
    """Page tableau avec cascade pour les types d'activités"""
    from apps.employees.permissions import is_directeur_poste
    context = {
        'title': 'Gestion des Types d\'Activités',
        'is_directeur_poste': is_directeur_poste(request.user)
    }
    return render(request, 'planning/crud/type_activite_table.html', context)


# ===== CRUD Groupes de types d'activités =====

def _groupe_dict(g):
    return {
        'id': str(g.id), 'nom': g.nom, 'icone': g.icone or 'fa-layer-group',
        'ordre': g.ordre, 'types_count': g.types.count(),
    }


def _groupe_fields(data, groupe=None):
    nom = (data.get('nom') if 'nom' in data else getattr(groupe, 'nom', '') or '').strip()
    if not nom:
        raise ValueError('Le nom du groupe est obligatoire')
    if GroupeTypeActivite.objects.filter(nom__iexact=nom).exclude(
            id=getattr(groupe, 'id', None)).exists():
        raise ValueError('Un groupe portant ce nom existe déjà')
    icone = (data.get('icone') or 'fa-layer-group').strip() or 'fa-layer-group'
    try:
        ordre = int(data.get('ordre', getattr(groupe, 'ordre', 0)))
    except (TypeError, ValueError):
        ordre = 0
    return nom, icone, ordre


@api_view(['GET'])
@permission_classes([AllowAny])
def groupe_type_activite_api(request):
    return Response([_groupe_dict(g) for g in GroupeTypeActivite.objects.all()])


@csrf_exempt
@require_http_methods(["POST"])
def groupe_type_activite_create(request):
    try:
        nom, icone, ordre = _groupe_fields(json.loads(request.body))
        g = GroupeTypeActivite.objects.create(nom=nom, icone=icone, ordre=ordre)
        return JsonResponse({'success': True, 'data': _groupe_dict(g)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def groupe_type_activite_update(request, groupe_id):
    try:
        g = get_object_or_404(GroupeTypeActivite, id=groupe_id)
        g.nom, g.icone, g.ordre = _groupe_fields(json.loads(request.body), g)
        g.save()
        return JsonResponse({'success': True, 'data': _groupe_dict(g)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def groupe_type_activite_delete(request, groupe_id):
    g = get_object_or_404(GroupeTypeActivite, id=groupe_id)
    n = g.types.count()
    if n:
        return JsonResponse({
            'success': False,
            'message': f"Impossible de supprimer: {n} type(s) d'activité sont rattachés à ce groupe"
        }, status=400)
    g.delete()
    return JsonResponse({'success': True, 'message': 'Groupe supprimé'})


# ===== CRUD TypeActivite =====

def type_activite_list(request):
    """Liste des types d'activités"""
    types_activites = TypeActivite.objects.all().order_by('nomtype')
    context = {
        'types_activites': types_activites,
        'title': 'Types d\'Activités'
    }
    return render(request, 'planning/crud/type_activite_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def type_activite_api(request):
    """API pour récupérer les types d'activités"""
    types = TypeActivite.objects.all().order_by('nomtype')
    data = []
    for type_act in types:
        data.append({
            'id': str(type_act.id),
            'nomtype': type_act.nomtype,
            'groupe_id': str(type_act.groupe_id) if type_act.groupe_id else None,
            'createdat': type_act.createdat.isoformat() if type_act.createdat else None,
            'activites_count': type_act.activites.count() if hasattr(type_act, 'activites') else 0,
            'fiches_poste_count': type_act.fiches_poste.count() if hasattr(type_act, 'fiches_poste') else 0
        })
    return Response(data)


@csrf_exempt
@require_http_methods(["POST"])
def type_activite_create(request):
    """Créer un nouveau type d'activité"""
    try:
        data = json.loads(request.body)
        type_activite = TypeActivite.objects.create(
            nomtype=data.get('nomtype', '').strip(),
            groupe=_resolve_groupe(data.get('groupe_id')),
        )
        return JsonResponse({
            'success': True,
            'message': 'Type d\'activité créé avec succès',
            'data': {
                'id': str(type_activite.id),
                'nomtype': type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def type_activite_update(request, type_id):
    """Modifier un type d'activité"""
    try:
        type_activite = get_object_or_404(TypeActivite, id=type_id)
        data = json.loads(request.body)
        type_activite.nomtype = data.get('nomtype', type_activite.nomtype).strip()
        if 'groupe_id' in data:
            type_activite.groupe = _resolve_groupe(data.get('groupe_id'))
        type_activite.save()

        return JsonResponse({
            'success': True,
            'message': 'Type d\'activité modifié avec succès',
            'data': {
                'id': str(type_activite.id),
                'nomtype': type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def type_activite_delete(request, type_id):
    """Supprimer un type d'activité"""
    try:
        type_activite = get_object_or_404(TypeActivite, id=type_id)

        # Les « activités » héritées (table activites) n'apparaissent pas sur la page : seules
        # celles encore utilisées par une activité de poste bloquent la suppression.
        # Les autres, orphelines, sont supprimées avec le type.
        bloquantes = list(
            type_activite.activites.filter(activites_postes__isnull=False).distinct()
        )
        if bloquantes:
            noms = ', '.join(a.nom for a in bloquantes[:5])
            return JsonResponse({
                'success': False,
                'message': (
                    f'Impossible de supprimer: {len(bloquantes)} activité(s) encore utilisée(s) '
                    f'par des activités de poste sont liées à ce type ({noms}). '
                    "Détachez-les ou supprimez-les d'abord."
                )
            }, status=400)

        type_activite.delete()
        return JsonResponse({
            'success': True,
            'message': 'Type d\'activité supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


# ===== CRUD Activite =====

def activite_list(request, type_activite_id=None):
    """Liste des activités (optionnellement filtrées par type)"""
    if type_activite_id:
        type_activite = get_object_or_404(TypeActivite, id=type_activite_id)
        activites = Activite.objects.filter(type_activite=type_activite).order_by('nom')
        context = {
            'activites': activites,
            'type_activite': type_activite,
            'title': f'Activités - {type_activite.nomtype}'
        }
    else:
        activites = Activite.objects.all().order_by('type_activite__nomtype', 'nom')
        context = {
            'activites': activites,
            'title': 'Toutes les Activités'
        }
    return render(request, 'planning/crud/activite_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def activite_api(request, type_activite_id=None):
    """API pour récupérer les activités"""
    if type_activite_id:
        activites = Activite.objects.filter(type_activite_id=type_activite_id).order_by('nom')
    else:
        activites = Activite.objects.all().order_by('type_activite__nomtype', 'nom')

    data = []
    for activite in activites:
        # Gérer les relations orphelines
        try:
            type_activite_id = str(activite.type_activite.id) if activite.type_activite else None
            type_activite_nom = activite.type_activite.nomtype if activite.type_activite else 'Type supprimé'
        except:
            type_activite_id = None
            type_activite_nom = 'Type supprimé'

        data.append({
            'id': str(activite.id),
            'nom': activite.nom,
            'description': activite.description,
            'type_activite_id': type_activite_id,
            'type_activite_nom': type_activite_nom,
            'is_active': activite.is_active,
            'postes_count': activite.activites_postes.count()
        })
    return Response(data)


@csrf_exempt
@require_http_methods(["POST"])
def activite_create(request):
    """Créer une nouvelle activité"""
    try:
        data = json.loads(request.body)
        type_activite = get_object_or_404(TypeActivite, id=data.get('type_activite'))

        activite = Activite.objects.create(
            nom=data.get('nom', '').strip(),
            description=data.get('description', '').strip(),
            type_activite=type_activite,
            is_active=data.get('is_active', True)
        )

        return JsonResponse({
            'success': True,
            'message': 'Activité créée avec succès',
            'data': {
                'id': str(activite.id),
                'nom': activite.nom,
                'type_activite_nom': type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def activite_update(request, activite_id):
    """Modifier une activité"""
    try:
        activite = get_object_or_404(Activite, id=activite_id)
        data = json.loads(request.body)

        # Supporter Ã  la fois type_activite_id et type_activite
        type_id = data.get('type_activite_id') or data.get('type_activite')
        if type_id:
            type_activite = get_object_or_404(TypeActivite, id=type_id)
            activite.type_activite = type_activite

        activite.nom = data.get('nom', activite.nom).strip()
        activite.description = data.get('description', activite.description or '').strip()
        activite.is_active = data.get('is_active', activite.is_active)
        activite.save()

        return JsonResponse({
            'success': True,
            'message': 'Activité modifiée avec succès',
            'data': {
                'id': str(activite.id),
                'nom': activite.nom,
                'type_activite_nom': activite.type_activite.nomtype
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def activite_delete(request, activite_id):
    """Supprimer une activité"""
    try:
        activite = get_object_or_404(Activite, id=activite_id)

        # Vérifier s'il y a des activités de poste liées
        postes_count = activite.activites_postes.count()
        if postes_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Impossible de supprimer: {postes_count} activité(s) de poste sont liées'
            }, status=400)

        activite.delete()
        return JsonResponse({
            'success': True,
            'message': 'Activité supprimée avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


# ===== CRUD ActivitePoste =====

def activite_poste_list(request, activite_id=None):
    """Liste des activités de poste (optionnellement filtrées par activité)"""
    if activite_id:
        activite = get_object_or_404(Activite, id=activite_id)
        activites_postes = ActivitePoste.objects.filter(activite=activite).order_by('nom')
        context = {
            'activites_postes': activites_postes,
            'activite': activite,
            'title': f'Activités de Poste - {activite.nom}'
        }
    else:
        activites_postes = ActivitePoste.objects.all().order_by('activite__nom', 'nom')
        context = {
            'activites_postes': activites_postes,
            'title': 'Toutes les Activités de Poste'
        }
    return render(request, 'planning/crud/activite_poste_list.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def activite_poste_api(request, activite_id=None, fiche_id=None):
    """API pour recuperer les liaisons poste / fiche de poste."""
    try:
        if fiche_id:
            postes = (
                ActivitePoste.objects
                .filter(fiche_poste_id=fiche_id)
                .select_related('poste', 'activite__type_activite', 'fiche_poste')
                .order_by('poste__ordre_affichage', 'poste__nom_poste', 'nom')
            )
        elif activite_id:
            postes = (
                ActivitePoste.objects
                .filter(activite_id=activite_id)
                .select_related('poste', 'activite__type_activite', 'fiche_poste')
                .order_by('poste__ordre_affichage', 'poste__nom_poste', 'nom')
            )
        else:
            postes = (
                ActivitePoste.objects
                .select_related('poste', 'activite__type_activite', 'fiche_poste')
                .order_by('poste__ordre_affichage', 'poste__nom_poste', 'nom')
            )

        postes = _scope_activite_poste_queryset_for_request(postes, request)

        data = []
        for activite_poste in postes:
            poste_nom = activite_poste.poste.nom_poste if activite_poste.poste else activite_poste.nom
            poste_id = str(activite_poste.poste.id) if activite_poste.poste else None

            activite = activite_poste.activite
            type_activite = activite.type_activite if activite else None
            activite_id_val = str(activite.id) if activite else None
            activite_nom = activite.nom if activite else None
            type_activite_id = str(type_activite.id) if type_activite else None
            type_activite_nom = type_activite.nomtype if type_activite else None

            data.append({
                'id': str(activite_poste.id),
                'nom': activite_poste.nom,
                'description': activite_poste.description,
                'activite_id': activite_id_val,
                'activite_nom': activite_nom,
                'type_activite_nom': type_activite_nom,
                'type_activite_id': type_activite_id,
                'poste_id': poste_id,
                'poste_nom': poste_nom,
                'fiche_poste_id': str(activite_poste.fiche_poste.id) if activite_poste.fiche_poste else None,
                'fiche_poste_tache': activite_poste.fiche_poste.tache if activite_poste.fiche_poste else None,
                'is_active': activite_poste.is_active,
                'frequence_mois': activite_poste.frequence_mois,
                'mode_frequence': activite_poste.mode_frequence,
                'created_at': activite_poste.created_at.isoformat() if activite_poste.created_at else None
            })
        return Response(data)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


def _resolve_activite_for_fiche_poste(fiche_poste, requested_activite_id=None):
    """Resout une activite technique pour conserver la compatibilite du modele."""
    if requested_activite_id:
        return get_object_or_404(Activite, id=requested_activite_id)

    existing_link = (
        ActivitePoste.objects
        .filter(fiche_poste=fiche_poste, activite__isnull=False)
        .select_related('activite')
        .order_by('-is_active', 'activite__is_active', 'activite__nom')
        .first()
    )
    if existing_link and existing_link.activite:
        return existing_link.activite

    type_activite_id = getattr(fiche_poste, 'type_activites_id', None)
    if not type_activite_id:
        poste = None
        try:
            poste = getattr(fiche_poste, 'poste', None)
        except Exception:
            poste = None

        if poste:
            poste_link = (
                ActivitePoste.objects
                .filter(poste=poste, activite__isnull=False)
                .select_related('activite')
                .order_by('-is_active', 'activite__is_active', 'activite__nom')
                .first()
            )
            if poste_link and poste_link.activite:
                return poste_link.activite

        fallback_activite = (
            Activite.objects
            .filter(is_active=True)
            .order_by('nom')
            .first()
        )
        if fallback_activite:
            return fallback_activite

        return None

    activite = (
        Activite.objects
        .filter(type_activite_id=type_activite_id, is_active=True)
        .order_by('nom')
        .first()
    )
    if activite:
        return activite

    return (
        Activite.objects
        .filter(type_activite_id=type_activite_id)
        .order_by('nom')
        .first()
    )


@csrf_exempt
@require_http_methods(["POST"])
def activite_poste_create(request):
    """Creer une nouvelle liaison poste pour une fiche de poste."""
    try:
        from apps.employees.models import Poste
        from apps.employees.models_evaluation import FichePoste
        data = json.loads(request.body)

        poste = get_object_or_404(Poste, id=data.get('poste_id'))
        fiche_poste = None
        if data.get('fiche_poste_id'):
            fiche_poste = get_object_or_404(FichePoste, id=data.get('fiche_poste_id'))

        activite_id = data.get('activite_id')
        activite = (
            _resolve_activite_for_fiche_poste(fiche_poste)
            if fiche_poste else
            get_object_or_404(Activite, id=activite_id)
        )
        if not activite:
            # Dernier recours: utiliser une activité active générique
            activite = Activite.objects.filter(is_active=True).order_by('nom').first()
        if not activite and fiche_poste:
            # Si aucune activité n'existe encore, créer une activité technique minimale
            type_default = TypeActivite.objects.filter(is_active=True).order_by('nomtype').first()
            if type_default:
                activite = Activite.objects.create(
                    nom=fiche_poste.tache or 'Activite technique',
                    description='Activite technique auto-geree pour liaison poste',
                    type_activite=type_default,
                    is_active=True,
                )
        if not activite:
            return JsonResponse({
                'success': False,
                'message': 'Aucune activite technique disponible pour cette liaison'
            }, status=400)

        existing = (
            ActivitePoste.objects.filter(fiche_poste=fiche_poste, poste=poste).first()
            if fiche_poste else
            ActivitePoste.objects.filter(activite=activite, poste=poste).first()
        )
        if existing:
            return JsonResponse({
                'success': False,
                'message': (
                    f'Ce poste est deja associe a la fiche "{fiche_poste.tache}"'
                    if fiche_poste else
                    f'Cette activite est deja associee au poste "{poste.nom_poste}"'
                )
            }, status=400)

        auto_label = fiche_poste.tache if fiche_poste else activite.nom
        activite_poste = ActivitePoste.objects.create(
            nom=f"{auto_label} - {poste.nom_poste}",
            description=f"Fiche {auto_label} pour le poste {poste.nom_poste}",
            activite=activite,
            poste=poste,
            fiche_poste=fiche_poste,
            is_active=data.get('is_active', True),
            frequence_mois=(int(data.get('frequence_mois')) if data.get('frequence_mois') not in [None, '', 'null'] else None),
            mode_frequence=(data.get('mode_frequence') if data.get('mode_frequence') not in [None, '', 'null'] else None)
        )

        return JsonResponse({
            'success': True,
            'message': 'Poste associe avec succes',
            'data': {
                'id': str(activite_poste.id),
                'nom': activite_poste.nom,
                'activite_nom': auto_label,
                'poste_nom': poste.nom_poste
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la creation: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def activite_poste_update(request, poste_id):
    """Modifier une liaison poste pour une fiche de poste."""
    try:
        from apps.employees.models import Poste as PosteModel
        from apps.employees.models_evaluation import FichePoste

        poste = get_object_or_404(ActivitePoste, id=poste_id)
        data = json.loads(request.body)
        activite_changed = False
        poste_changed = False
        original_nom = poste.nom
        original_description = poste.description or ''

        if 'fiche_poste_id' in data:
            if data['fiche_poste_id']:
                fiche_poste = get_object_or_404(FichePoste, id=data['fiche_poste_id'])
                poste.fiche_poste = fiche_poste
                resolved_activite = _resolve_activite_for_fiche_poste(fiche_poste)
                if resolved_activite and poste.activite_id != resolved_activite.id:
                    poste.activite = resolved_activite
                    activite_changed = True
            else:
                poste.fiche_poste = None

        if 'activite_id' in data and data.get('activite_id'):
            activite = get_object_or_404(Activite, id=data['activite_id'])
            if poste.activite_id != activite.id:
                poste.activite = activite
                activite_changed = True

        if poste.fiche_poste_id:
            resolved_activite = _resolve_activite_for_fiche_poste(poste.fiche_poste)
            if not resolved_activite:
                resolved_activite = Activite.objects.filter(is_active=True).order_by('nom').first()
            if not resolved_activite:
                return JsonResponse({
                    'success': False,
                    'message': 'Aucune activite technique disponible pour cette liaison'
                }, status=400)
            if poste.activite_id != resolved_activite.id:
                poste.activite = resolved_activite
                activite_changed = True

        if 'poste_id' in data:
            nouveau_poste = get_object_or_404(PosteModel, id=data['poste_id'])
            if poste.poste_id != nouveau_poste.id:
                poste.poste = nouveau_poste
                poste_changed = True

        if poste.fiche_poste_id and poste.poste_id:
            duplicate_exists = ActivitePoste.objects.filter(
                fiche_poste_id=poste.fiche_poste_id,
                poste_id=poste.poste_id,
            ).exclude(id=poste.id).exists()
            duplicate_message = 'Ce poste est deja associe a cette fiche de poste'
        elif poste.activite_id and poste.poste_id:
            duplicate_exists = ActivitePoste.objects.filter(
                activite_id=poste.activite_id,
                poste_id=poste.poste_id,
            ).exclude(id=poste.id).exists()
            duplicate_message = 'Cette activite est deja associee a ce poste'
        else:
            duplicate_exists = False
            duplicate_message = ''

        if duplicate_exists:
            return JsonResponse({
                'success': False,
                'message': duplicate_message,
            }, status=400)

        auto_label = poste.fiche_poste.tache if poste.fiche_poste else (poste.activite.nom if poste.activite else 'Liaison')
        auto_nom = original_nom
        auto_description = original_description
        if poste.poste:
            auto_nom = f"{auto_label} - {poste.poste.nom_poste}"
            auto_description = f"Fiche {auto_label} pour le poste {poste.poste.nom_poste}"

        poste.nom = data.get('nom', auto_nom if (activite_changed or poste_changed) else original_nom).strip()
        poste.description = data.get(
            'description',
            auto_description if (activite_changed or poste_changed) else original_description
        ).strip()
        poste.is_active = data.get('is_active', poste.is_active)
        if 'frequence_mois' in data:
            poste.frequence_mois = int(data.get('frequence_mois')) if data.get('frequence_mois') not in [None, '', 'null'] else None
        if 'mode_frequence' in data:
            poste.mode_frequence = data.get('mode_frequence') if data.get('mode_frequence') not in [None, '', 'null'] else None
        poste.save()

        return JsonResponse({
            'success': True,
            'message': 'Liaison poste modifiee avec succes',
            'data': {
                'id': str(poste.id),
                'nom': poste.nom,
                'activite_nom': auto_label,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def activite_poste_delete(request, poste_id):
    """Supprimer une activité de poste"""
    try:
        poste = get_object_or_404(ActivitePoste, id=poste_id)
        poste.delete()
        return JsonResponse({
            'success': True,
            'message': 'Activité de poste supprimée avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


# ===== APIs pour récupérer les données individuelles =====

@api_view(['GET'])
@permission_classes([AllowAny])
def type_activite_detail(request, type_id):
    """API pour récupérer un type d'activité spécifique"""
    try:
        type_activite = get_object_or_404(TypeActivite, id=type_id)
        data = {
            'id': str(type_activite.id),
            'nomtype': type_activite.nomtype,
            'groupe_id': str(type_activite.groupe_id) if type_activite.groupe_id else None,
            'createdat': type_activite.createdat.isoformat() if type_activite.createdat else None
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def activite_detail(request, activite_id):
    """API pour récupérer une activité spécifique"""
    try:
        activite = get_object_or_404(Activite, id=activite_id)
        data = {
            'id': str(activite.id),
            'nom': activite.nom,
            'description': activite.description or '',
            'type_activite_id': str(activite.type_activite.id) if activite.type_activite else None,
            'type_activite_nom': activite.type_activite.nomtype if activite.type_activite else 'Type supprimé',
            'is_active': activite.is_active
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def activite_poste_detail(request, poste_id):
    """API pour r??cup??rer une activité de poste spécifique"""
    try:
        activite_poste = get_object_or_404(ActivitePoste, id=poste_id)
        data = {
            'id': str(activite_poste.id),
            'nom': activite_poste.nom,
            'description': activite_poste.description or '',
            'activite_id': str(activite_poste.activite.id),
            'activite_nom': activite_poste.activite.nom,
            'poste_id': str(activite_poste.poste.id) if activite_poste.poste else None,
            'poste_nom': activite_poste.poste.nom_poste if activite_poste.poste else None,
            'fiche_poste_id': str(activite_poste.fiche_poste.id) if activite_poste.fiche_poste else None,
            'fiche_poste_tache': activite_poste.fiche_poste.tache if activite_poste.fiche_poste else None,
            'is_active': activite_poste.is_active
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la r??cup??ration: {str(e)}'
        }, status=400)


# ===== API pour charger les postes =====

@api_view(['GET'])
@permission_classes([AllowAny])
def postes_api(request):
    """API pour récupérer tous les postes disponibles"""
    try:
        from apps.employees.models import Poste

        postes = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')
        postes = _scope_poste_queryset_for_request(postes, request)
        data = []
        for poste in postes:
            data.append({
                'id': str(poste.id),
                'nom_poste': poste.nom_poste,
                'organisation_id': str(poste.organisation_id) if poste.organisation_id else None,
                'organisation_nom': poste.organisation.nom_organisation if poste.organisation else 'Organisation non définie'
            })
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des postes: {str(e)}'
        }, status=400)


# ===== CRUD FichePoste =====

def fiche_poste_table(request):
    """Page de gestion des Fiches de Poste, vue depuis le poste"""
    context = {
        'title': 'Gestion des Fiches de Poste'
    }
    return render(request, 'planning/crud/fiche_poste_par_poste.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def fiche_poste_orphelines(request):
    """API pour récupérer les fiches de poste sans type d'activité"""
    try:
        from apps.employees.models_evaluation import FichePoste
        fiches = FichePoste.objects.filter(type_activites__isnull=True).order_by('tache')
        data = [{'id': str(f.id), 'tache': f.tache} for f in fiches]
        return Response(data)
    except Exception as e:
        return Response({'error': str(e)}, status=400)


def _regles_fiche_payload(fiche):
    """Règles brutes (paramétrées) et règles effectives (après cohérence cible/composants)."""
    from apps.planning.reparation_composants import regles_fiche
    return {
        'cible_mode': fiche.cible_mode,
        'cible_types': fiche.cible_types,
        'composants_mode': fiche.composants_mode,
        'composants_multiple': fiche.composants_multiple,
        'composants_admis': fiche.composants_admis,
        'regles': regles_fiche(fiche),
    }


def _appliquer_regles_fiche(fiche, data):
    """Copie les règles reçues sur la fiche ; lève ValueError si une valeur est invalide."""
    from apps.employees.models_evaluation import FichePoste
    modes = {c[0] for c in FichePoste.MODE_CHOICES}
    types = {c[0] for c in FichePoste.CIBLE_TYPES_CHOICES}
    for champ, valides in (('cible_mode', modes), ('composants_mode', modes), ('cible_types', types)):
        if champ in data and data[champ] not in (None, ''):
            if data[champ] not in valides:
                raise ValueError(f"Valeur invalide pour {champ}")
            setattr(fiche, champ, data[champ])
    if 'composants_multiple' in data:
        fiche.composants_multiple = bool(data['composants_multiple'])
    if 'composants_admis' in data:
        fiche.composants_admis = '\n'.join(
            ligne.strip() for ligne in str(data['composants_admis'] or '').splitlines() if ligne.strip())


@api_view(['GET'])
@permission_classes([AllowAny])
def fiche_poste_api(request, type_id=None):
    """API pour récupérer les fiches de poste par type d'activité"""
    try:
        from apps.employees.models_evaluation import FichePoste
        
        if type_id:
            fiches = FichePoste.objects.filter(type_activites_id=type_id).order_by('ordre', 'tache')
        else:
            # Inclure aussi les fiches orphelines (type_activites=None).
            fiches = FichePoste.objects.all().order_by('ordre', 'tache')
        
        fiche_ids = list(fiches.values_list('id', flat=True))
        postes_counts = {
            str(item['fiche_poste_id']): item['count']
            for item in ActivitePoste.objects.filter(
                fiche_poste_id__in=fiche_ids
            ).values('fiche_poste_id').annotate(count=Count('id'))
        }

        from apps.planning.models import Planning
        plannings_counts = {
            str(item['fiche_poste_id']): item['count']
            for item in Planning.objects.filter(
                fiche_poste_id__in=fiche_ids
            ).values('fiche_poste_id').annotate(count=Count('id'))
        }

        data = []
        for fiche in fiches:
            data.append({
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'plannings_count': plannings_counts.get(str(fiche.id), 0),
                **_regles_fiche_payload(fiche),
                'ordre': fiche.ordre,
                'a_evaluer': fiche.a_evaluer,
                'dans_planning': fiche.dans_planning,
                'preuve_obligatoire': fiche.preuve_obligatoire,
            'preuve_type': fiche.preuve_type,
                'preuve_type': fiche.preuve_type,
                'postes_count': postes_counts.get(str(fiche.id), 0),
                'type_activites_id': str(fiche.type_activites.id) if fiche.type_activites else None,
                'type_activites_nom': fiche.type_activites.nomtype if fiche.type_activites else None,
                'date_creation': fiche.date_creation.isoformat() if fiche.date_creation else None
            })
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des fiches de poste: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def fiche_poste_create(request):
    """Créer une nouvelle fiche de poste"""
    try:
        from apps.employees.models_evaluation import FichePoste
        data = json.loads(request.body)
        
        # Type d'activités (optionnel)
        type_id = data.get('type_activites') or data.get('type_activite_id')
        type_activites = None
        if type_id:
            type_activites = get_object_or_404(TypeActivite, id=type_id)
        
        fiche = FichePoste.objects.create(
            type_activites=type_activites,
            tache=data.get('tache', '').strip(),
            description=data.get('description', '').strip(),
            outils=data.get('outils', '').strip(),
            ordre=data.get('ordre', 0),
            a_evaluer=data.get('a_evaluer', False),
            dans_planning=data.get('dans_planning', False),
            preuve_obligatoire=data.get('preuve_obligatoire', False),
            preuve_type=data.get('preuve_type') or 'piece_jointe'
        )
        _appliquer_regles_fiche(fiche, data)
        fiche.save()

        return JsonResponse({
            'success': True,
            'message': 'Fiche de poste créée avec succès',
            'data': {
                'id': str(fiche.id),
                'tache': fiche.tache,
                'type_activites_nom': type_activites.nomtype if type_activites else None
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la création: {str(e)}'
        }, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def fiche_poste_detail(request, fiche_id):
    """API pour récupérer une fiche de poste spécifique"""
    try:
        from apps.employees.models_evaluation import FichePoste
        
        fiche = get_object_or_404(FichePoste, id=fiche_id)
        data = {
            'id': str(fiche.id),
            'tache': fiche.tache,
            'description': fiche.description or '',
            'outils': fiche.outils or '',
            'ordre': fiche.ordre,
            'a_evaluer': fiche.a_evaluer,
            'dans_planning': fiche.dans_planning,
            'preuve_obligatoire': fiche.preuve_obligatoire,
            'preuve_type': fiche.preuve_type,
                'preuve_type': fiche.preuve_type,
            'type_activites_id': str(fiche.type_activites.id) if fiche.type_activites else None,
            'type_activites_nom': fiche.type_activites.nomtype if fiche.type_activites else None,
            **_regles_fiche_payload(fiche),
        }
        return Response(data)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def fiche_poste_update(request, fiche_id):
    """Modifier une fiche de poste"""
    try:
        from apps.employees.models_evaluation import FichePoste

        fiche = get_object_or_404(FichePoste, id=fiche_id)
        data = json.loads(request.body)

        # Mise ?? jour du type d'activités si fourni
        if 'type_activites' in data or 'type_activites_id' in data or 'type_activite_id' in data:
            type_id = (
                data.get('type_activites')
                or data.get('type_activites_id')
                or data.get('type_activite_id')
            )
            if type_id:
                type_activites = get_object_or_404(TypeActivite, id=type_id)
                fiche.type_activites = type_activites

        # Mise ?? jour des autres champs
        fiche.tache = data.get('tache', fiche.tache).strip()
        fiche.description = data.get('description', fiche.description or '').strip()
        fiche.outils = data.get('outils', fiche.outils or '').strip()
        fiche.ordre = data.get('ordre', fiche.ordre)
        fiche.a_evaluer = data.get('a_evaluer', fiche.a_evaluer)
        fiche.dans_planning = data.get('dans_planning', fiche.dans_planning)
        fiche.preuve_obligatoire = data.get('preuve_obligatoire', fiche.preuve_obligatoire)
        if 'preuve_type' in data:
            fiche.preuve_type = data.get('preuve_type') or fiche.preuve_type
        _appliquer_regles_fiche(fiche, data)
        fiche.save()

        return JsonResponse({
            'success': True,
            'message': 'Fiche de poste modifiée avec succès',
            'data': {
                'id': str(fiche.id),
                'tache': fiche.tache,
                'type_activites_nom': fiche.type_activites.nomtype if fiche.type_activites else None
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la modification: {str(e)}'
        }, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def fiche_poste_delete(request, fiche_id):
    """Supprimer une fiche de poste"""
    try:
        from apps.employees.models_evaluation import FichePoste
        
        fiche = get_object_or_404(FichePoste, id=fiche_id)
        
        # Vérifier s'il y a des activités de poste liées
        activites_postes_count = fiche.activites_postes.count() if hasattr(fiche, 'activites_postes') else 0
        if activites_postes_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Impossible de supprimer: {activites_postes_count} activité(s) de poste sont liées Ã  cette fiche'
            }, status=400)
        
        # Vérifier s'il y a des évaluations liées
        evaluations_count = fiche.evaluations.count() if hasattr(fiche, 'evaluations') else 0
        if evaluations_count > 0:
            return JsonResponse({
                'success': False,
                'message': f'Impossible de supprimer: {evaluations_count} évaluation(s) sont liées Ã  cette fiche'
            }, status=400)
        
        fiche.delete()
        return JsonResponse({
            'success': True,
            'message': 'Fiche de poste supprimée avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de la suppression: {str(e)}'
        }, status=400)


# ===== Vue "par poste" : fiches de poste d'un poste =====

def fiche_poste_table_classique(request):
    """Ancienne gestion centrée sur la fiche (catégorie > fiche > postes)."""
    return render(request, 'planning/crud/fiche_poste_list.html', {
        'title': 'Gestion des Fiches de Poste (vue par fiche)'
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def poste_fiches_api(request, poste_id):
    """Fiches de poste d'un poste, avec leurs paramètres et les AUTRES postes qui les partagent.

    Les paramètres (a_evaluer, dans_planning, preuve_*) sont portés par la fiche et donc
    communs à tous les postes qui l'utilisent : `autres_postes` permet d'en mesurer l'impact.
    """
    try:
        from apps.employees.models import Poste

        poste = get_object_or_404(_scope_poste_queryset_for_request(Poste.objects.all(), request), id=poste_id)
        liaisons = list(
            ActivitePoste.objects
            .filter(poste=poste, fiche_poste__isnull=False)
            .select_related('fiche_poste', 'fiche_poste__type_activites')
            .order_by('fiche_poste__type_activites__nomtype', 'fiche_poste__ordre', 'fiche_poste__tache')
        )
        fiche_ids = [l.fiche_poste_id for l in liaisons]

        autres = {}
        for ap in (
            ActivitePoste.objects
            .filter(fiche_poste_id__in=fiche_ids)
            .exclude(poste=poste)
            .select_related('poste')
            .order_by('poste__nom_poste')
        ):
            if ap.poste:
                autres.setdefault(ap.fiche_poste_id, []).append(
                    {'id': str(ap.poste_id), 'nom': ap.poste.nom_poste})

        from apps.planning.models import Planning
        plannings = {
            r['fiche_poste_id']: r['n']
            for r in Planning.objects.filter(fiche_poste_id__in=fiche_ids)
            .values('fiche_poste_id').annotate(n=Count('id'))
        }
        from apps.employees.models_evaluation import EvaluationDetail
        evaluations = {
            r['fiche_poste_id']: r['n']
            for r in EvaluationDetail.objects.filter(fiche_poste_id__in=fiche_ids)
            .values('fiche_poste_id').annotate(n=Count('id'))
        }

        data = []
        for l in liaisons:
            f = l.fiche_poste
            data.append({
                'liaison_id': str(l.id),
                'liaison_active': l.is_active,
                'frequence_mois': l.frequence_mois,
                'mode_frequence': l.mode_frequence,
                'fiche_id': str(f.id),
                'tache': f.tache,
                'description': f.description,
                'ordre': f.ordre,
                'type_activites_id': str(f.type_activites_id) if f.type_activites_id else None,
                'type_activites_nom': f.type_activites.nomtype if f.type_activites else None,
                'a_evaluer': f.a_evaluer,
                'dans_planning': f.dans_planning,
                'preuve_obligatoire': f.preuve_obligatoire,
                'preuve_type': f.preuve_type,
                'autres_postes': autres.get(f.id, []),
                'plannings_count': plannings.get(f.id, 0),
                'evaluations_count': evaluations.get(f.id, 0),
            })
        return Response({'poste': {'id': str(poste.id), 'nom': poste.nom_poste}, 'fiches': data})
    except Exception as e:
        return Response({'error': str(e)}, status=400)


