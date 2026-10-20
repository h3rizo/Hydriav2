param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

Add-Type -AssemblyName System.Drawing

$masterPath = Join-Path $PSScriptRoot 'hydria-vase-master.png'
$resPath = Join-Path $ProjectRoot 'app\src\main\res'

if (-not (Test-Path -LiteralPath $masterPath)) {
    throw "Master icon not found: $masterPath"
}

function Get-VisibleBounds([System.Drawing.Bitmap]$bitmap) {
    $minX = $bitmap.Width
    $minY = $bitmap.Height
    $maxX = -1
    $maxY = -1
    for ($y = 0; $y -lt $bitmap.Height; $y += 2) {
        for ($x = 0; $x -lt $bitmap.Width; $x += 2) {
            if ($bitmap.GetPixel($x, $y).A -gt 8) {
                if ($x -lt $minX) { $minX = $x }
                if ($y -lt $minY) { $minY = $y }
                if ($x -gt $maxX) { $maxX = $x }
                if ($y -gt $maxY) { $maxY = $y }
            }
        }
    }
    if ($maxX -lt 0) { throw 'The master icon has no visible pixels.' }
    return [System.Drawing.Rectangle]::FromLTRB($minX, $minY, $maxX + 1, $maxY + 1)
}

function New-Canvas([int]$size) {
    return New-Object System.Drawing.Bitmap $size, $size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
}

function Set-Quality([System.Drawing.Graphics]$graphics) {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
}

function Add-RoundedRectangle(
    [System.Drawing.Graphics]$graphics,
    [System.Drawing.Brush]$brush,
    [System.Drawing.RectangleF]$rectangle,
    [float]$radius
) {
    $diameter = $radius * 2
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddArc($rectangle.X, $rectangle.Y, $diameter, $diameter, 180, 90)
    $path.AddArc($rectangle.Right - $diameter, $rectangle.Y, $diameter, $diameter, 270, 90)
    $path.AddArc($rectangle.Right - $diameter, $rectangle.Bottom - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($rectangle.X, $rectangle.Bottom - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    $graphics.FillPath($brush, $path)
    $path.Dispose()
}

function Draw-Vase(
    [System.Drawing.Graphics]$graphics,
    [System.Drawing.Bitmap]$source,
    [System.Drawing.Rectangle]$sourceBounds,
    [int]$canvasSize,
    [float]$heightRatio
) {
    $targetHeight = [int]($canvasSize * $heightRatio)
    $targetWidth = [int]($targetHeight * $sourceBounds.Width / $sourceBounds.Height)
    $target = New-Object System.Drawing.Rectangle ([int](($canvasSize - $targetWidth) / 2)), ([int](($canvasSize - $targetHeight) / 2)), $targetWidth, $targetHeight
    $graphics.DrawImage($source, $target, $sourceBounds, [System.Drawing.GraphicsUnit]::Pixel)
}

function Save-Png([System.Drawing.Bitmap]$bitmap, [string]$path) {
    $directory = Split-Path -Parent $path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
}

$source = New-Object System.Drawing.Bitmap $masterPath
$bounds = Get-VisibleBounds $source

try {
    $foreground = New-Canvas 432
    $graphics = [System.Drawing.Graphics]::FromImage($foreground)
    try {
        Set-Quality $graphics
        $graphics.Clear([System.Drawing.Color]::Transparent)
        # Keep the complete vase inside aggressive circular launcher masks.
        Draw-Vase $graphics $source $bounds 432 0.44
    } finally {
        $graphics.Dispose()
    }
    # 432 px in xxxhdpi = 108 dp, the native adaptive-icon viewport.
    # Keeping this asset out of drawable-nodpi prevents Android from treating
    # 432 px as 432 dp and cropping it inside the launcher mask.
    Save-Png $foreground (Join-Path $resPath 'drawable-xxxhdpi\hydria_vase_foreground.png')
    $foreground.Dispose()

    $densities = [ordered]@{
        'mipmap-mdpi' = 48
        'mipmap-hdpi' = 72
        'mipmap-xhdpi' = 96
        'mipmap-xxhdpi' = 144
        'mipmap-xxxhdpi' = 192
    }

    foreach ($density in $densities.GetEnumerator()) {
        $size = [int]$density.Value
        foreach ($round in @($false, $true)) {
            $canvas = New-Canvas $size
            $graphics = [System.Drawing.Graphics]::FromImage($canvas)
            try {
                Set-Quality $graphics
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $background = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 10, 29, 39))
                try {
                    if ($round) {
                        $graphics.FillEllipse($background, 0, 0, $size, $size)
                    } else {
                        Add-RoundedRectangle $graphics $background (New-Object System.Drawing.RectangleF 0, 0, $size, $size) ($size * 0.22)
                    }
                } finally {
                    $background.Dispose()
                }
                Draw-Vase $graphics $source $bounds $size 0.50
            } finally {
                $graphics.Dispose()
            }
            $fileName = if ($round) { 'ic_launcher_round.png' } else { 'ic_launcher.png' }
            Save-Png $canvas (Join-Path $resPath "$($density.Key)\$fileName")
            $canvas.Dispose()
        }
    }
} finally {
    $source.Dispose()
}

Write-Output "Hydria launcher icons generated from $masterPath"
