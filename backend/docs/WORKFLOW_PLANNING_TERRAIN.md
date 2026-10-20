# Workflow Planning Terrain

## Objectif

Visualiser clairement :
- qui fait quoi
- quelle est la suite si tout est conforme
- quelle est la suite si ce n'est pas conforme
- si l'action se fait dans l'application ou sur papier

## Legende

- `Bleu` : Employe
- `Vert` : Superieur
- `Violet` : Caissiere
- `Gris` : Systeme / etat final
- `Jaune` : Decision

## Repartition des roles

### Employe
- Saisie du planning previsionnel
- Correction si demandee
- Execution terrain
- Annotation du planning imprime au retour
- Explication des ecarts entre prevu et realise
- Mise a jour finale du planning dans l'application

### Superieur
- Validation avant depart
- Refus ou demande de correction si le planning n'est pas conforme
- Controle du retour terrain
- Validation finale du retour et de la cloture

### Caissiere
- Preparation des avances
- Preparation des bons de livraison
- Impression des factures
- Impression du recap de recette au depart
- Controle du retour financier et des pieces

## Supports utilises

### Application
- Saisie du planning
- Validation par le superieur
- Preparation avances / bons / factures / recap
- Controle retour
- Mise a jour finale du planning

### Papier
- Planning imprime de depart
- Factures imprimees
- Recap de recette imprime
- Planning annote au retour
- Transmission physique des pieces et justificatifs

## Workflow detaille

1. `Employe` saisit le planning previsionnel dans l'application.
2. `Superieur` relit le planning.
3. Si le planning n'est pas conforme :
   - retour a l'employe pour correction dans l'application
   - nouvelle soumission au superieur
4. Si le planning est conforme :
   - validation par le superieur dans l'application
   - impression du planning de depart
5. `Caissiere` prepare dans l'application :
   - avances
   - bons de livraison
   - factures
   - recap de recette
6. `Caissiere` imprime les documents de depart.
7. `Employe` part sur le terrain avec les documents papier.
8. Au retour, `Employe` :
   - coche / annote le planning imprime
   - explique les ecarts entre prevu et realise
   - transmet le planning imprime et les pieces a la caissiere et au superieur
9. `Caissiere` controle le retour financier et documentaire.
10. Si les pieces ou montants ne sont pas conformes :
   - retour a l'employe pour complement ou explication
11. Si le retour financier est conforme :
   - enregistrement / controle du retour par la caissiere dans l'application
12. `Superieur` controle le retour operationnel.
13. Si les ecarts ne sont pas justifies :
   - retour a l'employe pour mise a jour du planning et justification
14. Si les ecarts sont justifies :
   - validation finale par le superieur
15. Le planning est cloture et mis a jour dans l'application.

## Diagramme Mermaid

```mermaid
flowchart TD
    SAISIE["Employe<br/>[APP] Saisie du planning previsionnel"]
    SAISIE2["Superieur<br/>[APP] traite les suites à donner de réparation dans les réunions bilans"]
    SAISIE3["Employe<br/>[PAPIER] écrit les demandes de transfert avec les fiches de stock pour justifier les soldes dans les stocks"]
    VALIDATION{"Superieur<br/>Planning conforme ?"}
    VALIDATION2{"Superieur<br/>Demande conforme ?"}
    CORRECTION["Employe<br/>[APP] Corrige puis resoumet"]
    VALIDATION3["Superieur<br/>[APP] Valide le planning"]
    IMPRESSION["Employé<br/>[APP -> PAPIER] Impression du planning valide"]
    PREPARATION["Caissiere<br/>[APP] Prepare avances, bons de livraison, factures et recap recette"]
    BONTRANSFERT["Caissière<br/>[APP] Rédige et imprime les bons de transfert"]
    EXECUTION["Employe<br/>[PAPIER / TERRAIN] Execute les activites"]
    EXECUTION2["Employe<br/>[PAPIER] Coche le planning imprime, note les ecarts et les explications"]
    EXECUTION3["Employe<br/>[PAPIER] Tient des fiches de stock et fait des bon de livraison pour les pièces utilisées"]
    COMPTERENDU["Transmission<br/>[PAPIER + justificatifs] Vers caissiere et superieur"]
    COMPTERENDU2{"Caissiere<br/>Retour des factures et du reste de l'argent"}
    COMPTERENDU3{"Caissiere<br/>Retour des fiches de stock, bons de livraison, pièces abimé et autres preuves d'utilisation"}
    COMPTERENDU4["Employe<br/>[APP / PAPIER] Complete ou justifie les ecarts financiers"]
    COMPTERENDU5["Caissiere<br/>[APP] Controle et enregistre le retour financier"]
    COMPTERENDU6{"Superieur<br/>Ecarts operationnels justifies ?"}
    MISAJOURPLANNING["Employe<br/>[APP] Met a jour le planning et complete les justifications"]
    MISAJOURPLANNING2["Superieur<br/>[APP] Valide le retour et marque comme terminé"]
    MISAJOURPLANNING3["Employe<br/>[APP] Saisie dans le planning les pièces utilisées"]

    SAISIE --> VALIDATION
    SAISIE2 --> VALIDATION3
    VALIDATION3 --> BONTRANSFERT
    BONTRANSFERT --> EXECUTION3
    SAISIE3 --> VALIDATION2
    VALIDATION -- "Non" --> CORRECTION
    CORRECTION --> VALIDATION
    VALIDATION -- "Oui" --> VALIDATION3
    VALIDATION3 --> IMPRESSION
    IMPRESSION --> PREPARATION
    PREPARATION --> EXECUTION
    EXECUTION --> EXECUTION2
    EXECUTION2 --> COMPTERENDU
    COMPTERENDU --> COMPTERENDU2
    EXECUTION3 --> COMPTERENDU3
    COMPTERENDU2 -- "Non" --> COMPTERENDU4
    COMPTERENDU2 -- "Oui" --> COMPTERENDU5
    COMPTERENDU5 --> COMPTERENDU6
    COMPTERENDU6 -- "Non" --> MISAJOURPLANNING
    COMPTERENDU6 -- "Oui" --> MISAJOURPLANNING2
    COMPTERENDU3 --> MISAJOURPLANNING3


    classDef employe fill:#dbeafe,stroke:#1d4ed8,color:#0f172a,stroke-width:1.5px;
    classDef superieur fill:#dcfce7,stroke:#15803d,color:#0f172a,stroke-width:1.5px;
    classDef caissiere fill:#f3e8ff,stroke:#7e22ce,color:#0f172a,stroke-width:1.5px;
    classDef systeme fill:#e5e7eb,stroke:#4b5563,color:#111827,stroke-width:1.5px;
    classDef decision fill:#fef3c7,stroke:#d97706,color:#111827,stroke-width:1.5px;

    class SAISIE,SAISIE3,CORRECTION,IMPRESSION,EXECUTION, EXECUTION2, EXECUTION3, COMPTERENDU, COMPTERENDU4, MISAJOURPLANNING, MISAJOURPLANNING3 employe;
    class SAISIE2,VALIDATION,VALIDATION2,VALIDATION3, COMPTERENDU6, MISAJOURPLANNING2 superieur;
    class PREPARATION,BONTRANSFERT,COMPTERENDU2,COMPTERENDU3, COMPTERENDU5 caissiere;
```

## Version tres courte pour affichage mural

- `Employe` saisit le planning dans l'application
- `Superieur` valide ou retourne pour correction
- `Caissiere` prepare et imprime les documents de depart
- `Employe` execute et annote le planning imprime au retour
- `Caissiere` controle les pieces et les montants
- `Superieur` controle les ecarts et cloture

## Suite possible

Ce workflow peut etre decliné ensuite en 3 formats :
- une page de documentation interne
- un schema imprime A3 / A4 pour les bureaux
- une page applicative interactive avec filtres par role
