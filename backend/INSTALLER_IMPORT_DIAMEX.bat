@echo off
chcp 65001 >nul
cd /d "%~dp0"
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
pip install pyodbc requests pillow

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
