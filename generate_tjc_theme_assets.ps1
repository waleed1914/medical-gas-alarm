Add-Type -AssemblyName System.Drawing

$OutputDirectory = Join-Path $PSScriptRoot "tjc_assets_theme"
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$PaleBlue = [System.Drawing.Color]::FromArgb(228, 244, 252)
$White = [System.Drawing.Color]::White
$Black = [System.Drawing.Color]::Black
$Blue = [System.Drawing.Color]::FromArgb(20, 111, 224)
$PaleYellow = [System.Drawing.Color]::FromArgb(255, 242, 153)
$PaleGreen = [System.Drawing.Color]::FromArgb(190, 244, 194)
$PaleGrey = [System.Drawing.Color]::FromArgb(224, 224, 224)

function New-Canvas([int]$Width, [int]$Height, [System.Drawing.Color]$StripColor) {
    $Bitmap = [System.Drawing.Bitmap]::new($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $Graphics.Clear($PaleBlue)
    $Graphics.FillRectangle([System.Drawing.SolidBrush]::new($StripColor), 2, $Height - 17, $Width - 4, 15)
    $Graphics.DrawRectangle([System.Drawing.Pen]::new($Black, 2), 1, 1, $Width - 3, $Height - 3)
    $Graphics.DrawLine([System.Drawing.Pen]::new($Blue, 2), 2, $Height - 18, $Width - 2, $Height - 18)
    return @($Bitmap, $Graphics)
}

function Draw-Label($Graphics, [string]$Text, [int]$X, [int]$Y, [int]$Width, [int]$Height, [float]$Size) {
    $Font = [System.Drawing.Font]::new("Arial Narrow", $Size, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $Format = [System.Drawing.StringFormat]::new()
    $Format.Alignment = [System.Drawing.StringAlignment]::Center
    $Format.LineAlignment = [System.Drawing.StringAlignment]::Center
    $Graphics.DrawString($Text, $Font, [System.Drawing.Brushes]::Black, [System.Drawing.RectangleF]::new($X, $Y, $Width, $Height), $Format)
    $Format.Dispose()
    $Font.Dispose()
}

function Draw-Speaker($Graphics, [bool]$Muted) {
    $Points = [System.Drawing.Point[]]@(
        [System.Drawing.Point]::new(12, 21),
        [System.Drawing.Point]::new(23, 21),
        [System.Drawing.Point]::new(35, 12),
        [System.Drawing.Point]::new(35, 42),
        [System.Drawing.Point]::new(23, 33),
        [System.Drawing.Point]::new(12, 33)
    )
    $Graphics.FillPolygon([System.Drawing.Brushes]::Black, $Points)
    $Pen = [System.Drawing.Pen]::new($Black, 3)
    if ($Muted) {
        $Graphics.DrawLine($Pen, 10, 12, 43, 43)
    } else {
        $Graphics.DrawArc($Pen, 31, 17, 17, 20, -65, 130)
        $Graphics.DrawArc($Pen, 34, 12, 25, 30, -65, 130)
    }
    $Pen.Dispose()
}

function Draw-Ethernet($Graphics, [bool]$Connected) {
    $Pen = [System.Drawing.Pen]::new($Black, 3)
    $Graphics.DrawRectangle($Pen, 10, 11, 38, 29)
    for ($Index = 0; $Index -lt 5; $Index++) {
        $Graphics.DrawLine($Pen, 16 + ($Index * 6), 14, 16 + ($Index * 6), 22)
    }
    $Graphics.DrawLine($Pen, 19, 40, 19, 34)
    $Graphics.DrawLine($Pen, 39, 40, 39, 34)
    if (-not $Connected) {
        $Graphics.DrawLine($Pen, 9, 10, 49, 42)
        $Graphics.DrawLine($Pen, 49, 10, 9, 42)
    }
    $Pen.Dispose()
}

function Draw-Test($Graphics, [bool]$Active) {
    $Pen = [System.Drawing.Pen]::new($Black, 3)
    $Graphics.DrawArc($Pen, 10, 10, 37, 32, 35, 255)
    $Arrow = [System.Drawing.Point[]]@(
        [System.Drawing.Point]::new(44, 9),
        [System.Drawing.Point]::new(50, 20),
        [System.Drawing.Point]::new(38, 19)
    )
    $Graphics.FillPolygon([System.Drawing.Brushes]::Black, $Arrow)
    if ($Active) {
        $Graphics.DrawLine($Pen, 20, 27, 27, 34)
        $Graphics.DrawLine($Pen, 27, 34, 40, 19)
    }
    $Pen.Dispose()
}

function Save-Button([string]$Name, [string]$Label, [string]$Icon, [bool]$Active, [System.Drawing.Color]$StripColor, [int]$Width, [float]$FontSize) {
    $Objects = New-Canvas $Width 60 $StripColor
    $Bitmap = $Objects[0]
    $Graphics = $Objects[1]

    if ($Icon -eq "speaker") { Draw-Speaker $Graphics $Active }
    if ($Icon -eq "ethernet") { Draw-Ethernet $Graphics $Active }
    if ($Icon -eq "test") { Draw-Test $Graphics $Active }

    Draw-Label $Graphics $Label 55 0 ($Width - 57) 43 $FontSize
    $Path = Join-Path $OutputDirectory ($Name + ".png")
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $Graphics.Dispose()
    $Bitmap.Dispose()
}

function Save-EthernetIndicator([string]$Name, [bool]$Connected, [System.Drawing.Color]$StripColor) {
    $Objects = New-Canvas 52 60 $StripColor
    $Bitmap = $Objects[0]
    $Graphics = $Objects[1]
    Draw-Ethernet $Graphics $Connected
    $Path = Join-Path $OutputDirectory ($Name + ".png")
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $Graphics.Dispose()
    $Bitmap.Dispose()
}

Save-Button "mute_action" "MUTE" "speaker" $false $White 150 22
Save-Button "unmute_action" "UNMUTE" "speaker" $true $PaleYellow 150 19
Save-Button "ethernet_connected" "CONNECTED" "ethernet" $true $PaleGreen 180 17
Save-Button "ethernet_disconnected" "DISCONNECTED" "ethernet" $false $PaleGrey 180 12
Save-Button "test_ready" "TEST" "test" $false $White 150 22
Save-Button "test_active" "TESTING" "test" $true $PaleYellow 150 15
Save-EthernetIndicator "ethernet_connected_icon" $true $PaleGreen
Save-EthernetIndicator "ethernet_disconnected_icon" $false $PaleGrey

Get-ChildItem $OutputDirectory -Filter "*.png" | Select-Object Name, Length
