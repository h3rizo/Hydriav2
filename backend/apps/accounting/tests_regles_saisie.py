"""Tests du moteur de saisie guidee (composition + resolution)."""
from types import SimpleNamespace

from django.test import TestCase

from apps.accounting.models_regles_saisie import RegleSaisieCompte
from apps.accounting.regles_saisie.engine import composer_ecriture, resoudre_regle
from apps.accounting.regles_saisie.schema import valider_config
from apps.accounting.regles_saisie.seed_data import REGLES


# --- resolver factice : evite les fixtures DB pour les tests de composition ---
_FOURNS = {
    "F_NIF": SimpleNamespace(idxls=58, nom_fournisseur="QUINCAILLERIE SOA",
                             numero_nif="1234567890", nif_ou_isi="NIF"),
    "F_ISI": SimpleNamespace(idxls=99, nom_fournisseur="Ets DUPONT",
                             numero_nif="", nif_ou_isi="ISI"),
    "F_TOTAL": SimpleNamespace(idxls=312, nom_fournisseur="TOTAL",
                               numero_nif="9999999999", nif_ou_isi="NIF"),
}
_OUVRAGES = {"O1": SimpleNamespace(nom_ouvrage="Ambanja BP")}
_POSTE = SimpleNamespace(prefixe="RESP")
_EMPLOYES = {"E1": SimpleNamespace(nom_complet="Jean DUPONT", nom="DUPONT",
                                   surnom="JDUP", poste_id=1, poste=_POSTE)}
_VEHICULES = {"V1": SimpleNamespace(immatriculation="1234 TAA", type_vehicule="voiture")}


def _resolver(kind, pk):
    return {"fournisseur": _FOURNS, "ouvrage": _OUVRAGES,
            "employe": _EMPLOYES, "vehicule": _VEHICULES}.get(kind, {}).get(pk)


def _regle(compte_cible):
    r = next(x for x in REGLES if x["compte_cible"] == compte_cible)
    return RegleSaisieCompte(compte_cible=r["compte_cible"], est_prefixe=r["est_prefixe"],
                             mode=r["mode"], sens=r["sens"], libelle=r["libelle"], config=r["config"])


class ConfigSeedTest(TestCase):
    def test_toutes_les_configs_valides(self):
        for r in REGLES:
            self.assertEqual(valider_config(r["config"]), [], f"config {r['compte_cible']}")

    def test_pas_de_doublon_compte(self):
        codes = [r["compte_cible"] for r in REGLES]
        self.assertEqual(len(codes), len(set(codes)))


class CompositionFournisseurTest(TestCase):
    def test_601011_ouvrage_sans_prestation(self):
        out = composer_ecriture(_regle("601011"), {
            "fournisseur": "F_NIF", "prestation": False, "libelle": "Ciment",
            "unite": "Sac", "pu": "45000", "cible": "ouvrage", "ouvrage": "O1", "reste": "",
        }, resolver=_resolver)
        self.assertEqual(out.description, "NIF_QUINCAILLERIE SOA_Ciment_Sac_45000_Ambanja BP")
        self.assertEqual(out.fournisseur, "58")
        self.assertEqual(out.sens, "out")
        self.assertEqual(out.warnings, [])

    def test_601011_prestation_isi(self):
        out = composer_ecriture(_regle("601011"), {
            "fournisseur": "F_ISI", "prestation": True, "libelle": "Pose",
            "unite": "Forfait", "pu": "120000", "cible": "magasin", "magasin": "Central", "reste": "urgence",
        }, resolver=_resolver)
        self.assertEqual(out.description, "ISI PREST_Ets DUPONT_Pose_Forfait_120000_urgence")
        self.assertEqual(out.fournisseur, "99")

    def test_606100_essence_vehicule(self):
        out = composer_ecriture(_regle("606100"), {
            "fournisseur": "F_TOTAL", "pu": "10000", "cible": "vehicule", "vehicule": "V1", "reste": "",
        }, resolver=_resolver)
        self.assertTrue(out.description.startswith("NIF_TOTAL_Essence_L_10000"))
        self.assertEqual(out.detail, "1234 TAA")  # immatriculation -> colonne Detail

    def test_748411_forfaitaire(self):
        out = composer_ecriture(_regle("748411"), {
            "ouvrage": "O1", "nb_tranches": "3", "tarif": "75000",
        }, resolver=_resolver)
        self.assertEqual(out.description, "Paiement forfaitaire_U_3_75000_Ambanja BP")
        self.assertEqual(out.sens, "in")


class CompositionEmployeTest(TestCase):
    def test_641_salaire(self):
        out = composer_ecriture(_regle("641"), {
            "employe": "E1", "nature": "Salaire", "annee_mois": "2025 03",
        }, resolver=_resolver)
        self.assertEqual(out.description, "RESP Jean DUPONT_Salaire_2025 03")
        self.assertEqual(out.fournisseur, "SALNET")
        self.assertEqual(out.detail, "JDUP")

    def test_641_frais_medicaux_marker(self):
        out = composer_ecriture(_regle("641"), {
            "employe": "E1", "nature": "Frais medicaux", "annee_mois": "2025 03",
        }, resolver=_resolver)
        self.assertEqual(out.fournisseur, "SALMED")

    def test_631_irsa_marker_fixe(self):
        out = composer_ecriture(_regle("631"), {
            "employe": "E1", "annee_mois": "2025 03",
        }, resolver=_resolver)
        self.assertEqual(out.description, "RESP Jean DUPONT_IRSA_2025 03")
        self.assertEqual(out.fournisseur, "SALIRSA")

    def test_625107_indemnite_terrain(self):
        out = composer_ecriture(_regle("625107"), {
            "employe": "E1", "nombre": "5", "pu": "10000", "annee_mois": "2025 03",
        }, resolver=_resolver)
        self.assertEqual(out.description, "RESP Jean DUPONT_Indemnite terrain_5 x 10000 2025 03")
        self.assertEqual(out.detail, "JDUP")


class CompositionRecetteTest(TestCase):
    def test_707401_paiement_volume(self):
        out = composer_ecriture(_regle("707401"), {
            "ouvrage": "O1", "periode": "2026 03", "releves": "03/2026 9200; 04/2026 246500",
        }, resolver=_resolver)
        self.assertEqual(
            out.description,
            "Paiement au volume Ambanja BP 01/03/2026 03/2026 9200; 04/2026 246500",
        )
        self.assertEqual(out.sens, "in")

    def test_707401_sans_releves(self):
        out = composer_ecriture(_regle("707401"), {
            "ouvrage": "O1", "periode": "2026-11",
        }, resolver=_resolver)
        self.assertEqual(out.description, "Paiement au volume Ambanja BP 01/11/2026")

    def test_748415_cartes_sociales(self):
        out = composer_ecriture(_regle("748415"), {
            "ouvrage": "O1", "periode": "2026 11",
        }, resolver=_resolver)
        self.assertEqual(out.description, "Cartes sociales Ambanja BP 01/11/2026")
        self.assertEqual(out.sens, "in")

    def test_748201_installation_bp(self):
        out = composer_ecriture(_regle("748201"), {
            "abonne": "RAKOTO Jean", "type_bp": "BP", "idxls": "81", "ouvrage": "O1",
        }, resolver=_resolver)
        self.assertEqual(out.description, "RAKOTO Jean_Paiement pour installation BP_81_Ambanja BP")
        self.assertEqual(out.sens, "in")


class CompositionLibreTest(TestCase):
    def test_614100_libre(self):
        out = composer_ecriture(_regle("614100"), {"description": "Divers frais bureau"},
                                resolver=_resolver)
        self.assertEqual(out.description, "Divers frais bureau")
        self.assertEqual(out.sens, "out")


class ResolutionRegleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.organization.models import Organisation
        cls.org = Organisation.objects.create(nom_organisation="Test Org Regles")
        RegleSaisieCompte.objects.create(organisation=cls.org, compte_cible="641",
                                         est_prefixe=True, mode="employe", sens="out", config={})
        RegleSaisieCompte.objects.create(organisation=cls.org, compte_cible="641402",
                                         est_prefixe=False, mode="employe", sens="out", config={})
        RegleSaisieCompte.objects.create(organisation=cls.org, compte_cible="6",
                                         est_prefixe=True, mode="libre", sens="out", config={})

    def test_exact_gagne_sur_prefixe(self):
        r = resoudre_regle(self.org.id, "641402")
        self.assertEqual(r.compte_cible, "641402")

    def test_prefixe_le_plus_long(self):
        r = resoudre_regle(self.org.id, "641500")
        self.assertEqual(r.compte_cible, "641")

    def test_prefixe_court_en_dernier_recours(self):
        r = resoudre_regle(self.org.id, "601011")
        self.assertEqual(r.compte_cible, "6")

    def test_aucune_regle(self):
        self.assertIsNone(resoudre_regle(self.org.id, "999999"))
