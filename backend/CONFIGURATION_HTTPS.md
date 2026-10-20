# 🔒 CONFIGURATION HTTPS - ÉTAPES FINALES

## ✅ État Actuel

- ✅ DNS configuré : **www.hydria.mg** → **46.105.73.48**
- ✅ Application fonctionnelle en HTTP : http://46.105.73.48
- ✅ Script de configuration HTTPS créé : `/tmp/setup-https.sh`

## 📋 ÉTAPE FINALE : Exécuter le script HTTPS

### Commande à exécuter

Connectez-vous au VPS et exécutez :

```bash
ssh soakoja@46.105.73.48
bash /tmp/setup-https.sh
```

### Ce que fait le script automatiquement

**Étape 1 : Mise à jour ALLOWED_HOSTS**
- Ajoute `www.hydria.mg` et `hydria.mg` dans le fichier `.env` de Django
- Crée une sauvegarde du fichier `.env` avant modification

**Étape 2 : Installation de Certbot**
- Installe `certbot` et `python3-certbot-nginx` via DNF
- Certbot est l'outil officiel de Let's Encrypt pour obtenir des certificats SSL

**Étape 3 : Vérification Nginx**
- Teste la configuration Nginx pour s'assurer qu'il n'y a pas d'erreur de syntaxe

**Étape 4 : Obtention du certificat SSL** ⚠️ **INTERACTION REQUISE**

Certbot va vous poser **4 questions** :

1. **Email** : Saisissez votre adresse email (pour les notifications d'expiration)
   ```
   Exemple : votreemail@example.com
   ```

2. **Conditions d'utilisation** : Tapez **A** pour accepter
   ```
   (A)gree/(C)ancel: A
   ```

3. **Partage de votre email** : Tapez **N** pour refuser
   ```
   (Y)es/(N)o: N
   ```

4. **Redirection HTTPS automatique** : Tapez **2** pour forcer HTTPS
   ```
   1: No redirect
   2: Redirect - Make all requests redirect to secure HTTPS

   Select: 2
   ```

**Étape 5 : Test du renouvellement automatique**
- Certbot teste que le renouvellement automatique fonctionne
- Le certificat sera renouvelé automatiquement tous les 60 jours

**Étape 6 : Redémarrage de Gunicorn**
- Redémarre Gunicorn pour prendre en compte les changements de configuration Django

### Résultat attendu

Vous devriez voir :

```
==========================================
Configuration HTTPS terminée !
==========================================

Vérifications :
✓ Gunicorn: ACTIF
✓ Nginx: ACTIF

Testez votre site en HTTPS :
  https://www.hydria.mg
  https://hydria.mg

Le renouvellement automatique est configuré (tous les 60 jours)
```

## 🌐 Tester l'application en HTTPS

Après l'exécution du script, accédez à :

- **https://www.hydria.mg** ← Version principale avec certificat SSL ✅
- **https://hydria.mg** ← Redirection automatique vers www

Vous devriez voir :
- Un **cadenas vert** 🔒 dans la barre d'adresse
- Le certificat SSL valide émis par **Let's Encrypt**

## 🔍 En cas de problème

### Vérifier les statuts des services

```bash
sudo systemctl status gunicorn --no-pager
sudo systemctl status nginx --no-pager
```

### Vérifier les logs Nginx

```bash
sudo tail -50 /var/log/nginx/hydria-error.log
```

### Vérifier le certificat SSL

```bash
sudo certbot certificates
```

Devrait afficher :
```
Certificate Name: www.hydria.mg
  Domains: www.hydria.mg hydria.mg
  Expiry Date: (dans 90 jours)
  Certificate Path: /etc/letsencrypt/live/www.hydria.mg/fullchain.pem
  Private Key Path: /etc/letsencrypt/live/www.hydria.mg/privkey.pem
```

### Test de sécurité SSL

Allez sur : **https://www.ssllabs.com/ssltest/**

Entrez votre domaine `www.hydria.mg` et vérifiez la note (objectif : **A** ou **A+**)

## 🔧 Configuration Django pour HTTPS (optionnel)

Une fois que HTTPS fonctionne, vous pouvez renforcer la sécurité en ajoutant ces paramètres dans `/home/soakoja/hydria/backend/.env` :

```bash
# Sécurité HTTPS (à ajouter APRÈS que HTTPS fonctionne)
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

Puis redémarrez Gunicorn :
```bash
sudo systemctl restart gunicorn
```

⚠️ **ATTENTION** : N'ajoutez ces paramètres **QU'APRÈS** avoir vérifié que HTTPS fonctionne correctement.

## 📅 Renouvellement automatique

Le certificat Let's Encrypt :
- **Durée de validité** : 90 jours
- **Renouvellement automatique** : Certbot installe un cron job qui renouvelle automatiquement le certificat tous les 60 jours
- **Emplacement du cron** : `/etc/cron.d/certbot`

Vous pouvez tester manuellement le renouvellement avec :
```bash
sudo certbot renew --dry-run
```

## 📞 Support

En cas de problème persistant :
1. Vérifiez les logs Gunicorn et Nginx (voir section "En cas de problème")
2. Vérifiez que le DNS pointe toujours vers le bon serveur : `ping www.hydria.mg`
3. Vérifiez que les ports 80 et 443 sont ouverts : `sudo firewall-cmd --list-all`

## 📝 Notes importantes

- **HTTP → HTTPS** : Certbot configure automatiquement Nginx pour rediriger HTTP vers HTTPS
- **www vs non-www** : Les deux versions (www.hydria.mg et hydria.mg) fonctionnent grâce au certificat
- **Expiration** : Vous recevrez un email d'alerte 30 jours avant l'expiration du certificat (mais il se renouvellera automatiquement)
- **Firewall** : Les ports 80 (HTTP) et 443 (HTTPS) sont déjà ouverts depuis l'installation précédente

## ✅ Prochaines étapes après HTTPS

Une fois HTTPS configuré et fonctionnel, vous pourrez passer à :

1. **Configuration des sauvegardes automatiques de la base de données** (recommandé)
2. Configuration de l'envoi d'emails (optionnel)
3. Mise en place d'un système de monitoring (optionnel)