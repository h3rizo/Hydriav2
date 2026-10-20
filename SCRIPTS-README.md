# 🚀 Scripts GitHub pour Hydria

## 📁 Scripts Disponibles

### 🎯 `deploy-complete.bat` - **SCRIPT PRINCIPAL ULTIME**
**Déploiement complet GitHub + Render**
- ✅ Exécute deploy-github.bat automatiquement
- ✅ Exécute deploy-render.bat automatiquement
- ✅ Guide complet du début à la fin
- ✅ Ouvre les liens nécessaires

**Usage :**
```cmd
deploy-complete.bat
```

### 🔧 `deploy-github.bat` - Configuration GitHub
**Déploiement automatique GitHub**
- ✅ Configure Git automatiquement
- ✅ Crée .gitignore et README.md
- ✅ Initialise le repository
- ✅ Fait le commit initial
- ✅ Pousse vers GitHub

**Usage :**
```cmd
deploy-github.bat
```

### 🌐 `deploy-render.bat` - Configuration Render.com
**Préparation déploiement Render**
- ✅ Crée render.yaml (Blueprint)
- ✅ Configure Django pour production
- ✅ Optimise package.json frontend
- ✅ Génère documentation Render

**Usage :**
```cmd
deploy-render.bat
```

### 📝 `setup-github.bat` - Configuration locale
**Prépare le projet pour GitHub (sans push)**
- ✅ Configure Git
- ✅ Crée les fichiers nécessaires
- ✅ Fait le commit initial
- ⚠️ N'envoie PAS vers GitHub

**Usage :**
```cmd
setup-github.bat
```

### 🚀 `push-to-github.bat` - Push uniquement
**Pousse un projet déjà configuré vers GitHub**
- ✅ Ajoute l'origine remote
- ✅ Pousse vers GitHub
- ⚠️ Le projet doit déjà être initialisé

**Usage :**
```cmd
push-to-github.bat
```

### ⚡ `commit-changes.bat` - Commit rapide
**Commit et push rapide des changements**
- ✅ Ajoute tous les fichiers modifiés
- ✅ Commit avec message personnalisé
- ✅ Push automatique

**Usage :**
```cmd
commit-changes.bat
```

## 📋 Workflow Recommandé

### 🎯 **Première fois (nouveau projet)**
```cmd
REM 1. Déploiement complet automatique
deploy-github.bat
```

### 🔄 **Modifications quotidiennes**
```cmd
REM 2. Commit rapide des changements
commit-changes.bat
```

## 🛠️ Prérequis

- ✅ **Git installé** (https://git-scm.com/download/win)
- ✅ **Compte GitHub** avec droits de création de repository
- ✅ **Identifiants Git configurés** (ou le script le fera)

## 🎨 Fonctionnalités des Scripts

### 🌈 Interface Colorée
- 🟢 **Vert** : Succès
- 🟡 **Jaune** : Information/En cours
- 🔴 **Rouge** : Erreur
- 🔵 **Bleu** : Instructions

### 🔒 Sécurité
- ✅ **.gitignore automatique** pour exclure les fichiers sensibles
- ✅ **Vérification des prérequis** avant exécution
- ✅ **Gestion d'erreurs** avec messages explicites

### 📖 Documentation Auto-générée
- ✅ **README.md complet** avec toutes les infos projet
- ✅ **Structure du projet** documentée
- ✅ **Instructions d'installation** incluses

## 🆘 Dépannage

### ❌ "Git n'est pas reconnu"
**Solution :**
1. Installer Git : https://git-scm.com/download/win
2. Redémarrer le terminal
3. Ou ajouter Git au PATH

### ❌ "Repository already exists"
**Solution :**
1. Supprimer le repository sur GitHub
2. Ou utiliser `push-to-github.bat` à la place

### ❌ "Permission denied"
**Solution :**
1. Vérifier vos droits sur le repository
2. Configurer l'authentification GitHub (token)
3. Ou utiliser SSH au lieu de HTTPS

## 📚 Ressources Utiles

- 📖 [Documentation Git](https://git-scm.com/doc)
- 🐙 [GitHub Guides](https://guides.github.com/)
- 🔑 [GitHub SSH Setup](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
- 🏺 [Documentation Hydria](README.md)

---

**🏺 Scripts générés par Claude Code pour optimiser votre workflow**