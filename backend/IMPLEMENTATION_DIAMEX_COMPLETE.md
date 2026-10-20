# Implémentation complète - Table TemporaireDiameX

## ✅ Modifications apportées

### 1. Modèle Fournisseur (apps/billing/models.py)
**Ajouté** :
- `prestation` (BooleanField) - Indique si c'est un prestataire (affichera "PREST" dans description DiameX)

**Champs existants utilisés** :
- `numero_nif` - Pour le NIF dans la description
- `nom_fournisseur` - Pour la colonne fournisseur_nom

### 2. Modèle TemporaireDiameX (apps/billing/models.py)
**Ajouté 11 nouvelles colonnes DiameX** :
- `journal` (CharField, default="00PERS") - Code journal comptable
- `datem` (CharField) - Format YYYY-MM (mois du ticket)
- `rec` (IntegerField, default=0) - Numéro reçu (sera défini dans prochain workflow)
- `date_rec` (DateField) - Date du ticket
- `description` (TextField) - Description formatée selon règles DiameX
- `in_amount` (DecimalField) - Entrée (montant si recette, sinon 0)
- `out_amount` (DecimalField) - Sortie (montant si avance, sinon 0)
- `cat` (CharField) - Code compte comptable (ex: 748411)
- `pers` (CharField) - Surnom employé
- `fournisseur_nom` (CharField) - Nom fournisseur
- `activ` (CharField) - Code base DiameX

### 3. Migration appliquée
**Fichier** : `apps/billing/migrations/0026_fournisseur_prestation_temporairediamex_activ_and_more.py`
- ✅ Migration créée et appliquée avec succès

---

## 📝 Logique de remplissage

### Types de tickets traités
**IMPORTANT** : Les bons de livraison ne créent PAS de ligne DiameX
- ✅ **Recettes** (Paiement forfaitaire) → Génère ligne DiameX
- ✅ **Avances** → Génère ligne DiameX
- ❌ **Bons de livraison** → PAS de ligne DiameX (workflow stock uniquement)

---

### Pour les RECETTES (Paiement forfaitaire)

#### Journal
```python
journal = "00PERS"  # Par défaut
# OU si base a un journal_retour défini :
journal = detail.planning.ouvrage.base.journal_retour.code
```

#### Description
```python
# Format: _Paiement forfaitaire_[Nom Ouvrage]_[Montant]
description = f"_Paiement forfaitaire_{nom_ouvrage}_{montant}"
# Exemple: "_Paiement forfaitaire_Ambohimanga_75000"
```

#### In / Out
```python
in_amount = detail.montant  # Entrée (recette)
out_amount = 0
```

#### Cat (Compte)
```python
cat = "748411"  # Code fixe pour paiements forfaitaires
```

#### Autres champs
- `datem` : `"2025-01"` (format YYYY-MM)
- `rec` : `0`
- `date_rec` : Date du planning (timezone Madagascar)
- `pers` : Surnom employé
- `fournisseur_nom` : `None` (pas de fournisseur pour recettes)
- `activ` : `base.base_diamex`

---

### Pour les AVANCES

#### Journal
```python
journal = "00PERS"  # Par défaut
# OU si base a un journal_retour défini :
journal = detail.planning.ouvrage.base.journal_retour.code
```

#### Description
```python
# Format: [NIF]_[PREST]_[2 premières désignations]_[Montant]

# 1. NIF du fournisseur
nif = detail.fournisseur.numero_nif or ""

# 2. PREST si fournisseur.prestation = True
prest = "PREST" if detail.fournisseur.prestation else ""

# 3. Récupérer les 2 premières désignations du même planning
designations = PlanningDetail.objects.filter(
    planning=detail.planning,
    utilise=True
).select_related('designation').order_by('id')[:2]

designations_str = "_".join([d.designation.nom for d in designations if d.designation])

# 4. Assemblage
parts = [nif, prest, designations_str, str(montant)]
description = "_".join([p for p in parts if p])

# Exemples:
# "123456789_PREST_Essence_Huile moteur_100000"
# "987654321__Carburant_50000" (sans PREST)
```

#### In / Out
```python
in_amount = 0
out_amount = detail.montant  # Sortie (dépense)
```

#### Cat (Compte)
```python
cat = detail.compte  # Code compte depuis PlanningDetail
# Exemple: "605100", "601200", etc.
```

#### Autres champs
- `datem` : `"2025-01"` (format YYYY-MM)
- `rec` : `0`
- `date_rec` : Date du planning (timezone Madagascar)
- `pers` : Surnom employé
- `fournisseur_nom` : `detail.fournisseur.nom_fournisseur`
- `activ` : `base.base_diamex`

---

## 🔄 Workflow complet

### 1. Caissière scanne/saisit numéro de ticket
**API** : `api_scanner_ticket()`
- Recherche PlanningDetail par `numero_bon_livraison`, `numero_bon_avance`, ou `numeroDiameX`
- Vérifie `utilise=True` et `retour=False`
- Détermine le type (recette, avance, livraison)
- Retourne `apercu_diamex` **seulement si recette ou avance** (null pour livraison)

### 2. Frontend affiche aperçu
- Si `apercu_diamex` est null (livraison) : Pas d'aperçu DiameX
- Si recette/avance : Affiche tableau avec données qui seront créées

### 3. Caissière valide le retour
**API** : `api_valider_retour_ticket()`

**Pour recettes et avances** :
1. Marque `PlanningDetail.retour = True`, `date_retour = now()`
2. Crée ligne dans `TemporaireDiameX` avec toutes les colonnes remplies
3. Retourne succès

**Pour bons de livraison** :
1. Marque `PlanningDetail.retour = True`, `date_retour = now()`
2. **Ne crée PAS de ligne DiameX**
3. Crée mouvement stock (entrée) et met à jour quantité
4. Retourne succès avec impact stock

---

## 📊 Exemple complet : Paiement forfaitaire

### Données entrée
- Ticket trouvé : PlanningDetail avec `designation.type_avance_caissiere = "Recette"`
- Numéro ticket : "123456" (numeroDiameX)
- Montant : 75000 Ar
- Employé : Victorien
- Ouvrage : Ambohimanga (base: BASE001)
- Date planning : 2025-01-15

### Ligne TemporaireDiameX créée
```json
{
  "planning_detail_id": "uuid...",
  "numero_ticket": "123456",
  "type_ticket": "recette",
  "designation": "Paiement forfaitaire",
  "quantite": 1.00,
  "prix_unitaire": 75000.00,
  "montant": 75000.00,

  "journal": "00PERS",
  "datem": "2025-01",
  "rec": 0,
  "date_rec": "2025-01-15",
  "description": "_Paiement forfaitaire_Ambohimanga_75000",
  "in_amount": 75000.00,
  "out_amount": 0.00,
  "cat": "748411",
  "pers": "Victorien",
  "fournisseur_nom": null,
  "activ": "BASE001",

  "employe_id": "...",
  "ouvrage_id": "...",
  "point_eau_id": "...",
  "traite_par_id": "...",
  "statut": "en_attente",
  "date_traitement": "2025-01-15 10:30:00"
}
```

---

## 📊 Exemple complet : Avance essence

### Données entrée
- Ticket trouvé : PlanningDetail avec `designation.type_avance_caissiere = "Avance"`
- Numéro ticket : "AV-2025-050" (numero_bon_avance)
- Planning contient 2 lignes : "Essence" (20L), "Huile moteur" (2L)
- Montant total : 100000 Ar
- Employé : Jean
- Ouvrage : Analavory (base: BASE002)
- Fournisseur : Total (NIF: 123456789, prestation: True)
- Compte : "605100"
- Date planning : 2025-01-20

### Ligne TemporaireDiameX créée
```json
{
  "planning_detail_id": "uuid...",
  "numero_ticket": "AV-2025-050",
  "type_ticket": "avance",
  "designation": "Essence",
  "quantite": 20.00,
  "prix_unitaire": 5000.00,
  "montant": 100000.00,

  "journal": "00PERS",
  "datem": "2025-01",
  "rec": 0,
  "date_rec": "2025-01-20",
  "description": "123456789_PREST_Essence_Huile moteur_100000",
  "in_amount": 0.00,
  "out_amount": 100000.00,
  "cat": "605100",
  "pers": "Jean",
  "fournisseur_nom": "Total",
  "activ": "BASE002",

  "employe_id": "...",
  "ouvrage_id": "...",
  "fournisseur_id": "...",
  "traite_par_id": "...",
  "statut": "en_attente",
  "date_traitement": "2025-01-20 14:15:00"
}
```

---

## 🧪 Tests à effectuer

### Test 1 : Paiement forfaitaire (recette)
1. Chercher un ticket avec `designation.type_avance_caissiere = "Recette"`
2. Scanner/saisir le numéro
3. Vérifier que l'aperçu DiameX s'affiche
4. Valider le retour
5. Vérifier dans la table `temporaire_diamex` :
   - ✅ `in_amount` = montant
   - ✅ `out_amount` = 0
   - ✅ `cat` = "748411"
   - ✅ `description` commence par "_Paiement forfaitaire_"

### Test 2 : Avance
1. Chercher un ticket avec `designation.type_avance_caissiere = "Avance"`
2. Scanner/saisir le numéro
3. Vérifier que l'aperçu DiameX s'affiche
4. Valider le retour
5. Vérifier dans la table `temporaire_diamex` :
   - ✅ `in_amount` = 0
   - ✅ `out_amount` = montant
   - ✅ `cat` = code compte depuis PlanningDetail
   - ✅ `description` contient NIF + PREST (si applicable) + désignations

### Test 3 : Bon de livraison
1. Chercher un ticket avec `designation.type_avance_caissiere = "Bon de livraison"`
2. Scanner/saisir le numéro (ex: BL-2025-009)
3. Vérifier que l'aperçu DiameX **NE S'AFFICHE PAS**
4. Valider le retour
5. Vérifier :
   - ✅ **Aucune ligne créée dans `temporaire_diamex`**
   - ✅ Mouvement stock créé
   - ✅ Quantité stock mise à jour

---

## 📍 Fichiers modifiés

1. **apps/billing/models.py** (lignes 238, 474-485)
   - Ajout champ `prestation` au modèle Fournisseur
   - Ajout 11 colonnes DiameX au modèle TemporaireDiameX

2. **apps/billing/views_caissiere.py** (lignes 143-159, 214-338)
   - Modification `api_scanner_ticket()` pour aperçu conditionnel
   - Modification `api_valider_retour_ticket()` pour remplissage complet colonnes DiameX

3. **templates/billing/traitement_retours_caissiere.html** (lignes 195-198, 555-584)
   - Ajout message info pour livraisons
   - Modification JavaScript `afficherApercuDiameX()` pour gérer apercu null

4. **apps/billing/migrations/0026_...py**
   - Migration créée et appliquée

---

## 🎯 Prochaines étapes

### Workflow suivant (étape 5)
1. **Export DiameX** : Créer une vue pour exporter les lignes `statut='en_attente'` vers les fichiers Access DiameX
2. **Mise à jour Rec** : Définir le numéro `rec` lors de l'export
3. **Changement statut** : Marquer `statut='envoye'` après export réussi
4. **Gestion erreurs** : Logger dans `erreur_message` si échec

### Tests manuels requis
1. ✅ Vérifier que les bases ont un `journal_retour` défini
2. ✅ Vérifier que les fournisseurs ont `numero_nif` et `prestation` remplis
3. ✅ Vérifier que les PlanningDetail ont un `compte` renseigné
4. ✅ Tester avec de vraies données de production

### Améliorations possibles
1. Ajouter validation du format NIF (10 chiffres)
2. Ajouter logs détaillés pour traçabilité
3. Créer rapport de contrôle avant export DiameX
4. Interface admin Django pour gérer table temporaire

---

## ✅ Résumé

**Implémentation terminée** :
- ✅ Champs modèles ajoutés
- ✅ Migrations appliquées
- ✅ Logique de remplissage implémentée selon règles métier
- ✅ Différenciation recette/avance/livraison
- ✅ Bons de livraison exclus de DiameX
- ✅ Frontend adapté avec aperçu conditionnel
- ✅ Timezone Madagascar respectée
- ✅ Règles de description complexes implémentées

**Tests à effectuer** :
- ⏳ Test avec ticket recette réel
- ⏳ Test avec ticket avance réel (avec fournisseur NIF + PREST)
- ⏳ Test avec bon de livraison (vérifier absence ligne DiameX)
- ⏳ Vérification des données dans PostgreSQL

**État du serveur** : ✅ Démarré et prêt pour tests
**URL** : http://localhost:8000/facturation/caissiere/retours/
