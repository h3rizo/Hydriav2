# Navigation Module Paiements Cartes Sociales

## Date : 16 décembre 2025

## Structure de navigation complète

### Point d'entrée principal : Vue Globale

**Accès depuis les menus** :
- **Menu Desktop** : Tableaux & Rapports → Rapports & Analyses → "Paiements cartes sociales"
- **Menu Mobile** : Rapports → "Paiements cartes sociales"

**URL** : `/plannings/conso-cartes-sociales/global/`

### Navigation depuis la Vue Globale

**Boutons dans l'en-tête** (ligne 14-21) :
1. **Vue Détaillée** (bouton bleu info)
   - Icône : `fa-list`
   - URL : `/plannings/conso-cartes-sociales/`
   - Affiche : Hiérarchie complète Région → District → Commune → Ouvrage → Point d'Eau

2. **Imprimer** (bouton bleu primary)
   - Icône : `fa-print`
   - URL : `/plannings/conso-cartes-sociales/impression/?annee=...&communes=...&ouvrage=...`
   - Ouvre : Nouvelle fenêtre (target="_blank")
   - Conserve : Filtres appliqués (année, communes, ouvrage)

### Navigation depuis la Vue Détaillée

**Boutons dans l'en-tête de conso_cartes_sociales.html** :
- **Vue Globale** → Retour vers `/plannings/conso-cartes-sociales/global/`
- **Imprimer** → Vue impression avec filtres

### Architecture des 3 pages

```
┌─────────────────────────────────────────────────────────────┐
│                      VUE GLOBALE                            │
│  /plannings/conso-cartes-sociales/global/                  │
│                                                             │
│  📊 Point d'entrée principal depuis menu                    │
│  ✓ Structure hiérarchique pliable                          │
│  ✓ Stats agrégées Région/District/Commune                  │
│  ✓ Modal détails commune (AJAX)                            │
│  ✓ Pas de scroll pour voir détails                         │
│                                                             │
│  Boutons navigation:                                        │
│  → Vue Détaillée | Imprimer                                │
└─────────────────────────────────────────────────────────────┘
                    ↓ Vue Détaillée
┌─────────────────────────────────────────────────────────────┐
│                    VUE DÉTAILLÉE                            │
│  /plannings/conso-cartes-sociales/                         │
│                                                             │
│  📋 Hiérarchie complète jusqu'aux points d'eau             │
│  ✓ Région → District → Commune → Ouvrage → Point d'Eau    │
│  ✓ Liste exhaustive avec tous les détails                  │
│  ✓ Nécessite scroll pour navigation                        │
│                                                             │
│  Boutons navigation:                                        │
│  ← Vue Globale | Imprimer                                  │
└─────────────────────────────────────────────────────────────┘
                    ↓ Imprimer
┌─────────────────────────────────────────────────────────────┐
│                   VUE IMPRESSION                            │
│  /plannings/conso-cartes-sociales/impression/              │
│                                                             │
│  🖨️ Page optimisée pour impression papier (Paysage)        │
│  ✓ Affichage carte par carte (regroupé par PE)            │
│  ✓ Hiérarchie: Commune → Ouvrage → Point d'Eau → Cartes   │
│  ✓ Colonnes: N° Carte, Bénéficiaire, Habitants, 12 mois   │
│  ✓ Mois affichés avec icônes: ✓ (payé) / ✗ (non payé)    │
│  ✓ Sous-totaux à chaque niveau (PE, Ouvrage, Commune)     │
│  ✓ Saut de page entre communes                            │
│  ✓ Filtres conservés (année/communes/ouvrage)             │
│  ❌ Pas de colonnes montant (supprimées)                   │
│                                                             │
│  Action: Ctrl+P (impression navigateur)                    │
│  Documentation: docs/IMPRESSION_CARTES_SOCIALES.md         │
└─────────────────────────────────────────────────────────────┘
```

## Cas d'usage recommandés

### 1. Consultation rapide par commune
**Utiliser** : Vue Globale → Clic sur région/district → Clic "Détails" sur commune
- ✅ Pas de changement de page
- ✅ Modal AJAX rapide
- ✅ Retour facile (fermer modal)

### 2. Analyse exhaustive d'une commune
**Utiliser** : Vue Globale → "Vue Détaillée" → Scroll jusqu'à commune
- ✅ Voir tous les points d'eau avec détails
- ✅ Navigation hiérarchique complète
- ⚠️ Nécessite scroll si beaucoup de données

### 3. Impression d'un rapport
**Utiliser** : Vue Globale → Appliquer filtres → "Imprimer"
- ✅ Conserve les filtres appliqués
- ✅ Format optimisé papier
- ✅ Ouvre dans nouvelle fenêtre

## Filtres disponibles

**Communs aux 3 pages** :
1. **Année** : Dropdown (2024, 2025, 2026)
2. **Région** : Liste déroulante
3. **District** : Liste déroulante
4. **Commune(s)** : Sélection multiple
5. **Ouvrage** : Liste déroulante

**Comportement** :
- Les filtres sont appliqués avec le bouton "Filtrer"
- Bouton "Réinitialiser" recharge la page sans filtres
- Les filtres sont conservés lors de la navigation Globale ↔ Détaillée
- Les filtres sont passés en URL à la vue impression

## Hiérarchie des données

### Vue Globale (3 niveaux)
```
Région
├── District
│   ├── Commune 1
│   ├── Commune 2
│   └── Commune N
└── Stats agrégées à chaque niveau
```

### Vue Détaillée (5 niveaux)
```
Région
├── District
│   ├── Commune
│   │   ├── Ouvrage
│   │   │   ├── Point d'Eau 1
│   │   │   ├── Point d'Eau 2
│   │   │   └── Point d'Eau N
```

### Modal Détails Commune (1 niveau)
```
Commune (District, Région)
├── Stats globales commune
└── Liste points d'eau
    ├── PE 1 : Stats individuelles
    ├── PE 2 : Stats individuelles
    └── PE N : Stats individuelles
```

## Stats affichées

### Niveau Région/District
- Nombre de cartes sociales
- Factures payées
- Factures non payées
- Taux de paiement (%)

### Niveau Commune
- Nombre de cartes sociales
- Nombre de points d'eau
- Total factures
- Factures payées
- Factures non payées
- Taux de paiement (%)

### Niveau Point d'Eau (modal)
- Nom point d'eau
- Ouvrage
- Nombre de cartes
- Total factures
- Payées
- Non payées
- Taux (%)

## Liens dans le code

### Menus (base.html)
- **Desktop** : Ligne 480
- **Mobile** : Ligne 220

### Vue Globale (conso_cartes_sociales_global.html)
- **Bouton Vue Détaillée** : Ligne 15-17
- **Bouton Imprimer** : Ligne 18-20
- **Modal détails** : Ligne 247-293
- **JavaScript modal** : Ligne 299-396

### API détails commune
- **Vue** : `views_conso_cartes_sociales.py` ligne 250-367
- **URL** : `urls.py` ligne 106
- **Endpoint** : `/plannings/conso-cartes-sociales/api/commune/<uuid>/`

## Maintenance

### Ajouter une colonne dans le modal
1. Modifier API backend : `api_commune_details()` ligne 250+
2. Ajouter colonne dans template modal : ligne 269-277
3. Ajouter cellule dans JavaScript : ligne 357-377

### Modifier les stats affichées
1. Backend : `gestion_conso_cartes_sociales_global()` ligne 90-221
2. Template stats globales : ligne 24-50
3. Template accordéons : ligne 140-236

### Changer les icônes
- Région : `fa-globe` (ligne 148)
- District : `fa-city` (ligne 165)
- Commune : `fa-map-marker-alt` (ligne 195)
- Carte : `fa-credit-card` (menu)

## Tests de validation

- [x] Accès depuis menu desktop
- [x] Accès depuis menu mobile
- [x] Affichage hiérarchie pliable
- [x] Stats agrégées correctes
- [x] Clic "Détails" ouvre modal
- [x] Modal charge données AJAX
- [x] Modal affiche stats + tableau
- [x] Fermeture modal (X ou backdrop)
- [x] Navigation vers Vue Détaillée
- [x] Navigation vers Impression
- [x] Filtres conservés entre pages
- [x] Django check sans erreur
