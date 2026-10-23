#Requires -Version 5.1
<#
.SYNOPSIS
    Passa a usar uma chave privada de pacote que voce JA TEM (por exemplo, a antiga).

.DESCRIPTION
    Le o arquivo da chave PRIVADA e escreve a chave PUBLICA correspondente em
    Fire Utils.tab\lib\plugin_pacote.py (_CHAVE_PACOTE_MODULO e _CHAVE_PACOTE_EXPOENTE),
    para o repositorio ficar de acordo com essa chave. Assim o publicar-pacote.ps1
    assina com ela e os plugins que ja tem a chave publica correspondente aceitam
    os pacotes.

    Nao gera chave nova e nao mexe no arquivo da chave privada. Use este script
    para voltar a uma chave antiga; NAO use gerar-chave-pacote.ps1 para isso (ele
    cria um par diferente). Depois, faca commit do plugin_pacote.py: todo
    instalador novo deve levar a MESMA chave publica.

    Escrito sem acentuacao de proposito (powershell.exe le arquivo sem BOM como ANSI).

.PARAMETER ChavePrivada
    Caminho do arquivo .xml da chave privada.

.EXAMPLE
    .\scripts\usar-chave-pacote.ps1 -ChavePrivada "C:\Users\victo\fireutils-pacote-privada-antiga.xml"
#>
param(
    [Parameter(Mandatory = $true)][string]$ChavePrivada
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ChavePrivada)) {
    throw "Arquivo nao encontrado: $ChavePrivada"
}

$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
$rsa.PersistKeyInCsp = $false
try {
    $rsa.FromXmlString([System.IO.File]::ReadAllText($ChavePrivada))
} catch {
    throw "O arquivo nao e uma chave RSA valida em XML: $($_.Exception.Message)"
}
if ($rsa.PublicOnly) {
    throw 'Este arquivo so tem a parte PUBLICA da chave. E preciso o arquivo da chave PRIVADA (com <D>, <P>, <Q>).'
}

$publica = [xml]$rsa.ToXmlString($false)
$linhaModulo   = ('_CHAVE_PACOTE_MODULO = u"{0}"' -f $publica.RSAKeyValue.Modulus)
$linhaExpoente = ('_CHAVE_PACOTE_EXPOENTE = u"{0}"' -f $publica.RSAKeyValue.Exponent)

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$alvo = Join-Path $RepoRoot 'Fire Utils.tab\lib\plugin_pacote.py'
$texto = [System.IO.File]::ReadAllText($alvo, [System.Text.Encoding]::UTF8)

$texto = [regex]::Replace($texto, '(?m)^_CHAVE_PACOTE_MODULO\s*=\s*u"[^"]*"', { param($m) $linhaModulo })
$texto = [regex]::Replace($texto, '(?m)^_CHAVE_PACOTE_EXPOENTE\s*=\s*u"[^"]*"', { param($m) $linhaExpoente })
[System.IO.File]::WriteAllText($alvo, $texto, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ''
Write-Host 'plugin_pacote.py agora tem a chave publica desta chave privada:' -ForegroundColor Green
Write-Host "  $ChavePrivada"
Write-Host ''
Write-Host 'Proximo passo: publicar o pacote com essa mesma chave.' -ForegroundColor Yellow
Write-Host ('  .\publicar-pacote.ps1 -Versao X.Y.Z -BaseMinima A.B.C -ChavePrivada "{0}"' -f $ChavePrivada)
Write-Host ''
