from datetime import date, datetime, timedelta

import pytz
from django.test import SimpleTestCase, TestCase

from apps.planning import doublons_reparations as dbl

TZ = pytz.timezone('Indian/Antananarivo')


class TypeEligibleTests(SimpleTestCase):
    def test_types_du_perimetre(self):
        for name in ('Réparation', 'Réhabilitation', 'Réparation maçonnerie', 'Maçonnerie', 'REPARATION'):
            self.assertTrue(dbl.type_eligible(name), name)

    def test_types_exclus(self):
        for name in ('Clôture', 'Entretien', 'PMH', 'Protection BV', 'Préparation terrain', 'Gestion', '', None):
            self.assertFalse(dbl.type_eligible(name), name)


class SummarizeTests(SimpleTestCase):
    own = date(2026, 9, 20)

    def test_aucun_doublon(self):
        self.assertEqual(dbl.summarize(self.own, [])['nb'], 0)
        self.assertFalse(dbl.summarize(self.own, [])['recent'])

    def test_limite_des_trois_mois(self):
        # exactement 3 mois : pas récent ; un jour de moins : récent
        self.assertFalse(dbl.summarize(self.own, [(date(2026, 6, 20), set())])['recent'])
        self.assertTrue(dbl.summarize(self.own, [(date(2026, 6, 21), set())])['recent'])

    def test_le_plus_recent_est_retenu(self):
        r = dbl.summarize(self.own, [(date(2025, 1, 1), set()), (date(2026, 8, 1), set()), (date(2026, 1, 1), set())])
        self.assertEqual((r['nb'], r['dernier_date'], r['dernier_display'], r['recent']),
                         (3, '2026-08-01', '01/08/2026', True))

    def test_composants(self):
        matches = [(date(2026, 8, 1), {'a'}), (date(2026, 7, 1), {'b'}), (date(2026, 6, 1), set())]
        self.assertEqual(dbl.summarize(self.own, matches, {'a'})['nb'], 2)   # 'a' + celui sans composant
        self.assertEqual(dbl.summarize(self.own, matches, set())['nb'], 3)   # sans composant : tout compte
        self.assertEqual(dbl.summarize(self.own, matches, {'z'})['nb'], 1)   # seul celui sans composant


class DoublonsIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.employees.models import FichePoste
        from apps.inspections.models import ComposantTypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage
        from apps.planning.models import Planning, TypeActivite

        cls.Planning = Planning
        cls.rep = TypeActivite.objects.create(nomtype='Réparation')
        cls.clo = TypeActivite.objects.create(nomtype='Clôture')
        tpe = TypePointEau.objects.create(nom_type='Borne fontaine')
        cls.robinet = ComposantTypePointEau.objects.create(type_point_eau=tpe, nom_composant='Robinet')
        cls.clapet = ComposantTypePointEau.objects.create(type_point_eau=tpe, nom_composant='Clapet')
        ouvrage = Ouvrage.objects.create(nom_ouvrage='O', type_ouvrage=TypeOuvrage.objects.create(nom_type_ouvrage='AEPG'))
        cls.pe1 = PointEau.objects.create(type_point_eau=tpe, ouvrage=ouvrage)
        cls.pe2 = PointEau.objects.create(type_point_eau=tpe, ouvrage=ouvrage)

        def mk(tache, type_):
            return FichePoste.objects.create(type_activites=type_, tache=tache, description='-')

        cls.remplacement = mk('Remplacement', cls.rep)
        cls.autre = mk('Soudure', cls.rep)
        cls.cloture = mk('Pose piquets', cls.clo)
        cls.ouvrage = ouvrage

    def make(self, jours, fiche=None, *, pe=None, done=True, comps=()):
        base = datetime(2026, 9, 20, 8, tzinfo=TZ)
        fiche = fiche or self.remplacement
        p = self.Planning.objects.create(
            date=base - timedelta(days=jours), fiche_poste=fiche, type_activite=fiche.type_activites,
            cible_point_eau=pe or self.pe1, estvalide=done, statut='termine' if done else 'en_cours',
            ouvrage=self.ouvrage)
        if comps:
            p.composants_point_eau.set(comps)
        return p

    def test_compteur_et_mention_recente(self):
        self.make(60)                       # il y a 2 mois : compte, récent
        self.make(200)                      # il y a ~7 mois : compte
        self.make(30, pe=self.pe2)          # autre cible : ignoré
        self.make(10, fiche=self.autre)     # autre activité : ignorée
        self.make(5, done=False)            # non réalisée : ignorée
        courante = self.make(0, done=False)
        res = dbl.calculer_doublons([courante.id])[str(courante.id)]
        self.assertEqual((res['nb'], res['recent'], res['dernier_display']), (2, True, '22/07/2026'))

    def test_pas_recent_si_le_dernier_a_plus_de_trois_mois(self):
        self.make(120)
        courante = self.make(0, done=False)
        res = dbl.calculer_doublons([courante.id])[str(courante.id)]
        self.assertEqual((res['nb'], res['recent']), (1, False))

    def test_premiere_intervention_affiche_zero(self):
        courante = self.make(0, done=False)
        res = dbl.calculer_doublons([courante.id])[str(courante.id)]
        self.assertEqual((res['nb'], res['dernier_date'], res['recent']), (0, None, False))

    def test_une_intervention_realisee_ne_se_compte_pas_elle_meme(self):
        seule = self.make(3)
        self.assertEqual(dbl.calculer_doublons([seule.id])[str(seule.id)]['nb'], 0)

    def test_les_plus_recentes_ne_comptent_pas_comme_deja_realisees(self):
        ancienne = self.make(100)
        self.make(10)  # postérieure à l'ancienne
        self.assertEqual(dbl.calculer_doublons([ancienne.id])[str(ancienne.id)]['nb'], 0)

    def test_hors_perimetre_absent(self):
        clo = self.make(0, fiche=self.cloture, done=False)
        self.make(30, fiche=self.cloture)
        self.assertEqual(dbl.calculer_doublons([clo.id]), {})

    def test_cible_deduite_du_materiel_saisi(self):
        from apps.planning.models import Designation, PlanningDetail
        des = Designation.objects.create(nom='Robinet', prix_unitaire=1000)
        ancienne = self.make(40)
        self.Planning.objects.filter(id=ancienne.id).update(cible_point_eau=None)
        PlanningDetail.objects.create(planning=ancienne, designation=des, quantity=1, pu=1000, montant=1000, point_eau=self.pe1)
        courante = self.make(0, done=False)
        self.assertEqual(dbl.calculer_doublons([courante.id])[str(courante.id)]['nb'], 1)

    def test_composants_distincts_ne_sont_pas_des_doublons(self):
        self.make(40, comps=[self.robinet])
        courante = self.make(0, done=False, comps=[self.clapet])
        self.assertEqual(dbl.calculer_doublons([courante.id])[str(courante.id)]['nb'], 0)
        meme = self.make(1, done=False, comps=[self.robinet])
        self.assertEqual(dbl.calculer_doublons([meme.id])[str(meme.id)]['nb'], 1)

    def test_sans_cible_absent(self):
        p = self.make(0, done=False)
        self.Planning.objects.filter(id=p.id).update(cible_point_eau=None)
        self.assertEqual(dbl.calculer_doublons([p.id]), {})
