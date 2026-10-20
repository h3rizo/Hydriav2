# Workflow Chantiers: mapping Excel vers Django

Ce document décrit la première traduction des fichiers Excel:
- `source Dossier technique 2.xlsx`
- `Dossier technique V3.xlsm`

## 1) Tables existantes réutilisées

- `planning.Designation` (`designations`)
- `infrastructure.TypeEquipement` (`types_equipements`)
- `organization.Ouvrage` (`ouvrages`)
- `billing.TypePointEau` (`typepointeaus`)

## 2) Nouvelles tables ajoutées (app `chantiers`)

- `WorkflowModeleEquipement`
  - gabarit de calcul par `type_equipement` et optionnellement `type_point_eau`
- `WorkflowModeleEquipementLigne`
  - lignes de désignations et quantités (`fixe` ou `formule`)
- `CiterneParametrageReference`
  - paramètres fixes de calcul citerne
  - exemple: `epaisseur_blocage_m = 0.20`, `epaisseur_beton_arme_m = 0.10`
- `CiterneDimensionnement`
  - dimensions saisies/calculées (diamètre intérieur, extérieur, volume réel)
- `PosteMainOeuvre`
  - référentiel main d'oeuvre séparé des désignations matériaux
- `BaremeMainOeuvre`
  - coût MO par `type_equipement` + `type_point_eau`
- `ChantierWorkflow`
  - entité de pilotage global du chantier
- `ChantierSelectionEquipement`
  - sélection des équipements/points d'eau à construire
- `ChantierBesoinLigne`
  - besoins consolidés auto + surplus (désignations + MO)
- `ChantierSurplusLigne`
  - étape surplus saisie manuelle
- `ChantierDocument`
  - devis, contrat, avenant, facture de tranche, devis final
- `ChantierMouvement`
  - commande, livraison, utilisation, retour, récolement

## 3) Feuilles Excel et correspondances

- `Designations` -> `planning.Designation` (déjà existant)
- `Catalogue_ouvrages` / `Ouvrage` -> `WorkflowModeleEquipement` + `WorkflowModeleEquipementLigne`
- `dim citerne` / `Dimensionnement citerne` -> `CiterneParametrageReference` + `CiterneDimensionnement`
- `Catalogue_MO` / `listeMOPourContrat` -> `PosteMainOeuvre` + `BaremeMainOeuvre`
- `Liste supplementaire` -> `ChantierSurplusLigne`
- `Commande` -> `ChantierMouvement` (`type_mouvement=commande`)
- `Devis` -> `ChantierDocument` (`type_document=devis`) + lignes besoins
- `Contrat`, `DetailContrat`, `TranchesContrat`, `TotalContrat` -> `ChantierDocument` (`contrat`/`avenant`)
- `Facture`, `FactureSP` -> `ChantierDocument` (`facture_tranche`)

## 4) Génération automatique des besoins

La fonction `generer_besoins_chantier()` dans `apps/chantiers/models_workflow.py`:
- lit les sélections d'équipements du chantier,
- applique les lignes de modèles (`WorkflowModeleEquipementLigne`),
- applique les barèmes de main d'oeuvre (`BaremeMainOeuvre`),
- produit les lignes dans `ChantierBesoinLigne`,
- bascule le chantier au statut `besoins_generes`.

## 5) Itérations suivantes recommandées

1. Ajouter un importeur de catalogues depuis Excel (management command).
2. Ajouter les API/écrans pour:
   - sélection équipements + points d'eau,
   - génération automatique,
   - saisie surplus,
   - édition devis/contrat/avenants/factures.
3. Ajouter le flux de validation des documents (brouillon -> validé -> annulé).
4. Brancher les mouvements sur le module stock (`inventory`) pour synchronisation.

## 6) API minimale déjà disponible

Routes (`/chantiers/...`):

- `POST /api/workflows/create/`
  - body JSON: `{"code": "WF-2026-001", "ouvrage_id": "<uuid>", "caracteristique_chantier_id": "<uuid|null>", "notes": ""}`
- `GET /api/workflows/<workflow_id>/`
  - détail + stats du workflow
- `POST /api/workflows/<workflow_id>/selections/add/`
  - body JSON:
    - cas simple: `{"type_equipement_id":"<uuid>", "type_point_eau_id":"<uuid|null>", "quantite":1}`
    - cas citerne inline: ajouter `citerne_dimensionnement` avec `volume_cible_m3`, `diametre_interieur_m`, `hauteur_eau_m`
- `POST /api/workflows/<workflow_id>/generate-besoins/`
  - body JSON: `{"reset_auto": true}`
- `GET /api/workflows/<workflow_id>/besoins/`
  - query optionnelle: `?type_ligne=designation` ou `?type_ligne=main_oeuvre`
- `POST /api/workflows/<workflow_id>/surplus/add/`
  - body JSON:
    - désignation: `{"type_ligne":"designation","designation_id":"<uuid>","quantite":2,"prix_unitaire":1000,"justification":"..."}`
    - MO: `{"type_ligne":"main_oeuvre","poste_main_oeuvre_id":"<uuid>","quantite":1,"prix_unitaire":50000,"justification":"..."}`
- `GET /api/workflows/<workflow_id>/surplus/`
  - liste des surplus saisis
- `POST /api/workflows/<workflow_id>/surplus/integrate/`
  - body JSON: `{"reset_surplus": true}`
  - copie les surplus vers `ChantierBesoinLigne` avec `origine="surplus"`
- `POST /api/workflows/<workflow_id>/devis/generate/`
  - génère un document devis (`ChantierDocument`) et calcule le montant total depuis les besoins
- `GET /api/workflows/<workflow_id>/documents/?type_document=devis`
  - liste des documents du workflow (devis, contrat, avenant, facture tranche, devis final)


- `POST /api/workflows/<workflow_id>/contrat/create/`
  - body JSON: `{"numero":"CTR-...","tacheron_id":"<uuid>","montant":2000000,"date_document":"YYYY-MM-DD"}`
- `POST /api/workflows/<workflow_id>/avenant/create/`
  - body JSON: `{"numero":"AV-...","contrat_document_id":"<uuid>","montant":150000,"date_document":"YYYY-MM-DD"}`
- `POST /api/workflows/<workflow_id>/facture-tranche/create/`
  - body JSON: `{"numero":"FTR-...","parent_document_id":"<uuid_contrat_ou_avenant>","montant":700000,"date_document":"YYYY-MM-DD"}`
- `POST /api/workflows/<workflow_id>/documents/<document_id>/statut/`
  - body JSON: `{"statut":"brouillon|valide|annule"}`
- `GET /api/workflows/<workflow_id>/contrat/suivi/`
  - synth?se des montants contrat/avenants/factures et reste ? facturer.


- `POST /api/workflows/<workflow_id>/mouvements/add/`
  - body JSON: `{"besoin_id":"<uuid>","type_mouvement":"commande|livraison|utilisation|retour|recollement","quantite":1,"reference_document":"..."}`
- `GET /api/workflows/<workflow_id>/mouvements/`
  - liste des mouvements (filtre optionnel `?type_mouvement=`)
- `GET /api/workflows/<workflow_id>/recollement/synthese/`
  - synth?se quantit?s pr?vues/command?es/livr?es/utilis?es/retourn?es + valeur finale
- `POST /api/workflows/<workflow_id>/devis-final/generate/`
  - g?n?re le document `devis_final` ? partir des mouvements et besoins
