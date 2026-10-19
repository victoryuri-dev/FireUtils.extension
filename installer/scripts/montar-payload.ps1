#Requires -Version 5.1
<#
.SYNOPSIS
    Monta em -Destino exatamente o que vai para a maquina do cliente.

.DESCRIPTION
    Usado por build.ps1 (que compila o .exe em cima disso) e por
    publicar.ps1 (que compacta o mesmo conteudo para a atualizacao pela
    dockpane). Os dois precisam do payload identico: o atualizador substitui
    arquivo por arquivo o que o instalador deixou no disco -- se as duas
    listas divergissem, atualizar deixaria a instalacao diferente de uma
    instalacao nova, e o bug apareceria so em quem atualizou.

    A pasta de destino e recriada do zero -- nunca edite nada dentro dela,
    as mudancas sao perdidas.

.PARAMETER Destino
    Pasta onde o payload e montado (recriada).

.PARAMETER SemRuntimeWebView2
    Deixa de fora as DLLs do WebView2. O atualizador nunca as substitui (o
    Revit as mantem abertas enquanto roda, ver _PRESERVADOS em
    atualizacao.py), entao no pacote de atualizacao elas seriam 5 MB de
    download jogados fora. O instalador precisa delas.

.OUTPUTS
    [pscustomobject] com Versao e TamanhoMb.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Destino,

    [switch] $SemRuntimeWebView2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Somente estes itens vao para a maquina do cliente. E uma lista de
# inclusao, nao de exclusao: algo novo na raiz do repositorio fica de fora
# ate ser adicionado aqui de proposito -- e o script avisa quando isso
# acontece, para a omissao nunca passar despercebida.
# webapp\dist não entra: a dockpane carrega a interface do servidor, e sem
# build local embutido o cliente também não fica com uma cópia offline dela.
$ItensDoPayload = @(
    @{ Origem = 'Fire Utils.tab';         Tipo = 'Pasta'   },
    @{ Origem = 'startup.py';             Tipo = 'Arquivo' },
    @{ Origem = 'fireutils.config.json';  Tipo = 'Arquivo' },
    @{ Origem = 'versao.json';            Tipo = 'Arquivo' }
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
    'package-lock.json', 'README.md', 'LICENSE',
    '__pycache__'
)

$RuntimeWebView2 = 'Fire Utils.tab\lib\webview2_runtime'

function Write-Aviso {
    param([string] $Texto)
    Write-Host "    AVISO: $Texto" -ForegroundColor Yellow
}

function Get-VersaoDoPlugin {
    <#
        versao.json e a unica fonte da versao: e o arquivo que viaja junto
        com o codigo, e o que o atualizador le para saber o que esta
        instalado. Qualquer outro lugar guardando o numero poderia ficar
        atrasado sem ninguem notar.
    #>
    $arquivo = Join-Path $RepoRoot 'versao.json'

    if (-not (Test-Path -LiteralPath $arquivo)) {
        throw "versao.json nao existe na raiz do repositorio."
    }

    try {
        $dados = Get-Content -LiteralPath $arquivo -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "versao.json nao e um JSON valido: $($_.Exception.Message)"
    }

    if (-not $dados.versao) {
        throw "versao.json nao tem a chave 'versao'."
    }

    return [string] $dados.versao
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

Write-Host ''
Write-Host '==> Validando a configuracao da dockpane' -ForegroundColor Cyan
Test-ConfigDaDockpane
$versao = Get-VersaoDoPlugin
Write-Host "    Versao: $versao"

Write-Host ''
Write-Host '==> Conferindo a raiz do repositorio' -ForegroundColor Cyan
Test-ItensNovosNaRaiz
Write-Host '    OK'

Write-Host ''
Write-Host '==> Montando o payload' -ForegroundColor Cyan
if (Test-Path -LiteralPath $Destino) {
    Remove-Item -LiteralPath $Destino -Recurse -Force
}
New-Item -ItemType Directory -Path $Destino -Force | Out-Null

foreach ($item in $ItensDoPayload) {
    $origem = Join-Path $RepoRoot $item.Origem

    if (-not (Test-Path -LiteralPath $origem)) {
        throw "Item obrigatorio do payload nao encontrado: $($item.Origem)"
    }

    $destinoItem = Join-Path $Destino $item.Origem

    if ($item.Tipo -eq 'Pasta') {
        $paiDoDestino = Split-Path -Parent $destinoItem
        if (-not (Test-Path -LiteralPath $paiDoDestino)) {
            New-Item -ItemType Directory -Path $paiDoDestino -Force | Out-Null
        }
        Copy-Item -LiteralPath $origem -Destination $destinoItem -Recurse -Force
    } else {
        Copy-Item -LiteralPath $origem -Destination $destinoItem -Force
    }

    Write-Host "    + $($item.Origem)"
}

# Poda a biblioteca de familias: entra apenas o que o Python abre do disco.
$libPayload = Join-Path $Destino 'Fire Utils.tab\lib\family_library'

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
        $destinoFamilia = Join-Path $libPayload $familia.Relativo
        $pasta          = Split-Path -Parent $destinoFamilia

        if (-not (Test-Path -LiteralPath $pasta)) {
            New-Item -ItemType Directory -Path $pasta -Force | Out-Null
        }

        Move-Item -LiteralPath $familia.Temp -Destination $destinoFamilia -Force
        Remove-Item -LiteralPath (Split-Path -Parent $familia.Temp) -Recurse -Force -ErrorAction SilentlyContinue

        Write-Host "    familia mantida: $($familia.Relativo)"
    }
}

if ($SemRuntimeWebView2) {
    $runtime = Join-Path $Destino $RuntimeWebView2
    if (Test-Path -LiteralPath $runtime) {
        Remove-Item -LiteralPath $runtime -Recurse -Force
        Write-Host "    - $RuntimeWebView2 (fica com o instalador)"
    }
}

# Caches do Python nunca devem ir junto: sao especificos da maquina e da
# versao do interpretador que os gerou.
Get-ChildItem -LiteralPath $Destino -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $Destino -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Soma acumulada em vez de Measure-Object -Sum: sob Set-StrictMode, ler a
# propriedade Sum do resultado quebra quando o pipeline nao produz o objeto
# esperado.
$totalBytes = 0
foreach ($arquivo in @(Get-ChildItem -LiteralPath $Destino -Recurse -File)) {
    $totalBytes += $arquivo.Length
}
$tamanhoMb = [math]::Round($totalBytes / 1MB, 1)
Write-Host "    Payload: $tamanhoMb MB"

[pscustomobject]@{
    Versao    = $versao
    TamanhoMb = $tamanhoMb
}
