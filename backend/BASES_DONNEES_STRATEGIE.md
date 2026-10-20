# 💾 STRATÉGIE DES BASES DE DONNÉES - LOCAL vs VPS

## 📊 Situation actuelle

Vous avez effectivement **DEUX bases de données PostgreSQL distinctes** :

### 1. Base de données LOCALE (Windows)
- 📍 **Emplacement** : `localhost:5432` sur votre ordinateur Windows
- 🗄️ **Nom** : `hydria`
- 👤 **Utilisateur** : `postgres`
- 🔑 **Mot de passe** : `c5a5113cd60642c7a6caa89abeb21680`
- 📦 **Taille** : ~74 MB
- 🎯 **Usage** : Développement local

### 2. Base de données VPS (Production)
- 📍 **Emplacement** : `localhost:5432` sur le VPS (46.105.73.48)
- 🗄️ **Nom** : `hydria`
- 👤 **Utilisateur** : `hydria`
- 🔑 **Mot de passe** : `hydria_password_2025`
- 📦 **Taille** : ~74 MB (importée depuis votre base locale)
- 🎯 **Usage** : Production

## ✅ C'est NORMAL et SOUHAITÉ !

Cette configuration est **parfaitement correcte** pour plusieurs raisons :

### Avantages de cette architecture :

1. **Séparation des environnements** 🔒
   - Vos tests locaux n'affectent PAS la production
   - Vous pouvez développer sans risque

2. **Sécurité** 🛡️
   - La base de production est isolée sur le VPS
   - Accès contrôlé par le firewall

3. **Performance** ⚡
   - Base locale rapide pour le développement
   - Base production optimisée pour les vrais utilisateurs

4. **Indépendance** 🔄
   - Vous pouvez travailler hors ligne
   - Le VPS fonctionne indépendamment

---

## 🔄 Workflow de développement recommandé

### 1. Développement LOCAL (votre ordinateur)

```bash
cd "c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
python manage.py runserver
```

- Accès : http://127.0.0.1:8000
- Base de données locale utilisée
- Modifications de code en temps réel

### 2. Test sur le VPS PRODUCTION

Après avoir testé localement :

```bash
# 1. Commiter vos changements
git add .
git commit -m "Nouvelle fonctionnalité"

# 2. Transférer sur le VPS (via Git ou SCP)
scp fichier.py soakoja@46.105.73.48:/home/soakoja/hydria/backend/

# 3. Redémarrer Gunicorn sur le VPS
ssh soakoja@46.105.73.48 "sudo systemctl restart gunicorn"
```

---

## 🔄 Synchronisation des bases de données

### Option 1 : Développement → Production (RECOMMANDÉ)

Vous développez en local, puis vous synchronisez vers production.

#### Méthode A : Export/Import complet

**Sur votre ordinateur Windows :**
```bash
# Export de votre base locale
pg_dump -h localhost -U postgres -d hydria -F c -f hydria_dev.backup
```

**Transférer vers le VPS :**
```bash
scp hydria_dev.backup soakoja@46.105.73.48:/tmp/
```

**Sur le VPS :**
```bash
# Arrêter Gunicorn
sudo systemctl stop gunicorn

# Restaurer la base
PGPASSWORD=hydria_password_2025 pg_restore -h localhost -U hydria -d hydria -c /tmp/hydria_dev.backup

# Redémarrer Gunicorn
sudo systemctl start gunicorn
```

#### Méthode B : Migrations Django (RECOMMANDÉ pour les changements de schéma)

**Sur votre ordinateur (après modification des modèles) :**
```bash
python manage.py makemigrations
git add .
git commit -m "Nouvelles migrations"
```

**Sur le VPS :**
```bash
cd /home/soakoja/hydria/backend
source /home/soakoja/hydria/venv/bin/activate
git pull  # Si vous utilisez Git
python manage.py migrate
sudo systemctl restart gunicorn
```

---

### Option 2 : Production → Développement

Récupérer les données de production pour tester localement.

**Sur le VPS (créer une sauvegarde) :**
```bash
PGPASSWORD=hydria_password_2025 pg_dump -h localhost -U hydria -d hydria -F c -f /tmp/hydria_prod.backup
```

**Télécharger sur votre ordinateur :**
```bash
scp soakoja@46.105.73.48:/tmp/hydria_prod.backup .
```

**Sur votre ordinateur Windows :**
```bash
# Restaurer dans votre base locale
pg_restore -h localhost -U postgres -d hydria -c hydria_prod.backup
```

⚠️ **ATTENTION** : Cela écrasera toutes vos données de développement local !

---

## 🎯 Stratégies selon les cas d'usage

### Cas 1 : Vous développez une nouvelle fonctionnalité

1. Travaillez en **LOCAL** avec votre base locale
2. Testez tout en local
3. Faites les migrations Django
4. Transférez **SEULEMENT le code** sur le VPS
5. Exécutez les migrations sur le VPS
6. Redémarrez Gunicorn

**Ne synchronisez PAS les données** dans ce cas.

---

### Cas 2 : Vous avez importé des données en local

1. Développez et testez en **LOCAL**
2. Exportez votre base locale
3. Importez sur le **VPS**
4. Les utilisateurs travaillent sur la base de production

**Synchronisez les données une fois**, puis gardez les deux bases séparées.

---

### Cas 3 : Les utilisateurs ajoutent des données en production

1. Les utilisateurs utilisent le site web (VPS)
2. Les données sont créées dans la base **VPS**
3. Vous développez en local avec votre propre base
4. Vous transférez **SEULEMENT le code** vers le VPS
5. Les données des utilisateurs restent intactes

**Ne synchronisez JAMAIS Production → Local** sauf pour déboguer.

---

## ⚠️ Règles CRITIQUES

### ✅ À FAIRE

1. **Utilisez Git** pour le code
   - Versionner votre code
   - Transférer facilement vers le VPS

2. **Migrations Django** pour le schéma
   - Gérer les changements de structure de base de données
   - Appliquer les changements sur les deux environnements

3. **Sauvegardes régulières** de la production
   - Le système automatique que nous avons configuré
   - Télécharger localement les sauvegardes importantes

4. **Garder les données de production séparées**
   - Ne jamais écraser les données des utilisateurs

### ❌ À NE PAS FAIRE

1. **Ne JAMAIS synchroniser automatiquement** Production → Local
   - Risque d'écrasement de vos tests

2. **Ne JAMAIS écraser la production** sans sauvegarde
   - Toujours créer une sauvegarde avant import

3. **Ne JAMAIS commiter les fichiers .env** dans Git
   - Les mots de passe doivent rester secrets

4. **Ne JAMAIS utiliser les mêmes mots de passe** local et production
   - Sécurité renforcée

---

## 📁 Configuration Git recommandée

### Initialiser Git sur votre ordinateur

```bash
cd "c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django"

# Initialiser Git
git init

# Vérifier que .gitignore existe et contient :
cat .gitignore
```

Votre `.gitignore` devrait contenir :
```
# Environnement
.env
venv/
*.pyc
__pycache__/

# Base de données
*.sqlite3
db.sqlite3

# Fichiers temporaires
*.log
*.pot
*.pyc

# Médias
media/

# Static files
staticfiles/
```

### Workflow Git recommandé

```bash
# 1. Ajouter vos changements
git add .

# 2. Commiter
git commit -m "Description des changements"

# 3. Optionnel : Push vers GitHub/GitLab
git push origin main
```

### Sur le VPS

```bash
cd /home/soakoja/hydria

# Initialiser Git
git init

# Ajouter votre dépôt distant (GitHub/GitLab)
git remote add origin https://github.com/votre-compte/hydria.git

# Récupérer les changements
git pull origin main

# Appliquer les migrations
cd backend
source /home/soakoja/hydria/venv/bin/activate
python manage.py migrate

# Redémarrer
sudo systemctl restart gunicorn
```

---

## 📊 Schéma récapitulatif

```
┌─────────────────────────────────┐
│  ORDINATEUR LOCAL (Windows)     │
│                                  │
│  PostgreSQL Local                │
│  - Nom: hydria                   │
│  - User: postgres                │
│  - Usage: Développement          │
│                                  │
│  Django runserver                │
│  http://127.0.0.1:8000           │
└─────────────┬───────────────────┘
              │
              │ Git / SCP (code uniquement)
              │ Export/Import (données occasionnellement)
              │
              ▼
┌─────────────────────────────────┐
│  VPS PRODUCTION (46.105.73.48)  │
│                                  │
│  PostgreSQL Production           │
│  - Nom: hydria                   │
│  - User: hydria                  │
│  - Usage: Production             │
│                                  │
│  Gunicorn + Nginx                │
│  https://www.hydria.mg           │
└──────────────────────────────────┘
```

---

## ✅ Résumé

**DEUX bases de données = NORMAL** ✅

- **Local** : Pour développer sans risque
- **VPS** : Pour les vrais utilisateurs

**Workflow recommandé :**
1. Développer en local
2. Tester en local
3. Transférer le CODE vers le VPS
4. Appliquer les migrations sur le VPS
5. Les DONNÉES restent sur le VPS

**Sauvegardes automatiques** protègent la production.

**Git** pour versionner le code (pas les données).

---

## 📞 Questions fréquentes

### Q : Dois-je synchroniser les deux bases régulièrement ?
**R** : NON. Synchronisez seulement quand vous avez besoin des données de production pour déboguer.

### Q : Comment appliquer mes changements de modèles ?
**R** : Utilisez les migrations Django (`makemigrations` en local, puis `migrate` sur le VPS).

### Q : Et si je casse la base de production ?
**R** : Les sauvegardes automatiques vous permettent de restaurer (voir `SAUVEGARDES_AUTOMATIQUES.md`).

### Q : Puis-je accéder à la base du VPS depuis mon ordinateur ?
**R** : Oui, mais ce n'est PAS recommandé. Utilisez SSH tunnel si vraiment nécessaire.