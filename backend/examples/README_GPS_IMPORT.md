# Import GPS - Guide d'utilisation

## 📍 Fonctionnalité

Cette fonctionnalité permet de mettre à jour **uniquement les coordonnées GPS** (latitude et longitude) des équipements et points d'eau depuis un fichier Excel, sans modifier les autres données.

## 📊 Format des fichiers Excel

### Structure attendue

Chaque fichier Excel doit contenir **4 colonnes** dans cet ordre :

| Colonne | Nom | Type | Description | Exemple |
|---------|-----|------|-------------|---------|
| **A** | ID | UUID | Identifiant unique de l'enregistrement | `12345678-1234-5678-1234-567812345678` |
| **B** | Nom | Texte | Nom (pour vérification visuelle) | `Pompe principale` |
| **C** | Latitude | Nombre | Latitude en format décimal | `-18.8792` |
| **D** | Longitude | Nombre | Longitude en format décimal | `47.5079` |

### Formats de coordonnées acceptés

- **Format décimal uniquement** : `-18.8792`, `47.5079`
- **Séparateur décimal** : Point (`.`) ou virgule (`,`)
- **Signe** : Latitude négative pour l'hémisphère Sud, Longitude positive pour Madagascar

### ⚠️ Points importants

1. **La ligne 1 doit contenir les en-têtes** (ID, Nom, Latitude, Longitude)
2. **L'ID doit être valide** et correspondre à un enregistrement existant
3. **Les coordonnées doivent être numériques** et valides
4. Les lignes sans ID seront ignorées
5. Les lignes avec coordonnées invalides généreront un avertissement

## 🚀 Utilisation

### 1. Accéder à la page Ouvrages

Rendez-vous sur : [http://localhost:8000/organisations/ouvrages/](http://localhost:8000/organisations/ouvrages/)

### 2. Cliquer sur "Import Excel"

Dans le coin supérieur droit, cliquez sur le bouton **"Import Excel"** (vert).

### 3. Sélectionner l'import GPS

Dans le menu déroulant, sous la section **"📍 Mise à jour GPS uniquement"**, choisissez :
- **GPS Équipements** : Pour mettre à jour les équipements
- **GPS Points d'Eau** : Pour mettre à jour les points d'eau

### 4. Préparer votre fichier Excel

#### Option A : Export + Modification
1. Exportez d'abord vos données (bouton "Export Excel")
2. Gardez uniquement les colonnes : ID, Nom, Latitude, Longitude
3. Remplissez les coordonnées GPS

#### Option B : Utiliser les exemples
1. Ouvrez un des fichiers exemples fournis :
   - `exemple_gps_equipements.xlsx`
   - `exemple_gps_points_eau.xlsx`
2. Remplacez les IDs et noms par vos vraies données
3. Remplissez les coordonnées GPS

### 5. Importer le fichier

1. Cliquez sur **"Parcourir"** et sélectionnez votre fichier
2. Cliquez sur **"Importer GPS"**
3. Attendez le traitement

### 6. Vérifier les résultats

Après l'import, vous verrez des messages :
- ✅ **Succès** : `X équipement(s) mis à jour avec succès`
- ⚠️ **Avertissements** : Détails des lignes en erreur (max 5 affichées)

## 📋 Exemples de fichiers

Deux fichiers exemples sont fournis dans ce dossier :

1. **`exemple_gps_equipements.xlsx`** : Exemple pour les équipements
2. **`exemple_gps_points_eau.xlsx`** : Exemple pour les points d'eau

Ces fichiers contiennent des données factices pour illustrer le format attendu.

## 🔍 Obtenir les IDs existants

### Méthode 1 : Export Excel
1. Allez sur la page Ouvrages
2. Cliquez sur **"Export Excel"** > **"Export Équipements"** ou **"Export Points d'Eau"**
3. Ouvrez le fichier téléchargé
4. La colonne **id** contient tous les UUIDs

### Méthode 2 : Pages consolidées
- **Équipements** : [http://localhost:8000/consolidated-equipements/](http://localhost:8000/consolidated-equipements/)
- **Points d'Eau** : [http://localhost:8000/facturation/consolidated-points-eau/](http://localhost:8000/facturation/consolidated-points-eau/)

Ces pages affichent les IDs dans la première colonne du tableau.

## 🛠️ Différences avec l'import complet

| Caractéristique | Import GPS uniquement | Import Excel complet |
|-----------------|----------------------|---------------------|
| **Champs modifiés** | Latitude, Longitude uniquement | Tous les champs |
| **Création d'enregistrements** | ❌ Non | ✅ Oui |
| **Mise à jour partielle** | ✅ Oui | ❌ Non (écrase tout) |
| **Risque de perte de données** | Très faible | Moyen |
| **Colonnes requises** | 4 (ID, Nom, Lat, Lon) | Toutes les colonnes |

## ❓ Cas d'usage typiques

### Cas 1 : Collecte GPS sur terrain
1. Exportez la liste des équipements/points d'eau
2. Imprimez ou emportez la liste sur tablette
3. Relevez les coordonnées GPS sur le terrain
4. Remplissez les colonnes Latitude/Longitude
5. Importez le fichier mis à jour

### Cas 2 : Correction de coordonnées erronées
1. Identifiez les enregistrements avec GPS manquant ou incorrect
2. Créez un fichier Excel avec uniquement ces enregistrements
3. Corrigez les coordonnées
4. Importez le fichier

### Cas 3 : Import massif depuis un GPS externe
1. Exportez vos données GPS depuis votre appareil
2. Faites correspondre les IDs avec vos enregistrements
3. Formatez au format requis (4 colonnes)
4. Importez le fichier

## 🚨 Erreurs courantes

### Erreur : "Équipement XXXXX introuvable"
**Cause** : L'ID n'existe pas dans la base de données
**Solution** : Vérifiez l'ID en exportant les données actuelles

### Erreur : "Coordonnées invalides"
**Cause** : Format de latitude/longitude incorrect
**Solution** : Utilisez le format décimal (ex: `-18.8792` pas `18°52'45"S`)

### Erreur : "Point d'eau XXXXX sans parcelle"
**Cause** : Le point d'eau n'a pas de parcelle associée (le GPS est stocké sur la parcelle)
**Solution** : Associez d'abord une parcelle au point d'eau depuis l'interface

### Pas de message après import
**Cause** : Le fichier est vide ou toutes les lignes ont été ignorées
**Solution** : Vérifiez que la ligne 1 contient les en-têtes et les lignes suivantes contiennent des données valides

## 📞 Support

En cas de problème, vérifiez :
1. Le format du fichier Excel (4 colonnes, en-têtes en ligne 1)
2. Les IDs correspondent bien aux enregistrements existants
3. Les coordonnées sont en format décimal
4. Le fichier n'est pas vide

Pour toute question technique, contactez l'administrateur système.
