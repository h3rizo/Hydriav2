# Guide de connexion MySQL - hydriav2_db

## Méthodes de connexion disponibles

### 1. MySQL Shell (Recommandé)
**Commande :**
```bash
mysqlsh --uri root@localhost:33060
```

**Étapes :**
1. Ouvrir PowerShell ou l'invite de commandes
2. Naviguer vers le dossier MySQL (optionnel) :
   ```bash
   cd "C:\Program Files\MySQL\MySQL Server 8.0\bin"
   ```
3. Exécuter la commande de connexion
4. Saisir le mot de passe root
5. Passer en mode SQL :
   ```javascript
   \sql
   ```
6. Utiliser la base de données :
   ```sql
   USE hydriav2_db;
   ```

### 2. MySQL classique (si le port 3306 fonctionne)
```bash
mysql -u root -p --port=3306
```

### 3. MySQL via le port X Protocol
```bash
mysql -u root -p --port=33060 --protocol=tcp
```

## Commandes essentielles

### Dans MySQL Shell
- **Passer en mode SQL :** `\sql`
- **Passer en mode JavaScript :** `\js`
- **Passer en mode Python :** `\py`
- **Aide :** `\help`
- **Quitter :** `\quit`

### Commandes SQL de base
```sql
-- Voir toutes les bases de données
SHOW DATABASES;

-- Utiliser hydriav2_db
USE hydriav2_db;

-- Voir toutes les tables
SHOW TABLES;

-- Voir la structure d'une table
DESCRIBE nom_table;
-- ou
SHOW CREATE TABLE nom_table;

-- Voir les données d'une table
SELECT * FROM nom_table LIMIT 10;
```

## Résolution de problèmes courants

### Erreur "Can't connect to MySQL server"
**Cause :** Le service MySQL n'est pas démarré

**Solution :**
```bash
# Ouvrir une invite de commande en tant qu'administrateur
net start mysql80
```

### Vérifier si MySQL fonctionne
```bash
# Voir les ports ouverts
netstat -an | findstr :3306
netstat -an | findstr :33060

# Voir les services MySQL
sc query mysql80
```

### Redémarrer MySQL si nécessaire
```bash
# En tant qu'administrateur
net stop mysql80
net start mysql80
```

## Configuration spécifique de votre installation

### Informations importantes :
- **Port MySQL standard :** 3306 (peut ne pas fonctionner)
- **Port X Protocol :** 33060 ✅ (fonctionne)
- **Service Windows :** mysql80
- **Utilisateur :** root
- **Base de données :** hydriav2_db

### Chemins importants :
- **Binaires MySQL :** `C:\Program Files\MySQL\MySQL Server 8.0\bin\`
- **Données :** `C:\Program Files\MySQL\MySQL Server 8.0\data\`
- **Configuration :** `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`

## Commandes rapides pour hydriav2_db

```sql
-- Connexion rapide à la base
USE hydriav2_db;

-- Voir le nombre d'enregistrements par table
SELECT 
    TABLE_NAME,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'hydriav2_db'
ORDER BY TABLE_ROWS DESC;

-- Tables principales du système
SELECT * FROM Regions LIMIT 5;
SELECT * FROM Districts LIMIT 5;
SELECT * FROM Ouvrages LIMIT 5;
SELECT * FROM Employes LIMIT 5;
```

## Accès via applications tierces

### MySQL Workbench
- **Host :** localhost
- **Port :** 33060
- **Username :** root
- **Connection Method :** Standard TCP/IP over SSH (si nécessaire)

### phpMyAdmin (si installé avec XAMPP/WAMP)
- **Serveur :** localhost:33060
- **Utilisateur :** root

## Sauvegarde et restauration

### Créer une sauvegarde
```bash
mysqldump -u root -p --port=33060 hydriav2_db > hydriav2_backup.sql
```

### Restaurer une sauvegarde
```bash
mysql -u root -p --port=33060 hydriav2_db < hydriav2_backup.sql
```

## Notes importantes

1. **Toujours utiliser le port 33060** pour votre installation
2. **Sauvegarder régulièrement** vos données
3. **Vérifier le service MySQL80** s'il y a des problèmes de connexion
4. **MySQL Shell est plus moderne** que l'interface MySQL classique

## Commande de connexion rapide

**Pour une connexion immédiate :**
```bash
mysqlsh --uri root@localhost:33060 --sql
```
Cette commande vous connecte directement en mode SQL.

---

*Ce guide a été créé spécifiquement pour votre configuration MySQL avec la base de données hydriav2_db.*