"""Tests du grand livre imprimable (financement + période choisis).

Page : /comptabilite/entries/grand-livre/impression/ (name accounting:entries_grand_livre_impression)

Verrouille : soldes de début/période/fin, sections Recettes/Dépenses/Neutres, regroupement
par Cat avec sous-totaux, exclusions 00BOOK/00PERS (00FND conservés), sélection du
financement, colonnes demandées et libellés affichés en entier (jamais tronqués).

Lancement : python manage.py test apps.accounting.tests_grand_livre_impression \
               --testrunner django.test.runner.DiscoverRunner
"""

import re
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte, Organisation

URL_IMPRESSION = reverse('accounting:entries_grand_livre_impression')


class GrandLivreImpressionTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(nom_organisation='Org Impression')
        cls.compte_fournisseur = Compte.objects.create(
            organisation=cls.organisation, compte='606100', nom_compte='Fournitures diverses',
            fournisseur_obligatoire=True)
        cls.compte_recette = Compte.objects.create(
            organisation=cls.organisation, compte='707401', nom_compte='Vente eau au volume')
        cls.compte_charge = Compte.objects.create(
            organisation=cls.organisation, compte='626100', nom_compte='Carburant vehicules')

        user_model = get_user_model()
        cls.user = user_model.objects.create_superuser(
            username='test_impression', email='impression@example.com', password='motdepasse')

    @classmethod
    def creer(cls, id_access, code_compte, *, date_rec, montant_in=0.0, montant_out=0.0,
              fin='Bailleur A', activ='AEP', description='', detail='', rec=None, date_m=None):
        comptes = {
            '606100': cls.compte_fournisseur,
            '707401': cls.compte_recette,
            '626100': cls.compte_charge,
        }
        return BaseDiameX.objects.create(
            id_access=id_access,
            fichier_source='TEST_IMPRESSION.MDB',
            compte_code=code_compte,
            compte=comptes.get(code_compte),
            journal_code='701',
            date_m=date_m or date_rec,
            date_rec=date_rec,
            rec=rec if rec is not None else id_access,
            description=description or f'ecriture {id_access}',
            detail=detail,
            montant_in=montant_in,
            montant_out=montant_out,
            fin=fin,
            activ=activ,
            prog='DIAMEX',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def get_document(self, **params):
        return self.client.get(URL_IMPRESSION, params)

    def test_soldes_debut_periode_fin(self):
        """Solde de début = cumul antérieur ; total période = entrées − sorties ; solde de fin."""
        self.creer(1, '707401', date_rec=date(2024, 12, 20), montant_in=1000)   # avant période
        self.creer(2, '626100', date_rec=date(2024, 12, 31), montant_out=200)   # avant période
        self.creer(3, '707401', date_rec=date(2025, 1, 10), montant_in=500)     # période
        self.creer(4, '626100', date_rec=date(2025, 2, 5), montant_out=300)     # période

        reponse = self.get_document(fin='Bailleur A', date_debut='2025-01-01', date_fin='2025-03-31')
        self.assertEqual(reponse.status_code, 200)
        document = reponse.context['document']
        self.assertEqual(document['solde_debut'], Decimal('800.0'))    # 1000 − 200
        self.assertEqual(document['total_periode'], Decimal('200.0'))  # 500 − 300
        self.assertEqual(document['solde_fin'], Decimal('1000.0'))
        self.assertEqual(document['nb_lignes'], 2)

    def test_sections_recettes_depenses_et_neutres(self):
        """Chaque ligne est classée par le signe de son CCY ; les mouvements nuls ont leur section."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=900, montant_out=0)
        self.creer(2, '626100', date_rec=date(2025, 1, 6), montant_out=400)
        self.creer(3, '606100', date_rec=date(2025, 1, 7), montant_in=150, montant_out=150)

        document = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                     date_fin='2025-01-31').context['document']
        sections = {section['cle']: section for section in document['sections']}
        self.assertEqual(sections['recettes']['nb'], 1)
        self.assertEqual(sections['recettes']['total'], Decimal('900.0'))
        self.assertEqual(sections['depenses']['nb'], 1)
        self.assertEqual(sections['depenses']['total'], Decimal('-400.0'))
        self.assertEqual(sections['neutres']['nb'], 1)
        self.assertEqual(sections['neutres']['total'], Decimal('0.0'))
        self.assertEqual(document['total_periode'], Decimal('500.0'))

    def test_regroupement_par_cat_avec_sous_totaux(self):
        """Deux lignes du même compte forment un seul groupe Cat, sous-total = somme des CCY."""
        self.creer(1, '626100', date_rec=date(2025, 1, 5), montant_out=100)
        self.creer(2, '626100', date_rec=date(2025, 1, 9), montant_out=250)
        self.creer(3, '606100', date_rec=date(2025, 1, 12), montant_out=50)

        document = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                     date_fin='2025-01-31').context['document']
        depenses = next(section for section in document['sections'] if section['cle'] == 'depenses')
        self.assertEqual([groupe['code'] for groupe in depenses['groupes']], ['606100', '626100'])
        groupe_carburant = next(g for g in depenses['groupes'] if g['code'] == '626100')
        self.assertEqual(groupe_carburant['nb'], 2)
        self.assertEqual(groupe_carburant['total'], Decimal('-350.0'))
        self.assertEqual(groupe_carburant['label'], '626100 - Carburant vehicules')
        self.assertEqual(depenses['total'],
                         sum((g['total'] for g in depenses['groupes']), Decimal('0')))

    def test_exclusions_00book_et_00pers_mais_00fnd_conserve(self):
        """00BOOK et 00PERS sortent du document, les 00FND restent."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=1000)
        self.creer(2, '00BOOK01', date_rec=date(2025, 1, 6), montant_in=5000, montant_out=5000)
        self.creer(3, '00PERS01', date_rec=date(2025, 1, 7), montant_out=700)
        self.creer(4, '00FND1XX', date_rec=date(2025, 1, 8), montant_out=250)

        document = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                     date_fin='2025-01-31').context['document']
        codes = {
            groupe['code']
            for section in document['sections'] for groupe in section['groupes']
        }
        self.assertEqual(codes, {'707401', '00FND1XX'})
        self.assertEqual(document['nb_lignes'], 2)

    def test_selection_du_financement_et_des_lignes_sans_financement(self):
        """Le financement choisi est le seul imprimé ; (Vide) regroupe les lignes sans financement."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=100, fin='Bailleur A')
        self.creer(2, '707401', date_rec=date(2025, 1, 6), montant_in=200, fin='Bailleur B')
        self.creer(3, '707401', date_rec=date(2025, 1, 7), montant_in=50, fin=None)
        self.creer(4, '707401', date_rec=date(2025, 1, 8), montant_in=25, fin='')

        document_a = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                       date_fin='2025-01-31').context['document']
        self.assertEqual(document_a['total_periode'], Decimal('100.0'))

        document_vide = self.get_document(fin='(Vide)', date_debut='2025-01-01',
                                          date_fin='2025-01-31').context['document']
        self.assertEqual(document_vide['total_periode'], Decimal('75.0'))

        document_tous = self.get_document(
            fin='TOUS', date_debut='2025-01-01', date_fin='2025-01-31').context['document']
        self.assertEqual(document_tous['total_periode'], Decimal('375.0'))

    def test_colonnes_demandees_et_libelles_non_tronques(self):
        """Les 7 colonnes sont là et un libellé long est affiché en entier (mise à la ligne CSS)."""
        libelle_long = (
            'ISI456_SOCIETE FORAGE ET TRAVAUX PUBLICS DE MADAGASCAR_'
            'Rehabilitation du reseau d adduction en eau potable du village '
            'd Ambohidratrimo phase 2 tranche ferme'
        )
        self.creer(1, '606100', date_rec=date(2025, 1, 5), montant_out=1234.56,
                   description=libelle_long, detail='DETAIL TRES LONG A CONSERVER ENTIEREMENT')

        reponse = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                    date_fin='2025-01-31')
        contenu = reponse.content.decode()
        for colonne in ('Date', 'Rec', 'Description', 'Detail', 'Fournisseur', 'Activ', 'CCY'):
            self.assertIn(f'>{colonne}<', contenu, f'colonne {colonne} absente')
        # Aucune troncature : le texte complet est dans la page (le retour à la ligne est en CSS).
        self.assertIn(libelle_long, contenu)
        self.assertIn('DETAIL TRES LONG A CONSERVER ENTIEREMENT', contenu)
        self.assertNotIn('text-overflow', contenu)
        self.assertNotIn('truncate', contenu)

    def test_fournisseur_rapproche_du_referentiel(self):
        """La colonne Fournisseur reprend le nom du référentiel quand le libellé le nomme."""
        from apps.billing.models import Fournisseur

        Fournisseur.objects.create(nom_fournisseur='SOCIETE FORAGE', nif_ou_isi='ISI', actif=True)
        self.creer(1, '606100', date_rec=date(2025, 1, 5), montant_out=100,
                   description='ISI456_SOCIETE FORAGE_TRAVAUX DE FORAGE')

        document = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                     date_fin='2025-01-31').context['document']
        ligne = document['sections'][1]['groupes'][0]['lignes'][0]
        self.assertEqual(ligne['fournisseur'], 'SOCIETE FORAGE')

    def test_lignes_sans_date_recue_signalees_et_exclues(self):
        """Une écriture sans date reçue est comptée et signalée (elle ne peut pas être située)."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=100)
        self.creer(2, '707401', date_rec=None, montant_in=999)

        document = self.get_document(fin='Bailleur A', date_debut='2025-01-01',
                                     date_fin='2025-01-31').context['document']
        self.assertEqual(document['nb_lignes'], 1)
        self.assertEqual(document['nb_sans_date'], 1)
        self.assertIn('sans date reçue', self.get_document(
            fin='Bailleur A', date_debut='2025-01-01', date_fin='2025-01-31').content.decode())

    def test_page_sans_parametre_affiche_le_formulaire(self):
        """Sans paramètre : formulaire seul (aucun document), avec les financements disponibles."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=100, fin='Bailleur A')
        self.creer(2, '707401', date_rec=date(2025, 1, 6), montant_in=100, fin='Fonds propre')

        reponse = self.get_document()
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.context['afficher'])
        self.assertIsNone(reponse.context['document'])
        contenu = reponse.content.decode()
        self.assertIn('Bailleur A', contenu)
        self.assertIn('Fonds propre', contenu)
        self.assertIn('(Sans financement)', contenu)
        self.assertIn('Afficher le grand livre', contenu)

    def test_periode_invalide(self):
        """Dates illisibles ou inversées : message d'erreur, pas de document."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=100)

        reponse = self.get_document(fin='Bailleur A', date_debut='hier', date_fin='2025-01-31')
        self.assertEqual(reponse.status_code, 200)
        self.assertIsNone(reponse.context['document'])
        self.assertTrue(reponse.context['erreurs'])

        reponse = self.get_document(fin='Bailleur A', date_debut='2025-03-01', date_fin='2025-01-31')
        self.assertTrue(reponse.context['erreurs'])

    def test_sans_elements_d_interface(self):
        """Le document ne charge ni navbar ni habillage de l'application."""
        self.creer(1, '707401', date_rec=date(2025, 1, 5), montant_in=100)
        contenu = self.get_document(
            fin='Bailleur A', date_debut='2025-01-01', date_fin='2025-01-31').content.decode()
        self.assertNotIn('planning_sidebar', contenu)
        self.assertNotIn('navbar', contenu)
        self.assertNotIn('class="drawer', contenu)
        self.assertIn('@media print', contenu)
        self.assertIn('size: A4 portrait', contenu)
        self.assertIn('window.print()', contenu)
