"""Tests des routes de synchronisation, des triggers et du cloisonnement entre organisations.

Ces tests ont besoin d'une base PostgreSQL (triggers) : Django crée une base ``test_*`` séparée,
la base de développement n'est pas touchée.
"""
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.billing.models import ModaliteGestion, PointEau
from apps.core.models import WidgetAuthToken
from apps.employees.models import Employe
from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import Activite, TypeActivite
from apps.sync.models import Fichier, SyncChange


class BaseSync(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organisation.objects.create(nom_organisation='Org A')
        cls.org_b = Organisation.objects.create(nom_organisation='Org B')
        cls.user_a = cls._utilisateur('agent_a', cls.org_a)
        cls.user_b = cls._utilisateur('agent_b', cls.org_b)
        cls.root = User.objects.create_superuser('root', 'root@example.com', 'pw-test-123')

        cls.region = Region.objects.create(nom_region='Analanjirofo')
        cls.district = District.objects.create(nom_district='Soanierana', region=cls.region)
        cls.commune = Commune.objects.create(nom_commune='Ampasina', district=cls.district)
        cls.fokontany = Fokontany.objects.create(nom_fokontany='Fkt 1', commune=cls.commune)
        cls.village = Village.objects.create(nom_village='Village 1', fokontany=cls.fokontany)
        cls.parcelle = Parcelle.objects.create(reference_parcelle='P1', village=cls.village)

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')
        cls.ouvrage_a = Ouvrage.objects.create(nom_ouvrage='Ouvrage A', type_ouvrage=type_ouvrage)
        cls.ouvrage_b = Ouvrage.objects.create(nom_ouvrage='Ouvrage B', type_ouvrage=type_ouvrage)
        for ouvrage, org in ((cls.ouvrage_a, cls.org_a), (cls.ouvrage_b, cls.org_b)):
            ModaliteGestion.objects.create(
                ouvrage=ouvrage, type_gestion='privee', gestionnaire=org, date_debut=date(2020, 1, 1))
        cls.equipement_a = EquipementConstitutif.objects.create(nom='Pompe A', ouvrage=cls.ouvrage_a)
        cls.point_a = PointEau.objects.create(nomabonne='Abonne A', ouvrage=cls.ouvrage_a, parcelle=cls.parcelle)
        type_activite = TypeActivite.objects.create(nomtype='Maintenance')
        cls.activite = Activite.objects.create(nom='Nettoyage', type_activite=type_activite)

    @staticmethod
    def _utilisateur(nom, organisation):
        base = Base.objects.create(nom_base=f'Base {nom}', organisation=organisation)
        user = User.objects.create_user(nom, f'{nom}@example.com', 'pw-test-123')
        Employe.objects.create(nom_employe=nom, nom=nom, base=base, user=user)
        return user

    def setUp(self):
        self.dossier = tempfile.mkdtemp(prefix='hydria-sync-api-')
        self.addCleanup(shutil.rmtree, self.dossier, True)
        reglage = override_settings(HYDRIA_STORAGE_DIR=self.dossier)
        reglage.enable()
        self.addCleanup(reglage.disable)

    def client_pour(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def deposer_equipement(self, user=None, nom='photo.jpg', contenu=b'\xff\xd8jpeg', categorie='photos_equipement',
                           entite=None):
        return self.client_pour(user or self.user_a).post('/api/sync/upload', {
            'fichier': SimpleUploadedFile(nom, contenu, content_type='application/octet-stream'),
            'categorie': categorie, 'entity_type': 'equipement',
            'entity_id': str(entite or self.equipement_a.id),
        }, format='multipart')

    def deposer_organisation(self, user=None, domaine='operationnel', categorie='procedure',
                             nom='procedure.pdf', contenu=b'%PDF-1.4 test', organisation=None):
        donnees = {
            'fichier': SimpleUploadedFile(nom, contenu),
            'categorie': categorie, 'domaine': domaine,
        }
        if organisation:
            donnees['organisation'] = str(organisation.id)
        return self.client_pour(user or self.user_a).post('/api/sync/upload', donnees, format='multipart')


class AuthentificationTests(BaseSync):
    def test_connexion_puis_acces_et_rotation_du_renouvellement(self):
        client = APIClient()
        device = str(uuid.uuid4())
        reponse = client.post('/api/sync/auth/login', {
            'username': 'agent_a', 'password': 'pw-test-123', 'device_id': device, 'device_label': 'PC bureau'},
            format='json')
        self.assertEqual(reponse.status_code, 200, reponse.content)
        jetons = reponse.json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access_token']}")
        self.assertEqual(client.get('/api/sync/changes').status_code, 200)

        renouvele = APIClient().post('/api/sync/auth/refresh', {'refresh_token': jetons['refresh_token']}, format='json')
        self.assertEqual(renouvele.status_code, 200)
        rejoue = APIClient().post('/api/sync/auth/refresh', {'refresh_token': jetons['refresh_token']}, format='json')
        self.assertEqual(rejoue.status_code, 401, "Un jeton de renouvellement ne sert qu'une fois.")

    def test_mauvais_mot_de_passe_et_sans_jeton(self):
        client = APIClient()
        self.assertEqual(client.post('/api/sync/auth/login', {
            'username': 'agent_a', 'password': 'faux', 'device_id': str(uuid.uuid4())}, format='json').status_code, 401)
        self.assertIn(client.get('/api/sync/changes').status_code, (401, 403))

    def test_jeton_d_un_autre_scope_refuse(self):
        jeton = WidgetAuthToken.objects.create(
            user=self.user_a, scope=WidgetAuthToken.SCOPE_MOBILE, expires_at=None)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {jeton.key}')
        self.assertEqual(client.get('/api/sync/changes').status_code, 401)


class DepotEtTelechargementTests(BaseSync):
    def test_depot_sur_equipement_puis_telechargement(self):
        contenu = b'\xff\xd8\xff photo de la pompe'
        reponse = self.deposer_equipement(contenu=contenu)
        self.assertEqual(reponse.status_code, 201, reponse.content)
        fiche = reponse.json()
        self.assertEqual(fiche['version'], 1)
        self.assertEqual(fiche['organisation'], str(self.org_a.id))
        self.assertEqual(fiche['taille'], len(contenu))
        fichier = Fichier.objects.get(pk=fiche['id'])
        self.assertTrue(fichier.storage_path.startswith(f'entite/equipement/{self.equipement_a.id}/photos_equipement/'))
        self.assertNotIn('photo.jpg', fichier.storage_path, "Le nom stocké est un identifiant généré.")
        self.assertEqual(fichier.nom, 'photo.jpg')

        telechargement = self.client_pour(self.user_a).get(fiche['telechargement'])
        self.assertEqual(telechargement.status_code, 200)
        self.assertEqual(b''.join(telechargement.streaming_content), contenu)
        self.assertEqual(telechargement['X-Fichier-Sha256'], fichier.sha256)

    def test_depot_organisation(self):
        reponse = self.deposer_organisation()
        self.assertEqual(reponse.status_code, 201, reponse.content)
        fichier = Fichier.objects.get(pk=reponse.json()['id'])
        self.assertEqual(fichier.portee, 'organisation')
        self.assertEqual(fichier.domaine, 'operationnel')
        self.assertTrue(fichier.storage_path.startswith(f'organisation/{self.org_a.id}/operationnel/procedure/'))

    def test_nom_malicieux_nettoye(self):
        reponse = self.deposer_equipement(nom='../../etc/passwd.jpg')
        self.assertEqual(reponse.status_code, 201, reponse.content)
        fichier = Fichier.objects.get(pk=reponse.json()['id'])
        self.assertEqual(fichier.nom, 'passwd.jpg')
        self.assertNotIn('..', fichier.storage_path)
        racine = Path(self.dossier).resolve()
        self.assertTrue((racine / fichier.storage_path).resolve().is_relative_to(racine))

    def test_domaines_financier_et_administratif_fermes_par_defaut(self):
        for domaine, categorie in (('financier', 'facture'), ('administratif', 'statuts')):
            reponse = self.deposer_organisation(domaine=domaine, categorie=categorie)
            self.assertEqual(reponse.status_code, 403, reponse.content)
            self.assertEqual(reponse.json()['code'], 'DOMAINE_INTERDIT')
        # un superutilisateur n'a pas d'organisation propre : il désigne celle qui dépose
        sans_organisation = self.deposer_organisation(user=self.root, domaine='financier', categorie='facture')
        self.assertEqual(sans_organisation.json()['code'], 'ORGANISATION_REQUISE')
        self.assertEqual(self.deposer_organisation(
            user=self.root, domaine='financier', categorie='facture', organisation=self.org_a).status_code, 201)

    def test_incoherences_categorie(self):
        # catégorie d'un autre type d'entité
        r = self.deposer_equipement(categorie='photos_village')
        self.assertEqual((r.status_code, r.json()['code']), (400, 'CATEGORIE_INCOHERENTE'))
        # catégorie d'organisation utilisée sur une entité
        r = self.deposer_equipement(categorie='procedure')
        self.assertEqual((r.status_code, r.json()['code']), (400, 'CATEGORIE_INCOHERENTE'))
        # mauvais domaine pour la catégorie
        r = self.deposer_organisation(domaine='logistique', categorie='procedure')
        self.assertEqual((r.status_code, r.json()['code']), (400, 'CATEGORIE_INCOHERENTE'))
        # type de fichier incohérent avec la catégorie (un exécutable dans des photos)
        r = self.deposer_equipement(nom='virus.exe', contenu=b'MZ')
        self.assertEqual((r.status_code, r.json()['code']), (400, 'TYPE_FICHIER_INCOHERENT'))
        # portée ambiguë / manquante / catégorie inconnue
        r = self.client_pour(self.user_a).post('/api/sync/upload', {
            'fichier': SimpleUploadedFile('a.pdf', b'x'), 'categorie': 'procedure',
            'domaine': 'operationnel', 'entity_type': 'equipement', 'entity_id': str(self.equipement_a.id)},
            format='multipart')
        self.assertEqual(r.json()['code'], 'PORTEE_AMBIGUE')
        r = self.client_pour(self.user_a).post('/api/sync/upload', {
            'fichier': SimpleUploadedFile('a.pdf', b'x'), 'categorie': 'inexistante', 'domaine': 'operationnel'},
            format='multipart')
        self.assertEqual(r.json()['code'], 'CATEGORIE_INCONNUE')
        self.assertEqual(Fichier.objects.count(), 0)

    def test_quota_organisation(self):
        with override_settings(HYDRIA_QUOTA_ORGA_GO=2000 / 1024 ** 3):  # ~2000 octets
            self.assertEqual(self.deposer_equipement(contenu=b'x' * 1500).status_code, 201)
            r = self.deposer_equipement(contenu=b'x' * 1500)
            self.assertEqual((r.status_code, r.json()['code']), (413, 'QUOTA_DEPASSE'))
            # le quota est propre à chaque organisation
            r = self.deposer_organisation(user=self.user_b, contenu=b'x' * 1500)
            self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Fichier.objects.count(), 2)

    def test_taille_maximale(self):
        with override_settings(HYDRIA_TAILLE_MAX_MO=1000 / 1024 ** 2):  # ~1000 octets
            r = self.deposer_equipement(contenu=b'x' * 2000)
        self.assertEqual((r.status_code, r.json()['code']), (413, 'FICHIER_TROP_VOLUMINEUX'))
        self.assertEqual(Fichier.objects.count(), 0)
        self.assertEqual([p for p in Path(self.dossier).rglob('*') if p.is_file()], [])


class CloisonnementTests(BaseSync):
    def test_autre_organisation_ne_voit_ni_ne_telecharge_ni_ne_depose(self):
        fiche = self.deposer_organisation().json()
        client_b = self.client_pour(self.user_b)
        self.assertEqual(client_b.get(fiche['telechargement']).status_code, 404)
        self.assertEqual(client_b.patch(f"/api/fichiers/{fiche['id']}/", {'nom': 'x.pdf'},
                                        format='json', HTTP_IF_MATCH='1').status_code, 404)
        self.assertEqual(client_b.delete(f"/api/fichiers/{fiche['id']}/").status_code, 404)
        fichiers = client_b.get('/api/fichiers/?domaine=operationnel').json()['fichiers']
        self.assertEqual(fichiers, [])
        # dépôt sur l'équipement d'un ouvrage géré par une autre organisation
        r = self.deposer_equipement(user=self.user_b)
        self.assertEqual((r.status_code, r.json()['code']), (404, 'ENTITE_INTROUVABLE'))
        # organisation étrangère demandée explicitement
        r = self.client_pour(self.user_b).post('/api/sync/upload', {
            'fichier': SimpleUploadedFile('p.pdf', b'x'), 'categorie': 'procedure', 'domaine': 'operationnel',
            'organisation': str(self.org_a.id)}, format='multipart')
        self.assertEqual((r.status_code, r.json()['code']), (403, 'ORGANISATION_INTERDITE'))

    def test_journal_des_changements_cloisonne(self):
        self.deposer_organisation()
        self.deposer_equipement()
        flux_b = self.client_pour(self.user_b).get('/api/sync/changes?limit=1000').json()['changes']
        self.assertTrue(flux_b, "B reçoit au moins le référentiel.")
        self.assertFalse([c for c in flux_b if c['fichier']], "B ne reçoit aucun fichier de A.")
        ids_ouvrages = {c['entity_id'] for c in flux_b if c['entity_type'] == 'ouvrage'}
        self.assertIn(str(self.ouvrage_b.id), ids_ouvrages)
        self.assertNotIn(str(self.ouvrage_a.id), ids_ouvrages)

        flux_a = self.client_pour(self.user_a).get('/api/sync/changes?limit=1000').json()['changes']
        self.assertEqual(len([c for c in flux_a if c['fichier']]), 2)

    def test_domaine_ferme_absent_du_journal(self):
        self.deposer_organisation(user=self.root, domaine='financier', categorie='facture', organisation=self.org_a)
        flux_a = self.client_pour(self.user_a).get('/api/sync/changes?limit=1000').json()['changes']
        self.assertFalse([c for c in flux_a if c['domaine'] == 'financier'])
        flux_root = self.client_pour(self.root).get('/api/sync/changes?limit=1000').json()['changes']
        self.assertTrue([c for c in flux_root if c['domaine'] == 'financier'])

    def test_arborescence_organisation_refusee_hors_perimetre(self):
        r = self.client_pour(self.user_b).get(f'/api/sync/arborescence?organisation={self.org_a.id}')
        self.assertEqual((r.status_code, r.json()['code']), (403, 'ORGANISATION_INTERDITE'))


class ConflitEtSuppressionTests(BaseSync):
    def test_if_match_et_conflit_409(self):
        fiche = self.deposer_organisation().json()
        url = f"/api/fichiers/{fiche['id']}/"
        client = self.client_pour(self.user_a)

        self.assertEqual(client.patch(url, {'nom': 'x.pdf'}, format='json').status_code, 428)
        self.assertEqual(client.patch(url, {'nom': 'x.pdf'}, format='json', HTTP_IF_MATCH='abc').status_code, 400)

        ok = client.patch(url, {'nom': 'renomme.pdf'}, format='json', HTTP_IF_MATCH='"1"')
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual((ok.json()['version'], ok.json()['nom']), (2, 'renomme.pdf'))

        conflit = client.patch(url, {'nom': 'autre.pdf'}, format='json', HTTP_IF_MATCH='1')
        self.assertEqual(conflit.status_code, 409)
        self.assertEqual(conflit.json()['code'], 'CONFLIT_VERSION')
        self.assertEqual(conflit.json()['version_actuelle'], 2)
        self.assertEqual(Fichier.objects.get(pk=fiche['id']).nom, 'renomme.pdf')

    def test_remplacement_du_contenu_cree_une_version_et_garde_l_ancienne(self):
        fiche = self.deposer_organisation(contenu=b'ancien contenu').json()
        ancien_chemin = Fichier.objects.get(pk=fiche['id']).storage_path
        r = self.client_pour(self.user_a).patch(
            f"/api/fichiers/{fiche['id']}/",
            {'fichier': SimpleUploadedFile('procedure.pdf', b'nouveau contenu')},
            format='multipart', HTTP_IF_MATCH='1')
        self.assertEqual(r.status_code, 200, r.content)
        fichier = Fichier.objects.get(pk=fiche['id'])
        self.assertEqual(fichier.version, 2)
        self.assertNotEqual(fichier.storage_path, ancien_chemin)
        self.assertTrue((Path(self.dossier) / ancien_chemin).exists(), "L'ancienne version reste consultable.")
        self.assertEqual(fichier.taille, len(b'nouveau contenu'))
        self.assertEqual(fichier.versions.count(), 2)
        self.assertFalse((Path(self.dossier) / '_corbeille').exists())

    def test_suppression_logique(self):
        fiche = self.deposer_organisation().json()
        client = self.client_pour(self.user_a)
        r = client.delete(f"/api/fichiers/{fiche['id']}/")
        self.assertEqual(r.status_code, 200, r.content)
        fichier = Fichier.objects.get(pk=fiche['id'])
        self.assertIsNotNone(fichier.deleted_at, "Le fichier n'est jamais supprimé de la base.")
        self.assertTrue(fichier.storage_path.startswith('_corbeille/'))
        self.assertEqual(client.get(fiche['telechargement']).status_code, 404)
        self.assertEqual(client.delete(f"/api/fichiers/{fiche['id']}/").status_code, 404)
        actions = list(SyncChange.objects.filter(fichier=fichier).order_by('seq').values_list('action', flat=True))
        self.assertEqual(actions, ['insert', 'delete'])


class TriggersTests(BaseSync):
    def changements(self, **filtres):
        return SyncChange.objects.filter(**filtres)

    def test_referentiel_diffuse_a_tous(self):
        region = Region.objects.create(nom_region='Nouvelle région')
        lignes = self.changements(entity_type='region', entity_id=region.id)
        self.assertEqual([(c.action, c.organisation_id, c.portee) for c in lignes], [('insert', None, 'entite')])
        region.nom_region = 'Renommée'
        region.save()
        region.save()  # sans changement : aucune ligne supplémentaire
        self.assertEqual(lignes.all().count(), 2)  # .all() : le queryset itéré plus haut est en cache
        region.delete()
        self.assertEqual(list(lignes.order_by('seq').values_list('action', flat=True)), ['insert', 'update', 'delete'])

    def test_ouvrage_diffuse_a_son_gestionnaire_seulement(self):
        self.ouvrage_a.observation = 'modifié'
        self.ouvrage_a.save()
        lignes = self.changements(entity_type='ouvrage', entity_id=self.ouvrage_a.id, action='update')
        self.assertEqual({c.organisation_id for c in lignes}, {self.org_a.id})

    def test_equipement_et_point_eau_suivent_leur_ouvrage(self):
        self.equipement_a.nom = 'Pompe A2'
        self.equipement_a.save()
        self.point_a.nomabonne = 'Abonne A2'
        self.point_a.save()
        for type_entite, pk in (('equipement', self.equipement_a.id), ('point_eau', self.point_a.id)):
            orgs = {c.organisation_id for c in self.changements(entity_type=type_entite, entity_id=pk, action='update')}
            self.assertEqual(orgs, {self.org_a.id}, type_entite)

    def test_point_eau_sans_ouvrage_est_public(self):
        libre = PointEau.objects.create(nomabonne='Sans ouvrage')
        orgs = {c.organisation_id for c in self.changements(entity_type='point_eau', entity_id=libre.id)}
        self.assertEqual(orgs, {None})

    def test_changement_de_gestionnaire_previent_l_ancien_et_le_nouveau(self):
        modalite = ModaliteGestion.objects.get(ouvrage=self.ouvrage_a)
        modalite.gestionnaire = self.org_b
        modalite.save()
        lignes = list(self.changements(entity_type='ouvrage', entity_id=self.ouvrage_a.id).order_by('-seq')[:2])
        par_org = {c.organisation_id: c.action for c in lignes}
        self.assertEqual(par_org, {self.org_b.id: 'update', self.org_a.id: 'delete'})

    def test_activite_et_village_dans_le_journal(self):
        self.assertTrue(self.changements(entity_type='activite', entity_id=self.activite.id).exists())
        self.assertTrue(self.changements(entity_type='village', entity_id=self.village.id).exists())
        self.assertTrue(self.changements(entity_type='fokontany', entity_id=self.fokontany.id).exists())

    def test_contraintes_de_coherence_en_base(self):
        base = dict(organisation=self.org_a, nom='x.pdf', sha256='0' * 64, taille=1)

        def creer(**kw):
            with transaction.atomic():
                Fichier.objects.create(storage_path=f'tests/{uuid.uuid4()}', **base, **kw)

        # portée entité sans entité
        with self.assertRaises(IntegrityError):
            creer(portee='entite', categorie_id='photos_village')
        # portée organisation avec une entité
        with self.assertRaises(IntegrityError):
            creer(portee='organisation', domaine='operationnel', entity_type='village',
                  entity_id=self.village.id, categorie_id='procedure')
        # catégorie d'un autre domaine (trigger sync_verifier_fichier)
        with self.assertRaises(IntegrityError):
            creer(portee='organisation', domaine='logistique', categorie_id='procedure')
        # catégorie qui n'accepte pas ce type d'entité
        with self.assertRaises(IntegrityError):
            creer(portee='entite', entity_type='equipement', entity_id=self.equipement_a.id,
                  categorie_id='photos_village')
        self.assertEqual(Fichier.objects.count(), 0)


class ArborescenceEtJournalTests(BaseSync):
    def test_arborescence_complete(self):
        r = self.client_pour(self.user_a).get('/api/sync/arborescence')
        self.assertEqual(r.status_code, 200, r.content)
        corps = r.json()
        self.assertEqual(corps['organisation']['id'], str(self.org_a.id))
        domaines = {d['code']: d for d in corps['organisation_branche']['domaines']}
        self.assertEqual(set(domaines), {'operationnel', 'administratif', 'financier', 'logistique'})
        self.assertTrue(domaines['operationnel']['acces']['ecriture'])
        self.assertFalse(domaines['financier']['acces']['lecture'])
        self.assertIn('procedure', {c['code'] for c in domaines['operationnel']['categories']})

        village = (corps['territoire']['regions'][0]['districts'][0]['communes'][0]
                   ['fokontany'][0]['villages'][0])
        self.assertEqual(village['nom'], 'Village 1')
        noms_ouvrages = {o['nom'] for o in village['ouvrages']}
        self.assertEqual(noms_ouvrages, {'Ouvrage A'}, "L'ouvrage de B n'est pas visible par A.")
        ouvrage = village['ouvrages'][0]
        self.assertEqual([e['nom'] for e in ouvrage['equipements']], ['Pompe A'])
        self.assertEqual([p['nom'] for p in ouvrage['points_eau']], ['Abonne A'])
        self.assertEqual(corps['territoire']['activites'][0]['activites'][0]['nom'], 'Nettoyage')
        self.assertIn('photos_equipement', {c['code'] for c in corps['categories_entite']})

    def test_pagination_et_curseur(self):
        for i in range(5):
            Region.objects.create(nom_region=f'R{i}')
        client = self.client_pour(self.user_a)
        page1 = client.get('/api/sync/changes?limit=3').json()
        self.assertEqual((len(page1['changes']), page1['has_more']), (3, True))
        page2 = client.get(f"/api/sync/changes?limit=1000&since={page1['next_seq']}").json()
        self.assertFalse(page2['has_more'])
        sequences = [c['seq'] for c in page1['changes'] + page2['changes']]
        self.assertEqual(sequences, sorted(set(sequences)))
        vide = client.get(f"/api/sync/changes?since={page2['next_seq']}").json()
        self.assertEqual((vide['changes'], vide['next_seq']), ([], page2['next_seq']))
        self.assertEqual(client.get('/api/sync/changes?since=-1').status_code, 400)

    def test_chemin_hierarchique_dans_le_journal(self):
        fiche = self.deposer_equipement().json()
        flux = self.client_pour(self.user_a).get('/api/sync/changes?limit=1000').json()['changes']
        ligne = next(c for c in flux if c['fichier'] and c['fichier']['id'] == fiche['id'])
        self.assertEqual([n['type'] for n in ligne['chemin']],
                         ['region', 'district', 'commune', 'fokontany', 'village', 'ouvrage', 'equipement'])
        self.assertEqual(ligne['chemin'][-1]['nom'], 'Pompe A')

    def test_appareil_enregistre(self):
        client = self.client_pour(self.user_a)
        suivant = client.get('/api/sync/changes?appareil=PC-test&limit=1000').json()['next_seq']
        from apps.sync.models import SyncDevice
        appareil = SyncDevice.objects.get(user=self.user_a, device_nom='PC-test')
        self.assertEqual(appareil.last_seq, suivant)
        self.assertEqual(appareil.organisation_id, self.org_a.id)
