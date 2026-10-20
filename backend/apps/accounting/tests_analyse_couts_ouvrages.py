"""Tests du service d'analyse des coûts par ouvrage."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.accounting.services import analyse_couts_ouvrages as svc


class ResoudrePeriodeTests(SimpleTestCase):
    def test_douze_mois_complets_mois_courant_exclu(self):
        d1, d2 = svc.resoudre_periode(reference=date(2026, 9, 10))
        self.assertEqual(d2, date(2026, 8, 31))  # fin = dernier jour du mois précédent
        self.assertEqual(d1, date(2025, 9, 1))   # début = 12 mois avant
        # le mois de la référence n'est jamais dans la fenêtre
        self.assertLess(d2, date(2026, 9, 1))

    def test_bascule_annee(self):
        d1, d2 = svc.resoudre_periode(reference=date(2026, 1, 5))
        self.assertEqual(d2, date(2025, 12, 31))
        self.assertEqual(d1, date(2025, 1, 1))


def _ctx(jours, pe):
    ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
    ctx.ouvrage_ids = set(jours) | set(pe)
    ctx.jours_planning_by_ouvrage = dict(jours)
    ctx.pe_public_by_ouvrage = dict(pe)
    return ctx


class PoidsOuvragesTests(SimpleTestCase):
    def test_alpha_1_utilise_les_jours_de_planning(self):
        ctx = _ctx({"a": 30, "b": 10}, {"a": 1, "b": 9})
        poids = svc.poids_ouvrages(ctx, Decimal("1"))
        self.assertAlmostEqual(float(poids["a"]), 0.75)
        self.assertAlmostEqual(float(poids["b"]), 0.25)

    def test_alpha_0_utilise_les_points_deau(self):
        ctx = _ctx({"a": 30, "b": 10}, {"a": 1, "b": 9})
        poids = svc.poids_ouvrages(ctx, Decimal("0"))
        self.assertAlmostEqual(float(poids["a"]), 0.1)
        self.assertAlmostEqual(float(poids["b"]), 0.9)

    def test_repli_sur_points_deau_si_aucun_planning(self):
        ctx = _ctx({}, {"a": 2, "b": 3})
        poids = svc.poids_ouvrages(ctx, Decimal("0.5"))
        self.assertAlmostEqual(float(poids["a"]), 0.4)
        self.assertAlmostEqual(float(poids["b"]), 0.6)


class RepartirCoutEmployeTests(SimpleTestCase):
    def _ctx_emp(self):
        ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        ctx.ouvrage_ids = {"o1", "o2"}
        ctx.pe_public_by_ouvrage = {"o1": 4, "o2": 4}
        ctx.employe_ouvrages_by_emp = {"emp": {"o1", "o2"}}
        ctx.jours_emp_ouvrage = {("emp", "o1"): 8, ("emp", "o2"): 2}
        return ctx

    def test_scinde_le_cout_sur_les_ouvrages_de_lemploye(self):
        ctx = self._ctx_emp()
        v, mode = svc.repartir_cout_employe(ctx, Decimal("1000"), "emp", Decimal("1"))
        self.assertEqual(mode, "direct")
        self.assertAlmostEqual(float(v["o1"]), 800.0)   # 8/10 des jours
        self.assertAlmostEqual(float(v["o2"]), 200.0)
        self.assertAlmostEqual(sum(float(x) for x in v.values()), 1000.0)

    def test_alpha_0_repartit_selon_points_deau(self):
        ctx = self._ctx_emp()
        v, mode = svc.repartir_cout_employe(ctx, Decimal("1000"), "emp", Decimal("0"))
        self.assertAlmostEqual(float(v["o1"]), 500.0)
        self.assertAlmostEqual(float(v["o2"]), 500.0)

    def test_aucun_ouvrage_rattachable_retourne_vide(self):
        ctx = self._ctx_emp()
        v, mode = svc.repartir_cout_employe(ctx, Decimal("1000"), "inconnu", Decimal("0.5"))
        self.assertEqual(v, {})
        self.assertEqual(mode, "aucun")

    def test_mode_hierarchie_via_subordonne(self):
        ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        ctx.ouvrage_ids = {"o1"}
        ctx.pe_public_by_ouvrage = {"o1": 3}
        ctx.employe_ouvrages_by_emp = {"sub": {"o1"}}
        ctx.subordonnes_by_emp = {"chef": {"sub"}}
        v, mode = svc.repartir_cout_employe(ctx, Decimal("900"), "chef", Decimal("0.5"))
        self.assertEqual(mode, "hierarchie")
        self.assertAlmostEqual(float(v["o1"]), 900.0)


class GestionStartTests(SimpleTestCase):
    class _Mod:
        def __init__(self, d):
            self.date_debut = d

    def _ctx(self):
        ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        ctx.ouvrage_ids = {"o1", "o2"}
        ctx.pe_public_by_ouvrage = {"o1": 5, "o2": 5}
        ctx.employe_ouvrages_by_emp = {"emp": {"o1", "o2"}}
        ctx.modalite_by_ouvrage = {"o1": self._Mod(date(2025, 11, 1))}  # o2 sans modalité
        return ctx

    def test_ligne_avant_debut_gestion_ecartee(self):
        ctx = self._ctx()
        self.assertFalse(svc._ouvrage_sous_gestion_a(ctx, "o1", date(2025, 10, 15)))
        self.assertTrue(svc._ouvrage_sous_gestion_a(ctx, "o1", date(2025, 11, 15)))
        self.assertTrue(svc._ouvrage_sous_gestion_a(ctx, "o2", date(2025, 3, 1)))

    def test_repartition_exclut_ouvrage_pas_encore_gere(self):
        ctx = self._ctx()
        # dépense d'octobre : o1 pas encore géré -> tout va sur o2
        v, _ = svc.repartir_cout_employe(ctx, Decimal("1000"), "emp", Decimal("0.5"), date(2025, 10, 10))
        self.assertNotIn("o1", v)
        self.assertAlmostEqual(float(v["o2"]), 1000.0)
        # dépense de décembre : les deux gérés -> réparti
        v2, _ = svc.repartir_cout_employe(ctx, Decimal("1000"), "emp", Decimal("0"), date(2025, 12, 10))
        self.assertAlmostEqual(float(v2["o1"]), 500.0)
        self.assertAlmostEqual(float(v2["o2"]), 500.0)


class _Ouv:
    def __init__(self, nom):
        self.nom_ouvrage = nom


class EstPrestationMiTests(SimpleTestCase):
    def test_detecte_compte_et_marqueur(self):
        self.assertTrue(svc._est_prestation_mi("621101", "NIF_X_Prestation MI_Ambato"))
        self.assertTrue(svc._est_prestation_mi("621101", "prestation mi divers"))  # insensible casse

    def test_ignore_autre_compte(self):
        self.assertFalse(svc._est_prestation_mi("621102", "Prestation MI Ambato"))

    def test_ignore_sans_marqueur(self):
        self.assertFalse(svc._est_prestation_mi("621101", "Indemnité RBF Ambato"))

    def test_gere_description_none(self):
        self.assertFalse(svc._est_prestation_mi("621101", None))


class EstChefLieuTests(SimpleTestCase):
    def _ctx(self):
        ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        ctx.ouvrages_by_id = {
            "chateau": _Ouv("Chateau"),
            "vohilengo_aepg": _Ouv("Vohilengo AEPG"),
            "ambato_bp": _Ouv("Ambato BP"),
        }
        ctx.commune_by_ouvrage = {
            "chateau": "c1",
            "vohilengo_aepg": "c2",
            "ambato_bp": "c3",
        }
        ctx.commune_nom_by_id = {"c1": "Chateau", "c2": "Vohilengo", "c3": "Ambato"}
        return ctx

    def test_nom_identique_est_chef_lieu(self):
        ctx = self._ctx()
        self.assertTrue(svc._est_chef_lieu(ctx, "chateau"))

    def test_exception_vohilengo_aepg(self):
        ctx = self._ctx()
        self.assertFalse(svc._est_chef_lieu(ctx, "vohilengo_aepg"))

    def test_nom_different_pas_chef_lieu(self):
        ctx = self._ctx()
        self.assertFalse(svc._est_chef_lieu(ctx, "ambato_bp"))

    def test_ouvrage_sans_commune(self):
        ctx = self._ctx()
        self.assertFalse(svc._est_chef_lieu(ctx, "inconnu"))


class RepartirPrestationMiTests(SimpleTestCase):
    def _ctx(self):
        ctx = svc.ContexteAnalyse(date_debut=date(2025, 1, 1), date_fin=date(2025, 12, 31))
        ctx.ouvrage_ids = {"a", "b", "d"}
        ctx.ouvrages_by_id = {
            "a": _Ouv("Chateau"),          # chef-lieu
            "b": _Ouv("Chateau Peripherie"),  # même commune, pas chef-lieu
            "d": _Ouv("Autre"),
        }
        ctx.commune_by_ouvrage = {"a": "c1", "b": "c1"}
        ctx.commune_nom_by_id = {"c1": "Chateau"}
        ctx.ouvrages_by_commune = {"c1": {"a", "b"}}
        ctx.pe_public_by_ouvrage = {"a": 2, "b": 8, "d": 10}
        ctx.employe_ouvrages_by_emp = {"emp": {"a", "d"}}
        return ctx

    def test_expansion_chef_lieu_sur_la_commune(self):
        ctx = self._ctx()
        v = svc.repartir_prestation_mi(ctx, Decimal("1200"), "emp")
        # Niveau 1 : a=200 (chef-lieu, éclaté sur commune), d=1000 (direct)
        # Niveau 2 sur commune c1 (a=2, b=8, total 10) : a -> 200*2/10=40, b -> 200*8/10=160
        self.assertAlmostEqual(float(v["a"]), 40.0)
        self.assertAlmostEqual(float(v["b"]), 160.0)
        self.assertAlmostEqual(float(v["d"]), 1000.0)
        self.assertAlmostEqual(sum(float(x) for x in v.values()), 1200.0)

    def test_aucun_ouvrage_responsable_retourne_vide(self):
        ctx = self._ctx()
        v = svc.repartir_prestation_mi(ctx, Decimal("500"), "inconnu")
        self.assertEqual(v, {})

    def test_repli_egal_sans_points_deau(self):
        ctx = self._ctx()
        ctx.pe_public_by_ouvrage = {}
        v = svc.repartir_prestation_mi(ctx, Decimal("1000"), "emp")
        # a et d à parts égales (500/500), a est chef-lieu -> réparti égal sur a/b (250/250)
        self.assertAlmostEqual(float(v["a"]), 250.0)
        self.assertAlmostEqual(float(v["b"]), 250.0)
        self.assertAlmostEqual(float(v["d"]), 500.0)


class NbTrimestresTests(SimpleTestCase):
    def test_fenetre_pleine(self):
        self.assertEqual(
            svc._nb_trimestres_periode(None, date(2025, 1, 1), date(2025, 12, 31)), 4
        )

    def test_debut_gestion_au_milieu(self):
        class M:
            date_debut = date(2025, 7, 1)

        self.assertEqual(
            svc._nb_trimestres_periode(M(), date(2025, 1, 1), date(2025, 12, 31)), 2
        )


def _ligne(depense_totale, recette_realisee, recette_prevue):
    return {
        "depenses": {"total": depense_totale},
        "recette_realisee": recette_realisee,
        "recette_prevue": recette_prevue,
    }


class RangPercentileTests(SimpleTestCase):
    def test_liste_vide(self):
        self.assertEqual(svc._rang_percentile([]), {})

    def test_une_seule_valeur_rang_neutre(self):
        self.assertEqual(svc._rang_percentile([("a", 42)]), {"a": 0.5})

    def test_ordre_croissant(self):
        rangs = svc._rang_percentile([("a", 30), ("b", 10), ("c", 20)])
        self.assertAlmostEqual(rangs["b"], 0.0)
        self.assertAlmostEqual(rangs["c"], 0.5)
        self.assertAlmostEqual(rangs["a"], 1.0)

    def test_ex_aequo_recoivent_le_meme_rang_moyen(self):
        rangs = svc._rang_percentile([("a", 10), ("b", 10), ("c", 30)])
        self.assertAlmostEqual(rangs["a"], rangs["b"])
        self.assertEqual(rangs["c"], 1.0)


class CalculerIndicateursFinanciersTests(SimpleTestCase):
    def test_recettes_facturees_egale_encaisse_plus_impaye(self):
        lignes = [_ligne(0, 700, 1000)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertEqual(l["recettes_facturees"], 1000)
        self.assertEqual(l["impayes"], 300)
        self.assertAlmostEqual(l["recettes_facturees"], l["impayes"] + 700)

    def test_taux_recouvrement_et_impayes(self):
        lignes = [_ligne(0, 750, 1000)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertAlmostEqual(l["taux_recouvrement"], 75.0)
        self.assertAlmostEqual(l["taux_impayes"], 25.0)

    def test_ratio_charges_superieur_a_1_signale_deficit(self):
        lignes = [_ligne(1500, 1000, 1000)]
        svc.calculer_indicateurs_financiers(lignes)
        self.assertAlmostEqual(lignes[0]["ratio_charges"], 1.5)
        self.assertFalse(lignes[0]["ratio_charges_infini"])

    def test_aucune_recette_encaissee_mais_depenses_ratio_infini(self):
        lignes = [_ligne(500, 0, 1000)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertIsNone(l["ratio_charges"])
        self.assertTrue(l["ratio_charges_infini"])
        # l'ouvrage a un historique (dépenses + facturation) -> score quand même calculé
        self.assertIsNotNone(l["score_criticite"])

    def test_aucune_depense_ratio_charges_zero_meme_sans_recette(self):
        lignes = [_ligne(0, 0, 1000)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertEqual(l["ratio_charges"], 0.0)
        self.assertFalse(l["ratio_charges_infini"])
        self.assertEqual(l["taux_impayes"], 100.0)

    def test_ouvrage_sans_historique_tous_indicateurs_a_none(self):
        lignes = [_ligne(0, 0, 0)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertTrue(l["sans_historique"])
        for cle in ("taux_recouvrement", "ratio_charges", "taux_impayes", "score_criticite"):
            self.assertIsNone(l[cle])

    def test_sans_facturation_taux_recouvrement_indefini(self):
        # recette encaissée sans base de facturation connue (rare, cas limite)
        lignes = [_ligne(0, 500, 0)]
        svc.calculer_indicateurs_financiers(lignes)
        l = lignes[0]
        self.assertFalse(l["sans_historique"])
        self.assertIsNone(l["taux_recouvrement"])
        self.assertEqual(l["impayes"], 0.0)

    def test_score_plus_eleve_pour_le_plus_deficitaire(self):
        sain = _ligne(100, 1000, 1000)       # ratio 0.1, 0% impayé
        moyen = _ligne(1000, 1000, 1200)     # ratio 1.0 (à l'équilibre), ~17% impayé
        maivoas = _ligne(500, 0, 2000)       # dépense mais rien d'encaissé -> ratio infini, 100% impayé
        lignes = [sain, moyen, maivoas]
        svc.calculer_indicateurs_financiers(lignes)
        self.assertLess(sain["score_criticite"], moyen["score_criticite"])
        self.assertLess(moyen["score_criticite"], maivoas["score_criticite"])
        self.assertTrue(maivoas["ratio_charges_infini"])
        self.assertEqual(maivoas["score_criticite"], 100.0)
        self.assertEqual(sain["score_criticite"], 0.0)

    def test_ligne_sans_historique_exclue_de_la_normalisation(self):
        # la ligne "sans historique" ne doit pas polluer le classement des deux autres
        a = _ligne(500, 500, 1000)   # ratio 1.0, 50% impayé
        b = _ligne(100, 900, 1000)   # ratio ~0.11, 10% impayé
        vide = _ligne(0, 0, 0)
        lignes = [a, b, vide]
        svc.calculer_indicateurs_financiers(lignes)
        self.assertIsNone(vide["score_criticite"])
        self.assertGreater(a["score_criticite"], b["score_criticite"])


class CleTriCriticiteTests(SimpleTestCase):
    def test_score_none_relegue_en_fin_de_liste(self):
        lignes = [
            {"score_criticite": None, "nom": "vide"},
            {"score_criticite": 20.0, "nom": "sain"},
            {"score_criticite": 80.0, "nom": "maivoas"},
        ]
        lignes.sort(key=svc._cle_tri_criticite)
        self.assertEqual([l["nom"] for l in lignes], ["maivoas", "sain", "vide"])
