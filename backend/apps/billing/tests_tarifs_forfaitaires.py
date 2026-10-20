import datetime
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import ConfigTarifForfaitaire, PointEau, TypePointEau
from apps.billing.tarifs_forfaitaires import (
    appliquer_tarifs_forfaitaires, champs_tarif_depuis_post, tarif_plein,
)


class TarifsForfaitairesTests(TestCase):
    def setUp(self):
        self.bf = TypePointEau.objects.create(nom_type='BF')
        self.bp = TypePointEau.objects.create(nom_type='BP')
        ConfigTarifForfaitaire.objects.create(
            type_point_eau=self.bf, tarif=Decimal('75000'), date_debut=datetime.date(2020, 1, 1))

    def test_pourcentage_donne_le_montant(self):
        pe = PointEau.objects.create(nomabonne='A', type_point_eau=self.bf, pourcentage_tarif=Decimal('50'))
        pe.refresh_from_db()
        self.assertEqual(pe.tarifforfaitaire, 37500.0)

    def test_montant_ancien_formulaire_deduit_le_pourcentage(self):
        pe = PointEau.objects.create(nomabonne='B', type_point_eau=self.bf, tarifforfaitaire=75000)
        pe.refresh_from_db()
        self.assertEqual(pe.pourcentage_tarif, Decimal('100.0000'))
        pe.tarifforfaitaire = 50000
        pe.save()
        pe.refresh_from_db()
        self.assertEqual(pe.tarifforfaitaire, 50000.0)  # montant exact conservé
        self.assertEqual(pe.pourcentage_tarif, Decimal('66.6667'))

    def test_vider_le_montant_vide_le_pourcentage(self):
        pe = PointEau.objects.create(nomabonne='C', type_point_eau=self.bf, tarifforfaitaire=75000)
        pe.tarifforfaitaire = None
        pe.save(update_fields=['tarifforfaitaire'])
        pe.refresh_from_db()
        self.assertIsNone(pe.pourcentage_tarif)

    def test_type_sans_tarif_plein_ne_change_rien(self):
        pe = PointEau.objects.create(nomabonne='D', type_point_eau=self.bp, tarifforfaitaire=1234)
        pe.refresh_from_db()
        self.assertEqual(pe.tarifforfaitaire, 1234.0)
        self.assertIsNone(pe.pourcentage_tarif)

    def test_changement_de_tarif_a_une_date(self):
        pe = PointEau.objects.create(nomabonne='E', type_point_eau=self.bf, pourcentage_tarif=Decimal('50'))
        ancien = ConfigTarifForfaitaire.objects.get(type_point_eau=self.bf)
        ancien.date_fin = datetime.date(2026, 12, 31)
        ancien.save()
        ConfigTarifForfaitaire.objects.create(
            type_point_eau=self.bf, tarif=Decimal('90000'), date_debut=datetime.date(2027, 1, 1))
        pe.refresh_from_db()
        self.assertEqual(pe.tarifforfaitaire, 37500.0)  # le nouveau tarif n'est pas encore en vigueur
        self.assertEqual(tarif_plein(self.bf.pk, datetime.date(2027, 6, 1)), Decimal('90000.00'))
        self.assertEqual(appliquer_tarifs_forfaitaires(date=datetime.date(2027, 6, 1)), 1)
        pe.refresh_from_db()
        self.assertEqual(pe.tarifforfaitaire, 45000.0)
        self.assertEqual(pe.pourcentage_tarif, Decimal('50.0000'))  # le pourcentage ne bouge pas

    def test_commande_dry_run(self):
        PointEau.objects.create(nomabonne='F', type_point_eau=self.bf, pourcentage_tarif=Decimal('100'))
        call_command('appliquer_tarifs_forfaitaires', '--dry-run')

    def test_champs_depuis_post(self):
        self.assertEqual(champs_tarif_depuis_post({'pourcentage_tarif': '50,5'}),
                         {'pourcentage_tarif': Decimal('50.5000')})
        self.assertEqual(champs_tarif_depuis_post({'pourcentage_tarif': ''}),
                         {'tarifforfaitaire': None, 'pourcentage_tarif': None})
        self.assertEqual(champs_tarif_depuis_post({'tarifforfaitaire': '75000'}), {'tarifforfaitaire': 75000.0})
        self.assertEqual(champs_tarif_depuis_post({'pourcentage_tarif': 'abc'}), {})


class HistoriqueTarifsTests(TestCase):
    """Les montants d'une année close restent calculés avec le tarif plein de cette année."""

    def setUp(self):
        from django.utils import timezone
        from apps.billing import tarifs_forfaitaires
        tarifs_forfaitaires._CACHE_PLEIN.clear()
        self.annee = timezone.localdate().year
        self.bf = TypePointEau.objects.create(nom_type='BF')
        ConfigTarifForfaitaire.objects.create(
            type_point_eau=self.bf, tarif=Decimal('75000'),
            date_debut=datetime.date(2020, 1, 1), date_fin=datetime.date(self.annee - 1, 12, 31))
        ConfigTarifForfaitaire.objects.create(
            type_point_eau=self.bf, tarif=Decimal('90000'), date_debut=datetime.date(self.annee, 1, 1))
        tarifs_forfaitaires._CACHE_PLEIN.clear()

    def test_annee_close_garde_l_ancien_tarif(self):
        from apps.billing.tarifs_forfaitaires import tarif_pour_annee
        pe = PointEau.objects.create(nomabonne='H', type_point_eau=self.bf, pourcentage_tarif=Decimal('50'))
        self.assertEqual(tarif_pour_annee(pe, self.annee - 1), Decimal('37500.0'))
        self.assertEqual(tarif_pour_annee(pe, self.annee), Decimal('45000.0'))
        self.assertEqual(tarif_pour_annee(pe, None), Decimal('45000.0'))

    def test_repli_sans_pourcentage_ni_tarif_plein(self):
        from apps.billing.tarifs_forfaitaires import tarif_pour_annee
        bp = TypePointEau.objects.create(nom_type='BP')
        pe = PointEau.objects.create(nomabonne='I', type_point_eau=bp, tarifforfaitaire=1234)
        self.assertEqual(tarif_pour_annee(pe, self.annee - 3), Decimal('1234.0'))
        sans = PointEau.objects.create(nomabonne='J', type_point_eau=bp)
        self.assertEqual(tarif_pour_annee(sans, self.annee), Decimal('0.00'))

    def test_annee_avant_tout_tarif_replie_sur_le_montant_stocke(self):
        from apps.billing.tarifs_forfaitaires import tarif_pour_annee
        pe = PointEau.objects.create(nomabonne='K', type_point_eau=self.bf, pourcentage_tarif=Decimal('100'))
        # 2019 : aucun tarif plein configuré -> montant actuellement stocké (90000)
        self.assertEqual(tarif_pour_annee(pe, 2019), Decimal('90000.0'))
