# Connexion MySQL Community avec Power BI

## 1. Prérequis

### Installation des composants nécessaires
- ✅ MySQL Community Server (installé)
- ✅ Power BI Desktop
- ⚠️ **MySQL .NET Connector** (pilote ODBC/Connector NET)

### Installation du pilote MySQL
**Option 1 - MySQL Connector/NET :**
1. Aller sur [MySQL Downloads](https://dev.mysql.com/downloads/connector/net/)
2. Télécharger "Connector/NET" (version la plus récente)
3. Installer le fichier `.msi`

**Option 2 - MySQL Connector/ODBC :**
1. Télécharger [MySQL Connector/ODBC](https://dev.mysql.com/downloads/connector/odbc/)
2. Choisir la version 64-bit si vous avez Power BI 64-bit

## 2. Vérification de la connexion MySQL

### Tester la connexion
Avant Power BI, vérifiez que MySQL fonctionne :

**Via MySQL Workbench :**
```
Host: localhost
Port: 3306 (ou 3307)
Username: root
Password: [votre mot de passe]
```

**Via ligne de commande :**
```cmd
mysql -u root -p -h localhost -P 3306
```

### Informations de connexion à noter
- **Serveur :** `localhost` ou `127.0.0.1`
- **Port :** `3306` (par défaut) ou autre port configuré
- **Nom d'utilisateur :** `root` ou votre utilisateur
- **Mot de passe :** défini lors de l'installation
- **Nom de la base de données :** nom de votre BDD

## 3. Connexion dans Power BI Desktop

### Étape 1 : Ouvrir Power BI Desktop
1. Lancer **Power BI Desktop**
2. Sur l'écran d'accueil, cliquer **"Obtenir des données"**
   - Ou **Accueil → Obtenir des données**

### Étape 2 : Sélectionner MySQL
1. Dans la fenêtre "Obtenir des données"
2. Chercher **"MySQL"** ou naviguer vers **Base de données → MySQL**
3. Cliquer **"Connecter"**

### Étape 3 : Configurer la connexion
Remplir les paramètres :

```
Serveur : localhost
Port : 3306
Base de données (optionnel) : nom_de_votre_base
```

**Exemple :**
```
Serveur : localhost:3306
Base de données : northwind
```

### Étape 4 : Authentification
1. Sélectionner **"Base de données"** dans l'onglet de gauche
2. Saisir :
   - **Nom d'utilisateur :** `root`
   - **Mot de passe :** [votre mot de passe MySQL]
3. Cliquer **"Se connecter"**

### Étape 5 : Sélectionner les données
1. **Navigateur** s'ouvre avec la liste des tables
2. Cocher les tables/vues à importer
3. **Aperçu** des données disponible
4. Cliquer **"Charger"** ou **"Transformer les données"**

## 4. Résolution des problèmes courants

### Erreur : "Provider MySQL non trouvé"
**Solution :**
- Installer MySQL Connector/NET ou Connector/ODBC
- Redémarrer Power BI Desktop
- Vérifier que le connecteur est en 64-bit si Power BI est en 64-bit

### Erreur : "Connexion refusée"
**Causes possibles :**
1. **MySQL n'est pas démarré**
   ```cmd
   net start mysql
   ```

2. **Port incorrect**
   - Vérifier le port dans `my.ini` ou `my.cnf`
   - Ou utiliser MySQL Workbench pour identifier le port

3. **Pare-feu bloque la connexion**
   - Autoriser MySQL dans le pare-feu Windows

### Erreur : "Accès refusé pour l'utilisateur"
**Solutions :**
1. **Vérifier les identifiants**
2. **Créer un utilisateur dédié :**
   ```sql
   CREATE USER 'powerbi'@'localhost' IDENTIFIED BY 'motdepasse';
   GRANT SELECT ON nom_base.* TO 'powerbi'@'localhost';
   FLUSH PRIVILEGES;
   ```

3. **Autoriser les connexions externes (si nécessaire) :**
   ```sql
   CREATE USER 'powerbi'@'%' IDENTIFIED BY 'motdepasse';
   GRANT SELECT ON nom_base.* TO 'powerbi'@'%';
   ```

### Erreur : "SSL connection error"
**Solution :**
Ajouter des paramètres SSL à la chaîne de connexion :
```
Serveur : localhost:3306
Paramètres avancés → Chaîne de connexion :
Server=localhost;Port=3306;Database=nom_base;Uid=root;Pwd=motdepasse;SslMode=none;
```

## 5. Configuration avancée

### Chaîne de connexion personnalisée
Si la connexion simple ne fonctionne pas :

**Accueil → Obtenir des données → Plus → Autres → Requête vide**

Puis utiliser :
```m
let
    Source = MySQL.Database("localhost:3306", "nom_base", [
        Query="SELECT * FROM ma_table"
    ])
in
    Source
```

### Paramètres de performance
Pour de gros volumes de données :
- **Mode DirectQuery** : données restent sur le serveur MySQL
- **Import** : données copiées dans Power BI (plus rapide pour les analyses)

### Optimisation des requêtes
```sql
-- Limiter les colonnes importées
SELECT col1, col2, col3 FROM ma_table WHERE date > '2024-01-01'

-- Utiliser des vues pour simplifier
CREATE VIEW vue_powerbi AS 
SELECT colonnes_necessaires FROM tables_complexes WHERE conditions;
```

## 6. Checklist de vérification

### Avant de se connecter
- [ ] MySQL Community Server installé et démarré
- [ ] MySQL Connector/NET ou ODBC installé
- [ ] Identifiants de connexion valides
- [ ] Base de données accessible via MySQL Workbench
- [ ] Port MySQL identifié (3306 par défaut)

### En cas de problème
- [ ] Vérifier les logs MySQL
- [ ] Tester la connexion via ligne de commande
- [ ] Vérifier les permissions utilisateur
- [ ] Redémarrer Power BI Desktop
- [ ] Tenter une chaîne de connexion personnalisée

## 7. Exemple complet

### Données de test
```sql
-- Créer une base de test
CREATE DATABASE powerbi_test;
USE powerbi_test;

-- Créer une table simple
CREATE TABLE ventes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produit VARCHAR(50),
    quantite INT,
    prix DECIMAL(10,2),
    date_vente DATE
);

-- Insérer des données de test
INSERT INTO ventes (produit, quantite, prix, date_vente) VALUES
('Ordinateur', 2, 800.00, '2024-01-15'),
('Souris', 10, 25.50, '2024-01-16'),
('Clavier', 5, 45.00, '2024-01-17');
```

### Configuration Power BI
```
Serveur : localhost:3306
Base de données : powerbi_test
Utilisateur : root
Mot de passe : [votre mot de passe]
```

---

**💡 Astuce :** Une fois la connexion établie, vous pouvez créer des requêtes personnalisées et des relations entre tables directement dans Power BI !