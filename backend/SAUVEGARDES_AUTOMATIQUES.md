# 💾 SAUVEGARDES AUTOMATIQUES DE LA BASE DE DONNÉES

## 📋 Vue d'ensemble

Ce guide vous permet de configurer des **sauvegardes automatiques quotidiennes** de votre base de données PostgreSQL.

### Caractéristiques du système de sauvegarde :

- ✅ **Sauvegarde quotidienne** à 2h00 du matin
- ✅ **Format compressé** (gzip) pour économiser l'espace
- ✅ **Rétention de 7 jours** (suppression automatique des anciennes sauvegardes)
- ✅ **Logs détaillés** de chaque sauvegarde
- ✅ **Restauration facile** en une seule commande

## 🚀 Installation (À exécuter sur le VPS)

### Méthode 1 : Script automatique (RECOMMANDÉ)

Connectez-vous au VPS et créez le script d'installation :

```bash
ssh soakoja@46.105.73.48

cat > /tmp/setup-backup-db.sh << 'EOF'
#!/bin/bash
# Script de configuration des sauvegardes automatiques PostgreSQL

echo "=========================================="
echo "Configuration des sauvegardes PostgreSQL"
echo "=========================================="
echo ""

# Étape 1 : Création du répertoire de sauvegarde
echo "[INFO] Étape 1/5: Création du répertoire de sauvegarde..."
sudo mkdir -p /home/soakoja/backups/database
sudo chown soakoja:soakoja /home/soakoja/backups/database
sudo chmod 755 /home/soakoja/backups/database

echo "Répertoire créé : /home/soakoja/backups/database"

# Étape 2 : Création du script de sauvegarde
echo ""
echo "[INFO] Étape 2/5: Création du script de sauvegarde..."

cat > /home/soakoja/backups/backup-database.sh << 'EOFSCRIPT'
#!/bin/bash
# Script de sauvegarde automatique PostgreSQL Hydria

BACKUP_DIR=/home/soakoja/backups/database
DB_NAME=hydria
DB_USER=hydria
DB_PASSWORD=hydria_password_2025
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/hydria_${DATE}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

# Fonction de log
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message "=========================================="
log_message "Début de la sauvegarde PostgreSQL"
log_message "=========================================="

# Vérifier que le répertoire existe
if [ ! -d "$BACKUP_DIR" ]; then
    log_message "ERREUR: Le répertoire $BACKUP_DIR n'existe pas"
    exit 1
fi

# Effectuer la sauvegarde avec pg_dump (format SQL compressé)
log_message "Sauvegarde de la base de données $DB_NAME..."
PGPASSWORD=$DB_PASSWORD pg_dump -h localhost -U $DB_USER -d $DB_NAME | gzip > "$BACKUP_FILE"

# Vérifier le succès de la sauvegarde
if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_message "✓ Sauvegarde réussie : $BACKUP_FILE ($BACKUP_SIZE)"
else
    log_message "✗ ERREUR lors de la sauvegarde"
    exit 1
fi

# Garder seulement les 7 dernières sauvegardes quotidiennes
log_message "Nettoyage des anciennes sauvegardes (conservation: 7 jours)..."
cd "$BACKUP_DIR"
ls -t hydria_*.sql.gz | tail -n +8 | xargs -r rm -f

# Compter les sauvegardes restantes
BACKUP_COUNT=$(ls -1 hydria_*.sql.gz 2>/dev/null | wc -l)
log_message "Nombre de sauvegardes conservées : $BACKUP_COUNT"

log_message "=========================================="
log_message "Sauvegarde terminée avec succès"
log_message "=========================================="
EOFSCRIPT

chmod +x /home/soakoja/backups/backup-database.sh
echo "Script de sauvegarde créé : /home/soakoja/backups/backup-database.sh"

# Étape 3 : Test de la sauvegarde
echo ""
echo "[INFO] Étape 3/5: Test de la première sauvegarde..."
bash /home/soakoja/backups/backup-database.sh

# Étape 4 : Configuration du cron job
echo ""
echo "[INFO] Étape 4/5: Configuration de la tâche automatique (cron)..."

# Créer la ligne cron (tous les jours à 2h du matin)
CRON_LINE="0 2 * * * /home/soakoja/backups/backup-database.sh >> /home/soakoja/backups/database/backup.log 2>&1"

# Vérifier si le cron existe déjà
(crontab -l 2>/dev/null | grep -q "backup-database.sh") && {
    echo "La tâche cron existe déjà"
} || {
    # Ajouter la ligne cron
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Tâche cron ajoutée : sauvegarde quotidienne à 2h00"
}

# Étape 5 : Vérification finale
echo ""
echo "[INFO] Étape 5/5: Vérification finale..."

# Vérifier que le fichier de sauvegarde existe
LATEST_BACKUP=$(ls -t /home/soakoja/backups/database/hydria_*.sql.gz 2>/dev/null | head -1)
if [ -f "$LATEST_BACKUP" ]; then
    BACKUP_SIZE=$(du -h "$LATEST_BACKUP" | cut -f1)
    echo "✓ Dernière sauvegarde : $LATEST_BACKUP ($BACKUP_SIZE)"
else
    echo "✗ Aucune sauvegarde trouvée"
fi

# Afficher les tâches cron configurées
echo ""
echo "Tâches cron configurées :"
crontab -l | grep backup-database

echo ""
echo "=========================================="
echo "Configuration des sauvegardes terminée !"
echo "=========================================="
echo ""
echo "Informations importantes :"
echo "  - Répertoire des sauvegardes : /home/soakoja/backups/database/"
echo "  - Script de sauvegarde : /home/soakoja/backups/backup-database.sh"
echo "  - Fréquence : Tous les jours à 2h00"
echo "  - Rétention : 7 dernières sauvegardes"
echo "  - Log : /home/soakoja/backups/database/backup.log"
echo ""
echo "Pour restaurer une sauvegarde :"
echo "  gunzip -c /home/soakoja/backups/database/hydria_YYYYMMDD_HHMMSS.sql.gz | psql -h localhost -U hydria -d hydria"
echo ""
EOF

chmod +x /tmp/setup-backup-db.sh
```

Ensuite, exécutez le script :

```bash
bash /tmp/setup-backup-db.sh
```

## 📊 Vérification de l'installation

### 1. Vérifier que la première sauvegarde a été créée

```bash
ls -lh /home/soakoja/backups/database/
```

Vous devriez voir un fichier `hydria_YYYYMMDD_HHMMSS.sql.gz` (exemple : `hydria_20250101_140530.sql.gz`)

### 2. Vérifier le contenu du log

```bash
cat /home/soakoja/backups/database/backup.log
```

Devrait afficher quelque chose comme :
```
[2025-01-01 14:05:30] ==========================================
[2025-01-01 14:05:30] Début de la sauvegarde PostgreSQL
[2025-01-01 14:05:30] ==========================================
[2025-01-01 14:05:30] Sauvegarde de la base de données hydria...
[2025-01-01 14:05:35] ✓ Sauvegarde réussie : /home/soakoja/backups/database/hydria_20250101_140530.sql.gz (18M)
[2025-01-01 14:05:35] Nettoyage des anciennes sauvegardes (conservation: 7 jours)...
[2025-01-01 14:05:35] Nombre de sauvegardes conservées : 1
[2025-01-01 14:05:35] ==========================================
[2025-01-01 14:05:35] Sauvegarde terminée avec succès
[2025-01-01 14:05:35] ==========================================
```

### 3. Vérifier que la tâche cron est configurée

```bash
crontab -l
```

Devrait afficher :
```
0 2 * * * /home/soakoja/backups/backup-database.sh >> /home/soakoja/backups/database/backup.log 2>&1
```

## 🔧 Utilisation

### Lancer une sauvegarde manuelle

```bash
/home/soakoja/backups/backup-database.sh
```

### Lister les sauvegardes disponibles

```bash
ls -lh /home/soakoja/backups/database/hydria_*.sql.gz
```

### Voir les logs des sauvegardes

```bash
# Dernières 50 lignes
tail -50 /home/soakoja/backups/database/backup.log

# Ou tout le fichier
cat /home/soakoja/backups/database/backup.log
```

## 🔄 Restauration d'une sauvegarde

### ⚠️ ATTENTION : La restauration écrase toutes les données actuelles

### Étape 1 : Choisir la sauvegarde à restaurer

```bash
ls -lh /home/soakoja/backups/database/
```

### Étape 2 : Arrêter Gunicorn (pour éviter les modifications pendant la restauration)

```bash
sudo systemctl stop gunicorn
```

### Étape 3 : Restaurer la base de données

```bash
# Remplacez YYYYMMDD_HHMMSS par la date de votre sauvegarde
gunzip -c /home/soakoja/backups/database/hydria_YYYYMMDD_HHMMSS.sql.gz | PGPASSWORD=hydria_password_2025 psql -h localhost -U hydria -d hydria
```

Exemple :
```bash
gunzip -c /home/soakoja/backups/database/hydria_20250101_140530.sql.gz | PGPASSWORD=hydria_password_2025 psql -h localhost -U hydria -d hydria
```

### Étape 4 : Redémarrer Gunicorn

```bash
sudo systemctl start gunicorn
```

### Étape 5 : Vérifier que l'application fonctionne

Accédez à : **https://www.hydria.mg** et vérifiez que vos données sont bien restaurées.

## 📅 Politique de rétention

Par défaut, le système conserve **les 7 dernières sauvegardes** (1 semaine).

### Modifier la période de rétention

Éditez le script de sauvegarde :

```bash
nano /home/soakoja/backups/backup-database.sh
```

Modifiez la ligne :
```bash
ls -t hydria_*.sql.gz | tail -n +8 | xargs -r rm -f
```

- Pour **30 jours** : Changez `+8` en `+31`
- Pour **14 jours** : Changez `+8` en `+15`

Puis enregistrez (Ctrl+O, Entrée, Ctrl+X).

## 🕒 Modifier l'heure de sauvegarde

Par défaut, la sauvegarde s'exécute à **2h00** du matin.

Pour modifier l'heure :

```bash
crontab -e
```

Modifiez la ligne :
```
0 2 * * * /home/soakoja/backups/backup-database.sh >> /home/soakoja/backups/database/backup.log 2>&1
```

Exemples :
- **3h30** : `30 3 * * *`
- **Minuit** : `0 0 * * *`
- **Midi** : `0 12 * * *`

Enregistrez et quittez (dans nano : Ctrl+O, Entrée, Ctrl+X).

## 💾 Espace disque

### Estimer l'espace nécessaire

Avec une base de 74 MB (non compressée), les sauvegardes compressées prendront environ **15-20 MB** chacune.

Pour 7 jours de sauvegardes : **~140 MB** maximum.

### Vérifier l'espace disque disponible

```bash
df -h /home/soakoja/backups/
```

## 🔐 Sécurité

### Le mot de passe dans le script

Le script contient le mot de passe PostgreSQL. Assurez-vous que seul l'utilisateur `soakoja` peut le lire :

```bash
chmod 700 /home/soakoja/backups/backup-database.sh
```

### Sauvegardes hors site (RECOMMANDÉ)

Pour plus de sécurité, copiez régulièrement les sauvegardes sur un autre serveur ou service cloud :

**Exemple avec rsync vers un autre serveur :**
```bash
rsync -avz /home/soakoja/backups/database/ user@backup-server:/backups/hydria/
```

**Exemple avec rclone vers Google Drive/Dropbox :**
```bash
# Installer rclone
curl https://rclone.org/install.sh | sudo bash

# Configurer rclone (suivre les instructions)
rclone config

# Synchroniser les sauvegardes
rclone sync /home/soakoja/backups/database/ remote:hydria-backups/
```

## 🐛 Dépannage

### La sauvegarde ne se crée pas

1. Vérifier que PostgreSQL fonctionne :
```bash
sudo systemctl status postgresql
```

2. Tester manuellement le script :
```bash
bash /home/soakoja/backups/backup-database.sh
```

3. Vérifier les logs d'erreurs :
```bash
tail -50 /home/soakoja/backups/database/backup.log
```

### Erreur "FATAL: password authentication failed"

Le mot de passe dans le script ne correspond pas. Vérifiez dans `/home/soakoja/hydria/backend/.env` :

```bash
grep DATABASE_URL /home/soakoja/hydria/backend/.env
```

Et mettez à jour le mot de passe dans `/home/soakoja/backups/backup-database.sh`.

### Le cron ne s'exécute pas

1. Vérifier que le service cron est actif :
```bash
sudo systemctl status crond
```

2. Vérifier les logs du cron :
```bash
sudo tail -50 /var/log/cron
```

3. Vérifier les permissions du script :
```bash
ls -l /home/soakoja/backups/backup-database.sh
# Doit afficher : -rwx------ (700)
```

## ✅ Résumé

Après cette configuration, vous avez :

- ✅ Sauvegarde automatique **tous les jours à 2h00**
- ✅ Conservation de **7 sauvegardes** (1 semaine)
- ✅ Format **compressé** (économie d'espace)
- ✅ **Logs détaillés** de chaque sauvegarde
- ✅ Restauration **facile et rapide**

**Votre base de données est maintenant protégée ! 🎉**

## 📞 Support

En cas de problème :
1. Consultez les logs : `/home/soakoja/backups/database/backup.log`
2. Vérifiez l'espace disque : `df -h`
3. Testez manuellement le script : `bash /home/soakoja/backups/backup-database.sh`