param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$original=[Drawing.Image]::FromFile($Source)
try {
    foreach($entry in @(@('StoreLogo.png',50),@('Square44x44Logo.png',44),@('Square150x150Logo.png',150))) {
        $size=[int]$entry[1]
        $bitmap=New-Object Drawing.Bitmap($size,$size)
        $graphics=[Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([Drawing.Color]::Transparent)
            $graphics.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.DrawImage($original,0,0,$size,$size)
            $bitmap.Save((Join-Path $Destination $entry[0]),[Drawing.Imaging.ImageFormat]::Png)
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
    }
} finally { $original.Dispose() }
