#Requires -Version 5.1
<#
.SYNOPSIS
    Monta o pacote de atualizacao que a dockpane oferece aos clientes.

.DESCRIPTION
    Gera, em installer\output\publicacao:

      fireutils-<versao>.zip   o mesmo payload do instalador, sem as DLLs
                               do WebView2 (o atualizador nunca as troca --
                               o Revit as mantem abertas enquanto roda)
      versao.json              { versao, sha256, notas }

    Depois suba os dois pelo painel do Supabase, em
    Storage > plugin-assets > atualizacao, substituindo o versao.json que
    estiver lá. SEMPRE o zip primeiro: o versao.json e o que anuncia a
    versao nova, e anunciar antes de o pacote existir faz todo cliente
    aberto tentar baixar um arquivo que ainda nao esta lá.

    Nada aqui fala com o Supabase. Subir exigiria a service_role key em
    disco (a anon key nao escreve no bucket), e uma chave com poder de
    escrever em tudo nao vale a economia de dois arrastares de arquivo.

    O sha256 no versao.json e o que autentica o pacote: o cliente baixa de
    um bucket publico e so instala se o checksum bater (ver atualizacao.py).

.PARAMETER Notas
    Uma linha sobre o que mudou, exibida na faixa de atualizacao da
    dockpane. Opcional.

.EXAMPLE
    .\publicar.ps1 -Notas "Corrige o calculo de perda de carga em trechos verticais."
#>
[CmdletBinding()]
param(
    [string] $Notas
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$InstallerDir   = $PSScriptRoot
$PublicacaoDir  = Join-Path $InstallerDir 'output\publicacao'
$PayloadTemp    = Join-Path $InstallerDir 'output\payload-atualizacao'

Write-Host ''
Write-Host 'Fire Utils - pacote de atualizacao' -ForegroundColor Green

$payload = & (Join-Path $PSScriptRoot 'scripts\montar-payload.ps1') `
    -Destino $PayloadTemp -SemRuntimeWebView2
$versao = $payload.Versao

Write-Host ''
Write-Host '==> Compactando' -ForegroundColor Cyan

if (Test-Path -LiteralPath $PublicacaoDir) {
    Remove-Item -LiteralPath $PublicacaoDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PublicacaoDir -Force | Out-Null

$zip = Join-Path $PublicacaoDir "fireutils-$versao.zip"

# ZipFile.CreateFromDirectory do .NET em vez de Compress-Archive: o cmdlet
# do PowerShell 5.1 grava os nomes das entradas com "\" em vez de "/", o
# que nao e o formato do zip e nem todo descompactador aceita. Aqui o
# descompactador e o do lado Python (atualizacao.py), e nao vale depender de
# ele ser tolerante com isso.
#
# $false no fim: os itens entram na raiz do zip, nao dentro de uma pasta
# "payload-atualizacao" -- o atualizador espera versao.json e
# "Fire Utils.tab" no primeiro nivel.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $PayloadTemp,
    $zip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

$sha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
$tamanhoMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)

Write-Host "    $([System.IO.Path]::GetFileName($zip)) ($tamanhoMb MB)"
Write-Host "    sha256: $sha256"

$manifesto = [ordered]@{
    versao = $versao
    sha256 = $sha256
}
if ($Notas) {
    $manifesto['notas'] = $Notas
}

$arquivoManifesto = Join-Path $PublicacaoDir 'versao.json'
# Sem BOM: o Python le este arquivo como UTF-8 puro, e o BOM que o
# Set-Content do PowerShell 5.1 escreveria entraria no primeiro nome de
# chave, quebrando o json.loads do lado do cliente.
[System.IO.File]::WriteAllText(
    $arquivoManifesto,
    ([pscustomobject] $manifesto | ConvertTo-Json),
    (New-Object System.Text.UTF8Encoding $false)
)

Remove-Item -LiteralPath $PayloadTemp -Recurse -Force

Write-Host ''
Write-Host "Pronto: $PublicacaoDir" -ForegroundColor Green
Write-Host ''
Write-Host 'Suba no painel do Supabase (Storage > plugin-assets > atualizacao):' -ForegroundColor Yellow
Write-Host "  1. fireutils-$versao.zip" -ForegroundColor Yellow
Write-Host '  2. versao.json (sobrescrevendo o que estiver lá)' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Nessa ordem: o versao.json e o que anuncia a versao nova.' -ForegroundColor Yellow
Write-Host ''
