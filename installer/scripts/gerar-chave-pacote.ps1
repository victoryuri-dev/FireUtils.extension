#Requires -Version 5.1
<#
.SYNOPSIS
    Gera o par de chaves RSA que assina os pacotes de atualizacao do plugin.

.DESCRIPTION
    Rode UMA vez. A chave PRIVADA e gravada num arquivo FORA do repositorio
    (padrao: %USERPROFILE%\fireutils-pacote-privada.xml): quem a tiver pode
    publicar atualizacoes que todos os clientes aceitam. Guarde em backup
    offline e nunca a coloque no Git, no Supabase, no Vercel nem em nuvem
    compartilhada. Se ela vazar ou se perder, e preciso gerar outro par e
    distribuir um instalador novo (a chave publica fica dentro do plugin).

    A chave PUBLICA e impressa no formato que lib\plugin_pacote.py espera: cole
    as duas linhas em _CHAVE_PACOTE_MODULO e _CHAVE_PACOTE_EXPOENTE.

    Esta chave e DIFERENTE da chave da licenca (essa fica nos secrets do
    Supabase). Escrito sem acentuacao de proposito (powershell.exe le arquivo
    sem BOM como ANSI).

    Alem de imprimir, grava as duas linhas PUBLICAS (so elas, nunca a privada)
    em installer\output\chave-publica-pacote.txt e abre o arquivo no Bloco de
    Notas. Com -AtualizarPlugin, cola as linhas direto em
    Fire Utils.tab\lib\plugin_pacote.py (depois disso e preciso gerar um
    instalador novo, que leva a chave publica).

.PARAMETER Saida
    Onde gravar a chave privada.

.PARAMETER AtualizarPlugin
    Substitui _CHAVE_PACOTE_MODULO e _CHAVE_PACOTE_EXPOENTE em
    lib\plugin_pacote.py pelos valores deste par.

.PARAMETER SemBlocoDeNotas
    Nao abre o arquivo da chave publica no Bloco de Notas.
#>
param(
    [string]$Saida = (Join-Path $env:USERPROFILE 'fireutils-pacote-privada.xml'),
    [switch]$AtualizarPlugin,
    [switch]$SemBlocoDeNotas
)

$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $Saida) {
    throw "Ja existe uma chave em $Saida. Nao vou sobrescrever: apague-a de proposito se quiser outro par."
}

$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider(2048)
$rsa.PersistKeyInCsp = $false

[System.IO.File]::WriteAllText($Saida, $rsa.ToXmlString($true))
$publica = [xml]$rsa.ToXmlString($false)

Write-Host ''
Write-Host "Chave PRIVADA gravada em: $Saida" -ForegroundColor Yellow
Write-Host 'Faca backup OFFLINE dela agora. Nao a envie para lugar nenhum.' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Cole em Fire Utils.tab\lib\plugin_pacote.py:' -ForegroundColor Green
Write-Host ''
$linhaModulo   = ('_CHAVE_PACOTE_MODULO = u"{0}"' -f $publica.RSAKeyValue.Modulus)
$linhaExpoente = ('_CHAVE_PACOTE_EXPOENTE = u"{0}"' -f $publica.RSAKeyValue.Exponent)
Write-Host $linhaModulo
Write-Host $linhaExpoente
Write-Host ''

# Arquivo so com a parte PUBLICA, ao lado do instalador (installer\output nao vai
# para o Git). Nunca escreva nada da chave privada aqui.
$RepoRoot  = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$OutputDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'output'
if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
$arquivoPublico = Join-Path $OutputDir 'chave-publica-pacote.txt'
[System.IO.File]::WriteAllText($arquivoPublico, ($linhaModulo + "`r`n" + $linhaExpoente + "`r`n"))
Write-Host "Chave publica gravada em: $arquivoPublico" -ForegroundColor Green

if ($AtualizarPlugin) {
    $alvo = Join-Path $RepoRoot 'Fire Utils.tab\lib\plugin_pacote.py'
    $texto = [System.IO.File]::ReadAllText($alvo, [System.Text.Encoding]::UTF8)
    $texto = [regex]::Replace($texto, '(?m)^_CHAVE_PACOTE_MODULO\s*=\s*u"[^"]*"', { param($m) $linhaModulo })
    $texto = [regex]::Replace($texto, '(?m)^_CHAVE_PACOTE_EXPOENTE\s*=\s*u"[^"]*"', { param($m) $linhaExpoente })
    # UTF-8 sem BOM, como o resto dos arquivos Python do plugin.
    [System.IO.File]::WriteAllText($alvo, $texto, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "plugin_pacote.py atualizado. Gere um INSTALADOR novo (.\build.ps1): ele leva a chave publica." -ForegroundColor Yellow
}

if (-not $SemBlocoDeNotas) {
    Start-Process notepad.exe -ArgumentList ('"{0}"' -f $arquivoPublico)
}
