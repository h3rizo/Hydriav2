# Guide d'installation Python 3.11 + Django sur AlmaLinux 9

## ⚠️ Problème actuel
Le VPS utilise Python 3.9.25, mais Django 5.2.6 nécessite Python 3.10+.

## Solution rapide : Installer Python 3.11

### Étape 1 : Installation de Python 3.11 sur AlmaLinux 9

```bash
# Se connecter au VPS
ssh soakoja@46.105.73.48

# Installer Python 3.11 depuis les dépôts AppStream
sudo dnf install -y python3.11 python3.11-pip python3.11-devel

# Vérifier l'installation
python3.11 --version
# Devrait afficher : Python 3.11.x
```

### Étape 2 : Recréer l'environnement virtuel

```bash
# Aller dans le répertoire du projet
cd /home/soakoja/hydria

# Supprimer l'ancien venv Python 3.9
rm -rf venv

# Créer un nouvel environnement virtuel avec Python 3.11
python3.11 -m venv venv

# Activer l'environnement virtuel
source venv/bin/activate

# Vérifier la version de Python dans le venv
python --version
# Devrait afficher : Python 3.11.x

# Mettre à jour pip
pip install --upgrade pip
```

### Étape 3 : Installation des dépendances

```bash
# Installer Django et toutes les dépendances
pip install -r requirements.txt

# Vérifier que Django est installé
python -m django --version
# Devrait afficher : 5.2.6
```

### Étape 4 : Configuration PostgreSQL

```bash
# Installer PostgreSQL
sudo dnf install -y postgresql postgresql-server postgresql-contrib

# Initialiser la base de données
sudo postgresql-setup --initdb

# Démarrer et activer PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Se connecter en tant qu'utilisateur postgres
sudo -u postgres psql

# Dans psql, créer l'utilisateur et la base de données
CREATE USER postgre WITH PASSWORD 'c5a5113cd60642c7a6caa89abeb21680';
CREATE DATABASE hydria OWNER postgre;
GRANT ALL PRIVILEGES ON DATABASE hydria TO postgre;
\q
```

### Étape 5 : Configuration de l'application

```bash
# Créer le fichier de configuration
sudo nano /home/soakoja/hydria/.env
```

Copiez-collez ce contenu (⚠️ MODIFIER les valeurs) :

```env
# Base de données PostgreSQL
DATABASE_URL=postgresql://postgre:c5a5113cd60642c7a6caa89abeb21680@localhost/hydria

# Django (générer avec: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
SECRET_KEY=CHANGEZ_CETTE_CLE_SECRETE_TRES_LONGUE_ET_ALEATOIRE
DEBUG=False
ALLOWED_HOSTS=www.hydria.mg,46.105.73.48

# Timezone Madagascar
TIME_ZONE=Indian/Antananarivo

# Sécurité (mettre True si HTTPS configuré)
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

### Étape 6 : Configuration Gunicorn

```bash
# Créer le fichier de service Gunicorn
sudo nano /etc/systemd/system/gunicorn.service
```

Copiez-collez ce contenu :

```ini
[Unit]
Description=Gunicorn daemon for Hydria Django application
After=network.target

[Service]
User=soakoja
Group=nginx
WorkingDirectory=/home/soakoja/hydria
Environment="PATH=/home/soakoja/hydria/venv/bin"
EnvironmentFile=/home/soakoja/hydria/.env
ExecStart=/home/soakoja/hydria/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/home/soakoja/hydria/hydria.sock \
          hydria.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
# Recharger systemd et démarrer Gunicorn
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn

# Vérifier le statut
sudo systemctl status gunicorn
```

### Étape 7 : Configuration Nginx

```bash
# Installer Nginx
sudo dnf install -y nginx

# Créer la configuration du site
sudo nano /etc/nginx/conf.d/hydria.conf
```

Copiez-collez ce contenu :

```nginx
server {
    listen 80;
    server_name 46.105.73.48 www.hydria.mg;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ {
        alias /home/soakoja/hydria/staticfiles/;
    }

    location /media/ {
        alias /home/soakoja/hydria/media/;
    }

    location / {
        proxy_pass http://unix:/home/soakoja/hydria/hydria.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Démarrer et activer Nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Vérifier la configuration
sudo nginx -t
```

---

## Étape 2️⃣ : Déploiement depuis Windows

### Sur votre PC Windows :

1. **Ouvrir PowerShell** dans le dossier du projet :

```powershell
cd "c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
```

2. **Modifier deploy.ps1** :

```powershell
notepad deploy.ps1
```

Changez ces 3 lignes :
```powershell
$VPS_USER = "root"              # Votre utilisateur SSH
$VPS_IP = "123.45.67.89"        # ← CHANGEZ avec l'IP de votre VPS
$VPS_PATH = "/var/www/hydria"   # OK par défaut
```

Sauvegarder et fermer.

3. **Lancer le déploiement** :

```powershell
# Autoriser l'exécution de scripts
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Déployer ! ⏱️ environ 3-5 minutes
.\deploy.ps1
```

Entrez votre mot de passe SSH quand demandé.

---

## Étape 3️⃣ : Démarrage et vérification

### Sur le VPS :

```bash
# Vérifier que tout fonctionne
sudo systemctl status gunicorn
sudo systemctl status nginx
sudo systemctl status postgresql
```

### Configurer SELinux pour permettre les connexions réseau

AlmaLinux utilise SELinux qui peut bloquer Nginx. Exécutez ces commandes :

```bash
# Permettre à Nginx de se connecter au réseau
sudo setsebool -P httpd_can_network_connect 1

# Restaurer le contexte SELinux sur les fichiers
sudo restorecon -Rv /home/soakoja/hydria

# Redémarrer Nginx
sudo systemctl restart nginx
```

### Configurer le firewall

```bash
# Ouvrir les ports HTTP et HTTPS
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https

# Recharger le firewall
sudo firewall-cmd --reload

# Vérifier
sudo firewall-cmd --list-all
```

### Tester dans le navigateur :

Ouvrez votre navigateur et allez sur :
```
http://46.105.73.48
```

🎉 **Votre application Hydria devrait être en ligne !**

---

## 🔄 Mises à jour futures

Pour mettre à jour votre application après des modifications :

```powershell
# Sur Windows - Depuis le dossier backend
.\deploy.ps1
```

C'est tout ! Le script fait tout automatiquement.

---

## 🐛 Problèmes courants

### 1. Erreur 502 Bad Gateway

**Cause :** Problème SELinux (spécifique à AlmaLinux/RHEL)

**Solution :**
```bash
# Sur le VPS
sudo setsebool -P httpd_can_network_connect 1
sudo restorecon -Rv /var/www/hydria
sudo systemctl restart gunicorn nginx
```

### 2. Permission denied sur les fichiers

**Solution :**
```bash
sudo chown -R hydria:nginx /var/www/hydria
sudo chmod -R 755 /var/www/hydria
```

### 3. PostgreSQL ne démarre pas

**Solution :**
```bash
# Vérifier les logs
sudo journalctl -u postgresql -f

# Réinitialiser si nécessaire
sudo postgresql-setup --initdb
sudo systemctl start postgresql
```

### 4. Les icônes ne s'affichent pas

**Solution :**
```bash
cd /var/www/hydria
source venv/bin/activate
python3 manage.py collectstatic --noinput
sudo systemctl restart nginx
```

### 5. Firewall bloque les connexions

**Solution :**
```bash
# Ouvrir les ports HTTP/HTTPS
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# Vérifier
sudo firewall-cmd --list-all
```

---

## 📊 Commandes utiles

```bash
# Voir les logs en temps réel
sudo journalctl -u gunicorn -f
sudo tail -f /var/log/nginx/error.log

# Redémarrer tous les services
sudo systemctl restart gunicorn nginx redis

# Vérifier l'état des services
sudo systemctl status gunicorn nginx postgresql redis

# Vérifier l'espace disque
df -h

# Voir les processus Python
ps aux | grep python
```

---

## 🔐 Sécuriser votre serveur (Recommandé)

### 1. Changer le port SSH (optionnel)

```bash
sudo nano /etc/ssh/sshd_config
# Changer Port 22 → Port 2222
sudo systemctl restart sshd
sudo firewall-cmd --permanent --add-port=2222/tcp
sudo firewall-cmd --permanent --remove-service=ssh
sudo firewall-cmd --reload
```

### 2. Installer un certificat SSL (HTTPS)

```bash
# Installer Certbot
sudo dnf install -y certbot python3-certbot-nginx

# Obtenir un certificat (remplacer votre-domaine.com)
sudo certbot --nginx -d votre-domaine.com

# Renouvellement automatique
sudo systemctl enable certbot-renew.timer
```

Après SSL, modifier `/var/www/hydria/.env` :
```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 3. Configurer fail2ban (protection brute force)

```bash
sudo dnf install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 📞 Aide supplémentaire

Si vous rencontrez des problèmes :

1. Vérifiez les logs : `sudo journalctl -u gunicorn -f`
2. Vérifiez SELinux : `sudo ausearch -m avc -ts recent`
3. Vérifiez le firewall : `sudo firewall-cmd --list-all`

**Différences importantes AlmaLinux vs Ubuntu :**
- `dnf` au lieu de `apt`
- `firewalld` au lieu de `ufw`
- SELinux actif par défaut (peut bloquer certaines opérations)
- PostgreSQL nécessite `postgresql-setup --initdb`

Bon déploiement ! 🚀
