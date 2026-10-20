# Icônes PWA Hydria

Ce dossier contient les icônes nécessaires pour la Progressive Web App (PWA) Hydria.

## Icônes requises

### Icônes PWA (obligatoires)
- `pwa-64x64.png` - Icône 64x64 pixels
- `pwa-192x192.png` - Icône 192x192 pixels  
- `pwa-512x512.png` - Icône 512x512 pixels
- `maskable-icon-512x512.png` - Icône maskable 512x512 pixels

### Icônes système (recommandées)
- `apple-touch-icon.png` - 180x180 pour iOS
- `favicon.ico` - Favicon classique
- `favicon-16x16.png` - Favicon 16x16
- `favicon-32x32.png` - Favicon 32x32

## Spécifications techniques

### Icône principale (512x512)
- Format : PNG
- Taille : 512x512 pixels
- Transparence : Supportée
- Design : Logo Hydria centré avec marge de 10%

### Icône maskable (512x512)  
- Format : PNG
- Taille : 512x512 pixels
- Zone de sécurité : Logo dans un cercle de 40% du centre
- Background : Couleur unie (bleu Hydria #1e40af)

### Génération automatique

Vous pouvez utiliser des outils comme :
- [PWA Asset Generator](https://github.com/onderceylan/pwa-asset-generator)
- [RealFaviconGenerator](https://realfavicongenerator.net/)
- [PWA Builder](https://www.pwabuilder.com/)

## Commande de génération

```bash
# Avec PWA Asset Generator
npx pwa-asset-generator logo-source.png public/icons --manifest public/manifest.json

# Avec ImageMagick (si installé)
convert logo-source.png -resize 64x64 public/icons/pwa-64x64.png
convert logo-source.png -resize 192x192 public/icons/pwa-192x192.png
convert logo-source.png -resize 512x512 public/icons/pwa-512x512.png
```

## Design Guidelines

### Logo Hydria
- Couleur principale : Bleu #1e40af
- Couleur secondaire : Bleu clair #3b82f6  
- Fond : Transparent ou blanc
- Style : Moderne, épuré
- Symbole : Goutte d'eau stylisée

### Cohérence visuelle
- Utiliser les mêmes couleurs que l'interface
- Maintenir les proportions du logo
- Assurer la lisibilité sur tous les backgrounds
- Tester sur différents appareils et tailles

## Validation

Testez vos icônes avec :
1. **Chrome DevTools** → Application → Manifest
2. **Lighthouse PWA** audit
3. **Différents appareils** (Android, iOS)
4. **Différentes tailles** d'écran

✅ Les icônes doivent être nettes à toutes les tailles  
✅ Le logo doit rester reconnaissable même petit  
✅ Les couleurs doivent être cohérentes avec l'app