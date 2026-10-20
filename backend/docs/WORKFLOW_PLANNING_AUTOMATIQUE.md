# Workflow Planning Automatique - Documentation Complète

## 📋 Vue d'ensemble

Système complet pour gérer automatiquement l'inscription au Planning des congés, récupérations, repos et jours fériés, avec distinction entre employés Journaliers et Salariés.

**Date de création** : 8 décembre 2025

---

## 🎯 Objectifs

1. **Automatiser l'inscription au Planning** après validation des congés/récupérations
2. **Générer automatiquement les Repos** (Sam+Dim) pour les salariés
3. **Générer automatiquement les Jours fériés** pour les salariés
4. **Permettre l'annulation** avec création automatique de récupération

---

## 👥 Distinction Journalier / Salarié

### Identification du type de contrat

**Champ** : `Contrat.type_contrat` (lié à `Employe` via FK)

**Valeurs possibles** :
- `'journalier'` → Journalier
- `'temps_plein'` → Salarié temps plein
- `'temps_partiel'` → Salarié temps partiel
- `'Mi-temps'` → Salarié mi-temps

**Helpers créés** (`apps/employees/utils_contrat.py`) :
```python
est_journalier(employe)  # True si journalier
est_salarie(employe)     # True si non journalier
get_contrat_actif(employe)  # Retourne le contrat actif
```

### Règles applicables

| Type | Repos Auto (Sam+Dim) | Jours Fériés Auto | Gestion Repos Manuelle |
|------|----------------------|-------------------|------------------------|
| **Journalier** | ❌ NON | ❌ NON | ✅ OUI (via Planning) |
| **Salarié** | ✅ OUI | ✅ OUI | ❌ NON (automatique) |

---

## 🔄 1. Congés → Planning Automatique

### Signal Django

**Fichier** : `apps/employees/signals_conges.py`

**Trigger** : `post_save` sur `DemandeConge`

**Condition** : `instance.statut == 'validee_directeur'`

**Actions** :
1. Récupère l'activité "Congé"
2. Pour chaque jour entre `date_debut` et `date_fin` :
   - Crée un `Planning` avec `valide=True`
   - Vérifie qu'il n'existe pas déjà un planning pour cette date
3. N'affecte PAS le statut de la demande de congé

**Résultat** : L'employé a automatiquement ses jours de congé dans le Planning

---

## 🔄 2. Récupérations → Planning Automatique

### Signal Django

**Fichier** : `apps/employees/signals_recuperations.py`

**Trigger** : `post_save` sur `Recuperation`

**Condition** : `instance.statut == 'validee_directeur'`

**Actions** :
1. Récupère l'activité "Récupération"
2. Pour chaque jour entre `date_debut_recup` et `date_fin_recup` :
   - Crée un `Planning` avec `valide=True`
   - Vérifie qu'il n'existe pas déjà un planning
3. Change le statut de la récupération : `validee_directeur` → `utilisee`

**Résultat** : La récupération est inscrite au Planning et marquée comme utilisée

---

## 🔄 3. Repos Automatiques (Samedi + Dimanche)

### Commande Django

**Fichier** : `apps/planning/management/commands/populate_repos_weekly.py`

**Usage** :
```bash
# 4 semaines à partir d'aujourd'hui (défaut)
python manage.py populate_repos_weekly

# Période spécifique
python manage.py populate_repos_weekly --start 2025-01-01 --end 2025-12-31

# Nombre de semaines
python manage.py populate_repos_weekly --weeks 8
```

**Logique** :
1. Récupère tous les employés salariés (`est_salarie()`)
2. Pour chaque employé salarié :
   - Parcourt tous les Samedis (weekday==5) et Dimanches (weekday==6)
   - Crée un `Planning` avec activité "Repos" et `valide=True`
   - Saute si un planning existe déjà pour cette date

**Fréquence recommandée** : Hebdomadaire ou mensuel (cron job)

**Exemple cron** :
```bash
# Tous les lundis à 6h - Générer 4 semaines de repos
0 6 * * 1 cd /path/to/backend && python manage.py populate_repos_weekly
```

---

## 🔄 4. Jours Fériés Automatiques

### Commande Django

**Fichier** : `apps/planning/management/commands/populate_jours_feries.py`

**Usage** :
```bash
# Année courante (défaut)
python manage.py populate_jours_feries

# Années spécifiques
python manage.py populate_jours_feries --year 2024 2025
```

**Liste des jours fériés** (hardcodée dans le fichier) :

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

**Logique** :
1. Récupère tous les employés salariés
2. Pour chaque jour férié de l'année :
   - Pour chaque employé salarié :
     - Crée un `Planning` avec activité "Jour férié" et `valide=True`
     - Saute si un planning existe déjà

**Fréquence recommandée** : Début d'année (manuel ou cron)

**Exemple cron** :
```bash
# 1er janvier à 1h - Générer l'année
0 1 1 1 * cd /path/to/backend && python manage.py populate_jours_feries --year $(date +%Y)
```

---

## 🔄 5. Annulation Repos/Jour Férié → Récupération Automatique

### API REST

**Fichier** : `apps/planning/views_annulation_repos.py`

**Endpoint** : `POST /plannings/api/<planning_id>/annuler-repos-ferie/`

**Logique** :
1. Vérifie que le planning existe et est bien un Repos ou Jour férié
2. Récupère les infos (employé, date, jour de la semaine)
3. **Supprime** le Planning
4. **SI Dimanche (weekday==6) OU Jour férié** :
   - Crée une `Recuperation` automatique
   - Motif : `'dimanche'` ou `'jour_ferie'`
   - Statut : `'acquise'`
5. **SI Samedi (weekday==5)** :
   - **PAS de récupération** (non récupérable selon les règles)

**Réponse JSON** :
```json
{
  "success": true,
  "message": "Planning annulé. Une récupération a été créée automatiquement (dimanche)",
  "recuperation_creee": true,
  "recuperation_id": "uuid"
}
```

**Cas d'usage** :
- Employé salarié doit travailler un Dimanche → Annule son Repos → Récupération créée
- Employé salarié doit travailler un Jour férié → Annule → Récupération créée
- Employé salarié annule Samedi → PAS de récupération

---

## 📊 Architecture Technique

### Activités utilisées

| Nom | UUID | Usage |
|-----|------|-------|
| Congé | 7f17dbe4-e392-423e-a2d2-16876273ea2d | Congés validés |
| Jour férié | 559a5f1d-0031-4ca6-a5f0-c92464e7e5d1 | Jours fériés auto |
| Récupération | 66157d28-c7ab-4085-b502-72e203e500ef | Récupérations validées |
| Repos | c9abcaa0-39f5-4718-b461-3a3a7f7ff386 | Repos Sam+Dim auto |

### Signals Django

**Activation** : `apps/employees/signals.py` (ligne 21-22)
```python
from . import signals_conges
from . import signals_recuperations
```

**Chargement** : Automatique via `EmployeesConfig.ready()` (apps.py ligne 9)

### Fichiers créés/modifiés

**Créés** :
1. `apps/employees/signals_conges.py` - Signal congés → Planning
2. `apps/employees/signals_recuperations.py` - Signal récupérations → Planning
3. `apps/employees/utils_contrat.py` - Helpers type contrat
4. `apps/planning/management/commands/populate_repos_weekly.py` - Commande repos
5. `apps/planning/management/commands/populate_jours_feries.py` - Commande jours fériés
6. `apps/planning/views_annulation_repos.py` - API annulation
7. `docs/WORKFLOW_PLANNING_AUTOMATIQUE.md` - Cette documentation

**Modifiés** :
1. `apps/employees/signals.py` - Import des nouveaux signals
2. `apps/planning/urls.py` - Route API annulation

---

## 🧪 Tests et Validation

### Test Signal Congés

```python
from apps.employees.models import Employe
from apps.employees.models_conges import DemandeConge
from datetime import date

# Créer une demande de congé
employe = Employe.objects.first()
conge = DemandeConge.objects.create(
    employe=employe,
    date_debut=date(2025, 12, 15),
    date_fin=date(2025, 12, 20),
    type_conge='annuel',
    statut='demandee'
)

# Valider par le directeur
conge.statut = 'validee_directeur'
conge.save()

# Vérifier que 6 plannings ont été créés
from apps.planning.models import Planning
plannings = Planning.objects.filter(
    employe=employe,
    date__date__range=[date(2025, 12, 15), date(2025, 12, 20)]
)
print(f"{plannings.count()} planning(s) créé(s)")  # Devrait afficher 6
```

### Test Commande Repos

```bash
# Test sur 2 semaines
python manage.py populate_repos_weekly --weeks 2

# Vérifier dans la base
python manage.py shell -c "
from apps.planning.models import Planning, Activite
activite_repos = Activite.objects.get(nom='Repos')
repos_crees = Planning.objects.filter(activite=activite_repos).count()
print(f'{repos_crees} repos dans la base')
"
```

### Test Annulation avec Récupération

```python
from apps.planning.models import Planning
from apps.employees.models_recuperations import Recuperation

# Trouver un Planning Repos Dimanche
planning_dimanche = Planning.objects.filter(
    activite__nom='Repos',
    date__week_day=1  # Dimanche (1=dimanche, 7=samedi en Django)
).first()

# Annuler via API (simuler)
from apps.planning.views_annulation_repos import api_annuler_repos_ferie
from django.test import RequestFactory

factory = RequestFactory()
request = factory.post(f'/api/{planning_dimanche.id}/annuler-repos-ferie/')

response = api_annuler_repos_ferie(request, str(planning_dimanche.id))
print(response.content)  # JSON avec recuperation_creee=true
```

---

## ⚠️ Points d'Attention

### 1. Éviter les doublons

Tous les scripts vérifient qu'un Planning n'existe **pas déjà** avant de créer :
```python
existing = Planning.objects.filter(
    employe=employe,
    date__date=date_courante
).first()

if not existing:
    # Créer le planning
```

### 2. Timezone Madagascar

**CRITICAL** : Toujours utiliser `timezone.make_aware()` avec `tz_madagascar` :
```python
import pytz
tz_madagascar = pytz.timezone('Indian/Antananarivo')
date_planning = timezone.make_aware(
    datetime.combine(date_courante, datetime.min.time()),
    tz_madagascar
)
```

### 3. Boucles infinies dans les signals

Les signals utilisent un flag `_plannings_crees` pour éviter les boucles :
```python
if hasattr(instance, '_plannings_crees') and instance._plannings_crees:
    return

# ... créer plannings ...

instance._plannings_crees = True
instance.save(update_fields=['statut'])  # Évite de re-trigger le signal
```

### 4. Samedi NON récupérable

**IMPORTANT** : Si un salarié annule son Repos Samedi, il ne reçoit **PAS** de récupération. Seuls les Dimanches et Jours fériés sont récupérables.

---

## 📈 Améliorations Futures

1. **Interface utilisateur** : Bouton "Annuler" dans le Planning avec modal de confirmation
2. **Notifications** : Email/SMS quand congé/récupération inscrit au Planning
3. **Rapports** : Dashboard des repos/jours fériés générés par période
4. **Gestion dynamique jours fériés** : Table BDD au lieu de liste hardcodée
5. **Proration** : Gérer les demi-journées de congé/récupération
6. **Audit trail** : Log de toutes les annulations avec raison

---

## 🎯 Résumé des Workflows

```
┌─────────────────────────────────────────────────────────────┐
│                    WORKFLOW COMPLET                          │
└─────────────────────────────────────────────────────────────┘

1️⃣ CONGÉS
   DemandeConge (validee_directeur)
   ↓ Signal automatique
   Planning créé (valide=True, activité="Congé")

2️⃣ RÉCUPÉRATIONS
   Recuperation (validee_directeur)
   ↓ Signal automatique
   Planning créé (valide=True, activité="Récupération")
   Statut récupération → "utilisee"

3️⃣ REPOS (Salariés seulement)
   Commande populate_repos_weekly
   ↓ Pour chaque Salarié
   Planning Samedi + Dimanche créés (valide=True, activité="Repos")

4️⃣ JOURS FÉRIÉS (Salariés seulement)
   Commande populate_jours_feries
   ↓ Pour chaque Salarié
   Planning Jour férié créé (valide=True, activité="Jour férié")

5️⃣ ANNULATION REPOS/FÉRIÉ
   API annuler-repos-ferie
   ↓ Planning supprimé
   SI Dimanche OU Jour férié
   ↓ Récupération créée automatiquement (statut="acquise")
   SI Samedi
   ↓ PAS de récupération
```

---

*Dernière mise à jour : 8 décembre 2025*
