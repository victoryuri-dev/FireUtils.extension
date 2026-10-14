#Requires -Version 5.1
<#
.SYNOPSIS
    Gera o icone e as imagens do assistente do instalador a partir da logo
    do Fire Utils.

.DESCRIPTION
    O Inno Setup nao aceita PNG: quer .ico para o icone e .bmp para as
    imagens do assistente. Este script faz a conversao usando System.Drawing,
    que ja vem com o .NET no Windows -- nao e preciso instalar nada.

    Chamado automaticamente pelo build.ps1 quando os arquivos ainda nao
    existem. Rode manualmente para regerar depois de trocar a logo.

    Saida em installer\assets\:
      fireutils.ico       icone do executavel (16 a 256 px)
      wizard-large.bmp    lateral das telas de boas-vindas e conclusao
      wizard-small.bmp    canto superior direito das demais telas

.PARAMETER Forcar
    Regera os arquivos mesmo que ja existam.
#>
[CmdletBinding()]
param(
    [switch] $Forcar
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$InstallerDir = Split-Path -Parent $PSScriptRoot
$RepoRoot     = Split-Path -Parent $InstallerDir
$AssetsDir    = Join-Path $InstallerDir 'assets'
$LogoPath     = Join-Path $RepoRoot 'Fire Utils.tab\lib\assets\fireutils-logo-h.png'

# A logo tem o texto em branco, entao sobre o fundo claro padrao do
# assistente ele sumiria. Um fundo escuro resolve e ainda destaca o vermelho
# da marca.
$CorFundo = [System.Drawing.Color]::FromArgb(23, 23, 26)

$IcoPath         = Join-Path $AssetsDir 'fireutils.ico'
$WizardLargePath = Join-Path $AssetsDir 'wizard-large.bmp'
$WizardSmallPath = Join-Path $AssetsDir 'wizard-small.bmp'

function Get-RetanguloDoSimbolo {
    <#
        A logo horizontal e o simbolo vermelho seguido do nome em branco.
        Para o icone quadrado interessa so o simbolo, entao localizamos os
        pixels vermelhos e devolvemos o retangulo que os contem.

        Detectar por cor em vez de recortar uma regiao fixa mantem o script
        correto se a logo for redesenhada com outras proporcoes.
    #>
    param([Parameter(Mandatory)] [System.Drawing.Bitmap] $Imagem)

    # GetPixel em PowerShell custa caro: uma logo de 822x216 sao quase 180 mil
    # leituras. Sem este aviso, a pausa parece travamento.
    Write-Host ("    Varrendo {0} pixels para localizar o simbolo (alguns segundos)..." -f
                ($Imagem.Width * $Imagem.Height))

    $xMin = $Imagem.Width;  $xMax = -1
    $yMin = $Imagem.Height; $yMax = -1

    for ($y = 0; $y -lt $Imagem.Height; $y++) {
        for ($x = 0; $x -lt $Imagem.Width; $x++) {
            $p = $Imagem.GetPixel($x, $y)

            # Vermelho da marca: opaco, canal R dominante sobre G e B.
            if ($p.A -gt 128 -and $p.R -gt 120 -and $p.R -gt ($p.G * 2) -and $p.R -gt ($p.B * 2)) {
                if ($x -lt $xMin) { $xMin = $x }
                if ($x -gt $xMax) { $xMax = $x }
                if ($y -lt $yMin) { $yMin = $y }
                if ($y -gt $yMax) { $yMax = $y }
            }
        }
    }

    if ($xMax -lt 0) {
        throw "Nenhum pixel vermelho encontrado em $LogoPath -- a logo mudou de cor?"
    }

    return New-Object System.Drawing.Rectangle(
        $xMin, $yMin, ($xMax - $xMin + 1), ($yMax - $yMin + 1)
    )
}

function New-BitmapQuadrado {
    <#
        Encaixa a imagem num quadrado transparente, centralizada e sem
        distorcer as proporcoes -- icone esticado denuncia amadorismo.
    #>
    param(
        [Parameter(Mandatory)] [System.Drawing.Bitmap] $Origem,
        [Parameter(Mandatory)] [int] $Lado,
        [int] $MargemPercentual = 8
    )

    $destino = New-Object System.Drawing.Bitmap($Lado, $Lado)
    $g = [System.Drawing.Graphics]::FromImage($destino)
    try {
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

        $margem = [int]($Lado * $MargemPercentual / 100)
        $util   = $Lado - (2 * $margem)

        $escala  = [Math]::Min($util / $Origem.Width, $util / $Origem.Height)
        $largura = [int]($Origem.Width * $escala)
        $altura  = [int]($Origem.Height * $escala)

        $g.DrawImage(
            $Origem,
            [int](($Lado - $largura) / 2),
            [int](($Lado - $altura) / 2),
            $largura,
            $altura
        )
    } finally {
        $g.Dispose()
    }

    return $destino
}

function Save-Ico {
    <#
        System.Drawing nao salva .ico com varias resolucoes. O formato, no
        entanto, aceita PNG embutido desde o Windows Vista, entao montamos
        o arquivo na mao: cabecalho, uma entrada por tamanho, e os PNGs.

        Varias resolucoes importam porque o Windows escolhe conforme o
        contexto -- 16 px na barra de titulo, 256 px em icones grandes do
        Explorer. Com um tamanho so, o resto sai borrado.
    #>
    param(
        [Parameter(Mandatory)] [System.Drawing.Bitmap[]] $Imagens,
        [Parameter(Mandatory)] [string] $Caminho
    )

    $blocosPng = @()
    foreach ($img in $Imagens) {
        $ms = New-Object System.IO.MemoryStream
        try {
            $img.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
            $blocosPng += , $ms.ToArray()
        } finally {
            $ms.Dispose()
        }
    }

    $fs = [System.IO.File]::Create($Caminho)
    $bw = New-Object System.IO.BinaryWriter($fs)
    try {
        # ICONDIR
        $bw.Write([uint16]0)                  # reservado
        $bw.Write([uint16]1)                  # tipo: 1 = icone
        $bw.Write([uint16]$Imagens.Count)

        # Uma ICONDIRENTRY por imagem (16 bytes cada), antes dos dados.
        $deslocamento = 6 + (16 * $Imagens.Count)

        for ($i = 0; $i -lt $Imagens.Count; $i++) {
            $img = $Imagens[$i]

            # 256 px e gravado como 0: o campo tem um byte so.
            $largura = if ($img.Width  -ge 256) { 0 } else { $img.Width }
            $altura  = if ($img.Height -ge 256) { 0 } else { $img.Height }

            $bw.Write([byte]$largura)
            $bw.Write([byte]$altura)
            $bw.Write([byte]0)                # cores da paleta (0 = sem paleta)
            $bw.Write([byte]0)                # reservado
            $bw.Write([uint16]1)              # planos de cor
            $bw.Write([uint16]32)             # bits por pixel
            $bw.Write([uint32]$blocosPng[$i].Length)
            $bw.Write([uint32]$deslocamento)

            $deslocamento += $blocosPng[$i].Length
        }

        foreach ($bloco in $blocosPng) {
            $bw.Write($bloco)
        }
    } finally {
        $bw.Dispose()
        $fs.Dispose()
    }
}

function Save-BmpDoAssistente {
    <#
        As imagens do assistente nao podem ter transparencia: o Inno Setup
        as desenha como fundo solido. Por isso pintamos o fundo escuro antes
        de compor a logo.
    #>
    param(
        [Parameter(Mandatory)] [System.Drawing.Bitmap] $Logo,
        [Parameter(Mandatory)] [int] $Largura,
        [Parameter(Mandatory)] [int] $Altura,
        [Parameter(Mandatory)] [string] $Caminho,
        [int] $MargemPercentual = 12
    )

    $destino = New-Object System.Drawing.Bitmap($Largura, $Altura)
    $g = [System.Drawing.Graphics]::FromImage($destino)
    try {
        $g.Clear($CorFundo)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

        $margem      = [int]([Math]::Min($Largura, $Altura) * $MargemPercentual / 100)
        $utilLargura = $Largura - (2 * $margem)
        $utilAltura  = $Altura  - (2 * $margem)

        $escala  = [Math]::Min($utilLargura / $Logo.Width, $utilAltura / $Logo.Height)
        $largura = [int]($Logo.Width * $escala)
        $altura  = [int]($Logo.Height * $escala)

        $g.DrawImage(
            $Logo,
            [int](($Largura - $largura) / 2),
            [int](($Altura - $altura) / 2),
            $largura,
            $altura
        )
    } finally {
        $g.Dispose()
    }

    $destino.Save($Caminho, [System.Drawing.Imaging.ImageFormat]::Bmp)
    $destino.Dispose()
}

# ---------------------------------------------------------------------------

$jaExistem = (Test-Path -LiteralPath $IcoPath) -and
             (Test-Path -LiteralPath $WizardLargePath) -and
             (Test-Path -LiteralPath $WizardSmallPath)

if ($jaExistem -and -not $Forcar) {
    Write-Host '    Imagens do instalador ja existem (use -Forcar para regerar).'
    exit 0
}

if (-not (Test-Path -LiteralPath $LogoPath)) {
    throw "Logo nao encontrada: $LogoPath"
}

if (-not (Test-Path -LiteralPath $AssetsDir)) {
    New-Item -ItemType Directory -Path $AssetsDir -Force | Out-Null
}

$logo = New-Object System.Drawing.Bitmap($LogoPath)
try {
    Write-Host ("    Logo: {0}x{1}" -f $logo.Width, $logo.Height)

    $retangulo = Get-RetanguloDoSimbolo -Imagem $logo
    Write-Host ("    Simbolo detectado em: {0}" -f $retangulo)

    $simbolo = $logo.Clone($retangulo, $logo.PixelFormat)
    try {
        $tamanhos = @(16, 24, 32, 48, 64, 128, 256)
        $imagensIco = @()
        foreach ($tamanho in $tamanhos) {
            $imagensIco += New-BitmapQuadrado -Origem $simbolo -Lado $tamanho
        }

        try {
            Save-Ico -Imagens $imagensIco -Caminho $IcoPath
            Write-Host ("    + fireutils.ico ({0} resolucoes)" -f $tamanhos.Count)
        } finally {
            foreach ($img in $imagensIco) { $img.Dispose() }
        }

        # 164x314 e 55x58 sao as dimensoes que o Inno Setup espera em 100% de
        # DPI; ele mesmo reescala em telas com DPI maior.
        Save-BmpDoAssistente -Logo $logo -Largura 164 -Altura 314 -Caminho $WizardLargePath
        Write-Host '    + wizard-large.bmp (164x314)'

        Save-BmpDoAssistente -Logo $simbolo -Largura 55 -Altura 58 -Caminho $WizardSmallPath -MargemPercentual 10
        Write-Host '    + wizard-small.bmp (55x58)'
    } finally {
        $simbolo.Dispose()
    }
} finally {
    $logo.Dispose()
}
