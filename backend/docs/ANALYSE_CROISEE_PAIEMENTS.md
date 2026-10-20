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
- **Lignes** : Employés **groupés par Base** avec leur préfixe de poste
  - **Indicateurs d'anomalies** : Badges visuels (⚠️ Type) affichés sous le nom pour chaque type de paiement avec moyenne >1
  - **Tooltip** : Survol du badge montre le nombre de mois concernés et la moyenne
- **Colonnes** : Mois de l'année (Jan-Déc) + Colonne Moyenne
- **Valeurs** : Nombre de paiements du type sélectionné
- **Regroupement** : Les employés sont ventilés par Base (organisation) avec ligne de séparation

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
- Filtres : Année (select) + Type de paiement (select avec optgroups)
- Tableau avec colonnes épinglées (sticky)
- Modal détails avec tableau des paiements ⭐ NOUVEAU
- Fonction JavaScript `chargerDonnees()` pour chargement asynchrone
- Fonction `afficherTableau(data)` pour remplissage du tableau
- Fonction `afficherDetails(employeId, mois, surnom, prefixe)` pour modal ⭐ NOUVEAU

**Dépendances** :
- DaisyUI pour les composants (select, table, badges, modal)
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
2. ~~**Détails au clic**~~ : ✅ **IMPLÉMENTÉ (12 déc 2025)** - Modal avec liste des paiements du mois
3. **Graphiques** : Visualisation tendances par employé
4. **Alertes automatiques** : Notification si anomalie détectée
5. **Comparaison d'années** : Afficher 2 années côte à côte
6. **Filtres avancés** : Par organisation, base DiameX, montant
7. ~~**Améliorer mapper**~~ : ✅ **IMPLÉMENTÉ (12 déc 2025)** - Détection de 6 sous-types de salaire

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

**1. Modifier le mapper** (views_verification_croisee.py, lignes 269-316) :

```python
def mapper_type_groupe(type_paiement, description=''):
    # ... code existant ...

    # Ajouter pattern pour salaire
    if type_paiement == 'salaire':
        if 'nouveau_pattern' in desc_lower:
            return 'nouveau_type'

    # Ou ajouter type direct
    mapping = {
        # ... existants ...
        'nouveau_type': 'nouveau_type',
    }

    return mapping.get(type_paiement, None)
```

**2. Ajouter dans la liste des types suivis** (views_verification_croisee.py, ligne 157) :

```python
types_a_suivre = [
    'salaire', 'ajustement_salaire', 'prime', 'solde_tout_compte',
    'allocation_terrain', 'indemnite_compensatrice',
    'nouveau_type',  # ← Ajouter ici
    # ...
]
```

**3. Ajouter l'option dans le select** (template HTML, dans le bon optgroup) :

```html
<optgroup label="💰 Salaires">
    <option value="nouveau_type">Nouveau Type</option>
</optgroup>
```

**4. Ajouter dans le mapping JavaScript** (template HTML, ligne ~340) :

```javascript
const nomsTypes = {
    // ... existants ...
    'nouveau_type': 'Nouveau Type',
};
```

### Modifier les seuils de couleur

**Fichier** : verification_paiements_croisee.html, lignes ~270-280

```javascript
// Coloration cellule
if (count > 1) {  // Modifier ce seuil
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

## Historique des modifications

**12 décembre 2025 (3)** - Indicateurs d'anomalies par employé
- Badges visuels à côté du nom de l'employé pour chaque type avec anomalies
- Format : "⚠️ Type" avec tooltip (nb mois, moyenne)
- Affichage automatique si moyenne >1 pour un type
- 16 types abrégés (Sal, IRSA, CNaPS, Prime, etc.)
- Légende mise à jour avec 2 colonnes
- Documentation : `INDICATEURS_ANOMALIES_EMPLOYES.md`
- Fichier modifié : `verification_paiements_croisee.html` (lignes 489-539, 191-225)

**12 décembre 2025 (2)** - Correction détection employés avec surnoms
- Amélioration de l'algorithme de recherche (fallback 5)
- Les employés avec surnoms dans DiameX sont maintenant détectés
- Ex: "FENOMANANA Syressi Tilamb" → Trouve "Syressi FENOMANANA"
- Recherche d'abord avec 2 premiers mots, puis tous les mots si échec
- Documentation : `FIX_DETECTION_EMPLOYES_SURNOMS.md`
- Fichier modifié : `views_verification_croisee.py` (lignes 162-176)

**12 décembre 2025 (1)** - Ajout du regroupement par Base
- Les employés sont maintenant groupés par Base (organisation)
- Ligne de séparation avec badge de compteur pour chaque base
- Tri alphabétique des bases et des employés
- Documentation : `ANALYSE_CROISEE_GROUPEMENT_BASE.md`
- Fichiers modifiés : `views_verification_croisee.py`, `verification_paiements_croisee.html`

---

**Créé le** : 12 décembre 2025
**Dernière mise à jour** : 12 décembre 2025
**Auteur** : Claude Code
