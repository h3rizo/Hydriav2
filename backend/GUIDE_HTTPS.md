# 🔒 GUIDE CONFIGURATION HTTPS - Hydria

## Vue d'ensemble

Ce guide vous aide à configurer HTTPS pour sécuriser les communications entre le navigateur et votre serveur.

---

## Option A : HTTPS avec Let's Encrypt (Nom de domaine requis)

### Prérequis
- ✅ Nom de domaine pointant vers `46.105.73.48`
- ✅ Port 80 ouvert (déjà fait)
- ✅ Port 443 ouvert (déjà fait)

### Étapes

#### 1. Vérifier que le domaine pointe vers le serveur

Depuis votre ordinateur local :
```bash
ping votre-domaine.com
```

Doit retourner : `46.105.73.48`

#### 2. Installer Certbot

Sur le VPS :
```bash
sudo dnf install -y certbot python3-certbot-nginx
```

#### 3. Mettre à jour ALLOWED_HOSTS dans Django

Sur le VPS :
```bash
nano /home/soakoja/hydria/backend/.env
```

Modifiez la ligne :
```
ALLOWED_HOSTS=46.105.73.48,localhost,127.0.0.1,votre-domaine.com
```

Redémarrez Gunicorn :
```bash
sudo systemctl restart gunicorn
```

#### 4. Obtenir le certificat SSL

```bash
sudo certbot --nginx -d votre-domaine.com
```

**Questions posées par Certbot** :
- Email : `votre-email@example.com` (pour notifications d'expiration)
- Conditions : Accepter (A)
- Partage email : Non (N)
- Redirection HTTPS : Oui (2)

#### 5. Renouvellement automatique

Certbot installe automatiquement un cron job. Testez-le :
```bash
sudo certbot renew --dry-run
```

#### 6. Vérification

Accédez à : `https://votre-domaine.com`

Vous devriez voir un cadenas vert 🔒

---

## Option B1 : Certificat auto-signé (Sans nom de domaine)

### ⚠️ Avertissement
Cette option génère un avertissement "Connexion non sécurisée" dans le navigateur car le certificat n'est pas vérifié par une autorité de certification reconnue.

### Étapes

#### 1. Créer le certificat auto-signé

```bash
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/hydria.key \
    -out /etc/nginx/ssl/hydria.crt \
    -subj "/C=MG/ST=Madagascar/L=Antananarivo/O=Hydria/CN=46.105.73.48"
```

#### 2. Mettre à jour la configuration Nginx

```bash
sudo nano /etc/nginx/conf.d/hydria.conf
```

Remplacez le contenu par :

```nginx
upstream hydria_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

# Redirection HTTP → HTTPS
server {
    listen 80;
    server_name 46.105.73.48;
    return 301 https://$server_name$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name 46.105.73.48;

    # Certificat auto-signé
    ssl_certificate /etc/nginx/ssl/hydria.crt;
    ssl_certificate_key /etc/nginx/ssl/hydria.key;

    # Paramètres SSL recommandés
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 50M;

    access_log /var/log/nginx/hydria-access.log;
    error_log /var/log/nginx/hydria-error.log;

    location = /favicon.ico {
        access_log off;
        log_not_found off;
    }

    location = /robots.txt {
        access_log off;
        log_not_found off;
    }

    location /static/ {
        alias /home/soakoja/hydria/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/soakoja/hydria/backend/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://hydria_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
```

#### 3. Configurer Django pour HTTPS

Dans `/home/soakoja/hydria/backend/.env`, ajoutez :
```
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

#### 4. Redémarrer les services

```bash
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl restart gunicorn
```

#### 5. Accès

Accédez à : `https://46.105.73.48`

**Le navigateur affichera un avertissement** - Cliquez sur "Avancé" puis "Continuer vers le site".

---

## Option B2 : Domaine gratuit + Let's Encrypt

### Fournisseurs de domaines gratuits

1. **Freenom** (https://www.freenom.com)
   - Extensions : `.tk`, `.ml`, `.ga`, `.cf`, `.gq`
   - Gratuit pour 1 an (renouvelable)

2. **afraid.org** (https://freedns.afraid.org)
   - Sous-domaines gratuits
   - Plus de 50 000 domaines disponibles

3. **nom.za** (https://www.nom.za)
   - Extension `.nom.za`
   - Gratuit

### Étapes

#### 1. Obtenir un domaine gratuit

Exemple avec Freenom :
1. Allez sur https://www.freenom.com
2. Cherchez un nom disponible (ex: `hydria.tk`)
3. Créez un compte gratuit
4. Enregistrez le domaine (gratuit)

#### 2. Configurer le DNS

Dans le panneau Freenom :
1. Allez dans "Services" → "My Domains"
2. Cliquez sur "Manage Domain"
3. Allez dans "Management Tools" → "Nameservers"
4. Sélectionnez "Use custom nameservers"
5. Ajoutez un enregistrement A :
   - Type : `A`
   - Nom : `@` (ou vide)
   - Destination : `46.105.73.48`
   - TTL : `3600`

**Attendez 5-30 minutes** pour la propagation DNS.

#### 3. Vérifier la propagation

```bash
ping votre-domaine.tk
```

Doit retourner : `46.105.73.48`

#### 4. Suivre "Option A" (Let's Encrypt)

Une fois le DNS configuré, suivez les étapes de l'Option A ci-dessus.

---

## Option B3 : Acheter un nom de domaine

### Fournisseurs recommandés

| Fournisseur | Prix/an | Extensions |
|-------------|---------|------------|
| **Namecheap** | $8-15 | .com, .net, .org |
| **OVH** | 10-15€ | .com, .fr, .eu |
| **Gandi** | 12-18€ | .com, .net, .org |
| **Google Domains** | $12 | .com, .net |

### Étapes

#### 1. Acheter le domaine

Choisissez un fournisseur et achetez votre domaine.

#### 2. Configurer le DNS

Dans le panneau de gestion DNS du fournisseur :

Ajoutez un enregistrement **A** :
- Nom/Host : `@` (ou vide pour le domaine racine)
- Type : `A`
- Valeur/Destination : `46.105.73.48`
- TTL : `3600` (1 heure)

Si vous voulez `www.votre-domaine.com`, ajoutez aussi :
- Nom/Host : `www`
- Type : `CNAME`
- Valeur : `votre-domaine.com`

#### 3. Attendre la propagation DNS

Cela peut prendre de 5 minutes à 48 heures (généralement < 1 heure).

Vérifiez avec :
```bash
nslookup votre-domaine.com
```

#### 4. Suivre "Option A" (Let's Encrypt)

Une fois le DNS propagé, suivez les étapes de l'Option A.

---

## Commandes de vérification

### Vérifier le certificat SSL
```bash
sudo certbot certificates
```

### Renouveler manuellement
```bash
sudo certbot renew
```

### Vérifier l'expiration
```bash
echo | openssl s_client -servername votre-domaine.com -connect votre-domaine.com:443 2>/dev/null | openssl x509 -noout -dates
```

### Test de sécurité SSL

Allez sur : https://www.ssllabs.com/ssltest/

Entrez votre domaine et vérifiez la note (objectif : A ou A+).

---

## Dépannage

### Erreur : "Port 80 déjà utilisé"
```bash
sudo systemctl stop nginx
sudo certbot certonly --standalone -d votre-domaine.com
sudo systemctl start nginx
```

### Certificat expiré
```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

### Erreur : "DNS resolution failed"
- Vérifiez que le domaine pointe bien vers `46.105.73.48`
- Attendez plus longtemps pour la propagation DNS

---

## Configuration Django pour HTTPS (après installation)

Dans `/home/soakoja/hydria/backend/.env`, ajoutez :

```bash
# Sécurité HTTPS
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

Dans `backend/hydria/settings.py`, vérifiez que ces lignes existent :

```python
# HTTPS/SSL
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
    CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
```

Redémarrez Gunicorn :
```bash
sudo systemctl restart gunicorn
```

---

## Résumé des options

| Option | Coût | Avertissement navigateur | Difficulté |
|--------|------|--------------------------|------------|
| A - Let's Encrypt + domaine acheté | 10-15€/an | ❌ Non | ⭐⭐ Moyenne |
| B1 - Certificat auto-signé | Gratuit | ✅ Oui | ⭐ Facile |
| B2 - Domaine gratuit + Let's Encrypt | Gratuit | ❌ Non | ⭐⭐⭐ Moyenne-Élevée |

**Recommandation** : Option A (domaine acheté) pour un site professionnel.