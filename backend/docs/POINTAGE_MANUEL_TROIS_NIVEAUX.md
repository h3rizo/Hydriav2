# Pointage manuel à trois niveaux — lignes DiameX & rapprochements

**Page** : `/comptabilite/pointage-mensuel/` (`accounting:pointage_mensuel`)
**Menu** : Comptabilité → « Pointage et validation mensuelle »

## Objectif

Circuit de validation manuelle traçable **caissière → responsable opérationnel →
directeur**, commun aux lignes DiameX et aux rapprochements de soldes, avec remarques,
retours en correction et validation mensuelle.

**Contrainte** : toutes les données de pointage restent dans Hydria. **Aucune colonne
n'est ajoutée aux bases Access.** Les enregistrements Hydria sont reliés à l'identifiant
Access stable (`id_access` pour les lignes, `journal:<code>` / `tiers:<pers>` pour les
rapprochements) + le `fichier_source`.

## Modèles — `apps/accounting/models_pointage.py`

| Modèle | Rôle |
|---|---|
| `MoisPointage` | un (`fichier_source`, `periode`) ; porte la validation mensuelle |
| `ObjetPointage` | une ligne ou un rapprochement : `niveau` (0→3), `correction`, `empreinte`, et pour les soldes `solde_reference` / `justification` / `document` |
| `DecisionPointage` | journal immuable de chaque décision (auteur, rôle, action, remarque, empreinte) |

Migration : `0031_pointage_manuel_trois_niveaux`.

## Moteur — `apps/accounting/pointage_workflow.py`

- `construire_mois(source, periode)` reconstruit l'état complet du mois à chaque lecture
  et **recalcule une empreinte SHA-256** de chaque objet à partir des données Access + des
  contrôles. Si l'empreinte a changé depuis le dernier visa (synchro Access qui modifie
  montant, libellé, Cat, Fin…), l'objet retombe à `niveau 0 / correction` et le mois
  validé repasse **« À revalider »** — sans dépendre de signaux.
- `controles_ligne(entry)` : contrôles applicables selon le compte
  (`Scan` toujours ; `Avec ouvrage` / `Sans ouvrage` selon `Compte.necessite_ouvrage` ;
  `Fournisseur` selon `Compte.fournisseur_obligatoire` ; sinon `Autres`).
  Exception : les **codes techniques DiameX** (`settings.POINTAGE_CODES_TECHNIQUES`,
  par défaut préfixes `00PERS`, `00BOOK`, `00SPLITBOOK`, `00FND` — tiers, transferts
  entre comptes, financements) sont reconnus **sans fiche `Compte`** ; contrôle
  `Compte technique`, aucun contrôle ouvrage/fournisseur/charte/financement, scan non
  exigé, seul le libellé est vérifié.
  Le pointage est
  **bloqué** tant qu'un contrôle obligatoire échoue ou que le scan est absent ; les
  raisons sont affichées. Une **remarque** reste possible même bloqué.
- `decider(user, source, periode, cle, action, role, fingerprint, remarque, preparation)` :
  actions `pointer`, `remarque`, `correction` (remarque obligatoire), `preparer`
  (caissière prépare un rapprochement : solde de référence + justificatif + explication),
  `valider_mois` (directeur, seulement si tout est pointé niveau 3 sans correction).
- `roles_utilisateur(user)` : mappe le **poste** de l'employé (actif, non débauché, non
  visiteur) vers un rôle via `settings.POINTAGE_POSTES` :
  ```python
  POINTAGE_POSTES = {
      'caissiere':   ('Caissiere', 'Caissier'),
      'responsable': ('Responsable operationnel',),
      'directeur':   ('Directeur', 'Directrice', 'Directeur adjoint'),
  }
  ```
  Comparaison sans accent ni casse. Un superuser sans employé est en lecture seule.
- `verifier_source` : un `fichier_source` ne peut être pointé/validé que s'il relève
  **entièrement** du périmètre de l'utilisateur (un mois ne se valide pas à moitié).

## Vue / gabarit

- `apps/accounting/views_pointage.py` : contrat GET/POST, compteurs du **tableau de suivi
  mensuel** (bloqués / à corriger / attente caissière / attente responsable / attente
  directeur / validés), filtres `?filtre=`.
- `templates/accounting/pointage_mensuel.html` (étend `accounting/base.html`, DaisyUI) +
  `includes/pointage_fields.html` + `includes/pointage_suivi_carte.html`.

## Admin

`apps/accounting/admin.py` enregistre les 3 modèles en **lecture seule** (audit).

## Rapprochements

- **Solde de référence** (`journal:<code>`) : pré-rempli depuis la table `soldes_reels`
  (import Access « SoldesReels ») — match `fichier_source` + `journal` + `date_m` = 1er du
  mois de la période, `SUM(ccy)` (`solde_reel_reference()`). Le solde réel importé (fichier
  RAF validé) fait aussi office de **justificatif**.
- Si aucun solde réel n'est importé pour ce journal/mois → « Solde de référence à
  renseigner » ; la caissière saisit une valeur manuelle via « Préparer » (facultatif si
  l'import existe) et/ou joint un `DocumentationComptable` (types `comptage_caisse`,
  `releve_bancaire`, `recap_tiers`, `rapprochement_solde`, même fichier / même mois).
- **Comptes de tiers** (`tiers:<pers>`, issus de `00PERS`) : **pas de solde de référence
  externe**. Les trois niveaux valident directement que le **solde calculé** est correct
  (à partir de la liste des mouvements) — aucun blocage. Un tiers dont les mouvements du
  mois s'annulent (solde = 0) **n'est pas affiché**. Le libellé montre `Pers` + le nom
  résolu (`_noms_tiers()` : surnom d'employé ou idxls de fournisseur). La caissière peut
  ajouter une observation.
- **Compte clôturé** : si le solde comptable cumulé est nul **et** qu'aucun solde de
  référence n'existe (ni saisi, ni importé), le rapprochement n'est pas bloqué
  (`rien_a_rapprocher`) — « compte sans solde, rien à rapprocher ». Si le compte existe
  encore, le solde réel importé renseigne la référence et la comparaison reprend.
- Rapprochement bloqué tant que : solde de référence manquant (hors compte clôturé),
  justificatif manquant, ou écart non justifié. Réimporter un solde réel modifié invalide
  les visas (empreinte).
- Désync d'état de migration préexistante sur `InfoPaiementTaxeCommune` (migration `0030`
  en `SeparateDatabaseAndState`) : `makemigrations accounting` proposera toujours
  « Remove field annee » ; ne pas fusionner avec les migrations de pointage.
