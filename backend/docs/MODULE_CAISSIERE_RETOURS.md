# Module Caissière - Traitement des retours de tickets

## 📋 Vue d'ensemble

Ce module permet à la caissière de traiter les retours de tickets de caisse (bons de livraison, avances, recettes/paiements forfaitaires) après leur utilisation par les agents sur le terrain.

## 🎯 Fonctionnalités principales

### 1. Scanner QR Code
- **Technologie** : Bibliothèque ZXing JavaScript
- **Fonctionnement** : Active la caméra du device pour scanner le QR code imprimé sur le ticket
- **Auto-recherche** : Dès qu'un QR code est détecté, le système recherche automatiquement le ticket dans la base

### 2. Saisie manuelle
- **Fallback** : Si le scanner ne fonctionne pas ou si le QR code est illisible
- **Format** : Saisie du numéro de ticket affiché sur le document imprimé
- **Validation** : Le système vérifie que le ticket existe et est valide pour retour

### 3. Types de tickets traités

#### 📦 Bon de livraison
- **Vérification** : Le bon doit avoir été utilisé par l'agent (champ `utilise=True`)
- **Actions** :
  1. Marquer le détail comme retourné (`retour=True`, `date_retour=now()`)
  2. Créer une ligne dans `TemporaireDiameX` (type='livraison')
  3. **Impact stock** : Ajouter la quantité au stock de l'équipement
  4. Créer un mouvement de stock (type='entree')
- **Informations affichées** : Fournisseur, équipement, quantité, montant

#### 💰 Avance
- **Vérification** : L'avance doit avoir été utilisée par l'agent
- **Actions** :
  1. Marquer comme retourné
  2. Créer une ligne dans `TemporaireDiameX` (type='avance')
  3. Prêt pour transmission à la comptabilité
- **Informations affichées** : Désignation, montant, employé, ouvrage

#### 💵 Recette / Paiement forfaitaire
- **Vérification** : Le paiement doit avoir été collecté par l'agent
- **Actions** :
  1. Marquer comme retourné
  2. Créer une ligne dans `TemporaireDiameX` (type='recette')
  3. Prêt pour transmission à DiameX
- **Informations affichées** : Point d'eau, abonné, montant collecté

## 🗄️ Architecture base de données

### Table `temporaire_diamex`

Stockage temporaire avant envoi vers DiameX (système externe de gestion financière).

```python
class TemporaireDiameX(models.Model):
    # Identification
    id = UUIDField
    numero_ticket = CharField(50)  # Numéro du bon/facture
    type_ticket = CharField(choices=['livraison', 'avance', 'recette'])

    # Référence
    planning_detail = ForeignKey(PlanningDetail)

    # Données financières
    designation = CharField(255)
    quantite = DecimalField
    prix_unitaire = DecimalField
    montant = DecimalField

    # Contexte
    employe = ForeignKey(Employe)
    ouvrage = ForeignKey(Ouvrage)
    point_eau = ForeignKey(PointEau, null=True)  # Pour recettes
    fournisseur = ForeignKey(Fournisseur, null=True)  # Pour livraisons
    equipement_constitutif = ForeignKey(EquipementConstitutif, null=True)

    # Traçabilité
    statut = CharField(choices=['en_attente', 'envoye', 'erreur'])
    traite_par = ForeignKey(User)  # Caissière
    date_ticket = DateField
    date_traitement = DateTimeField(auto_now_add=True)
    date_envoi_diamex = DateTimeField(null=True)

    # Logs
    erreur_message = TextField(null=True)
```

## 🔄 Workflow complet

```
1. Agent terrain utilise un ticket (livraison/avance/paiement)
   └─> PlanningDetail.utilise = True
   └─> PlanningDetail.numeroDiameX / numeroBonLivraison = généré

2. Agent retourne le ticket physique à la caissière

3. Caissière scanne/saisit le numéro
   └─> API vérifie : utilise=True, retour=False

4. Caissière valide le retour
   └─> PlanningDetail.retour = True, date_retour = now()
   └─> Création ligne TemporaireDiameX (statut='en_attente')
   └─> Si livraison : MAJ stock automatique

5. Export périodique vers DiameX
   └─> Lignes avec statut='en_attente' sont envoyées
   └─> Après succès : statut='envoye', date_envoi_diamex=now()
   └─> En cas d'erreur : statut='erreur', erreur_message
```

## 📡 APIs disponibles

### `POST /billing/caissiere/api/scanner-ticket/`
**Rechercher un ticket par son numéro**

**Request :**
```json
{
  "numero_ticket": "BL-2025-001234"
}
```

**Response (succès) :**
```json
{
  "success": true,
  "ticket": {
    "numero_ticket": "BL-2025-001234",
    "type_ticket": "livraison",
    "detail_id": "uuid",
    "designation": "Tuyau PVC Ø20mm",
    "quantite": 50,
    "prix_unitaire": 2500,
    "montant": 125000,
    "date_planning": "2025-01-15",
    "employe": "Victorien",
    "ouvrage": "Ambohitrimanjaka",
    "fournisseur": "JIRAMA Supplies",
    "equipement": "Tuyau PVC"
  }
}
```

**Response (erreur) :**
```json
{
  "success": false,
  "error": "Ticket BL-2025-001234 non trouvé"
}
```

### `POST /billing/caissiere/api/valider-retour/`
**Valider le retour d'un ticket**

**Request :**
```json
{
  "detail_id": "uuid",
  "numero_ticket": "BL-2025-001234"
}
```

**Response (succès) :**
```json
{
  "success": true,
  "message": "Ticket BL-2025-001234 retourné avec succès",
  "ligne_diamex_id": "uuid",
  "stock_impact": {
    "equipement": "Tuyau PVC Ø20mm",
    "quantite_ajoutee": 50,
    "nouveau_stock": 245
  }
}
```

### `GET /billing/caissiere/api/liste-lignes-diamex/`
**Liste des lignes temporaires DiameX**

**Query params :**
- `statut` : en_attente, envoye, erreur
- `type_ticket` : livraison, avance, recette
- `date_debut` : YYYY-MM-DD
- `date_fin` : YYYY-MM-DD

**Response :**
```json
{
  "success": true,
  "lignes": [
    {
      "id": "uuid",
      "numero_ticket": "BL-2025-001234",
      "type_ticket": "Bon de livraison",
      "designation": "Tuyau PVC Ø20mm",
      "quantite": 50,
      "montant": 125000,
      "employe": "Victorien",
      "ouvrage": "Ambohitrimanjaka",
      "statut": "En attente d'envoi",
      "date_traitement": "15/01/2025 14:30"
    }
  ],
  "total": 1
}
```

## 🎨 Interface utilisateur

### Onglet 1 : Scanner QR
- Affichage vidéo de la caméra
- Overlay avec ligne de scan animée
- Détection automatique du QR code
- Arrêt automatique après détection

### Onglet 2 : Saisie manuelle
- Champ de saisie large avec focus automatique
- Bouton de recherche
- Support du scan avec douchette laser (input rapide + Enter)

### Zone de détails du ticket
- Badge coloré selon le type (🔵 livraison, 🔵 avance, 🟡 recette)
- Affichage de toutes les informations pertinentes
- Bouton "Valider le retour" en vert

### Liste des derniers tickets traités
- Tableau avec 20 derniers tickets
- Filtrable en temps réel
- Badges de statut colorés

## 🔒 Sécurité et validations

### Vérifications backend
1. ✅ Le ticket existe dans la base
2. ✅ Le ticket a été utilisé (`utilise=True`)
3. ✅ Le ticket n'est pas déjà retourné (`retour=False`)
4. ✅ L'utilisateur est authentifié
5. ✅ Transaction atomique pour éviter les doublons

### Gestion d'erreurs
- Ticket non trouvé → Message clair avec numéro
- Ticket déjà retourné → Affichage de la date de retour précédente
- Ticket pas encore utilisé → Message explicatif
- Erreur réseau → Toast d'erreur avec retry possible

## 📊 Statistiques en temps réel

Le dashboard affiche :
- **En attente** : Nombre de lignes à envoyer vers DiameX
- **Envoyé** : Nombre de lignes transmises avec succès
- **Erreurs** : Nombre de lignes en échec d'envoi
- **Montant total** : Somme des montants en attente (Ar)

## 🚀 Prochaines étapes

### À implémenter
1. **Export vers DiameX** : Script/API pour envoyer les lignes en attente
2. **Retry automatique** : Réessayer les lignes en erreur
3. **Notifications** : Alerter quand le nombre de lignes en attente dépasse un seuil
4. **Rapports** : Export Excel des lignes traitées par période
5. **Intégration comptabilité** : Transmission avances vers module comptabilité

### Améliorations possibles
- Support de plusieurs caméras (sélection)
- Mode batch : scanner plusieurs tickets d'affilée
- Historique de scan avec undo
- Statistiques par caissière
- Graphiques d'évolution des retours

## 🔗 Accès

**URL** : `/billing/caissiere/retours/`

**Menu** :
- Navigation principale : Plannings → Caissière - Retours → Scanner/Traiter tickets
- Mobile : Menu hamburger → Plannings → Caissière - Retours

**Permissions** : Utilisateur authentifié (login requis)
