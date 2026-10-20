# Remplacement des icônes PWA - Logo Vase Grecque Hydria

## Date
30 décembre 2025

## Objectif
Remplacer les icônes PWA par défaut (rond blanc sur fond bleu) par le logo de la vase grecque qui apparaît à côté du mot "Hydria" sur la page d'accueil.

## Changements effectués

### 1. Icônes principales (8 tailles)
Toutes les icônes PWA ont été remplacées par des versions redimensionnées du logo vase grecque :

- `icon-72x72.png` (6.3 KB)
- `icon-96x96.png` (9.6 KB)
- `icon-128x128.png` (15 KB)
- `icon-144x144.png` (18 KB)
- `icon-152x152.png` (20 KB)
- `icon-192x192.png` (29 KB)
- `icon-384x384.png` (106 KB)
- `icon-512x512.png` (180 KB)

### 2. Icônes de raccourcis (3 raccourcis)
Les icônes de raccourcis ont été créées avec la vase grecque sur des fonds colorés :

- `shortcut-feed.png` - Fond orange (#f97316) - Fil d'actualité
- `shortcut-planning.png` - Fond vert (#22c55e) - Plannings
- `shortcut-accounting.png` - Fond bleu (#3b82f6) - Comptabilité

### 3. Source du logo
**Fichier source** : `backend/static/images/logo.png`
- Dimensions : 1024x1024 pixels
- Format : PNG avec transparence (RGBA)
- Contenu : Vase grecque (logo Hydria)

### 4. Méthode de génération
Les icônes ont été générées automatiquement avec Python (PIL/Pillow) :

1. **Icônes principales** : Redimensionnement du logo avec algorithme LANCZOS pour haute qualité
2. **Icônes raccourcis** : Logo redimensionné à 70% et centré sur fond coloré

### 5. Configuration manifest.json
Le fichier `backend/static/manifest.json` n'a pas été modifié car il référence déjà les bons chemins :

```json
{
  "icons": [
    {
      "src": "/static/images/icons/icon-72x72.png",
      "sizes": "72x72",
      "type": "image/png",
      "purpose": "any maskable"
    },
    ...
  ],
  "shortcuts": [
    {
      "name": "Fil d'actualité",
      "icons": [
        {
          "src": "/static/images/icons/shortcut-feed.png",
          "sizes": "96x96"
        }
      ]
    },
    ...
  ]
}
```

## Instructions pour voir le nouveau logo

### Sur navigateur desktop
1. Ouvrir l'application : http://localhost:8000/
2. **Désinstaller l'ancienne PWA** :
   - Chrome : Menu 3 points > Plus d'outils > Désinstaller Hydria
   - Edge : Paramètres et plus > Applications > Gérer les applications > Hydria > Désinstaller
3. **Réinstaller avec le nouveau logo** :
   - Actualiser la page (Ctrl+F5)
   - Cliquer sur l'icône d'installation dans la barre d'adresse
   - Ou Menu > Installer Hydria

### Sur mobile (Android/iOS)
1. Ouvrir l'application dans le navigateur
2. Supprimer l'ancienne application de l'écran d'accueil
3. Actualiser la page dans le navigateur
4. Ajouter à nouveau à l'écran d'accueil

## Fichiers créés/modifiés

**Modifiés** :
- `backend/static/images/icons/icon-72x72.png`
- `backend/static/images/icons/icon-96x96.png`
- `backend/static/images/icons/icon-128x128.png`
- `backend/static/images/icons/icon-144x144.png`
- `backend/static/images/icons/icon-152x152.png`
- `backend/static/images/icons/icon-192x192.png`
- `backend/static/images/icons/icon-384x384.png`
- `backend/static/images/icons/icon-512x512.png`
- `backend/static/images/icons/shortcut-feed.png`
- `backend/static/images/icons/shortcut-planning.png`
- `backend/static/images/icons/shortcut-accounting.png`

**Créés** :
- `backend/docs/PWA_ICONS_REPLACEMENT.md` (ce fichier)

## Notes techniques

### Qualité des icônes
- Algorithme de redimensionnement : **LANCZOS** (haute qualité)
- Format : **PNG optimisé** (compression sans perte)
- Transparence : **Préservée** depuis le logo source

### Compatibilité
- ✅ **Chrome/Edge** : Supporté (purpose: "any maskable")
- ✅ **Firefox** : Supporté
- ✅ **Safari** : Supporté
- ✅ **Android** : Supporté
- ✅ **iOS** : Supporté

### Tailles d'icônes PWA (standard)
- **72x72** : Android legacy
- **96x96** : Raccourcis, Chrome
- **128x128** : Chrome Web Store
- **144x144** : Windows 8/10
- **152x152** : iOS Safari
- **192x192** : Android Chrome (standard)
- **384x384** : Chrome recommended
- **512x512** : Chrome splash screen

## Résultat

✅ **Avant** : Icône PWA = rond blanc sur fond bleu carré
✅ **Après** : Icône PWA = vase grecque (logo Hydria complet)

Les utilisateurs verront maintenant le vrai logo Hydria (la vase grecque) sur :
- L'icône de l'application installée (desktop/mobile)
- Les raccourcis vers Feed/Plannings/Comptabilité
- L'écran de démarrage (splash screen)
- La barre des tâches/dock/écran d'accueil
