$ErrorActionPreference = "Stop"

$outputPath = Join-Path $PSScriptRoot "transformer_fft_hybrid_loss_model_editable.vsdx"
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
$visio.AlertResponse = 1
$visio.EventsEnabled = $false

try {
    $doc = $visio.Documents.Add("")
    $page = $doc.Pages.Item(1)

    $pageWidth = 2.34
    $pageHeight = 4.27
    $page.PageSheet.CellsU("PageWidth").FormulaU = "$pageWidth in"
    $page.PageSheet.CellsU("PageHeight").FormulaU = "$pageHeight in"
    $page.PageSheet.CellsU("PrintPageOrientation").FormulaU = "1"

    function X([double]$px) { return $px / 100.0 }
    function Y([double]$py) { return $pageHeight - ($py / 100.0) }

    function Visio-Color([string]$hex) {
        if ([string]::IsNullOrWhiteSpace($hex)) {
            $hex = "#111111"
        }
        $value = $hex.TrimStart("#")
        if ($value.Length -ne 6) {
            throw "Invalid color value passed to Visio-Color: '$hex'"
        }
        $r = [Convert]::ToInt32($value.Substring(0, 2), 16)
        $g = [Convert]::ToInt32($value.Substring(2, 2), 16)
        $b = [Convert]::ToInt32($value.Substring(4, 2), 16)
        return "RGB($r,$g,$b)"
    }

    function Set-LineStyle($shape, [string]$color = "#111111", [double]$weight = 0.012) {
        $colorFormula = Visio-Color -hex $color
        $shape.CellsU("LineColor").FormulaU = $colorFormula
        $shape.CellsU("LineWeight").FormulaU = "$weight in"
    }

    function Add-Box(
        [double]$x, [double]$y, [double]$w, [double]$h,
        [string]$text, [string]$fill,
        [double]$fontSize = 6.0, [double]$rounding = 0.0,
        [string]$lineColor = "#111111"
    ) {
        $shape = $page.DrawRectangle((X $x), (Y ($y + $h)), (X ($x + $w)), (Y $y))
        $shape.Text = $text
        $fillFormula = Visio-Color -hex $fill
        $shape.CellsU("FillForegnd").FormulaU = $fillFormula
        $shape.CellsU("FillPattern").FormulaU = "1"
        Set-LineStyle $shape $lineColor 0.012
        if ($rounding -gt 0) {
            $shape.CellsU("Rounding").FormulaU = "$(X $rounding) in"
        }
        $shape.CellsU("Char.Size").FormulaU = "$fontSize pt"
        $shape.CellsU("Para.HorzAlign").FormulaU = "1"
        $shape.CellsU("VerticalAlign").FormulaU = "1"
        $shape.CellsU("TextBkgnd").FormulaU = "255"
        $shape.CellsU("TextBkgndTrans").FormulaU = "100%"
        return $shape
    }

    function Add-Line(
        [double]$x1, [double]$y1, [double]$x2, [double]$y2,
        [bool]$arrow = $true
    ) {
        $line = $page.DrawLine((X $x1), (Y $y1), (X $x2), (Y $y2))
        Set-LineStyle $line "#111111" 0.012
        if ($arrow) {
            $line.CellsU("EndArrow").FormulaU = "4"
            $line.CellsU("EndArrowSize").FormulaU = "2"
        }
        return $line
    }

    function Add-Elbow(
        [double[]]$points,
        [bool]$arrow = $true
    ) {
        for ($i = 0; $i -lt $points.Length - 4; $i += 2) {
            Add-Line $points[$i] $points[$i + 1] $points[$i + 2] $points[$i + 3] $false | Out-Null
        }
        Add-Line $points[-4] $points[-3] $points[-2] $points[-1] $arrow | Out-Null
    }

    function Add-Label(
        [double]$x, [double]$y, [double]$w, [double]$h,
        [string]$text, [double]$fontSize = 7.0
    ) {
        $shape = Add-Box $x $y $w $h $text "#FFFFFF" $fontSize 0 "#FFFFFF"
        $shape.CellsU("FillPattern").FormulaU = "0"
        $shape.CellsU("LinePattern").FormulaU = "0"
        return $shape
    }

    # Page background
    $background = Add-Box 0 0 234 427 "" "#FFFFFF" 1
    $background.SendToBack()

    # Main sections, matching the first generated diagram.
    Add-Box 3 36 228 105 "" "#D9D9D9" 1 12 | Out-Null
    Add-Box 3 145 228 231 "" "#D9D9D9" 1 17 | Out-Null

    # Main vertical flow connectors.
    Add-Line 117 381 117 360 | Out-Null
    Add-Line 117 334 117 326 | Out-Null
    Add-Line 117 305 117 289 | Out-Null
    Add-Line 117 267 117 250 | Out-Null
    Add-Line 117 229 117 215 | Out-Null
    Add-Line 117 193 117 179 | Out-Null
    Add-Line 117 158 117 141 | Out-Null
    Add-Line 118 108 118 106 | Out-Null
    Add-Line 117 83 117 69 | Out-Null
    Add-Line 117 47 117 30 | Out-Null

    # Original side and bypass routes, intentionally left easy to select and edit.
    Add-Elbow @(103,346, 35,346, 35,278, 69,278) | Out-Null
    Add-Elbow @(103,278, 35,278, 35,204, 68,204) | Out-Null
    Add-Elbow @(96,390, 25,390, 25,118, 13,118) | Out-Null
    Add-Elbow @(46,108, 46,96, 68,96) | Out-Null
    Add-Elbow @(189,108, 189,96, 167,96) | Out-Null
    Add-Line 76 346 103 346 | Out-Null

    # Fusion blocks.
    Add-Box 77 47 80 22 "三层 MLP 回归" "#CCE0ED" 7 | Out-Null
    $fusionBox = Add-Box 68 83 99 23 "多特征拼接融合" "#CCE0ED" 7
    $fusionBox.CellsU("FillForegnd").FormulaU = "RGB(204,224,237)"
    $fftBox = Add-Box 13 108 66 21 "FFT 前16阶" "#EAF3DC" 6.5
    $fftBox.CellsU("FillForegnd").FormulaU = "RGB(234,243,220)"
    Add-Box 84 108 69 21 "Transformer特征" "#F7EAC8" 6.2 | Out-Null
    Add-Box 159 108 60 21 "T, f, Hdc, Bm" "#EAF3DC" 6.2 | Out-Null
    Add-Label 169 127 48 12 "Fusion" 7 | Out-Null

    # Encoder blocks.
    Add-Box 77 158 80 21 "平均池化" "#F7EAC8" 7 | Out-Null
    Add-Box 68 193 99 22 "前馈神经网络" "#CCE0ED" 7 | Out-Null
    $normBox1 = Add-Box 77 229 80 21 "层归一化" "#F7EAC8" 7
    $normBox1.CellsU("FillForegnd").FormulaU = "RGB(247,234,200)"
    Add-Box 69 267 97 22 "多头自注意力" "#DCEBD2" 7 | Out-Null
    $normBox2 = Add-Box 77 305 80 21 "层归一化" "#F7EAC8" 7
    $normBox2.CellsU("FillForegnd").FormulaU = "RGB(247,234,200)"
    Add-Box 12 334 64 24 "波形类型选择" "#BFD0E8" 6.2 7 | Out-Null
    Add-Label 166 342 52 16 "Encoder" 7 | Out-Null
    Add-Label 19 224 20 45 "FFT分支" 6.5 | Out-Null

    # Editable addition node.
    $circle = $page.DrawOval((X 103), (Y 360), (X 131), (Y 332))
    $circle.Text = "+"
    $whiteFormula = Visio-Color -hex "#FFFFFF"
    $circle.CellsU("FillForegnd").FormulaU = $whiteFormula
    $circle.CellsU("FillPattern").FormulaU = "1"
    Set-LineStyle $circle "#111111" 0.02
    $circle.CellsU("Char.Size").FormulaU = "18 pt"
    $circle.CellsU("Char.Style").FormulaU = "1"
    $circle.CellsU("Para.HorzAlign").FormulaU = "1"
    $circle.CellsU("VerticalAlign").FormulaU = "1"

    # Input and output nodes.
    Add-Box 75 2 84 27 "损耗密度 Pcv" "#F4F2CF" 7 | Out-Null
    Add-Box 72 381 90 42 "B(t) 波形" "#EEF4D9" 8 | Out-Null

    # Small editable waveform line inside the input box.
    Add-Line 95 411 102 397 $false | Out-Null
    Add-Line 102 397 109 394 $false | Out-Null
    Add-Line 109 394 116 411 $false | Out-Null
    Add-Line 116 411 124 424 $false | Out-Null
    Add-Line 124 424 132 424 $false | Out-Null
    Add-Line 132 424 139 411 $false | Out-Null

    # visSaveAsListInMRU only; do not set the read-only flag.
    $doc.SaveAsEx($outputPath, 4)
    $doc.Close()
}
finally {
    $visio.Quit()
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($visio) | Out-Null
}

Write-Output $outputPath
