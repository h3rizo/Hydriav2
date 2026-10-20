@echo off
chcp 65001 >nul
cd /d "%~dp0"
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
