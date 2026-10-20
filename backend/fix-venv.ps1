# Script PowerShell pour réparer l'environnement virtuel corrompu
Write-Host "Suppression de l'ancien environnement virtuel..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Remove-Item -Recurse -Force venv
}

Write-Host "Création d'un nouvel environnement virtuel..." -ForegroundColor Green
python -m venv venv

Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Green
.\venv\Scripts\Activate.ps1

Write-Host "Mise à jour de pip..." -ForegroundColor Green
pip install --upgrade pip

Write-Host "Installation des dépendances..." -ForegroundColor Green
pip install -r requirements.txt

Write-Host "`nEnvironnement virtuel réparé avec succès!" -ForegroundColor Green
Write-Host "Vous pouvez maintenant utiliser:" -ForegroundColor Yellow
Write-Host "  python manage.py migrate" -ForegroundColor White
Write-Host "  python manage.py runserver" -ForegroundColor White