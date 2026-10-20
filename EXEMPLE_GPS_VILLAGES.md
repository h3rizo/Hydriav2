# Format d'import GPS pour Villages

## 📋 Description

Ce fichier Excel permet de **mettre à jour** les coordonnées GPS des villages existants dans la base de données (pas de création de nouveaux villages).

## 📊 Format Excel requis

| Colonne A | Colonne B | Colonne C | Colonne D | Colonne E (optionnel) |
|-----------|-----------|-----------|-----------|------------------------|
| **ID Village (UUID)** | **Nom du village** | **Latitude** | **Longitude** | **Altitude (m)** |
| 123e4567-e89b-12d3-a456-426614174000 | Ambohidratrimo | -18.7850000 | 47.4450000 | 1300 |
| 234e5678-f90c-23e4-b567-537725285111 | Antananarivo | -18.8792000 | 47.5079000 | 1280 |
| 345f6789-g01d-34f5-c678-648836396222 | Antsirabe | -19.8667000 | 47.0333000 | 1500 |

## ⚠️ Règles importantes

1. **La première ligne doit contenir les en-têtes** (ID, Nom, Latitude, Longitude, Altitude)
2. **L'ID du village est obligatoire** et doit être l'UUID exact du village dans la base
3. Le **nom du village** (colonne B) est optionnel, utilisé uniquement pour référence visuelle
4. **Latitude** : Nombre décimal (négatif pour hémisphère sud)
5. **Longitude** : Nombre décimal
6. **Altitude** : Optionnelle, en mètres

## 🔑 Comment obtenir les IDs des villages ?

**Méthode recommandée** : Exportez d'abord la liste des villages
1. Allez sur http://localhost:8000/geography/
2. Cliquez sur **Export Excel** → **Export Villages**
3. Le fichier Excel téléchargé contiendra les IDs de tous les villages
4. Copiez les colonnes ID et Nom dans votre fichier GPS
5. Ajoutez les colonnes Latitude, Longitude, Altitude

## 📍 Format des coordonnées

### ✅ Exemples valides :
- Latitude : `-18.9332847` (Madagascar est dans l'hémisphère sud, donc négatif)
- Longitude : `47.5079055` (Est de Madagascar)
- Altitude : `1280` (en mètres)

### ❌ Formats invalides :
- `18° 56' 00" S` → Utiliser le format décimal
- `47,5079055` → Utiliser un point (.) pas une virgule

## 🎯 Utilisation

1. Accéder à http://localhost:8000/geography/
2. Cliquer sur **Import Excel** → **MAJ GPS Villages**
3. Sélectionner votre fichier Excel
4. Cliquer sur **Mettre à jour les GPS**

## 📝 Résultats attendus

Le système affichera :
- ✅ Nombre de villages mis à jour avec succès
- ⚠️ Nombre de villages non trouvés dans la base
- ❌ Liste des erreurs (coordonnées invalides, etc.)

## 💡 Conseils

- **Utilisez toujours l'export pour obtenir les IDs** : Cela évite les erreurs de saisie
- Les IDs sont des UUID (format : 8-4-4-4-12 caractères hexadécimaux)
- Les villages non trouvés (ID invalide) ne provoqueront **pas d'erreur**, juste un avertissement
- Le nom du village (colonne B) n'est pas utilisé pour la recherche, uniquement pour votre référence
