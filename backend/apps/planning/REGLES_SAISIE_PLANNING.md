# Règles de Saisie Planning - Hydria

## 📋 Vue d'ensemble
Document définissant les règles métier pour la saisie des plannings dans l'application Hydria.

## 🔐 Règles de Validation

### **Validation par Niveau d'Autorisation (≥ 3)**
- **Principe :** Seuls les utilisateurs de niveau 3 et plus peuvent valider les plannings
- **Implémentation :** 
  - Vérification du niveau utilisateur avant affichage du bouton "Valider"
  - Contrôle côté serveur lors de la soumission
  - Message d'erreur si niveau insuffisant

```python
# Exemple de logique de validation
if user.niveau_autorisation >= 3:
    planning.estvalide = True
    planning.save()
else:
    raise PermissionDenied("Niveau d'autorisation insuffisant pour valider")
```

### **Niveaux d'Autorisation**
- **Niveau 1 :** Saisie uniquement
- **Niveau 2 :** Saisie + Modification
- **Niveau 3 :** Saisie + Modification + Validation
- **Niveau 4+ :** Tous droits + Administration

## 🧮 Calculs Automatiques

### **Calculs lors de la Saisie**
1. **Calcul des indemnités** basé sur :
   - Type d'activité
   - Durée de l'intervention
   - Base/localisation
   - Barème en vigueur

2. **Calcul des coûts** :
   - Coût matériel
   - Coût main d'œuvre
   - Frais de déplacement
   - Total automatique

3. **Validation des données** :
   - Vérification des dates
   - Contrôle de cohérence employé/base
   - Validation des montants

### **Règles de Calcul Spécifiques**
```python
# Exemple de calcul d'indemnité
def calculer_indemnite(activite, duree, base):
    tarif_base = TARIFS_INDEMNITES[activite.type]
    coefficient_base = COEFFICIENTS_BASES[base.zone]
    return tarif_base * duree * coefficient_base
```

## 📦 Workflow de Saisie Planning

### **Vue d'ensemble du Workflow**

Le système de planning utilise un workflow conditionnel basé sur le type d'activité :

```
┌─────────────────────┬──────────────────────┬───────────────────┐
│  Réparation/        │   MP/Bilan/          │   Repos/          │
│  Livraison          │   Relève             │   Congé           │
└─────────┬───────────┴──────────┬───────────┴─────────┬─────────┘
          │                      │                     │
          ▼                      ▼                     ▼
    ┌──────────────┐      ┌──────────────┐    ┌──────────────┐
    │   Saisir     │      │   Saisir     │    │ Pas de       │
    │ Désignation  │      │  Ouvrage     │    │ détails      │
    │ + Quantité   │      │              │    │ requis       │
    └──────┬───────┘      └──────────────┘    └──────────────┘
           │
           ▼
    ┌──────────────────┐
    │ Type de          │
    │ désignation?     │
    └─────┬──────┬─────┘
          │      │
    ┌─────▼──┐ ┌▼────────┐
    │ Avance │ │Bon      │
    │        │ │Livraison│
    └────┬───┘ └───┬─────┘
         │         │
         ▼         ▼
    ┌────────────────────┐
    │Prix unitaire       │
    │auto-rempli         │
    └────┬───────┬────────┘
         │       │
    ┌────▼───┐ ┌▼─────────────┐
    │Avance: │ │Bon Livraison:│
    │Prix    │ │Prix + Magasin│
    │unitaire│ │+ Acheteur    │
    └────────┘ └──────────────┘
```

### **Type 1 : Réparation/Livraison**

**Étape 1 : Saisir Désignation + Quantité**
- Interface : Sélection de la désignation depuis la liste
- Champs requis : `designation`, `quantite`
- Déclencheur : Affichage du choix "Type de désignation"

**Étape 2 : Type de désignation ?**

#### **2A. Si Avance :**
- **Table** : `planning_details`
- **Identification** : `numero_bon_avance` (généré automatiquement)
- **Champs saisis** :
  - Prix unitaire (auto-rempli depuis `Designation.prix_unitaire`)
  - Montant = quantité × prix unitaire
- **Champs optionnels** : `baseDiameX`, `numeroDiameX` (pour traçabilité)
- **Workflow** : Création → Export DiameX → Retour Caissière

#### **2B. Si Bon de livraison :**
- **Table** : `bons_livraison` (table séparée)
- **Relation** : ForeignKey vers `Planning`
- **Champs saisis** :
  - Prix unitaire (auto-rempli depuis `Designation.prix_unitaire`)
  - Magasin (où récupérer le matériel)
  - Acheteur (employé responsable de l'achat)
- **Champs conditionnels** :
  - `point_eau` : Si livraison vers un point d'eau
  - `equipement` : Si livraison vers un équipement constitutif
- **Impact** : Mise à jour automatique des stocks (module Inventory)
- **Traçabilité** : `numero_bon` généré automatiquement

### **Type 2 : MP/Bilan/Relève**

**Workflow simplifié :**
- **Étape unique** : Saisir Ouvrage
- **Champs requis** : `ouvrage`
- **Pas de PlanningDetail** : Pas de désignation, pas de quantité
- **Objectif** : Enregistrer l'activité terrain liée à un ouvrage

### **Type 3 : Repos/Congé**

**Workflow minimal :**
- **Pas de détails requis**
- **Champs Planning uniquement** : `date`, `employe`, `type_activite`, `activite`
- **Statut** : Validation possible mais pas obligatoire

### **Architecture des Tables**

```
Planning (Table principale - plannings)
├── id, date, employe, type_activite, activite
├── ouvrage (optionnel, requis pour MP/Bilan/Relève)
├── remarque, estvalide, statut
└── Relations conditionnelles:
    ├── PlanningDetail (si Avance)
    │   └── numero_bon_avance, designation, quantite, pu, montant
    └── BonLivraison (si Bon de livraison)
        └── designation, quantite, pu, magasin, acheteur, numero_bon
```

### **Champs Conditionnels - Résumé**

| Type Activité | Désignation | Quantité | Ouvrage | Magasin | Acheteur | Prix Unit. |
|---------------|-------------|----------|---------|---------|----------|------------|
| **Réparation/Livraison** (Avance) | ✅ Requis | ✅ Requis | ❌ | ❌ | ❌ | ✅ Auto |
| **Réparation/Livraison** (Bon Liv.) | ✅ Requis | ✅ Requis | ❌ | ✅ Requis | ✅ Requis | ✅ Auto |
| **MP/Bilan/Relève** | ❌ | ❌ | ✅ Requis | ❌ | ❌ | ❌ |
| **Repos/Congé** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### **⚠️ Notes Importantes**

1. **Recettes ≠ Planning** : Les recettes (facturation) sont gérées dans le module `apps.billing` (Releve, Paiement, Tarif). Workflow totalement séparé.

2. **Prix unitaire auto-rempli** : Lors de la saisie d'une désignation (Avance ou Bon Livraison), le prix unitaire est automatiquement récupéré depuis `Designation.prix_unitaire`.

3. **Tables séparées** : `BonLivraison` est une table à part avec ForeignKey vers Planning, tandis que les Avances utilisent `PlanningDetail` avec `numero_bon_avance` non null.

4. **Validation** : Tous les types de planning peuvent être validés (par niveau d'autorisation ≥ 3), mais les champs requis diffèrent selon le type d'activité.

## 🔄 Intégration DiameX

### **Synchronisation Bidirectionnelle**
- **Export vers DiameX :** Plannings validés, indemnités calculées
- **Import depuis DiameX :** Données terrain, relevés, mises à jour statuts
- **Règles de conflit :** En cas de divergence, priorité aux données terrain

### **Champs Synchronisés**
- Plannings et leurs statuts
- Indemnités et validations
- Achats et mouvements de stock
- Relevés de compteurs
- Données cartes sociales

## ⚠️ Contraintes et Validations

### **Contraintes de Saisie**
1. **Temporelles :**
   - Date planning >= date actuelle (sauf correction rétroactive)
   - Durée intervention cohérente avec type activité

2. **Logiques :**
   - Employé disponible à la date/heure
   - Matériel disponible en stock
   - Budget disponible pour les indemnités

3. **Autorisations :**
   - Saisie limitée aux plannings de sa base (sauf admin)
   - Modification interdite après validation niveau 3

### **Messages d'Erreur Standard**
- "Niveau d'autorisation insuffisant"
- "Employé non disponible à cette date"
- "Stock insuffisant pour cette livraison"
- "Budget dépassé pour cette période"

## 📊 Indicateurs Automatiques

### **Tableaux de Bord**
- Taux de réalisation par base
- Coûts moyens par type d'activité
- Performance des équipes
- Alertes dépassement budget

### **Rapports Automatisés**
- Rapport mensuel d'activité
- État des stocks critique
- Suivi des avances en cours
- Performance vs objectifs DiameX

---
*Document mis à jour le 11/09/2025 - Version 1.0*