#Requires -Version 5.1
<#
.SYNOPSIS
    Gera o .sha256 ao lado de um instalador do Fire Utils.

.DESCRIPTION
    A atualizacao pela dockpane exige <instalador>.exe.sha256 no bucket
    plugin-releases, junto do .exe. O build.ps1 ja gera um na hora do build;
    use este script de novo DEPOIS de assinar o .exe (assinar muda o arquivo, e
    um hash antigo faria a conferencia falhar).

    Sem parametro, usa o instalador mais recente de installer\output.

.EXAMPLE
    .\gerar-hash.ps1
    .\gerar-hash.ps1 -Instalador .\output\FireUtils-Setup-3.1.2.exe
#>
param(
    [string]$Instalador
)

$ErrorActionPreference = 'Stop'

if (-not $Instalador) {
    $saida = Join-Path $PSScriptRoot 'output'
    $ultimo = Get-ChildItem -LiteralPath $saida -Filter 'FireUtils-Setup-*.exe' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $ultimo) { throw "Nenhum instalador em $saida. Rode .\build.ps1 primeiro." }
    $Instalador = $ultimo.FullName
}

if (-not (Test-Path -LiteralPath $Instalador)) { throw "Arquivo nao encontrado: $Instalador" }

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Instalador).Hash.ToLower()
$destino = "$Instalador.sha256"
[System.IO.File]::WriteAllText($destino, $hash)

Write-Host "Hash gerado: $destino" -ForegroundColor Green
Write-Host "Suba o .sha256 e o .exe no bucket plugin-releases (o .sha256 primeiro)."
