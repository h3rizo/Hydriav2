"""
Views pour le retour des frais de déplacement
Module séparé pour traiter les frais de déplacement des employés
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Q, Count
from decimal import Decimal
import json
import pytz
import math
import unicodedata

from apps.planning.models import PlanningDetail, Planning, Deplacement
from apps.accounting.models import DiameXTemporaire
from apps.employees.models import Employe


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_planning_scope(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'
    if getattr(user, 'is_superuser', False):
        return 'all'
    employe = getattr(user, 'employe', None)
    if not employe:
        return 'none'

    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    if poste_nom == 'directeur':
        return 'all'

    organisation_postes = (
        'directeur adjoint',
        'responsable administratif',
        'responsable administratif et financier',
        'raf',
    )
    if any(p in poste_nom for p in organisation_postes):
        return 'organisation'
    return 'base'


def _filter_bases_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(id=base_id)


def _filter_employes_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(base_id=base_id)


def _filter_frais_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(planning__employe__base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(planning__employe__base_id=base_id)


@login_required
def retour_frais_deplacement_print(request):
    """
    Page d'impression dédiée sans éléments d'interface
    """
    # Récupérer l'organisation de l'utilisateur connecté pour afficher le logo
    organisation = None
    logo_url = None

    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base and request.user.employe.base.organisation:
            organisation = request.user.employe.base.organisation
            if organisation.logo:
                logo_url = organisation.logo.url

    context = {
        'organisation': organisation,
        'logo_url': logo_url,
    }

    return render(request, 'billing/retour_frais_deplacement_print.html', context)


@login_required
def retour_frais_deplacement(request):
    """
    Vue principale pour le retour des frais de déplacement
    """
    # Récupérer les IDs des employés qui ont réellement des frais de déplacement non retournés
    # en partant de PlanningDetail et remontant via Planning
    employes_ids_qs = PlanningDetail.objects.filter(
        designation__nom__iexact='Frais de déplacement',  # Exact match pour éviter "Frais colis" etc
        retour=False,
        planning__isnull=False,  # S'assurer qu'il y a bien un planning
        planning__employe__isnull=False  # S'assurer que le planning a un employé
    )
    employes_ids_qs = _filter_frais_by_scope(employes_ids_qs, request.user)
    employes_ids = employes_ids_qs.values_list('planning__employe_id', flat=True).distinct()

    # Employés avec frais: utile pour diagnostic et cohérence métier
    employes_avec_frais = Employe.objects.filter(
        id__in=employes_ids,
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by('nom', 'prenom')
    employes_avec_frais = _filter_employes_by_scope(employes_avec_frais, request.user)

    # Liste déroulante: tous les employés actifs du périmètre visible
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by('nom', 'prenom')
    employes = _filter_employes_by_scope(employes, request.user)

    # Debug : afficher le nombre d'employés
    print(f"DEBUG: {len(employes_ids)} employés ont des frais de déplacement non retournés")
    print(f"DEBUG: {employes_avec_frais.count()} employés actifs avec frais")
    print(f"DEBUG: {employes.count()} employés actifs dans la liste déroulante")

    # Récupérer les bases filtrées par l'organisation de l'utilisateur connecté
    from apps.organization.models import Base
    bases = Base.objects.all().order_by('nom_base')

    bases = _filter_bases_by_scope(bases, request.user)
    user_employe = getattr(request.user, 'employe', None)
    user_base_id = str(user_employe.base_id) if getattr(user_employe, 'base_id', None) else ''
    if user_base_id and bases.filter(id=user_base_id).exists():
        default_base_id = user_base_id
    elif bases.count() == 1:
        default_base_id = str(bases.first().id)
    else:
        default_base_id = ''

    employes_dropdown_data = []
    for employe in employes:
        base_nom = employe.base.nom_base if employe.base else ''
        employe_label = (
            employe.surnom
            or employe.prenom
            or employe.nom_complet
            or str(employe)
        )
        employes_dropdown_data.append({
            'id': str(employe.id),
            'base_id': str(employe.base_id) if employe.base_id else '',
            'label': f"{employe_label} - {base_nom}",
        })

    context = {
        'title': 'Retour frais de déplacement',
        'employes': employes,
        'employes_dropdown_data': employes_dropdown_data,
        'bases': bases,
        'default_base_id': default_base_id,
    }

    return render(request, 'billing/retour_frais_deplacement.html', context)


@login_required
@require_http_methods(["GET"])
def api_frais_deplacement_employe(request):
    """
    API pour récupérer les frais de déplacement d'un employé pour un mois donné
    """
    try:
        employe_id = request.GET.get('employe_id')
        mois = request.GET.get('mois')  # Format: YYYY-MM
        annee = request.GET.get('annee')

        if not employe_id or not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (employe_id, mois, annee)'
            }, status=400)

        # Convertir mois et annee en entiers
        try:
            mois_int = int(mois)
            annee_int = int(annee)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Format mois/annee invalide'
            }, status=400)

        # Récupérer les frais de déplacement pour cet employé et ce mois
        # Critères: designation contient "frais de déplacement", pas encore marqué comme retourné
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        details = PlanningDetail.objects.filter(
            planning__employe_id=employe_id,
            designation__nom__icontains='frais de déplacement',
            retour=False  # Pas encore retourné
         )
        details = _filter_frais_by_scope(details, request.user).select_related(
            'planning',
            'planning__ouvrage',
            'planning__fiche_poste',
            'planning__type_activite',
            'planning__employe__base__village_depart',
            'designation',
            'deplacement__point_a',
            'deplacement__point_b'
        ).order_by('planning__date')

        # Filtrer par mois/annee en Python (timezone-aware)
        frais_list = []
        details_du_mois = []
        for detail in details:
            if detail.planning and detail.planning.date:
                date_aware = detail.planning.date
                if date_aware.tzinfo:
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                else:
                    date_madagascar = tz_madagascar.localize(date_aware)

                if date_madagascar.year == annee_int and date_madagascar.month == mois_int:
                    details_du_mois.append(detail)
                    frais_list.append({
                        'id': str(detail.id),
                        'date': date_madagascar.strftime('%Y-%m-%d'),
                        'date_display': date_madagascar.strftime('%d/%m/%Y'),
                        'ouvrage': detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else '',
                        'activite': (
                            detail.planning.fiche_poste.tache
                            if getattr(detail.planning, 'fiche_poste', None)
                            else (
                                detail.planning.type_activite.nomtype
                                if getattr(detail.planning, 'type_activite', None)
                                else ''
                            )
                        ),
                        'point_a': detail.point_a.nom_village if detail.point_a else '',
                        'point_b': detail.point_b.nom_village if detail.point_b else '',
                        'trajet': detail.trajet or '',
                        'prix_unitaire': float(detail.pu or 0),
                        'montant': float(detail.montant or 0),
                        'designation': detail.designation.nom if detail.designation else '',
                    })

        # Contrôle par la distance et la durée de route (aide au contrôle : ne modifie aucun montant).
        # Une erreur ici ne doit jamais empêcher d'afficher les frais.
        controle = {'jours': [], 'resume': None}
        try:
            from apps.billing.frais_trajets import analyser
            analyse = analyser(details_du_mois)
            lignes_par_id = {str(k): v for k, v in analyse['lignes'].items()}
            for item in frais_list:
                item['trajet_info'] = lignes_par_id.get(item['id'])
            controle = {'jours': analyse['jours'], 'resume': analyse['resume']}
        except Exception as exc:
            print(f"[WARNING] Contrôle des trajets indisponible: {exc}")

        return JsonResponse({
            'success': True,
            'frais': frais_list,
            'total': len(frais_list),
            'controle': controle,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_imprimer_frais_deplacement(request):
    """
    API pour imprimer la facture et exporter vers DiameX
    Après impression, crée une ligne dans DiameXTemporaire
    """
    try:
        data = json.loads(request.body)
        frais_ids = data.get('frais_ids', [])
        employe_id = data.get('employe_id')
        mois = data.get('mois')
        annee = data.get('annee')

        if not frais_ids or not employe_id or not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        # Récupérer l'employé
        try:
            employes_scoped = _filter_employes_by_scope(Employe.objects.select_related('poste', 'base'), request.user)
            employe = employes_scoped.get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employé non trouvé'
            }, status=404)

        # Récupérer les frais sélectionnés
        frais = PlanningDetail.objects.filter(
            id__in=frais_ids,
            retour=False
        ).select_related('planning', 'designation', 'deplacement__point_a', 'deplacement__point_b')
        frais = _filter_frais_by_scope(frais, request.user).filter(planning__employe_id=employe_id)

        if not frais.exists():
            return JsonResponse({
                'success': False,
                'error': 'Aucun frais de déplacement trouvé'
            }, status=404)

        # Calculer le total
        montant_total = sum([float(f.montant or 0) for f in frais])

        # Arrondir au supérieur (100 Ar)
        montant_arrondi = Decimal(math.ceil(montant_total / 100) * 100)

        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Créer la ligne DiameXTemporaire
        with transaction.atomic():
            # Marquer les frais comme retournés
            frais.update(
                retour=True,
                date_retour=timezone.now()
            )

            # Préparer la description selon le format salaire
            # Format: [Préfixe poste] [Nom complet]_Frais déplacement_[Année] [Mois:02d]
            prefixe_poste = employe.poste.prefixe if employe.poste and employe.poste.prefixe else ''
            nom_complet = employe.nom_complet
            description = f"{prefixe_poste} {nom_complet}_Frais déplacement_{annee} {int(mois):02d}".strip()

            # Date = 1er du mois
            date_rec = timezone.datetime(int(annee), int(mois), 1).date()

            # Journal
            journal = "00PERS"
            if employe.base and employe.base.journal_retour:
                journal = employe.base.journal_retour.code if hasattr(employe.base.journal_retour, 'code') else "00PERS"

            # Cat (compte) : 625200 (demandé par l'utilisateur)
            cat = "625200"

            # PERS = surnom ou detail de l'employé
            pers = employe.surnom if employe.surnom else (employe.prenom or '')

            # ACTIV = volet de l'employé
            activ = employe.volet if employe.volet else None

            # Prog = programme DiameX de la base
            prog = employe.base.prog_diamex if employe.base and employe.base.prog_diamex else None

            # Créer la ligne DiameX
            ligne_diamex = DiameXTemporaire.objects.create(
                type_transaction='depense',
                journal_code=journal,
                date_m=date_rec,
                rec=0,
                date_rec=date_rec,
                description=description,
                montant_in=0,
                montant_out=float(montant_arrondi),
                compte_code=cat,
                pers=pers,
                detail=pers,
                info='hydria frais déplacement',
                scan='',
                prog=prog,
                activ=activ,
                fournisseur=None,
                statut='en_attente',
                created_by=request.user.employe if hasattr(request.user, 'employe') else None
            )

            # Mettre Ã  jour la table Deplacements si les montants ont changé
            # Pour chaque frais retourné, vérifier s'il existe une ligne correspondante
            # dans Deplacements et mettre Ã  jour le prix_unitaire et date_prix si nécessaire
            nb_deplacements_maj = 0
            for frais in frais:
                if frais.point_a and frais.point_b and frais.montant:
                    # Rechercher ou créer le déplacement correspondant
                    # On cherche par point_a, point_b et moyen de transport (si disponible)
                    try:
                        # Déterminer le moyen de transport depuis le trajet si possible
                        moyen_transport = None
                        if frais.trajet:
                            trajet_lower = frais.trajet.lower()
                            if 'taxi' in trajet_lower or 'brousse' in trajet_lower:
                                moyen_transport = 'taxi-brousse'
                            elif 'pirogue' in trajet_lower:
                                moyen_transport = 'pirogue'
                            elif 'bac' in trajet_lower:
                                moyen_transport = 'bac'

                        # Si on n'a pas pu déterminer le moyen de transport, utiliser taxi-brousse par défaut
                        if not moyen_transport:
                            moyen_transport = 'taxi-brousse'

                        # Chercher un déplacement existant avec ces paramètres
                        deplacement, created = Deplacement.objects.get_or_create(
                            point_a=frais.point_a,
                            point_b=frais.point_b,
                            moyen_transport=moyen_transport,
                            date_prix=frais.planning.date.date() if frais.planning and frais.planning.date else date_rec,
                            defaults={
                                'prix_unitaire': frais.montant
                            }
                        )

                        # Si le déplacement existait déjÃ , mettre Ã  jour le prix_unitaire si différent
                        if not created and deplacement.prix_unitaire != frais.montant:
                            deplacement.prix_unitaire = frais.montant
                            deplacement.date_prix = frais.planning.date.date() if frais.planning and frais.planning.date else date_rec
                            deplacement.save()
                            nb_deplacements_maj += 1
                        elif created:
                            nb_deplacements_maj += 1

                    except Exception as e:
                        # En cas d'erreur, ne pas bloquer le retour, juste logger
                        print(f"Erreur lors de la mise Ã  jour du déplacement: {e}")

        message = f'{len(frais_ids)} frais de déplacement marqués comme retournés'
        if nb_deplacements_maj > 0:
            message += f', {nb_deplacements_maj} déplacement(s) mis Ã  jour'

        return JsonResponse({
            'success': True,
            'message': message,
            'montant_total': float(montant_total),
            'montant_arrondi': float(montant_arrondi),
            'ligne_diamex_id': str(ligne_diamex.id),
            'nb_deplacements_maj': nb_deplacements_maj
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_update_montant_frais(request):
    """
    API pour modifier le montant d'un frais de déplacement
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')
        nouveau_montant = data.get('montant')

        if not frais_id or nouveau_montant is None:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        # Récupérer le frais
        try:
            frais = _filter_frais_by_scope(PlanningDetail.objects.filter(id=frais_id, retour=False), request.user).get()
        except PlanningDetail.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Frais non trouvé ou déjÃ  retourné'
            }, status=404)

        # Mettre Ã  jour le montant
        frais.montant = Decimal(str(nouveau_montant))
        frais.save(update_fields=['montant'])

        return JsonResponse({
            'success': True,
            'message': 'Montant mis Ã  jour'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


