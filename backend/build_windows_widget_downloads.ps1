# -Only <zip> [<zip>...] : ne reconstruit que ces zips (ex. -Only hydria-planning-widget-windows.zip).
param([string[]]$Only)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $env:USERPROFILE 'Desktop'
$electronDist = Join-Path $desktopRoot 'WeatherWidgetElectron\node_modules\electron\dist'
$downloadRoot = Join-Path $PSScriptRoot 'static\downloads\android'
$stagingParent = Join-Path $PSScriptRoot '.windows-package-staging'
$stagingRoot = Join-Path $stagingParent ("hydria-widget-packages-" + [guid]::NewGuid().ToString('N'))

if (-not (Test-Path -LiteralPath (Join-Path $electronDist 'electron.exe'))) {
    throw "Electron est introuvable dans $electronDist"
}

$packages = @(
    @{
        Name = 'HydriaWidgetWindows'
        Exe = 'Hydria Widget.exe'
        Zip = 'hydria-widget-windows.zip'
        Source = Join-Path $projectRoot 'desktop_widgets\WeatherWidgetElectron'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'weather_widget.html')
    },
    @{
        Name = 'HydriaCompteursWidgetWindows'
        Exe = 'Hydria Compteurs.exe'
        Zip = 'hydria-compteurs-widget-windows.zip'
        Source = Join-Path $projectRoot 'desktop_widgets\CompteursTeteWidgetElectron'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'widget.html')
    },
    @{
        Name = 'HydriaDebitsWidgetWindows'
        Exe = 'Hydria Debits.exe'
        Zip = 'hydria-debits-widget-windows.zip'
        Source = Join-Path $projectRoot 'desktop_widgets\DebitsSourceWidgetElectron'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'widget.html')
    },
    @{
        Name = 'HydriaConsommationWidgetWindows'
        Exe = 'Hydria Consommation.exe'
        Zip = 'hydria-consommation-widget-windows.zip'
        Source = Join-Path $projectRoot 'desktop_widgets\ConsommationWidgetElectron'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'widget.html')
    },
    @{
        Name = 'HydriaActionsRapidesWindows'
        Exe = 'Hydria Actions Rapides.exe'
        Zip = 'hydria-actions-rapides-windows.zip'
        # Sources dans le depot depuis le 2026-09-23 (auparavant seulement sur le Bureau).
        Source = Join-Path $projectRoot 'desktop_widgets\HydriaQuickActions'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'bubble.html')
    },
    @{
        # Widget Planning combine (activites du jour + calendrier).
        Name = 'HydriaPlanningWidgetWindows'
        Exe = 'Hydria Planning.exe'
        Zip = 'hydria-planning-widget-windows.zip'
        Source = Join-Path $projectRoot 'desktop_widgets\PlanningWidgetElectron'
        Files = @('main.js', 'preload.js', 'package.json', 'icon.png', 'widget.html')
    }
)

if ($Only) {
    $packages = @($packages | Where-Object { $Only -contains $_.Zip })
    if (-not $packages) { throw "Aucun paquet ne correspond a : $($Only -join ', ')" }
}

New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

try {
    foreach ($package in $packages) {
        $packageRoot = Join-Path $stagingRoot $package.Name
        $appRoot = Join-Path $packageRoot 'resources\app'
        New-Item -ItemType Directory -Path $packageRoot | Out-Null
        Copy-Item -Path (Join-Path $electronDist '*') -Destination $packageRoot -Recurse -Force
        Move-Item -LiteralPath (Join-Path $packageRoot 'electron.exe') -Destination (Join-Path $packageRoot $package.Exe) -Force
        New-Item -ItemType Directory -Path $appRoot -Force | Out-Null

        foreach ($file in $package.Files) {
            Copy-Item -LiteralPath (Join-Path $package.Source $file) -Destination (Join-Path $appRoot $file) -Force
        }

        $zipPath = Join-Path $downloadRoot $package.Zip
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
        Write-Host ("Créé : {0}" -f $zipPath)
    }
}
finally {
    $resolvedParent = [System.IO.Path]::GetFullPath($stagingParent) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedStage = [System.IO.Path]::GetFullPath($stagingRoot)
    if ($resolvedStage.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStage)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
