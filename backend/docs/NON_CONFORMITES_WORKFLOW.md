# Workflow des Non-Conformités - Module d'Inspection

## 📋 Vue d'ensemble

Ce document décrit le système complet de gestion des non-conformités lors des inspections d'équipements.

## 🎯 Objectif

Lorsqu'un point de contrôle est marqué comme **non conforme** lors d'une inspection, l'utilisateur peut maintenant :

1. ✅ Rédiger un **narratif détaillé** du problème avec mesures précises
2. ✅ Décrire la **solution** de manière explicite avec quantités exactes
3. ✅ Lister les **matériaux nécessaires** (désignations + quantités)
4. ✅ Indiquer s'il a besoin d'un **superviseur technique**
5. ✅ Définir le **niveau de la solution** (Mpikojakoja, ST, Social, Projet)
6. ✅ Définir la **priorité** (Haute, Moyenne, Basse)
7. ✅ Définir l'**échéance** (Immédiat, 3 mois, 6 mois)
8. ✅ Estimer le **coût** de la réparation

## 🗂️ Architecture

### Modèle de données

**Fichier** : `backend/apps/inspections/models.py` (lignes 884-1032)

**Table** : `non_conformites`

**Champs principaux** :
- `resultat_inspection` (OneToOneField) - Lié au résultat d'inspection
- `narratif_probleme` (TextField) - Description détaillée avec mesures
- `solution_detaillee` (TextField) - Solution explicite avec quantités
- `materiaux_necessaires` (JSONField) - Liste des matériaux : `[{designation, quantite, unite}]`
- `besoin_superviseur` (BooleanField) - Nécessite un superviseur technique
- `niveau_solution` (CharField) - Choix : mpikojakoja, st, social, projet
- `priorite` (CharField) - Choix : basse, moyenne, haute
- `echeance` (CharField) - Choix : immediat, 3_mois, 6_mois
- `cout_estime` (DecimalField) - Coût estimé en Ariary
- `creee_par` (ForeignKey User) - Qui a créé la non-conformité

### Choix des valeurs

#### Niveau de solution
- `mpikojakoja` : **Niveau Mpikojakoja ifotony** - Réparation par l'agent local
- `st` : **Niveau ST (Superviseur Technique)** - Intervention du superviseur
- `social` : **Niveau Social** - Dépend du service social
- `projet` : **Niveau Projet** - Nécessite intervention du projet

#### Priorité
- `basse` : **Basse - Pas de gêne particulière** - La défaillance n'occasionne pas de gêne
- `moyenne` : **Moyenne - Gênante pour fonctionnement** - La défaillance est gênante
- `haute` : **Haute - Occasionne des pannes** - La défaillance cause des pannes

#### Échéance
- `immediat` : **Immédiatement - Outils disponibles** - L'agent a déjà les outils nécessaires
- `3_mois` : **Dans 3 mois - Commande matériaux** - Besoin de commander des matériaux
- `6_mois` : **Dans 6 mois - Planification avec équipe** - Planification avec autres employés

## 🚀 Workflow utilisateur

### Étape 1 : Marquer un point comme non conforme

1. Accéder à la page d'inspection : `/inspections/equipment-selection/?planning_id=...`
2. Parcourir les points de contrôle
3. Pour un point de type booléen, sélectionner **"Non conforme"**
4. La section corrective s'affiche automatiquement

### Étape 2 : Détailler la non-conformité

1. Cliquer sur le bouton **"Détailler la non-conformité"** (bouton jaune warning)
2. Un modal s'ouvre avec le formulaire complet

### Étape 3 : Remplir le narratif du problème

**Champ obligatoire** : Narratif du problème

**Exemple** :
```
Clôture défectueuse - 3 piquets cassés (hauteur 1.2m),
2 planches manquantes (largeur 15cm, longueur 2m),
zone endommagée : 3m de long sur le côté ouest
```

### Étape 4 : Décrire la solution

**Champ obligatoire** : Solution détaillée

**Exemple** :
```
Remplacer 3 piquets en bois dur (diamètre 10cm, hauteur 1.5m),
ajouter 2 planches en bois de 2m x 15cm,
utiliser 24 clous de 10cm
```

### Étape 5 : Ajouter les matériaux nécessaires

1. Remplir les champs :
   - **Désignation** : Ex: "Piquet bois dur"
   - **Quantité** : Ex: 3
   - **Unité** : Ex: "pièces"
2. Cliquer sur le bouton **+**
3. Répéter pour chaque matériau
4. Possibilité de supprimer un matériau avec l'icône poubelle

**Stockage** : Les matériaux sont stockés en JSON :
```json
[
  {"designation": "Piquet bois dur", "quantite": 3, "unite": "pièces"},
  {"designation": "Planche bois 2m", "quantite": 2, "unite": "pièces"},
  {"designation": "Clous 10cm", "quantite": 24, "unite": "pièces"}
]
```

### Étape 6 : Définir les paramètres

- ☑️ **Cocher** si besoin d'un superviseur technique
- **Sélectionner** le niveau de solution (par défaut : Mpikojakoja)
- **Sélectionner** la priorité (par défaut : Moyenne)
- **Sélectionner** l'échéance (par défaut : 3 mois)
- **Saisir** le coût estimé (optionnel)

### Étape 7 : Enregistrer

1. Cliquer sur **"Enregistrer"**
2. Le système crée automatiquement :
   - La **non-conformité** dans la base de données
   - Une **action corrective** associée (via la méthode `generer_action_corrective()`)
3. Message de confirmation affiché
4. Le modal se ferme

## 🔌 APIs Backend

### Créer une non-conformité

**Endpoint** : `POST /inspections/api/non-conformite/creer/`

**Fichier** : `backend/apps/inspections/views_non_conformites.py` (lignes 16-75)

**Paramètres** :
- `resultat_inspection_id` (UUID) - Obligatoire
- `narratif_probleme` (text) - Obligatoire
- `solution_detaillee` (text) - Obligatoire
- `materiaux_necessaires` (JSON string) - Liste des matériaux
- `besoin_superviseur` (boolean)
- `niveau_solution` (string)
- `priorite` (string)
- `echeance` (string)
- `cout_estime` (decimal) - Optionnel

**Réponse** :
```json
{
  "success": true,
  "message": "Non-conformité créée avec succès",
  "non_conformite_id": "uuid...",
  "action_corrective_id": "uuid..."
}
```

### Récupérer une non-conformité

**Endpoint** : `GET /inspections/api/non-conformite/<uuid:resultat_id>/`

**Fichier** : `backend/apps/inspections/views_non_conformites.py` (lignes 77-122)

**Réponse** :
```json
{
  "success": true,
  "non_conformite": {
    "id": "uuid...",
    "narratif_probleme": "...",
    "solution_detaillee": "...",
    "materiaux_necessaires": [...],
    "besoin_superviseur": false,
    "niveau_solution": "mpikojakoja",
    "priorite": "moyenne",
    "echeance": "3_mois",
    "cout_estime": "50000.00",
    "date_creation": "2025-11-15T10:30:00",
    "creee_par": {
      "id": 1,
      "username": "jdupont",
      "nom_complet": "Jean DUPONT"
    }
  }
}
```

### Modifier une non-conformité

**Endpoint** : `PUT /inspections/api/non-conformite/<uuid:non_conformite_id>/update/`

**Fichier** : `backend/apps/inspections/views_non_conformites.py` (lignes 124-177)

**Paramètres** : Mêmes que la création (tous optionnels)

## 🎨 Interface utilisateur

### Template

**Fichier** : `backend/templates/inspections/equipment_selection.html`

**Modifications** :
- **Lignes 1347-1354** : Bouton "Détailler la non-conformité" ajouté dans la section corrective
- **Lignes 2606-2787** : Modal complet de saisie de non-conformité
- **Ligne 2792** : Import du script JavaScript

### JavaScript

**Fichier** : `backend/static/js/non_conformites.js` (192 lignes)

**Fonctions principales** :
- `ouvrirModalNonConformite(resultatId, pointControleNom)` - Ouvre le modal
- `ajouterMateriau()` - Ajoute un matériau à la liste
- `afficherListeMateriaux()` - Affiche la liste des matériaux
- `supprimerMateriau(index)` - Supprime un matériau
- `sauvegarderNonConformite()` - Envoie les données à l'API
- `getCookie(name)` - Récupère le CSRF token

## 🔗 Génération automatique d'action corrective

**Méthode** : `NonConformite.generer_action_corrective()`

**Fichier** : `backend/apps/inspections/models.py` (lignes 998-1032)

**Logique** :
1. Mappe la priorité non-conformité → priorité action corrective
   - `basse` → `basse`
   - `moyenne` → `normale`
   - `haute` → `urgente`
2. Calcule la date prévue selon l'échéance :
   - `immediat` → Aujourd'hui + 7 jours
   - `3_mois` → Aujourd'hui + 90 jours
   - `6_mois` → Aujourd'hui + 180 jours
3. Crée une `ActionCorrective` avec :
   - **Titre** : "Correction: [Nom du point de contrôle]"
   - **Description** : Narratif + Solution
   - **Priorité** : Mappée depuis la non-conformité
   - **Date prévue** : Calculée selon échéance
   - **Responsable** : Qui a créé la non-conformité
   - **Coût estimé** : Depuis la non-conformité

## 📝 Exemple de cas d'usage complet

### Contexte
L'agent Rakoto inspecte un ouvrage et constate que la clôture est défectueuse.

### Actions dans l'interface

1. **Marque le point** "État de la clôture" comme **Non conforme**
2. **Clique** sur "Détailler la non-conformité"
3. **Remplit** le narratif :
   ```
   Clôture défectueuse - 3 piquets cassés (hauteur 1.2m) sur le côté ouest,
   2 planches manquantes (largeur 15cm, longueur 2m) au niveau du portail,
   zone totale endommagée : 3m de long
   ```
4. **Remplit** la solution :
   ```
   Remplacer 3 piquets en bois dur (diamètre 10cm, hauteur 1.5m),
   ajouter 2 planches en bois de 2m x 15cm,
   utiliser 24 clous de 10cm,
   appliquer 1 litre de vernis de protection
   ```
5. **Ajoute** les matériaux :
   - Piquet bois dur : 3 pièces
   - Planche bois 2m : 2 pièces
   - Clous 10cm : 24 pièces
   - Vernis protection : 1 litre
6. **Paramètres** :
   - ☑️ Besoin superviseur : Non
   - Niveau : Mpikojakoja ifotony
   - Priorité : Moyenne
   - Échéance : Dans 3 mois (commande matériaux)
   - Coût estimé : 75 000 Ar
7. **Clique** sur "Enregistrer"

### Résultat dans la base

**Table `non_conformites`** :
```
id: 12345-6789-abcd-...
resultat_inspection_id: [lien vers ResultatInspectionComposant]
narratif_probleme: "Clôture défectueuse - 3 piquets cassés..."
solution_detaillee: "Remplacer 3 piquets en bois dur..."
materiaux_necessaires: [{"designation":"Piquet bois dur","quantite":3,"unite":"pièces"},...]
besoin_superviseur: false
niveau_solution: 'mpikojakoja'
priorite: 'moyenne'
echeance: '3_mois'
cout_estime: 75000.00
creee_par_id: [ID de Rakoto]
date_creation: 2025-11-15 10:30:00
```

**Table `actions_correctives`** (générée automatiquement) :
```
id: abcd-1234-efgh-...
resultat_inspection_id: [même que ci-dessus]
titre: "Correction: État de la clôture"
description: "Clôture défectueuse...\n\nSOLUTION:\nRemplacer 3 piquets..."
priorite: 'normale' (mappée depuis 'moyenne')
date_prevue: 2025-02-13 (aujourd'hui + 90 jours)
responsable_id: [ID de Rakoto]
cout_estime: 75000.00
statut: 'en_attente'
```

## 🔍 Points de vérification

### Test complet du workflow

- [ ] Marquer un point comme non conforme → Section corrective s'affiche
- [ ] Cliquer sur "Détailler la non-conformité" → Modal s'ouvre
- [ ] Remplir narratif vide → Validation bloque
- [ ] Remplir solution vide → Validation bloque
- [ ] Ajouter matériau sans quantité → Alert affiché
- [ ] Ajouter matériau complet → Apparaît dans la liste
- [ ] Supprimer un matériau → Disparaît de la liste
- [ ] Enregistrer avec champs obligatoires → Success
- [ ] Vérifier en base de données → Non-conformité créée
- [ ] Vérifier en base de données → ActionCorrective créée automatiquement

### Vérification des données

**SQL pour lister les non-conformités** :
```sql
SELECT
    nc.id,
    nc.narratif_probleme,
    nc.priorite,
    nc.echeance,
    nc.cout_estime,
    u.username AS creee_par,
    nc.date_creation
FROM non_conformites nc
LEFT JOIN auth_user u ON nc.creee_par_id = u.id
ORDER BY nc.date_creation DESC;
```

**Python pour tester l'API** :
```python
from apps.inspections.models import NonConformite, ResultatInspectionComposant

# Récupérer une non-conformité
nc = NonConformite.objects.first()
print(f"Narratif: {nc.narratif_probleme}")
print(f"Matériaux: {nc.materiaux_necessaires}")

# Vérifier l'action corrective générée
action = nc.resultat_inspection.action_corrective
print(f"Action: {action.titre}")
print(f"Date prévue: {action.date_prevue}")
```

## 📊 Statistiques et rapports

### Requêtes utiles

**Nombre de non-conformités par priorité** :
```python
from django.db.models import Count
from apps.inspections.models import NonConformite

stats = NonConformite.objects.values('priorite').annotate(
    total=Count('id')
).order_by('-total')
```

**Non-conformités nécessitant un superviseur** :
```python
nc_superviseur = NonConformite.objects.filter(
    besoin_superviseur=True,
    resultat_inspection__action_corrective__statut='en_attente'
).count()
```

**Coût total des non-conformités en attente** :
```python
from django.db.models import Sum
cout_total = NonConformite.objects.filter(
    resultat_inspection__action_corrective__statut='en_attente'
).aggregate(total=Sum('cout_estime'))['total']
```

## 🚀 Prochaines améliorations possibles

1. **Photos** : Permettre l'upload de photos du problème (déjà prévu dans le modèle avec champ `photos`)
2. **Export PDF** : Générer un rapport de non-conformité au format PDF
3. **Notifications** : Alerter automatiquement le superviseur si `besoin_superviseur=True`
4. **Validation** : Workflow de validation par le superviseur avant création de l'action
5. **Catalogue matériaux** : Liste prédéfinie de matériaux avec prix unitaires
6. **Calcul automatique** : Calculer le coût estimé basé sur les matériaux et prix unitaires
7. **Historique** : Tracker les modifications de la non-conformité
8. **Dashboard** : Page de visualisation de toutes les non-conformités avec filtres et graphiques

## ✅ Checklist de déploiement

Avant de mettre en production :

- [x] Migration appliquée : `0013_add_non_conformite`
- [x] Modèle `NonConformite` créé et testé
- [x] APIs créées et fonctionnelles
- [x] Routes URL configurées
- [x] Template modifié avec modal
- [x] JavaScript fonctionnel
- [x] Fichier JS inclus dans le template
- [ ] Tests unitaires pour le modèle
- [ ] Tests d'intégration pour les APIs
- [ ] Tests E2E pour le workflow complet
- [ ] Documentation utilisateur rédigée
- [ ] Formation des utilisateurs effectuée

## 📚 Fichiers concernés

**Backend** :
- `backend/apps/inspections/models.py` (lignes 884-1032)
- `backend/apps/inspections/views_non_conformites.py` (fichier complet)
- `backend/apps/inspections/urls.py` (lignes 147-149)
- `backend/apps/inspections/migrations/0013_add_non_conformite.py`

**Frontend** :
- `backend/templates/inspections/equipment_selection.html` (lignes 1347-1354, 2606-2792)
- `backend/static/js/non_conformites.js` (fichier complet)

**Documentation** :
- `backend/docs/NON_CONFORMITES_WORKFLOW.md` (ce fichier)

---

**Dernière mise à jour** : 6 décembre 2025
**Version** : 1.0
**Auteur** : Claude Code Assistant
