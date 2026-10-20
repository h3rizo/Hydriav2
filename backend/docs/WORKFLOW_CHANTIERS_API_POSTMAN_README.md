# Workflow Chantiers API - Postman

Collection fournie:
- `backend/docs/WORKFLOW_CHANTIERS_API.postman_collection.json`

## Import dans Postman

1. Ouvrir Postman.
2. Importer le fichier JSON de collection.
3. Vérifier la variable `base_url` (par défaut `http://localhost:8000`).

## Variables à renseigner avant exécution

- `ouvrage_id`
- `type_equipement_citerne_id`
- `designation_id`
- `poste_main_oeuvre_id`
- `tacheron_id`
- `besoin_id` (un besoin existant du workflow)

Variables auto-remplies par les tests Postman:
- `workflow_id` (après `0. Create Workflow`)
- `contrat_document_id` (après `10. Create Contrat`)
- `avenant_document_id` (après `11. Create Avenant`)
- `facture_document_id` (après `12. Create Facture Tranche`)

## Ordre conseillé

1. `0` à `4` (création workflow + besoins)
2. `5` à `9` (surplus + devis)
3. `10` à `14` (contrat + suivi)
4. `15` à `23` (mouvements + récolement + devis final)

## Remarque

La collection ne gère pas l'authentification spécifique. Si votre environnement impose une session/auth, ajoutez les headers/cookies requis dans Postman.

## Script PowerShell automatisé

Script fourni:
- `backend/docs/run_workflow_chantiers_api.ps1`

Exemple d'exécution:

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\docs\run_workflow_chantiers_api.ps1 `
  -BaseUrl "http://localhost:8000" `
  -OuvrageId "<uuid>" `
  -TypeEquipementCiterneId "<uuid>" `
  -DesignationId "<uuid>" `
  -PosteMainOeuvreId "<uuid>" `
  -TacheronId "<uuid>"
```

`BesoinId` est optionnel: le script prend automatiquement le premier besoin du workflow créé.
