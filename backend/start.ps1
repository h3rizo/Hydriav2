# Script PowerShell pour demarrer l'application Hydria
$venvPath = $null
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    $venvPath = ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    $venvPath = ".\venv\Scripts\Activate.ps1"
} else {
    Write-Host "Aucun environnement virtuel trouve (.venv ou venv)." -ForegroundColor Red
    exit 1
}

Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Green
& $venvPath

Write-Host "`nInstallation/verification des dependances..." -ForegroundColor Green
pip install -r requirements.txt

Write-Host "`nMigrations de la base de donnees..." -ForegroundColor Green
python manage.py migrate

Write-Host "`nDemarrage du serveur Django..." -ForegroundColor Green
Write-Host "Ouvrir http://127.0.0.1:8000/ dans votre navigateur" -ForegroundColor Yellow
python manage.py runserver
