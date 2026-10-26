# Signe les installateurs Hydria Sync (Authenticode). A lancer APRES `gradlew :syncclient:packageExe :syncclient:packageMsi`.
#
#   $env:HYDRIA_CERT_PFX      = "C:\chemin\certificat.pfx"
#   $env:HYDRIA_CERT_PASSWORD = "mot de passe du certificat"   (ne jamais l'ecrire dans un fichier du depot)
#   .\syncclient\packaging\signer.ps1
#
# Necessite signtool.exe (Windows SDK : https://developer.microsoft.com/windows/downloads/windows-sdk/) et un
# certificat de signature de code delivre par une autorite reconnue. Sans signature, SmartScreen affiche
# « Windows a protege votre ordinateur » pour tout installateur telecharge (voir syncclient/README.md).
$ErrorActionPreference = 'Stop'

if (-not $env:HYDRIA_CERT_PFX -or -not (Test-Path $env:HYDRIA_CERT_PFX)) { throw "HYDRIA_CERT_PFX absent ou introuvable." }
if (-not $env:HYDRIA_CERT_PASSWORD) { throw "HYDRIA_CERT_PASSWORD non defini." }

$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
if (-not $signtool) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $signtool) { throw "signtool.exe introuvable : installez le Windows SDK (composant « Signing Tools »)." }

$racine = Join-Path $PSScriptRoot '..\build\compose\binaries\main'
$fichiers = @(Get-ChildItem (Join-Path $racine 'exe'), (Join-Path $racine 'msi') -Include *.exe, *.msi -File -ErrorAction SilentlyContinue)
if (-not $fichiers) { throw "Aucun installateur dans $racine : lancez d'abord gradlew :syncclient:packageExe :syncclient:packageMsi." }

foreach ($f in $fichiers) {
    Write-Host "Signature de $($f.Name)..."
    # SHA-256 + horodatage : la signature reste valide apres l'expiration du certificat.
    & $signtool sign /fd SHA256 /f $env:HYDRIA_CERT_PFX /p $env:HYDRIA_CERT_PASSWORD `
        /tr http://timestamp.digicert.com /td SHA256 /d "Hydria Sync" $f.FullName
    if ($LASTEXITCODE -ne 0) { throw "Echec de la signature de $($f.Name)." }
    & $signtool verify /pa $f.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "La signature de $($f.Name) n'est pas valide." }
}
Write-Host "Termine : $($fichiers.Count) fichier(s) signe(s)."
