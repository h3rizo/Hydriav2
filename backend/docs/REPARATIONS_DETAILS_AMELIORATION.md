# Améliorations Page Réparations - Affichage Détails et Bons de Livraison

## Date : 27 décembre 2025

## Vue d'ensemble
Enrichissement de la page de suivi des réparations (`/plannings/reparations/`) pour afficher les détails de planning (PlanningDetail) et les bons de livraison (BonLivraison) associés à chaque réparation.

## Modifications effectuées

### 1. Backend - API enrichie

**Fichier** : `backend/apps/planning/views_reparations_apis.py`

**Fonction modifiée** : `api_reparations_list()` (lignes 144-218)

**Ajouts** :
- Récupération des PlanningDetails liés à chaque Planning
- Pour chaque PlanningDetail, récupération des BonLivraison via la table de liaison `planningdetail_bonlivraison`
- Structure JSON enrichie avec informations complètes

**Structure de données retournée** :

```json
{
  "success": true,
  "reparations": [
    {
      "id": "uuid",
      "description": "Réparation fuite",
      "date_signalement": "2025-12-27",
      "statut": "en_cours",
      "details": [
        {
          "id": "uuid",
          "designation": "Tuyau PVC 1/2 pouce",
          "type_designation": "Achat matériel",
          "quantite": 5,
          "prix_unitaire": 2500.00,
          "montant": 12500.00,
          "equipement": "Réseau de distribution",
          "point_eau": "PE-001",
          "retour_caissiere": true,
          "date_retour": "2025-12-26",
          "bons_livraison": [
            {
              "id": "uuid",
              "numero": "BL-2025-001",
              "date_emission": "2025-12-20",
              "fournisseur": "Quincaillerie Soakoja",
              "statut": "livre",
              "montant_total": 12500.00
            }
          ]
        }
      ],
      "total_details": 1
    }
  ]
}
```

**Champs PlanningDetail inclus** :
- `designation` : Nom de la désignation
- `type_designation` : Type (Achat, Avance, Recette, etc.)
- `quantite` : Quantité commandée
- `prix_unitaire` : Prix unitaire en Ariary
- `montant` : Montant total (quantité × prix unitaire)
- `equipement` : Équipement constitutif concerné
- `point_eau` : Point d'eau concerné
- `retour_caissiere` : Boolean - Ticket retourné ou non
- `date_retour` : Date de retour du ticket

**Champs BonLivraison inclus** :
- `numero` : Numéro du bon de livraison
- `date_emission` : Date d'émission
- `fournisseur` : Nom du fournisseur
- `statut` : Statut du bon (en_attente, en_cours, livre, annule)
- `montant_total` : Montant total du bon

### 2. Frontend - Affichage dans le modal

**Fichier** : `backend/templates/planning/suivi_reparations.html`

**Fonction modifiée** : `displayReparationsList()` (lignes 1434-1510)

**Affichage ajouté** :

### 3. Frontend - Affichage dans la version imprimable

**Fichier** : `backend/templates/planning/reparations_print.html`

**Section ajoutée** : Lignes 367-472

**Affichage ajouté** :

#### Section Détails de Planning

Affichée uniquement si `rep.details` existe et contient au moins un élément.

**Titre de section** :
- Icône : `fas fa-list-ul` (bleu info)
- Texte : "Détails de planning (X)" avec compteur dynamique

**Tableau des détails** :
- Colonnes : Désignation, Type, Qté, P.U., Montant, Équipement, Point d'eau, Retour
- Style : `table table-xs table-zebra` (DaisyUI)
- Scroll horizontal automatique pour petits écrans

**Colonnes détaillées** :

| Colonne | Contenu | Format |
|---------|---------|--------|
| Désignation | Nom du produit/service | Texte en gras |
| Type | Type de désignation | Badge ghost |
| Qté | Quantité | Nombre aligné à droite |
| P.U. | Prix unitaire | Montant formaté (ex: 2 500 Ar) |
| Montant | Total (qté × P.U.) | Montant en gras |
| Équipement | Nom de l'équipement | Texte petit |
| Point d'eau | Code/nom du point d'eau | Texte petit |
| Retour | Statut retour caissière | Badge success/warning |

**Badge Retour** :
- ✅ **Vert avec check** : `retour_caissiere = True` + tooltip avec date
- ⏱️ **Jaune avec horloge** : `retour_caissiere = False` (en attente)

#### Sous-section Bons de Livraison

Affichée uniquement si `detail.bons_livraison` contient au moins un élément.

**Insertion** : Ligne expansible sous chaque détail concerné (colspan=8)

**Titre** :
- Icône : `fas fa-truck` (vert success)
- Texte : "Bons de livraison (X)" avec compteur

**Affichage des bons** :
- Layout : Flexbox horizontal avec gap
- Fond : `bg-base-200` (gris clair)
- Espacement : `p-2 rounded` (padding + coins arrondis)

**Informations par bon** :
1. **Numéro** : Police monospace en gras (ex: BL-2025-001)
2. **Date** : Date d'émission
3. **Fournisseur** : Nom du fournisseur (flex-1 pour prendre l'espace)
4. **Statut** : Badge coloré selon le statut
   - `livre` → Badge success (vert)
   - `en_cours` → Badge warning (jaune)
   - Autres → Badge ghost (gris)
5. **Montant** : Montant total formaté en Ariary

### 3. Corrections appliquées

#### Problème 1 : Accès au champ `volet`

**Fichier** : `backend/apps/billing/views_encaissement_forfaitaire.py` (lignes 112-118, 150-156)

**Erreur initiale** : `'Ouvrage' object has no attribute 'volet'`

**Cause** : Tentative d'accès direct à `ouvrage.volet` alors que le champ existe dans le modèle `Base`, pas `Ouvrage`

**Correction** : Utilisation de la chaîne de relations correcte :
```
Ouvrage → ModaliteGestion (date_fin=null) → Employe → Base → volet
```

**Code corrigé** :
```python
# Récupérer le volet depuis la Base de l'employé via ModaliteGestion
activ_value = None
if ouvrage_commun:
    # Ouvrage → ModaliteGestion (active) → Employe → Base → volet
    modalite = ouvrage_commun.modalites_gestion.filter(date_fin__isnull=True).first()
    if modalite and modalite.employe and modalite.employe.base:
        activ_value = modalite.employe.base.volet
```

**Point CRITICAL** : Toujours filtrer ModaliteGestion par `date_fin__isnull=True` pour obtenir uniquement les modalités actives.

## Workflow utilisateur

1. **Accéder à la page** : `http://localhost:8000/plannings/reparations/`

2. **Ouvrir les réparations d'un ouvrage** :
   - Cliquer sur "Voir réparations" dans la carte ou ligne d'un ouvrage
   - Le modal "Réparations - [Nom ouvrage]" s'ouvre

3. **Consulter les détails** :
   - Chaque réparation affiche ses informations de base (description, dates, statut)
   - Si la réparation a des détails de planning, une section "Détails de planning" apparaît
   - Le tableau montre tous les matériaux/services liés avec quantités et montants

4. **Consulter les bons de livraison** :
   - Si un détail a des bons de livraison associés, une ligne expansible apparaît
   - La sous-section liste tous les bons avec numéro, date, fournisseur, statut et montant
   - Permet de tracer la chaîne : Réparation → Détails → Bons → Fournisseur

## Avantages de cette amélioration

1. **Traçabilité complète** : De la réparation jusqu'au fournisseur
2. **Visibilité budgétaire** : Montants détaillés par ligne et par bon
3. **Suivi des retours** : Statut de retour caissière visible (tickets utilisés)
4. **Gestion des stocks** : Lien avec les bons de livraison pour inventaire
5. **Audit facilité** : Toutes les informations dans un seul écran

## Points techniques importants

### Relation ManyToMany BonLivraison ↔ PlanningDetail

La relation utilise une table intermédiaire `planningdetail_bonlivraison` avec les champs :
- `planning_detail_id` : UUID du PlanningDetail
- `bon_livraison_id` : UUID du BonLivraison

**Requête ORM** :
```python
bons_qs = BonLivraison.objects.filter(
    planningdetail_bonlivraison__planning_detail_id=detail.id
).select_related('fournisseur')
```

### Gestion des erreurs

**Principe** : Les erreurs dans les sections bonus (détails, bons) ne doivent PAS bloquer l'affichage des réparations principales.

**Implémentation** :
```python
try:
    # Requête bonus (bons de livraison)
    bons_qs = BonLivraison.objects.filter(...)
except Exception as e:
    pass  # Ignorer l'erreur, continuer avec bons=[]
```

### Formatage des montants

**JavaScript** :
```javascript
detail.montant.toLocaleString('fr-FR') + ' Ar'
```

**Résultat** : `12 500 Ar` (espace comme séparateur de milliers)

### Responsive design

**Tableau scroll** :
```html
<div class="overflow-x-auto">
    <table class="table table-xs">...</table>
</div>
```

Sur mobile, le tableau devient scrollable horizontalement au lieu de briser la mise en page.

## Tests de validation

- [x] Django check sans erreur
- [x] API retourne détails et bons correctement
- [x] Modal affiche section détails si données existent
- [x] Modal n'affiche PAS section détails si aucune donnée
- [x] Tableau responsive fonctionne sur mobile
- [x] Bons de livraison s'affichent en sous-ligne
- [x] Badges retour caissière corrects (vert/jaune)
- [x] Badges statut bon corrects (success/warning/ghost)
- [x] Montants formatés correctement (séparateur milliers)
- [x] Tooltip date de retour fonctionne

## Fichiers modifiés

1. `backend/apps/billing/views_encaissement_forfaitaire.py` (lignes 112-118, 150-156)
   - Correction accès au champ `volet`

2. `backend/apps/planning/views_reparations_apis.py` (lignes 144-218)
   - Enrichissement API avec PlanningDetails et BonLivraison

3. `backend/templates/planning/suivi_reparations.html` (lignes 1434-1510)
   - Affichage détails et bons dans le modal

## Prochaines améliorations possibles

1. **Export Excel** : Exporter les réparations avec détails et bons
2. **Filtres avancés** : Filtrer par type de désignation ou fournisseur
3. **Totaux** : Afficher le total des montants par réparation
4. **Photos** : Ajouter photos des travaux dans les détails
5. **Timeline** : Afficher la chronologie (planning → bon → livraison → retour)
6. **Notifications** : Alerter quand un bon est livré
7. **Liens directs** : Cliquer sur un bon pour ouvrir sa fiche complète

## Documentation associée

- `TIMEZONE_GUIDE.md` - Règles de gestion des dates (Indian/Antananarivo)
- `CLAUDE.md` - Section "RÈGLES AFFICHAGE EMPLOYÉS" (utilisation du surnom)
- Modèles Django :
  - `apps.planning.models.Planning`
  - `apps.planning.models.PlanningDetail`
  - `apps.billing.models.BonLivraison`
  - `apps.organization.models.Ouvrage`
  - `apps.organization.models.ModaliteGestion`

## Conclusion

Cette amélioration complète le workflow de gestion des réparations en offrant une visibilité complète depuis la réparation planifiée jusqu'aux matériaux livrés par les fournisseurs. La traçabilité est maintenant totale et facilite l'audit, la gestion budgétaire et le suivi des stocks.
