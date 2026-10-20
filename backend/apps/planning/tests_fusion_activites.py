from django.test import SimpleTestCase

from apps.planning import services_fusion_activites as svc

VOCAB = [
    {'nom': 'Robinet', 'fold': 'robinet'},
    {'nom': 'Clapet anti-retour', 'fold': 'clapet anti-retour'},
    {'nom': 'Clapet', 'fold': 'clapet'},
    {'nom': 'Flotteur', 'fold': 'flotteur'},
]


def propre(tache):
    noms, spans = svc.detect_composants(tache, VOCAB)
    return noms, svc.strip_spans(tache, spans)


class FoldTests(SimpleTestCase):
    def test_same_length_and_accents(self):
        text = 'Réparation Été à côté'
        self.assertEqual(len(svc.fold(text)), len(text))
        self.assertEqual(svc.fold(text), 'reparation ete a cote')


class DetectComposantsTests(SimpleTestCase):
    def test_simple(self):
        self.assertEqual(propre('Remplacement robinet'), (['Robinet'], 'Remplacement'))

    def test_article_and_suffix_kept_out_of_name(self):
        self.assertEqual(propre('Remplacement du robinet'), (['Robinet'], 'Remplacement'))
        self.assertEqual(propre("Remplacement d'un robinet"), (['Robinet'], 'Remplacement'))

    def test_plural_and_case_and_accent(self):
        self.assertEqual(propre('REMPLACEMENT ROBINETS'), (['Robinet'], 'REMPLACEMENT'))
        self.assertEqual(propre('Réparation flotteur'), (['Flotteur'], 'Réparation'))

    def test_longest_match_wins(self):
        self.assertEqual(propre('Remplacement clapet anti-retour'), (['Clapet anti-retour'], 'Remplacement'))

    def test_several_components(self):
        noms, name = propre('Remplacement robinet et clapet')
        self.assertEqual(noms, ['Robinet', 'Clapet'])
        self.assertEqual(name, 'Remplacement')

    def test_no_partial_word_match(self):
        self.assertEqual(propre('Nettoyage des robinetteries'), ([], 'Nettoyage des robinetteries'))

    def test_nothing_detected(self):
        self.assertEqual(propre('Réparation fuite'), ([], 'Réparation fuite'))

    def test_label_only_component_leaves_empty_stem(self):
        self.assertEqual(propre('Robinet'), (['Robinet'], ''))

    def test_middle_component_keeps_rest(self):
        self.assertEqual(propre('Remplacement robinet BF'), (['Robinet'], 'Remplacement BF'))


class SplitComposantsTextTests(SimpleTestCase):
    def test_split_and_dedup(self):
        self.assertEqual(svc.split_composants_text('Robinet, robinet ; Clapet\nÉlément'), ['Robinet', 'Clapet', 'Élément'])
        self.assertEqual(svc.split_composants_text(''), [])
        self.assertEqual(svc.split_composants_text(['a', ' A ']), ['a'])


from django.test import TestCase
from django.utils import timezone

from apps.billing.models import PointEau, TypePointEau
from apps.core.models import RepairActivityPointTypePolicy
from apps.employees.models import FichePoste
from apps.inspections.models import ComposantTypePointEau
from apps.planning.models import FusionFichePosteLog, Planning, TypeActivite


class FusionIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.type_rep = TypeActivite.objects.create(nomtype='Réparation')
        cls.type_bp = TypePointEau.objects.create(nom_type='Borne fontaine')
        cls.robinet = ComposantTypePointEau.objects.create(type_point_eau=cls.type_bp, nom_composant='Robinet')
        cls.pe = PointEau.objects.create(type_point_eau=cls.type_bp)
        mk = lambda t: FichePoste.objects.create(type_activites=cls.type_rep, tache=t, description='-')
        cls.cible = mk('Remplacement')
        cls.dbl1 = mk('Remplacement robinet')
        cls.dbl2 = mk('Remplacement du clapet')
        now = timezone.now()
        cls.p_cible = Planning.objects.create(date=now, fiche_poste=cls.cible, type_activite=cls.type_rep)
        cls.p1 = Planning.objects.create(date=now, fiche_poste=cls.dbl1, type_activite=cls.type_rep, cible_point_eau=cls.pe)
        cls.p2 = Planning.objects.create(date=now, fiche_poste=cls.dbl1, type_activite=cls.type_rep)  # sans cible
        cls.p3 = Planning.objects.create(date=now, fiche_poste=cls.dbl2, type_activite=cls.type_rep, cible_point_eau=cls.pe)
        cls.policy = RepairActivityPointTypePolicy.objects.create(type_point_eau=cls.type_bp)
        cls.policy.allowed_activities.add(cls.dbl1)

    def payload(self, **extra):
        return {
            'target_id': str(self.cible.id),
            'source_ids': [str(self.dbl1.id), str(self.dbl2.id)],
            'composants': {str(self.dbl1.id): 'Robinet', str(self.dbl2.id): 'Clapet'},
            **extra,
        }

    def test_apercu_ne_modifie_rien(self):
        res = svc.apercu(self.payload())
        self.assertEqual(res['composants']['sans_cible'], 1)
        self.assertEqual([m['composant'] for m in res['composants']['manquants']], ['Clapet'])
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.fiche_poste_id, self.dbl1.id)
        self.assertEqual(FusionFichePosteLog.objects.count(), 0)

    def test_composant_manquant_bloque_sans_confirmation(self):
        with self.assertRaises(svc.FusionError):
            svc.appliquer(self.payload(), None)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.fiche_poste_id, self.dbl1.id)  # rien n'a bougé

    def test_appliquer_puis_annuler(self):
        res = svc.appliquer(self.payload(creer_composants_manquants=True), None)
        self.assertEqual(res['resume']['plannings'], 3)

        for p in (self.p1, self.p2, self.p3):
            p.refresh_from_db()
            self.assertEqual(p.fiche_poste_id, self.cible.id)
        self.assertEqual([c.nom_composant for c in self.p1.composants_point_eau.all()], ['Robinet'])
        self.assertEqual([c.nom_composant for c in self.p3.composants_point_eau.all()], ['Clapet'])
        self.assertEqual(self.p2.composants_point_eau.count(), 0)  # pas de cible -> pas de composant
        clapet = ComposantTypePointEau.objects.get(nom_composant='Clapet')
        self.assertFalse(clapet.est_obligatoire)

        self.dbl1.refresh_from_db()
        self.assertIsNone(self.dbl1.type_activites_id)
        self.assertTrue(self.dbl1.tache.startswith('[Fusionnée] '))
        self.assertEqual(list(self.policy.allowed_activities.all()), [self.cible])

        svc.annuler(res['log_id'], None)
        for p, fiche in ((self.p1, self.dbl1), (self.p2, self.dbl1), (self.p3, self.dbl2)):
            p.refresh_from_db()
            self.assertEqual(p.fiche_poste_id, fiche.id)
            self.assertEqual(p.composants_point_eau.count(), 0)
        self.dbl1.refresh_from_db()
        self.assertEqual((self.dbl1.tache, self.dbl1.type_activites_id), ('Remplacement robinet', self.type_rep.id))
        self.assertFalse(ComposantTypePointEau.objects.filter(nom_composant='Clapet').exists())
        self.assertEqual(list(self.policy.allowed_activities.all()), [self.dbl1])
        with self.assertRaises(svc.FusionError):
            svc.annuler(res['log_id'], None)

    def test_deduit_la_cible_du_materiel_saisi(self):
        from apps.planning.models import Designation, PlanningDetail
        from apps.organization.models import Ouvrage, TypeOuvrage
        ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage test', type_ouvrage=TypeOuvrage.objects.create(nom_type_ouvrage='AEPG'))
        PointEau.objects.filter(id=self.pe.id).update(ouvrage=ouvrage)
        Planning.objects.filter(id=self.p2.id).update(ouvrage=ouvrage)
        self.p2.refresh_from_db(); self.pe.refresh_from_db()
        des = Designation.objects.create(nom='Robinet 1/2', prix_unitaire=1000)
        PlanningDetail.objects.create(planning=self.p2, designation=des, quantity=1, pu=1000, montant=1000, point_eau=self.pe)
        res = svc.appliquer({'target_id': str(self.cible.id), 'source_ids': [str(self.dbl1.id)],
                             'composants': {str(self.dbl1.id): 'Robinet'}}, None)
        self.p2.refresh_from_db()
        self.assertEqual(self.p2.cible_point_eau_id, self.pe.id)
        self.assertEqual(self.p2.composants_point_eau.count(), 1)
        svc.annuler(res['log_id'], None)
        self.p2.refresh_from_db()
        self.assertIsNone(self.p2.cible_point_eau_id)

    def test_changement_de_type_exige_confirmation(self):
        autre = TypeActivite.objects.create(nomtype='Réhabilitation')
        src = FichePoste.objects.create(type_activites=autre, tache='Remplacement robinet BF', description='-')
        with self.assertRaises(svc.FusionError):
            svc.appliquer({'target_id': str(self.cible.id), 'source_ids': [str(src.id)]}, None)
