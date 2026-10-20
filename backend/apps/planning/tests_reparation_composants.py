from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.planning import reparation_composants as rc


def _planning(eq_id=None, pe_id=None):
    return SimpleNamespace(
        cible_equipement_id=eq_id, cible_point_eau_id=pe_id,
        cible_equipement=None, cible_point_eau=None,
        save=MagicMock(), composants_equipement=MagicMock(), composants_point_eau=MagicMock(),
    )


class ParseComposantsIdsTests(SimpleTestCase):
    def test_absent_returns_none(self):
        self.assertIsNone(rc.parse_composants_ids({'x': 1}))

    def test_comma_separated_string_from_mobile_form(self):
        self.assertEqual(rc.parse_composants_ids({'composants_ids': 'a, b,,a'}), ['a', 'b'])
        self.assertEqual(rc.parse_composants_ids({'composants_ids': ''}), [])

    def test_empty_and_dedup(self):
        self.assertEqual(rc.parse_composants_ids({'composants_ids': None}), [])
        self.assertEqual(rc.parse_composants_ids({'composants_ids': ['a', ' a ', '', 'b']}), ['a', 'b'])
        self.assertEqual(rc.parse_composants_ids({'composants': 'a'}), ['a'])


class ApplyRepairTargetTests(SimpleTestCase):
    def test_both_targets_rejected(self):
        with self.assertRaises(rc.ComposantsError):
            rc.apply_repair_target(_planning(), SimpleNamespace(id=1), SimpleNamespace(id=2), [])

    def test_components_without_target_rejected(self):
        with self.assertRaises(rc.ComposantsError):
            rc.apply_repair_target(_planning(), None, None, ['c1'])

    def test_unchanged_target_and_none_keeps_components(self):
        p = _planning(pe_id=7)
        rc.apply_repair_target(p, None, SimpleNamespace(id=7, type_point_eau_id=1), None)
        p.composants_point_eau.set.assert_not_called()

    def test_changed_target_clears_components(self):
        p = _planning(pe_id=7)
        rc.apply_repair_target(p, SimpleNamespace(id=9, type_equipement_id=1), None, None)
        p.composants_equipement.set.assert_called_once_with([])
        p.composants_point_eau.set.assert_called_once_with([])

    def test_components_of_other_type_rejected(self):
        p = _planning()
        pe = SimpleNamespace(id=1, type_point_eau_id=5)
        with patch.object(rc.ComposantTypePointEau.objects, 'filter', return_value=[object()]):
            with self.assertRaises(rc.ComposantsError):
                rc.apply_repair_target(p, None, pe, ['c1', 'c2'])

    def test_valid_point_eau_components_saved(self):
        p = _planning()
        pe = SimpleNamespace(id=1, type_point_eau_id=5)
        comps = [object(), object()]
        with patch.object(rc.ComposantTypePointEau.objects, 'filter', return_value=comps) as f:
            rc.apply_repair_target(p, None, pe, ['c1', 'c2'])
        f.assert_called_once_with(id__in=['c1', 'c2'], type_point_eau_id=5)
        p.composants_point_eau.set.assert_called_once_with(comps)
        p.composants_equipement.set.assert_called_once_with([])


class ReglesFicheTests(SimpleTestCase):
    """Règles de cible / composants paramétrées par activité (FichePoste)."""

    EQ, PE = SimpleNamespace(id=1), SimpleNamespace(id=2)

    def _verifier(self, fiche, eq, pe, ids, disponibles=None):
        disponibles = [{'id': 'c1', 'nom': 'x'}] if disponibles is None else disponibles
        with patch.object(rc, 'composants_disponibles', return_value=disponibles):
            rc.verifier_regles_fiche(fiche, eq, pe, ids)

    def _fiche(self, **kwargs):
        return SimpleNamespace(tache='Réparation fuite', **kwargs)

    def test_sans_fiche_ou_par_defaut_rien_n_est_exige(self):
        self._verifier(None, None, None, [])
        self._verifier(self._fiche(), None, None, [])

    def test_cible_obligatoire(self):
        fiche = self._fiche(cible_mode='obligatoire')
        with self.assertRaises(rc.ComposantsError):
            self._verifier(fiche, None, None, [])
        self._verifier(fiche, None, self.PE, [])

    def test_types_de_cible_admis(self):
        with self.assertRaises(rc.ComposantsError):
            self._verifier(self._fiche(cible_types='point_eau'), self.EQ, None, [])
        with self.assertRaises(rc.ComposantsError):
            self._verifier(self._fiche(cible_types='equipement'), None, self.PE, [])
        self._verifier(self._fiche(cible_types='equipement'), self.EQ, None, [])

    def test_composants_obligatoires_impliquent_une_cible(self):
        fiche = self._fiche(composants_mode='obligatoire')
        with self.assertRaises(rc.ComposantsError):
            self._verifier(fiche, None, None, [])
        with self.assertRaises(rc.ComposantsError):
            self._verifier(fiche, None, self.PE, [])
        self._verifier(fiche, None, self.PE, ['c1'])

    def test_composants_obligatoires_sans_catalogue_ne_bloquent_pas(self):
        self._verifier(self._fiche(composants_mode='obligatoire'), None, self.PE, [], disponibles=[])

    def test_un_seul_composant(self):
        fiche = self._fiche(composants_multiple=False)
        with self.assertRaises(rc.ComposantsError):
            self._verifier(fiche, None, self.PE, ['a', 'b'])
        self._verifier(fiche, None, self.PE, ['a'])

    def test_regles_effectives(self):
        self.assertEqual(rc.regles_fiche(self._fiche(composants_mode='obligatoire'))['cible_mode'], 'obligatoire')
        effectives = rc.regles_fiche(self._fiche(cible_mode='non'))
        self.assertEqual(effectives['composants_mode'], 'non')


class ComposantsAdmisTests(SimpleTestCase):
    """Activité restreinte à certains composants (ex. anti-rouille -> parties métalliques)."""

    PE = SimpleNamespace(id=2, type_point_eau_id=5)

    def _fiche(self, admis):
        fiche = SimpleNamespace(tache='Anti-rouille', composants_admis=admis)
        fiche.composants_admis_liste = lambda: [n.strip() for n in admis.splitlines() if n.strip()]
        return fiche

    def test_normalisation_ignore_accents_casse_et_tirets(self):
        self.assertEqual(rc.normaliser_nom_composant(' Boîte  Métallique '), 'boite metallique')
        self.assertEqual(rc.normaliser_nom_composant('Cadenas-vita gasy'), 'cadenas vita gasy')

    def test_liste_filtree_par_activite(self):
        fiche = self._fiche('Boite metallique\nFer plat')
        catalogue = [SimpleNamespace(id=1, nom_composant='Boîte métallique'),
                     SimpleNamespace(id=2, nom_composant='Robinet'),
                     SimpleNamespace(id=3, nom_composant='FER PLAT')]
        with patch.object(rc.ComposantTypePointEau.objects, 'filter', return_value=catalogue):
            noms = [c['nom'] for c in rc.composants_disponibles(point_eau=self.PE, fiche=fiche)]
            tous = rc.composants_disponibles(point_eau=self.PE)
        self.assertEqual(noms, ['Boîte métallique', 'FER PLAT'])
        self.assertEqual(len(tous), 3)

    def test_composant_non_admis_refuse(self):
        fiche = self._fiche('Boîte métallique')
        robinet = SimpleNamespace(id='c2', nom_composant='Robinet')
        with patch.object(rc.ComposantTypeEquipement.objects, 'filter', return_value=[]), \
                patch.object(rc.ComposantTypePointEau.objects, 'filter', return_value=[robinet]):
            with self.assertRaises(rc.ComposantsError) as ctx:
                rc.verifier_regles_fiche(fiche, None, self.PE, ['c2'])
        self.assertIn('Robinet', str(ctx.exception))

    def test_regles_exposent_la_liste(self):
        self.assertEqual(rc.regles_fiche(self._fiche('Fer plat\n\nCadenas'))['composants_admis'], ['Fer plat', 'Cadenas'])
        self.assertEqual(rc.regles_fiche(SimpleNamespace(tache='x'))['composants_admis'], [])


class DecodeMobilePhotoTests(SimpleTestCase):
    """Base64 des photos terrain altéré pendant le transport."""

    def test_reparations_de_transport(self):
        import base64
        from apps.planning.views_preparation_tournee import _decode_mobile_photo
        brut = bytes(range(256)) * 3          # contient des octets donnant « + » et « / »
        propre = base64.b64encode(brut).decode()
        self.assertIn('+', propre)
        variantes = [
            propre,
            propre.replace('+', ' '),                                        # « + » lu comme espace
            '\n'.join(propre[i:i + 76] for i in range(0, len(propre), 76)),  # Base64.DEFAULT
            base64.urlsafe_b64encode(brut).decode().rstrip('='),             # URL-safe sans padding
        ]
        for variante in variantes:
            data, content_type, error = _decode_mobile_photo({'photo_data': variante, 'content_type': 'image/jpeg'})
            self.assertIsNone(error, variante[:20])
            self.assertEqual(base64.b64decode(data), brut)

    def test_vraiment_invalide(self):
        from apps.planning.views_preparation_tournee import _decode_mobile_photo
        self.assertIn('Photo invalide', _decode_mobile_photo({'photo_data': 'abc$%^'})[2])
        self.assertIn('vide', _decode_mobile_photo({'photo_data': '  '})[2])
