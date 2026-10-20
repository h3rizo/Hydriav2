# Manuel d'Utilisateur - Application Hydria

## 📋 Table des matières

1. [Introduction](#introduction)
2. [Connexion et Navigation](#connexion-et-navigation)
3. [Modules par Fonction](#modules-par-fonction)
4. [Workflows Détaillés](#workflows-détaillés)
5. [Rôles et Permissions](#rôles-et-permissions)
6. [FAQ et Dépannage](#faq-et-dépannage)

---

## 1. Introduction

### Qu'est-ce qu'Hydria ?

Hydria est une application web de gestion complète pour l'approvisionnement en eau potable à Madagascar. Elle permet de gérer :

- **Les infrastructures** : Ouvrages, points d'eau, équipements
- **La facturation** : Relevés, paiements forfaitaires et volumétriques
- **Les ressources humaines** : Employés, congés, paie, indemnités
- **La comptabilité** : Recoupement avec DiameX, vérifications
- **Les plannings** : Activités terrain, réparations, inspections
- **Les stocks** : Inventaire, mouvements, achats

### Qui utilise Hydria ?

- **Directeurs** : Vision globale, validations finales
- **Chefs de base** : Gestion des équipes, validations intermédiaires
- **Employés de terrain** : Saisie relevés, inspections, réparations
- **Comptables** : Vérifications comptables, recoupements DiameX
- **Gestionnaires RH** : Paie, congés, contrats
- **Clients/Usagers** : Consultation factures et consommation

---

## 2. Connexion et Navigation

### 2.1 Se connecter

1. Ouvrir votre navigateur web (Chrome, Firefox, Edge)
2. Aller sur l'URL fournie par votre administrateur
3. Saisir votre **nom d'utilisateur** et **mot de passe**
4. Cocher "Se souvenir de moi" si c'est votre ordinateur personnel
5. Cliquer sur **"Se connecter"**

**En cas d'oubli de mot de passe** : Contactez votre administrateur système

### 2.2 Interface principale

L'interface se compose de :

- **Barre de navigation** (haut) : Accès aux modules principaux
- **Menu hamburger** (mobile) : Version mobile de la navigation
- **Fil d'actualité** (page d'accueil) : Actualités et statistiques
- **Switch thème** : Basculer entre mode clair/sombre

### 2.3 Navigation par module

**Menu principal (Desktop)** :
- **Dashboard** : Statistiques globales
- **Recherche** : Rechercher ouvrages, points d'eau, parcelles
- **Facturation** : Relevés, paiements, recettes
- **Plannings** : Activités, congés, paie, réparations
- **Comptabilité** : Vérifications, recoupements DiameX
- **Inspections** : Analyses eau, inspections équipements
- **Référentiel** : Organisations, employés, fournisseurs, stocks
- **Système** : Administration, utilisateurs, logs

---

## 3. Modules par Fonction

### 3.1 MODULE FACTURATION

#### 3.1.1 Workflow Forfaitaire (Paiements Mensuels)

**Qui ?** Gestionnaire de base + Comptable

**Étapes** :

1. **Créer paiement forfaitaire**
   - Menu : Facturation > Paiements Forfaitaires > Nouveau
   - Remplir : Ouvrage, Mois/Année, Montant
   - Type : "Mensuel" ou "Prorata" si début/fin de mois
   - Enregistrer

2. **Marquer comme payé**
   - Trouver le paiement dans la liste
   - Clic "Marquer payé"
   - Saisir date de paiement
   - Le système génère automatiquement le numéro DiameX

3. **Exporter vers DiameX**
   - Les paiements marqués comme payés sont automatiquement exportés
   - Vérifier dans Comptabilité > Recoupement Forfaitaires

**Cas particuliers** :
- **Prorata** : Si un point d'eau démarre en milieu de mois
- **Suspension** : Ne pas créer de paiement pour les mois de suspension

#### 3.1.2 Workflow Volumétrique (Relevés)

**Qui ?** Agent terrain + Gestionnaire + Comptable

**Étapes** :

1. **Saisie relevé terrain** (Agent)
   - Menu : Facturation > Relevés > Workflow Relevés
   - Sélectionner ouvrage
   - Saisir nouvel index
   - Le système calcule automatiquement le volume consommé
   - Enregistrer

2. **Calcul facturation** (Gestionnaire)
   - Menu : Facturation > Workflow Facturation
   - Sélectionner ouvrage et mois
   - Clic "Calculer factures"
   - Vérifier montants calculés selon tarif volumétrique
   - Enregistrer

3. **Imprimer factures** (Gestionnaire)
   - Sélectionner les factures calculées
   - Clic "Imprimer"
   - ⚠️ **ATTENTION** : Une fois imprimées, les factures ne peuvent plus être recalculées
   - Le système enregistre automatiquement dans DiameX

**Informations affichées sur la facture** :
- Ancien index, Nouvel index, Volume consommé
- Détail par tranche tarifaire
- **Taxe communale 7%** (indicatif, NON ajouté au total)
- **Montant arrondi** à 100 Ar près (arrondi supérieur)
- **Impayés antérieurs** (2025+) affichés séparément en rouge

**Règles importantes** :
- Le mois de facturation = Mois suivant le relevé (Ex: Relevé mars → Facture avril)
- Les impayés ne sont PAS ajoutés au total à payer
- Arrondi automatique : 1,234 Ar → 1,300 Ar

#### 3.1.3 Workflow Indemnités PE (RBF/PPMH)

**Qui ?** Gestionnaire + Comptable

**Contexte** : Les indemnités RBF (Robinet à Boisseau Fermant) et PPMH (Pompe à Main Hydraulique) sont des paiements forfaitaires mensuels aux gestionnaires de points d'eau de type BF, PMH, PMHI.

**Étapes** :

1. **Consulter les paiements**
   - Menu : Comptabilité > Recoupement > Indemnités PE
   - Voir les paiements groupés par point d'eau
   - Filtrer par organisation, mois, commune

2. **Vérifier les anomalies**
   - Section "Dépassements 5000 Ar" : Montants supérieurs au plafond réglementaire
   - Section "Type PE Invalide" : Indemnités versées à des Kiosques/BP (NON ÉLIGIBLES)
   - Section "Non Extraites" : Descriptions non reconnues

3. **Gérer les anomalies**
   - **Dépassement** : Vérifier justification (plusieurs mois cumulés ?)
   - **Type invalide** : Demander explication à l'employé ayant saisi
   - **Non extrait** : Corriger la description dans DiameX

**Plafond réglementaire** : 5,000 Ar par tranche mensuelle

**Types éligibles uniquement** : BF, PMH, PMHI (PAS Kiosque, PAS BP)

### 3.2 MODULE PLANNINGS

#### 3.2.1 Workflow Congés

**Qui ?** Employé → Chef de base → Directeur

**Étapes** :

1. **Demander un congé** (Employé)
   - Menu : Plannings > Congés & Absences > Mes Congés
   - Clic "Nouvelle Demande"
   - Remplir : Type (Annuel/Maladie/Maternité), Date début, Date fin, Motif
   - Enregistrer
   - Statut : "En attente"

2. **Valider niveau 1** (Chef de base)
   - Menu : Plannings > Congés & Absences > Demandes en attente
   - Voir les demandes de son équipe
   - Clic "Valider (Chef)"
   - Statut : "Validé Chef"

3. **Valider niveau 2** (Directeur)
   - Menu : Plannings > Congés & Absences > Validation Directeur
   - Voir toutes les demandes validées chef
   - Clic "Valider (Directeur)"
   - Statut : "Validé Directeur"
   - ✅ **Inscription automatique au Planning**

**Soldes de congés** :
- Visible dans "Mes Congés" > Onglet "Solde"
- Mis à jour automatiquement après validation directeur

**Rejet** : Possible à tout niveau avec motif obligatoire

#### 3.2.2 Workflow Récupérations

**Qui ?** Gestionnaire → Chef → Directeur

**Contexte** : Quand un employé travaille un dimanche ou un jour férié, il acquiert un jour de récupération.

**Étapes** :

1. **Enregistrer récupération acquise** (Gestionnaire)
   - Menu : Plannings > Congés & Absences > Récupérations
   - Sélectionner employé
   - Le système affiche les dimanches/jours fériés travaillés (vérifiés dans Planning)
   - Sélectionner la date
   - Enregistrer
   - Statut : "Acquise"

2. **Demander utilisation** (Employé/Gestionnaire)
   - Trouver la récupération acquise
   - Clic "Demander"
   - Saisir date début et fin d'utilisation + motif
   - Statut : "Demandée"

3. **Validation** (Chef → Directeur)
   - Même workflow que les congés
   - Après validation directeur : Inscription automatique au Planning + Statut "Utilisée"

**⚠️ Règles importantes** :
- **Samedi NON récupérable** (repos hebdomadaire normal)
- **Dimanche récupérable** si travaillé
- **Jour férié récupérable** si travaillé

#### 3.2.3 Workflow Paie

**Qui ?** Gestionnaire RH + Comptable + Caissière

**Étapes** :

1. **Créer grille de salaire** (Gestionnaire RH)
   - Menu : Plannings > Paie > Grilles de Salaire
   - Sélectionner employé + mois/année
   - Le système calcule automatiquement :
     - Salaire de base (depuis contrat)
     - Primes (depuis poste)
     - Indemnités terrain (depuis plannings)
     - IRSA (1% si > 350,000 Ar)
     - CNaPS employé (1%)
     - Mutuelle santé (si adhérent)
   - Statut : "À traiter"

2. **Créer paiement** (Gestionnaire RH)
   - Dans la grille, clic "Créer Paiement"
   - Saisir date de paiement (généralement 1er du mois suivant)
   - Le système crée les paiements pour :
     - Salaire net
     - IRSA (si applicable)
     - CNaPS (cotisation employeur + employé)
     - FMFP
     - Mutuelle santé (si applicable)
   - Statut : "Payé"

3. **Imprimer fiches de paie** (Gestionnaire RH)
   - Menu : Plannings > Paie > Fiches de Paie Mensuelles
   - Filtrer par mois/année
   - Sélectionner les fiches à imprimer
   - Clic "Imprimer" (affiche message "2 exemplaires")
   - Confirmer après impression
   - ✅ **Export automatique vers DiameX** avec :
     - Description : `[Préfixe poste] [Nom complet]_Salaire_[Année] [Mois]`
     - Montant : Salaire net arrondi (100 Ar près, arrondi supérieur)
     - Compte : Compte salaire du poste

4. **Remettre fiches** (Caissière)
   - Imprimer en 2 exemplaires
   - Faire signer l'employé sur les 2 exemplaires
   - 1 exemplaire pour l'employé
   - 1 exemplaire pour le dossier

**Paiements CNaPS/FMFP** :
- Menu : Plannings > Paie > Paiements CNaPS/FMFP
- Générer facture Excel trimestrielle
- Télécharger pour envoi aux organismes

**Paiements Mutuelle Santé** :
- Menu : Plannings > Paie > Paiements Mutuelle Santé
- Générer factures AMIT et OSIEFSoVa
- Télécharger pour envoi

#### 3.2.4 Workflow Réparations

**Qui ?** Agent terrain → Gestionnaire → Validateur

**Étapes** :

1. **Signaler réparation** (Agent/Gestionnaire)
   - Menu : Plannings > Suivi & Contrôle > Réparations
   - Clic "Nouvelle Réparation"
   - Remplir : Ouvrage, Description, Priorité (Basse/Moyenne/Haute)
   - Optionnel : Nom usager, Contact, Coût estimé
   - Statut : "Signalée"

2. **Planifier** (Gestionnaire)
   - Trouver réparation signalée
   - Clic "Planifier"
   - Saisir date prévue + assigner agent
   - Statut : "Planifiée"

3. **Démarrer travaux** (Agent)
   - Dans la liste ou le Kanban
   - Clic "Démarrer"
   - Date de début enregistrée automatiquement
   - Statut : "En cours"

4. **Terminer travaux** (Agent)
   - Clic "Terminer"
   - Saisir compte-rendu + coût réel
   - Date de fin enregistrée
   - Statut : "Terminée"

5. **Valider** (Gestionnaire/Validateur)
   - Clic "Valider"
   - Saisir commentaire de validation (optionnel)
   - Statut : "Validée"

6. **Informer usager** (Optionnel, à tout moment)
   - Si nom usager renseigné
   - Clic "Informer usager"
   - Flag enregistré

**Vues disponibles** :
- **Liste** : Tableau avec filtres
- **Kanban** : Colonnes par statut (glisser-déposer non implémenté)

**Statistiques** : Total par statut affichées en haut

### 3.3 MODULE COMPTABILITÉ

#### 3.3.1 Workflow Import DiameX

**Qui ?** Comptable

**Étapes** :

1. **Exporter depuis DiameX**
   - Ouvrir DiameX (logiciel externe)
   - Exporter les bases souhaitées en Excel/CSV

2. **Importer dans Hydria**
   - Menu : Comptabilité > Import DiameX
   - Sélectionner fichier Excel
   - Sélectionner base DiameX (DATA, SoldesReels, etc.)
   - Clic "Importer"
   - Le système :
     - Lit les données ligne par ligne
     - Extrait ouvrage, point d'eau, mois selon patterns
     - Dédoublonne par clé (prog, id_access)
     - Stocke dans BaseDiameX

3. **Vérifier import**
   - Menu : Comptabilité > Vérification
   - Voir les lignes importées avec conformité de charte

**Champs clés** :
- `prog` : Code de la base DiameX
- `id_access` : Numéro unique de la ligne
- `date_rec` : Date d'enregistrement (utilisée pour filtrage)
- `compte_code` : Compte comptable (ex: 621102, 7011)

**⚠️ Important** : Utiliser `(prog, id_access)` comme clé unique (PAS seulement id_access)

#### 3.3.2 Workflow Vérification Comptabilité

**Qui ?** Comptable

**But** : Vérifier que les descriptions DiameX respectent les chartes définies

**Étapes** :

1. **Accéder à la vérification**
   - Menu : Comptabilité > Vérification > Avec Ouvrage (ou Sans Ouvrage)
   - "Avec Ouvrage" : Comptes nécessitant extraction d'ouvrage (621102, 7011...)
   - "Sans Ouvrage" : Comptes sans extraction nécessaire (employés, fournisseurs...)

2. **Filtrer les données**
   - Prog (base DiameX)
   - Compte comptable
   - Source (fichier importé)
   - Type (Entrée/Sortie)
   - Conformité (Conforme/Non conforme/Expliqué)
   - Statut Ouvrage (Sans ouvrage/Non trouvé/Trouvé)
   - Recherche textuelle

3. **Analyser les non-conformités**
   - **Badge rouge "Non conforme"** : Description ne respecte pas la charte
   - Clic sur "Modifier" pour corriger
   - Ou marquer comme "Expliqué" si justifié

4. **Ouvrir scans**
   - Clic sur bouton "Ouvrir" pour voir le justificatif scanné
   - S'ouvre dans la visionneuse Windows

**Statistiques affichées** :
- Total lignes
- Conformes (vert)
- Non conformes (rouge)
- Expliqués (bleu)
- Stats d'extraction ouvrage (si applicable)

#### 3.3.3 Workflow Recoupement

**Qui ?** Comptable

**But** : Vérifier la cohérence entre données Hydria et DiameX

**Types de recoupement** :

**A. Recoupement Forfaitaires**
- Menu : Comptabilité > Recoupement > Paiements Forfaitaires
- Compare `PaiementForfaitaire` (Hydria) ↔ `BaseDiameX` (compte 7011)
- Vérifie que tous les paiements marqués "payés" ont une ligne DiameX

**B. Recoupement Indemnités PE**
- Menu : Comptabilité > Recoupement > Indemnités PE
- Vérifie les paiements du compte 621102
- Détecte :
  - Dépassements du plafond 5000 Ar
  - Paiements sur types PE non éligibles (Kiosque, BP)
  - Lignes non extraites

**C. Recoupement Salaires**
- Menu : Comptabilité > Recoupement > Salaires
- Compare champs `numero_diamex_*` des salaires avec BaseDiameX
- Vérifie 5 types : Salaire, IRSA, CNaPS, FMFP, Santé

**D. Recoupement Intelligent**
- Menu : Comptabilité > Recoupement > Intelligent
- Recherche automatique de correspondances pour lignes DiameX orphelines
- Suggère des relevés candidats selon extraction ouvrage/mois

**Workflow type** :
1. Filtrer par mois/base/statut
2. Analyser les écarts (badge rouge si montant différent)
3. Corriger dans Hydria ou DiameX selon le cas
4. Re-vérifier après correction

### 3.4 MODULE INSPECTIONS

#### 3.4.1 Workflow Analyses d'Eau

**Qui ?** Agent laboratoire + Superviseur

**Contexte** : Les analyses d'eau sont groupées par **pack** (jour d'analyse). Chaque pack doit contenir :
- **Témoin positif** : Point d'eau traditionnel (doit contenir coliformes)
- **Témoin négatif** : Bouteille d'eau stérile (ne doit JAMAIS contenir coliformes)
- **Échantillons réels** : Points d'eau à analyser (ne doivent PAS contenir coliformes)

**Étapes** :

1. **Prélever échantillons terrain** (Agent)
   - Toujours prélever :
     - 1 témoin positif (eau traditionnelle)
     - 1 témoin négatif (bouteille stérile)
     - Les points d'eau à analyser
   - Noter date, heure, température

2. **Analyser en laboratoire** (Agent labo)
   - Compter coliformes pour chaque échantillon
   - Saisir dans Hydria :
     - Menu : Inspections > Analyses d'Eau
     - Importer depuis Excel OU saisir manuellement

3. **Valider le pack** (Superviseur)
   - Vérifier résultats :
     - ✅ **Témoin positif** : Doit avoir coliformes (valide le processus)
     - ✅ **Témoin négatif** : Ne doit PAS avoir coliformes
     - ⚠️ **Si témoin négatif contaminé** : TOUT le pack est invalide → Refaire analyses

4. **Statuts de pack** :
   - **❌ CONTAMINÉ** : Coliformes sur bouteille → Pack invalide
   - **⚠️ PROBLÉMATIQUE** : Coliformes sur équipement/PE → Contamination réelle
   - **✅ VALIDE** : Témoin positif OK + aucune contamination témoin négatif
   - **❓ INDÉTERMINÉ** : Pas de témoin positif → Processus non validé

**⚠️ RÈGLE CRITIQUE** : Un pack contaminé (bouteille avec coliformes) invalide TOUTES ses analyses, même celles qui semblaient problématiques.

#### 3.4.2 Workflow Inspections Équipements

**Qui ?** Agent terrain

**Étapes** :

1. **Accéder à l'inspection**
   - Menu : Inspections > Sélection Équipement
   - Sélectionner ouvrage

2. **Inspecter chaque point de contrôle**
   - Le système affiche tous les points de contrôle du type d'ouvrage
   - Pour chaque point :
     - **Booléen** : Cocher Conforme/Non conforme
     - **Quantité** : Saisir valeur (ex: niveau d'eau en cm)
     - **Photo** : Télécharger (optionnel)

3. **Gérer les non-conformités**
   - Si un point est "Non conforme"
   - Clic "Détailler la non-conformité"
   - Remplir modal :
     - Narratif du problème (description précise)
     - Solution détaillée
     - Matériaux nécessaires (liste dynamique)
     - Niveau solution (Mpikojakoja/ST/Social/Projet)
     - Priorité (Basse/Moyenne/Haute)
     - Échéance (Immédiat/3 mois/6 mois)
     - Coût estimé

4. **Génération automatique**
   - ✅ Une **ActionCorrective** est créée automatiquement
   - Priorité mappée : Basse→Basse, Moyenne→Normale, Haute→Urgente
   - Date prévue calculée : Immédiat→+7j, 3 mois→+90j, 6 mois→+180j

**Points de contrôle types** :
- État clôture
- Propreté aire de puisage
- Niveau d'eau
- État pompe
- Fuites visibles
- Système de drainage

### 3.5 MODULE RÉFÉRENTIEL

#### 3.5.1 Gestion Employés

**Qui ?** Gestionnaire RH

**Étapes** :

1. **Créer employé**
   - Menu : Référentiel > Ressources Humaines > Employés
   - Clic "Nouvel Employé"
   - Remplir : Nom, Prénom, CIN, Téléphone, Email
   - Sélectionner : Base, Poste
   - **Code Tiers** : 6 chiffres pour comptabilité en partie double (optionnel)
   - Enregistrer

2. **Créer contrat**
   - Dans la fiche employé
   - Onglet "Contrats" > Nouveau
   - Type : Journalier/Temps plein/Temps partiel/Mi-temps
   - Date début
   - Salaire de base
   - Enregistrer

3. **Affecter permissions**
   - Menu : Système > Gestion Utilisateurs
   - Créer compte utilisateur lié à l'employé
   - Définir permissions selon rôle

**Distinction Journalier/Salarié** :
- **Journalier** : Pas de repos/jours fériés automatiques
- **Salarié** : Repos Sam+Dim + jours fériés générés automatiquement

#### 3.5.2 Gestion Fournisseurs

**Qui ?** Gestionnaire achats

**Étapes** :

1. **Créer fournisseur**
   - Menu : Référentiel > Fournisseurs & Stocks > Fournisseurs
   - Clic "Nouveau Fournisseur"
   - Remplir :
     - Nom fournisseur (obligatoire)
     - Type : Personnel/Entreprise/Institution
     - **Code Tiers** : 6 chiffres (optionnel)
     - Contact, Téléphone, Email
     - NIF, STAT, CIN
   - Enregistrer

2. **Utiliser dans achats**
   - Lors de création d'achat, sélectionner fournisseur
   - Le code tiers est utilisé pour export comptable

**Statistiques affichées** :
- Total fournisseurs
- Actifs / Inactifs
- Avec code tiers renseigné

### 3.6 MODULE RECHERCHE

#### 3.6.1 Rechercher Ouvrage

**Qui ?** Tous utilisateurs

**Étapes** :

1. **Lancer recherche**
   - Menu : Recherche > Recherche Rapide
   - Saisir nom ouvrage (minimum 3 caractères)
   - Filtrer par : Type, District, Commune

2. **Voir résultats**
   - Liste avec photo, nom, type, localisation
   - Clic sur carte pour voir détails

3. **Détails ouvrage**
   - Onglets :
     - Informations : Caractéristiques techniques
     - Points d'eau : Liste des PE liés
     - Modalités gestion : Historique des gestionnaires
     - Équipements : Liste équipements constitutifs
     - Historique : Réparations, inspections

#### 3.6.2 Rechercher Point d'Eau

**Étapes** :

1. **Lancer recherche**
   - Menu : Recherche > Points d'Eau
   - Saisir nom ou code
   - Filtrer par : Type, Ouvrage, Village

2. **Détails point d'eau**
   - Informations générales
   - Tarif (forfaitaire ou volumétrique)
   - Historique relevés
   - **Factures impayées** (pour clients connectés)

---

## 4. Workflows Détaillés

### 4.1 Workflow Complet : Facturation Volumétrique d'un Ouvrage

**Acteurs** : Agent terrain, Gestionnaire, Comptable

**Durée** : 1 mois (du relevé à la comptabilisation)

```
┌─────────────────┐
│ 1. AGENT TERRAIN│
└────────┬────────┘
         │ Début du mois M+1 (ex: 05/04 pour mars)
         ▼
    Saisir relevé
    - Ouvrage : Ambanja BP
    - Date relevé : 31/03/2025
    - Nouvel index : 1250.5 m³
    - Ancien index : 1130.2 m³ (automatique)
    - Volume : 120.3 m³ (automatique)
         │
         ▼
    Enregistrer
    [Statut : Relevé enregistré]
         │
         │
┌────────▼─────────┐
│ 2. GESTIONNAIRE  │
└────────┬─────────┘
         │ Mi-mois M+1 (ex: 15/04)
         ▼
    Calculer factures
    - Menu : Workflow Facturation
    - Sélectionner Ambanja BP + Avril 2025
    - Clic "Calculer"
         │
         ▼
    Vérifier montant
    - Tranche 1 (0-10 m³) : 10 × 3,250 = 32,500 Ar
    - Tranche 2 (10-2000 m³) : 110.3 × 5,000 = 551,500 Ar
    - Total HT : 584,000 Ar
    - Arrondi : 584,000 Ar (déjà multiple de 100)
    - Taxe 7% : 40,880 Ar (indicatif, NON ajouté)
    - À PAYER : 584,000 Ar
         │
         ▼
    Enregistrer factures
    [Statut : Calculé, Montant = 584,000 Ar]
         │
         │
         ▼
    Imprimer factures
    - Sélectionner toutes les factures
    - Clic "Imprimer"
    - ⚠️ Confirmer (irréversible)
         │
         ▼
    [Statut : Imprimé]
    ✅ Export auto vers DiameX
         │
         │
┌────────▼─────────┐
│ 3. COMPTABLE     │
└────────┬─────────┘
         │ Fin du mois M+1 (ex: 30/04)
         ▼
    Vérifier recoupement
    - Menu : Recoupement Intelligent
    - Filtrer Avril 2025
    - Vérifier ligne DiameX créée :
      * Description : "Paiement_volume_Ambanja BP_2025 04"
      * Montant : 584,000 Ar
      * Compte : 7011
         │
         ▼
    Si écart détecté
    - Corriger dans Hydria OU DiameX
    - Re-calculer si pas encore imprimé
         │
         ▼
    ✅ Validation comptable
```

### 4.2 Workflow Complet : Congé Annuel d'un Employé

**Acteurs** : Employé, Chef de base, Directeur

**Durée** : 3-5 jours ouvrés

```
┌─────────────┐
│ 1. EMPLOYÉ  │
└──────┬──────┘
       │ Jour J
       ▼
  Demander congé
  - Menu : Mes Congés > Nouveau
  - Type : Congé annuel
  - Du 15/05 au 20/05 (6 jours)
  - Motif : "Voyage famille"
       │
       ▼
  Enregistrer
  [Statut : En attente]
  📧 Notification → Chef
       │
       │
┌──────▼──────┐
│ 2. CHEF BASE│
└──────┬──────┘
       │ Jour J+1
       ▼
  Consulter demande
  - Menu : Demandes en attente
  - Voir : Employé, Dates, Solde disponible
       │
       ▼
  Vérifier disponibilité
  - Solde : 15 jours disponibles ✓
  - Période chargée ? Non ✓
       │
       ▼
  Valider niveau 1
  - Clic "Valider (Chef)"
  [Statut : Validé Chef]
  📧 Notification → Directeur
       │
       │
┌──────▼────────┐
│ 3. DIRECTEUR  │
└──────┬────────┘
       │ Jour J+2
       ▼
  Consulter demande
  - Menu : Validation Directeur
  - Voir historique validation chef
       │
       ▼
  Valider niveau 2
  - Clic "Valider (Directeur)"
  [Statut : Validé Directeur]
       │
       ▼
  ✅ Inscription automatique Planning
  - Dates 15-20/05 → Activité "Congé"
  - Solde employé : 15 - 6 = 9 jours
       │
       ▼
  📧 Notification → Employé
  "Votre congé est validé"
```

### 4.3 Workflow Complet : Réparation d'un Ouvrage

**Acteurs** : Usager, Agent terrain, Gestionnaire, Validateur

**Durée** : Variable selon priorité

```
┌─────────────┐
│ 1. USAGER   │
└──────┬──────┘
       │
       ▼
  Signaler problème
  - Téléphone à l'agent
  - "Fuite au niveau du robinet"
       │
       │
┌──────▼────────┐
│ 2. AGENT      │
└──────┬────────┘
       │ Sur site
       ▼
  Constater problème
  - Fuite importante
  - Perte d'eau estimée : 50L/h
       │
       ▼
  Signaler dans Hydria
  - Menu : Réparations > Nouveau
  - Ouvrage : Ambanja BP
  - Description : "Fuite robinet principal - Joint usé - Perte ~50L/h"
  - Priorité : Haute
  - Nom usager : "Jean RAKOTO"
  - Contact : 034 12 345 67
  [Statut : Signalée]
       │
       │
┌──────▼─────────┐
│ 3. GESTIONNAIRE│
└──────┬─────────┘
       │ J+1
       ▼
  Consulter signalement
  - Vue Kanban ou Liste
  - Badge rouge "Priorité Haute"
       │
       ▼
  Planifier
  - Clic "Planifier"
  - Date prévue : Demain
  - Assigner : Agent RAZAKA
  [Statut : Planifiée]
  📧 Notification → Agent RAZAKA
       │
       │
┌──────▼────────┐
│ 4. AGENT      │
└──────┬────────┘
       │ J+2 (matin)
       ▼
  Démarrer travaux
  - Mobile : Voir réparation assignée
  - Clic "Démarrer"
  - Aller sur site avec matériel
  [Statut : En cours]
  [Date début : 08h00]
       │
       ▼
  Réparer
  - Démonter robinet
  - Remplacer joint
  - Tester étanchéité
       │
       ▼
  Terminer
  - Clic "Terminer"
  - Compte-rendu : "Joint remplacé. Robinet étanche. Testé OK."
  - Coût réel : 15,000 Ar (joint + déplacement)
  [Statut : Terminée]
  [Date fin : 10h30]
       │
       │
┌──────▼─────────┐
│ 5. GESTIONNAIRE│
└──────┬─────────┘
       │ J+2 (après-midi)
       ▼
  Valider
  - Consulter compte-rendu
  - Vérifier coût réel vs estimé
  - Clic "Valider"
  - Commentaire : "Intervention rapide et efficace"
  [Statut : Validée]
       │
       ▼
  Informer usager
  - Clic "Informer usager"
  - Téléphone à Jean RAKOTO
  - "Réparation terminée"
  [Flag : Usager informé]
       │
       ▼
  ✅ Réparation clôturée
  - Historique complet enregistré
  - Visible dans détails ouvrage
```

### 4.4 Workflow Automatique : Repos et Jours Fériés

**Acteurs** : Système (automatique) + Gestionnaire (annulations)

**Fréquence** : Hebdomadaire (repos) + Annuelle (jours fériés)

```
┌──────────────────────┐
│ SYSTÈME (AUTOMATIQUE)│
└──────────┬───────────┘
           │ Tous les lundis à 6h
           ▼
    Commande : populate_repos_weekly
    - Générer Sam+Dim pour les 4 prochaines semaines
    - Pour TOUS les salariés (temps plein, temps partiel, mi-temps)
    - ❌ EXCLURE les journaliers
           │
           ▼
    Créer Planning
    - Activité : "Repos"
    - Validé : True
    - Pour chaque employé salarié :
      * Samedi 10/05/2025
      * Dimanche 11/05/2025
      * Samedi 17/05/2025
      * Dimanche 18/05/2025
      * ... (4 semaines)
           │
           │
┌──────────▼───────────┐
│ GESTIONNAIRE         │
└──────────┬───────────┘
           │ Si besoin d'annuler (ex: dimanche travaillé)
           ▼
    Annuler repos dimanche
    - Menu : Planning > Liste ou Calendrier
    - Trouver Planning "Repos" du 11/05
    - Clic "Annuler"
    - Confirmer : "Ce dimanche sera travaillé ?"
           │
           ▼
    ✅ Planning supprimé
    ✅ Récupération créée automatiquement
    - Date : 11/05/2025
    - Statut : "Acquise"
    - Employé peut la demander plus tard
           │
           │ Si besoin d'annuler samedi (rare)
           ▼
    Annuler repos samedi
    - Même workflow
    - ❌ AUCUNE récupération créée (samedi non récupérable)
           │
           │
           │ 1er janvier de chaque année
           ▼
    Commande : populate_jours_feries
    - Générer tous les jours fériés de l'année
    - 01/01, Lundi de Pâques, 01/05, 26/06, 15/08, 01/11, 25/12...
    - Pour TOUS les salariés
    - ❌ EXCLURE les journaliers
           │
           ▼
    Créer Planning
    - Activité : "Jour férié"
    - Validé : True
           │
           │ Si jour férié travaillé
           ▼
    Annuler jour férié
    - Même workflow que dimanche
    - ✅ Récupération créée automatiquement
```

**⚠️ Règles importantes** :
- **Samedi annulé** = PAS de récupération
- **Dimanche annulé** = Récupération automatique
- **Jour férié annulé** = Récupération automatique
- **Journaliers** = AUCUN repos/férié automatique (gestion manuelle)

---

## 5. Rôles et Permissions

### 5.1 Matrice des Rôles

| Fonction | Directeur | Chef Base | Gestionnaire | Agent Terrain | Comptable | Client |
|----------|-----------|-----------|--------------|---------------|-----------|--------|
| **Dashboard** | ✅ Tout | ✅ Sa base | ✅ Sa base | ❌ | ✅ Global | ❌ |
| **Facturation** |||||||
| - Saisir relevés | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| - Calculer factures | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| - Imprimer factures | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| - Voir ses factures | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Plannings** |||||||
| - Demander congé | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| - Valider congé (Chef) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| - Valider congé (Directeur) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| - Gérer paie | ✅ | ❌ | ✅ RH | ❌ | ❌ | ❌ |
| - Créer réparation | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Comptabilité** |||||||
| - Import DiameX | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| - Vérifications | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| - Recoupements | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Inspections** |||||||
| - Analyses eau | ✅ | ✅ | ✅ | ✅ Saisie | ❌ | ❌ |
| - Inspections équip | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Référentiel** |||||||
| - Gérer employés | ✅ | ❌ | ✅ RH | ❌ | ❌ | ❌ |
| - Gérer fournisseurs | ✅ | ❌ | ✅ Achats | ❌ | ❌ | ❌ |
| - Gérer stocks | ✅ | ✅ | ✅ | ✅ Consult | ❌ | ❌ |
| **Système** |||||||
| - Gérer utilisateurs | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| - Config système | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 5.2 Profils Types

#### Directeur Général
**Accès** : Complet sur toutes les bases

**Responsabilités** :
- Validation finale des congés
- Supervision comptabilité
- Décisions stratégiques
- Gestion des utilisateurs

**Workflow quotidien** :
1. Consulter dashboard global
2. Valider demandes de congés
3. Vérifier statistiques financières
4. Consulter rapports d'anomalies

#### Chef de Base
**Accès** : Limité à sa base géographique

**Responsabilités** :
- Validation niveau 1 des congés de son équipe
- Suivi des réparations
- Supervision terrain
- Validation des relevés

**Workflow quotidien** :
1. Consulter dashboard de sa base
2. Valider congés de l'équipe
3. Planifier réparations signalées
4. Vérifier relevés saisis

#### Gestionnaire RH
**Accès** : Module paie, employés, congés

**Responsabilités** :
- Création grilles de salaire
- Génération fiches de paie
- Gestion contrats
- Export CNaPS/FMFP

**Workflow mensuel** :
1. Créer grilles de salaire (J-5 du mois)
2. Vérifier indemnités terrain importées
3. Créer paiements
4. Imprimer fiches de paie
5. Générer factures organismes (trimestriel)

#### Agent Terrain
**Accès** : Saisie relevés, inspections, signalement réparations

**Responsabilités** :
- Relevés mensuels
- Inspections équipements
- Signalement pannes
- Réalisation réparations

**Workflow type journée terrain** :
1. Consulter plannings du jour
2. Se déplacer vers ouvrage
3. Saisir relevés
4. Inspecter équipements
5. Signaler anomalies
6. Mettre à jour réparations en cours

#### Comptable
**Accès** : Module comptabilité, vérifications, recoupements

**Responsabilités** :
- Import données DiameX
- Vérifications conformité
- Recoupements Hydria ↔ DiameX
- Correction anomalies

**Workflow mensuel** :
1. Importer fichiers DiameX (début du mois)
2. Vérifier conformité des descriptions
3. Recouper paiements forfaitaires
4. Recouper salaires
5. Recouper indemnités PE
6. Signaler anomalies aux gestionnaires

#### Client/Usager
**Accès** : Consultation de son point d'eau uniquement

**Responsabilités** :
- Consulter sa consommation
- Voir ses factures
- Voir ses impayés

**Utilisation** :
1. Se connecter avec son compte
2. Voir détails de son point d'eau
3. Consulter historique relevés
4. Voir montant impayés (alerte rouge)
5. Contacter gestionnaire si besoin

---

## 6. FAQ et Dépannage

### 6.1 Questions Fréquentes

**Q1 : Je ne vois pas certains menus, pourquoi ?**

R : Vous n'avez peut-être pas les permissions nécessaires. Contactez votre administrateur pour vérifier vos droits d'accès.

---

**Q2 : Puis-je modifier une facture déjà imprimée ?**

R : ❌ **NON**. Une fois qu'une facture volumétrique est imprimée, elle ne peut plus être recalculée ni modifiée. C'est une sécurité pour garantir la traçabilité comptable. Si vous devez corriger, il faut créer un avoir ou une note de crédit.

---

**Q3 : Pourquoi mon congé n'apparaît pas dans le planning ?**

R : Le congé n'apparaît dans le planning qu'après validation par le **Directeur** (validation niveau 2). Si votre congé est seulement "Validé Chef", attendez la validation directeur.

---

**Q4 : Comment savoir si un employé est journalier ou salarié ?**

R : Dans la fiche employé > Onglet Contrats > Type de contrat :
- **Journalier** = Type "Journalier"
- **Salarié** = Type "Temps plein", "Temps partiel" ou "Mi-temps"

---

**Q5 : Quelle est la différence entre "Impayés" et "Montant à payer" sur une facture ?**

R :
- **Montant à payer** : Ce que le client doit payer AUJOURD'HUI (encadré noir)
- **Impayés** : Dettes des mois précédents (encadré rouge pointillé, informatif uniquement, NON ajouté au total)

---

**Q6 : Pourquoi certaines indemnités PE sont dans "Type PE Invalide" ?**

R : Les indemnités RBF/PPMH ne concernent que les points d'eau de type **BF, PMH, PMHI**. Si une indemnité a été versée à un Kiosque ou une Borne Publique (BP), c'est une anomalie qui nécessite une explication de l'employé ayant saisi.

---

**Q7 : Comment annuler un repos ou un jour férié ?**

R : Dans le planning (Liste ou Calendrier), trouver le planning "Repos" ou "Jour férié", clic "Annuler", confirmer.
- Si c'est un **dimanche** ou **jour férié** : Une récupération est créée automatiquement
- Si c'est un **samedi** : Aucune récupération (samedi non récupérable)

---

**Q8 : Que signifie "Pack CONTAMINÉ" dans les analyses d'eau ?**

R : Cela signifie que le **témoin négatif** (bouteille d'eau stérile) contenait des coliformes. Tout le pack d'analyses de ce jour est **invalide** et doit être refait avec du matériel stérile neuf.

---

**Q9 : Puis-je créer plusieurs paiements forfaitaires pour le même ouvrage le même mois ?**

R : Oui, par exemple si vous avez plusieurs points d'eau à des tarifs différents. Mais généralement, il y a **un seul paiement par ouvrage par mois**.

---

**Q10 : Comment retrouver le scan d'une pièce comptable ?**

R : Dans Comptabilité > Vérification, le bouton "Ouvrir" à droite de chaque ligne ouvre le scan dans la visionneuse Windows (si le chemin est correct).

---

### 6.2 Problèmes Courants

#### Problème 1 : Import Excel échoue

**Symptômes** : Message d'erreur lors de l'import DiameX

**Causes possibles** :
1. Format de fichier incorrect (doit être .xlsx)
2. Colonnes manquantes ou mal nommées
3. Dates dans un format non reconnu

**Solutions** :
1. Vérifier que c'est bien un fichier Excel (.xlsx)
2. Comparer avec le template fourni
3. Vérifier que les colonnes obligatoires sont présentes : prog, id_access, date_rec, compte_code, description
4. Formater les dates en DD/MM/YYYY ou YYYY-MM-DD

---

#### Problème 2 : Scan ne s'ouvre pas

**Symptômes** : Clic sur "Ouvrir" mais rien ne se passe

**Causes possibles** :
1. Chemin du fichier incorrect
2. Fichier déplacé ou supprimé
3. Permissions Windows insuffisantes

**Solutions** :
1. Vérifier que le chemin dans `chemin_base` est correct
2. Vérifier que le fichier existe à l'emplacement indiqué
3. Contacter l'administrateur système pour les permissions

---

#### Problème 3 : Statistiques dashboard à zéro

**Symptômes** : Dashboard affiche 0 partout

**Causes possibles** :
1. Aucune donnée importée
2. Filtres trop restrictifs
3. Permissions limitées à une organisation sans données

**Solutions** :
1. Vérifier qu'il y a des données dans les modules (ouvrages, points d'eau, relevés)
2. Réinitialiser les filtres (bouton "Réinitialiser")
3. Contacter administrateur pour vérifier permissions

---

#### Problème 4 : Relevé enregistré mais volume à zéro

**Symptômes** : Relevé saisi mais volume = 0 m³

**Causes possibles** :
1. Même index que le relevé précédent
2. Nouvel index < ancien index
3. Relevé précédent non trouvé

**Solutions** :
1. Vérifier que le nouvel index est bien supérieur à l'ancien
2. Si compteur remis à zéro, ajouter une note explicative
3. Contacter gestionnaire si c'est anormal

---

#### Problème 5 : Facture avec montant bizarre

**Symptômes** : Montant facturé ne correspond pas au volume

**Causes possibles** :
1. Tarif volumétrique incorrect
2. Volume non facturé mal calculé
3. Minimum de facturation non respecté

**Solutions** :
1. Vérifier le tarif volumétrique de l'ouvrage (Menu Référentiel > Ouvrages)
2. Vérifier le volume non facturé (ex: carte sociale)
3. Vérifier le minimum de facturation (ex: minimum 8 m³)
4. Clic "Voir détails" pour voir le calcul détaillé par tranche

---

#### Problème 6 : Congé refusé après validation chef

**Symptômes** : Congé validé par le chef mais refusé par le directeur

**Cause** : Le directeur a jugé que le congé ne pouvait pas être accordé (période chargée, solde insuffisant mal vérifié, etc.)

**Solution** :
1. Consulter le motif de refus (affiché dans la demande)
2. Contacter le directeur pour explications
3. Créer une nouvelle demande avec d'autres dates si possible

---

#### Problème 7 : Récupération non créée après annulation dimanche

**Symptômes** : Dimanche annulé mais pas de récupération dans la liste

**Causes possibles** :
1. L'employé est journalier (pas de récupérations)
2. Bug système

**Solutions** :
1. Vérifier type de contrat (Menu Employés > Contrats)
2. Si salarié et pas de récupération, contacter administrateur
3. Créer récupération manuellement si besoin

---

### 6.3 Contacts Support

**Support Technique** :
- Email : support@hydria.mg
- Téléphone : +261 XX XX XXX XX
- Heures : Lundi-Vendredi 8h-17h

**Support Comptabilité** :
- Email : compta@hydria.mg
- Pour questions DiameX, recoupements

**Support RH/Paie** :
- Email : rh@hydria.mg
- Pour questions congés, salaires, contrats

**Urgences Terrain** :
- Téléphone : +261 XX XX XXX XX (24/7)
- Pour pannes critiques, contaminations eau

---

## Annexes

### A. Glossaire

- **BF** : Borne Fontaine
- **BP** : Borne Publique
- **CNaPS** : Caisse Nationale de Prévoyance Sociale
- **DiameX** : Logiciel de comptabilité externe
- **FMFP** : Fonds de Maternité et de Formation Professionnelle
- **IDxls** : Numéro unique du point d'eau dans l'ouvrage
- **IRSA** : Impôt sur les Revenus Salariaux et Assimilés
- **Pack** : Groupe d'analyses d'eau réalisées le même jour
- **PE** : Point d'Eau
- **PMH** : Pompe à Main Hydraulique
- **PMHI** : Pompe à Main Hydraulique Indienne
- **Prorata** : Paiement proportionnel (début/fin de mois)
- **RBF** : Robinet à Boisseau Fermant (indemnité)
- **PPMH** : Pompe à Main Hydraulique (indemnité)

### B. Raccourcis Clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl + K` | Recherche rapide |
| `Ctrl + S` | Sauvegarder (formulaires) |
| `Échap` | Fermer modal |
| `Tab` | Passer au champ suivant |
| `Shift + Tab` | Passer au champ précédent |

### C. Codes de Statut

**Congés** :
- `en_attente` : En attente validation chef
- `validee_chef` : Validé par le chef, attente directeur
- `validee_directeur` : Validé définitif, inscrit au planning
- `rejete` : Rejeté (voir motif)

**Réparations** :
- `signalee` : Signalée, pas encore planifiée
- `planifiee` : Planifiée avec date et agent
- `en_cours` : Travaux en cours
- `terminee` : Travaux terminés, attente validation
- `validee` : Validée définitivement

**Paiements** :
- `brouillon` : En cours de création
- `valide` : Validé, prêt pour export
- `paye` : Payé et exporté vers DiameX

**Analyses Eau (Pack)** :
- `contamine` : Témoin négatif contaminé → Pack invalide
- `problematique` : Contamination PE/équipement
- `valide` : Témoin positif OK + aucune contamination témoin négatif
- `indetermine` : Pas de témoin positif

### D. Formats de Date

**Affichage** : DD/MM/YYYY (ex: 15/04/2025)

**Import Excel** : DD/MM/YYYY ou YYYY-MM-DD

**Export** : YYYY-MM-DD (format ISO)

**Timezone** : Indian/Antananarivo (UTC+3)

---

**Version** : 1.0
**Dernière mise à jour** : 26 décembre 2025
**Auteur** : Herizo
