# Guide Timezone - Projet Hydria

## ⚠️ RÈGLES CRITIQUES - À RESPECTER ABSOLUMENT

Ce document contient les règles essentielles pour gérer correctement les dates et timezones dans l'application Hydria.
**TOUS les imports, affichages et filtres de dates DOIVENT suivre ces règles.**

---

## 🌍 Contexte Timezone

- **Timezone application**: `Indian/Antananarivo` (Madagascar, UTC+3)
- **Stockage base de données**: PostgreSQL stocke en UTC
- **Problème principal**: Les dates Excel/utilisateur sont en heure locale Madagascar, mais stockées en UTC

### Exemple de conversion:
```
Date utilisateur: 2025-01-01 00:00 Madagascar
Date stockée BDD: 2024-12-31 21:00 UTC (21h = minuit - 3h)
Date affichée:     2025-01-01 (après conversion)
```

---

## 📥 RÈGLE 1: Import de dates depuis Excel/CSV/Formulaires

### ✅ BON CODE (À TOUJOURS UTILISER):

```python
from django.utils import timezone as dj_timezone
import pytz
from datetime import datetime

# Initialiser le timezone Madagascar
tz_madagascar = pytz.timezone('Indian/Antananarivo')

# Si date vient d'Excel ou string YYYY-MM-DD
date_str = "2025-01-01"  # ou row[0] depuis Excel

# 1. Parser la date naive (sans timezone)
date_naive = datetime.strptime(str(date_str), '%Y-%m-%d')

# 2. Localiser en timezone Madagascar (pas make_aware!)
date_obj = tz_madagascar.localize(date_naive)

# 3. Sauvegarder dans le modèle
planning.date = date_obj
planning.save()
```

### ❌ MAUVAIS CODE (NE JAMAIS FAIRE):

```python
# ❌ N'utilise pas make_aware() - il peut utiliser le mauvais timezone
date_obj = dj_timezone.make_aware(date_naive)

# ❌ Ne pas stocker directement sans timezone
planning.date = date_naive  # Mauvais!

# ❌ Ne pas utiliser datetime.now() sans timezone
planning.date = datetime.now()  # Mauvais!
```

### 📋 Checklist Import:
- [ ] Import `pytz` et créer `tz_madagascar = pytz.timezone('Indian/Antananarivo')`
- [ ] Parser la date en naive avec `strptime()`
- [ ] Utiliser `tz_madagascar.localize(date_naive)` (PAS `make_aware`)
- [ ] Vérifier que la date stockée est correcte: minuit Madagascar = 21h UTC la veille

---

## 📊 RÈGLE 2: Affichage et Filtrage de dates

### ✅ BON CODE - API/Vues Django:

```python
import pytz
from django.utils import timezone

def get_planning_data(request):
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les plannings
    plannings = Planning.objects.all()

    # Convertir chaque date avant affichage
    for planning in plannings:
        if planning.date:
            # 1. S'assurer que la date a un timezone
            date_aware = planning.date if planning.date.tzinfo else timezone.make_aware(planning.date)

            # 2. Convertir en timezone Madagascar
            date_madagascar = date_aware.astimezone(tz_madagascar)

            # 3. Extraire la date (sans heure)
            date_obj = date_madagascar.date()

            # 4. Utiliser cette date pour affichage
            planning_data = {
                'date_planning': date_obj.isoformat(),  # "2025-01-01"
                'year': date_obj.year,
                'month': date_obj.month,
                'day': date_obj.day
            }
```

### ✅ BON CODE - Filtre par mois (TOUJOURS EN PYTHON, JAMAIS EN SQL):

```python
def filter_by_month(request):
    filter_mois = request.GET.get('mois')  # Format: "2025-01"
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Parser le filtre
    if filter_mois:
        year_month = filter_mois.split('-')
        filter_year = int(year_month[0])
        filter_month = int(year_month[1])

    # Récupérer tous les plannings (sans filtre SQL par date)
    plannings = Planning.objects.all()

    # Filtrer en Python après conversion timezone
    filtered_plannings = []
    for planning in plannings:
        date_aware = planning.date if planning.date.tzinfo else timezone.make_aware(planning.date)
        date_madagascar = date_aware.astimezone(tz_madagascar)
        date_obj = date_madagascar.date()

        # Appliquer le filtre
        if date_obj.year == filter_year and date_obj.month == filter_month:
            filtered_plannings.append(planning)

    return filtered_plannings
```

### ❌ MAUVAIS CODE (NE JAMAIS FAIRE):

```python
# ❌ Ne JAMAIS utiliser AT TIME ZONE dans PostgreSQL
query = "SELECT * FROM plannings WHERE EXTRACT(MONTH FROM date AT TIME ZONE 'Indian/Antananarivo') = %s"
# PostgreSQL AT TIME ZONE donne des résultats incorrects!

# ❌ Ne pas extraire .date() directement sans conversion
date_obj = planning.date.date()  # Mauvais! Utilise UTC

# ❌ Ne pas filtrer par date en SQL sans conversion
plannings = Planning.objects.filter(date__year=2025, date__month=1)  # Filtre en UTC!
```

### 📋 Checklist Affichage/Filtre:
- [ ] Import `pytz` et créer `tz_madagascar`
- [ ] Convertir chaque date avec `.astimezone(tz_madagascar)`
- [ ] Extraire `.date()` APRÈS conversion timezone
- [ ] Filtrer en Python, PAS en SQL
- [ ] Vérifier que "2024-12-31 21:00 UTC" s'affiche comme "2025-01-01"

---

## 🌐 RÈGLE 3: JavaScript/Frontend

### ✅ BON CODE - Parser des dates ISO:

```javascript
// L'API Django renvoie: "2025-01-01"
function formatDate(dateString) {
    if (!dateString) return '';

    // Parser comme date locale (pas UTC)
    const parts = dateString.split('-');
    if (parts.length === 3) {
        // Créer date locale: année, mois (0-indexé), jour
        const date = new Date(
            parseInt(parts[0]),
            parseInt(parts[1]) - 1,
            parseInt(parts[2])
        );
        return date.toLocaleDateString('fr-FR');
    }

    // Fallback
    return dateString;
}
```

### ❌ MAUVAIS CODE:

```javascript
// ❌ Ne pas parser directement avec new Date(string)
function formatDate(dateString) {
    const date = new Date(dateString);  // Mauvais! Parse en UTC
    return date.toLocaleDateString('fr-FR');
}
```

### 📋 Checklist Frontend:
- [ ] Parser manuellement YYYY-MM-DD (split et parseInt)
- [ ] Créer Date avec `new Date(year, month-1, day)`
- [ ] NE PAS utiliser `new Date(string)` directement

---

## 🧪 RÈGLE 4: Tests et Validation

### Comment vérifier qu'une date est correcte:

```python
import pytz

# 1. Récupérer un planning
planning = Planning.objects.first()

# 2. Vérifier le stockage UTC
print(f"Date stockée UTC: {planning.date}")
# Devrait être: 2024-12-31 21:00:00+00:00

# 3. Convertir en Madagascar
tz_mg = pytz.timezone('Indian/Antananarivo')
date_mg = planning.date.astimezone(tz_mg)
print(f"Date Madagascar: {date_mg}")
# Devrait être: 2025-01-01 00:00:00+03:00

# 4. Vérifier la date affichée
print(f"Date affichée: {date_mg.date()}")
# Devrait être: 2025-01-01

# ✅ Si minuit Madagascar = 21h UTC la veille, c'est correct!
assert date_mg.hour == 0
assert date_mg.date().day == 1
```

---

## 📝 Cas d'usage courants

### Import Excel de plannings:
```python
# Voir: backend/apps/planning/views.py lignes 1943-1973
tz_madagascar = pytz.timezone('Indian/Antananarivo')
date_naive = datetime.strptime(str(date_str), '%Y-%m-%d')
date_obj = tz_madagascar.localize(date_naive)
```

### Export Excel de plannings:
```python
# Voir: backend/apps/planning/views.py lignes 1354-1359, 1228
import pytz
tz_madagascar = pytz.timezone('Indian/Antananarivo')

# Convertir AVANT d'exporter
date_aware = planning.date if planning.date.tzinfo else timezone.make_aware(planning.date)
date_madagascar = date_aware.astimezone(tz_madagascar)
date_str = date_madagascar.strftime('%Y-%m-%d')

# ❌ NE PAS FAIRE: planning.date.strftime('%Y-%m-%d')  # Utilise UTC!
```

### API de liste de plannings avec filtre mois:
```python
# Voir: backend/apps/planning/views_simple.py lignes 91-142
# Filtrer en Python APRÈS conversion timezone
if filter_year and filter_month and date_obj:
    if date_obj.year != filter_year or date_obj.month != filter_month:
        continue
```

### Template JavaScript affichage dates:
```javascript
// Voir: backend/templates/planning/planning_dashboard.html lignes 1082-1094
const parts = dateString.split('-');
const date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
```

---

## 🚨 Symptômes de problèmes timezone

Si vous voyez ces comportements, c'est qu'il y a un problème timezone:

1. **Décalage d'un jour dans l'affichage**
   - Ex: Excel "2025-01-01" → Affichage "2024-12-31" ou "2025-01-02"
   - Solution: Convertir avec `.astimezone(tz_madagascar)` avant `.date()`

2. **Filtre par mois décalé**
   - Ex: Filtre "janvier 2025" affiche des dates de décembre ou février
   - Solution: Filtrer en Python après conversion timezone

3. **Heure incorrecte (18:00 au lieu de 00:00)**
   - Ex: Date stockée "2024-12-31 18:00" au lieu de "21:00"
   - Solution: Utiliser `tz_madagascar.localize()` à l'import

4. **PostgreSQL AT TIME ZONE donne des résultats bizarres**
   - Solution: Ne JAMAIS utiliser AT TIME ZONE, filtrer en Python

---

## 📌 Références

- **Import de dates**: `backend/apps/planning/views.py` lignes 1943-1973
- **API avec filtre timezone**: `backend/apps/planning/views_simple.py` lignes 91-142
- **JavaScript formatDate**: `backend/templates/planning/planning_dashboard.html` lignes 1082-1094
- **Tests timezone**: `backend/test_timezone.py`
- **Configuration Django**: `TIME_ZONE = 'Indian/Antananarivo'` dans `settings.py`

---

## 🎯 Checklist avant commit

Avant de commiter du code qui manipule des dates:

- [ ] J'ai utilisé `tz_madagascar.localize()` pour l'import
- [ ] J'ai converti avec `.astimezone(tz_madagascar)` pour l'affichage
- [ ] Je filtre par date en Python, PAS en SQL
- [ ] J'ai testé avec une date qui change de jour (ex: 2025-01-01)
- [ ] J'ai vérifié que minuit Madagascar = 21h UTC la veille
- [ ] Frontend parse "YYYY-MM-DD" manuellement avec split()

---

**Date création**: 23 octobre 2025
**Dernière mise à jour**: 23 octobre 2025
**Auteur**: Claude (corrections suite à problèmes d'import/affichage)
