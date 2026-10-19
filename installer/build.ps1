#Requires -Version 5.1
<#
.SYNOPSIS
    Monta o payload da extensao e compila o instalador do Fire Utils.

.DESCRIPTION
    Rode no Windows, com o Inno Setup 6 instalado. O script:

      1. Monta installer\payload (ver scripts\montar-payload.ps1, que valida
         a URL da interface e a versao);
      2. Chama o ISCC.exe, gerando installer\output\FireUtils-Setup-<versao>.exe

    A versao vem de versao.json, na raiz do repositorio -- o mesmo arquivo
    que viaja no payload e que o atualizador da dockpane le para saber o que
    esta instalado.

    O frontend nao entra no instalador: a dockpane carrega a interface do
    servidor configurado. Publicar interface nova e deploy, nao instalador.

.PARAMETER Version
    Confere a versao antes de compilar. Opcional -- se informada, tem que
    bater com versao.json; serve para nao gerar o instalador errado quando
    se esquece de atualizar o arquivo.

.EXAMPLE
    .\build.ps1
#>
[CmdletBinding()]
param(
    [string] $Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$InstallerDir = $PSScriptRoot
$PayloadDir   = Join-Path $InstallerDir 'payload'
$OutputDir    = Join-Path $InstallerDir 'output'
$IssFile      = Join-Path $InstallerDir 'FireUtils.iss'

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

# ---------------------------------------------------------------------------

Write-Host ''
Write-Host 'Fire Utils - build do instalador' -ForegroundColor Green

Write-Host ''
Write-Host '==> Preparando icone e imagens do assistente' -ForegroundColor Cyan
# Sem checar $LASTEXITCODE: ele so e definido por programa externo, e um
# script PowerShell que termina normalmente o deixa indefinido -- o que sob
# Set-StrictMode vira erro ao ler. Os scripts auxiliares tambem rodam com
# $ErrorActionPreference = 'Stop', entao qualquer falha la ja chega aqui
# como excecao e aborta o build.
& (Join-Path $PSScriptRoot 'scripts\gerar-imagens.ps1')

$payload = & (Join-Path $PSScriptRoot 'scripts\montar-payload.ps1') -Destino $PayloadDir
$versaoFinal = $payload.Versao

if ($Version -and $Version -ne $versaoFinal) {
    throw ("Voce pediu a versao $Version, mas versao.json diz $versaoFinal. " +
           "Atualize versao.json (e um commit so dele) antes de compilar.")
}

Write-Host ''
Write-Host '==> Compilando o instalador' -ForegroundColor Cyan
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
