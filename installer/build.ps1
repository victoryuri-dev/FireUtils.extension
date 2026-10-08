#Requires -Version 5.1
<#
.SYNOPSIS
    Monta o payload da extensao e compila o instalador do Fire Utils.

.DESCRIPTION
    Rode no Windows, com o Inno Setup 6 instalado. O script:

      1. Valida a URL da interface em fireutils.config.json;
      2. Copia para installer\payload apenas o que o cliente precisa;
      3. Chama o ISCC.exe, gerando installer\output\FireUtils-Setup-<versao>.exe

    A pasta payload\ e recriada do zero a cada execucao -- nunca edite nada
    dentro dela, as mudancas sao perdidas.

    O frontend nao entra no instalador: a dockpane carrega a interface do
    servidor configurado. Publicar interface nova e deploy, nao instalador.

.PARAMETER Version
    Versao do instalador (ex: 1.0.0). Padrao: conteudo de installer\VERSION.

.EXAMPLE
    .\build.ps1 -Version 1.0.0
#>
[CmdletBinding()]
param(
    [string] $Version
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
# webapp\dist não entra: a dockpane carrega a interface do servidor, e sem
# build local embutido o cliente também não fica com uma cópia offline dela.
$ItensDoPayload = @(
    @{ Origem = 'Fire Utils.tab';         Tipo = 'Pasta'   },
    @{ Origem = 'startup.py';             Tipo = 'Arquivo' },
    @{ Origem = 'fireutils.config.json';  Tipo = 'Arquivo' }
)

# A family_library tem ~53 MB, mas o acervo vive no Supabase: a dockpane
# baixa sob demanda, e garantir_familia_no_projeto() apenas verifica se a
# família já está no documento -- não carrega do disco. A pasta continua no
# repositório porque alimenta migration/generate_catalog.py, mas no
# instalador só precisam ir as famílias que o Python abre com LoadFamily.
#
# Caminhos relativos a "Fire Utils.tab\lib\family_library".
$FamiliasNecessarias = @(
    'Hidrantes\Valvula para Hidrante.rfa'   # hydrant_family.garantir_valvula
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

function Test-ConfigDaDockpane {
    <#
        A dockpane carrega a interface da URL em fireutils.config.json. Sem
        ela, o plugin instala e o painel abre num erro -- nao ha mais build
        local embutido para servir de alternativa. Melhor falhar aqui do que
        descobrir na maquina do cliente.
    #>
    $config = Join-Path $RepoRoot 'fireutils.config.json'

    if (-not (Test-Path -LiteralPath $config)) {
        throw "fireutils.config.json nao existe na raiz do repositorio."
    }

    try {
        $dados = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "fireutils.config.json nao e um JSON valido: $($_.Exception.Message)"
    }

    $url = $dados.webappUrl

    if (-not $url) {
        throw "fireutils.config.json nao tem a chave 'webappUrl'."
    }

    if ($url -match '^https?://(localhost|127\.0\.0\.1)') {
        throw ("webappUrl aponta para localhost ($url). Isso e a configuracao " +
               "de desenvolvimento -- devolva a URL de producao antes de gerar " +
               "o instalador.")
    }

    if ($url -notmatch '^https://') {
        throw "webappUrl precisa comecar com https:// (valor: $url)."
    }

    Write-Host "    Interface: $url"
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

Write-Passo 'Validando a configuracao da dockpane'
Test-ConfigDaDockpane

Write-Passo 'Conferindo a raiz do repositorio'
Test-ItensNovosNaRaiz
Write-Host '    OK'

Write-Passo 'Preparando icone e imagens do assistente'
# Sem checar $LASTEXITCODE: ele so e definido por programa externo, e um
# script PowerShell que termina normalmente o deixa indefinido -- o que sob
# Set-StrictMode vira erro ao ler. O script auxiliar tambem roda com
# $ErrorActionPreference = 'Stop', entao qualquer falha la ja chega aqui
# como excecao e aborta o build.
& (Join-Path $PSScriptRoot 'scripts\gerar-imagens.ps1')

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

# Poda a biblioteca de familias: entra apenas o que o Python abre do disco.
$libPayload = Join-Path $PayloadDir 'Fire Utils.tab\lib\family_library'

if (Test-Path -LiteralPath $libPayload) {
    $guardadas = @()

    foreach ($relativo in $FamiliasNecessarias) {
        $origem = Join-Path $RepoRoot (Join-Path 'Fire Utils.tab\lib\family_library' $relativo)

        if (-not (Test-Path -LiteralPath $origem)) {
            throw ("Familia necessaria nao encontrada: $relativo`n" +
                   "Se ela foi renomeada ou removida, atualize `$FamiliasNecessarias " +
                   "-- e confira o codigo que a carrega, que vai quebrar junto.")
        }

        $destinoTemp = Join-Path $env:TEMP ('fireutils-fam-{0}' -f ([guid]::NewGuid().ToString('N')))
        New-Item -ItemType Directory -Path $destinoTemp -Force | Out-Null
        Copy-Item -LiteralPath $origem -Destination $destinoTemp -Force

        $guardadas += @{
            Relativo = $relativo
            Temp     = (Join-Path $destinoTemp (Split-Path -Leaf $relativo))
        }
    }

    Remove-Item -LiteralPath $libPayload -Recurse -Force

    foreach ($familia in $guardadas) {
        $destino = Join-Path $libPayload $familia.Relativo
        $pasta   = Split-Path -Parent $destino

        if (-not (Test-Path -LiteralPath $pasta)) {
            New-Item -ItemType Directory -Path $pasta -Force | Out-Null
        }

        Move-Item -LiteralPath $familia.Temp -Destination $destino -Force
        Remove-Item -LiteralPath (Split-Path -Parent $familia.Temp) -Recurse -Force -ErrorAction SilentlyContinue

        Write-Host "    familia mantida: $($familia.Relativo)"
    }
}

# Caches do Python nunca devem ir junto: sao especificos da maquina e da
# versao do interpretador que os gerou.
Get-ChildItem -LiteralPath $PayloadDir -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $PayloadDir -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Soma acumulada em vez de Measure-Object -Sum: sob Set-StrictMode, ler a
# propriedade Sum do resultado quebra quando o pipeline nao produz o objeto
# esperado.
$totalBytes = 0
foreach ($arquivo in @(Get-ChildItem -LiteralPath $PayloadDir -Recurse -File)) {
    $totalBytes += $arquivo.Length
}
$tamanhoMb = [math]::Round($totalBytes / 1MB, 1)
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
