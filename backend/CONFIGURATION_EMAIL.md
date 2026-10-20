# 📧 CONFIGURATION EMAIL - HYDRIA

## 📋 Vue d'ensemble

Ce guide vous permet de configurer l'envoi d'emails dans votre application Hydria pour :
- ✉️ Réinitialisation de mot de passe
- 🔔 Notifications aux utilisateurs
- 📨 Alertes administrateurs
- 📊 Rapports automatiques

## 🎯 Options disponibles

### Option 1 : Gmail (RECOMMANDÉ pour débuter)
- **Avantages** : Gratuit, facile à configurer, fiable
- **Limites** : 500 emails/jour maximum
- **Coût** : Gratuit

### Option 2 : Mailgun
- **Avantages** : API puissante, bon pour production
- **Limites** : Forfait gratuit limité (10 000 emails/mois)
- **Coût** : Gratuit jusqu'à 10 000 emails/mois, puis payant

### Option 3 : SendGrid
- **Avantages** : Excellente délivrabilité
- **Limites** : 100 emails/jour en gratuit
- **Coût** : Gratuit jusqu'à 100 emails/jour

### Option 4 : Serveur SMTP personnalisé
- **Avantages** : Contrôle total
- **Limites** : Configuration complexe
- **Coût** : Dépend du fournisseur

---

## 🚀 Configuration avec Gmail (Recommandé)

### Étape 1 : Créer un mot de passe d'application Google

⚠️ **Depuis 2022, Google ne permet plus l'utilisation du mot de passe principal.**

1. Allez sur : https://myaccount.google.com/security
2. Activez la **validation en deux étapes** (si pas déjà fait)
3. Allez dans **Mots de passe des applications** : https://myaccount.google.com/apppasswords
4. Sélectionnez :
   - **Application** : Autre (nom personnalisé)
   - **Nom** : `Hydria Production`
5. Cliquez sur **Générer**
6. **Copiez le mot de passe** généré (16 caractères sans espaces)

### Étape 2 : Configurer Django sur le VPS

Connectez-vous au VPS :

```bash
ssh soakoja@46.105.73.48
```

Éditez le fichier `.env` :

```bash
nano /home/soakoja/hydria/backend/.env
```

Modifiez ces lignes :

```bash
# Email Gmail
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre.email@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx  # Le mot de passe d'application (16 caractères)
DEFAULT_FROM_EMAIL=Hydria <votre.email@gmail.com>
SERVER_EMAIL=votre.email@gmail.com
```

**Exemple complet** :
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=contact@hydria.mg
EMAIL_HOST_PASSWORD=abcd efgh ijkl mnop
DEFAULT_FROM_EMAIL=Hydria <contact@hydria.mg>
SERVER_EMAIL=contact@hydria.mg
```

Enregistrez (Ctrl+O, Entrée) et quittez (Ctrl+X).

### Étape 3 : Redémarrer Gunicorn

```bash
sudo systemctl restart gunicorn
```

### Étape 4 : Tester l'envoi d'email

Connectez-vous au shell Django :

```bash
cd /home/soakoja/hydria/backend
source /home/soakoja/hydria/venv/bin/activate
python manage.py shell
```

Testez l'envoi :

```python
from django.core.mail import send_mail

send_mail(
    'Test Hydria',
    'Ceci est un email de test depuis Hydria.',
    'contact@hydria.mg',  # Expéditeur
    ['votre.email@gmail.com'],  # Destinataire
    fail_silently=False,
)
```

Si tout fonctionne, vous verrez :
```
1
```

Vérifiez votre boîte email. Si vous ne recevez rien, vérifiez les **spams**.

Quittez le shell :
```python
exit()
```

---

## 🔧 Configuration avec Mailgun

### Étape 1 : Créer un compte Mailgun

1. Allez sur : https://www.mailgun.com/
2. Créez un compte gratuit
3. Vérifiez votre email
4. Allez dans **Sending** > **Domains**
5. Utilisez le domaine sandbox (pour les tests) ou ajoutez votre propre domaine

### Étape 2 : Récupérer les identifiants

Dans **Sending** > **Domain settings** :
- **SMTP Hostname** : `smtp.mailgun.org`
- **Port** : `587`
- **Username** : `postmaster@sandboxxxxx.mailgun.org`
- **Password** : Cliquez sur "Reset password" pour obtenir le mot de passe

### Étape 3 : Configurer Django

Éditez `/home/soakoja/hydria/backend/.env` :

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=postmaster@sandboxxxxx.mailgun.org
EMAIL_HOST_PASSWORD=votre_mot_de_passe_mailgun
DEFAULT_FROM_EMAIL=Hydria <noreply@votre-domaine.com>
```

Redémarrez Gunicorn et testez comme pour Gmail.

---

## 📧 Configuration avec SendGrid

### Étape 1 : Créer un compte SendGrid

1. Allez sur : https://sendgrid.com/
2. Créez un compte gratuit (100 emails/jour)
3. Vérifiez votre email

### Étape 2 : Créer une clé API

1. Allez dans **Settings** > **API Keys**
2. Cliquez sur **Create API Key**
3. Nom : `Hydria Production`
4. Type : **Full Access**
5. **Copiez la clé** (commence par `SG.`)

### Étape 3 : Configurer Django

Éditez `/home/soakoja/hydria/backend/.env` :

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_FROM_EMAIL=Hydria <noreply@votre-domaine.com>
```

⚠️ **IMPORTANT** : `EMAIL_HOST_USER` doit être exactement `apikey` (pas votre email).

---

## 🔍 Vérification dans Django settings.py

Assurez-vous que votre fichier `backend/hydria/settings.py` contient :

```python
# Email configuration
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=25, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@hydria.mg')
SERVER_EMAIL = config('SERVER_EMAIL', default='server@hydria.mg')
```

Si ce n'est pas le cas, ajoutez ces lignes dans `settings.py`.

---

## 🐛 Dépannage

### Erreur : "Authentication failed"

- Vérifiez que le mot de passe d'application Gmail est correct (16 caractères)
- Assurez-vous que la validation en deux étapes est activée sur Google

### Erreur : "Connection refused"

- Vérifiez le port (587 pour TLS, 465 pour SSL)
- Vérifiez que `EMAIL_USE_TLS=True` est défini

### Les emails arrivent en spam

- Ajoutez un enregistrement SPF dans votre DNS
- Utilisez un domaine vérifié (pas Gmail personnel)
- Pour Mailgun/SendGrid, suivez leurs guides de configuration DNS

### Test depuis la ligne de commande

```bash
cd /home/soakoja/hydria/backend
source /home/soakoja/hydria/venv/bin/activate
python manage.py shell

from django.core.mail import send_mail
send_mail('Test', 'Message de test', 'from@example.com', ['to@example.com'])
```

---

## 📊 Utilisation dans le code Django

### Envoi d'un email simple

```python
from django.core.mail import send_mail

send_mail(
    subject='Sujet de l\'email',
    message='Contenu du message',
    from_email='noreply@hydria.mg',
    recipient_list=['destinataire@example.com'],
    fail_silently=False,
)
```

### Envoi d'un email HTML

```python
from django.core.mail import EmailMultiAlternatives

subject = 'Bienvenue sur Hydria'
text_content = 'Ceci est le contenu texte'
html_content = '<h1>Bienvenue !</h1><p>Ceci est le contenu HTML</p>'
from_email = 'noreply@hydria.mg'
to = ['destinataire@example.com']

msg = EmailMultiAlternatives(subject, text_content, from_email, to)
msg.attach_alternative(html_content, "text/html")
msg.send()
```

### Envoi avec pièce jointe

```python
from django.core.mail import EmailMessage

email = EmailMessage(
    subject='Rapport mensuel',
    body='Veuillez trouver ci-joint le rapport',
    from_email='noreply@hydria.mg',
    to=['destinataire@example.com'],
)
email.attach_file('/chemin/vers/fichier.pdf')
email.send()
```

---

## 🔐 Sécurité

### Ne jamais commiter les identifiants

Assurez-vous que `.env` est dans `.gitignore` :

```bash
cd /home/soakoja/hydria/backend
cat .gitignore | grep .env
```

Si `.env` n'est pas listé, ajoutez-le :
```bash
echo ".env" >> .gitignore
```

### Utiliser des variables d'environnement

Tous les identifiants doivent être dans `.env`, jamais dans `settings.py`.

---

## 📈 Monitoring

### Vérifier les logs d'emails

Dans Django, les erreurs d'envoi d'emails apparaissent dans :
```bash
sudo tail -50 /home/soakoja/hydria/logs/gunicorn-error.log
```

### Statistiques Gmail

Consultez votre compte Gmail pour voir les emails envoyés.

### Statistiques Mailgun/SendGrid

Allez dans le dashboard de votre compte pour voir :
- Emails envoyés
- Emails délivrés
- Emails ouverts
- Emails cliqués
- Erreurs

---

## ✅ Résumé - Configuration recommandée

Pour **démarrer rapidement** (développement/petite production) :
→ **Gmail** avec mot de passe d'application

Pour **production moyenne** (> 500 emails/jour) :
→ **Mailgun** (10 000 emails/mois gratuit)

Pour **grande production** :
→ **SendGrid** ou **Amazon SES**

---

## 📞 Support

En cas de problème :
1. Vérifiez les logs : `sudo tail -50 /home/soakoja/hydria/logs/gunicorn-error.log`
2. Testez depuis le shell Django (voir section "Tester l'envoi d'email")
3. Vérifiez que Gunicorn a bien redémarré : `sudo systemctl status gunicorn`