# 💰 Workflow d'Encaissement des Paiements Forfaitaires

## 📋 Vue d'ensemble

Ce document explique le workflow complet pour encaisser les paiements forfaitaires après l'émission des tickets.

## 🔄 Workflow Complet

### 1️⃣ **Émission des tickets forfaitaires**

**Page** : Suivi paiements forfaitaires (`/billing/suivi-forfaitaires/`)

**Actions** :
1. Filtrer les ouvrages/points d'eau
2. Vérifier l'historique des paiements
3. Créer une nouvelle facture si nécessaire
4. Imprimer le ticket pour l'usager

**Statut après impression** :
- ✅ `PaiementForfaitaire` créé
- ❌ `paye = False` (pas encore encaissé)
- ❌ `date_paiement = None`
- ❌ `numeroDiameX = None`

---

### 2️⃣ **Encaissement du paiement** (2 méthodes)

#### **Méthode A : Import Excel avec numéro DiameX** ⭐ (Recommandée)

**Page** : Workflow Paiements Forfaitaires (`/billing/paiements-forfaitaires/`)

**Étapes** :
1. **Télécharger le template Excel**
   - Clic sur "Télécharger template"
   - Fichier : `template_paiements_forfaitaires.xlsx`

2. **Remplir le fichier Excel**

   | ID Point d'Eau | Date Facture | Quantité | Prix Unitaire | Montant | **Numéro DiameX** | Base DiameX |
   |----------------|--------------|----------|---------------|---------|-------------------|-------------|
   | uuid-123...    | 2025-01-15   | 2        | 50000         | 100000  | **12345**         | SOAKOJA     |

   **Colonnes obligatoires** :
   - `ID Point d'Eau` : UUID du point d'eau
   - `Date Facture` : YYYY-MM-DD
   - `Quantité` : Nombre de périodes de 3 mois
   - `Prix Unitaire` : Tarif forfaitaire
   - `Montant` : Quantité × Prix Unitaire

   **Colonnes pour encaissement** :
   - `Numéro DiameX` : **C'est la clé !** Si renseigné → paiement marqué comme payé
   - `Base DiameX` : Nom de la base DiameX (ex: SOAKOJA)

3. **Importer le fichier**
   - Clic sur "Importer Excel"
   - Sélectionner le fichier rempli
   - Le système va **automatiquement** :
     - ✅ Trouver le paiement existant (même point d'eau + même mois/année)
     - ✅ Mettre à jour `numeroDiameX` et `baseDiameX`
     - ✅ **NOUVEAU** : Marquer `paye = True`
     - ✅ **NOUVEAU** : Enregistrer `date_paiement = date_facture`

**Code appliqué** ([views_paiement_forfaitaire.py:583-603](backend/apps/billing/views_paiement_forfaitaire.py#L583-L603)) :
```python
if paiement_existant:
    # Mise à jour
    paiement_existant.quantite = quantite
    paiement_existant.prix_unitaire = prix_unitaire
    paiement_existant.montant = montant
    if numero_diamex:
        paiement_existant.numeroDiameX = str(numero_diamex)
        # ✅ NOUVEAU : Si numéro DiameX renseigné, marquer comme payé
        paiement_existant.paye = True
        if not paiement_existant.date_paiement:
            paiement_existant.date_paiement = date_facture
    if base_diamex:
        paiement_existant.baseDiameX = str(base_diamex)
    paiement_existant.save()
else:
    # Création
    PaiementForfaitaire.objects.create(
        point_eau=point_eau,
        date_facture=date_facture,
        quantite=quantite,
        prix_unitaire=prix_unitaire,
        montant=montant,
        numeroDiameX=str(numero_diamex) if numero_diamex else None,
        baseDiameX=str(base_diamex) if base_diamex else None,
        paye=True if numero_diamex else False,  # ✅ NOUVEAU
        date_paiement=date_facture if numero_diamex else None  # ✅ NOUVEAU
    )
```

**Résultat** :
- ✅ Paiement marqué comme `paye = True`
- ✅ `date_paiement` enregistrée
- ✅ `numeroDiameX` et `baseDiameX` renseignés
- ✅ Apparaît comme "Payé" dans l'interface

---

#### **Méthode B : API d'encaissement direct** (Alternative)

**API** : `POST /billing/paiements-forfaitaires/api/encaisser/`

**Utilisation** : Pour encaisser manuellement après impression des tickets

**Request Body (JSON)** :
```json
{
  "paiement_ids": ["uuid1", "uuid2", "uuid3"],
  "numero_diamex": "12345",  // Optionnel
  "base_diamex": "SOAKOJA"   // Optionnel
}
```

**Response** :
```json
{
  "success": true,
  "message": "3 paiement(s) encaissé(s)",
  "nb_encaisses": 3,
  "erreurs": []
}
```

**Code** : [views_encaissement_forfaitaire.py](backend/apps/billing/views_encaissement_forfaitaire.py)

**Actions** :
- ✅ Marque `paye = True` pour tous les paiements de la liste
- ✅ Enregistre `date_paiement = today()` si pas déjà renseignée
- ✅ Enregistre `numeroDiameX` et `baseDiameX` si fournis

**Exemple d'utilisation (JavaScript)** :
```javascript
async function encaisserPaiements(paiementIds, numeroDiameX) {
    const response = await fetch('/billing/paiements-forfaitaires/api/encaisser/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            paiement_ids: paiementIds,
            numero_diamex: numeroDiameX,
            base_diamex: 'SOAKOJA'
        })
    });

    const data = await response.json();
    if (data.success) {
        alert(data.message);
        location.reload();  // Rafraîchir la page
    } else {
        alert('Erreur: ' + data.error);
    }
}
```

---

### 3️⃣ **Vérification de l'encaissement**

**Page** : Suivi paiements forfaitaires (`/billing/suivi-forfaitaires/`)

**Vérifications** :
1. Le paiement apparaît avec badge **"Payé"** (vert)
2. La date de paiement est affichée
3. Le numéro DiameX est visible
4. Le statut `paye = True` dans la base de données

**Requête SQL de vérification** :
```sql
SELECT
    id,
    point_eau_id,
    date_facture,
    montant,
    paye,
    date_paiement,
    "numeroDiameX",
    "baseDiameX"
FROM paiements_forfaitaires
WHERE date_facture >= '2025-01-01'
ORDER BY date_facture DESC;
```

---

## 🔑 Points Clés

### **Différence entre les champs**

| Champ | Rôle | Quand renseigné |
|-------|------|-----------------|
| `paye` | Boolean indiquant si le paiement est encaissé | À l'import Excel avec numéro DiameX OU via API |
| `date_paiement` | Date effective de l'encaissement | À l'import Excel avec numéro DiameX OU via API |
| `numeroDiameX` | Numéro comptable pour traçabilité | À l'import Excel uniquement |
| `baseDiameX` | Base DiameX (ex: SOAKOJA) | À l'import Excel uniquement |

### **Règles CRITICAL**

1. ⚠️ **Si `numeroDiameX` est renseigné** → `paye = True` automatiquement
2. ⚠️ **Si `paye = True`** → `date_paiement` doit être renseignée
3. ⚠️ **L'import Excel remplace la création** si un paiement existe déjà pour le même point d'eau + même mois/année
4. ⚠️ **L'API d'encaissement ne remplace rien** → elle marque juste comme payé

---

## 📊 Statistiques et Rapports

### **Voir les paiements non encaissés**

```python
from apps.billing.models import PaiementForfaitaire

paiements_non_payes = PaiementForfaitaire.objects.filter(
    paye=False
).select_related('point_eau', 'point_eau__ouvrage')

for p in paiements_non_payes:
    print(f"{p.point_eau.nomabonne} - {p.date_facture} - {p.montant} Ar")
```

### **Voir les paiements encaissés ce mois**

```python
from datetime import datetime
from apps.billing.models import PaiementForfaitaire

mois = datetime.now().month
annee = datetime.now().year

paiements_payes = PaiementForfaitaire.objects.filter(
    paye=True,
    date_paiement__month=mois,
    date_paiement__year=annee
)

total = sum([p.montant for p in paiements_payes])
print(f"Total encaissé ce mois : {total} Ar")
```

---

## 🚀 Prochaines Améliorations Possibles

1. **Bouton "Encaisser" dans l'interface** : Ajouter un bouton après impression du ticket
2. **Notification d'encaissement** : Alerter les gestionnaires après encaissement
3. **Export DiameX automatique** : Exporter directement vers DiameX après encaissement
4. **Dashboard encaissements** : Graphiques de suivi des encaissements
5. **Rapprochement bancaire** : Comparer avec les relevés bancaires

---

## 📝 Fichiers Modifiés

1. `backend/apps/billing/views_paiement_forfaitaire.py` (lignes 583-603)
   - Ajout de la logique de marquage automatique comme payé lors de l'import Excel

2. `backend/apps/billing/views_encaissement_forfaitaire.py` (nouveau fichier)
   - API d'encaissement direct des paiements

3. `backend/apps/billing/urls.py` (ligne 162)
   - Ajout de la route `/paiements-forfaitaires/api/encaisser/`

---

**Date de création** : 27 décembre 2025
**Auteur** : Claude Code
**Version** : 1.0
