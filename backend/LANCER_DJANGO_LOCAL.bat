@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo Serveur Django Local (http://localhost:8000)
echo ========================================
echo.

echo Activation de l'environnement virtuel...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Aucun environnement virtuel trouve ^(.venv ou venv^).
    exit /b 1
)

echo.
echo Lancement du serveur Django...
echo.
echo IMPORTANT: Pour tester l'agent local DiameX, acceder à:
echo   http://localhost:8000/comptabilite/import/
echo.
echo Au lieu de:
echo   https://www.hydria.mg/comptabilite/import/
echo.
echo Raison: Le navigateur bloque HTTPS vers HTTP (Mixed Content)
echo.
echo ========================================
echo.

python manage.py runserver

echo.
echo Serveur arrete.
pause
