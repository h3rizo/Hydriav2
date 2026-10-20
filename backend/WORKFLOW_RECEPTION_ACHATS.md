# 📦 Workflow de Réception des Achats et Export DiameX

## Vue d'ensemble

Ce document explique comment **réceptionner un achat** et comment la transaction est **automatiquement envoyée vers DiameX** pour la comptabilité.

---

## 🏗️ Structure des données

```
Organisation
    ↓
  Base (volet, organisation)
    ↓
Magasin (nom_magasin, base)
    ↓
Purchase (achat, base, magasin via base.magasins)
```

---

## 📋 Étape 1 : Accéder à la page des achats

**URL :** `http://localhost:8000/stocks/achats/`

Sur cette page, vous voyez la liste de tous les achats avec les colonnes suivantes :

| N° Achat | Date | Fournisseur | Magasin | Articles | Montant Total | Numéro DiameX | Base DiameX | Statut | Actions |
|----------|------|-------------|---------|----------|---------------|---------------|-------------|--------|---------|
| A-2025-001 | 15/11/2025 | Fournisseur ABC | Magasin Ambanja | 5 articles | 1,250,000 Ar | - | - | **Commandé** | 👁️ ✅ ✏️ 🗑️ |

### Légende des actions :
- 👁️ **Voir détails** : Affiche tous les détails de l'achat
- ✅ **Réceptionner** : Apparaît seulement si le statut est "Commandé" ou "Livré"
- ✏️ **Modifier** : Éditer l'achat
- 🗑️ **Supprimer** : Supprimer l'achat

---

## 📦 Étape 2 : Réceptionner un achat

### Conditions requises :
Le bouton "Réceptionner" (✅) n'apparaît QUE si le statut de l'achat est :
- **Commandé** (`commande`)
- **Livré** (`livre`)

### Processus de réception :

1. **Clic sur le bouton ✅ "Réceptionner"**

   Un message de confirmation apparaît :
   ```
   Voulez-vous réceptionner l'achat A-2025-001 ?

   Cela créera automatiquement une transaction DiameX en attente d'export.
   ```

2. **Confirmer la réception**

   Le système effectue automatiquement les actions suivantes :

   a) **Met à jour l'achat** :
      - Statut → `recu` (Réceptionné)
      - Date de réception → Date du jour

   b) **Crée une transaction DiameXTemporaire** avec :
      - **Type** : `depense` (sortie d'argent)
      - **Date** : Date de réception
      - **Description** : Format spécial (voir ci-dessous)
      - **Montant OUT** : Montant total de l'achat
      - **Compte** : `601` (compte achats par défaut)
      - **Prog** : Volet de la base (ex: "SOAKOJA", "JIRAMA")
      - **Statut** : `en_attente` (en attente de validation/export)
      - **Lien** : Référence vers l'achat (Purchase)

3. **Message de succès**
   ```
   ✓ Achat A-2025-001 réceptionné avec succès. Transaction DiameX créée.
   ```

---

## 📝 Format de la description DiameX

La description est générée automatiquement selon ce format :

```
NIF [NIF] - [Nom Fournisseur] - [Article 1 (unité)], [Article 2 (unité)], [Article 3 (unité)]... - [Montant] Ar
```

### Exemples :

**Exemple 1 - Avec NIF :**
```
NIF 500123456789 - Fournisseur ABC - Ciment (sac), Fer (kg), Tôle (unité) - 1,250,000 Ar
```

**Exemple 2 - Sans NIF :**
```
Supplier XYZ - Fournitures (lot), Outils (unité) - 850,500 Ar
```

**Exemple 3 - Plus de 3 articles :**
```
NIF 500987654321 - Quincaillerie Centrale - Vis (boîte), Clous (kg), Peinture (litre)... - 2,150,000 Ar
```

### Règles de formatage :
- Si le fournisseur a un **NIF**, il est affiché en premier
- Maximum **3 désignations** affichées
- Si plus de 3 articles → ajout de "..." à la fin
- Chaque article affiche : **Nom (unité)**
- Montant formaté avec séparateurs de milliers
- Longueur max : **255 caractères** (tronqué si nécessaire)

---

## 💾 Étape 3 : Consulter la transaction créée

**URL :** `http://localhost:8000/comptabilite/temporaire/`

Sur cette page, vous verrez la nouvelle transaction dans la table **DiameXTemporaire** :

| Date | Description | Compte | Prog | IN | OUT | Statut | Source |
|------|-------------|--------|------|----|----|--------|--------|
| 15/11/2025 | NIF 500123456789 - Fournisseur ABC - Ciment (sac), Fer (kg)... - 1,250,000 Ar | 601 | SOAKOJA | - | 1,250,000 | 🟡 En attente | 📦 Achat |

### Colonnes importantes :
- **Date** : Date de réception de l'achat
- **Description** : Description automatique formatée
- **Compte** : 601 (achats)
- **Prog** : Volet de la base (SOAKOJA, JIRAMA, etc.)
- **OUT** : Montant de la dépense
- **Statut** : En attente (jaune) → prêt pour export
- **Source** : Indique que c'est un achat réceptionné

---

## 📤 Étape 4 : Exporter vers Access DiameX

### Sur la page `/comptabilite/temporaire/` :

1. **Filtrer les transactions en attente**
   - Statut : "En attente"
   - Type : "Dépense"

2. **Sélectionner les transactions à exporter**
   - Cocher la case de la transaction de l'achat
   - Ou sélectionner plusieurs transactions

3. **Clic sur "Exporter vers DiameX"**

### Processus d'export :

Le système effectue automatiquement :

1. **Connexion à la base Access DiameX**
   - Ouvre le fichier `.mdb` de la base correspondante
   - Table cible : `DATA`

2. **Insertion de la transaction**
   ```sql
   INSERT INTO DATA (
       Date_M, Description, Pers, Detail,
       Prog, Activ, Cpt, D, C
   ) VALUES (
       '15/11/2025',
       'NIF 500123456789 - Fournisseur ABC - Ciment...',
       '',
       '',
       'SOAKOJA',
       'SOAKOJA',
       '601',
       1250000,
       0
   )
   ```

3. **Récupération de l'ID Access**
   - Access génère automatiquement un **ID** unique
   - Récupère aussi le **Prog** utilisé

4. **Mise à jour de l'achat dans Django**
   ```python
   Purchase.numeroDiameX = "12345"  # ID généré par Access
   Purchase.baseDiameX = "SOAKOJA"  # Prog utilisé
   ```

5. **Mise à jour de la transaction DiameXTemporaire**
   - Statut → `exporte` (vert)
   - Date d'export enregistrée

---

## ✅ Étape 5 : Vérification finale

### Retour sur `/stocks/achats/` :

L'achat réceptionné affiche maintenant :

| N° Achat | Date | Fournisseur | Magasin | Articles | Montant Total | **Numéro DiameX** | **Base DiameX** | Statut | Actions |
|----------|------|-------------|---------|----------|---------------|-------------------|-----------------|--------|---------|
| A-2025-001 | 15/11/2025 | Fournisseur ABC | Magasin Ambanja | 5 articles | 1,250,000 Ar | **12345** | **SOAKOJA** | **Réceptionné** | 👁️ ✏️ 🗑️ |

**Observations :**
- ✅ Statut = "Réceptionné" (badge vert)
- ✅ Numéro DiameX rempli (ex: 12345)
- ✅ Base DiameX rempli (ex: SOAKOJA)
- ❌ Bouton "Réceptionner" disparu (car déjà réceptionné)

---

## 🔄 Schéma du workflow complet

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. ACHAT CRÉÉ/COMMANDÉ                       │
│  Statut: "Commandé" ou "Livré"                                  │
│  numeroDiameX: vide                                             │
│  baseDiameX: vide                                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│          2. CLIC SUR BOUTON "RÉCEPTIONNER" (✅)                 │
│  Confirmation: "Créera transaction DiameX"                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  3. MISE À JOUR ACHAT                           │
│  Statut: "Commandé" → "Réceptionné"                             │
│  actual_delivery_date: Date du jour                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           4. CRÉATION TRANSACTION DiameXTemporaire              │
│  Type: depense                                                  │
│  Description: "NIF XXX - Fournisseur - Articles - Amount Ar"   │
│  montant_out: Montant total achat                               │
│  compte_code: 601                                               │
│  prog: Volet de la base                                         │
│  statut: en_attente                                             │
│  purchase: Lien vers Purchase                                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│     5. VALIDATION/EXPORT VERS ACCESS (Page temporaire)          │
│  URL: /comptabilite/temporaire/                                 │
│  Action: "Exporter vers DiameX"                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              6. INSERTION DANS ACCESS DATA                      │
│  Table: DATA                                                    │
│  Champs: Date_M, Description, Prog, Activ, Cpt, D, C           │
│  Résultat: Access génère ID unique                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│           7. COPIE DES IDs VERS PURCHASE                        │
│  Purchase.numeroDiameX = Access.ID                              │
│  Purchase.baseDiameX = Access.Prog                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  8. WORKFLOW TERMINÉ ✅                         │
│  Achat: Réceptionné + IDs DiameX remplis                        │
│  Transaction DiameXTemporaire: Exportée                         │
│  Access DATA: Nouvelle entrée créée                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Fichiers techniques impliqués

### Backend Django :

1. **`apps/inventory/models.py`**
   - Modèle `Purchase` avec champs `numeroDiameX` et `baseDiameX`

2. **`apps/inventory/views.py`**
   - Fonction `purchase_receive(request, purchase_id)` (ligne 324-406)
   - Gère la réception et création de transaction

3. **`apps/accounting/models.py`**
   - Modèle `DiameXTemporaire` avec champ `purchase` (ForeignKey)

4. **`apps/accounting/views_export_access.py`**
   - Fonction d'export vers Access (ligne 381-390)
   - Copie des IDs vers Purchase

### Frontend :

5. **`templates/inventory/purchases_list.html`**
   - Bouton "Réceptionner" (ligne 233-237)
   - Fonction JavaScript `receivePurchase()` (ligne 641-658)

### URLs :

6. **`apps/inventory/urls.py`**
   - Route : `achats/<uuid:purchase_id>/receive/` (ligne 23)

---

## ❓ Questions fréquentes

### Q1 : Pourquoi le bouton "Réceptionner" n'apparaît pas ?

**R :** Le bouton n'apparaît QUE si le statut de l'achat est :
- "Commandé" (`commande`)
- "Livré" (`livre`)

Si l'achat est en "Brouillon", changez d'abord le statut à "Commandé".

### Q2 : Puis-je réceptionner plusieurs fois ?

**R :** Non. Une fois réceptionné, le statut passe à "Réceptionné" et le bouton disparaît. Si vous devez annuler, modifiez manuellement le statut.

### Q3 : Que se passe-t-il si j'ai plus de 3 articles ?

**R :** Seuls les 3 premiers articles sont affichés dans la description DiameX, suivis de "..." pour indiquer qu'il y en a plus.

### Q4 : Puis-je modifier la description DiameX ?

**R :** Oui, dans la page `/comptabilite/temporaire/`, vous pouvez modifier la transaction AVANT de l'exporter vers Access.

### Q5 : Le magasin ne se charge pas dans le modal "Modifier"

**R :** Vérifiez que :
- L'achat a bien un `base_id` (obligatoire)
- Le magasin appartient à cette base
- Les données sont retournées par l'API `/stocks/achats/<id>/`

---

## 🎯 Résumé en 3 étapes

1. **Réceptionner** → Clic sur ✅ dans `/stocks/achats/`
2. **Vérifier** → Transaction créée dans `/comptabilite/temporaire/`
3. **Exporter** → Clic "Exporter" → IDs copiés automatiquement

**C'est tout ! 🎉**
