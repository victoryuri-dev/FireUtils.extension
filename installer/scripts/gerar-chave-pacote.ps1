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

.PARAMETER Saida
    Onde gravar a chave privada.
#>
param(
    [string]$Saida = (Join-Path $env:USERPROFILE 'fireutils-pacote-privada.xml')
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
Write-Host ('_CHAVE_PACOTE_MODULO = u"{0}"' -f $publica.RSAKeyValue.Modulus)
Write-Host ('_CHAVE_PACOTE_EXPOENTE = u"{0}"' -f $publica.RSAKeyValue.Exponent)
Write-Host ''
