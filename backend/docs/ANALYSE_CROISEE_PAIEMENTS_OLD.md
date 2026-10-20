# Documentation - Analyse Croisée des Paiements

## Vue d'ensemble

La page d'analyse croisée des paiements employés permet de visualiser le nombre de paiements par type pour chaque employé sur une période mensuelle, sous forme de matrice.

**URL d'accès** : http://localhost:8000/verification-paiements-croisee/

**Menu** : Administration → Vérification & Contrôle → Analyse Croisée (Mois × Types)

## Fonctionnalités

### 1. Filtrage
- **Par année** : Sélectionner l'année à analyser (liste dynamique des années disponibles)
- **Par type de paiement** (organisés en 4 groupes) :

  **💰 Salaires** :
  - Salaire (salaire standard mensuel)
  - Ajustement salaire (régularisations, rappels)
  - Prime (primes diverses)
  - Solde de tout compte (paiement final)
  - Allocation terrain (allocation de terrain)
  - Indemnité compensatrice (indemnité de congé)

  **📋 Charges sociales** :
  - IRSA
  - CNaPS
  - FMFP
  - Mutuelle santé

  **🏥 Remboursements** :
  - Frais médicaux
  - Frais de scolarité

  **🚗 Indemnités terrain** :
  - Indemnité terrain
  - Indemnité hors zone
  - Indemnité stage
  - Frais déplacement

### 2. Tableau matriciel

**Structure** :
- **Lignes** : Employés avec leur préfixe de poste
- **Colonnes** : Mois de l'année (Jan-Déc) + Colonne Moyenne
- **Valeurs** : Nombre de paiements du type sélectionné

**Code couleur** :
- **Vert** (0-1) : Normal - Un paiement ou moins par mois
- **Orange** (>1) : Anomalie - Plus d'un paiement dans le mois
- **Rouge** (moyenne >1) : Anomalies récurrentes - L'employé a régulièrement plusieurs paiements

**⭐ Nouveau : Compteurs cliquables** :
- Cliquez sur n'importe quel compteur (vert ou orange) pour voir les détails
- Modal affichant tous les paiements du mois avec :
  - Date exacte
  - Description complète
  - Type de paiement
  - Montant
  - Compte comptable
  - Base DiameX
  - Total des paiements affichés

### 3. Données affichées

Pour chaque cellule :
- Nombre de paiements dans le mois
- Coloration selon le code défini

Pour la colonne Moyenne :
- Moyenne des paiements par mois pour l'employé
- Arrondie à 2 décimales
- En rouge si >1 (indique un problème récurrent)

### 4. Employés inclus

Le tableau inclut tous les employés :
- Actuellement actifs (contrat sans date de fin)
- Ayant été actifs pendant l'année sélectionnée (via table Contrat)
- Filtrage basé sur `debut_contrat` et `fin_contrat`

**Correction appliquée (12 décembre 2025)** :
- Ancien filtre : Basé sur `Employe.date_debauchage` (5 employés seulement)
- Nouveau filtre : Basé sur `Contrat.debut_contrat` et `fin_contrat` (tous les employés ayant travaillé dans l'année)

Cela permet de voir l'historique complet des paiements même pour les employés partis.

## Architecture technique

### Backend

**Fichier** : `backend/apps/employees/views_verification_croisee.py`

**Vues** :
1. `verification_paiements_croisee(request)` - Page principale
   - Récupère la liste des années disponibles
   - Récupère les employés actifs dans l'année (via Contrat)
   - Retourne le template

2. `api_verification_paiements_croisee(request)` - API JSON
   - Paramètres : `annee` (requis), `type_paiement` (optionnel)
   - Retourne : Matrice {employe_id: {surnom, prefixe, actif, mois: {type: count}, moyennes: {type: avg}}}

3. `api_details_paiements_mois(request)` - API Détails ⭐ NOUVEAU
   - Paramètres : `employe_id`, `annee`, `mois`, `type_paiement` (optionnel)
   - Retourne : Liste détaillée des paiements avec date, description, montant, compte, base
   - Utilisé par le modal cliquable

**Fonction de mapping** : `mapper_type_groupe(type_paiement, description='')`
- Détecte le type de paiement depuis la description DiameX
- **Nouveau** : Accepte la description complète pour distinction fine des types de salaire

**Patterns reconnus pour les salaires** :
  - `solde de tout compte` → solde_tout_compte
  - `_prime_` ou `prime` → prime
  - `ajustement`, `regularisation`, `rappel` → ajustement_salaire
  - `allocation terrain` → allocation_terrain
  - `indemnite compensatrice` → indemnite_compensatrice
  - Défaut → salaire (salaire standard)

**Autres types directs** :
  - IRSA, CNaPS, FMFP, Mutuelle santé
  - Frais médicaux, Frais scolarité
  - Indemnités terrain, hors zone, stage
  - Frais déplacement

### Frontend

**Fichier** : `backend/templates/employees/verification_paiements_croisee.html`

**Composants** :
- Filtres : Année (select) + Type de paiement (select)
- Tableau avec colonnes épinglées (sticky)
- Modal détails avec tableau des paiements ⭐ NOUVEAU
- Fonction JavaScript `chargerDonnees()` pour chargement asynchrone
- Fonction `afficherTableau(data)` pour remplissage du tableau
- Fonction `afficherDetails(employeId, mois, surnom, prefixe)` pour modal ⭐ NOUVEAU

**Dépendances** :
- DaisyUI pour les composants (select, table, badges)
- Tailwind CSS pour le style
- Font Awesome pour les icônes

## Cas d'usage

### 1. Détecter les doublons de salaire
**Filtre** : Type = Salaire, Année = 2025
**Rechercher** : Cases oranges (>1 paiement/mois) ou moyennes rouges
**Action** : Vérifier si légitimes (ajustements) ou erreurs

### 2. Vérifier régularité IRSA
**Filtre** : Type = IRSA, Année = 2025
**Rechercher** : Mois sans paiement (0) pour employés actifs
**Action** : Identifier oublis de déclaration

### 3. Analyser employés avec paiements multiples
**Filtre** : Type = Frais médicaux, Année = 2025
**Rechercher** : Employés avec forte moyenne (>1)
**Action** : Vérifier si abus ou famille nombreuse

### 4. Comparer activité par mois
**Filtre** : Type = CNaPS, Année = 2025
**Observer** : Distribution des paiements sur l'année
**Action** : Identifier mois avec pic/creux d'activité

## Améliorations futures

1. **Export Excel** : Télécharger la matrice en XLSX
2. **Détails au clic** : Modal avec liste des paiements du mois
3. **Graphiques** : Visualisation tendances par employé
4. **Alertes automatiques** : Notification si anomalie détectée
5. **Comparaison d'années** : Afficher 2 années côte à côte
6. **Filtres avancés** : Par organisation, base DiameX, montant
7. **Améliorer mapper** : Détecter ajustements salaire et soldes de tout compte

## Dépannage

### Problème : Tableau vide
**Causes possibles** :
- Aucun paiement pour l'année/type sélectionné
- Erreur de mapping des types de paiement
- Problème d'accès base DiameX

**Solution** :
1. Vérifier les données dans la page Vérification Paiements standard
2. Consulter la console navigateur pour erreurs JavaScript
3. Vérifier les logs backend Django

### Problème : Mauvais comptage
**Causes possibles** :
- Type de paiement non reconnu par le mapper
- Description DiameX non standard

**Solution** :
1. Vérifier format des descriptions dans DiameX
2. Améliorer la fonction `mapper_type_groupe()` si besoin
3. Ajouter patterns manquants

## Fichiers du module

```
backend/
├── apps/employees/
│   ├── views_verification_croisee.py    # Backend
│   └── urls.py                           # Routes (lignes 196-198)
├── templates/employees/
│   └── verification_paiements_croisee.html  # Frontend
├── templates/
│   └── base.html                         # Menu (lignes 411-413, 720-722)
└── docs/
    └── ANALYSE_CROISEE_PAIEMENTS.md      # Cette documentation
```

## Maintenance

### Ajouter un nouveau type de paiement

**1. Modifier le mapper** (views_verification_croisee.py, lignes 142-185) :
```python
def mapper_type_groupe(type_paiement):
    # ... code existant ...

    # Ajouter pattern
    if 'nouveau_type' in desc_lower:
        return 'nouveau_type'

    return None
```

**2. Ajouter l'option dans le select** (template HTML, ligne 36) :
```html
<option value="nouveau_type">Nouveau Type</option>
```

### Modifier les seuils de couleur

**Fichier** : verification_paiements_croisee.html, lignes 142-167

```javascript
// Coloration cellule
if (count > 1) {
    cellule.classList.add('bg-orange-100', 'text-orange-800', 'font-bold');
} else if (count === 1) {
    cellule.classList.add('bg-green-50', 'text-green-700');
}

// Coloration moyenne
if (moyenne > 1) {  // Modifier ce seuil
    celluleMoyenne.classList.add('bg-red-100', 'text-red-800', 'font-bold');
}
```

---

**Créé le** : 12 décembre 2025
**Dernière mise à jour** : 12 décembre 2025
**Auteur** : Claude Code
