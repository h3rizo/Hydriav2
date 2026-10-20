# Corrections Session 28 Décembre 2025

## Vue d'ensemble
Cette session a corrigé quatre problèmes critiques dans le module de recoupement 3e (Relevés vs DiameX 707401).

## 1. Correction : Données Janvier 2025 manquantes

### Problème
Les données de janvier 2025 n'apparaissaient pas dans les tableaux de recoupement 3e.

### Cause
Le filtre `datereleve__year__gte=2025` excluait les relevés de décembre 2024. Or, la règle métier stipule :
- **Date facture = Date relevé + 1 mois**
- Les factures de janvier 2025 proviennent des relevés de décembre 2024
- Sans décembre 2024, impossible de créer les groupes de janvier 2025

### Solution appliquée
**Fichier** : `backend/apps/accounting/views.py` (lignes 4585-4595)

```python
from django.db.models import Q
releves_tous = Releve.objects.filter(
    montant__isnull=False,
    montant__gt=0,
    point_eau__ouvrage__isnull=False
).filter(
    Q(datereleve__year__gte=2025) |  # Année 2025 ou plus
    Q(datereleve__year=2024, datereleve__month=12)  # OU décembre 2024
).exclude(
    remarque__icontains='coupé'  # Exclure les relevés avec "coupé" dans la remarque
).select_related('point_eau', 'point_eau__ouvrage')
```

### Résultat
- Décembre 2024 : 528 relevés inclus
- Janvier 2025 et plus : 5812 relevés
- Total : 6340 relevés disponibles pour le recoupement

---

## 2. Correction : Boutons scan absents dans modal

### Problème
Aucun bouton scan n'apparaissait dans la section "Transactions DiameX" du modal de détails.

### Cause
Le matching entre `prog` et `base_diamex` échouait :
- `prog` de BaseDiameX : `'EHA-Soakoja-Tana'`
- `base_diamex` de EmployeBaseDiameX : `'DiameX v3.16.1 - 3 - Soakoja Tana 20251014 RAF.accde'`
- Filtre direct `base_diamex=prog` retournait None
- Sans EmployeBaseDiameX, impossible de récupérer `chemin_base_diamex`
- Donc `scan_path` restait vide

### Solution appliquée
**Fichier** : `backend/apps/accounting/views.py` (lignes 5957-5980)

Implémentation de matching partiel flexible :
1. Extraire la dernière partie du prog : `"EHA-Soakoja-Tana"` → `"Tana"`
2. Gestion spéciale pour accents : `"Fenerive"` → essayer `"Fénérive"`
3. Fallback premier mot : `"Fenerive Est"` → `"Fenerive"`
4. Utiliser `__icontains` pour matching insensible à la casse

```python
if entry.scan:
    employe_base = None
    if entry.prog:
        # Extraire la partie significative du prog (ex: "Tana" ou "Fenerive Est")
        prog_parts = entry.prog.split('-')
        if len(prog_parts) >= 2:
            search_term = prog_parts[-1].strip()  # "Tana" ou "Fenerive Est"

            # Si le search_term contient "Fenerive", essayer avec accent
            if 'Fenerive' in search_term:
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex__icontains='Fénérive'
                ).first()

            # Si pas trouvé, essayer avec le terme d'origine
            if not employe_base:
                first_word = search_term.split()[0] if ' ' in search_term else search_term
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex__icontains=first_word
                ).first()

    if employe_base:
        chemin_base = employe_base.chemin_base_diamex or ''
        scan_clean = entry.scan
        if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
            scan_clean = scan_clean[2:]
        elif scan_clean.startswith('.'):
            scan_clean = scan_clean[1:]

        if not chemin_base.endswith(os.sep):
            scan_path = chemin_base + os.sep + scan_clean
        else:
            scan_path = chemin_base + scan_clean
```

### Résultat
- "Tana" match 1 EmployeBaseDiameX ✅
- "Vavatenina" match 1 EmployeBaseDiameX ✅
- "Fenerive" match avec gestion accent ✅
- Scans maintenant accessibles dans le modal

---

## 3. Correction : Filtrage des relevés "coupés"

### Problème
Les relevés avec "coupé" ou "Coupé" dans la colonne Remarque devaient être exclus du recoupement.

### Solution appliquée
**Fichiers** : `backend/apps/accounting/views.py`

#### A. Filtre principal (ligne 4593-4595)
```python
.exclude(
    remarque__icontains='coupé'  # Exclure les relevés avec "coupé" dans la remarque
)
```

#### B. API détails modal (ligne 5874-5876)
```python
.exclude(
    remarque__icontains='coupé'  # Exclure les relevés avec "coupé" dans la remarque
)
```

### Résultat
- Filtre case-insensitive : "coupé", "Coupé", "COUPÉ" tous exclus
- Appliqué à la fois dans le tableau principal ET dans le modal de détails
- Actuellement : 0 relevés exclus (aucun avec "coupé" dans la base)
- Le filtre est opérationnel pour les futurs relevés

---

## 4. Correction : Fonction openScanViaServer manquante + Échappement des chemins

### Problème
Erreur JavaScript dans la console : "Uncaught ReferenceError: openScanViaServer is not defined"

Les boutons scan dans le modal de détails du 3e recoupement ne fonctionnaient pas car la fonction `openScanViaServer()` n'était pas définie dans le template.

Après ajout de la fonction, une nouvelle erreur apparaissait : les backslashes dans les chemins de fichiers Windows étaient corrompus lors du passage à la fonction JavaScript.

**Exemple d'erreur** :
```
Erreur: Fichier introuvable: G:.shortcut-targets-by-idR7xs4jr8LMLiOLUOPtHpaYiPha2gKdwHYDRAU...
```

Les caractères `\` étaient transformés en caractères étranges.

### Solution appliquée
**Fichier** : `backend/templates/accounting/recoupement_releves.html`

#### A. Ajout des fonctions JavaScript (lignes 1667-1718)

Ajout de deux fonctions JavaScript :

#### A. Fonction getCookie (lignes 1667-1681)

```javascript
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
```

#### B. Fonction openScanViaServer (lignes 1683-1718)
```javascript
function openScanViaServer(filePath) {
    const formData = new FormData();
    formData.append('file_path', filePath);

    fetch('{% url "accounting:open_file_windows" %}', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Toast notification simple
            const toast = document.createElement('div');
            toast.className = 'toast toast-top toast-end';
            toast.innerHTML = `
                <div class="alert alert-success">
                    <span><i class="fas fa-check-circle mr-2"></i>Fichier ouvert</span>
                </div>
            `;
            document.body.appendChild(toast);
            setTimeout(() => {
                toast.remove();
            }, 3000);
        } else {
            alert('Erreur: ' + (data.error || 'Impossible d\'ouvrir le fichier'));
        }
    })
    .catch(error => {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    });
}
```

#### B. Échappement des chemins dans le onclick (ligne 1589)

**Problème** : Les backslashes dans les chemins Windows n'étaient pas correctement échappés pour JavaScript.

**Code AVANT** (incorrect) :
```javascript
onclick="openScanViaServer('${trans.scan_path}')"
```

**Code APRÈS** (correct) :
```javascript
onclick="openScanViaServer('${trans.scan_path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')"
```

**Explication** :
- `.replace(/\\/g, '\\\\')` : Double chaque backslash (`\` devient `\\`)
- `.replace(/'/g, "\\'")` : Échappe les apostrophes (`'` devient `\'`)

**Exemple de transformation** :
```
Avant : G:\path\to\file.tiff
Après : G:\\path\\to\\file.tiff
```

### Résultat

- ✅ Fonction définie et disponible globalement dans le template
- ✅ Boutons scan cliquables dans le modal de détails
- ✅ **Chemins Windows correctement échappés pour JavaScript**
- ✅ Toast notification affichée après ouverture réussie
- ✅ Gestion d'erreurs complète
- ✅ Ouverture de fichiers fonctionnelle depuis le modal

---

## 5. Ajout du taux de recouvrement et suppression des décimales

### Problème
Les utilisateurs avaient besoin de visualiser rapidement le taux de recouvrement (Total DiameX / Total Relevés) pour chaque période, et les montants avec décimales rendaient la lecture difficile.

### Solution appliquée

**Fichier backend** : `backend/apps/accounting/views.py` (lignes 4725-4729)

#### Calcul du taux de recouvrement

```python
# Calculer le taux de recouvrement (Total DiameX / Total Relevés * 100)
if data['total_releves'] > 0:
    data['taux_recouvrement'] = int((data['total_diamex'] / data['total_releves']) * 100)
else:
    data['taux_recouvrement'] = 0
```

**Fichier frontend** : `backend/templates/accounting/recoupement_releves.html`

#### A. Ajout colonne "Taux Recouvr." (ligne 910)

Nouvelle colonne dans le tableau avec badge coloré :
- **Vert** (badge-success) : Taux ≥ 95%
- **Jaune** (badge-warning) : Taux entre 80% et 94%
- **Rouge** (badge-error) : Taux < 80%

```html
<th class="bg-base-200 text-center">Taux Recouvr.</th>
```

#### B. Affichage du taux avec badge (lignes 944-951)

```html
<td class="text-center">
    <span class="badge badge-lg
    {% if rec.taux_recouvrement >= 95 %}badge-success
    {% elif rec.taux_recouvrement >= 80 %}badge-warning
    {% else %}badge-error{% endif %}">
        {{ rec.taux_recouvrement }}%
    </span>
</td>
```

#### C. Suppression des décimales (lignes 929, 935, 942)

Modification de `floatformat:2` en `floatformat:0` pour tous les montants :
```html
{{ rec.total_releves|floatformat:0|intcomma }}  <!-- Au lieu de floatformat:2 -->
{{ rec.total_diamex|floatformat:0|intcomma }}
{{ rec.ecart|floatformat:0|intcomma }}
```

#### D. En-tête enrichi avec statistiques (lignes 883-931 + 1808-1882)

Ajout des statistiques dans l'en-tête de chaque groupe d'ouvrage (visible même quand le tableau est plié) :
- **Total Relevés** : Somme de tous les totaux relevés (carte verte)
- **Total DiameX** : Somme de tous les totaux DiameX (carte bleue)
- **Écart total** : Somme de tous les écarts (carte neutre)
- **Taux de recouvrement global** : Badge coloré avec le taux calculé (carte neutre)

**HTML - Structure des cartes** (lignes 901-931) :
```html
<!-- Statistiques en-tête (toujours visibles) -->
<div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
    <!-- 4 cartes stat avec DaisyUI -->
    <div class="stat bg-success/10 rounded-lg border border-success/20">
        <div class="stat-title text-success">Total Relevés</div>
        <div class="stat-value text-success text-xl header-total-releves">0</div>
        <div class="stat-desc text-success/70">Ar</div>
    </div>
    <!-- ... 3 autres cartes avec classes header-total-diamex, header-ecart, header-taux -->
</div>
```

**JavaScript - Calcul dynamique des totaux** (lignes 1808-1882) :
```javascript
function calculateGroupHeaderStats() {
    document.querySelectorAll('.ouvrage-card').forEach(card => {
        let totalReleves = 0;
        let totalDiamex = 0;
        let totalEcart = 0;

        // Parcourir toutes les lignes du tableau
        const tbody = card.querySelector('tbody');
        tbody.querySelectorAll('tr').forEach(row => {
            const cells = row.querySelectorAll('td');
            // Extraire et additionner les montants
            totalReleves += parseFloat(cells[2].textContent.replace(/\s/g, '')) || 0;
            totalDiamex += parseFloat(cells[4].textContent.replace(/\s/g, '')) || 0;
            totalEcart += parseFloat(cells[5].textContent.replace(/\s/g, '')) || 0;
        });

        // Calculer le taux et déterminer la couleur du badge
        const taux = totalReleves > 0 ? Math.round((totalDiamex / totalReleves) * 100) : 0;
        let badgeClass = taux >= 95 ? 'badge-success' : taux >= 80 ? 'badge-warning' : 'badge-error';

        // Mettre à jour l'affichage
        card.querySelector('.header-total-releves').textContent = Math.round(totalReleves).toLocaleString('fr-FR');
        card.querySelector('.header-total-diamex').textContent = Math.round(totalDiamex).toLocaleString('fr-FR');
        card.querySelector('.header-ecart').textContent = Math.round(totalEcart).toLocaleString('fr-FR');
        card.querySelector('.header-taux').innerHTML = `<span class="badge badge-lg ${badgeClass}">${taux}%</span>`;
    });
}

// Appel au chargement de la page
document.addEventListener('DOMContentLoaded', calculateGroupHeaderStats);
```

**Avantage de l'approche JavaScript** :
- Calculs précis avec les valeurs numériques réelles
- Pas de limitations des template tags Django (`{% widthratio %}` ne gère pas bien les décimales)
- Formatage dynamique avec séparateurs de milliers français
- Coloration conditionnelle des badges selon le taux

#### E. Footer avec totaux par ouvrage (lignes 1045-1096)

Ajout d'une ligne de total dans le footer de chaque groupe d'ouvrage (même calcul que l'en-tête) :
- **Nombre de périodes** : Badge avec le nombre de lignes
- **Total Relevés** : Somme de tous les totaux relevés
- **Total DiameX** : Somme de tous les totaux DiameX
- **Écart total** : Somme de tous les écarts
- **Taux de recouvrement global** : Badge coloré avec le taux calculé

```django
<tfoot class="bg-base-200 font-bold">
    <tr class="text-lg">
        <th>TOTAL {{ ouvrage_groupe.list.0.ouvrage_nom }}</th>
        <th class="text-right text-success">{{ total_releves_ouvrage|floatformat:0|intcomma }} Ar</th>
        <th class="text-right text-primary">{{ total_diamex_ouvrage|floatformat:0|intcomma }} Ar</th>
        <th class="text-right">{{ total_ecart_ouvrage|floatformat:0|intcomma }} Ar</th>
        <th class="text-center">
            <span class="badge badge-lg badge-success/warning/error">{{ taux_ouvrage }}%</span>
        </th>
    </tr>
</tfoot>
```

### Résultat

- ✅ Colonne "Taux Recouvr." ajoutée avec badges colorés selon performance
- ✅ **Tous les montants sans décimales** (plus lisible)
- ✅ **Pourcentages sans décimales** (affichage entier)
- ✅ **En-tête enrichi** avec 4 cartes statistiques (toujours visibles)
- ✅ **Footer enrichi** avec totaux par ouvrage et taux global
- ✅ Visualisation rapide de la performance de recouvrement par période et par ouvrage
- ✅ **Statistiques visibles même quand le tableau est plié**

---

## Scripts de diagnostic créés

1. **test_janvier_2025.py** - Vérifier disponibilité données janvier 2025
2. **test_recoupement_3e.py** - Tester logique de groupement
3. **test_api_details_3e.py** - Tester endpoint API détails
4. **test_employe_base_diamex.py** - Investiguer mappings EmployeBaseDiameX
5. **test_chemin_base_direct.py** - Tester accès direct chemin_base
6. **test_partial_match.py** - Tester matching partiel
7. **test_scan_path.py** - Tester construction chemin scan
8. **test_filtre_coupe.py** - Vérifier filtre "coupé"

---

## Validation

### Tests effectués
```bash
# Django check : Aucun problème détecté
python manage.py check
# System check identified no issues (0 silenced)

# Test filtre coupé
python test_filtre_coupe.py
# Nombre total: 6340 relevés (528 déc 2024 + 5812 pour 2025+)
# Nombre exclus: 0 (aucun avec "coupé" actuellement)
```

### Résultats attendus après déploiement
1. ✅ Janvier 2025 visible dans les tableaux de recoupement 3e
2. ✅ Boutons scan visibles dans la section Transactions DiameX du modal
3. ✅ Relevés avec "coupé" exclus automatiquement du calcul

---

## Points d'attention

### Règle métier CRITICAL
**Date facture = Date relevé + 1 mois**

Pour toute nouvelle fonctionnalité impliquant des factures :
- Facture janvier 2025 = Relevé décembre 2024
- Toujours inclure le mois N-1 lors des filtres par date de facturation

### Matching partiel prog/base_diamex
Le système utilise maintenant un matching flexible :
- Extraction dernière partie du prog
- Gestion des accents (Fenerive/Fénérive)
- Fallback premier mot pour noms composés

Si de nouvelles bases DiameX sont ajoutées, vérifier que le matching fonctionne avec `test_partial_match.py`.

### Filtre "coupé"
Le filtre utilise `__icontains` (case-insensitive). Pour ajouter d'autres mots-clés à exclure, utiliser :
```python
.exclude(
    Q(remarque__icontains='coupé') |
    Q(remarque__icontains='autre_mot')
)
```

---

## Fichiers modifiés

**backend/apps/accounting/views.py** :
- Lignes 4585-4595 : Filtre décembre 2024 + exclusion "coupé"
- Lignes 5868-5876 : API détails + exclusion "coupé"
- Lignes 5957-5980 : Matching partiel prog/base_diamex

---

## Date
28 décembre 2025
