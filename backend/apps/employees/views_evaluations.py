"""
Vues pour le workflow d'évaluation des employés
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db.models import Q, Avg, Count
import json
from datetime import datetime
import re
import unicodedata

from apps.employees.models import Employe
from apps.organization.models import Base
from apps.employees.models_evaluation import Evaluation, EvaluationDetail, FichePoste
from apps.employees.permissions import employe_required
from apps.organization.scoping import apply_employee_organisation_scope, resolve_employee_organisation_scope


def _organisation_scope(request):
    """Périmètre d'affichage des pages d'évaluation (sélecteur ?organisation=, superuser : tout par défaut)."""
    return resolve_employee_organisation_scope(
        request.user, request.GET.get('organisation', ''), superuser_default_all=True,
    )


def _employes_visibles(request):
    """Employés que l'utilisateur peut évaluer ou consulter : toutes les organisations de son périmètre."""
    scope = resolve_employee_organisation_scope(request.user, 'all', superuser_default_all=True)
    return apply_employee_organisation_scope(Employe.objects.all(), scope)


AUTO_SAISIE_POSTES = {
    "assistant admin",
    "assistant e admin",
    "assistante admin",
    "responsable operationnel",
    "responsable administratif et financier",
}

AUTO_RECOUVREMENT_POSTES = {
    "agent de recouvrement",
    "agent de recouvrement superviseur technique",
}


def _normalize_poste_name(poste_nom):
    if not poste_nom:
        return ""
    normalized = unicodedata.normalize("NFKD", poste_nom)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", ascii_only.casefold())
    return " ".join(cleaned.split())


def _poste_in_set(poste_nom, allowed_postes):
    return _normalize_poste_name(poste_nom) in allowed_postes


def _get_fiches_for_poste(poste):
    """Retourne les fiches de poste liées à un poste via ActivitePoste.

    Fallback: si aucun lien direct, tenter un match sur le nom du poste
    quand les ActivitePoste n'ont pas de poste renseigné.
    """
    if not poste:
        return FichePoste.objects.none()

    fiches = FichePoste.objects.filter(
        activites_postes__poste=poste,
        a_evaluer=True
    ).distinct()

    if fiches.exists():
        return fiches.order_by('ordre', 'tache')

    # Fallback : certains activites_postes ont le poste manquant, mais le nom contient le poste
    poste_nom = (poste.nom_poste or '').strip()
    if not poste_nom:
        return fiches.order_by('ordre', 'tache')

    return FichePoste.objects.filter(
        activites_postes__poste__isnull=True,
        activites_postes__nom__icontains=poste_nom,
        a_evaluer=True
    ).distinct().order_by('ordre', 'tache')


@employe_required
def evaluations_list(request):
    """Page de liste des évaluations"""
    # Filtrer les employés actifs (sans date de débauchage)
    employes = Employe.objects.filter(date_debauchage__isnull=True)

    # Périmètre : organisation de l'utilisateur, avec bascule pour les superusers et les partenaires
    organisation_scope = _organisation_scope(request)
    employes = apply_employee_organisation_scope(employes, organisation_scope)
    bases = Base.objects.all()
    if organisation_scope['organisations'] is not None:
        bases = bases.filter(organisation__in=organisation_scope['organisations'])

    employes = employes.order_by('surnom', 'nom', 'prenom')
    bases = bases.order_by('nom_base')

    context = {
        'employes': employes,
        'bases': bases,
        'organisation_options': organisation_scope['options'],
        'organisation_selected': organisation_scope['selected'],
    }
    return render(request, 'employees/evaluations_list.html', context)


@employe_required
def evaluation_creer(request):
    """Page de création d'une nouvelle évaluation"""
    # Filtrer les employés actifs (sans date de débauchage), dans le périmètre de l'utilisateur
    employes = _employes_visibles(request).filter(date_debauchage__isnull=True).order_by('surnom', 'nom', 'prenom')

    current_evaluateur_id = None
    if hasattr(request.user, 'employe') and request.user.employe:
        current_evaluateur_id = str(request.user.employe.id)

    context = {
        'employes': employes,
        'current_evaluateur_id': current_evaluateur_id,
    }
    return render(request, 'employees/evaluation_creer.html', context)


@employe_required
def evaluation_detail(request, evaluation_id):
    """Page de détail/modification d'une évaluation"""
    from apps.employees.permissions import is_directeur_poste
    evaluation = get_object_or_404(
        Evaluation.objects.select_related('employe', 'evaluateur', 'employe__poste'),
        id=evaluation_id
    )

    # Récupérer toutes les évaluations précédentes de cet employé
    evaluations_historique = Evaluation.objects.filter(
        employe=evaluation.employe,
        statut='terminee'
    ).exclude(id=evaluation_id).order_by('-date_evaluation')

    # Filtrer les employés actifs (sans date de débauchage), dans le périmètre de l'utilisateur
    employes = _employes_visibles(request).filter(date_debauchage__isnull=True).order_by('surnom', 'nom', 'prenom')

    poste_nom = evaluation.employe.poste.nom_poste if evaluation.employe.poste else ""
    can_auto_saisie = _poste_in_set(poste_nom, AUTO_SAISIE_POSTES)
    can_auto_recouvrement = _poste_in_set(poste_nom, AUTO_RECOUVREMENT_POSTES)

    context = {
        'evaluation': evaluation,
        'evaluations_historique': evaluations_historique,
        'employes': employes,
        'is_directeur_poste': is_directeur_poste(request.user),
        'can_auto_saisie': can_auto_saisie,
        'can_auto_recouvrement': can_auto_recouvrement,
    }
    return render(request, 'employees/evaluation_detail.html', context)


@employe_required
@csrf_exempt
@require_http_methods(["GET"])
def api_evaluations_list(request):
    """API pour lister les évaluations avec filtres"""
    try:
        employe_id = request.GET.get('employe_id')
        evaluateur_id = request.GET.get('evaluateur_id')
        statut = request.GET.get('statut')
        annee = request.GET.get('annee')
        base_id = request.GET.get('base_id')

        evaluations = Evaluation.objects.select_related(
            'employe', 'evaluateur', 'employe__poste'
        ).all()

        # Périmètre : organisation de l'utilisateur, avec bascule (?organisation=) pour superusers et partenaires
        evaluations = apply_employee_organisation_scope(
            evaluations, _organisation_scope(request), field='employe__base__organisation',
        )

        # Filtres
        if base_id:
            evaluations = evaluations.filter(employe__base_id=base_id)
        if employe_id:
            evaluations = evaluations.filter(employe_id=employe_id)
        if evaluateur_id:
            evaluations = evaluations.filter(evaluateur_id=evaluateur_id)
        if statut:
            evaluations = evaluations.filter(statut=statut)
        if annee:
            evaluations = evaluations.filter(date_evaluation__year=annee)

        data = []
        for evaluation in evaluations:
            data.append({
                'id': str(evaluation.id),
                'employe_nom': evaluation.employe.surnom or evaluation.employe.nom_complet,
                'employe_poste': evaluation.employe.poste.nom_poste if evaluation.employe.poste else '-',
                'evaluateur_nom': evaluation.evaluateur.surnom if evaluation.evaluateur and evaluation.evaluateur.surnom else (evaluation.evaluateur.nom_complet if evaluation.evaluateur else '-'),
                'date_evaluation': evaluation.date_evaluation.strftime('%Y-%m-%d'),
                'periode_debut': evaluation.periode_debut.strftime('%Y-%m-%d'),
                'periode_fin': evaluation.periode_fin.strftime('%Y-%m-%d'),
                'est_auto_evaluation': evaluation.est_auto_evaluation,
                'statut': evaluation.statut,
                'note_totale': evaluation.note_totale,
                'note_maximale': evaluation.note_maximale,
                'pourcentage': evaluation.pourcentage,
            })

        return JsonResponse({
            'success': True,
            'evaluations': data,
            'count': len(data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["GET"])
def api_evaluation_detail(request, evaluation_id):
    """API pour récupérer le détail d'une évaluation avec toutes les notes"""
    try:
        evaluation = get_object_or_404(
            Evaluation.objects.select_related('employe', 'evaluateur'),
            id=evaluation_id
        )

        # Récupérer les détails avec les fiches de poste
        details = EvaluationDetail.objects.filter(
            evaluation=evaluation
        ).select_related('fiche_poste', 'fiche_poste__type_activites').order_by('fiche_poste__ordre', 'fiche_poste__tache')

        details_data = []
        for detail in details:
            fiche_poste = detail.fiche_poste
            type_activites = fiche_poste.type_activites if fiche_poste and fiche_poste.type_activites else None
            fiche_poste_id = str(fiche_poste.id) if fiche_poste else f"missing-{detail.id}"
            details_data.append({
                'id': str(detail.id),
                'fiche_poste_id': fiche_poste_id,
                'type_activites_id': str(type_activites.id) if type_activites else '',
                'type_activites_nom': type_activites.nomtype if type_activites else 'Sans type',
                'tache': fiche_poste.tache if fiche_poste else 'Tache supprimee',
                'description': fiche_poste.description if fiche_poste else '',
                'outils': fiche_poste.outils if fiche_poste else '',
                'fiche_poste_missing': fiche_poste is None,
                'note': detail.note,
                'note_label': detail.note_label,
                'remarques': detail.remarques,
                'piece_jointe_url': detail.piece_jointe.url if detail.piece_jointe else '',
                'piece_jointe_name': detail.piece_jointe.name.split('/')[-1] if detail.piece_jointe else '',
            })

        return JsonResponse({
            'success': True,
            'evaluation': {
                'id': str(evaluation.id),
                'employe_nom': evaluation.employe.surnom or evaluation.employe.nom_complet,
                'employe_poste': evaluation.employe.poste.nom_poste if evaluation.employe.poste else '-',
                'evaluateur_nom': evaluation.evaluateur.surnom if evaluation.evaluateur and evaluation.evaluateur.surnom else (evaluation.evaluateur.nom_complet if evaluation.evaluateur else '-'),
                'date_evaluation': evaluation.date_evaluation.strftime('%Y-%m-%d'),
                'periode_debut': evaluation.periode_debut.strftime('%Y-%m-%d'),
                'periode_fin': evaluation.periode_fin.strftime('%Y-%m-%d'),
                'commentaire_general': evaluation.commentaire_general,
                'besoins_formation': evaluation.besoins_formation,
                'perspectives_evolution': evaluation.perspectives_evolution,
                'est_auto_evaluation': evaluation.est_auto_evaluation,
                'statut': evaluation.statut,
                'note_totale': evaluation.note_totale,
                'note_maximale': evaluation.note_maximale,
                'pourcentage': evaluation.pourcentage,
                'priorite_1_id': str(evaluation.priorite_1_id) if evaluation.priorite_1_id else '',
                'priorite_2_id': str(evaluation.priorite_2_id) if evaluation.priorite_2_id else '',
                'priorite_3_id': str(evaluation.priorite_3_id) if evaluation.priorite_3_id else '',
            },
            'details': details_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_create(request):
    """API pour créer une nouvelle évaluation"""
    try:
        data = json.loads(request.body)

        employe_id = data.get('employe_id')
        evaluateur_id = data.get('evaluateur_id')
        date_evaluation = data.get('date_evaluation')
        periode_debut = data.get('periode_debut')
        periode_fin = data.get('periode_fin')
        commentaire_general = data.get('commentaire_general', '').strip()
        besoins_formation = data.get('besoins_formation', '').strip()
        perspectives_evolution = data.get('perspectives_evolution', '').strip()

        # Validation
        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'employé est obligatoire'
            }, status=400)

        if not evaluateur_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'évaluateur est obligatoire'
            }, status=400)

        if not date_evaluation or not periode_debut or not periode_fin:
            return JsonResponse({
                'success': False,
                'error': 'Les dates sont obligatoires'
            }, status=400)

        # Récupérer les employés
        employe = get_object_or_404(_employes_visibles(request), id=employe_id)
        evaluateur = get_object_or_404(_employes_visibles(request), id=evaluateur_id)

        # Vérifier que l'employé a un poste
        if not employe.poste:
            return JsonResponse({
                'success': False,
                'error': 'L\'employé n\'a pas de poste assigné'
            }, status=400)

        # Vérifier qu'il y a des fiches de poste pour ce poste
        nb_fiches = _get_fiches_for_poste(employe.poste).count()
        if nb_fiches == 0:
            return JsonResponse({
                'success': False,
                'error': f'Aucune tâche définie pour le poste "{employe.poste.nom_poste}"'
            }, status=400)

        # Créer l'évaluation
        evaluation = Evaluation.objects.create(
            employe=employe,
            evaluateur=evaluateur,
            date_evaluation=datetime.strptime(date_evaluation, '%Y-%m-%d').date(),
            periode_debut=datetime.strptime(periode_debut, '%Y-%m-%d').date(),
            periode_fin=datetime.strptime(periode_fin, '%Y-%m-%d').date(),
            commentaire_general=commentaire_general,
            besoins_formation=besoins_formation,
            perspectives_evolution=perspectives_evolution,
            statut='brouillon'
        )

        # Créer automatiquement les détails pour chaque tâche du poste (note=0 par défaut)
        fiches = _get_fiches_for_poste(employe.poste)
        for fiche in fiches:
            EvaluationDetail.objects.create(
                evaluation=evaluation,
                fiche_poste=fiche,
                note=0,
                remarques=''
            )

        return JsonResponse({
            'success': True,
            'message': 'Évaluation créée avec succès',
            'evaluation_id': str(evaluation.id)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_update_detail(request, detail_id):
    """API pour mettre a jour la note, les remarques et la piece jointe d'un detail"""
    try:
        detail = get_object_or_404(EvaluationDetail, id=detail_id)

        # Verifier que l'evaluation n'est pas terminee
        if detail.evaluation.statut in ['terminee', 'validee']:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de modifier une evaluation terminee ou validee'
            }, status=400)

        if request.FILES or (request.content_type and request.content_type.startswith('multipart')):
            note_value = request.POST.get('note')
            remarques_value = request.POST.get('remarques')
            piece_jointe = request.FILES.get('piece_jointe')

            if note_value is not None and note_value != '':
                try:
                    note_int = int(note_value)
                    if note_int < 0 or note_int > 2:
                        raise ValueError
                    detail.note = note_int
                except (ValueError, TypeError):
                    return JsonResponse({
                        'success': False,
                        'error': 'La note doit etre 0, 1 ou 2'
                    }, status=400)

            if remarques_value is not None:
                detail.remarques = remarques_value.strip()

            if piece_jointe:
                detail.piece_jointe = piece_jointe

            detail.save()

            return JsonResponse({
                'success': True,
                'message': 'Detail mis a jour',
                'detail': {
                    'note': detail.note,
                    'note_label': detail.note_label,
                    'remarques': detail.remarques,
                    'piece_jointe_url': detail.piece_jointe.url if detail.piece_jointe else '',
                    'piece_jointe_name': detail.piece_jointe.name.split('/')[-1] if detail.piece_jointe else ''
                }
            })

        data = json.loads(request.body)
        note = data.get('note')
        remarques = data.get('remarques', '').strip()

        # Validation de la note
        if note is None:
            return JsonResponse({
                'success': False,
                'error': 'La note est obligatoire'
            }, status=400)

        try:
            note = int(note)
            if note < 0 or note > 2:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'La note doit etre 0, 1 ou 2'
            }, status=400)

        # Mise a jour
        detail.note = note
        detail.remarques = remarques
        detail.save()

        return JsonResponse({
            'success': True,
            'message': 'Note mise a jour',
            'detail': {
                'note': detail.note,
                'note_label': detail.note_label,
                'remarques': detail.remarques,
                'piece_jointe_url': detail.piece_jointe.url if detail.piece_jointe else '',
                'piece_jointe_name': detail.piece_jointe.name.split('/')[-1] if detail.piece_jointe else ''
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_delete_detail(request, detail_id):
    """API pour supprimer un détail (fiche) d'une évaluation"""
    try:
        from apps.employees.permissions import is_directeur_poste

        if not is_directeur_poste(request.user):
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé'
            }, status=403)

        detail = get_object_or_404(EvaluationDetail, id=detail_id)

        if detail.evaluation.statut in ['terminee', 'validee']:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de modifier une évaluation terminée ou validée'
            }, status=400)

        detail.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_terminer(request, evaluation_id):
    """API pour terminer une évaluation"""
    try:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id)

        if evaluation.statut != 'brouillon':
            return JsonResponse({
                'success': False,
                'error': 'Cette évaluation n\'est pas en brouillon'
            }, status=400)

        evaluation.statut = 'terminee'
        evaluation.save()

        return JsonResponse({
            'success': True,
            'message': 'Évaluation terminée',
            'note_totale': evaluation.note_totale,
            'note_maximale': evaluation.note_maximale,
            'pourcentage': evaluation.pourcentage
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_delete(request, evaluation_id):
    """API pour supprimer une évaluation."""
    try:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id)

        evaluation.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_update_priorites(request, evaluation_id):
    """API pour enregistrer les 3 priorites d'amelioration d'une evaluation."""
    try:
        evaluation = get_object_or_404(Evaluation.objects.prefetch_related('details'), id=evaluation_id)
        data = json.loads(request.body or '{}')
        priorite_ids = [
            data.get('priorite_1_id') or None,
            data.get('priorite_2_id') or None,
            data.get('priorite_3_id') or None,
        ]

        chosen_ids = [pid for pid in priorite_ids if pid]
        if len(chosen_ids) != len(set(chosen_ids)):
            return JsonResponse({
                'success': False,
                'error': 'Les 3 priorites doivent etre differentes'
            }, status=400)

        details = {
            str(detail.id): detail
            for detail in evaluation.details.all()
        }

        selected = []
        for pid in chosen_ids:
            detail = details.get(pid)
            if not detail:
                return JsonResponse({
                    'success': False,
                    'error': 'Une priorite selectionnee est introuvable dans cette evaluation'
                }, status=400)
            if detail.note == 2:
                return JsonResponse({
                    'success': False,
                    'error': 'Une priorite ne peut pas correspondre a une fiche deja notee 2'
                }, status=400)
            selected.append(detail)

        evaluation.priorite_1 = selected[0] if len(selected) > 0 else None
        evaluation.priorite_2 = selected[1] if len(selected) > 1 else None
        evaluation.priorite_3 = selected[2] if len(selected) > 2 else None
        evaluation.save(update_fields=['priorite_1', 'priorite_2', 'priorite_3', 'date_modification'])

        return JsonResponse({
            'success': True,
            'message': 'Priorites enregistrees'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["POST"])
def api_evaluation_update_developpement(request, evaluation_id):
    """API pour enregistrer la section formation et progression d'une evaluation."""
    try:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id)

        if evaluation.statut in ['terminee', 'validee']:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de modifier une evaluation terminee ou validee'
            }, status=400)

        data = json.loads(request.body or '{}')
        evaluation.besoins_formation = data.get('besoins_formation', '').strip()
        evaluation.perspectives_evolution = data.get('perspectives_evolution', '').strip()
        evaluation.save(update_fields=['besoins_formation', 'perspectives_evolution', 'date_modification'])

        return JsonResponse({
            'success': True,
            'message': 'Section formation et progression enregistree'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
def evaluation_rapport(request):
    """Page de rapport d'évaluation par employé"""
    # Filtrer les employés actifs (sans date de débauchage)
    employes = Employe.objects.filter(date_debauchage__isnull=True)

    # Périmètre : organisation de l'utilisateur, avec bascule pour les superusers et les partenaires
    organisation_scope = _organisation_scope(request)
    employes = apply_employee_organisation_scope(employes, organisation_scope)

    employes = employes.order_by('surnom', 'nom', 'prenom')

    context = {
        'employes': employes,
        'organisation_options': organisation_scope['options'],
        'organisation_selected': organisation_scope['selected'],
    }
    return render(request, 'employees/evaluation_rapport.html', context)


@employe_required
@csrf_exempt
@require_http_methods(["GET"])
def api_evaluation_rapport_data(request):
    """API pour récupérer les données du rapport d'évaluation agrégées par fiche de poste"""
    try:
        employe_id = request.GET.get('employe_id')
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        evaluation_ids_raw = request.GET.get('evaluation_ids', '')
        evaluation_ids = [item for item in evaluation_ids_raw.split(',') if item]
        evaluation_ids.extend(request.GET.getlist('evaluation_ids[]'))

        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'employé est obligatoire'
            }, status=400)

        employe = get_object_or_404(_employes_visibles(request), id=employe_id)

        # Récupérer les évaluations terminées de cet employé
        evaluations = Evaluation.objects.filter(
            employe=employe,
            statut__in=['terminee', 'validee']
        ).select_related('evaluateur')

        # Filtrer par evaluations selectionnees si fournies
        if evaluation_ids:
            evaluations = evaluations.filter(id__in=evaluation_ids)
        else:
            # Filtrer par dates si fournies
            if date_debut:
                evaluations = evaluations.filter(date_evaluation__gte=date_debut)
            if date_fin:
                evaluations = evaluations.filter(date_evaluation__lte=date_fin)

        evaluations = evaluations.order_by('-date_evaluation')

        # Si pas d'évaluations, retourner vide
        if not evaluations.exists():
            return JsonResponse({
                'success': True,
                'employe': {
                    'id': str(employe.id),
                    'nom': employe.surnom or employe.nom_complet,
                    'poste': employe.poste.nom_poste if employe.poste else '-',
                },
                'fiches_poste': [],
                'evaluations': [],
                'nb_evaluations': 0
            })

        # Récupérer les fiches de poste du poste de l'employé
        fiches_poste = []
        if employe.poste:
            fiches_poste = _get_fiches_for_poste(employe.poste)

        # Construire les données du rapport par fiche de poste
        rapport_data = []
        for fiche in fiches_poste:
            fiche_data = {
                'id': str(fiche.id),
                'tache': fiche.tache,
                'description': fiche.description,
                'outils': fiche.outils,
                'evaluations': []
            }

            # Pour chaque évaluation, récupérer le détail de cette fiche
            for evaluation in evaluations:
                detail = EvaluationDetail.objects.filter(
                    evaluation=evaluation,
                    fiche_poste=fiche
                ).first()

                if detail:
                    fiche_data['evaluations'].append({
                        'evaluation_id': str(evaluation.id),
                        'date_evaluation': evaluation.date_evaluation.strftime('%d/%m/%Y'),
                        'evaluateur': evaluation.evaluateur.surnom if evaluation.evaluateur and evaluation.evaluateur.surnom else (evaluation.evaluateur.nom_complet if evaluation.evaluateur else '-'),
                        'est_auto_evaluation': evaluation.est_auto_evaluation,
                        'note': detail.note,
                        'note_label': detail.note_label,
                        'remarques': detail.remarques or '',
                    })

            rapport_data.append(fiche_data)

        # Liste des évaluations pour l'en-tête
        evaluations_liste = []
        for evaluation in evaluations:
            evaluations_liste.append({
                'id': str(evaluation.id),
                'date_evaluation': evaluation.date_evaluation.strftime('%d/%m/%Y'),
                'periode': f"{evaluation.periode_debut.strftime('%d/%m/%Y')} - {evaluation.periode_fin.strftime('%d/%m/%Y')}",
                'evaluateur': evaluation.evaluateur.surnom if evaluation.evaluateur and evaluation.evaluateur.surnom else (evaluation.evaluateur.nom_complet if evaluation.evaluateur else '-'),
                'est_auto_evaluation': evaluation.est_auto_evaluation,
                'note_totale': evaluation.note_totale,
                'note_maximale': evaluation.note_maximale,
                'pourcentage': evaluation.pourcentage,
                'commentaire_general': evaluation.commentaire_general or '',
                'besoins_formation': evaluation.besoins_formation or '',
                'perspectives_evolution': evaluation.perspectives_evolution or '',
            })

        return JsonResponse({
            'success': True,
            'employe': {
                'id': str(employe.id),
                'nom': employe.surnom or employe.nom_complet,
                'poste': employe.poste.nom_poste if employe.poste else '-',
            },
            'fiches_poste': rapport_data,
            'evaluations': evaluations_liste,
            'nb_evaluations': len(evaluations_liste)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@employe_required
@csrf_exempt
@require_http_methods(["GET"])
def api_evaluations_historique(request, employe_id):
    """API pour récupérer l'historique des évaluations d'un employé"""
    try:
        if not _employes_visibles(request).filter(id=employe_id).exists():
            return JsonResponse({'success': False, 'error': 'Employé introuvable'}, status=404)
        evaluations = Evaluation.objects.filter(
            employe_id=employe_id,
            statut__in=['terminee', 'validee']
        ).select_related('evaluateur').order_by('-date_evaluation')

        data = []
        for evaluation in evaluations:
            data.append({
                'id': str(evaluation.id),
                'date_evaluation': evaluation.date_evaluation.strftime('%Y-%m-%d'),
                'periode_debut': evaluation.periode_debut.strftime('%Y-%m-%d'),
                'periode_fin': evaluation.periode_fin.strftime('%Y-%m-%d'),
                'evaluateur_nom': evaluation.evaluateur.surnom if evaluation.evaluateur and evaluation.evaluateur.surnom else (evaluation.evaluateur.nom_complet if evaluation.evaluateur else '-'),
                'est_auto_evaluation': evaluation.est_auto_evaluation,
                'statut': evaluation.statut,
                'note_totale': evaluation.note_totale,
                'note_maximale': evaluation.note_maximale,
                'pourcentage': evaluation.pourcentage,
                'commentaire_general': evaluation.commentaire_general,
                'besoins_formation': evaluation.besoins_formation,
                'perspectives_evolution': evaluation.perspectives_evolution,
            })

        return JsonResponse({
            'success': True,
            'evaluations': data,
            'count': len(data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
