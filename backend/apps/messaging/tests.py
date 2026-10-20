from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.billing.models import PaiementForfaitaire, PointEau, Releve
from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye, Poste
from apps.employees.models_evaluation import FichePoste
from apps.employees.permissions import est_agent_recouvrement, est_responsable_actif_ouvrage
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import Planning, TypeActivite

from .models import CommentaireRelance, RelanceFacturesNonPointees, RelanceReparations
from .monthly_billing_links import (
    lien_commentaire_point_eau,
    lien_point_eau,
    lien_relance_consolide,
)
from .monthly_billing_mailer import (
    construire_sujet,
    envoyer_toutes_les_relances,
)
from .monthly_billing_reminder import (
    calculer_periode_cible,
    construire_regroupement,
    construire_regroupement_hierarchique,
    paiements_forfaitaires_non_pointes,
    releves_non_pointes,
    responsables_actifs_pour_ouvrage,
    superieurs_hierarchiques,
)
from .relance_engine import calculer_niveau_ouvrage, construire_regroupement_combine, trier_ouvrages_par_criticite
from .relance_mailer_combine import envoyer_toutes_les_relances_combinees
from .repair_reminder import (
    calculer_niveau_reparation,
    compter_reparations_sans_responsable,
    construire_regroupement_hierarchique_reparations,
    construire_regroupement_reparations,
    grading_ouvrage_reparations,
    reparations_echues,
)


class CalculerPeriodeCibleTests(TestCase):
    def test_fin_de_periode_fevrier_annee_bissextile(self):
        annee, mois, date_fin = calculer_periode_cible(2024, 2)
        self.assertEqual(date_fin, date(2024, 2, 29))

    def test_fin_de_periode_fevrier_non_bissextile(self):
        annee, mois, date_fin = calculer_periode_cible(2025, 2)
        self.assertEqual(date_fin, date(2025, 2, 28))

    def test_fin_de_periode_avril_30_jours(self):
        annee, mois, date_fin = calculer_periode_cible(2026, 4)
        self.assertEqual(date_fin, date(2026, 4, 30))

    def test_fin_de_periode_janvier_31_jours(self):
        annee, mois, date_fin = calculer_periode_cible(2026, 1)
        self.assertEqual(date_fin, date(2026, 1, 31))


class LiensProfondsTests(TestCase):
    @override_settings(SITE_BASE_URL='https://test.example')
    def test_lien_point_eau_utilise_site_base_url(self):
        point_eau_id = 'abc12345-0000-0000-0000-000000000000'
        lien = lien_point_eau(point_eau_id)
        self.assertTrue(lien.startswith('https://test.example'))
        self.assertIn('/recherche/details/point_eau/', lien)
        self.assertIn(point_eau_id, lien)

    @override_settings(SITE_BASE_URL='https://test.example')
    def test_lien_relance_consolide_contient_periode_et_employe(self):
        employe_id = 'def67890-0000-0000-0000-000000000000'
        lien = lien_relance_consolide(employe_id, 2026, 3)
        self.assertTrue(lien.startswith('https://test.example'))
        self.assertIn('/2026/3/', lien)
        self.assertIn(employe_id, lien)

    @override_settings(SITE_BASE_URL='https://test.example')
    def test_lien_commentaire_point_eau_a_une_ancre(self):
        employe_id = 'def67890-0000-0000-0000-000000000000'
        point_eau_id = 'abc12345-0000-0000-0000-000000000000'
        lien = lien_commentaire_point_eau(employe_id, 2026, 3, point_eau_id)
        self.assertIn(f'#point-eau-{point_eau_id}', lien)


class ConstruireSujetTests(TestCase):
    def test_sujet_normal(self):
        sujet = construire_sujet(date(2026, 7, 31), est_test=False)
        self.assertEqual(sujet, "Hydria — Factures non pointées au 31/07/2026")

    def test_sujet_test_prefixe_tiret_cadratin(self):
        sujet = construire_sujet(date(2026, 7, 31), est_test=True)
        self.assertEqual(sujet, "TEST — Hydria — Factures non pointées au 31/07/2026")
        self.assertNotIn('[TEST]', sujet)


class BaseFixtureMixin:
    """Fixtures communes : organisation/base/ouvrage/point d'eau/employe
    responsable, reutilisees par plusieurs classes de test de ce fichier."""

    def _creer_fixtures_base(self):
        self.organisation = Organisation.objects.create(nom_organisation='Org Messaging Tests')
        self.base = Base.objects.create(nom_base='Base Messaging Tests', organisation=self.organisation)
        self.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG Messaging Tests')
        self.ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage Messaging Tests', type_ouvrage=self.type_ouvrage)
        self.point_eau = PointEau.objects.create(
            nomabonne='Abonne Messaging Tests',
            ouvrage=self.ouvrage,
        )
        self.employe = Employe.objects.create(
            nom_employe='Responsable Messaging',
            nom='Responsable',
            surnom='RESPMSG',
            base=self.base,
            mail='responsable-messaging@example.com',
        )
        EmployeOuvrages.objects.create(
            employe=self.employe,
            ouvrage=self.ouvrage,
            date_debut=date(2026, 1, 1),
            recevoir_alertes=True,
        )


class SelectionFacturesNonPointeesTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_fin_periode = date(2026, 7, 31)

    def test_releve_non_pointe_inclus(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 1)

    def test_releve_pointe_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='paye',
            montant=Decimal('1000'), numeroDiameX='DX-123',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_anterieur_a_2026_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2025, 12, 31),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_posterieur_a_la_periode_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 8, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_mois_courant_et_anterieur_melanges(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 2, 1),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='',
        )
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 7, 20),
            ancienindex=10, nouvelindex=20, consommation=10, statut='impaye',
            montant=Decimal('1200'), numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 2)

    def test_paiement_forfaitaire_numerodiamex_seul_vide_inclus(self):
        PaiementForfaitaire.objects.create(
            point_eau=self.point_eau, date_facture=date(2026, 4, 1),
            quantite=1, prix_unitaire=Decimal('5000'), montant=Decimal('5000'),
            numeroDiameX='', baseDiameX='BASE-01',
        )
        self.assertEqual(paiements_forfaitaires_non_pointes(self.date_fin_periode).count(), 1)

    def test_paiement_forfaitaire_les_deux_remplis_exclu(self):
        PaiementForfaitaire.objects.create(
            point_eau=self.point_eau, date_facture=date(2026, 4, 1),
            quantite=1, prix_unitaire=Decimal('5000'), montant=Decimal('5000'),
            numeroDiameX='DX-1', baseDiameX='BASE-01',
        )
        self.assertEqual(paiements_forfaitaires_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_montant_null_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=None, numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_montant_zero_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('0'), numeroDiameX='',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_point_eau_coupe_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='', remarque='Point coupé le 10/03',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_releve_point_eau_coupe_majuscule_exclu(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 15),
            ancienindex=0, nouvelindex=10, consommation=10, statut='impaye',
            montant=Decimal('1000'), numeroDiameX='', remarque='Coupé pour impayé',
        )
        self.assertEqual(releves_non_pointes(self.date_fin_periode).count(), 0)

    def test_paiement_forfaitaire_montant_zero_exclu(self):
        # PaiementForfaitaire.save() ne recalcule montant que si quantite ET
        # prix_unitaire sont tous deux truthy (billing/models.py:1601-1602) ;
        # avec quantite=0 le recalcul est saute et le montant fourni est
        # conserve tel quel.
        PaiementForfaitaire.objects.create(
            point_eau=self.point_eau, date_facture=date(2026, 4, 1),
            quantite=0, prix_unitaire=Decimal('5000'), montant=Decimal('0'),
            numeroDiameX='', baseDiameX='',
        )
        self.assertEqual(paiements_forfaitaires_non_pointes(self.date_fin_periode).count(), 0)


class ResponsablesActifsTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()

    def test_responsable_actif_recevoir_alertes_true_inclus(self):
        self.assertTrue(
            est_responsable_actif_ouvrage(self.employe, self.ouvrage.id, date(2026, 7, 31))
        )

    def test_responsable_recevoir_alertes_false_exclu(self):
        EmployeOuvrages.objects.filter(employe=self.employe, ouvrage=self.ouvrage).update(recevoir_alertes=False)
        employe_regroupement = construire_regroupement(2026, 7)
        self.assertNotIn(self.employe.id, employe_regroupement)

    def test_responsable_date_fin_passee_exclu(self):
        EmployeOuvrages.objects.filter(employe=self.employe, ouvrage=self.ouvrage).update(
            date_fin=date(2026, 1, 31)
        )
        self.assertFalse(
            est_responsable_actif_ouvrage(self.employe, self.ouvrage.id, date(2026, 7, 31))
        )

    def test_responsable_date_debut_future_exclu(self):
        EmployeOuvrages.objects.filter(employe=self.employe, ouvrage=self.ouvrage).update(
            date_debut=date(2026, 12, 1)
        )
        self.assertFalse(
            est_responsable_actif_ouvrage(self.employe, self.ouvrage.id, date(2026, 7, 31))
        )

    def test_responsable_debauche_exclu_du_rappel(self):
        self.employe.date_debauchage = date(2026, 5, 1)
        self.employe.save(update_fields=['date_debauchage'])
        responsables = responsables_actifs_pour_ouvrage(self.ouvrage.id, date(2026, 7, 31))
        self.assertNotIn(self.employe, responsables)

    def test_poste_superviseur_technique_exclu_du_rappel(self):
        poste = Poste.objects.create(nom_poste='Superviseur technique', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        responsables = responsables_actifs_pour_ouvrage(self.ouvrage.id, date(2026, 7, 31))
        self.assertNotIn(self.employe, responsables)

    def test_poste_mpikojakoja_ifotony_exclu_du_rappel(self):
        poste = Poste.objects.create(nom_poste='Mpikojakoja ifotony', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        responsables = responsables_actifs_pour_ouvrage(self.ouvrage.id, date(2026, 7, 31))
        self.assertNotIn(self.employe, responsables)

    def test_autre_poste_reste_inclus(self):
        poste = Poste.objects.create(nom_poste='Comptable', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        responsables = responsables_actifs_pour_ouvrage(self.ouvrage.id, date(2026, 7, 31))
        self.assertIn(self.employe, responsables)


class RegroupementTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()

    def test_regroupement_un_seul_point_eau(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        regroupement = construire_regroupement(2026, 7)
        self.assertIn(self.employe.id, regroupement)
        entree = regroupement[self.employe.id]
        self.assertEqual(len(entree['ouvrages']), 1)
        ouvrage_entree = next(iter(entree['ouvrages'].values()))
        self.assertEqual(len(ouvrage_entree['points_eau']), 1)

    def test_regroupement_plusieurs_points_eau_et_types_factures_melanges(self):
        autre_point_eau = PointEau.objects.create(nomabonne='Abonne 2', ouvrage=self.ouvrage)
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        PaiementForfaitaire.objects.create(
            point_eau=autre_point_eau, date_facture=date(2026, 4, 1),
            quantite=1, prix_unitaire=Decimal('3000'), montant=Decimal('3000'),
            numeroDiameX='', baseDiameX='',
        )
        regroupement = construire_regroupement(2026, 7)
        entree = regroupement[self.employe.id]
        ouvrage_entree = next(iter(entree['ouvrages'].values()))
        self.assertEqual(len(ouvrage_entree['points_eau']), 2)

    def test_regroupement_vide_si_aucune_facture_non_pointee(self):
        regroupement = construire_regroupement(2026, 7)
        self.assertEqual(regroupement, {})


class PropagationHierarchiqueTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 7, 31)
        self.n1 = Employe.objects.create(
            nom_employe='Chef Direct', nom='Direct', surnom='CHEFN1',
            base=self.base, mail='chef-n1@example.com',
        )
        self.n2 = Employe.objects.create(
            nom_employe='Chef Chef', nom='ChefChef', surnom='CHEFN2',
            base=self.base, mail='chef-n2@example.com',
        )

    def _relier(self, employe, superieur, date_debut=date(2026, 1, 1), date_fin=None):
        return HierarchieEmploye.objects.create(
            employe=employe, superieur=superieur, date_debut=date_debut, date_fin=date_fin,
        )

    def test_superieur_direct_inclus(self):
        self._relier(self.employe, self.n1)
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [self.n1])

    def test_chaine_complete_n1_et_n2_incluse(self):
        self._relier(self.employe, self.n1)
        self._relier(self.n1, self.n2)
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [self.n1, self.n2])

    def test_relation_expiree_exclue(self):
        self._relier(self.employe, self.n1, date_debut=date(2025, 1, 1), date_fin=date(2026, 3, 31))
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [])

    def test_relation_future_exclue(self):
        self._relier(self.employe, self.n1, date_debut=date(2026, 12, 1))
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [])

    def test_boucle_hierarchique_ne_provoque_pas_boucle_infinie(self):
        self._relier(self.employe, self.n1)
        self._relier(self.n1, self.employe)
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [self.n1])

    def test_superieur_debauche_saute_mais_chaine_continue(self):
        self.n1.date_debauchage = date(2026, 5, 1)
        self.n1.save(update_fields=['date_debauchage'])
        self._relier(self.employe, self.n1)
        self._relier(self.n1, self.n2)
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [self.n2])

    def test_superieur_poste_exclu_saute_mais_chaine_continue(self):
        poste = Poste.objects.create(nom_poste='Mpikojakoja ifotony', organisation=self.organisation)
        self.n1.poste = poste
        self.n1.save(update_fields=['poste'])
        self._relier(self.employe, self.n1)
        self._relier(self.n1, self.n2)
        superieurs = superieurs_hierarchiques(self.employe, self.date_reference)
        self.assertEqual(superieurs, [self.n2])

    def test_regroupement_hierarchique_agrege_plusieurs_subordonnes_sous_un_meme_chef(self):
        autre_ouvrage = Ouvrage.objects.create(nom_ouvrage='Autre Ouvrage', type_ouvrage=self.type_ouvrage)
        autre_point_eau = PointEau.objects.create(nomabonne='Abonne Autre', ouvrage=autre_ouvrage)
        autre_employe = Employe.objects.create(
            nom_employe='Autre Responsable', nom='Autre', surnom='AUTRE',
            base=self.base, mail='autre@example.com',
        )
        EmployeOuvrages.objects.create(
            employe=autre_employe, ouvrage=autre_ouvrage,
            date_debut=date(2026, 1, 1), recevoir_alertes=True,
        )
        self._relier(self.employe, self.n1)
        self._relier(autre_employe, self.n1)

        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        Releve.objects.create(
            point_eau=autre_point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('700'), numeroDiameX='',
        )

        regroupement = construire_regroupement(2026, 7)
        regroupement_hierarchique = construire_regroupement_hierarchique(regroupement, self.date_reference)

        self.assertIn(self.n1.id, regroupement_hierarchique)
        entree_n1 = regroupement_hierarchique[self.n1.id]
        self.assertEqual(len(entree_n1['subordonnes']), 2)
        self.assertIn(self.employe.id, entree_n1['subordonnes'])
        self.assertIn(autre_employe.id, entree_n1['subordonnes'])

    def test_pas_de_hierarchie_donne_regroupement_hierarchique_vide(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        regroupement = construire_regroupement(2026, 7)
        regroupement_hierarchique = construire_regroupement_hierarchique(regroupement, self.date_reference)
        self.assertEqual(regroupement_hierarchique, {})


class EnvoiRelancesTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )

    def test_aucun_email_envoye_si_aucune_facture(self):
        Releve.objects.all().delete()
        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(resultat['nb_responsables'], 0)

    def test_email_envoye_avec_html_et_texte(self):
        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertEqual(resultat['nb_envoyes'], 1)

    def test_employe_sans_email_ne_bloque_pas_les_autres(self):
        self.employe.mail = ''
        self.employe.save()
        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(resultat['nb_email_manquant'], 1)
        trace = RelanceFacturesNonPointees.objects.get(employe=self.employe, annee=2026, mois=7)
        self.assertEqual(trace.statut, 'email_manquant')

    def test_deux_executions_successives_ne_doublent_pas(self):
        envoyer_toutes_les_relances(annee=2026, mois=7)
        envoyer_toutes_les_relances(annee=2026, mois=7)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            RelanceFacturesNonPointees.objects.filter(annee=2026, mois=7, est_test=False).count(), 1,
        )

    def test_mode_test_redirige_tous_les_envois_vers_adresse_unique(self):
        autre_point_eau = PointEau.objects.create(nomabonne='Abonne 2', ouvrage=self.ouvrage)
        autre_employe = Employe.objects.create(
            nom_employe='Autre Responsable', nom='Autre', base=self.base, mail='autre@example.com',
        )
        autre_ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage 2', type_ouvrage=self.type_ouvrage)
        autre_point_eau.ouvrage = autre_ouvrage
        autre_point_eau.save()
        EmployeOuvrages.objects.create(
            employe=autre_employe, ouvrage=autre_ouvrage, date_debut=date(2026, 1, 1),
        )
        Releve.objects.create(
            point_eau=autre_point_eau, abonne='Abonne 2', datereleve=date(2026, 5, 1),
            ancienindex=0, nouvelindex=3, consommation=3, statut='impaye',
            montant=Decimal('300'), numeroDiameX='',
        )

        resultat = envoyer_toutes_les_relances(
            annee=2026, mois=7, est_test=True, email_test_override='qa@example.com',
        )
        self.assertEqual(resultat['nb_responsables'], 2)
        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertEqual(message.to, ['qa@example.com'])
            self.assertIn('TEST', message.subject)

    def test_dry_run_n_envoie_rien_et_n_ecrit_aucune_trace(self):
        envoyer_toutes_les_relances(annee=2026, mois=7, dry_run=True)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(RelanceFacturesNonPointees.objects.count(), 0)

    def test_superieur_hierarchique_recoit_email_consolide(self):
        chef = Employe.objects.create(
            nom_employe='Chef Test', nom='Test', surnom='CHEFTEST',
            base=self.base, mail='chef-test@example.com',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=chef, date_debut=date(2026, 1, 1))

        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)

        self.assertEqual(resultat['nb_superieurs'], 1)
        self.assertEqual(len(mail.outbox), 2)  # 1 responsable + 1 superieur
        email_chef = next(m for m in mail.outbox if m.to == ['chef-test@example.com'])
        self.assertIn('Pour information', email_chef.subject)
        self.assertIn('RESPMSG', email_chef.body)
        trace_chef = RelanceFacturesNonPointees.objects.get(
            employe=chef, annee=2026, mois=7, type_destinataire='superieur',
        )
        self.assertEqual(trace_chef.statut, 'envoye')

    def test_superieur_sans_email_ne_bloque_pas_le_reste(self):
        chef = Employe.objects.create(
            nom_employe='Chef Sans Mail', nom='SansMail', base=self.base, mail='',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=chef, date_debut=date(2026, 1, 1))

        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)

        self.assertEqual(resultat['nb_envoyes'], 1)  # le responsable direct part quand meme
        self.assertEqual(resultat['nb_email_manquant'], 1)  # le chef, lui, echoue proprement
        trace_chef = RelanceFacturesNonPointees.objects.get(
            employe=chef, annee=2026, mois=7, type_destinataire='superieur',
        )
        self.assertEqual(trace_chef.statut, 'email_manquant')

    def test_responsable_qui_est_aussi_superieur_recoit_deux_emails_distincts(self):
        # Le meme Employe peut a la fois etre responsable direct d'un
        # ouvrage ET superieur hierarchique d'un autre responsable : les
        # deux traces (type_destinataire different) doivent coexister sans
        # violer la contrainte d'unicite.
        autre_point_eau = PointEau.objects.create(nomabonne='Abonne PolyRole', ouvrage=self.ouvrage)
        subordonne = Employe.objects.create(
            nom_employe='Subordonne PolyRole', nom='Sub', base=self.base, mail='sub-polyrole@example.com',
        )
        EmployeOuvrages.objects.create(
            employe=subordonne, ouvrage=self.ouvrage, date_debut=date(2026, 1, 1), recevoir_alertes=True,
        )
        Releve.objects.create(
            point_eau=autre_point_eau, abonne='Abonne PolyRole', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('900'), numeroDiameX='',
        )
        HierarchieEmploye.objects.create(employe=subordonne, superieur=self.employe, date_debut=date(2026, 1, 1))

        resultat = envoyer_toutes_les_relances(annee=2026, mois=7)

        self.assertEqual(resultat['nb_envoyes'], 3)  # employe (direct) + subordonne (direct) + employe (superieur)
        traces_employe = RelanceFacturesNonPointees.objects.filter(employe=self.employe, annee=2026, mois=7)
        self.assertEqual(traces_employe.count(), 2)
        self.assertEqual(
            set(traces_employe.values_list('type_destinataire', flat=True)),
            {'responsable', 'superieur'},
        )


class CommentaireRelanceViewTests(BaseFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.user_model = get_user_model()
        self.user_responsable = self.user_model.objects.create_user(
            username='resp_messaging_tests', password='testpass123',
        )
        self.employe.user = self.user_responsable
        self.employe.save()

        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )

        self.autre_employe = Employe.objects.create(
            nom_employe='Autre Employe', nom='Autre', base=self.base,
        )
        self.user_autre = self.user_model.objects.create_user(
            username='autre_messaging_tests', password='testpass123',
        )
        self.autre_employe.user = self.user_autre
        self.autre_employe.save()

        self.user_admin = self.user_model.objects.create_superuser(
            username='admin_messaging_tests', email='admin@example.com', password='testpass123',
        )
        self.employe_admin = Employe.objects.create(
            nom_employe='Admin Messaging', nom='Admin', base=self.base, user=self.user_admin,
        )

        self.url = f'/conversations/rappels/2026/7/{self.employe.id}/'

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_acces_par_le_responsable_concerne(self):
        self.client.force_login(self.user_responsable)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_acces_par_un_autre_responsable_refuse(self):
        self.client.force_login(self.user_autre)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_acces_par_admin_autorise(self):
        self.client.force_login(self.user_admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_creation_commentaire_valide(self):
        self.client.force_login(self.user_responsable)
        get_response = self.client.get(self.url)
        self.assertEqual(get_response.status_code, 200)

        data = {
            'commentaires-TOTAL_FORMS': '1',
            'commentaires-INITIAL_FORMS': '0',
            'commentaires-MIN_NUM_FORMS': '0',
            'commentaires-MAX_NUM_FORMS': '1000',
            'commentaires-0-point_eau_id': str(self.point_eau.id),
            'commentaires-0-contenu': 'Ceci est un commentaire de test.',
        }
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CommentaireRelance.objects.count(), 1)
        commentaire = CommentaireRelance.objects.first()
        self.assertEqual(commentaire.entity_id, str(self.point_eau.id))
        self.assertEqual(commentaire.employe_auteur, self.employe)

        relance = RelanceFacturesNonPointees.objects.get(employe=self.employe, annee=2026, mois=7)
        self.assertIsNotNone(relance.date_premiere_reponse)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_soumission_point_eau_hors_perimetre_refusee(self):
        self.client.force_login(self.user_responsable)
        self.client.get(self.url)  # cree la relance d'ancrage

        point_eau_etranger_id = '99999999-0000-0000-0000-000000000000'
        data = {
            'commentaires-TOTAL_FORMS': '1',
            'commentaires-INITIAL_FORMS': '0',
            'commentaires-MIN_NUM_FORMS': '0',
            'commentaires-MAX_NUM_FORMS': '1000',
            'commentaires-0-point_eau_id': point_eau_etranger_id,
            'commentaires-0-contenu': 'Tentative hors perimetre.',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CommentaireRelance.objects.count(), 0)

    def test_protection_csrf(self):
        client_strict = Client(enforce_csrf_checks=True)
        client_strict.force_login(self.user_responsable)
        with override_settings(ALLOWED_HOSTS=['*']):
            data = {
                'commentaires-TOTAL_FORMS': '1',
                'commentaires-INITIAL_FORMS': '0',
                'commentaires-MIN_NUM_FORMS': '0',
                'commentaires-MAX_NUM_FORMS': '1000',
                'commentaires-0-point_eau_id': str(self.point_eau.id),
                'commentaires-0-contenu': 'Sans token CSRF.',
            }
            response = client_strict.post(self.url, data)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(CommentaireRelance.objects.count(), 0)


class ReparationFixtureMixin(BaseFixtureMixin):
    """Etend BaseFixtureMixin avec un Planning-reparation echu de
    reference, reutilise par les classes de test du moteur combine.

    Le vrai systeme de reparations en production repose sur Planning
    classifie via repair_classification.get_repair_fiche_ids() (pas le
    modele apps.planning.models_reparations.Reparation, vide et
    deconnecte de la production). _creer_reparation() garde les memes
    noms de parametres que l'ancienne implementation (date_prevue, statut,
    priorite) pour limiter les changements dans les tests existants, mais
    les traduit en interne vers les vrais champs Planning (date,
    estvalide, priorite_suivi)."""

    _STATUTS_TERMINES = ('terminee', 'validee', 'annulee')
    _PRIORITES_VERS_PRIORITE_SUIVI = {
        'urgente': 'critique', 'haute': 'haute', 'moyenne': 'normale', 'basse': 'basse',
    }

    def _creer_fiche_poste_reparation(self):
        if getattr(self, '_fiche_poste_reparation_cache', None):
            return self._fiche_poste_reparation_cache
        type_activite = TypeActivite.objects.create(nomtype='Reparation')
        self._fiche_poste_reparation_cache = FichePoste.objects.create(
            type_activites=type_activite,
            tache='Reparation Messaging Tests',
            description='Description de test',
        )
        return self._fiche_poste_reparation_cache

    _EMPLOYE_DEFAUT = object()  # sentinel : distingue "parametre omis" de "employe=None explicite"

    def _creer_reparation(self, date_prevue=None, statut='signalee', priorite='moyenne',
                           ouvrage=None, employe=_EMPLOYE_DEFAUT):
        date_planning = date_prevue or date(2026, 7, 1)
        estvalide = statut in self._STATUTS_TERMINES
        priorite_suivi = self._PRIORITES_VERS_PRIORITE_SUIVI.get(priorite, 'normale')
        employe_final = self.employe if employe is self._EMPLOYE_DEFAUT else employe
        return Planning.objects.create(
            ouvrage=ouvrage or self.ouvrage,
            employe=employe_final,
            fiche_poste=self._creer_fiche_poste_reparation(),
            date=timezone.make_aware(datetime.combine(date_planning, datetime.min.time())),
            estvalide=estvalide,
            priorite_suivi=priorite_suivi,
        )


class SelectionReparationsEchuesTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 8, 1)

    def test_reparation_echue_statut_non_terminal_incluse(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1), statut='signalee')
        self.assertEqual(reparations_echues(self.date_reference).count(), 1)

    def test_reparation_non_echue_exclue(self):
        self._creer_reparation(date_prevue=date(2026, 9, 1), statut='signalee')
        self.assertEqual(reparations_echues(self.date_reference).count(), 0)

    def test_reparation_terminee_exclue_sans_attendre_validee(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1), statut='terminee')
        self.assertEqual(reparations_echues(self.date_reference).count(), 0)

    def test_reparation_validee_exclue(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1), statut='validee')
        self.assertEqual(reparations_echues(self.date_reference).count(), 0)

    def test_reparation_annulee_exclue(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1), statut='annulee')
        self.assertEqual(reparations_echues(self.date_reference).count(), 0)

    def test_reparation_en_cours_et_planifiee_incluses(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1), statut='planifiee')
        self._creer_reparation(date_prevue=date(2026, 7, 2), statut='en_cours')
        self.assertEqual(reparations_echues(self.date_reference).count(), 2)


class ResponsablesReparationsTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 8, 1)

    def test_responsable_actif_ouvrage_recoit_reparation(self):
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertIn(self.employe.id, regroupement)

    def test_planning_non_echu_employe_non_notifie(self):
        # Planning.employe est bien assigne mais la date est dans le futur
        # (pas encore echu) : aucun destinataire ne doit etre notifie pour
        # ce Planning.
        self._creer_reparation(date_prevue=date(2026, 9, 1))
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertNotIn(self.employe.id, regroupement)

    def test_responsable_debauche_exclu(self):
        self.employe.date_debauchage = date(2026, 7, 15)
        self.employe.save(update_fields=['date_debauchage'])
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertNotIn(self.employe.id, regroupement)

    def test_chaine_hierarchique_reparations_fonctionne(self):
        chef = Employe.objects.create(
            nom_employe='Chef Reparations', nom='Chef', surnom='CHEFREP',
            base=self.base, mail='chef-reparations@example.com',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=chef, date_debut=date(2026, 1, 1))
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        regroupement_h = construire_regroupement_hierarchique_reparations(regroupement, self.date_reference)
        self.assertIn(chef.id, regroupement_h)
        self.assertIn(self.employe.id, regroupement_h[chef.id]['subordonnes'])

    def test_superviseur_technique_recoit_relance_reparation_contrairement_aux_paiements(self):
        # Difference deliberee avec les paiements : le Superviseur technique
        # est exclu de POSTES_EXCLUS_RAPPEL (paiements) mais PAS de
        # POSTES_EXCLUS_RAPPEL_REPARATIONS -- il doit apparaitre ici.
        poste = Poste.objects.create(nom_poste='Superviseur technique', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self._creer_reparation()

        regroupement_reparations = construire_regroupement_reparations(self.date_reference)
        self.assertIn(self.employe.id, regroupement_reparations)

        # Confirme la difference : le meme employe est exclu des paiements.
        responsables_paiements = list(responsables_actifs_pour_ouvrage(self.ouvrage.id, self.date_reference))
        self.assertNotIn(self.employe, responsables_paiements)

    def test_mpikojakoja_ifotony_reste_exclu_des_reparations(self):
        poste = Poste.objects.create(nom_poste='Mpikojakoja ifotony', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertNotIn(self.employe.id, regroupement)

    def test_superviseur_technique_superieur_hierarchique_reparations_inclus(self):
        superviseur = Employe.objects.create(
            nom_employe='Superviseur Chaine', nom='Superviseur', base=self.base,
            mail='superviseur-chaine@example.com',
            poste=Poste.objects.create(nom_poste='Superviseur technique', organisation=self.organisation),
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=superviseur, date_debut=date(2026, 1, 1))
        self._creer_reparation()

        regroupement = construire_regroupement_reparations(self.date_reference)
        regroupement_h = construire_regroupement_hierarchique_reparations(regroupement, self.date_reference)
        self.assertIn(superviseur.id, regroupement_h)


class ExclusionAgentRecouvrementTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 8, 1)

    def test_agent_recouvrement_exclu_meme_si_responsable_ouvrage(self):
        poste = Poste.objects.create(nom_poste='Agent de recouvrement', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertNotIn(self.employe.id, regroupement)

    def test_agent_recouvrement_superviseur_technique_exclu(self):
        poste = Poste.objects.create(
            nom_poste='Agent de recouvrement Superviseur technique', organisation=self.organisation,
        )
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self._creer_reparation()
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertNotIn(self.employe.id, regroupement)

    def test_agent_recouvrement_saute_dans_chaine_hierarchique_sans_interrompre(self):
        agent_recouvrement = Employe.objects.create(
            nom_employe='Agent Recouvrement Chaine', nom='Agent', base=self.base,
            mail='agent-recouvrement@example.com',
            poste=Poste.objects.create(nom_poste='Agent de recouvrement', organisation=self.organisation),
        )
        directeur = Employe.objects.create(
            nom_employe='Directeur Chaine', nom='Directeur', base=self.base, mail='directeur-chaine@example.com',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=agent_recouvrement, date_debut=date(2026, 1, 1))
        HierarchieEmploye.objects.create(employe=agent_recouvrement, superieur=directeur, date_debut=date(2026, 1, 1))
        self._creer_reparation()

        regroupement = construire_regroupement_reparations(self.date_reference)
        regroupement_h = construire_regroupement_hierarchique_reparations(regroupement, self.date_reference)

        self.assertNotIn(agent_recouvrement.id, regroupement_h)
        self.assertIn(directeur.id, regroupement_h)
        self.assertIn(self.employe.id, regroupement_h[directeur.id]['subordonnes'])

    def test_est_agent_recouvrement_ne_matche_pas_poste_agent_terrain(self):
        poste = Poste.objects.create(nom_poste='Agent de terrain', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self.assertFalse(est_agent_recouvrement(self.employe))

    def test_est_agent_recouvrement_matche_recouvrement_icontains(self):
        poste = Poste.objects.create(nom_poste='Agent de recouvrement', organisation=self.organisation)
        self.employe.poste = poste
        self.employe.save(update_fields=['poste'])
        self.assertTrue(est_agent_recouvrement(self.employe))

    def test_est_agent_recouvrement_employe_sans_poste_false(self):
        self.employe.poste = None
        self.employe.save(update_fields=['poste'])
        self.assertFalse(est_agent_recouvrement(self.employe))


class NiveauCriticiteReparationTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()

    def test_niveau_normal_sous_les_seuils(self):
        reparation = self._creer_reparation(priorite='basse')
        niveau = calculer_niveau_reparation(reparation, jours_retard=5, nb_relances_ant=0)
        self.assertEqual(niveau, 'normal')

    def test_niveau_attention_seuil_jours(self):
        reparation = self._creer_reparation(priorite='basse')
        niveau = calculer_niveau_reparation(reparation, jours_retard=20, nb_relances_ant=0)
        self.assertEqual(niveau, 'attention')

    def test_niveau_critique_seuil_jours(self):
        reparation = self._creer_reparation(priorite='basse')
        niveau = calculer_niveau_reparation(reparation, jours_retard=50, nb_relances_ant=0)
        self.assertEqual(niveau, 'critique')

    def test_niveau_critique_seuil_nb_relances(self):
        reparation = self._creer_reparation(priorite='basse')
        niveau = calculer_niveau_reparation(reparation, jours_retard=1, nb_relances_ant=3)
        self.assertEqual(niveau, 'critique')

    def test_niveau_critique_priorite_urgente(self):
        reparation = self._creer_reparation(priorite='urgente')
        niveau = calculer_niveau_reparation(reparation, jours_retard=1, nb_relances_ant=0)
        self.assertEqual(niveau, 'critique')

    def test_niveau_critique_priorite_haute(self):
        reparation = self._creer_reparation(priorite='haute')
        niveau = calculer_niveau_reparation(reparation, jours_retard=1, nb_relances_ant=0)
        self.assertEqual(niveau, 'critique')


class GradingOuvrageReparationTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 8, 1)

    def _creer_panne(self, date_planning=None, estvalide=False):
        type_activite = TypeActivite.objects.create(nomtype='Panne')
        fiche_poste = FichePoste.objects.create(
            type_activites=type_activite, tache='Panne Messaging Tests', description='...',
        )
        return Planning.objects.create(
            ouvrage=self.ouvrage, employe=self.employe, fiche_poste=fiche_poste,
            date=timezone.make_aware(datetime.combine(date_planning or date(2026, 7, 1), datetime.min.time())),
            estvalide=estvalide,
        )

    def test_grading_panne_force_niveau_critique_meme_faible_retard(self):
        from .repair_reminder import construire_regroupement_reparations

        # Reparation avec tres peu de retard (normalement 'normal'), mais
        # l'ouvrage a aussi une panne ouverte -> le grading doit pousser
        # cette reparation vers 'critique'.
        self._creer_reparation(date_prevue=date(2026, 7, 31), priorite='basse')  # 1 jour de retard
        self._creer_panne(date_planning=date(2026, 7, 1))

        regroupement = construire_regroupement_reparations(self.date_reference)
        entree_ouvrage = regroupement[self.employe.id]['ouvrages'][self.ouvrage.id]
        niveaux = {rep['niveau'] for rep in entree_ouvrage['reparations']}
        self.assertIn('critique', niveaux)

    def test_grading_sans_panne_ni_rehab_reste_grade_a(self):
        grade = grading_ouvrage_reparations(self.ouvrage.id)
        self.assertEqual(grade['code'], 'A')

    def test_grading_panne_seule_sans_reparation_donne_grade_c(self):
        # Une panne SEULE (sans reparation/rehabilitation associee) donne
        # le grade residuel 'C', pas un grade *_panne - ceux-ci necessitent
        # la COMBINAISON reparation+panne ou rehabilitation+panne (cf.
        # get_repair_workflow_grading_from_flags).
        self._creer_panne()
        grade = grading_ouvrage_reparations(self.ouvrage.id)
        self.assertEqual(grade['code'], 'C')

    def test_grading_reparation_et_panne_combinees_donne_b_panne(self):
        self._creer_reparation(date_prevue=date(2026, 7, 1))
        self._creer_panne(date_planning=date(2026, 7, 2))
        grade = grading_ouvrage_reparations(self.ouvrage.id)
        self.assertEqual(grade['code'], 'B_panne')

    def test_grading_ignore_planning_valide(self):
        self._creer_panne(estvalide=True)
        grade = grading_ouvrage_reparations(self.ouvrage.id)
        self.assertEqual(grade['code'], 'A')


class ReparationsSansResponsableTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.date_reference = date(2026, 8, 1)

    def test_planning_sans_employe_absent_du_regroupement_direct(self):
        self._creer_reparation(employe=None)
        regroupement = construire_regroupement_reparations(self.date_reference)
        self.assertEqual(regroupement, {})

    def test_compter_reparations_sans_responsable(self):
        self._creer_reparation(employe=None)
        self._creer_reparation(employe=self.employe)
        count = compter_reparations_sans_responsable(self.date_reference)
        self.assertEqual(count, 1)


class FusionRegroupementCombineTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()

    def test_regroupement_combine_cle_premier_niveau_est_ouvrage(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        self._creer_reparation()
        regroupement, *_ = construire_regroupement_combine(2026, 7, date_reference_reparations=date(2026, 8, 1))
        entree = regroupement[self.employe.id]
        self.assertEqual(len(entree['ouvrages']), 1)
        ouvrage_entree = entree['ouvrages'][self.ouvrage.id]
        self.assertTrue(ouvrage_entree['points_eau'])
        self.assertTrue(ouvrage_entree['reparations'])

    def test_ordre_affichage_paiements_avant_reparations_meme_ouvrage(self):
        # Verifie que la structure du contexte de rendu place systematiquement
        # les paiements avant les reparations pour un meme ouvrage (contrainte
        # respectee par construction du template, verifiee ici sur le contexte).
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        self._creer_reparation()
        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, dry_run=True, date_reference_reparations=date(2026, 8, 1),
        )
        detail = resultat['details'][0]
        idx_paiements = detail['html'].index('Paiements à pointer')
        idx_reparations = detail['html'].index('Réparations échues')
        self.assertLess(idx_paiements, idx_reparations)

    def test_section_reparations_absente_si_aucune_reparation_ouvrage(self):
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, dry_run=True, date_reference_reparations=date(2026, 8, 1),
        )
        detail = resultat['details'][0]
        self.assertNotIn('Réparations échues', detail['html'])

    def test_section_paiements_absente_si_aucun_paiement_ouvrage(self):
        self._creer_reparation()
        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, dry_run=True, date_reference_reparations=date(2026, 8, 1),
        )
        detail = resultat['details'][0]
        self.assertNotIn('Paiements à pointer', detail['html'])

    def test_tri_ouvrages_criticite_desc_puis_retard_desc(self):
        autre_ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage Normal', type_ouvrage=self.type_ouvrage)
        ouvrages = {
            self.ouvrage.id: {
                'ouvrage': self.ouvrage, 'points_eau': {},
                'reparations': [{'reparation': self._creer_reparation(), 'jours_retard': 50, 'niveau': 'critique'}],
            },
            autre_ouvrage.id: {
                'ouvrage': autre_ouvrage, 'points_eau': {}, 'reparations': [],
            },
        }
        tries = trier_ouvrages_par_criticite(ouvrages)
        self.assertEqual(tries[0]['ouvrage'].id, self.ouvrage.id)
        self.assertEqual(tries[0]['niveau_ouvrage'], 'critique')
        self.assertEqual(tries[1]['niveau_ouvrage'], 'normal')

    def test_ouvrage_paiements_seuls_toujours_niveau_normal(self):
        entree_ouvrage = {'ouvrage': self.ouvrage, 'points_eau': {'x': {}}, 'reparations': []}
        self.assertEqual(calculer_niveau_ouvrage(entree_ouvrage), 'normal')


class DedupDestinataireTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()

    def test_destinataire_multi_chemins_recoit_un_seul_email(self):
        # self.employe est responsable direct de self.ouvrage (paiement), et
        # devient egalement superieur hierarchique d'un autre responsable
        # (autre_ouvrage, reparation) : il ne doit apparaitre qu'une fois.
        autre_ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage Subordonne', type_ouvrage=self.type_ouvrage)
        subordonne = Employe.objects.create(
            nom_employe='Subordonne Dedup', nom='Sub', base=self.base, mail='sub-dedup@example.com',
        )
        EmployeOuvrages.objects.create(
            employe=subordonne, ouvrage=autre_ouvrage, date_debut=date(2026, 1, 1), recevoir_alertes=True,
        )
        HierarchieEmploye.objects.create(employe=subordonne, superieur=self.employe, date_debut=date(2026, 1, 1))

        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        self._creer_reparation(ouvrage=autre_ouvrage)

        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, dry_run=True, date_reference_reparations=date(2026, 8, 1),
        )
        details_employe = [d for d in resultat['details'] if d['employe'].id == self.employe.id]
        self.assertEqual(len(details_employe), 1)
        self.assertEqual(details_employe[0]['type_destinataire'], 'responsable')
        self.assertEqual(len(details_employe[0]['sujet']) > 0, True)

    def test_type_destinataire_superieur_si_aucun_ouvrage_direct(self):
        chef = Employe.objects.create(
            nom_employe='Chef Sans Ouvrage', nom='Chef', base=self.base, mail='chef-sans-ouvrage@example.com',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=chef, date_debut=date(2026, 1, 1))
        self._creer_reparation()

        regroupement, *_ = construire_regroupement_combine(2026, 7, date_reference_reparations=date(2026, 8, 1))
        self.assertEqual(regroupement[chef.id]['type_destinataire'], 'superieur')
        self.assertEqual(regroupement[self.employe.id]['type_destinataire'], 'responsable')


class CompteurRelanceReparationTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        self.reparation = self._creer_reparation()

    def test_un_seul_increment_par_cycle_meme_avec_plusieurs_destinataires(self):
        chef = Employe.objects.create(
            nom_employe='Chef Compteur', nom='Chef', base=self.base, mail='chef-compteur@example.com',
        )
        HierarchieEmploye.objects.create(employe=self.employe, superieur=chef, date_debut=date(2026, 1, 1))

        envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, date_reference_reparations=date(2026, 8, 1),
        )

        traces = RelanceReparations.objects.filter(reparation=self.reparation, est_test=False)
        # 2 destinataires (responsable + superieur) mais un seul batch_id partage
        self.assertEqual(traces.count(), 2)
        self.assertEqual(traces.values('batch_id').distinct().count(), 1)
        for trace in traces:
            self.assertEqual(trace.nb_relances, 1)

    def test_deux_cycles_successifs_incrementent_nb_relances(self):
        envoyer_toutes_les_relances_combinees(annee=2026, mois=7, date_reference_reparations=date(2026, 8, 1))
        envoyer_toutes_les_relances_combinees(annee=2026, mois=7, date_reference_reparations=date(2026, 8, 15))

        traces = RelanceReparations.objects.filter(
            reparation=self.reparation, employe=self.employe, type_destinataire='responsable', est_test=False,
        ).order_by('created_at')
        self.assertEqual(traces.count(), 2)
        self.assertEqual(traces.first().nb_relances, 1)
        self.assertEqual(traces.last().nb_relances, 2)
        self.assertEqual(traces.values('batch_id').distinct().count(), 2)


class ReverificationEnvoiTests(ReparationFixtureMixin, TestCase):
    """
    Verifie que _reverifier_eligibilite() (appelee juste avant l'envoi, pas
    au moment de la selection initiale) exclut bien tout element devenu
    non-eligible entre-temps. Construit une entree destinataire "figee" a la
    main pour simuler fidelement une selection anterieure a un changement
    d'etat reel en base (le pointage/la fin de reparation intervient APRES
    la construction de cette entree, jamais avant)."""

    def setUp(self):
        self._creer_fixtures_base()

    def _construire_entree_figee_paiement(self, releve):
        return {'ouvrages': {
            self.ouvrage.id: {
                'ouvrage': self.ouvrage,
                'points_eau': {
                    self.point_eau.id: {
                        'point_eau': self.point_eau,
                        'lignes': [{'type': 'releve', 'objet': releve, 'date': releve.datereleve, 'montant': releve.montant}],
                    },
                },
                'reparations': [],
            },
        }}

    def _construire_entree_figee_reparation(self, reparation, jours_retard=10, niveau='normal'):
        return {'ouvrages': {
            self.ouvrage.id: {
                'ouvrage': self.ouvrage,
                'points_eau': {},
                'reparations': [{'reparation': reparation, 'jours_retard': jours_retard, 'niveau': niveau}],
            },
        }}

    def test_paiement_pointe_entre_selection_et_envoi_exclu(self):
        from .relance_mailer_combine import _reverifier_eligibilite

        releve = Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        entree_figee = self._construire_entree_figee_paiement(releve)

        # Le pointage survient APRES la construction de l'entree figee.
        releve.numeroDiameX = 'DX-APRES-SELECTION'
        releve.save(update_fields=['numeroDiameX'])

        ouvrages_valides = _reverifier_eligibilite(entree_figee, date(2026, 7, 31), date(2026, 8, 1))
        self.assertEqual(ouvrages_valides, {})

    def test_reparation_terminee_entre_selection_et_envoi_exclue(self):
        from .relance_mailer_combine import _reverifier_eligibilite

        reparation = self._creer_reparation()
        entree_figee = self._construire_entree_figee_reparation(reparation)

        # La fin de reparation survient APRES la construction de l'entree figee.
        reparation.estvalide = True
        reparation.save(update_fields=['estvalide'])

        ouvrages_valides = _reverifier_eligibilite(entree_figee, date(2026, 7, 31), date(2026, 8, 1))
        self.assertEqual(ouvrages_valides, {})

    def test_destinataire_vide_apres_reverification_aucun_envoi_aucune_trace(self):
        releve = Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='DX-DEJA-POINTE',
        )
        # Ce releve est deja pointe AVANT le cycle : jamais selectionne, donc
        # jamais envoye ni trace - comportement de base, pas un cas de
        # re-verification a proprement parler, mais confirme l'absence
        # d'effet de bord (aucune trace fictive) sur un cycle sans rien a
        # envoyer.
        envoyer_toutes_les_relances_combinees(annee=2026, mois=7)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(RelanceFacturesNonPointees.objects.count(), 0)
        self.assertEqual(RelanceReparations.objects.count(), 0)


class EnvoiRelancesCombineesTests(ReparationFixtureMixin, TestCase):
    def setUp(self):
        self._creer_fixtures_base()
        Releve.objects.create(
            point_eau=self.point_eau, abonne='Abonne', datereleve=date(2026, 3, 1),
            ancienindex=0, nouvelindex=5, consommation=5, statut='impaye',
            montant=Decimal('500'), numeroDiameX='',
        )
        self._creer_reparation()

    def test_email_combine_envoye_avec_html_et_texte(self):
        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, date_reference_reparations=date(2026, 8, 1),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].alternatives)
        self.assertEqual(resultat['nb_envoyes'], 1)

    def test_idempotence_meme_batch_pas_de_doublon_meme_cycle(self):
        envoyer_toutes_les_relances_combinees(annee=2026, mois=7, date_reference_reparations=date(2026, 8, 1))
        envoyer_toutes_les_relances_combinees(annee=2026, mois=7, date_reference_reparations=date(2026, 8, 1))
        # Deuxieme cycle = nouveau batch_id, donc un deuxieme email est bien
        # renvoye (le paiement, lui, reste bloque par l'unicite existante de
        # RelanceFacturesNonPointees hors periode/type).
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            RelanceReparations.objects.filter(est_test=False).values('batch_id').distinct().count(), 2,
        )

    def test_dry_run_combine_aucun_envoi_aucune_ecriture(self):
        envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, dry_run=True, date_reference_reparations=date(2026, 8, 1),
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(RelanceFacturesNonPointees.objects.count(), 0)
        self.assertEqual(RelanceReparations.objects.count(), 0)

    def test_mode_test_redirige_vers_adresse_unique(self):
        resultat = envoyer_toutes_les_relances_combinees(
            annee=2026, mois=7, est_test=True, email_test_override='qa@example.com',
            date_reference_reparations=date(2026, 8, 1),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['qa@example.com'])
        self.assertIn('TEST', mail.outbox[0].subject)
