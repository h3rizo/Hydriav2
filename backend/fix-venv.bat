@echo off
echo Suppression de l'ancien environnement virtuel...
if exist venv rmdir /s /q venv

echo Creation d'un nouvel environnement virtuel...
python -m venv venv

echo Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

echo Mise a jour de pip...
pip install --upgrade pip

echo Installation des dependances...
pip install -r requirements.txt

echo.
echo Environnement virtuel repare avec succes!
echo Vous pouvez maintenant utiliser:
echo   python manage.py migrate
echo   python manage.py runserver
pause