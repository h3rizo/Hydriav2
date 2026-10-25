"""Historique consultable des versions (Q12) et migration des dossiers techniques (Q6)."""
import hashlib
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings

from apps.organization.models import Ouvrage, OuvrageDossierTechnique
from apps.sync.models import CategorieFichier, Fichier, FichierVersion

from .test_api import BaseSync


class HistoriqueDesVersionsTests(BaseSync):
    def deposer_et_remplacer(self, contenus):
        """Dépose le premier contenu puis remplace avec les suivants ; retourne l'id du fichier."""
        fiche = self.deposer_organisation(contenu=contenus[0]).json()
        client = self.client_pour(self.user_a)
        for numero, contenu in enumerate(contenus[1:], start=1):
            r = client.patch(f"/api/fichiers/{fiche['id']}/",
                             {'fichier': SimpleUploadedFile('procedure.pdf', contenu)},
                             format='multipart', HTTP_IF_MATCH=str(numero))
            self.assertEqual(r.status_code, 200, r.content)
        return fiche['id']

    def test_liste_et_telechargement_d_une_ancienne_version(self):
        fid = self.deposer_et_remplacer([b'version un', b'version deux', b'version trois'])
        client = self.client_pour(self.user_a)
        corps = client.get(f'/api/fichiers/{fid}/versions/').json()
        self.assertEqual([v['numero'] for v in corps['versions']], [3, 2, 1])
        self.assertEqual([v['courante'] for v in corps['versions']], [True, False, False])
        self.assertEqual(corps['versions'][2]['origine'], 'depot')
        self.assertEqual(corps['versions'][1]['origine'], 'remplacement')
        self.assertEqual(corps['versions'][2]['sha256'], hashlib.sha256(b'version un').hexdigest())

        ancien = client.get(f'/api/fichiers/{fid}/versions/1/telechargement')
        self.assertEqual(b''.join(ancien.streaming_content), b'version un')
        courant = client.get(f'/api/fichiers/{fid}/telechargement')
        self.assertEqual(b''.join(courant.streaming_content), b'version trois')
        self.assertEqual(client.get(f'/api/fichiers/{fid}/versions/9/telechargement').status_code, 404)

    def test_renommage_ne_cree_pas_de_version_de_contenu(self):
        fid = self.deposer_et_remplacer([b'un'])
        client = self.client_pour(self.user_a)
        r = client.patch(f'/api/fichiers/{fid}/', {'nom': 'autre.pdf'}, format='json', HTTP_IF_MATCH='1')
        self.assertEqual((r.status_code, r.json()['version']), (200, 2))
        versions = client.get(f'/api/fichiers/{fid}/versions/').json()['versions']
        self.assertEqual([(v['numero'], v['nom']) for v in versions], [(1, 'autre.pdf')])

    def test_restauration_recopie_sans_reecrire_l_historique(self):
        fid = self.deposer_et_remplacer([b'version un', b'version deux'])
        client = self.client_pour(self.user_a)
        self.assertEqual(client.post(f'/api/fichiers/{fid}/versions/1/restaurer').status_code, 428)
        self.assertEqual(client.post(f'/api/fichiers/{fid}/versions/1/restaurer', HTTP_IF_MATCH='1').status_code, 409)
        r = client.post(f'/api/fichiers/{fid}/versions/1/restaurer', HTTP_IF_MATCH='2')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['version'], 3)

        versions = client.get(f'/api/fichiers/{fid}/versions/').json()['versions']
        self.assertEqual([v['numero'] for v in versions], [3, 2, 1])
        self.assertEqual((versions[0]['origine'], versions[0]['restaure_de']), ('restauration', 1))
        courant = client.get(f'/api/fichiers/{fid}/telechargement')
        self.assertEqual(b''.join(courant.streaming_content), b'version un')
        deux = client.get(f'/api/fichiers/{fid}/versions/2/telechargement')
        self.assertEqual(b''.join(deux.streaming_content), b'version deux', "La version 2 reste intacte.")
        # restaurer la version déjà courante n'a pas de sens
        r = client.post(f'/api/fichiers/{fid}/versions/3/restaurer', HTTP_IF_MATCH='3')
        self.assertEqual((r.status_code, r.json()['code']), (400, 'DEJA_COURANTE'))

    def test_elagage_au_dela_du_maximum(self):
        with override_settings(HYDRIA_VERSIONS_MAX=2):
            fid = self.deposer_et_remplacer([b'un', b'deux', b'trois'])
        fichier = Fichier.objects.get(pk=fid)
        self.assertEqual(list(fichier.versions.order_by('numero').values_list('numero', flat=True)), [2, 3])
        corbeille = [p for p in (Path(self.dossier) / '_corbeille').rglob('*') if p.is_file()]
        self.assertEqual(len(corbeille), 1, "La version élaguée est déplacée dans la corbeille, pas détruite.")

    def test_le_quota_compte_toutes_les_versions(self):
        with override_settings(HYDRIA_QUOTA_ORGA_GO=2000 / 1024 ** 3):  # ~2000 octets
            fiche = self.deposer_organisation(contenu=b'x' * 1500).json()
            r = self.client_pour(self.user_a).patch(
                f"/api/fichiers/{fiche['id']}/", {'fichier': SimpleUploadedFile('p.pdf', b'y' * 1500)},
                format='multipart', HTTP_IF_MATCH='1')
        self.assertEqual((r.status_code, r.json()['code']), (413, 'QUOTA_DEPASSE'))
        self.assertEqual(Fichier.objects.get(pk=fiche['id']).versions.count(), 1)

    def test_suppression_deplace_toutes_les_versions(self):
        fid = self.deposer_et_remplacer([b'un', b'deux'])
        r = self.client_pour(self.user_a).delete(f'/api/fichiers/{fid}/')
        self.assertEqual(r.status_code, 200, r.content)
        chemins = list(FichierVersion.objects.filter(fichier_id=fid).values_list('storage_path', flat=True))
        self.assertEqual(len(chemins), 2)
        for chemin in chemins:
            self.assertTrue(chemin.startswith('_corbeille/'))
            self.assertTrue((Path(self.dossier) / chemin).is_file())
        self.assertEqual(self.client_pour(self.user_a).get(f'/api/fichiers/{fid}/versions/').status_code, 404)

    def test_autre_organisation_ne_voit_pas_l_historique(self):
        fid = self.deposer_et_remplacer([b'un', b'deux'])
        client_b = self.client_pour(self.user_b)
        self.assertEqual(client_b.get(f'/api/fichiers/{fid}/versions/').status_code, 404)
        self.assertEqual(client_b.get(f'/api/fichiers/{fid}/versions/1/telechargement').status_code, 404)
        self.assertEqual(client_b.post(f'/api/fichiers/{fid}/versions/1/restaurer', HTTP_IF_MATCH='2').status_code, 404)


class MigrationDossiersTechniquesTests(BaseSync):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp(prefix='hydria-media-test-')
        self.addCleanup(shutil.rmtree, self.media, True)
        reglage = override_settings(MEDIA_ROOT=self.media)
        reglage.enable()
        self.addCleanup(reglage.disable)

    def creer_dossier(self, ouvrage, nom, contenu=b'contenu'):
        return OuvrageDossierTechnique.objects.create(
            ouvrage=ouvrage, fichier=SimpleUploadedFile(nom, contenu), nom_affichage=nom)

    def lancer(self, *arguments):
        sortie = StringIO()
        call_command('migrer_dossiers_techniques', *arguments, stdout=sortie, stderr=sortie)
        return sortie.getvalue()

    def test_simulation_n_ecrit_rien(self):
        self.creer_dossier(self.ouvrage_a, 'plan.xlsm')
        sortie = self.lancer()
        self.assertIn('SIMULATION', sortie)
        self.assertEqual(Fichier.objects.count(), 0)
        self.assertEqual([p for p in Path(self.dossier).rglob('*') if p.is_file()], [])

    def test_migration_complete_idempotente_et_non_destructive(self):
        ancien = self.creer_dossier(self.ouvrage_a, 'plan.xlsm', b'plan technique')
        self.creer_dossier(self.ouvrage_b, 'schema.pdf', b'%PDF schema')
        sortie = self.lancer('--appliquer')
        self.assertIn('APPLIQUÉ', sortie)

        plan = Fichier.objects.get(nom='plan.xlsm')
        self.assertEqual((plan.organisation_id, plan.entity_type, plan.entity_id, plan.categorie_id),
                         (self.org_a.id, 'ouvrage', self.ouvrage_a.id, 'dossier_technique'))
        self.assertEqual(plan.sha256, hashlib.sha256(b'plan technique').hexdigest())
        self.assertEqual((Path(self.dossier) / plan.storage_path).read_bytes(), b'plan technique')
        self.assertEqual(plan.versions.count(), 1)
        self.assertEqual(Fichier.objects.get(nom='schema.pdf').organisation_id, self.org_b.id)

        ancien.refresh_from_db()
        self.assertTrue(Path(ancien.fichier.path).is_file(), "L'ancien fichier de media/ n'est pas touché.")
        self.assertEqual(OuvrageDossierTechnique.objects.count(), 2)

        sortie = self.lancer('--appliquer')
        self.assertEqual(Fichier.objects.count(), 2, "Relancer ne crée pas de doublon.")
        self.assertIn('déjà migrés : 2', sortie)

    def test_cas_ignores_et_organisation_par_defaut(self):
        type_ouvrage = self.ouvrage_a.type_ouvrage
        orphelin = Ouvrage.objects.create(nom_ouvrage='Sans gestionnaire', type_ouvrage=type_ouvrage)
        self.creer_dossier(orphelin, 'orphelin.pdf')
        self.creer_dossier(self.ouvrage_a, 'virus.exe', b'MZ')
        sortie = self.lancer('--appliquer')
        self.assertEqual(Fichier.objects.count(), 0)
        self.assertIn('sans gestionnaire (ignorés) : 1', sortie)
        self.assertIn('extension refusée : 1', sortie)

        self.lancer('--appliquer', '--organisation-defaut', str(self.org_b.id))
        self.assertEqual(Fichier.objects.get(nom='orphelin.pdf').organisation_id, self.org_b.id)

    def test_extensions_des_dossiers_existants_acceptees(self):
        extensions = set(CategorieFichier.objects.get(code='dossier_technique').extensions)
        self.assertTrue({'xls', 'xlsx', 'doc', 'pdf', 'xlsm', 'pub', 'jpg', 'docx', 'bmp', 'txt', 'vsdx'} <= extensions)
