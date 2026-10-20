"""
Signals pour la gestion automatique des conges dans le Planning.
"""
from datetime import datetime, timedelta

import pytz
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models_conges import DemandeConge
from apps.employees.views_gardiens import _resolve_planning_targets_for_activity
from apps.planning.models import Activite, Planning


@receiver(post_save, sender=DemandeConge)
def creer_planning_conge_valide(sender, instance, created, **kwargs):
    """
    Cree automatiquement les entrees Planning quand un vrai conge est valide.

    Ne doit pas s'executer pour les repos ou jours feries, qui ont leur
    propre workflow de creation de planning.
    """
    if instance.statut != 'validee_directeur':
        return
    if instance.type_demande not in ('conge', 'conge_demi'):
        return
    if hasattr(instance, '_plannings_crees') and instance._plannings_crees:
        return

    try:
        activite_conge = Activite.objects.get(nom__icontains='Cong')
    except Activite.DoesNotExist:
        print("ERREUR: Activite 'Conge' non trouvee")
        return

    _, fiche_poste_conge, type_activite_conge = _resolve_planning_targets_for_activity('Cong')
    if not type_activite_conge and activite_conge.type_activite_id:
        type_activite_conge = activite_conge.type_activite

    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    date_courante = instance.date_debut
    plannings_crees = []

    while date_courante <= instance.date_fin:
        date_planning = timezone.make_aware(
            datetime.combine(date_courante, datetime.min.time()),
            tz_madagascar,
        )

        existing = Planning.objects.filter(
            employe=instance.employe,
            date__date=date_courante,
        ).first()

        if not existing:
            planning_kwargs = {
                'employe': instance.employe,
                'date': date_planning,
                'estvalide': True,
            }
            if fiche_poste_conge:
                planning_kwargs['fiche_poste'] = fiche_poste_conge
            if type_activite_conge:
                planning_kwargs['type_activite'] = type_activite_conge
            planning = Planning.objects.create(**planning_kwargs)
            plannings_crees.append(planning)

        date_courante += timedelta(days=1)

    instance._plannings_crees = True
    print(f"[conges] {len(plannings_crees)} planning(s) crees pour {instance.employe.nom_complet}")
