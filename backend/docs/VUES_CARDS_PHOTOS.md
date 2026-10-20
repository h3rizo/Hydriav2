# Documentation - Vues Cards avec Photos

## 📋 Vue d'ensemble

Ajout de vues en mode "cards" (grille) pour les pages consolidées de Points d'Eau et Équipements, avec gestion complète des photos.

## ✨ Fonctionnalités implémentées

### 1. Toggle Vue Table/Cards

**Emplacement** : Header des pages
- Bouton pour basculer entre vue tableau (défaut) et vue cards
- Mémorisation du choix dans `localStorage`
- Icônes Font Awesome : `fa-table` et `fa-th-large`

**Pages concernées** :
- `/facturation/consolidated-points-eau/`
- `/consolidated-equipements/`

### 2. Vue Cards - Points d'Eau

**Template** : `backend/templates/billing/consolidated_points_eau.html`

**Grille responsive** :
- 1 colonne sur mobile
- 2 colonnes sur tablette (md)
- 3 colonnes sur desktop (lg)
- 4 colonnes sur grand écran (xl)

**Chaque card affiche** :
- **Photo principale** (figure 48px de hauteur)
  - Image si photos disponibles
  - Badge avec nombre de photos si > 1
  - Placeholder avec bouton "Ajouter" si aucune photo
- **Badge statut** : Actif (vert) ou Inactif (rouge)
- **Titre** : Nom de l'abonné
- **Type point d'eau** : Badge accent
- **IDxls** : Badge ghost avec police monospace
- **Infos géographiques** :
  - Ouvrage (avec icône building)
  - Village, Commune (avec icône map-marker)
  - Téléphone si disponible (avec icône phone)
- **Badges info** :
  - GPS : Vert si coordonnées, rouge sinon
  - Clôture : Badge warning si besoin
  - Date branchement
- **Actions** :
  - Bouton "Voir photos" si photos disponibles
  - Bouton "Modifier" pour ouvrir le modal existant

### 3. Vue Cards - Équipements

**Template** : `backend/templates/infrastructure/consolidated_equipements.html`

**Grille responsive** : Identique aux points d'eau

**Chaque card affiche** :
- **Photo principale** (figure 48px de hauteur)
  - Image si photos disponibles
  - Badge avec nombre de photos si > 1
  - Placeholder avec icône `fa-cogs` si aucune photo
- **Badge statut** :
  - Opérationnel (vert)
  - En panne (rouge)
  - En maintenance (warning)
  - Autres (ghost)
- **Titre** : Nom de l'équipement
- **Type équipement** : Badge accent
- **Ouvrage** : Nom avec icône building
- **Dans le village** : Icône home si applicable
- **Badge GPS** : Vert si coordonnées, rouge sinon
- **Actions** :
  - Bouton "Voir photos" si photos disponibles
  - Bouton "Modifier" pour ouvrir le modal existant

### 4. Modals de gestion des photos

**3 modals créés** :

#### a) Modal Upload (`uploadPhotoModal`)
- **Déclencheur** : Bouton "Ajouter" dans le placeholder photo
- **Fonction** : `openUploadPhotoModal(entityId, entityType, entityName)`
- **Champs** :
  - Input file multiple (accept="image/*")
  - Preview en grille 3 colonnes
  - Affichage de la taille de chaque photo
- **Validation** :
  - Max 5MB par photo (côté serveur)
  - Types acceptés : image/* (JPG, PNG, etc.)
- **Soumission** :
  - FormData avec CSRF token
  - Routes différentes selon type (point_eau / equipement)
  - Rechargement automatique après succès

#### b) Modal View Photos (`viewPhotosModal`)
- **Déclencheur** : Bouton "Voir photos" dans les actions
- **Fonction** : `viewPhotos(photos)` - reçoit un array JSON
- **Affichage** :
  - Grille 1 colonne (mobile) / 2 colonnes (desktop)
  - Images en taille réelle avec border
  - Description si disponible

#### c) Modal Edit (existant)
- Conservé tel quel
- Upload de photos disponible dans la section "Photos de l'équipement/du point d'eau"

### 5. APIs Backend

**Fichier créé** : `backend/apps/core/views_photos.py`

#### a) Upload Points d'Eau
```python
POST /facturation/api/point-eau/<uuid:point_eau_id>/upload-photos/
```

**Paramètres** :
- `photos` : Fichiers multiples (FormData)

**Traitement** :
- Validation taille (max 5MB par photo)
- Validation type (image/*)
- Génération nom unique avec UUID
- Stockage dans `media/photos/points_eau/<point_eau_id>/`
- Ajout métadonnées dans JSONField `PointEau.photos`

**Retour** :
```json
{
    "success": true,
    "nb_uploaded": 3,
    "total_photos": 5
}
```

#### b) Upload Équipements
```python
POST /api/equipement/<uuid:equipement_id>/upload-photos/
```

**Paramètres** : Identiques

**Traitement** :
- Stockage dans `media/photos/equipements/<equipement_id>/`
- Mise à jour `EquipementConstitutif.photos`

**Retour** : Identique

### 6. Structure des métadonnées photos (JSONField)

```json
[
  {
    "url": "/media/photos/points_eau/<id>/<uuid>.jpg",
    "filename": "<uuid>.jpg",
    "size": 1234567,
    "uploaded_at": "timestamp",
    "description": "optionnel"
  },
  ...
]
```

## 🔧 Configuration requise

### Settings Django

**MEDIA_ROOT et MEDIA_URL doivent être configurés** :

```python
# settings.py
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'
```

**Servir les fichiers media en développement** :

```python
# urls.py (projet principal)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ... vos routes
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### Structure des dossiers

```
backend/
├── media/
│   └── photos/
│       ├── points_eau/
│       │   └── <uuid>/
│       │       ├── <uuid1>.jpg
│       │       └── <uuid2>.png
│       └── equipements/
│           └── <uuid>/
│               ├── <uuid1>.jpg
│               └── <uuid2>.png
```

## 📁 Fichiers modifiés/créés

### Créés
1. `backend/apps/core/views_photos.py` - APIs upload photos
2. `backend/docs/VUES_CARDS_PHOTOS.md` - Cette documentation

### Modifiés
1. `backend/templates/billing/consolidated_points_eau.html`
   - Ajout toggle vue table/cards
   - Vue cards complète (lignes 220-357)
   - 3 modals (upload, view, edit existant)
   - JavaScript pour toggle, upload, view photos

2. `backend/templates/infrastructure/consolidated_equipements.html`
   - Ajout toggle vue table/cards
   - Vue cards complète (lignes 169-296)
   - 3 modals (upload, view, edit existant)
   - JavaScript pour toggle, upload, view photos

3. `backend/apps/billing/urls.py`
   - Import `views_photos`
   - Route `/api/point-eau/<uuid:point_eau_id>/upload-photos/`

4. `backend/apps/infrastructure/urls.py`
   - Import `views_photos`
   - Route `/api/equipement/<uuid:equipement_id>/upload-photos/`

## 🎨 Design Pattern

### Couleurs DaisyUI

- **Badge statut Actif** : `badge-success` (vert)
- **Badge statut Inactif** : `badge-error` (rouge)
- **Badge statut Opérationnel** : `badge-success` (vert)
- **Badge statut En panne** : `badge-error` (rouge)
- **Badge statut En maintenance** : `badge-warning` (orange)
- **Badge type** : `badge-accent`
- **Badge GPS disponible** : `badge-success`
- **Badge GPS manquant** : `badge-error`
- **Badge nombre photos** : `badge-primary`

### Icônes Font Awesome

- Points d'eau : `fa-tint`, `fa-camera-retro`
- Équipements : `fa-cogs`
- GPS : `fa-map-marker-alt`
- Photos : `fa-camera`, `fa-images`
- Actions : `fa-eye` (voir), `fa-edit` (modifier), `fa-upload`
- Infos : `fa-building` (ouvrage), `fa-phone`, `fa-home`

### Transitions

```css
class="hover:shadow-xl transition-shadow"
```

## 🧪 Tests suggérés

### Points d'Eau
1. ✅ Afficher la page `/facturation/consolidated-points-eau/`
2. ✅ Toggle vers vue cards
3. ✅ Cliquer "Ajouter" sur une card sans photo
4. ✅ Uploader 2-3 photos (JPG, PNG)
5. ✅ Vérifier badge "X photos" apparaît
6. ✅ Cliquer "Voir photos"
7. ✅ Vérifier localStorage conserve le choix cards/table

### Équipements
1. ✅ Afficher la page `/consolidated-equipements/`
2. ✅ Toggle vers vue cards
3. ✅ Cliquer "Ajouter" sur une card sans photo
4. ✅ Uploader des photos
5. ✅ Vérifier affichage correct

### Edge cases
1. ❌ Uploader fichier > 5MB → Doit être ignoré
2. ❌ Uploader fichier non-image → Doit être ignoré
3. ✅ Uploader 10 photos d'un coup → Toutes acceptées si < 5MB
4. ✅ Cliquer "Voir photos" quand 1 seule photo → Affichage correct
5. ✅ Rechargement page → Vue conservée (cards ou table)

## 📝 Notes techniques

### Pourquoi JSONField pour les photos ?

- **Flexibilité** : Métadonnées évolutives (description, tags, etc.)
- **Performance** : Pas de jointure SQL pour récupérer les photos
- **Migration** : Pas besoin de table séparée PhotoPointEau/PhotoEquipement

### Limitations

- **Pas de suppression individuelle** : Actuellement, on peut seulement ajouter
- **Pas de réorganisation** : Ordre d'ajout = ordre d'affichage
- **Pas de légendes** : Upload basique sans description

### Améliorations futures possibles

1. **Suppression de photos** : Bouton × dans le modal view
2. **Légendes** : Input description par photo lors de l'upload
3. **Drag & drop** : Réorganiser l'ordre des photos
4. **Crop/Resize** : Édition d'image avant upload
5. **Photo principale** : Sélectionner quelle photo afficher en premier
6. **Lightbox** : Affichage plein écran avec navigation
7. **Lazy loading** : Charger les images à la demande

## ✅ Statut

**TERMINÉ** - Fonctionnel et prêt pour utilisation en production

**Dernière mise à jour** : 15 décembre 2025
