"""Tests des coûts types (barème par activité / cible / composant)."""
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.planning.models import Designation
from apps.planning.models_couts_types import CoutTypeActivite, CoutTypeLigne
from apps.planning.views_couts_types import famille_fiche


def _fiche(tache, type_name):
    return SimpleNamespace(tache=tache, type_activites=SimpleNamespace(nomtype=type_name))


class FamilleFicheTests(SimpleTestCase):
    def test_familles(self):
        self.assertEqual(famille_fiche(_fiche('Réparation fuite', 'Réparation')), 'reparation')
        self.assertEqual(famille_fiche(_fiche('Remise en état', 'Réhabilitation')), 'rehabilitation')
        self.assertEqual(famille_fiche(_fiche('Pose borne', 'Installation')), 'installation')
        self.assertEqual(famille_fiche(_fiche('Changer pompe', 'Remplacement')), 'remplacement')
        self.assertEqual(famille_fiche(_fiche('Visite', 'Suivi')), '')


class CoutTypeLigneTests(SimpleTestCase):
    def test_pu_par_defaut_de_la_designation(self):
        ligne = CoutTypeLigne(quantite=Decimal('3'))
        ligne.designation = Designation(nom='Ciment', prix_unitaire=Decimal('2500'))
        self.assertEqual(ligne.pu_effectif, Decimal('2500'))
        self.assertEqual(ligne.montant, Decimal('7500'))

    def test_surcharge_du_pu(self):
        ligne = CoutTypeLigne(quantite=Decimal('2'), pu=Decimal('1000'))
        ligne.designation = Designation(nom='Ciment', prix_unitaire=Decimal('2500'))
        self.assertEqual(ligne.montant, Decimal('2000'))


class CoutTypeCleanTests(SimpleTestCase):
    def test_cible_obligatoire_unique(self):
        with self.assertRaises(ValidationError):
            CoutTypeActivite().clean()  # ni équipement ni point d'eau


class FusionnerLignesTests(SimpleTestCase):
    def _ct(self, *lignes):
        class _Lignes:
            def all(self_inner):
                return lignes
        return SimpleNamespace(lignes=_Lignes())

    def test_quantites_additionnees_pour_une_meme_designation(self):
        from apps.planning.couts_types import fusionner_lignes
        ciment = Designation(id='c1', nom='Ciment', prix_unitaire=Decimal('100'))
        sable = Designation(id='s1', nom='Sable', prix_unitaire=Decimal('50'))
        ct1 = self._ct(CoutTypeLigne(designation=ciment, quantite=Decimal('2')))
        ct2 = self._ct(CoutTypeLigne(designation=ciment, quantite=Decimal('3')),
                       CoutTypeLigne(designation=sable, quantite=Decimal('1')))
        res = {r['designation'].nom: r for r in fusionner_lignes([ct1, ct2])}
        self.assertEqual(res['Ciment']['quantite'], Decimal('5'))
        self.assertEqual(res['Sable']['quantite'], Decimal('1'))


from django.test import override_settings  # noqa: E402


@override_settings(
    ALLOWED_HOSTS=['www.hydria.mg', 'ouvrages.hydria.mg'],
    OUVRAGES_SUBDOMAIN_HOSTS=['ouvrages.hydria.mg'],
    OUVRAGES_SUBDOMAIN_URL='https://ouvrages.hydria.mg',
)
class PageCoutsTypesSousDomaineTests(SimpleTestCase):
    def test_ancienne_adresse_redirige_vers_le_sous_domaine(self):
        for chemin in ('/plannings/couts-types/', '/plannings/couts-types'):
            response = self.client.get(chemin + '?x=1', HTTP_HOST='www.hydria.mg')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['Location'], 'https://ouvrages.hydria.mg/couts-types/?x=1')

    def test_le_sous_domaine_ne_redirige_pas(self):
        response = self.client.get('/couts-types/', HTTP_HOST='ouvrages.hydria.mg')
        self.assertNotIn('ouvrages.hydria.mg/couts-types/', response.get('Location', ''))
        self.assertEqual(response.status_code, 302)  # connexion requise, pas de boucle
        self.assertIn('/accounts/login', response['Location'])

    def test_api_apercu_reste_sur_le_site_principal(self):
        response = self.client.get('/plannings/couts-types/api/apercu/', HTTP_HOST='www.hydria.mg')
        self.assertNotIn('ouvrages.hydria.mg', response.get('Location', ''))


class HistoriqueAgregationTests(SimpleTestCase):
    @staticmethod
    def _ligne(did, nom, quantite, pu):
        return {'designation_id': did, 'designation': nom, 'type': 'Matériel', 'unite': 'sac',
                'pu_designation': pu, 'quantite': quantite, 'pu': pu, 'montant': quantite * pu}

    def _interventions(self):
        def interv(lignes):
            return {'planning_id': 'x', 'date': '01/01/2026', 'ouvrage': 'O', 'cible': 'C',
                    'composants': [], 'lignes': lignes, 'total': sum(l['montant'] for l in lignes)}
        return [
            interv([self._ligne('c', 'Ciment', 2, 100), self._ligne('s', 'Sable', 1, 50)]),
            interv([self._ligne('c', 'Ciment', 4, 120)]),
            interv([self._ligne('c', 'Ciment', 3, 110)]),
            interv([]),  # intervention sans coût saisi : ignorée des statistiques
        ]

    def test_statistiques_par_designation(self):
        from apps.planning.couts_types_historique import agreger_historique
        res = agreger_historique(self._interventions())
        self.assertEqual(res['nb_interventions'], 3)
        self.assertEqual(res['nb_sans_detail'], 1)
        ciment, sable = res['designations']          # triées : la plus fréquente d'abord
        self.assertEqual((ciment['designation'], ciment['nb'], ciment['frequence']), ('Ciment', 3, 100))
        self.assertEqual(ciment['quantite_mediane'], 3)
        self.assertEqual(ciment['pu_moyen'], 110)
        self.assertEqual((sable['nb'], sable['frequence']), (1, 33))

    def test_designation_repetee_dans_une_intervention_est_cumulee(self):
        from apps.planning.couts_types_historique import agreger_historique
        interv = {'planning_id': 'x', 'date': '', 'ouvrage': '', 'cible': '', 'composants': [],
                  'lignes': [self._ligne('c', 'Ciment', 2, 100), self._ligne('c', 'Ciment', 1, 100)],
                  'total': 300}
        res = agreger_historique([interv])
        self.assertEqual(res['designations'][0]['quantite_mediane'], 3)
        self.assertEqual(res['designations'][0]['nb'], 1)

    def test_historique_vide(self):
        from apps.planning.couts_types_historique import agreger_historique
        res = agreger_historique([])
        self.assertEqual((res['nb_interventions'], res['total_moyen'], res['designations']), (0, 0, []))


class ChoixNiveauHistoriqueTests(SimpleTestCase):
    def test_premier_niveau_qui_atteint_le_seuil(self):
        from apps.planning.couts_types_historique import choisir_niveau_auto
        evals = [('composant', 1), ('souple', 4), ('type', 30), ('activite', 80)]
        self.assertEqual(choisir_niveau_auto(evals), 'souple')

    def test_composant_exact_suffisant(self):
        from apps.planning.couts_types_historique import choisir_niveau_auto
        self.assertEqual(choisir_niveau_auto([('composant', 5), ('souple', 9)]), 'composant')

    def test_sans_niveau_suffisant_prend_celui_qui_a_le_plus_d_interventions(self):
        from apps.planning.couts_types_historique import choisir_niveau_auto
        evals = [('composant', 0), ('souple', 2), ('type', 2), ('activite', 1)]
        self.assertEqual(choisir_niveau_auto(evals), 'souple')   # égalité : le plus précis

    def test_rien_nulle_part_garde_le_plus_precis(self):
        from apps.planning.couts_types_historique import choisir_niveau_auto
        self.assertEqual(choisir_niveau_auto([('composant', 0), ('souple', 0)]), 'composant')

    def test_niveaux_a_essayer(self):
        from apps.planning.couts_types_historique import niveaux_a_essayer
        self.assertEqual(niveaux_a_essayer('x'), ['composant', 'souple', 'type', 'activite'])
        self.assertEqual(niveaux_a_essayer(None), ['type', 'activite'])


class ChecklistTests(SimpleTestCase):
    FICHE = 'f1'

    def _cle(self, genre='equipement', type_id='t1', composant=None):
        from apps.planning.couts_types_checklist import cle_combinaison
        return cle_combinaison(self.FICHE, genre, type_id, composant)

    def test_statuts_a_remplir_vide_rempli(self):
        from apps.planning.couts_types_checklist import assembler_checklist
        a, b, c = self._cle(type_id='a'), self._cle(type_id='b'), self._cle(type_id='c')
        observees = {a: {'nb': 5, 'nb_chiffrees': 4, 'totaux': [100.0, 300.0]},
                     b: {'nb': 1, 'nb_chiffrees': 0, 'totaux': []},
                     c: {'nb': 2, 'nb_chiffrees': 2, 'totaux': [50.0]}}
        bareme = {b: {'id': 'B', 'nb_lignes': 0}, c: {'id': 'C', 'nb_lignes': 3}}
        res = {l['cle']: l for l in assembler_checklist(observees, bareme)}
        self.assertEqual(res[a]['statut'], 'a_remplir')
        self.assertEqual(res[a]['reel_moyen'], 200.0)
        self.assertEqual(res[b]['statut'], 'vide')
        self.assertEqual(res[c]['statut'], 'rempli')
        self.assertEqual(res[c]['cout_type_id'], 'C')

    def test_union_des_sources_sans_doublon(self):
        from apps.planning.couts_types_checklist import assembler_checklist
        commune = self._cle(type_id='x')
        seul_bareme = self._cle(type_id='y')
        seul_theorique = self._cle(type_id='z')
        res = assembler_checklist(
            {commune: {'nb': 1, 'nb_chiffrees': 1, 'totaux': [10.0]}},
            {commune: {'id': 'K', 'nb_lignes': 1}, seul_bareme: {'id': 'L', 'nb_lignes': 2}},
            theoriques=[commune, seul_theorique],
        )
        self.assertEqual(len(res), 3)
        par_cle = {l['cle']: l for l in res}
        self.assertTrue(par_cle[commune]['observee'])
        self.assertFalse(par_cle[seul_bareme]['observee'])
        self.assertFalse(par_cle[seul_theorique]['observee'])
        self.assertEqual(par_cle[seul_theorique]['statut'], 'a_remplir')
        self.assertEqual(par_cle[seul_theorique]['nb_historique'], 0)

    def test_cle_composant_distincte_du_type(self):
        self.assertNotEqual(self._cle(composant=None), self._cle(composant='c1'))
        self.assertEqual(self._cle(composant=None)[3], None)
