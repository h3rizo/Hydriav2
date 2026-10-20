# GUIDE DE DÉPLOIEMENT COMPLET - PACKAGE IMPORT DIAMEX

## Vue d'ensemble
Ce guide vous permet de déployer manuellement les 5 fichiers du package d'import DiameX sur le VPS, en contournant les problèmes d'authentification SSH automatisée.

## Prérequis
- ✅ Session SSH active sur le VPS : `ssh soakoja@46.105.73.48`
- ✅ Répertoire de destination : `/home/soakoja/hydria/backend`

---

## MÉTHODE DE DÉPLOIEMENT EN 3 ÉTAPES

### ÉTAPE 1 : Créer les 3 fichiers courts via heredoc

**Dans votre session SSH active**, exécutez ces commandes une par une :

#### 1.1 - Créer config_import.ini
```bash
cd /home/soakoja/hydria/backend && cat > config_import.ini << 'EOF'
# Configuration pour l'import DiameX Local
# Ce fichier peut être modifié avec le Bloc-notes

[SERVEUR]
# URL du serveur Django (production)
DJANGO_URL = https://www.hydria.mg

# Pour tests en local, décommentez la ligne ci-dessous et commentez celle du dessus
# DJANGO_URL = http://localhost:8000

[OPTIONS]
# Timeout pour les requêtes (en secondes)
TIMEOUT = 300

# Afficher les détails lors de l'import (True/False)
VERBOSE = True
EOF
```

Vérification : `cat config_import.ini` (doit afficher 16 lignes)

#### 1.2 - Créer INSTALLER_IMPORT_DIAMEX.bat
```bash
cd /home/soakoja/hydria/backend && cat > INSTALLER_IMPORT_DIAMEX.bat << 'EOF'
@echo off
chcp 65001 >nul
echo ========================================
echo Installation Import DiameX Local
echo ========================================
echo.

REM Vérifier si Python est installé
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installé ou n'est pas dans le PATH
    echo.
    echo Veuillez installer Python depuis https://www.python.org/downloads/
    echo IMPORTANT: Cochez "Add Python to PATH" lors de l'installation
    pause
    exit /b 1
)

echo [OK] Python détecté:
python --version
echo.

REM Installer les dépendances
echo Installation des dépendances Python...
pip install --upgrade pip
pip install pyodbc requests

if errorlevel 1 (
    echo [ERREUR] Échec de l'installation des dépendances
    pause
    exit /b 1
)

echo.
echo [OK] Dépendances installées avec succès
echo.

REM Vérifier si le driver Access est disponible
echo Vérification du driver Microsoft Access...
python -c "import pyodbc; drivers = [d for d in pyodbc.drivers() if 'Access' in d]; print('Drivers Access trouvés:', drivers if drivers else 'AUCUN'); exit(0 if drivers else 1)"

if errorlevel 1 (
    echo.
    echo [ATTENTION] Driver Microsoft Access non détecté
    echo.
    echo Le driver est automatiquement installé avec Microsoft Office.
    echo Si vous n'avez pas Office, vous pouvez installer:
    echo - Microsoft Access Database Engine 2016 Redistributable
    echo   https://www.microsoft.com/en-us/download/details.aspx?id=54920
    echo.
    echo Choisissez la version selon votre système:
    echo - 32-bit (x86) pour Windows 32-bit ou Office 32-bit
    echo - 64-bit (x64) pour Windows 64-bit ET Office 64-bit
    echo.
    pause
) else (
    echo [OK] Driver Access disponible
)

echo.
echo ========================================
echo Installation terminée !
echo ========================================
echo.
echo Prochaine étape:
echo 1. Ouvrez "config_import.ini" avec le Bloc-notes
echo 2. Vérifiez que l'URL Django est correcte
echo 3. Lancez "LANCER_IMPORT.bat" pour importer
echo.
pause
EOF
```

Vérification : `wc -l INSTALLER_IMPORT_DIAMEX.bat` (doit afficher 70 lignes)

#### 1.3 - Créer LANCER_IMPORT.bat
```bash
cd /home/soakoja/hydria/backend && cat > LANCER_IMPORT.bat << 'EOF'
@echo off
chcp 65001 >nul
echo ========================================
echo Import DiameX Local vers Hydria
echo ========================================
echo.

REM Vérifier si Python est disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installé ou n'est pas dans le PATH
    echo.
    echo Veuillez d'abord exécuter INSTALLER_IMPORT_DIAMEX.bat
    pause
    exit /b 1
)

REM Vérifier si le fichier de configuration existe
if not exist "config_import.ini" (
    echo [ERREUR] Fichier config_import.ini introuvable
    echo.
    echo Assurez-vous que config_import.ini est dans le même dossier
    pause
    exit /b 1
)

REM Vérifier si le script d'import existe
if not exist "import_diamex_portable.py" (
    echo [ERREUR] Script import_diamex_portable.py introuvable
    echo.
    echo Assurez-vous que import_diamex_portable.py est dans le même dossier
    pause
    exit /b 1
)

echo [INFO] Lancement de l'import...
echo.

REM Lancer l'import
python import_diamex_portable.py

echo.
echo ========================================
echo Import terminé
echo ========================================
echo.
pause
EOF
```

Vérification : `wc -l LANCER_IMPORT.bat` (doit afficher 47 lignes)

---

### ÉTAPE 2 : Créer le script Python pour les fichiers longs

**Dans votre session SSH**, créez le fichier `create_long_files.py` :

```bash
cd /home/soakoja/hydria/backend
nano create_long_files.py
```

**Dans l'éditeur nano :**
1. Copiez TOUT le contenu du fichier `create_long_files.py` (celui que je viens de créer dans votre dossier backend local)
2. Collez dans nano (Ctrl+Shift+V ou clic droit)
3. Enregistrez : Ctrl+O, puis Entrée
4. Quittez : Ctrl+X

**Alternativement**, si vous avez accès SFTP (FileZilla/WinSCP), uploadez directement `create_long_files.py` sur le VPS.

---

### ÉTAPE 3 : Exécuter le script pour créer les 2 fichiers longs

**Dans votre session SSH** :

```bash
cd /home/soakoja/hydria/backend
python3 create_long_files.py
```

**Sortie attendue** :
```
================================================================================
CRÉATION DES FICHIERS LONGS SUR LE VPS
================================================================================
[OK] Fichier 'import_diamex_portable.py' créé (309 lignes)
[OK] Fichier 'README_IMPORT_DIAMEX.txt' créé (220 lignes)

================================================================================
VÉRIFICATION
================================================================================
✓ import_diamex_portable.py : XXXXX bytes
✓ README_IMPORT_DIAMEX.txt : XXXXX bytes

================================================================================
PROCHAINES ÉTAPES
================================================================================
1. Vérifier que les 3 autres fichiers existent déjà :
   - INSTALLER_IMPORT_DIAMEX.bat
   - LANCER_IMPORT.bat
   - config_import.ini

2. Lister tous les fichiers avec :
   ls -lh *.bat *.ini *.py *.txt

3. Le package est maintenant complet et prêt pour le ZIP !
================================================================================
```

---

## VÉRIFICATION FINALE

**Commande de vérification complète** :
```bash
cd /home/soakoja/hydria/backend
ls -lh *.bat *.ini *.py *.txt
```

**Vous devez voir 5 fichiers** :
- ✅ `INSTALLER_IMPORT_DIAMEX.bat` (~3-4 KB)
- ✅ `LANCER_IMPORT.bat` (~1-2 KB)
- ✅ `config_import.ini` (~0.5 KB)
- ✅ `import_diamex_portable.py` (~10-12 KB)
- ✅ `README_IMPORT_DIAMEX.txt` (~8-10 KB)

**Optionnel** : Supprimer le script helper :
```bash
rm create_long_files.py
```

---

## TEST DU PACKAGE ZIP

Une fois tous les fichiers créés sur le VPS, testez le téléchargement :

1. **Ouvrir l'interface web** : https://www.hydria.mg/comptabilite/import/
2. **Cliquer sur "Télécharger le package"**
3. **Vérifier le ZIP téléchargé** :
   - Nom : `Import_DiameX_Local.zip`
   - Contient les 5 fichiers
   - Taille : ~20-30 KB

4. **Tester le package (sur un PC Windows de test)** :
   - Extraire le ZIP
   - Double-clic sur `INSTALLER_IMPORT_DIAMEX.bat`
   - Vérifier l'installation Python + dépendances
   - Lire `README_IMPORT_DIAMEX.txt`
   - Configurer `config_import.ini` si nécessaire
   - Tester `LANCER_IMPORT.bat` (nécessite un fichier Access DiameX)

---

## RÉSOLUTION DE PROBLÈMES

### Problème : "Permission denied" lors de la création des fichiers
**Solution** :
```bash
# Vérifier les permissions du répertoire
ls -ld /home/soakoja/hydria/backend

# Changer le propriétaire si nécessaire (avec sudo)
sudo chown soakoja:soakoja /home/soakoja/hydria/backend

# Ou créer dans un répertoire temporaire puis déplacer
cd /tmp
# ... créer les fichiers ...
mv *.bat *.ini *.py *.txt /home/soakoja/hydria/backend/
```

### Problème : "command not found: python3"
**Solution** :
```bash
# Essayer avec python2
python create_long_files.py

# Ou installer python3
sudo apt-get update
sudo apt-get install python3
```

### Problème : Le ZIP téléchargé ne contient pas tous les fichiers
**Solution** :
```bash
# Vérifier que le code Django a accès au répertoire
cd /home/soakoja/hydria/backend
ls -la *.bat *.ini *.py *.txt

# Vérifier les logs Django
tail -f /path/to/django/logs/error.log

# Redémarrer Gunicorn après déploiement
sudo systemctl restart gunicorn
```

---

## MAINTENANCE FUTURE

Pour mettre à jour le package :

1. **Modifier les fichiers localement** (sur votre PC Windows)
2. **Redéployer sur le VPS** :
   - Soit : Refaire les étapes 1-3 de ce guide
   - Soit : Utiliser SFTP pour uploader directement les fichiers modifiés
3. **Redémarrer Gunicorn** : `sudo systemctl restart gunicorn`
4. **Tester le nouveau ZIP**

---

## RÉSUMÉ DES FICHIERS

| Fichier | Rôle | Taille | Méthode création |
|---------|------|--------|------------------|
| **INSTALLER_IMPORT_DIAMEX.bat** | Installe Python et dépendances | ~3 KB | Heredoc (Étape 1.2) |
| **LANCER_IMPORT.bat** | Lance l'import | ~1 KB | Heredoc (Étape 1.3) |
| **config_import.ini** | Configuration utilisateur | ~0.5 KB | Heredoc (Étape 1.1) |
| **import_diamex_portable.py** | Script d'import principal | ~10 KB | Python script (Étape 3) |
| **README_IMPORT_DIAMEX.txt** | Documentation | ~8 KB | Python script (Étape 3) |

**Total : 5 fichiers, ~22 KB**

---

## CONTACT ET SUPPORT

En cas de problème persistant :
- Vérifier les logs Django : `/var/log/gunicorn/error.log`
- Vérifier les permissions : `namei -l /home/soakoja/hydria/backend/`
- Consulter la documentation Django du projet

---

**Dernière mise à jour** : 8 janvier 2026
**Auteur** : Claude Code Assistant
**Version** : 1.0