"""
Page de configuration des tarifs forfaitaires pleins (ConfigTarifForfaitaire).

Tarif d'un point d'eau = tarif plein de son type à la date considérée x pourcentage du point / 100.
Un changement de tarif = une nouvelle ligne avec sa date de début ; l'ancienne reçoit une date de
fin (la veille). ``ConfigTarifForfaitaire.save()/delete()`` recalculent les montants des points.
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import ConfigTarifForfaitaire, PointEau, TypePointEau


def _peut_modifier(user):
    """Superutilisateur, staff ou directeur (même règle que les autres écrans de configuration)."""
    if user.is_superuser or user.is_staff:
        return True
    employe = getattr(user, 'employe', None)
    poste = getattr(employe, 'poste', None) if employe else None
    return bool(poste and (getattr(poste, 'nom_poste', '') or '').strip().lower() == 'directeur')


def _refus():
    return JsonResponse({'success': False, 'error': "Réservé au directeur ou à l'administrateur."}, status=403)


def _lire_json(request):
    try:
        return json.loads(request.body or '{}')
    except ValueError:
        return {}


def _date(valeur):
    try:
        return datetime.strptime(str(valeur or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _tarif(valeur):
    try:
        tarif = Decimal(str(valeur).strip().replace(' ', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        return None
    return tarif if tarif > 0 else None


def _en_vigueur(config, jour):
    return config.date_debut <= jour and (config.date_fin is None or config.date_fin >= jour)


@login_required
def config_tarifs_forfaitaires(request):
    """Tarifs pleins par type de point d'eau, avec historique."""
    aujourdhui = timezone.localdate()
    configs = list(ConfigTarifForfaitaire.objects.select_related('type_point_eau'))
    par_type = {}
    for config in configs:
        par_type.setdefault(config.type_point_eau_id, []).append(config)

    # Points concernés par type : ceux qui ont un tarif forfaitaire ou un pourcentage
    points_par_type = {
        ligne['type_point_eau_id']: ligne['n']
        for ligne in PointEau.objects.filter(type_point_eau__isnull=False).filter(
            Q(pourcentage_tarif__isnull=False) | Q(tarifforfaitaire__gt=0)
        ).values('type_point_eau_id').annotate(n=Count('id'))
    }

    lignes = []
    for type_pe in TypePointEau.objects.filter(actif=True).order_by('nom_type'):
        historique = sorted(par_type.get(type_pe.id, []), key=lambda c: c.date_debut, reverse=True)
        courant = next((c for c in historique if _en_vigueur(c, aujourdhui)), None)
        a_venir = [c for c in historique if c.date_debut > aujourdhui]
        if not historique and not points_par_type.get(type_pe.id):
            continue  # type sans tarif forfaitaire ni point concerné : inutile à l'écran
        lignes.append({
            'type': type_pe,
            'courant': courant,
            'a_venir': a_venir,
            'historique': historique,
            'nb_points': points_par_type.get(type_pe.id, 0),
        })

    return render(request, 'billing/config_tarifs_forfaitaires.html', {
        'lignes': lignes,
        'types_point_eau': TypePointEau.objects.filter(actif=True).order_by('nom_type'),
        'peut_modifier': _peut_modifier(request.user),
        'aujourdhui': aujourdhui.isoformat(),
    })


@login_required
@require_http_methods(['POST'])
def api_config_tarif_creer(request):
    """Nouveau tarif plein pour un type : l'éventuel tarif ouvert à cette date reçoit une date de fin."""
    if not _peut_modifier(request.user):
        return _refus()
    donnees = _lire_json(request)
    type_pe = TypePointEau.objects.filter(pk=donnees.get('type_point_eau_id')).first()
    tarif = _tarif(donnees.get('tarif'))
    date_debut = _date(donnees.get('date_debut'))
    if not type_pe or tarif is None or date_debut is None:
        return JsonResponse({'success': False, 'error': 'Type, tarif (> 0) et date de début sont obligatoires.'}, status=400)

    with transaction.atomic():
        if ConfigTarifForfaitaire.objects.filter(type_point_eau=type_pe, date_debut=date_debut).exists():
            return JsonResponse({'success': False, 'error': 'Un tarif commence déjà à cette date pour ce type.'}, status=400)
        # Clôturer la période qui couvre la nouvelle date de début (ou qui reste ouverte avant elle)
        for ancien in ConfigTarifForfaitaire.objects.filter(
            type_point_eau=type_pe, date_debut__lt=date_debut
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=date_debut)):
            ancien.date_fin = date_debut - timedelta(days=1)
            ancien.save()
        ConfigTarifForfaitaire.objects.create(type_point_eau=type_pe, tarif=tarif, date_debut=date_debut)
    return JsonResponse({'success': True, 'message': f'Tarif {tarif:,.0f} Ar créé pour {type_pe.nom_type}.'.replace(',', ' ')})


@login_required
@require_http_methods(['POST'])
def api_config_tarif_modifier(request, config_id):
    if not _peut_modifier(request.user):
        return _refus()
    config = ConfigTarifForfaitaire.objects.filter(pk=config_id).first()
    if config is None:
        return JsonResponse({'success': False, 'error': 'Tarif introuvable.'}, status=404)
    donnees = _lire_json(request)
    tarif = _tarif(donnees.get('tarif'))
    date_debut = _date(donnees.get('date_debut'))
    date_fin = _date(donnees.get('date_fin')) if donnees.get('date_fin') else None
    if tarif is None or date_debut is None or (donnees.get('date_fin') and date_fin is None):
        return JsonResponse({'success': False, 'error': 'Tarif (> 0) et dates valides obligatoires.'}, status=400)
    if date_fin and date_fin < date_debut:
        return JsonResponse({'success': False, 'error': 'La date de fin doit être postérieure à la date de début.'}, status=400)
    if ConfigTarifForfaitaire.objects.filter(
        type_point_eau=config.type_point_eau, date_debut=date_debut
    ).exclude(pk=config.pk).exists():
        return JsonResponse({'success': False, 'error': 'Un autre tarif commence déjà à cette date pour ce type.'}, status=400)
    config.tarif, config.date_debut, config.date_fin = tarif, date_debut, date_fin
    config.save()
    return JsonResponse({'success': True, 'message': 'Tarif modifié.'})


@login_required
@require_http_methods(['POST'])
def api_config_tarif_supprimer(request, config_id):
    if not _peut_modifier(request.user):
        return _refus()
    config = ConfigTarifForfaitaire.objects.filter(pk=config_id).first()
    if config is None:
        return JsonResponse({'success': False, 'error': 'Tarif introuvable.'}, status=404)
    config.delete()
    return JsonResponse({'success': True, 'message': 'Tarif supprimé.'})
