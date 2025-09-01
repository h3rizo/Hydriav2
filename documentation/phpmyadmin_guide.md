# Guide complet phpMyAdmin - hydriav2_db

## Connexion à phpMyAdmin

### Étape 1 : Démarrer XAMPP
1. **Ouvrir XAMPP Control Panel**
   - Cherchez "XAMPP" dans le menu Démarrer
   - Lancez "XAMPP Control Panel"

2. **Démarrer les services**
   - Cliquez **"Start"** pour **Apache** → doit devenir vert
   - Cliquez **"Start"** pour **MySQL** → doit devenir vert

### Étape 2 : Accéder à phpMyAdmin
**URL principale :**
```
http://localhost/phpmyadmin
```

**URL alternatives si problème :**
```
http://localhost:8080/phpmyadmin
http://localhost/dashboard → puis cliquer "phpMyAdmin"
```

### Étape 3 : Connexion automatique
- **Utilisateur :** root
- **Mot de passe :** (vide par défaut)
- Connexion automatique dans la plupart des cas

---

## Création et gestion de la base de données

### 1. Créer la base hydriav2_db
1. **À gauche**, cliquez **"Nouvelle base de données"**
2. **Nom :** `hydriav2_db`
3. **Interclassement :** `utf8mb4_general_ci`
4. Cliquez **"Créer"**

### 2. Créer toutes les tables d'un coup
1. **Sélectionnez** la base `hydriav2_db` dans la liste à gauche
2. Cliquez sur l'onglet **"SQL"** en haut
3. **Copiez-collez** tout le script de l'artifact précédent
4. Cliquez **"Exécuter"**
5. ✅ Toutes vos tables sont créées !

---

## Import des fichiers CSV

### Configuration standard pour vos CSV
**Vos fichiers utilisent :**
- **Séparateur :** `;` (point-virgule)
- **Format de date :** `26/09/2024`
- **En-tête :** Première ligne à ignorer

### Procédure d'import par table

#### Étape 1 : Sélectionner la table
1. Dans la liste à gauche, cliquez sur le nom de la table (ex: `Organisations`)

#### Étape 2 : Lancer l'import
1. Cliquez sur l'onglet **"Importer"** en haut
2. **"Choisir un fichier"** → Sélectionnez votre fichier CSV

#### Étape 3 : Configuration d'import
**Section "Format spécifique à CSV" :**
- **Colonnes séparées par :** `;`
- **Colonnes entourées par :** (laisser vide)
- **Échapper avec :** `\`
- **Lignes terminées par :** `auto`
- **Ignorer un nombre de lignes :** `1` ⭐ (Important !)

#### Étape 4 : Exécuter
1. Cliquez **"Exécuter"**
2. Vérifiez le message de succès
3. Si erreur, supprimez les données et réessayez

---

## Ordre d'import recommandé

### Niveau 1 : Tables indépendantes (aucune dépendance)
```
✅ Organisations (déjà fait)
✅ Regions
✅ TypesOuvrages  
✅ TypesActivites
✅ Postes
✅ TypeDesignations
✅ TypesPointsEaus
✅ Gestionnaires
✅ TypesTypesOuvragesConstitutifs
```

### Niveau 2 : Dépendances simples
```
✅ Districts (après Regions)
✅ TypesOuvragesConstitutifs (après TypesTypesOuvragesConstitutifs)
```

### Niveau 3 : Dépendances géographiques
```
✅ Communes (après Districts)
✅ Villages (après Communes)  
✅ Parcelles (après Villages)
```

### Niveau 4 : Tables principales
```
✅ Ouvrages (après Organisations + TypesOuvrages)
✅ Bases (après Organisations + Ouvrages)
✅ Employes (après Postes + Bases)
```

### Niveau 5 : Tables complexes
```
✅ Tout le reste des tables...
```

---

## Vérifications après import

### Vérifier le nombre d'enregistrements
1. Cliquez sur une table dans la liste
2. L'onglet **"Parcourir"** montre les données
3. En bas : nombre total d'enregistrements

### Vérifier les données
```sql
-- Dans l'onglet SQL de la base
SELECT * FROM Organisations LIMIT 5;
SELECT COUNT(*) AS Total FROM Organisations;
```

### Vérifier les relations
```sql
-- Exemple : Regions et Districts
SELECT r.Nom as Region, COUNT(d.ID) as NbDistricts 
FROM Regions r 
LEFT JOIN Districts d ON r.ID = d.RegionID 
GROUP BY r.ID;
```

---

## Gestion des erreurs courantes

### Erreur de clé étrangère
**Problème :** Table parent non remplie
**Solution :** Importer d'abord la table parent

### Erreur de doublons
**Problème :** ID déjà existant
**Solutions :**
1. **Vider la table :** Opérations → "Vider la table"
2. **Ou ignorer les doublons :** Dans l'import, cocher "Ignorer les erreurs"

### Problème d'encodage (caractères spéciaux)
**Solutions :**
1. **Fichier CSV :** Sauvegarder en UTF-8
2. **phpMyAdmin :** Vérifier l'interclassement `utf8mb4_general_ci`

### Import très lent
**Solutions :**
1. **Désactiver les clés étrangères temporairement :**
```sql
SET FOREIGN_KEY_CHECKS = 0;
-- Faire les imports
SET FOREIGN_KEY_CHECKS = 1;
```

---

## Outils utiles dans phpMyAdmin

### Export des données
1. **Sélectionner la base ou table**
2. Onglet **"Exporter"**
3. **Format :** SQL pour sauvegarde complète
4. **Télécharger** le fichier

### Rechercher dans les données
1. **Sélectionner une table**
2. Onglet **"Rechercher"**
3. Critères de recherche
4. **Rechercher**

### Modifier la structure d'une table
1. **Sélectionner la table**
2. Onglet **"Structure"**
3. **Modifier** les colonnes si nécessaire

### Requêtes SQL personnalisées
1. **Sélectionner la base**
2. Onglet **"SQL"**
3. Écrire votre requête
4. **Exécuter**

---

## Raccourcis et astuces

### Navigation rapide
- **Ctrl+Home :** Retour à l'accueil
- **Liste des tables :** Clic direct pour accéder
- **Breadcrumb :** Utiliser le fil d'Ariane en haut

### Import en lot
Si vous avez beaucoup de CSV :
1. Préparer tous les fichiers dans un dossier
2. Les importer un par un dans l'ordre recommandé
3. Vérifier après chaque import

### Sauvegarde régulière
**Exporter la base complète régulièrement :**
```
Base hydriav2_db → Exporter → SQL → Télécharger
```

---

## Résolution de problèmes de connexion

### phpMyAdmin inaccessible
1. **Vérifier XAMPP :** Apache et MySQL démarrés ?
2. **Tester :** http://localhost (page d'accueil XAMPP)
3. **Port alternatif :** http://localhost:8080
4. **Redémarrer :** XAMPP Control Panel → Stop/Start

### Erreur de connexion MySQL
1. **XAMPP Control Panel :** MySQL bien démarré ?
2. **Port conflit :** Changer port MySQL dans `my.ini`
3. **Logs :** Cliquer "Logs" à côté de MySQL

### Page blanche phpMyAdmin
1. **Effacer cache navigateur**
2. **Navigateur différent**
3. **Redémarrer Apache**

---

## Commandes SQL utiles

### Statistiques générales
```sql
-- Nombre d'enregistrements par table
SELECT 
    TABLE_NAME as 'Table',
    TABLE_ROWS as 'Lignes'
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'hydriav2_db' 
ORDER BY TABLE_ROWS DESC;
```

### Vérification de l'intégrité
```sql
-- Organisations sans ouvrages
SELECT * FROM Organisations o
WHERE NOT EXISTS (SELECT 1 FROM Ouvrages ouv WHERE ouv.OrganisationID = o.ID);
```

### Nettoyage des données
```sql
-- Supprimer les lignes vides (exemple)
DELETE FROM Organisations WHERE Nom = '' OR Nom IS NULL;
```

---

*Avec ce guide, vous pouvez gérer complètement votre base hydriav2_db via phpMyAdmin !* 🎉