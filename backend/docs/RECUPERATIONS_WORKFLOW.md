# Module Récupérations - Documentation Complète

## 📋 Vue d'ensemble

Le module **Récupérations** permet de gérer les jours de repos accordés aux employés après avoir travaillé un dimanche ou un jour férié.

### Caractéristiques principales
- ✅ Vérification automatique dans la table Planning
- ✅ Workflow de validation en 2 étapes (Chef → Directeur)
- ✅ Détection automatique des dimanches et jours fériés
- ✅ Exclusion des dates déjà récupérées
- ✅ Traçabilité complète (lien vers Planning)
- ✅ Interface moderne avec modal en 2 étapes

---

## 🔄 Workflow Complet

### Phase 1 : Acquisition (Droits de récupération)

**Contexte** : L'employé travaille un dimanche ou un jour férié

**Système** : Le Planning enregistre automatiquement cette journée travaillée

**Résultat** : L'employé acquiert le droit à une récupération

### Phase 2 : Enregistrement de la récupération

**Page** : `/recuperations/` → Clic "Nouvelle Récupération"

**Étapes** :

1. **Sélection de l'employé** (Étape 1)
   - Choisir l'employé dans la liste déroulante
   - Sélectionner l'année (2024, 2025)
   - Le système interroge la table Planning

2. **Vérification automatique** (Backend)
   - Recherche des plannings pour l'année
   - Identifie les dimanches travaillés (`weekday == 6`)
   - Identifie les jours fériés travaillés (comparaison avec liste)
   - Exclut les dates déjà enregistrées comme récupérations

3. **Sélection de la date** (Étape 2)
   - Liste des dates récupérables s'affiche
   - Chaque date montre :
     - Date formatée (ex: "12 octobre 2025")
     - Type : Dimanche ou Jour férié
     - Activité effectuée
     - Ouvrage associé (si applicable)
     - Jour de la semaine
   - Sélectionner une date avec radio button
   - Valider

4. **Création** (Backend)
   - Création de l'enregistrement `Recuperation`
   - Statut initial : `acquise` (non utilisée)
   - Lien vers `Planning` (traçabilité)
   - Mise à jour du solde de récupérations

### Phase 3 : Demande d'utilisation

**Quand** : L'employé souhaite prendre son jour de récupération

**Comment** : Clic sur bouton "Demander" dans la liste

**Informations requises** :
- Date de début de récupération
- Date de fin de récupération
- Motif de la demande (optionnel)

**Statut** : `acquise` → `demandee`

### Phase 4 : Validation Chef

**Qui** : Chef de service

**Action** : Clic sur "Valider (Chef)"

**Statut** : `demandee` → `validee_chef`

### Phase 5 : Validation Directeur

**Qui** : Directeur

**Action** : Clic sur "Valider (Directeur)"

**Statut** : `validee_chef` → `validee_directeur`

### Phase 6 : Utilisation effective

**Quand** : Le jour de la récupération arrive

**Comment** : Inscription au planning (manuel ou automatique)

**Statut** : `validee_directeur` → `utilisee`

---

## 🗃️ Structure de la base de données

### Table `recuperations`

| Champ | Type | Description |
|-------|------|-------------|
| `id` | UUID | Identifiant unique |
| `employe_id` | UUID | FK vers Employe |
| `date_travail_exceptionnel` | Date | Date du dimanche/férié travaillé |
| `motif_acquisition` | Varchar(20) | `dimanche` ou `jour_ferie` |
| `nb_jours_acquis` | Decimal(3,1) | Nombre de jours (défaut: 1.0) |
| `planning_travail_id` | UUID | FK vers Planning (PREUVE) |
| `statut` | Varchar(20) | État actuel |
| `date_demande` | DateTime | Quand l'employé a demandé |
| `date_debut_recup` | Date | Début de la récupération |
| `date_fin_recup` | Date | Fin de la récupération |
| `motif_demande` | Text | Raison de la demande |
| `validateur_chef_id` | UUID | Qui a validé (chef) |
| `date_validation_chef` | DateTime | Quand validé (chef) |
| `validateur_directeur_id` | UUID | Qui a validé (directeur) |
| `date_validation_directeur` | DateTime | Quand validé (directeur) |
| `date_expiration` | Date | Date limite d'utilisation |
| `created_at` | DateTime | Date de création |
| `updated_at` | DateTime | Dernière modification |

### Table `soldes_recuperations`

| Champ | Type | Description |
|-------|------|-------------|
| `id` | UUID | Identifiant unique |
| `employe_id` | UUID | FK vers Employe |
| `annee` | Integer | Année concernée |
| `nb_jours_acquis` | Decimal(5,1) | Total acquis |
| `nb_jours_utilises` | Decimal(5,1) | Total utilisé |
| `nb_jours_en_attente` | Decimal(5,1) | En cours de validation |
| `nb_jours_disponibles` | Decimal(5,1) | Disponibles (calculé) |

---

## 🔍 Détection des jours fériés

### Liste des jours fériés malgaches

**2024** :
- 01/01 : Nouvel An
- 29/03 : Vendredi Saint
- 01/04 : Lundi de Pâques
- 01/05 : Fête du Travail
- 09/05 : Ascension
- 20/05 : Lundi de Pentecôte
- 26/06 : Fête de l'Indépendance
- 15/08 : Assomption
- 01/11 : Toussaint
- 25/12 : Noël

**2025** :
- 01/01 : Nouvel An
- 18/04 : Vendredi Saint
- 21/04 : Lundi de Pâques
- 01/05 : Fête du Travail
- 29/05 : Ascension
- 09/06 : Lundi de Pentecôte
- 26/06 : Fête de l'Indépendance
- 15/08 : Assomption
- 01/11 : Toussaint
- 25/12 : Noël

**Note** : Cette liste est hardcodée dans le code. Pour ajouter une année, modifier `views_recuperations.py` ligne 142-165.

---

## 🔐 Sécurité et validations

### Validations automatiques

1. **Employé existe** : Vérifie que l'ID employé est valide
2. **Planning existe** : Vérifie qu'un planning existe pour la date
3. **Pas de doublon** : Une seule récupération par date et par employé
4. **Date valide** : La date doit être un dimanche ou jour férié
5. **Non déjà récupéré** : Exclut les dates déjà enregistrées

### Permissions

- **Consultation** : Tous les utilisateurs authentifiés
- **Création** : Tous les utilisateurs (avec validation)
- **Demande** : Employé concerné ou gestionnaire
- **Validation Chef** : Chef de service
- **Validation Directeur** : Directeur

---

## 📊 APIs disponibles

### 1. Liste des récupérations
```
GET /api/recuperations/list/
Query params:
  - employe_id (UUID)
  - statut (acquise, demandee, validee_chef, etc.)
  - annee (2024, 2025)
```

### 2. Dates récupérables (✅ CORRIGÉ)
```
GET /api/recuperations/<employe_id>/dates-recuperables/
Query params:
  - annee (optionnel, défaut: 6 derniers mois)

Response:
{
  "success": true,
  "dates_recuperables": [
    {
      "date": "2025-10-12",
      "planning_id": "uuid",
      "motif": "dimanche",
      "motif_display": "Dimanche",
      "activite": "Réparation",
      "ouvrage": "Ambanja BP",
      "jour_semaine": "Sunday"
    }
  ],
  "total": 10,
  "periode": {
    "debut": "2025-01-01",
    "fin": "2025-12-31"
  }
}
```

### 3. Créer une récupération
```
POST /api/recuperations/creer/
Body:
{
  "employe_id": "uuid",
  "date_travail_exceptionnel": "2025-10-12",
  "motif_acquisition": "dimanche",
  "planning_id": "uuid",
  "nb_jours_acquis": 1.0
}
```

### 4. Demander une récupération
```
POST /api/recuperations/<recuperation_id>/demander/
Body:
{
  "date_debut_recup": "2025-11-05",
  "date_fin_recup": "2025-11-05",
  "motif_demande": "Raison personnelle"
}
```

### 5. Valider une récupération
```
POST /api/recuperations/<recuperation_id>/valider/
Body:
{
  "type": "chef"  // ou "directeur"
}
```

### 6. Solde de récupérations
```
GET /api/recuperations/<employe_id>/solde/
Query params:
  - annee (optionnel)
```

---

## 🐛 Corrections apportées (8 décembre 2025)

### Problème 1 : URLs incorrectes dans le template
**Symptôme** : "Erreur lors du chargement des dates récupérables"

**Cause** : Les URLs dans le JavaScript utilisaient `/employes/api/recuperations/...` alors que la configuration Django génère `/api/recuperations/...`

**Correction** :
- Ligne 375 : `/employes/api/...` → `/api/...`
- Ligne 507 : `/employes/api/...` → `/api/...`
- Ligne 535 : `/employes/api/...` → `/api/...`
- Ligne 562 : `/employes/api/...` → `/api/...`

**Fichier** : `templates/employees/recuperations_list.html`

### Problème 2 : Warnings timezone
**Symptôme** : `RuntimeWarning: DateTimeField Planning.date received a naive datetime`

**Cause** : Comparaison avec des datetime naïfs (`datetime(2025, 1, 1)`)

**Correction** :
- Utilisation de `timezone.make_aware()` pour créer des datetime timezone-aware
- Comparaison SQL avec `date__gte` et `date__lte` sur datetime aware

**Fichier** : `apps/employees/views_recuperations.py` lignes 123-139

### Problème 3 : Conversion date pour comparaison
**Cause** : `planning.date` (datetime aware) comparé directement avec liste de dates

**Correction** :
- Ajout de `.date()` pour convertir en date simple
- Variable `planning_date` utilisée dans toute la boucle

**Fichier** : `apps/employees/views_recuperations.py` lignes 173-195

---

## ✅ État actuel du système

### Tests réussis
- ✅ Django check : 0 erreurs
- ✅ URLs configurées correctement
- ✅ Modèles accessibles
- ✅ API testée : 10 dates récupérables trouvées
- ✅ Plus de warnings timezone
- ✅ Page accessible (redirection vers login si non authentifié)

### Navigation
- **URL** : `/recuperations/`
- **Menu** : Congés & Absences → Récupérations
- **Icône** : `fa-calendar-plus` (orange)

### Fichiers créés/modifiés

**Créés** :
1. `apps/employees/models_recuperations.py` - Modèles Recuperation + SoldeRecuperation
2. `apps/employees/views_recuperations.py` - 7 APIs REST
3. `templates/employees/recuperations_list.html` - Interface complète
4. `apps/employees/migrations/0033_add_recuperations.py` - Migration
5. `docs/RECUPERATIONS_WORKFLOW.md` - Cette documentation

**Modifiés** :
1. `apps/employees/urls.py` - 7 routes ajoutées
2. `apps/employees/models.py` - Import des modèles récupérations
3. `templates/base.html` - Liens menu (desktop + mobile)

---

## 🚀 Utilisation en production

### Prérequis
1. Serveur Django démarré
2. Utilisateur authentifié
3. Employés avec des plannings enregistrés

### Premier lancement
1. Accéder à `/recuperations/`
2. Cliquer "Nouvelle Récupération"
3. Sélectionner un employé
4. Choisir l'année
5. → Le système affiche les dates récupérables

### Workflow complet
1. **Enregistrer** : Sélectionner une date → Valider
2. **Demander** : Clic "Demander" → Remplir dates + motif
3. **Valider Chef** : Clic "Valider (Chef)"
4. **Valider Directeur** : Clic "Valider (Directeur)"
5. **Utiliser** : Inscrire au planning (manuel)

---

## 📈 Améliorations futures

### Suggestions
1. **Table jours fériés** : Remplacer la liste hardcodée par une table BDD
2. **Notifications** : Email/SMS lors des validations
3. **Automatisation** : Inscription automatique au planning
4. **Export** : Export Excel des récupérations
5. **Statistiques** : Dashboard avec graphiques
6. **Expiration automatique** : Cron job pour marquer les récupérations expirées
7. **Historique** : Audit trail complet des actions

---

## 📞 Support

**En cas de problème** :
1. Vérifier les logs Django : `python manage.py runserver`
2. Consulter la console navigateur (F12)
3. Tester l'API directement avec curl :
   ```bash
   curl "http://localhost:8000/api/recuperations/<employe_id>/dates-recuperables/?annee=2025"
   ```

**Documentation technique** :
- CLAUDE.md - Section "MODULE RÉCUPÉRATIONS"
- Code source : `apps/employees/`

---

*Dernière mise à jour : 8 décembre 2025*
