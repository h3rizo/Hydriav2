"""
Moteur de saisie comptable guidee : compose la `description` DiameX (et remplit
`fournisseur` / `detail`) a partir de champs structures, selon une `RegleSaisieCompte`.

- `engine.resoudre_regle(organisation_id, compte_code)` -> RegleSaisieCompte | None
- `engine.composer_ecriture(regle, valeurs)` -> EcritureComposee
- `seed_data.REGLES` : les regles par compte, chargees par la commande `seed_regles_saisie`
"""
