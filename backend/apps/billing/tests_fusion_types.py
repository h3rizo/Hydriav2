import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from apps.billing.models import PointEau, TypePointEau
from apps.billing.payment_modalities import is_private_point_type_name

migration = importlib.import_module('apps.billing.migrations.0081_fusion_types_institutionnels')


class FusionTypesInstitutionnelsTests(TestCase):
    def test_bp_institutionnel_n_est_pas_prive(self):
        self.assertTrue(is_private_point_type_name('BP'))
        self.assertFalse(is_private_point_type_name('BP', True))
        self.assertFalse(is_private_point_type_name('Kiosque'))

    def test_fusion_deplace_les_points_et_coche_le_champ(self):
        bf, bp, pmh = (TypePointEau.objects.create(nom_type=n) for n in ('BF', 'BP', 'PMH'))
        bi, bi_vol, pmhi = (TypePointEau.objects.create(nom_type=n) for n in ('BI', 'BI volume', 'PMHI'))
        attendu = {}
        for ancien, cible in ((bi, bf), (bi_vol, bp), (pmhi, pmh)):
            pe = PointEau.objects.create(nomabonne=f'Inst {ancien.nom_type}', type_point_eau=ancien)
            attendu[pe.pk] = cible.pk
        autre = PointEau.objects.create(nomabonne='Normal', type_point_eau=bf)

        migration.fusionner_types(django_apps, None)

        for pk, cible_pk in attendu.items():
            pe = PointEau.objects.get(pk=pk)
            self.assertEqual(pe.type_point_eau_id, cible_pk)
            self.assertTrue(pe.estbranchementinstitutionnel)
        autre.refresh_from_db()
        self.assertFalse(autre.estbranchementinstitutionnel)
        self.assertFalse(TypePointEau.objects.get(pk=bi.pk).actif)
        self.assertTrue(TypePointEau.objects.get(pk=bf.pk).actif)
