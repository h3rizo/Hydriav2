# Mapping des colonnes - Table TemporaireDiameX

## Vue d'ensemble
Ce document décrit comment remplir chaque colonne de la table `temporaire_diamex` lors du traitement d'un retour de ticket par la caissière.

## Source de données
**Objet principal**: `PlanningDetail` (récupéré via le numéro de ticket)

---

## Colonnes et leur remplissage

### 1. CHAMPS TECHNIQUES (gérés automatiquement)

| Colonne           | Type     | Source      | Remarque            |
|-------------------|----------|-------------|---------------------|
| `id`              | UUID     | Auto-généré | `uuid.uuid4()`      |
| `created_at`      | DateTime | Auto        | `auto_now_add=True` |
| `updated_at`      | DateTime | Auto        | `auto_now=True`     |
| `date_traitement` | DateTime | Auto        | `auto_now_add=True` - Date/heure du traitement par caissière |

---

### 2. RÉFÉRENCE AU PLANNING DETAIL (OBLIGATOIRE)

| Colonne           | Type       | Source              | Exemple               |
|-------------------|------------|---------------------|-----------------------|
| `planning_detail` | ForeignKey | `PlanningDetail.id` | UUID du détail trouvé |

**Code**:
```python
planning_detail=detail  # L'objet PlanningDetail trouvé
```

---

### 3. INFORMATIONS DU TICKET (OBLIGATOIRES)

| Colonne          | Type           | Source                                     | Logique                             |
|------------------|----------------|--------------------------------------------|-------------------------------------|
| `numero_ticket`  | CharField(50)  | Variable selon type                        | Voir tableau ci-dessous             |
| `type_ticket`    | CharField(20)  | `detail.designation.type_avance_caissiere` | 'livraison', 'avance', ou 'recette' |
| `designation`    | CharField(255) | `detail.designation.nom`                   | Nom de la désignation               |
| `quantite`       | Decimal(10,2)  | `detail.quantity`                          | Quantité (défaut: 0)                |
| `prix_unitaire`  | Decimal(15,2)  | `detail.pu`                                | Prix unitaire (défaut: 0)           |
| `montant`        | Decimal(15,2)  | `detail.montant`                           | Montant total (défaut: 0)           |
| `date_ticket`    | Date           | `detail.planning.date`                     | Date du planning (converti en date) |

#### Détermination du numéro de ticket

```python
# Ordre de priorité pour récupérer le numéro
if detail.numero_bon_livraison:
    numero_ticket = detail.numero_bon_livraison  # Ex: "BL-2025-009"
elif detail.numero_bon_avance:
    numero_ticket = detail.numero_bon_avance     # Ex: "AV-2025-123"
elif detail.numeroDiameX:
    numero_ticket = str(detail.numeroDiameX)     # Ex: "456789"
else:
    numero_ticket = f"TICKET-{detail.id[:8]}"    # Fallback
```

#### Détermination du type de ticket

```python
type_ticket = 'livraison'  # Par défaut

if detail.designation and detail.designation.type_avance_caissiere:
    type_avance = detail.designation.type_avance_caissiere.lower()

    if 'recette' in type_avance:
        type_ticket = 'recette'
    elif 'avance' in type_avance:
        type_ticket = 'avance'
    elif 'bon de livraison' in type_avance or 'livraison' in type_avance:
        type_ticket = 'livraison'
```

---

### 4. INFORMATIONS CONTEXTUELLES (OPTIONNELLES)

| Colonne                  | Type       | Source                          | Condition                            |
|--------------------------|------------|---------------------------------|--------------------------------------|
| `employe`                | ForeignKey | `detail.planning.employe`       | Si planning existe                   |
| `ouvrage`                | ForeignKey | `detail.planning.ouvrage`       | Si planning existe                   |
| `point_eau`              | ForeignKey | `detail.point_eau`              | Pour recettes/paiements forfaitaires |
| `fournisseur`            | ForeignKey | `detail.fournisseur`            | Pour bons de livraison               |
| `equipement_constitutif` | ForeignKey | `detail.equipement_constitutif` | Pour bons de livraison               |

**Code**:
```python
employe = detail.planning.employe if detail.planning else None
ouvrage = detail.planning.ouvrage if detail.planning else None
point_eau = detail.point_eau if detail.point_eau else None
fournisseur = detail.fournisseur if detail.fournisseur else None
equipement_constitutif = detail.equipement_constitutif if detail.equipement_constitutif else None
```

---

### 5. GESTION DU STATUT ET TRAÇABILITÉ

| Colonne             | Type             | Source         | Valeur par défaut                   |
|---------------------|------------------|----------------|-------------------------------------|
| `statut`            | CharField(20)    | Manuel         | `'en_attente'`                      |
| `traite_par`        | ForeignKey(User) | `request.user` | Utilisateur connecté (caissière)    |
| `date_envoi_diamex` | DateTime         | NULL           | Rempli lors de l'export vers DiameX |
| `erreur_message`    | TextField        | NULL           | Rempli si erreur lors de l'export   |

**Choix de statut**:
- `'en_attente'`: Ligne créée, en attente d'export vers DiameX (défaut)
- `'envoye'`: Ligne exportée avec succès vers DiameX
- `'erreur'`: Erreur lors de l'export (voir `erreur_message`)

---

## Exemple complet de création

### Cas 1: Bon de livraison (BL-2025-009)

```python
from django.utils import timezone
from apps.billing.models import TemporaireDiameX

# detail = PlanningDetail trouvé via numero_bon_livraison='BL-2025-009'

ligne_diamex = TemporaireDiameX.objects.create(
    # Référence
    planning_detail=detail,

    # Ticket
    numero_ticket='BL-2025-009',
    type_ticket='livraison',
    designation='Cadenas PM',
    quantite=1.0,
    prix_unitaire=14000.00,
    montant=14000.00,
    date_ticket=detail.planning.date.date(),

    # Contexte
    employe=detail.planning.employe,
    ouvrage=detail.planning.ouvrage,
    fournisseur=detail.fournisseur,           # IMPORTANT pour livraisons
    equipement_constitutif=detail.equipement_constitutif,  # IMPORTANT pour livraisons

    # Traçabilité
    statut='en_attente',
    traite_par=request.user,
)
```

**Résultat**:
- Ligne créée dans `temporaire_diamex`
- Stock mis à jour: `Stock[Cadenas PM].quantite_actuelle += 1`
- `PlanningDetail.retour = True`, `date_retour = maintenant`

---

### Cas 2: Avance (AV-2025-050)

```python
ligne_diamex = TemporaireDiameX.objects.create(
    # Référence
    planning_detail=detail,

    # Ticket
    numero_ticket='AV-2025-050',
    type_ticket='avance',
    designation='Essence',
    quantite=20.0,
    prix_unitaire=5000.00,
    montant=100000.00,
    date_ticket=detail.planning.date.date(),

    # Contexte
    employe=detail.planning.employe,
    ouvrage=detail.planning.ouvrage,
    fournisseur=None,                  # Pas de fournisseur pour avances
    equipement_constitutif=None,       # Pas d'équipement pour avances
    point_eau=None,                    # Pas de point d'eau pour avances

    # Traçabilité
    statut='en_attente',
    traite_par=request.user,
)
```

**Résultat**:
- Ligne créée dans `temporaire_diamex`
- PAS d'impact stock (avance = dépense)
- Sera transmis à la comptabilité via export DiameX
- `PlanningDetail.retour = True`, `date_retour = maintenant`

---

### Cas 3: Recette/Paiement forfaitaire (numéro DiameX: 123456)

```python
ligne_diamex = TemporaireDiameX.objects.create(
    # Référence
    planning_detail=detail,

    # Ticket
    numero_ticket='123456',
    type_ticket='recette',
    designation='Paiement forfaitaire',
    quantite=1.0,
    prix_unitaire=75000.00,
    montant=75000.00,
    date_ticket=detail.planning.date.date(),

    # Contexte
    employe=detail.planning.employe,
    ouvrage=detail.planning.ouvrage,
    point_eau=detail.point_eau,        # IMPORTANT pour recettes
    fournisseur=None,                  # Pas de fournisseur pour recettes
    equipement_constitutif=None,       # Pas d'équipement pour recettes

    # Traçabilité
    statut='en_attente',
    traite_par=request.user,
)
```

**Résultat**:
- Ligne créée dans `temporaire_diamex`
- PAS d'impact stock (recette = encaissement)
- Sera transmis à la comptabilité via export DiameX
- `PlanningDetail.retour = True`, `date_retour = maintenant`

---

## Actions post-création

### 1. Pour tous les types
```python
# Marquer le détail comme retourné
detail.retour = True
detail.date_retour = timezone.now()
detail.save()
```

### 2. Spécifique aux bons de livraison
```python
if type_ticket == 'livraison' and detail.equipement_constitutif:
    from apps.inventory.models import Stock, StockMovement
    from decimal import Decimal

    # Récupérer ou créer le stock
    stock, created = Stock.objects.get_or_create(
        equipement=detail.equipement_constitutif
    )

    # Créer mouvement d'entrée
    mouvement = StockMovement.objects.create(
        stock=stock,
        type_mouvement='entree',
        quantite=detail.quantity or 0,
        motif=f'Retour bon de livraison {numero_ticket}',
        reference=numero_ticket,
        created_by=request.user
    )

    # Mettre à jour quantité en stock
    stock.quantite_actuelle += Decimal(str(detail.quantity or 0))
    stock.save()
```

---

## Affichage de l'aperçu (Frontend)

### Colonnes à afficher dans le tableau d'aperçu

| Colonne affichée | Source                             |
|------------------|------------------------------------|
| N° Ticket        | `numero_ticket`                    |
| Type             | Badge coloré selon `type_ticket`   |
| Désignation      | `designation`                      |
| Quantité         | `quantite`                         |  
| Prix unitaire    | `prix_unitaire` + " Ar"            |
| Montant          | `montant` + " Ar" (en gras)        |
| Employé          | `employe.surnom`                   |
| Ouvrage          | `ouvrage.nom_ouvrage`              |
| Date             | `date_ticket` (format DD/MM/YYYY)  |
| Statut           | Badge "En attente" (warning)       |

### Champs conditionnels (selon type)

**Pour livraisons**:
- Fournisseur: `fournisseur.nom_fournisseur`
- Équipement: `equipement_constitutif.nom`

**Pour recettes**:
- Point d'eau: `point_eau.idxls` ou `point_eau.nomabonne`

**Pour avances**:
- Aucun champ supplémentaire

---

## Questions pour ajustement

1. **Format de `date_ticket`**: Faut-il stocker la date complète du planning ou juste la partie date ?
   - ✅ Proposition: Utiliser `.date()` pour avoir uniquement la date (YYYY-MM-DD)

2. **Numéro de ticket manquant**: Que faire si aucun numéro n'existe ?
   - ✅ Proposition: Générer `"TICKET-{uuid[:8]}"` comme fallback

3. **Champs NULL vs valeurs par défaut**:
   - ✅ Proposition actuelle: Laisser NULL pour les FK optionnelles, 0 pour quantité/prix/montant

4. **Validation avant création**:
   - Vérifier que `detail.utilise == True`
   - Vérifier que `detail.retour == False`
   - ✅ Déjà fait dans l'API `api_scanner_ticket()`

5. **Colonnes supplémentaires nécessaires** ?
   - Ex: `village`, `fokontany`, `commune` pour géolocalisation ?
   - Ex: `compte_comptable` pour ventilation comptable ?

---

## Résumé du workflow

```
1. Caissière scanne/saisit numéro de ticket
   └─> API recherche PlanningDetail

2. API retourne aperçu avec toutes les données
   └─> Frontend affiche aperçu dans tableau

3. Caissière valide le retour
   └─> API crée ligne TemporaireDiameX
   └─> Marque PlanningDetail.retour = True
   └─> Si livraison: Impact stock (+quantité)
   └─> Retourne succès avec message

4. Plus tard: Export vers DiameX
   └─> Récupère lignes avec statut='en_attente'
   └─> Envoie vers système externe DiameX
   └─> Met à jour statut='envoye' + date_envoi_diamex
```

---

## Prochaines étapes suggérées

1. ✅ Valider ce mapping avec l'utilisateur
2. Ajuster les champs si nécessaire
3. Implémenter la création complète dans `api_valider_retour_ticket()`
4. Tester avec les 3 types de tickets
5. Créer la vue/export DiameX pour vider la table temporaire
