#Requires -Version 5.1
<#
.SYNOPSIS
    Gera e assina um pacote de atualizacao rapida (so codigo Python) do plugin.

.DESCRIPTION
    Monta installer\output\FireUtils-Pacote-<Versao>-base-<BaseMinima>.zip a
    partir de "Fire Utils.tab" do repositorio e o assina com a sua chave
    privada (ver scripts\gerar-chave-pacote.ps1), gerando o .zip.sig ao lado.
    Suba os DOIS no bucket plugin-releases (o .sig primeiro).

    O pacote leva so codigo e dados (.py .xaml .yaml .json .png .svg .ico .txt
    .md .ps1). NUNCA leva DLLs (lib\webview2_runtime), as familias
    (lib\family_library) nem o startup.py: mudou algum desses, gere um
    INSTALADOR (build.ps1) em vez de um pacote.

    -BaseMinima e a menor versao de INSTALADOR que aceita este pacote (em geral,
    a do ultimo instalador publicado). O plugin recusa o pacote se a base
    instalada for menor, e a dockpane so o oferece a quem tem a base certa.

    Escrito sem acentuacao de proposito.

.PARAMETER Versao        Versao do pacote (ex: 3.2.0). Maior que a instalada.
.PARAMETER BaseMinima    Menor versao de instalador que aceita o pacote.
.PARAMETER ChavePrivada  Arquivo da chave privada. Padrao: %USERPROFILE%\fireutils-pacote-privada.xml

.EXAMPLE
    .\publicar-pacote.ps1 -Versao 3.2.0 -BaseMinima 3.1.0
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+(\.\d+){0,3}$')][string]$Versao,
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+(\.\d+){0,3}$')][string]$BaseMinima,
    [string]$ChavePrivada = (Join-Path $env:USERPROFILE 'fireutils-pacote-privada.xml')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$InstallerDir = $PSScriptRoot
$RepoRoot     = Split-Path -Parent $InstallerDir
$OutputDir    = Join-Path $InstallerDir 'output'
$Codigo       = Join-Path $RepoRoot 'Fire Utils.tab'

$Extensoes  = @('.py', '.xaml', '.yaml', '.json', '.png', '.svg', '.ico', '.txt', '.md', '.ps1')
$Protegidos = @('fire utils.tab/lib/webview2_runtime/', 'fire utils.tab/lib/family_library/')

if (-not (Test-Path -LiteralPath $ChavePrivada)) {
    throw "Chave privada nao encontrada: $ChavePrivada. Rode scripts\gerar-chave-pacote.ps1 primeiro."
}
if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# A chave publica embutida no plugin tem de ser a deste par, senao ninguem aceita o pacote.
$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
$rsa.PersistKeyInCsp = $false
$rsa.FromXmlString([System.IO.File]::ReadAllText($ChavePrivada))
$publica = [xml]$rsa.ToXmlString($false)
$fonte = Get-Content -LiteralPath (Join-Path $RepoRoot 'Fire Utils.tab\lib\plugin_pacote.py') -Raw -Encoding UTF8
if ($fonte -notmatch ('_CHAVE_PACOTE_MODULO\s*=\s*u"' + [regex]::Escape($publica.RSAKeyValue.Modulus) + '"')) {
    throw ('A chave publica em lib\plugin_pacote.py nao e a deste par de chaves. ' +
           'Cole os valores impressos por scripts\gerar-chave-pacote.ps1 e gere o INSTALADOR antes.')
}

$nome = "FireUtils-Pacote-$Versao-base-$BaseMinima.zip"
$zipPath = Join-Path $OutputDir $nome
$sigPath = "$zipPath.sig"
foreach ($p in $zipPath, $sigPath) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force } }

$arquivos = Get-ChildItem -LiteralPath $Codigo -Recurse -File | Where-Object {
    $rel = ('Fire Utils.tab/' + $_.FullName.Substring($Codigo.Length + 1).Replace('\', '/'))
    $minusculo = $rel.ToLowerInvariant()
    ($Extensoes -contains $_.Extension.ToLowerInvariant()) -and
    -not ($Protegidos | Where-Object { $minusculo.StartsWith($_) }) -and
    $minusculo -notmatch '/__pycache__/'
}
if (-not $arquivos) { throw 'Nenhum arquivo para empacotar.' }

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')
try {
    foreach ($arq in $arquivos) {
        $rel = 'Fire Utils.tab/' + $arq.FullName.Substring($Codigo.Length + 1).Replace('\', '/')
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $arq.FullName, $rel, 'Optimal')
    }
    $manifesto = (@{ versao = $Versao; baseMinima = $BaseMinima; criadoEm = (Get-Date -Format 's') } | ConvertTo-Json -Compress)
    $entrada = $zip.CreateEntry('pacote.json')
    $escritor = New-Object System.IO.StreamWriter($entrada.Open(), (New-Object System.Text.UTF8Encoding($false)))
    $escritor.Write($manifesto)
    $escritor.Dispose()
} finally {
    $zip.Dispose()
}

$bytes = [System.IO.File]::ReadAllBytes($zipPath)
$assinatura = $rsa.SignData($bytes, 'SHA256')
[System.IO.File]::WriteAllText($sigPath, [Convert]::ToBase64String($assinatura))

# Confere o que acabou de assinar, do jeito que o plugin vai conferir.
$conferir = New-Object System.Security.Cryptography.RSACryptoServiceProvider
$conferir.PersistKeyInCsp = $false
$conferir.FromXmlString($rsa.ToXmlString($false))
if (-not $conferir.VerifyData($bytes, 'SHA256', $assinatura)) { throw 'A assinatura gerada nao confere.' }

$tamanho = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1KB, 0)
Write-Host ''
Write-Host "Pacote:     $zipPath ($tamanho KB, $($arquivos.Count) arquivos)" -ForegroundColor Green
Write-Host "Assinatura: $sigPath" -ForegroundColor Green
Write-Host ''
Write-Host 'Suba no bucket plugin-releases: primeiro o .sig, depois o .zip (sem renomear).'
Write-Host "Quem tem instalador $BaseMinima ou mais novo recebe a atualizacao ao abrir a dockpane."
