"""Tests de la vue « grand livre » (/comptabilite/entries/?view_mode=grand_livre).

Le grand livre s'affichait en chargeant puis enrichissant *toutes* les écritures du
périmètre (plusieurs requêtes par écriture) avant de les rendre : sur un journal de
production, la page dépassait le délai du serveur (Gateway time-out 504). Il est
désormais rendu à partir d'agrégats SQL, par niveaux :

    arbre (activ > financement > catégorie)  ->  gl_cat=…  ->  gl_detail=1 (écritures)

Ces tests verrouillent : les totaux, la navigation entre niveaux, le filtrage exact
d'un groupe, l'absence de chargement des écritures (nombre de requêtes constant), et
la non-régression de la vue liste.

Lancement : python manage.py test apps.accounting.tests_grand_livre \
               --testrunner django.test.runner.DiscoverRunner
"""

import re
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.accounting import views as V
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte, Organisation

ENTREE_URL = '/comptabilite/entries/'


class GrandLivreTestCase(TestCase):
    """Socle : une organisation, deux comptes typés, un journal d'écritures variées."""

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(nom_organisation='Org Grand Livre')
        cls.compte_ouvrage = Compte.objects.create(
            organisation=cls.organisation, compte='748201', nom_compte='Installation BP/BF',
            necessite_ouvrage=True)
        cls.compte_fournisseur = Compte.objects.create(
            organisation=cls.organisation, compte='606100', nom_compte='Fournitures',
            fournisseur_obligatoire=True)

        user_model = get_user_model()
        cls.user = user_model.objects.create_superuser(
            username='test_grand_livre', email='gl@example.com', password='motdepasse')

    @classmethod
    def creer_ecriture(cls, id_access, code_compte, montant_in=0.0, montant_out=0.0,
                       activ='AEP', fin='Budget', **extra):
        """Crée une écriture DiameX minimale (compte lié déduit du code)."""
        comptes = {'748201': cls.compte_ouvrage, '606100': cls.compte_fournisseur}
        donnees = {
            'id_access': id_access,
            'fichier_source': 'TEST_GL.MDB',
            'compte_code': code_compte,
            'compte': comptes.get(code_compte),
            'journal_code': '701',
            'date_m': date(2024, 6, 15),
            'date_rec': date(2024, 6, 16),
            'description': f'ecriture {id_access}',
            'montant_in': montant_in,
            'montant_out': montant_out,
            'activ': activ,
            'fin': fin,
            'prog': 'DIAMEX',
        }
        donnees.update(extra)
        return BaseDiameX.objects.create(**donnees)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def get_page(self, **params):
        return self.client.get(ENTREE_URL, params)

    @staticmethod
    def extraire_lien(contenu, marqueur):
        """Premier href contenant ``marqueur`` (liens du grand livre)."""
        trouve = re.search(r'href="([^"]*' + re.escape(marqueur) + r'[^"]*)"', contenu)
        return trouve.group(1).replace('&amp;', '&') if trouve else None

    @staticmethod
    def totaux_arbre(groupes):
        """{(activ, fin, catégorie) normalisés: (total_in, total_out, nb)} de l'arbre."""
        totaux = {}
        for activ in groupes:
            for fin in activ['financements']:
                for categorie in fin['categories']:
                    cle = tuple(V._normalize_text(valeur) for valeur in
                                (activ['label'], fin['label'], categorie['label']))
                    totaux[cle] = (categorie['total_in'], categorie['total_out'], categorie['nb'])
        return totaux


class ArbreGrandLivreTests(GrandLivreTestCase):

    def test_arbre_agrege_par_activ_financement_categorie(self):
        """L'arbre affiche les totaux par catégorie, sans aucune ligne d'écriture."""
        self.creer_ecriture(1, '748201', montant_in=1000, montant_out=0, activ='AEP', fin='Budget')
        self.creer_ecriture(2, '748201', montant_in=0, montant_out=250, activ='AEP', fin='Budget')
        self.creer_ecriture(3, '606100', montant_in=0, montant_out=400, activ='Forage', fin='Budget')

        response = self.get_page(view_mode='grand_livre')
        self.assertEqual(response.status_code, 200)
        contenu = response.content.decode()

        self.assertIn('Vue grand livre', contenu)
        self.assertIn('AEP', contenu)
        self.assertIn('Forage', contenu)
        # Les écritures elles-mêmes ne sont pas rendues dans l'arbre.
        self.assertNotIn('ecriture 1', contenu)
        self.assertNotIn('ecriture 3', contenu)

        groupes = response.context['grand_livre_groups']
        totaux = self.totaux_arbre(groupes)
        self.assertEqual(
            totaux[(V._normalize_text('AEP'), V._normalize_text('Budget'),
                    V._normalize_text('Paiements ou recettes avec ouvrage'))],
            (Decimal('1000.0'), Decimal('250.0'), 2))
        self.assertEqual(
            totaux[(V._normalize_text('Forage'), V._normalize_text('Budget'),
                    V._normalize_text('Paiements fournisseurs'))],
            (Decimal('0.0'), Decimal('400.0'), 1))
        self.assertEqual(response.context['total_count'], 3)

    def test_nombre_de_requetes_independant_du_volume(self):
        """Aucune requête par écriture : le coût ne dépend pas du nombre de lignes."""
        for index in range(1, 4):
            self.creer_ecriture(100 + index, '748201', montant_in=10)

        with CaptureQueriesContext(connection) as petit:
            self.get_page(view_mode='grand_livre')

        for index in range(4, 40):
            self.creer_ecriture(100 + index, '606100', montant_out=5)

        with CaptureQueriesContext(connection) as grand:
            self.get_page(view_mode='grand_livre')

        self.assertLessEqual(
            len(grand.captured_queries), len(petit.captured_queries) + 1,
            "le nombre de requêtes ne doit pas croître avec le nombre d'écritures")

    def test_filtres_utilisateur_appliques_aux_totaux(self):
        """Un filtre de la page (activ) restreint bien les totaux du grand livre."""
        self.creer_ecriture(1, '748201', montant_in=1000, activ='AEP')
        self.creer_ecriture(2, '748201', montant_in=500, activ='Forage')

        response = self.get_page(view_mode='grand_livre', activ='Forage')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_count'], 1)
        totaux = self.totaux_arbre(response.context['grand_livre_groups'])
        self.assertEqual([cle[0] for cle in totaux], [V._normalize_text('Forage')])

    def test_totaux_arbre_egaux_a_la_somme_des_ecritures(self):
        """Les totaux agrégés en SQL valent la somme des écritures (ancienne agrégation)."""
        ecritures = [
            self.creer_ecriture(1, '748201', montant_in=1200.5, activ='AEP', fin='Budget'),
            self.creer_ecriture(2, '606100', montant_out=300.25, activ='aep', fin=' budget '),
            self.creer_ecriture(3, '748201', montant_in=10, montant_out=90, activ=None, fin=None),
            self.creer_ecriture(4, '606100', montant_out=45.75, activ='Forage', fin='Bailleur'),
        ]

        groupes = V._build_grand_livre_groups(
            BaseDiameX.objects.select_related('compte', 'journal'), avec_comptes=False)

        attendu = {}
        for ecriture in ecritures:
            ecriture.compte_categorie_label = V._get_entry_compte_category_label(ecriture)
            cle = tuple(V._normalize_text(valeur) for valeur in (
                (ecriture.activ or 'Sans activ').strip(),
                (ecriture.fin or 'Sans financement').strip(),
                ecriture.compte_categorie_label,
            ))
            total = attendu.setdefault(cle, [Decimal('0'), Decimal('0'), 0])
            total[0] += Decimal(str(ecriture.montant_in or 0))
            total[1] += Decimal(str(ecriture.montant_out or 0))
            total[2] += 1

        totaux = self.totaux_arbre(groupes)
        self.assertEqual(set(totaux), set(attendu))
        for cle, (total_in, total_out, nb) in attendu.items():
            self.assertEqual(totaux[cle][2], nb, cle)
            self.assertEqual(Decimal(totaux[cle][0]).quantize(Decimal('0.01')),
                             total_in.quantize(Decimal('0.01')), cle)
            self.assertEqual(Decimal(totaux[cle][1]).quantize(Decimal('0.01')),
                             total_out.quantize(Decimal('0.01')), cle)

    def test_variantes_de_casse_regroupees(self):
        """« AEP », « aep » et «  AEP  » forment un seul groupe d'activité."""
        self.creer_ecriture(1, '748201', montant_in=100, activ='AEP')
        self.creer_ecriture(2, '748201', montant_in=200, activ='aep')
        self.creer_ecriture(3, '748201', montant_in=300, activ='  AEP  ')

        groupes = V._build_grand_livre_groups(
            BaseDiameX.objects.all(), avec_comptes=False)
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]['nb'], 3)
        self.assertEqual(groupes[0]['total_in'], Decimal('600.0'))


class NavigationGrandLivreTests(GrandLivreTestCase):

    def setUp(self):
        super().setUp()
        self.ecriture_ouvrage = self.creer_ecriture(
            1, '748201', montant_in=1000, activ='AEP', fin='Budget')
        self.ecriture_fournisseur = self.creer_ecriture(
            2, '606100', montant_out=400, activ='Forage', fin='Bailleur')

    def test_niveau_comptes_filtre_la_categorie(self):
        """Le lien « Voir les comptes » n'affiche que les comptes de la catégorie."""
        arbre = self.get_page(view_mode='grand_livre')
        lien = self.extraire_lien(arbre.content.decode(), 'gl_cat=')

        self.assertIsNotNone(lien, "l'arbre doit proposer un lien vers les comptes")
        reponse = self.client.get(ENTREE_URL + lien)
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.context['gl_comptes_mode'])
        contenu = reponse.content.decode()
        self.assertIn('748201', contenu)
        self.assertNotIn('606100', contenu)
        self.assertEqual(reponse.context['total_count'], 1)

    def test_niveau_ecritures_filtre_le_compte(self):
        """Le lien « Ouvrir les écritures » n'affiche que les écritures du compte."""
        arbre = self.get_page(view_mode='grand_livre')
        lien_comptes = self.extraire_lien(arbre.content.decode(), 'gl_cat=')
        page_comptes = self.client.get(ENTREE_URL + lien_comptes)
        lien_ecritures = self.extraire_lien(page_comptes.content.decode(), 'gl_detail=1')

        self.assertIsNotNone(lien_ecritures, "la page des comptes doit proposer le détail")
        reponse = self.client.get(ENTREE_URL + lien_ecritures)
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.context['gl_detail'])
        contenu = reponse.content.decode()
        self.assertIn('ecriture 1', contenu)
        self.assertNotIn('ecriture 2', contenu)
        self.assertEqual(reponse.context['total_count'], 1)
        # Le détail est bien la table paginée habituelle (page d'objets, pas une liste brute).
        self.assertEqual(list(reponse.context['page_obj']), [self.ecriture_ouvrage])

    def test_retour_arbre_depuis_les_ecritures(self):
        """Le fil d'Ariane remonte au niveau parent : comptes de la catégorie, puis arbre."""
        arbre = self.get_page(view_mode='grand_livre')
        page_comptes = self.client.get(
            ENTREE_URL + self.extraire_lien(arbre.content.decode(), 'gl_cat='))
        page_ecritures = self.client.get(
            ENTREE_URL + self.extraire_lien(page_comptes.content.decode(), 'gl_detail=1'))

        retour_comptes = page_ecritures.context['gl_back_url']
        self.assertNotIn('gl_detail', retour_comptes)
        reponse = self.client.get(ENTREE_URL + retour_comptes)
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.context['gl_comptes_mode'])
        self.assertEqual(reponse.context['total_count'], 1)

        retour_arbre = reponse.context['gl_back_url']
        self.assertNotIn('gl_cat', retour_arbre)
        arbre_final = self.client.get(ENTREE_URL + retour_arbre)
        self.assertEqual(arbre_final.status_code, 200)
        self.assertFalse(arbre_final.context['gl_comptes_mode'])
        self.assertEqual(arbre_final.context['total_count'], 2)

    def test_vue_liste_toujours_paginee(self):
        """La vue liste reste inchangée : lignes d'écritures et pagination."""
        reponse = self.get_page(view_mode='liste')
        self.assertEqual(reponse.status_code, 200)
        contenu = reponse.content.decode()
        self.assertIn('ecriture 1', contenu)
        self.assertIn('ecriture 2', contenu)


class StatistiquesGrandLivreTests(GrandLivreTestCase):

    def test_statistiques_agregees_egales_aux_calculs_detaillees(self):
        """L'en-tête agrégé donne les mêmes chiffres que les calculs requête par requête."""
        self.creer_ecriture(1, '748201', montant_in=1000)
        self.creer_ecriture(2, '606100', montant_out=400)
        self.creer_ecriture(3, '00BOOK01', montant_in=500)
        self.creer_ecriture(4, '00FND1XX', montant_out=300,
                            description='Transfert EDF eclairage public')
        self.creer_ecriture(5, '00PERS01', montant_in=100, montant_out=700)

        ecritures = BaseDiameX.objects.all()
        stats = V._grand_livre_stats(ecritures, None, [], [])

        recettes_entries = ecritures.exclude(
            V.Q(compte_code__startswith='00BOOK') | V.Q(compte_code__startswith='00PERS')
        ).exclude(
            V.Q(compte_code__startswith='00FND1') & ~(
                V.Q(description__icontains='EDF') | V.Q(info__icontains='EDF')))
        totaux = recettes_entries.aggregate(
            recettes_in=V.Sum('montant_in'), recettes_out=V.Sum('montant_out'))
        self.assertEqual(stats['recettes'], totaux['recettes_in'] or 0)
        self.assertEqual(stats['depenses'], totaux['recettes_out'] or 0)
        self.assertEqual(stats['solde'], stats['recettes'] - stats['depenses'])

        transferts = ecritures.filter(compte_code__startswith='00BOOK') | ecritures.filter(
            compte_code__startswith='00FND1').exclude(
            V.Q(description__icontains='EDF') | V.Q(info__icontains='EDF'))
        self.assertEqual(stats['transferts_count'], transferts.count())
        self.assertEqual(
            stats['transferts_solde'],
            (transferts.aggregate(total=V.Sum('montant_in'))['total'] or 0)
            - (transferts.aggregate(total=V.Sum('montant_out'))['total'] or 0))

        pers = ecritures.filter(compte_code__startswith='00PERS')
        self.assertEqual(stats['pers_count'], pers.count())
        self.assertEqual(
            Decimal(str(stats['pers_solde'])),
            (pers.aggregate(total=V.Sum('montant_out'))['total'] or 0)
            - (pers.aggregate(total=V.Sum('montant_in'))['total'] or 0))

    def test_comptages_scans_avec_cache_volumineux(self):
        """Les scans validés/liens morts utilisent le cache de vérification du périmètre."""
        ecriture = self.creer_ecriture(1, '748201', montant_in=1000)
        autre = self.creer_ecriture(2, '748201', montant_in=1000, scan='./scans/a.pdf')

        stats = V._grand_livre_stats(
            BaseDiameX.objects.all(), None, [autre.id], [ecriture.id])
        self.assertEqual(stats['scans_valides_count'], 1)
        self.assertEqual(stats['liens_morts_count'], 1)
        self.assertEqual(stats['operations_total'], 2)

    def test_liste_des_filtres_agregee(self):
        """Les listes de filtres (fichiers, journaux, comptes…) restent complètes."""
        self.creer_ecriture(1, '748201', montant_in=10, fichier_source='A.MDB', journal_code='701')
        self.creer_ecriture(2, '606100', montant_out=10, fichier_source='B.MDB', journal_code='702')

        valeurs = V._grand_livre_filter_values(BaseDiameX.objects.all(), self.user)
        self.assertEqual(valeurs['fichiers_sources'], ['A.MDB', 'B.MDB'])
        self.assertEqual(valeurs['journaux_codes'], ['701', '702'])
        self.assertEqual([option['code'] for option in valeurs['comptes_options']],
                         ['606100', '748201'])
        self.assertIn('Fournitures', valeurs['comptes_options'][0]['nom'])
