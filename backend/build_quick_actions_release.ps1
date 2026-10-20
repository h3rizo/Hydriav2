$ErrorActionPreference = 'Stop'

$backendRoot = $PSScriptRoot
# Sources dans le depot depuis le 2026-09-23 (auparavant seulement sur le Bureau).
$sourceRoot = Join-Path (Split-Path -Parent $backendRoot) 'desktop_widgets\HydriaQuickActions'
$electronDist = Join-Path $env:USERPROFILE 'Desktop\WeatherWidgetElectron\node_modules\electron\dist'
$downloadRoot = Join-Path $backendRoot 'static\downloads\android'
$package = Get-Content (Join-Path $sourceRoot 'package.json') -Raw | ConvertFrom-Json
$version = [string]$package.version
$stagingParent = Join-Path $backendRoot '.windows-package-staging'
$stagingRoot = Join-Path $stagingParent ("hydria-quick-actions-" + [guid]::NewGuid().ToString('N'))
$packageRoot = Join-Path $stagingRoot 'HydriaActionsRapidesWindows'
$appRoot = Join-Path $packageRoot 'resources\app'

if (-not (Test-Path -LiteralPath (Join-Path $electronDist 'electron.exe'))) {
    throw "Electron est introuvable dans $electronDist"
}

New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    Copy-Item -Path (Join-Path $electronDist '*') -Destination $packageRoot -Recurse -Force
    Move-Item -LiteralPath (Join-Path $packageRoot 'electron.exe') -Destination (Join-Path $packageRoot 'Hydria Actions Rapides.exe') -Force
    New-Item -ItemType Directory -Path $appRoot -Force | Out-Null

    foreach ($file in @('main.js', 'preload.js', 'package.json', 'icon.png', 'bubble.html')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination (Join-Path $appRoot $file) -Force
    }

    $versionedZip = Join-Path $downloadRoot "hydria-actions-rapides-windows-$version.zip"
    $latestZip = Join-Path $downloadRoot 'hydria-actions-rapides-windows.zip'
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $versionedZip -CompressionLevel Optimal -Force
    Copy-Item -LiteralPath $versionedZip -Destination $latestZip -Force

    Write-Host "Cree : $versionedZip"
    Write-Host "Cree : $latestZip"
}
finally {
    $resolvedParent = [System.IO.Path]::GetFullPath($stagingParent) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedStage = [System.IO.Path]::GetFullPath($stagingRoot)
    if ($resolvedStage.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStage)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
