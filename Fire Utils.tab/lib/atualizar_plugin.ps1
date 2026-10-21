#Requires -Version 5.1
<#
.SYNOPSIS
    Instala o Fire Utils depois que o Revit for fechado.

.DESCRIPTION
    Disparado em segundo plano por plugin_atualizacao.py (a dockpane baixou e
    conferiu o instalador). O instalador nao roda com o Revit aberto, entao
    este script espera todo Revit fechar, confere o instalador DE NOVO (o
    arquivo ficou numa pasta do usuario enquanto esperava) e so entao o
    executa em modo silencioso.

    Escrito sem acentuacao de proposito: o powershell.exe le arquivo sem BOM
    como ANSI, e um salvamento acidental corromperia as mensagens.

.PARAMETER Instalador   Caminho do FireUtils-Setup-X.Y.Z.exe baixado.
.PARAMETER Sha256       Hash esperado (hex) do instalador.
.PARAMETER Publicador   CN esperado da assinatura digital do instalador.
.PARAMETER Log          Arquivo de log.
#>
param(
    [Parameter(Mandatory = $true)][string]$Instalador,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$Sha256,
    [Parameter(Mandatory = $true)][string]$Publicador,
    [Parameter(Mandatory = $true)][string]$Log
)

$ErrorActionPreference = 'Stop'

function Write-Log([string]$Mensagem) {
    try {
        Add-Content -LiteralPath $Log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Mensagem)
    } catch { }
}

# Uma atualizacao agendada por vez: o segundo disparo sai sem fazer nada.
$criou = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\FireUtilsAtualizacao', [ref]$criou)
if (-not $criou) {
    Write-Log 'Ja ha uma atualizacao agendada; este disparo foi ignorado.'
    exit 0
}

try {
    Write-Log "Atualizacao agendada: $Instalador"

    # Sem limite de espera: o usuario fecha o Revit quando quiser.
    while (Get-Process -Name 'Revit' -ErrorAction SilentlyContinue) {
        Start-Sleep -Seconds 5
    }
    Write-Log 'Revit fechado.'

    if (-not (Test-Path -LiteralPath $Instalador)) {
        throw 'O instalador baixado nao existe mais.'
    }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Instalador).Hash
    if ($hash -ne $Sha256.ToUpperInvariant()) {
        throw 'O hash do instalador mudou desde o download.'
    }

    $assinatura = Get-AuthenticodeSignature -LiteralPath $Instalador
    if ($assinatura.Status -ne 'Valid') {
        throw "Assinatura digital invalida ($($assinatura.Status))."
    }
    $achou = [regex]::Match($assinatura.SignerCertificate.Subject, '(?:^|,\s*)CN=(?:"((?:[^"]|"")*)"|([^,]*))')
    $cn = if ($achou.Groups[1].Success) { $achou.Groups[1].Value.Replace('""', '"').Trim() } else { $achou.Groups[2].Value.Trim() }
    if (-not $achou.Success -or $cn -ne $Publicador) {
        throw "Assinante inesperado: $cn"
    }

    # /NOCLOSEAPPLICATIONS: se o Revit abriu de novo neste intervalo, o
    # instalador recusa em vez de fecha-lo a forca.
    $processo = Start-Process -FilePath $Instalador `
        -ArgumentList '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS' `
        -PassThru -Wait
    Write-Log "Instalador terminou com codigo $($processo.ExitCode)."

    if ($processo.ExitCode -eq 0) {
        Remove-Item -LiteralPath $Instalador -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Log "Falhou: $($_.Exception.Message)"
    exit 1
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
