import base64
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.client import RequestFactory

from apps.billing.models import PointEau
from apps.core.models import ContributionTerrain
from apps.employees.models import Employe
from apps.infrastructure.models import EquipementConstitutif
from apps.organization import views
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)
MEDIA = tempfile.mkdtemp(prefix='hydria_test_media_')


def appeler(user, cible_type, cible_id, nom='IMG_1.png', type_mime='image/png'):
    """Appelle la vue d'import sans passer par employe_required (inutile pour ce test)."""
    import inspect
    vue = inspect.unwrap(views.api_ouvrage_photo_lot_import)
    requete = RequestFactory().post('/x', data={
        'cible_type': cible_type, 'cible_id': str(cible_id), 'taille_origine': str(len(PNG)),
        'fichier': SimpleUploadedFile(nom, PNG, content_type=type_mime),
    })
    requete.user = user
    return vue(requete)


@override_settings(MEDIA_ROOT=MEDIA)
class ImportPhotoLotTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user('agent', password='x', is_superuser=True, is_staff=True)
        organisation = Organisation.objects.create(nom_organisation='Org Test')
        base = Base.objects.create(nom_base='Base Test', organisation=organisation)
        self.employe = Employe.objects.create(user=self.user, nom_employe='Agent Test', nom='Test', surnom='AG', base=base)
        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')
        self.ouvrage = Ouvrage.objects.create(nom_ouvrage='Test Ouvrage', type_ouvrage=type_ouvrage)
        self.equipement = EquipementConstitutif.objects.create(nom='Citerne', ouvrage=self.ouvrage)
        self.point = PointEau.objects.create(nomabonne='Rakoto', ouvrage=self.ouvrage, idxls='12')

    def test_photo_sur_un_equipement(self):
        # Régression : EquipementConstitutif.updated_by est un User, pas un Employe (HTTP 500)
        reponse = appeler(self.user, 'equipement', self.equipement.pk)
        self.assertEqual(reponse.status_code, 200, reponse.content)
        self.equipement.refresh_from_db()
        self.assertEqual(len(self.equipement.photos), 1)
        self.assertEqual(self.equipement.photos[0]['original_name'], 'IMG_1.png')
        self.assertEqual(self.equipement.updated_by, self.user)

    def test_photo_sur_un_point_eau(self):
        reponse = appeler(self.user, 'pointeau', self.point.pk)
        self.assertEqual(reponse.status_code, 200, reponse.content)
        self.point.refresh_from_db()
        self.assertEqual(len(self.point.photos), 1)
        self.assertEqual(self.point.updated_by, self.employe)

    def test_meme_photo_deux_fois_est_ignoree(self):
        appeler(self.user, 'equipement', self.equipement.pk)
        reponse = appeler(self.user, 'equipement', self.equipement.pk)
        self.assertIn(b'"ignore": true', reponse.content)
        self.equipement.refresh_from_db()
        self.assertEqual(len(self.equipement.photos), 1)

    def test_le_journal_compte_la_photo(self):
        from apps.core.contributions import definir_auteur
        definir_auteur(self.user, 'web')
        try:
            appeler(self.user, 'equipement', self.equipement.pk)
        finally:
            definir_auteur(None)
        ligne = ContributionTerrain.objects.get(categorie='photo')
        self.assertEqual((ligne.action, ligne.quantite, ligne.employe), ('ajout', 1, self.employe))

    def test_heic_sans_type_mime_est_accepte_et_un_fichier_texte_refuse(self):
        # Windows/Edge envoie les .heic avec un type vide : l'extension doit suffire
        accepte = appeler(self.user, 'equipement', self.equipement.pk, nom='IMG_2.HEIC', type_mime='application/octet-stream')
        self.assertEqual(accepte.status_code, 200, accepte.content)
        refuse = appeler(self.user, 'equipement', self.equipement.pk, nom='notes.txt', type_mime='text/plain')
        self.assertEqual(refuse.status_code, 400)


class NomFichierDossierTechniqueTests(SimpleTestCase):
    def test_chemin_de_stockage_tient_dans_100_caracteres(self):
        from types import SimpleNamespace
        from apps.organization.models import ouvrage_dossier_technique_upload_to
        instance = SimpleNamespace(ouvrage_id='1e70e668-0e7b-47fa-84da-c9529c1c2990')
        chemin = ouvrage_dossier_technique_upload_to(instance, 'Sys Des 2.027 Andongozabe 2024 ( à vérifié).xlsm')
        self.assertLessEqual(len(chemin), 100 - 8)
        self.assertTrue(chemin.endswith('.xlsm'))
        court = ouvrage_dossier_technique_upload_to(instance, 'plan.pdf')
        self.assertTrue(court.endswith('/plan.pdf'))
