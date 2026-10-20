# 📧 CONFIGURATION EMAIL GMAIL - ÉTAPES RAPIDES

## ⚡ Configuration en 5 minutes

### Étape 1 : Créer un mot de passe d'application Google (2 minutes)

1. **Accéder aux paramètres Google** : https://myaccount.google.com/security

2. **Activer la validation en deux étapes** (si pas déjà fait)
   - Cliquez sur "Validation en deux étapes"
   - Suivez les instructions

3. **Créer un mot de passe d'application** : https://myaccount.google.com/apppasswords
   - Application : **Autre (nom personnalisé)**
   - Nom : `Hydria Production`
   - Cliquez sur **Générer**
   - **⚠️ COPIEZ LE MOT DE PASSE** (16 caractères sans espaces)
   - Exemple : `abcd efgh ijkl mnop`

### Étape 2 : Configurer Django sur le VPS (2 minutes)

**Connectez-vous au VPS** :
```bash
ssh soakoja@46.105.73.48
```

**Éditez le fichier .env** :
```bash
nano /home/soakoja/hydria/backend/.env
```

**Ajoutez ces lignes à la fin** (ou modifiez si elles existent déjà) :
```bash
# Configuration Email Gmail
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre.email@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx
DEFAULT_FROM_EMAIL=Hydria <votre.email@gmail.com>
SERVER_EMAIL=votre.email@gmail.com
```

**⚠️ REMPLACEZ** :
- `votre.email@gmail.com` par votre vrai email Gmail
- `xxxx xxxx xxxx xxxx` par le mot de passe d'application généré à l'étape 1

**Enregistrez** :
- Appuyez sur `Ctrl+O` puis `Entrée` pour enregistrer
- Appuyez sur `Ctrl+X` pour quitter

### Étape 3 : Redémarrer Gunicorn (30 secondes)

```bash
sudo systemctl restart gunicorn
```

### Étape 4 : Tester l'envoi d'email (1 minute)

**Accédez au shell Django** :
```bash
cd /home/soakoja/hydria/backend
source /home/soakoja/hydria/venv/bin/activate
python manage.py shell
```

**Testez l'envoi** (copiez-collez ces lignes) :
```python
from django.core.mail import send_mail

send_mail(
    'Test Hydria',
    'Ceci est un email de test depuis Hydria. Si vous recevez cet email, la configuration fonctionne !',
    'votre.email@gmail.com',  # Remplacez par votre email
    ['votre.email@gmail.com'],  # Destinataire (peut être le même)
    fail_silently=False,
)
```

**Si tout fonctionne**, vous verrez :
```
1
```

**Quittez le shell** :
```python
exit()
```

### Étape 5 : Vérifier la réception

1. Ouvrez votre boîte email Gmail
2. Vérifiez la boîte de réception
3. **Si vous ne voyez rien**, vérifiez les **SPAM**

---

## ✅ C'est tout !

Votre application peut maintenant envoyer des emails pour :
- ✉️ Réinitialisation de mot de passe
- 🔔 Notifications aux utilisateurs
- 📨 Alertes administrateurs
- 📊 Rapports automatiques

---

## 🐛 Dépannage rapide

### Erreur "Authentication failed"
- Vérifiez que le mot de passe d'application est correct (16 caractères)
- Vérifiez que la validation en deux étapes est activée sur Google

### Erreur "Connection refused"
- Vérifiez que `EMAIL_PORT=587` (pas 465)
- Vérifiez que `EMAIL_USE_TLS=True` est défini

### Les emails arrivent en spam
- Normal pour les premiers envois
- Les emails suivants arriveront en boîte de réception

---

## 📚 Documentation complète

Pour plus de détails (Mailgun, SendGrid, etc.), consultez :
- `CONFIGURATION_EMAIL.md` - Guide complet avec toutes les options

---

## 🔐 Sécurité

**⚠️ IMPORTANT** :
- Ne partagez JAMAIS votre mot de passe d'application
- Ne commitez JAMAIS le fichier `.env` dans Git
- Gardez ces informations confidentielles