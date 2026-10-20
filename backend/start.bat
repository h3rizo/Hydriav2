@echo off
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
echo Installation/verification des dependances...
pip install -r requirements.txt

echo.
echo Migrations de la base de donnees...
python manage.py migrate

echo.
echo Demarrage du serveur Django...
echo Ouvrir http://127.0.0.1:8000/ dans votre navigateur
python manage.py runserver

pause
