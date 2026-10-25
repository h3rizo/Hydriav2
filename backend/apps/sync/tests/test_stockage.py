"""Tests du service de stockage (sans base de données)."""
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.sync import stockage


class StockageTests(SimpleTestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp(prefix='hydria-sync-test-')
        self.addCleanup(shutil.rmtree, self.dossier, True)
        reglage = override_settings(HYDRIA_STORAGE_DIR=self.dossier)
        reglage.enable()
        self.addCleanup(reglage.disable)
        self.ident = uuid.uuid4()
        self.entite = uuid.uuid4()

    # --- chemins ---------------------------------------------------------

    def test_chemins_attendus(self):
        chemin = stockage.chemin_relatif_entite('equipement', self.entite, 'photos_equipement', self.ident, 'jpg')
        self.assertEqual(chemin, f'entite/equipement/{self.entite}/photos_equipement/{self.ident}.jpg')
        orga = uuid.uuid4()
        chemin = stockage.chemin_relatif_organisation(orga, 'financier', 'facture', self.ident, 'pdf')
        self.assertEqual(chemin, f'organisation/{orga}/financier/facture/{self.ident}.pdf')

    def test_refuse_composants_malicieux(self):
        for mauvais in ('../etc', 'a/b', 'Photos', '', 'a b', '..'):
            with self.assertRaises(stockage.CheminInvalide, msg=mauvais):
                stockage.chemin_relatif_entite(mauvais, self.entite, 'photos_equipement', self.ident)
            with self.assertRaises(stockage.CheminInvalide, msg=mauvais):
                stockage.chemin_relatif_entite('equipement', self.entite, mauvais, self.ident)
        with self.assertRaises(stockage.CheminInvalide):
            stockage.chemin_relatif_entite('equipement', '../../x', 'photos_equipement', self.ident)
        with self.assertRaises(stockage.CheminInvalide):
            stockage.chemin_relatif_entite('equipement', self.entite, 'photos_equipement', self.ident, 'p/../x')

    def test_path_traversal_refuse(self):
        for mauvais in ('../secret', 'entite/../../secret', '/etc/passwd', 'C:/Windows/x', 'a\\b',
                        'entite//x', './x', 'a/./b', '', 'x\x00y'):
            with self.assertRaises(stockage.CheminInvalide, msg=repr(mauvais)):
                stockage.resoudre(mauvais)
            with self.assertRaises(stockage.CheminInvalide, msg=repr(mauvais)):
                stockage.ecrire([b'x'], mauvais)
        self.assertEqual(list(Path(self.dossier).iterdir()), [])

    def test_lien_symbolique_sortant_refuse(self):
        dehors = tempfile.mkdtemp(prefix='hydria-dehors-')
        self.addCleanup(shutil.rmtree, dehors, True)
        lien = Path(self.dossier) / 'entite'
        try:
            lien.symlink_to(dehors, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Liens symboliques non disponibles sur cette machine.")
        with self.assertRaises(stockage.CheminInvalide):
            stockage.resoudre('entite/x.txt')

    def test_refuse_stockage_dans_media_ou_static(self):
        with override_settings(HYDRIA_STORAGE_DIR=str(Path(settings.MEDIA_ROOT) / 'sync')):
            with self.assertRaises(ImproperlyConfigured):
                stockage.racine()

    # --- écriture / lecture ---------------------------------------------

    def test_ecriture_atomique_avec_sha256(self):
        contenu = b'bonjour Hydria' * 1000
        chemin = stockage.chemin_relatif_entite('village', self.entite, 'photos_village', self.ident, 'jpg')
        sha, taille = stockage.ecrire([contenu[:5000], contenu[5000:]], chemin)
        self.assertEqual(sha, hashlib.sha256(contenu).hexdigest())
        self.assertEqual(taille, len(contenu))
        with stockage.ouvrir(chemin) as f:
            self.assertEqual(f.read(), contenu)
        restes = [p.name for p in Path(self.dossier).rglob('.tmp-*')]
        self.assertEqual(restes, [], "Aucun fichier temporaire ne doit rester.")

    def test_taille_max_refusee_sans_laisser_de_fichier(self):
        chemin = stockage.chemin_relatif_entite('village', self.entite, 'photos_village', self.ident, 'jpg')
        with self.assertRaises(stockage.FichierTropVolumineux):
            stockage.ecrire([b'x' * 600, b'x' * 600], chemin, taille_max=1000)
        self.assertFalse(stockage.existe(chemin))
        self.assertEqual([p for p in Path(self.dossier).rglob('*') if p.is_file()], [])

    def test_quota_refuse(self):
        chemin = stockage.chemin_relatif_entite('village', self.entite, 'photos_village', self.ident, 'jpg')
        with self.assertRaises(stockage.QuotaDepasse):
            stockage.ecrire([b'x' * 600], chemin, quota_restant=500)
        self.assertFalse(stockage.existe(chemin))

    def test_corbeille_deplace_sans_supprimer(self):
        chemin = stockage.chemin_relatif_entite('village', self.entite, 'photos_village', self.ident, 'jpg')
        stockage.ecrire([b'abc'], chemin)
        corbeille = stockage.mettre_a_la_corbeille(chemin)
        self.assertTrue(corbeille.startswith('_corbeille/'))
        self.assertFalse(stockage.existe(chemin))
        with stockage.ouvrir(corbeille) as f:
            self.assertEqual(f.read(), b'abc')
        self.assertIsNone(stockage.mettre_a_la_corbeille(chemin))

    def test_lecture_fichier_absent(self):
        with self.assertRaises(FileNotFoundError):
            stockage.ouvrir('entite/village/' + str(self.entite) + '/photos_village/absent.jpg')

    def test_reglages_lus_dans_le_fichier_env(self):
        """Régression du 2026-10-25 : python-decouple lit .env sans l'exporter dans os.environ ;
        en production les variables HYDRIA_* étaient ignorées (dépôts en 503)."""
        valeurs = {'HYDRIA_STORAGE_DIR': self.dossier, 'HYDRIA_TAILLE_MAX_MO': '25',
                   'HYDRIA_QUOTA_ORGA_GO': '5', 'HYDRIA_VERSIONS_MAX': '7'}
        faux_env = mock.Mock(side_effect=lambda nom, default=None: valeurs.get(nom, default))
        with override_settings(HYDRIA_STORAGE_DIR=''), \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(stockage, '_config', faux_env):
            for nom in valeurs:
                os.environ.pop(nom, None)
            self.assertEqual(stockage.racine(), Path(self.dossier).resolve())
            self.assertEqual(stockage.taille_max_octets(), 25 * 1024 * 1024)
            self.assertEqual(stockage.quota_organisation_octets(), 5 * 1024 ** 3)
            self.assertEqual(stockage.versions_max(), 7)

    def test_limites_configurables(self):
        with override_settings(HYDRIA_TAILLE_MAX_MO=2, HYDRIA_QUOTA_ORGA_GO=3):
            self.assertEqual(stockage.taille_max_octets(), 2 * 1024 * 1024)
            self.assertEqual(stockage.quota_organisation_octets(), 3 * 1024 ** 3)
