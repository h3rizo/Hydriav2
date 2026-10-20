"""
Vues pour le recoupement des indemnités avec la comptabilité DiameX
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
from decimal import Decimal
import json

from apps.planning.models import IndemniteJournaliere
from apps.employees.models import Employe
from apps.organization.models import Base
from .models import BaseDiameX


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return []
    return list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


def _filter_employes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(base__organisation_id=organisation_id)


@login_required
def recoupement_indemnites(request):
    """
    Page de recoupement des indemnités avec la comptabilité DiameX.
    Compare les montants d'indemnités exportées avec les lignes correspondantes dans BaseDiameX.
    """
    from datetime import datetime

    # Filtres
    filter_mois = request.GET.get('mois', '')
    filter_base = request.GET.get('base', '')
    filter_employe = request.GET.get('employe', '')

    # Base queryset - indemnités imprimées ou exportées
    base_qs = IndemniteJournaliere.objects.filter(
        statut__in=['imprimee', 'exportee']
    ).select_related(
        'employe', 'employe__base', 'employe__poste'
    )
    organisation_id = _get_user_organisation_id(request.user)
    allowed_progs = _get_allowed_progs(request.user)
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        base_qs = base_qs.filter(employe__base__organisation_id=organisation_id)

    # Appliquer les filtres
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            base_qs = base_qs.filter(
                date__year=int(year),
                date__month=int(month)
            )
        except:
            pass

    if filter_base:
        base_qs = base_qs.filter(employe__base_id=filter_base)

    if filter_employe:
        base_qs = base_qs.filter(employe_id=filter_employe)

    # Grouper par employé et mois
    from collections import defaultdict
    groupes = defaultdict(lambda: {
        'indemnites': [],
        'total_hydria': Decimal('0'),
        'employe': None,
        'mois': None,
        'annee': None,
        'correspondance_diamex': None,
        'statut_recoupement': 'non_verifie'
    })

    for ind in base_qs.order_by('employe__nom', 'date'):
        key = (str(ind.employe_id), ind.date.year, ind.date.month)
        groupes[key]['indemnites'].append(ind)
        groupes[key]['total_hydria'] += ind.montant
        groupes[key]['employe'] = ind.employe
        groupes[key]['mois'] = ind.date.month
        groupes[key]['annee'] = ind.date.year

    # Rechercher les correspondances DiameX
    resultats = []
    stats = {
        'total_groupes': 0,
        'avec_correspondance': 0,
        'sans_correspondance': 0,
        'montants_concordants': 0,
        'montants_discordants': 0
    }

    for key, groupe in groupes.items():
        employe = groupe['employe']
        annee = groupe['annee']
        mois = groupe['mois']

        # Rechercher dans DiameX
        correspondance = rechercher_diamex_indemnite(employe, annee, mois, allowed_progs=allowed_progs)

        if correspondance:
            groupe['correspondance_diamex'] = correspondance
            stats['avec_correspondance'] += 1

            # Comparer les montants
            montant_hydria = float(groupe['total_hydria'])
            montant_diamex = correspondance['montant_out']

            if abs(montant_hydria - montant_diamex) < 1:  # Tolérance 1 Ar
                groupe['statut_recoupement'] = 'concordant'
                stats['montants_concordants'] += 1
            else:
                groupe['statut_recoupement'] = 'discordant'
                stats['montants_discordants'] += 1
        else:
            groupe['statut_recoupement'] = 'sans_correspondance'
            stats['sans_correspondance'] += 1

        stats['total_groupes'] += 1
        resultats.append({
            'key': key,
            'employe': employe,
            'annee': annee,
            'mois': mois,
            'nb_jours': len(groupe['indemnites']),
            'total_hydria': groupe['total_hydria'],
            'correspondance_diamex': groupe['correspondance_diamex'],
            'statut_recoupement': groupe['statut_recoupement'],
            'indemnites': groupe['indemnites']
        })

    # Listes pour filtres
    bases_list = Base.objects.all().order_by('nom_base')
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        bases_list = bases_list.filter(organisation_id=organisation_id)
    employes_list = _filter_employes_by_scope(Employe.objects, request.user).filter(
        indemnites_journalieres__statut__in=['imprimee', 'exportee']
    ).distinct().order_by('nom')

    # Générer la liste des mois disponibles
    mois_disponibles_qs = IndemniteJournaliere.objects.filter(
        statut__in=['imprimee', 'exportee']
    )
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        mois_disponibles_qs = mois_disponibles_qs.filter(employe__base__organisation_id=organisation_id)
    mois_disponibles = mois_disponibles_qs.dates('date', 'month', order='DESC')[:24]

    context = {
        'resultats': resultats,
        'stats': stats,
        'bases_list': bases_list,
        'employes_list': employes_list,
        'mois_disponibles': mois_disponibles,
        'filter_mois': filter_mois,
        'filter_base': filter_base,
        'filter_employe': filter_employe,
    }

    return render(request, 'accounting/recoupement_indemnites.html', context)


def rechercher_diamex_indemnite(employe, annee, mois, allowed_progs=None):
    """
    Recherche une correspondance dans BaseDiameX pour une indemnité.

    Format attendu dans DiameX:
    _[Prefixe] [Nom]_Indemnité terrain_[Nb jours]_jours_[PU]_[Total]_[Année] [Mois]

    Args:
        employe: Instance Employe
        annee: Année (int)
        mois: Mois (int)

    Returns:
        dict avec {id, prog, description, detail, montant_out} ou None
    """
    surnom = employe.surnom or employe.prenom

    # Pattern de recherche: "Indemnité terrain" + année + mois + surnom dans detail
    pattern_indemnite = "Indemnité terrain"
    pattern_date = f"_{annee} {mois}"

    resultats = BaseDiameX.objects.filter(
        Q(description__icontains=pattern_indemnite) &
        Q(description__icontains=pattern_date),
        detail__icontains=surnom
    ).values('id_access', 'prog', 'description', 'detail', 'montant_out', 'montant_in')
    if allowed_progs is not None:
        resultats = resultats.filter(prog__in=allowed_progs)

    if resultats.exists():
        resultat = resultats.first()
        return {
            'id': resultat['id_access'],
            'prog': resultat['prog'],
            'description': resultat['description'],
            'detail': resultat['detail'],
            'montant_out': float(resultat['montant_out']) if resultat['montant_out'] else 0,
            'montant_in': float(resultat['montant_in']) if resultat['montant_in'] else 0
        }

    return None


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_appliquer_diamex_indemnites(request):
    """
    API pour appliquer les correspondances DiameX trouvées aux indemnités.
    Met à jour numero_diamex et base_diamex dans IndemniteJournaliere.
    """
    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        annee = data.get('annee')
        mois = data.get('mois')
        correspondance = data.get('correspondance')

        if not all([employe_id, annee, mois, correspondance]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        # Mettre à jour toutes les indemnités du groupe
        queryset_update = IndemniteJournaliere.objects.filter(
            employe_id=employe_id,
            date__year=annee,
            date__month=mois,
            statut__in=['imprimee', 'exportee']
        )
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id and not getattr(request.user, 'is_superuser', False):
            queryset_update = queryset_update.filter(employe__base__organisation_id=organisation_id)

        nb_updated = queryset_update.update(
            numero_diamex=str(correspondance['id']),
            base_diamex=correspondance['prog']
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} indemnité(s) mise(s) à jour',
            'nb_updated': nb_updated
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_rechercher_correspondance_indemnite(request):
    """
    API pour rechercher une correspondance DiameX pour un groupe d'indemnités.
    """
    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        annee = data.get('annee')
        mois = data.get('mois')

        if not all([employe_id, annee, mois]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        employe = _filter_employes_by_scope(Employe.objects, request.user).get(id=employe_id)
        correspondance = rechercher_diamex_indemnite(
            employe,
            annee,
            mois,
            allowed_progs=_get_allowed_progs(request.user)
        )

        return JsonResponse({
            'success': True,
            'correspondance': correspondance,
            'employe': {
                'surnom': employe.surnom or employe.prenom,
                'nom_complet': employe.nom_complet
            }
        })

    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_recoupement_batch_indemnites(request):
    """
    API pour recouper automatiquement toutes les indemnités en batch.
    """
    try:
        # Récupérer les indemnités sans correspondance DiameX
        indemnites_sans_diamex = IndemniteJournaliere.objects.filter(
            statut__in=['imprimee', 'exportee'],
            numero_diamex__isnull=True
        ).select_related('employe')
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id and not getattr(request.user, 'is_superuser', False):
            indemnites_sans_diamex = indemnites_sans_diamex.filter(employe__base__organisation_id=organisation_id)

        # Grouper par employé/mois
        from collections import defaultdict
        groupes = defaultdict(list)

        for ind in indemnites_sans_diamex:
            key = (str(ind.employe_id), ind.date.year, ind.date.month)
            groupes[key].append(ind)

        nb_groupes_traites = 0
        nb_indemnites_mises_a_jour = 0
        erreurs = []

        for key, indemnites in list(groupes.items())[:50]:  # Limiter à 50
            try:
                employe = indemnites[0].employe
                _, annee, mois = key

                correspondance = rechercher_diamex_indemnite(
                    employe,
                    annee,
                    mois,
                    allowed_progs=_get_allowed_progs(request.user)
                )

                if correspondance:
                    # Mettre à jour toutes les indemnités du groupe
                    for ind in indemnites:
                        ind.numero_diamex = str(correspondance['id'])
                        ind.base_diamex = correspondance['prog']
                        ind.save()
                        nb_indemnites_mises_a_jour += 1

                    nb_groupes_traites += 1

            except Exception as e:
                erreurs.append(f"Groupe {key}: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'{nb_groupes_traites} groupe(s) traité(s), {nb_indemnites_mises_a_jour} indemnité(s) mise(s) à jour',
            'nb_groupes_traites': nb_groupes_traites,
            'nb_indemnites_mises_a_jour': nb_indemnites_mises_a_jour,
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
