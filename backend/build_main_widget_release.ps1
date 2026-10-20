$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot 'desktop_widgets\WeatherWidgetElectron'
$electronDist = Join-Path $env:USERPROFILE 'Desktop\WeatherWidgetElectron\node_modules\electron\dist'
$downloadRoot = Join-Path $PSScriptRoot 'static\downloads\android'
$androidApk = Join-Path $projectRoot 'android_widgets\HydriaWidgetAndroid\app\build\outputs\apk\debug\app-debug.apk'
$package = Get-Content (Join-Path $sourceRoot 'package.json') -Raw | ConvertFrom-Json
$windowsVersion = [string]$package.version
$androidVersion = '1.24'
$stagingParent = Join-Path $PSScriptRoot '.windows-package-staging'
$stagingRoot = Join-Path $stagingParent ("hydria-main-widget-" + [guid]::NewGuid().ToString('N'))
$packageRoot = Join-Path $stagingRoot 'HydriaWidgetWindows'
$appRoot = Join-Path $packageRoot 'resources\app'

if (-not (Test-Path -LiteralPath (Join-Path $electronDist 'electron.exe'))) {
    throw "Electron est introuvable dans $electronDist"
}
if (-not (Test-Path -LiteralPath $androidApk)) {
    throw "APK Android introuvable : $androidApk"
}

New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    Copy-Item -Path (Join-Path $electronDist '*') -Destination $packageRoot -Recurse -Force
    Move-Item -LiteralPath (Join-Path $packageRoot 'electron.exe') -Destination (Join-Path $packageRoot 'Hydria Widget.exe') -Force
    New-Item -ItemType Directory -Path $appRoot -Force | Out-Null

    foreach ($file in @('main.js', 'preload.js', 'package.json', 'icon.png', 'weather_widget.html')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination (Join-Path $appRoot $file) -Force
    }

    $versionedZip = Join-Path $downloadRoot "hydria-widget-windows-$windowsVersion.zip"
    $latestZip = Join-Path $downloadRoot 'hydria-widget-windows.zip'
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $versionedZip -CompressionLevel Optimal -Force
    Copy-Item -LiteralPath $versionedZip -Destination $latestZip -Force

    $versionedApk = Join-Path $downloadRoot "hydria-widget-$androidVersion.apk"
    $latestApk = Join-Path $downloadRoot 'hydria-widget.apk'
    Copy-Item -LiteralPath $androidApk -Destination $versionedApk -Force
    Copy-Item -LiteralPath $androidApk -Destination $latestApk -Force

    Write-Host "Cree : $versionedZip"
    Write-Host "Cree : $latestZip"
    Write-Host "Cree : $versionedApk"
    Write-Host "Cree : $latestApk"
}
finally {
    $resolvedParent = [System.IO.Path]::GetFullPath($stagingParent) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedStage = [System.IO.Path]::GetFullPath($stagingRoot)
    if ($resolvedStage.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStage)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
