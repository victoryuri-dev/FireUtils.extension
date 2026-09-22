#Requires -Version 5.1
<#
.SYNOPSIS
    Monta o payload da extensao e compila o instalador do Fire Utils.

.DESCRIPTION
    Rode no Windows, com o Inno Setup 6 instalado. O script:

      1. Valida que webapp\dist esta presente e atualizado;
      2. Copia para installer\payload apenas o que o cliente precisa;
      3. Chama o ISCC.exe, gerando installer\output\FireUtils-Setup-<versao>.exe

    A pasta payload\ e recriada do zero a cada execucao -- nunca edite nada
    dentro dela, as mudancas sao perdidas.

.PARAMETER Version
    Versao do instalador (ex: 1.0.0). Padrao: conteudo de installer\VERSION.

.PARAMETER SkipFrontendCheck
    Ignora o aviso de webapp\dist desatualizado. Use apenas quando souber
    que o build do frontend esta correto.

.EXAMPLE
    .\build.ps1 -Version 1.0.0
#>
[CmdletBinding()]
param(
    [string] $Version,
    [switch] $SkipFrontendCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$InstallerDir = $PSScriptRoot
$RepoRoot     = Split-Path -Parent $InstallerDir
$PayloadDir   = Join-Path $InstallerDir 'payload'
$OutputDir    = Join-Path $InstallerDir 'output'
$IssFile      = Join-Path $InstallerDir 'FireUtils.iss'

# Somente estes itens vao para a maquina do cliente. E uma lista de
# inclusao, nao de exclusao: algo novo na raiz do repositorio fica de fora
# ate ser adicionado aqui de proposito -- e o script avisa quando isso
# acontece, para a omissao nunca passar despercebida.
$ItensDoPayload = @(
    @{ Origem = 'Fire Utils.tab'; Tipo = 'Pasta'   },
    @{ Origem = 'webapp\dist';    Tipo = 'Pasta'   },
    @{ Origem = 'startup.py';     Tipo = 'Arquivo' }
)

# Itens da raiz que sao intencionalmente de desenvolvimento e nao devem
# disparar o aviso de "item novo nao contemplado".
$IgnoradosNaRaiz = @(
    '.git', '.github', '.gitignore', '.claude',
    'installer', 'migration', 'webapp',
    'package-lock.json', 'README.md', 'LICENSE'
)

function Write-Passo {
    param([string] $Texto)
    Write-Host ''
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Write-Aviso {
    param([string] $Texto)
    Write-Host "    AVISO: $Texto" -ForegroundColor Yellow
}

function Resolve-Versao {
    if ($Version) { return $Version }

    $arquivoVersao = Join-Path $InstallerDir 'VERSION'
    if (Test-Path -LiteralPath $arquivoVersao) {
        $lida = (Get-Content -LiteralPath $arquivoVersao -Raw).Trim()
        if ($lida) { return $lida }
    }

    throw "Informe a versao com -Version 1.0.0 ou crie o arquivo installer\VERSION."
}

function Find-Iscc {
    $candidatos = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )

    foreach ($caminho in $candidatos) {
        if ($caminho -and (Test-Path -LiteralPath $caminho)) { return $caminho }
    }

    $noPath = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($noPath) { return $noPath.Source }

    throw ("Inno Setup 6 nao encontrado. Instale de https://jrsoftware.org/isdl.php " +
           "ou adicione o ISCC.exe ao PATH.")
}

function Test-FrontendAtualizado {
    <#
        webapp\dist e versionado de proposito, para o cliente nao precisar
        de Node. O risco disso e empacotar um dist antigo depois de mexer
        em webapp\src -- o plugin instala e roda a interface velha, sem
        nenhum erro visivel. Comparar as datas pega exatamente esse caso.
    #>
    $srcDir  = Join-Path $RepoRoot 'webapp\src'
    $distDir = Join-Path $RepoRoot 'webapp\dist'

    if (-not (Test-Path -LiteralPath $srcDir)) { return }

    $srcMaisNovo = Get-ChildItem -LiteralPath $srcDir -Recurse -File -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $distMaisNovo = Get-ChildItem -LiteralPath $distDir -Recurse -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if (-not $srcMaisNovo -or -not $distMaisNovo) { return }

    if ($srcMaisNovo.LastWriteTime -gt $distMaisNovo.LastWriteTime) {
        Write-Aviso "webapp\dist parece desatualizado em relacao a webapp\src."
        Write-Aviso "  src  modificado em: $($srcMaisNovo.LastWriteTime)"
        Write-Aviso "  dist gerado em:     $($distMaisNovo.LastWriteTime)"
        Write-Aviso "Rode 'npm run build' dentro de webapp\ antes de gerar o instalador,"
        Write-Aviso "senao o cliente recebe a interface antiga."

        $resposta = Read-Host "Continuar mesmo assim? (s/N)"
        if ($resposta -notmatch '^[sS]') {
            throw 'Build cancelado. Atualize webapp\dist e rode de novo.'
        }
    }
}

function Test-ItensNovosNaRaiz {
    $contemplados = $IgnoradosNaRaiz + ($ItensDoPayload | ForEach-Object { $_.Origem.Split('\')[0] })

    $novos = Get-ChildItem -LiteralPath $RepoRoot -Force |
             Where-Object { $contemplados -notcontains $_.Name }

    foreach ($item in $novos) {
        Write-Aviso ("'{0}' esta na raiz do repositorio mas nao vai para o instalador. " +
                     "Se deveria ir, adicione em `$ItensDoPayload." -f $item.Name)
    }
}

# ---------------------------------------------------------------------------

$versaoFinal = Resolve-Versao
Write-Host ''
Write-Host "Fire Utils - build do instalador $versaoFinal" -ForegroundColor Green

Write-Passo 'Validando o frontend'
if ($SkipFrontendCheck) {
    Write-Aviso 'Verificacao do frontend pulada (-SkipFrontendCheck).'
} else {
    Test-FrontendAtualizado
}

$distDir = Join-Path $RepoRoot 'webapp\dist'
if (-not (Test-Path -LiteralPath (Join-Path $distDir 'index.html'))) {
    throw ("webapp\dist\index.html nao existe. Rode 'npm install && npm run build' " +
           "dentro de webapp\ antes de gerar o instalador.")
}
Write-Host '    OK'

Write-Passo 'Conferindo a raiz do repositorio'
Test-ItensNovosNaRaiz
Write-Host '    OK'

Write-Passo 'Montando o payload'
if (Test-Path -LiteralPath $PayloadDir) {
    Remove-Item -LiteralPath $PayloadDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PayloadDir -Force | Out-Null

foreach ($item in $ItensDoPayload) {
    $origem = Join-Path $RepoRoot $item.Origem

    if (-not (Test-Path -LiteralPath $origem)) {
        throw "Item obrigatorio do payload nao encontrado: $($item.Origem)"
    }

    $destino = Join-Path $PayloadDir $item.Origem

    if ($item.Tipo -eq 'Pasta') {
        $paiDoDestino = Split-Path -Parent $destino
        if (-not (Test-Path -LiteralPath $paiDoDestino)) {
            New-Item -ItemType Directory -Path $paiDoDestino -Force | Out-Null
        }
        Copy-Item -LiteralPath $origem -Destination $destino -Recurse -Force
    } else {
        Copy-Item -LiteralPath $origem -Destination $destino -Force
    }

    Write-Host "    + $($item.Origem)"
}

# Caches do Python nunca devem ir junto: sao especificos da maquina e da
# versao do interpretador que os gerou.
Get-ChildItem -LiteralPath $PayloadDir -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $PayloadDir -Recurse -Force -File -Include '*.pyc', '*.pyo' -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$tamanhoMb = [math]::Round(
    ((Get-ChildItem -LiteralPath $PayloadDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB), 1
)
Write-Host "    Payload: $tamanhoMb MB"

Write-Passo 'Compilando o instalador'
$iscc = Find-Iscc
Write-Host "    ISCC: $iscc"

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

& $iscc "/DAppVersion=$versaoFinal" $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe falhou com codigo $LASTEXITCODE."
}

$instalador = Join-Path $OutputDir "FireUtils-Setup-$versaoFinal.exe"
$tamanhoInstalador = [math]::Round((Get-Item -LiteralPath $instalador).Length / 1MB, 1)

Write-Host ''
Write-Host "Instalador gerado: $instalador ($tamanhoInstalador MB)" -ForegroundColor Green
Write-Host ''
Write-Host 'Antes de enviar ao cliente, assine digitalmente o executavel --' -ForegroundColor Yellow
Write-Host 'sem assinatura o SmartScreen exibe um alerta de editor desconhecido.' -ForegroundColor Yellow
Write-Host ''
