"""Activités proposées dans les réparations de l'app terrain (Android + Windows)."""
from django.test import TestCase

from apps.employees.models import FichePoste
from apps.planning.models import GroupeTypeActivite, TypeActivite
from apps.planning.repair_classification import (
    get_mobile_repair_fiches_queryset, get_repair_fiches_queryset, is_works_operations_group,
)


class MobileRepairFichesTests(TestCase):
    def fiche(self, tache, type_nom, groupe=None):
        type_activite = TypeActivite.objects.create(nomtype=type_nom, groupe=groupe)
        return FichePoste.objects.create(tache=tache, description='-', outils='', type_activites=type_activite)

    def test_groupe_operations_sur_les_ouvrages_et_installations(self):
        ouvrages, _ = GroupeTypeActivite.objects.get_or_create(nom='Opérations sur les ouvrages', defaults={'ordre': 1})
        usagers, _ = GroupeTypeActivite.objects.get_or_create(nom='Opérations sur les usagers', defaults={'ordre': 2})
        construction = self.fiche('Construction BF', 'Construction', ouvrages)
        installation = self.fiche('Pose compteur', 'Installation et remplacement', ouvrages)
        reparation = self.fiche('Réparation fuite', 'Réparation', ouvrages)
        social = self.fiche('Réunion usagers', 'Sensibilisation', usagers)

        ids = set(get_mobile_repair_fiches_queryset().values_list('id', flat=True))
        self.assertIn(construction.id, ids)
        self.assertIn(installation.id, ids)
        self.assertIn(reparation.id, ids)
        self.assertNotIn(social.id, ids)
        # La liste historique (notation des ouvrages) n'est pas modifiée.
        self.assertNotIn(construction.id, set(get_repair_fiches_queryset().values_list('id', flat=True)))

    def test_nom_du_groupe_tolerant(self):
        self.assertTrue(is_works_operations_group('OPERATION SUR LES OUVRAGES'))
        self.assertFalse(is_works_operations_group('Opérations sur les usagers'))
