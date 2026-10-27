# Signe les installateurs Hydria Sync (Authenticode). A lancer APRES `gradlew :syncclient:packageExe :syncclient:packageMsi`.
#
# Depuis juin 2023, un certificat de signature de code neuf a sa cle privee sur un materiel certifie (cle USB du
# fournisseur) ou dans un service cloud : il n'existe plus de fichier .pfx a telecharger. Trois modes, choisis
# par les variables d'environnement (jamais de mot de passe ni de jeton dans un fichier du depot) :
#
#   1. Certificat dans le magasin Windows (cle USB branchee, ou pilote cloud du fournisseur : SSL.com eSigner,
#      DigiCert KeyLocker...) :
#        $env:HYDRIA_CERT_THUMBPRINT = "empreinte SHA-1 du certificat"
#   2. Azure Artifact Signing (ex-Trusted Signing), via la DLL Azure.CodeSigning.Dlib :
#        $env:HYDRIA_SIGN_DLIB     = "C:\...\Azure.CodeSigning.Dlib.dll"
#        $env:HYDRIA_SIGN_METADATA = "C:\...\metadata.json"
#   3. Ancien certificat en fichier .pfx (emis avant juin 2023, ou certificat d'essai) :
#        $env:HYDRIA_CERT_PFX = "C:\chemin\certificat.pfx" ; $env:HYDRIA_CERT_PASSWORD = "..."
#
#   .\syncclient\packaging\signer.ps1
#
# Necessite signtool.exe (Windows SDK : composant « Signing Tools »). Sans signature, SmartScreen affiche
# « Windows a protege votre ordinateur » pour tout installateur telecharge (voir syncclient/README.md).
$ErrorActionPreference = 'Stop'

$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
if (-not $signtool) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $signtool) { throw "signtool.exe introuvable : installez le Windows SDK (composant « Signing Tools »)." }

# Arguments propres a chaque mode ; SHA-256 et horodatage : la signature reste valide apres l'expiration du certificat.
$horodatage = @('/tr', 'http://timestamp.digicert.com', '/td', 'SHA256')
if ($env:HYDRIA_CERT_THUMBPRINT) {
    $mode = 'magasin Windows'
    $args_signature = @('/fd', 'SHA256', '/sha1', $env:HYDRIA_CERT_THUMBPRINT, '/s', 'My') + $horodatage
} elseif ($env:HYDRIA_SIGN_DLIB -and $env:HYDRIA_SIGN_METADATA) {
    if (-not (Test-Path $env:HYDRIA_SIGN_DLIB)) { throw "HYDRIA_SIGN_DLIB introuvable : $env:HYDRIA_SIGN_DLIB" }
    if (-not (Test-Path $env:HYDRIA_SIGN_METADATA)) { throw "HYDRIA_SIGN_METADATA introuvable : $env:HYDRIA_SIGN_METADATA" }
    $mode = 'Azure Artifact Signing'
    # le service fournit son propre horodatage : /tr et /td sont ceux de la documentation Microsoft
    $args_signature = @('/fd', 'SHA256', '/dlib', $env:HYDRIA_SIGN_DLIB, '/dmdf', $env:HYDRIA_SIGN_METADATA,
        '/tr', 'http://timestamp.acs.microsoft.com', '/td', 'SHA256')
} elseif ($env:HYDRIA_CERT_PFX) {
    if (-not (Test-Path $env:HYDRIA_CERT_PFX)) { throw "HYDRIA_CERT_PFX introuvable : $env:HYDRIA_CERT_PFX" }
    if (-not $env:HYDRIA_CERT_PASSWORD) { throw "HYDRIA_CERT_PASSWORD non defini." }
    $mode = 'fichier .pfx'
    $args_signature = @('/fd', 'SHA256', '/f', $env:HYDRIA_CERT_PFX, '/p', $env:HYDRIA_CERT_PASSWORD) + $horodatage
} else {
    throw ("Aucun certificat indique. Definissez HYDRIA_CERT_THUMBPRINT (certificat dans le magasin Windows), " +
        "ou HYDRIA_SIGN_DLIB + HYDRIA_SIGN_METADATA (Azure Artifact Signing), ou HYDRIA_CERT_PFX + HYDRIA_CERT_PASSWORD.")
}

$racine = Join-Path $PSScriptRoot '..\build\compose\binaries\main'
$fichiers = @(Get-ChildItem (Join-Path $racine 'exe'), (Join-Path $racine 'msi') -Include *.exe, *.msi -File -ErrorAction SilentlyContinue)
if (-not $fichiers) { throw "Aucun installateur dans $racine : lancez d'abord gradlew :syncclient:packageExe :syncclient:packageMsi." }

Write-Host "Signature ($mode) de $($fichiers.Count) fichier(s)."
foreach ($f in $fichiers) {
    Write-Host "  $($f.Name)..."
    & $signtool sign @args_signature /d "Hydria Sync" $f.FullName
    if ($LASTEXITCODE -ne 0) { throw "Echec de la signature de $($f.Name)." }
    & $signtool verify /pa $f.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "La signature de $($f.Name) n'est pas valide." }
}
Write-Host "Termine : $($fichiers.Count) fichier(s) signe(s). Republiez-les sur le serveur."
