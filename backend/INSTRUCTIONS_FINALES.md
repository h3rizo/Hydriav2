# 🚀 INSTRUCTIONS FINALES - DÉPLOIEMENT PRODUCTION

## ✅ Statut actuel

- ✅ Base de données PostgreSQL configurée et importée (74MB)
- ✅ Django configuré et fonctionnel
- ✅ Gunicorn installé dans l'environnement virtuel
- ✅ Fichiers de configuration transférés :
  - `/tmp/setup-production.sh` : Script automatique de configuration
  - `/tmp/hydria.nginx.conf` : Configuration Nginx
  - `/tmp/gunicorn.service` : Service systemd Gunicorn

## 📋 Prochaine étape : Exécuter le script de production

### Commande à exécuter sur le VPS

Connectez-vous au VPS et exécutez :

```bash
ssh soakoja@46.105.73.48
cd /tmp
sudo bash setup-production.sh
```

**Mot de passe sudo** : Votre mot de passe utilisateur soakoja

### Ce que fait le script automatiquement

1. ✅ **Crée le dossier logs** (`/home/soakoja/hydria/logs/`)
2. ✅ **Installe le service Gunicorn** (systemd)
3. ✅ **Collecte les fichiers statiques Django** (CSS, JS, images)
4. ✅ **Installe Nginx** (si non installé)
5. ✅ **Configure Nginx** comme reverse proxy
6. ✅ **Démarre les services** (Gunicorn + Nginx)
7. ✅ **Configure le firewall** (ouvre ports 80 et 443)

### Résultat attendu

Après exécution du script, vous devriez voir :

```
=========================================
  CONFIGURATION TERMINÉE !
=========================================

Vérification des services:

● gunicorn.service - Gunicorn daemon for Hydria Django Application
   Loaded: loaded
   Active: active (running)

● nginx.service - The nginx HTTP and reverse proxy server
   Loaded: loaded
   Active: active (running)

Application accessible sur: http://46.105.73.48
```

## 🌐 Tester l'application

Ouvrez votre navigateur et accédez à :

**http://46.105.73.48**

Vous devriez voir la page d'accueil de Hydria.

## 🔍 En cas de problème

### 1. Vérifier les logs Gunicorn

```bash
sudo tail -50 /home/soakoja/hydria/logs/gunicorn-error.log
```

### 2. Vérifier les logs Nginx

```bash
sudo tail -50 /var/log/nginx/hydria-error.log
```

### 3. Vérifier le statut des services

```bash
sudo systemctl status gunicorn
sudo systemctl status nginx
```

### 4. Redémarrer les services

```bash
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

## 📚 Commandes utiles

### Redémarrer l'application après modification du code

```bash
sudo systemctl restart gunicorn
```

### Voir les logs en temps réel

```bash
# Gunicorn
sudo journalctl -u gunicorn -f

# Nginx
sudo tail -f /var/log/nginx/hydria-access.log
sudo tail -f /var/log/nginx/hydria-error.log
```

### Collecter les fichiers statiques après modification CSS/JS

```bash
cd /home/soakoja/hydria
source venv/bin/activate
cd backend
python manage.py collectstatic --noinput
```

## 🔒 Sécurité (Prochaines étapes recommandées)

1. **Générer SECRET_KEY sécurisée** :
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
Copier la clé générée dans `backend/.env` : `SECRET_KEY='...'`

2. **Configurer SSL (HTTPS)** avec Let's Encrypt :
```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d votre-domaine.com
```

3. **Activer DEBUG=False** dans `backend/.env`

4. **Configurer les sauvegardes automatiques** de la base de données

## 📞 Support

En cas de problème, vérifiez :
- Les logs Gunicorn : `/home/soakoja/hydria/logs/gunicorn-error.log`
- Les logs Nginx : `/var/log/nginx/hydria-error.log`
- Le statut des services : `sudo systemctl status gunicorn nginx`
