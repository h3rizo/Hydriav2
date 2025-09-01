# Guide de débogage MySQL/MariaDB dans XAMPP

## 1. Diagnostic initial

### Vérifier l'état dans XAMPP Control Panel
- ✅ MySQL est-il démarré (vert) ?
- ❌ Y a-t-il des croix rouges ?
- 📋 Cliquer sur "Logs" pour voir les messages d'erreur

### Messages d'erreur courants
```
Status change detected: stopped
Error: MySQL shutdown unexpectedly
```

## 2. Consulter les logs d'erreur

### Localisation des logs
- **Logs XAMPP** : Bouton "Logs" dans Control Panel
- **Logs MySQL** : `C:\xampp\mysql\data\[nom-ordinateur].err`
- **Windows Event Viewer** : Rechercher "MySQL" ou "MariaDB"

### Erreurs fréquentes à identifier
- `Aria recovery failed` → Tables Aria corrompues
- `Port already in use` → Conflit de port
- `Access denied` → Problème de permissions
- `Cannot find checkpoint record` → Corruption des données

## 3. Solutions par type d'erreur

### A. Tables Aria corrompues
**Symptômes :**
```
Aria recovery failed. Please run aria_chk -r
Cannot find checkpoint record at LSN
```

**Solution :**
1. Arrêter XAMPP complètement
2. Aller dans `C:\xampp\mysql\data\`
3. Supprimer tous les fichiers `aria_log.*` et `aria_log_control`
4. Redémarrer MySQL

**Commande alternative (PowerShell Administrateur) :**
```powershell
cd C:\xampp\mysql\data
Remove-Item aria_log.* -Force
Remove-Item aria_log_control -Force
```

### B. Conflit de port
**Symptômes :**
```
Port 3306 in use by another process
```

**Solutions :**
1. **Identifier le processus :**
   ```cmd
   netstat -ano | findstr :3306
   ```
2. **Changer le port MySQL :**
   - Éditer `C:\xampp\mysql\bin\my.ini`
   - Modifier `port=3306` vers `port=3307`
   - Mettre à jour `C:\xampp\phpMyAdmin\config.inc.php`

### C. Problèmes de permissions
**Solutions :**
1. Lancer XAMPP **en tant qu'Administrateur**
2. Vérifier l'antivirus (peut bloquer MySQL)
3. Désactiver temporairement le pare-feu

## 4. Procédure de récupération d'urgence

### Si rien ne fonctionne
1. **Sauvegarder les données importantes**
2. **Reset complet :**
   - Arrêter XAMPP
   - Renommer `C:\xampp\mysql\data\` en `data_backup`
   - Copier `C:\xampp\mysql\backup\` vers `C:\xampp\mysql\data\`
   - Redémarrer MySQL

### Commandes de sauvegarde préventive
```cmd
# Exportation des bases de données
mysqldump -u root -p --all-databases > backup_all.sql

# Via phpMyAdmin
Aller sur http://localhost/phpmyadmin → Export → Exporter tout
```

## 5. Configuration phpMyAdmin

### Fichier de configuration
`C:\xampp\phpMyAdmin\config.inc.php`

### Paramètres importants à vérifier
```php
$cfg['Servers'][$i]['host'] = '127.0.0.1';
$cfg['Servers'][$i]['port'] = '3307';  // Adapter selon votre port
$cfg['Servers'][$i]['user'] = 'root';
$cfg['Servers'][$i]['password'] = '';
```

## 6. Maintenance préventive

### Actions régulières
- ✅ Redémarrer XAMPP proprement (Stop → Start)
- ✅ Faire des sauvegardes régulières des bases de données
- ✅ Éviter les arrêts brutaux du système
- ✅ Maintenir XAMPP à jour

### Signaux d'alerte
- MySQL se ferme de manière inattendue
- Messages d'erreur répétés dans les logs
- Lenteur inhabituelle des requêtes
- Erreurs de connexion intermittentes

## 7. Checklist de dépannage rapide

1. [ ] XAMPP lancé en tant qu'Administrateur ?
2. [ ] Port 3306/3307 disponible ?
3. [ ] Fichiers `aria_log.*` supprimés ?
4. [ ] Antivirus/Pare-feu vérifié ?
5. [ ] Configuration phpMyAdmin adaptée au bon port ?
6. [ ] Logs consultés pour identifier l'erreur exacte ?

## 8. Ressources utiles

### Commandes utiles
```cmd
# Vérifier les ports utilisés
netstat -ano | findstr :3306

# Tuer un processus MySQL bloqué
taskkill /PID [numéro_PID] /F

# Vérifier l'intégrité des tables
mysqlcheck -u root -p --all-databases
```

### Emplacements des fichiers importants
- Configuration MySQL : `C:\xampp\mysql\bin\my.ini`
- Données : `C:\xampp\mysql\data\`
- Logs d'erreur : `C:\xampp\mysql\data\[nom-pc].err`
- Config phpMyAdmin : `C:\xampp\phpMyAdmin\config.inc.php`

---

**💡 Conseil :** Toujours faire une sauvegarde avant de modifier des fichiers de configuration !