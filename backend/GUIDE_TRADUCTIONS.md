# 📝 GUIDE DE MODIFICATION DES TRADUCTIONS FR/MG

## 📂 Fichiers à modifier

**Fichier malgache (MG)** :
```
backend/locale/mg/LC_MESSAGES/django.po
```

**Fichier français (FR)** :
```
backend/locale/fr/LC_MESSAGES/django.po
```

## ✏️ Comment modifier une traduction

### 1. Ouvrir le fichier `.po` avec un éditeur de texte

### 2. Chercher la traduction à modifier

Exemple : Si vous voulez modifier "Filter"
```bash
Ctrl+F dans votre éditeur
Chercher : msgid "Filter"
```

### 3. Modifier la ligne `msgstr`

**AVANT** :
```po
msgid "Filter"
msgstr "Sivao"
```

**APRÈS** (exemple de modification) :
```po
msgid "Filter"
msgstr "Sivana"  # Votre nouvelle traduction
```

### 4. Sauvegarder le fichier

### 5. Recompiler les fichiers .mo

**Commande à exécuter dans le terminal** :
```bash
cd backend
python compile_po_with_polib.py
```

### 6. Recharger la page dans le navigateur

Appuyez sur `Ctrl+F5` pour recharger complètement.

---

## 📋 LISTE DES TRADUCTIONS PRINCIPALES

### **Navigation principale**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Dashboard | Tondrozotra | 21 |
| Plannings | Drafitra | 24 |
| Billing | Faktiora | 27 |
| Search | Tadiavo | 39 |
| Administration | Fitantanana | 36 |
| Applications | Rindranasa | 268 |

### **Actions communes**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Save | Tehirizo | 46 |
| Cancel | Aoka ihany | 49 |
| Delete | Fafao | 52 |
| Edit | Ovay | 55 |
| Create | Hamorona | 58 |
| View | Jereo | 61 |
| Filter | Sivao | 79 |
| Export | Avoaka | 82 |
| Import | Ampidiro | 85 |
| Print | Printiao | 88 |

### **Menu Tableaux & Rapports**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Tableaux & Rapports | Tondrozotra sy Tatitra | ~526 |
| Vue d'ensemble | Topimaso ankapobeny | 218 |
| Carte interactive | Sarintany mihetsika | 236 |
| Paiements forfaitaires | Fandoavam-bola lafo | 221 |
| Analyses consommation | Famakafakana fanjifana | 259 |

### **Menu Plannings**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Vue calendrier | Fisehon-tetiandro | 543 |
| Opérations terrain | Asa an-tany | 424 |
| Livraison | Fandefasana | 409 |
| Avance | Vola mialoha | 277 |
| Indemnités Journalières | Karama isan-andro | 385 |

### **Menu Facturation**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Paiements | Fandoavam-bola | 430 |
| Factures | Faktiora | 355 |
| Compteurs | Mpandika | 307 |
| Usagers | Mpampiasa | 538 |
| Cartes sociales | Karatra sosialy | 298 |

### **Menu Référentiel**

| Français | Malgache actuel | Ligne |
|----------|----------------|-------|
| Référentiel | Toby | 481 |
| Interface Admin | Efitrano fitantanana | ~394 |
| Interface Django | Efitrano Django | ~397 |
| Géographie | Jeografia | 373 |
| Organisations | Fikambanana | 166 |
| Fournisseurs | Mpamatsy | 193 |

### **Page Feed (Fil d'actualité)**

| Français | Malgache actuel | Notes |
|----------|----------------|-------|
| News Feed | Vaovao | Titre de la page |
| Filter | Sivao | Titre section filtres |
| Search | Tadiavo | Label recherche |
| Tous | (à vérifier) | Bouton "Tous" |
| Inspections | Fizohiana | Type de filtre |
| Employés | Mpiasa | Label employé |

---

## 🔧 APRÈS MODIFICATION

### Étapes obligatoires :

1. ✅ **Sauvegarder** le fichier `.po`
2. ✅ **Recompiler** avec `python compile_po_with_polib.py`
3. ✅ **Recharger** le navigateur (Ctrl+F5)

### Vérification :

1. Changez la langue en malgache (dropdown en haut à droite)
2. Vérifiez que vos modifications apparaissent
3. Si ça ne marche pas, rechargez avec `Ctrl+Shift+R` (force le cache)

---

## 📍 TRADUCTIONS MANQUANTES OU À VÉRIFIER

Si vous trouvez du texte non traduit dans l'application :

1. Identifiez le texte en français
2. Cherchez `msgid "Texte en français"` dans `django.po`
3. Si absent, ajoutez manuellement :
```po
msgid "Nouveau texte"
msgstr "Traduction malgache"
```
4. Recompilez avec `python compile_po_with_polib.py`

---

## ⚠️ ATTENTION

- **NE PAS modifier** les lignes `msgid` (texte source français)
- **MODIFIER uniquement** les lignes `msgstr` (traduction malgache)
- **Respecter** les guillemets `"` autour du texte
- **Ne pas supprimer** les lignes vides entre les traductions

---

## 📞 BESOIN D'AIDE ?

Si vous avez des questions sur une traduction spécifique, cherchez le numéro de ligne dans le fichier `django.po` et notez le contexte (section commentée au-dessus).
