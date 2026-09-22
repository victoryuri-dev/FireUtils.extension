#Requires -Version 5.1
<#
.SYNOPSIS
    Garante que as dependencias do Fire Utils estejam presentes na maquina:
    pyRevit e o WebView2 Runtime.

.DESCRIPTION
    Chamado pelo instalador (Inno Setup) antes de copiar a extensao. Nao
    depende do CLI `pyrevit`: ele e distribuido separado do instalador
    principal e o comando de registrar caminho de extensao tem historico de
    falhar silenciosamente (pyrevitlabs/pyRevit#1032). A extensao e copiada
    direto para a pasta de extensoes pelo proprio Inno Setup.

    Este arquivo e escrito sem acentuacao de proposito: o Inno Setup o
    executa via powershell.exe, e um salvamento acidental sem BOM
    corromperia as mensagens. A interface que o cliente le fica no .iss,
    que e Unicode nativo.

.PARAMETER SkipPyRevit
    Nao verifica nem instala o pyRevit.

.PARAMETER SkipWebView2
    Nao verifica nem instala o WebView2 Runtime.

.PARAMETER LogPath
    Arquivo de log. Padrao: %TEMP%\FireUtils-install.log

.OUTPUTS
    Codigo de saida:
      0 - tudo pronto
      1 - pyRevit ausente e a instalacao automatica nao foi possivel
      2 - falha inesperada
#>
[CmdletBinding()]
param(
    [switch] $SkipPyRevit,
    [switch] $SkipWebView2,
    [string] $LogPath = (Join-Path $env:TEMP 'FireUtils-install.log')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# GUID do WebView2 Evergreen Runtime no EdgeUpdate. Documentado pela
# Microsoft como a forma suportada de detectar o runtime.
$script:WebView2ClientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'

# Link oficial e estavel do Evergreen Bootstrapper (~2 MB, baixa o resto).
$script:WebView2BootstrapperUrl = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'

# Confirmado com `winget search pyrevit` (22/09/2026, retornou 6.5.5.26237).
# Nao confundir com pyRevit.pyRevit.CLI, que e o CLI -- pacote separado que
# nao carrega no Revit.
$script:PyRevitWingetId = 'pyRevit.pyRevit'

$script:PyRevitReleasesApi = 'https://api.github.com/repos/pyrevitlabs/pyRevit/releases/latest'
$script:PyRevitReleasesPage = 'https://github.com/pyrevitlabs/pyRevit/releases/latest'

function Write-Log {
    param(
        [Parameter(Mandatory)] [string] $Message,
        [ValidateSet('INFO', 'WARN', 'ERRO')] [string] $Level = 'INFO'
    )
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    try {
        Add-Content -Path $LogPath -Value $line -Encoding UTF8
    } catch {
        # Log e diagnostico, nunca motivo para abortar a instalacao.
    }
}

function Invoke-ProcessoComTimeout {
    <#
        Start-Process -Wait nao aceita timeout. Se o processo chamado abrir
        um prompt interativo -- o winget faz isso na primeira execucao,
        pedindo aceite dos termos das fontes -- a espera nunca termina. Como
        o instalador executa este script com a janela oculta, o cliente
        veria a instalacao travada sem nenhuma explicacao.

        Devolve o codigo de saida, ou $null se estourou o tempo.
    #>
    param(
        [Parameter(Mandatory)] [string]   $Caminho,
        [Parameter(Mandatory)] [string[]] $Argumentos,
        [int] $TimeoutSegundos = 600
    )

    $processo = Start-Process -FilePath $Caminho -ArgumentList $Argumentos -PassThru -NoNewWindow

    # Ler .Handle cacheia o handle nativo. Sem isso, ExitCode pode vir
    # indisponivel depois que o processo termina.
    $null = $processo.Handle

    if (-not $processo.WaitForExit($TimeoutSegundos * 1000)) {
        Write-Log ("Tempo esgotado ({0}s), encerrando: {1}" -f $TimeoutSegundos, $Caminho) 'ERRO'
        try { $processo.Kill() } catch { }
        return $null
    }

    return $processo.ExitCode
}

function Test-PyRevitInstalled {
    <#
        O sinal confiavel e o arquivo .addin dentro da pasta de Addins do
        Revit: e ele que faz o Revit carregar o pyRevit. A pasta
        %APPDATA%\pyRevit sozinha nao serve, porque sobra no disco depois
        de uma desinstalacao.
    #>
    $addinRoots = @(
        (Join-Path $env:APPDATA 'Autodesk\Revit\Addins'),
        (Join-Path $env:ProgramData 'Autodesk\Revit\Addins')
    )

    foreach ($root in $addinRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }

        $found = Get-ChildItem -LiteralPath $root -Filter 'pyRevit*.addin' -Recurse -File -ErrorAction SilentlyContinue |
                 Select-Object -First 1

        if ($found) {
            Write-Log ("pyRevit detectado: {0}" -f $found.FullName)
            return $true
        }
    }

    Write-Log 'pyRevit nao encontrado (nenhum .addin do pyRevit nas pastas de Addins do Revit).' 'WARN'
    return $false
}

function Install-PyRevitViaWinget {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Log 'winget nao disponivel nesta maquina.' 'WARN'
        return $false
    }

    Write-Log ("Instalando pyRevit via winget (id={0})..." -f $script:PyRevitWingetId)
    try {
        $codigo = Invoke-ProcessoComTimeout -Caminho $winget.Source -Argumentos @(
            'install',
            '--id', $script:PyRevitWingetId,
            '--exact',
            '--silent',
            '--accept-package-agreements',
            '--accept-source-agreements',
            # Sem isto o winget pode parar pedindo confirmacao (o aceite dos
            # termos das fontes aparece na primeira execucao da maquina).
            # Com a flag, ele falha na hora em vez de esperar -- e a falha
            # cai no download direto do GitHub.
            '--disable-interactivity'
        )

        if ($null -eq $codigo) {
            Write-Log 'winget nao respondeu no tempo esperado.' 'WARN'
            return $false
        }
        if ($codigo -eq 0) {
            Write-Log 'winget concluiu a instalacao do pyRevit.'
            return $true
        }
        Write-Log ("winget retornou codigo {0}." -f $codigo) 'WARN'
        return $false
    } catch {
        Write-Log ("Falha ao executar winget: {0}" -f $_.Exception.Message) 'WARN'
        return $false
    }
}

function Resolve-PyRevitInstallerUrl {
    <#
        Descobre o instalador na release mais recente em vez de fixar um
        nome de arquivo. Descarta o instalador "admin" (exige privilegio
        de administrador e instala para todos os usuarios) e o CLI, que e
        um pacote separado e nao carrega no Revit.

        Se a filtragem nao deixar exatamente um candidato, devolve $null em
        vez de arriscar baixar o arquivo errado.
    #>
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.SecurityProtocolType]::Tls12 -bor [Net.ServicePointManager]::SecurityProtocol
    } catch {
        Write-Log 'Nao foi possivel forcar TLS 1.2; seguindo com o padrao do sistema.' 'WARN'
    }

    try {
        Write-Log 'Consultando a release mais recente do pyRevit...'
        $release = Invoke-RestMethod -Uri $script:PyRevitReleasesApi -Headers @{
            'User-Agent' = 'FireUtils-Installer'
            'Accept'     = 'application/vnd.github+json'
        } -TimeoutSec 30

        $candidates = @(
            $release.assets |
            Where-Object { $_.name -like '*.exe' } |
            Where-Object { $_.name -notmatch '(?i)admin' } |
            Where-Object { $_.name -notmatch '(?i)\bcli\b|_cli|-cli' }
        )

        if ($candidates.Count -eq 1) {
            Write-Log ("Instalador resolvido: {0} (release {1})" -f $candidates[0].name, $release.tag_name)
            return $candidates[0].browser_download_url
        }

        Write-Log ("Filtro deixou {0} candidatos; nao da para escolher com seguranca." -f $candidates.Count) 'WARN'
        foreach ($c in $candidates) { Write-Log ("  candidato: {0}" -f $c.name) 'WARN' }
        return $null
    } catch {
        Write-Log ("Falha ao consultar a API do GitHub: {0}" -f $_.Exception.Message) 'WARN'
        return $null
    }
}

function Install-PyRevitViaDownload {
    $url = Resolve-PyRevitInstallerUrl
    if (-not $url) { return $false }

    $destino = Join-Path $env:TEMP ('pyRevit-setup-{0}.exe' -f ([guid]::NewGuid().ToString('N')))

    try {
        Write-Log ("Baixando {0}" -f $url)
        $progressoAnterior = $ProgressPreference
        # Sem isso o Invoke-WebRequest fica ordens de grandeza mais lento.
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -Uri $url -OutFile $destino -UseBasicParsing -TimeoutSec 600
        } finally {
            $ProgressPreference = $progressoAnterior
        }

        Write-Log 'Executando o instalador do pyRevit em modo silencioso...'
        # O pyRevit usa Inno Setup; estes sao os switches padrao dele.
        $codigo = Invoke-ProcessoComTimeout -Caminho $destino -Argumentos @(
            '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
        )

        if ($null -eq $codigo) {
            Write-Log 'Instalador do pyRevit nao respondeu no tempo esperado.' 'WARN'
            return $false
        }
        if ($codigo -eq 0) {
            Write-Log 'Instalador do pyRevit concluiu com sucesso.'
            return $true
        }
        Write-Log ("Instalador do pyRevit retornou codigo {0}." -f $codigo) 'WARN'
        return $false
    } catch {
        Write-Log ("Falha ao baixar/instalar o pyRevit: {0}" -f $_.Exception.Message) 'ERRO'
        return $false
    } finally {
        if (Test-Path -LiteralPath $destino) {
            Remove-Item -LiteralPath $destino -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-WebView2Installed {
    <#
        Windows 10/11 com Edge atualizado ja vem com o runtime. A chave do
        EdgeUpdate existe nas tres variantes conforme o runtime foi
        instalado (por maquina 64/32 bits ou por usuario).
    #>
    $chaves = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$($script:WebView2ClientGuid)",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$($script:WebView2ClientGuid)",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$($script:WebView2ClientGuid)"
    )

    foreach ($chave in $chaves) {
        if (-not (Test-Path -LiteralPath $chave)) { continue }

        $pv = (Get-ItemProperty -LiteralPath $chave -Name 'pv' -ErrorAction SilentlyContinue).pv
        # Uma chave orfa de desinstalacao deixa pv vazio ou 0.0.0.0.
        if ($pv -and $pv -ne '0.0.0.0') {
            Write-Log ("WebView2 Runtime detectado (versao {0})." -f $pv)
            return $true
        }
    }

    Write-Log 'WebView2 Runtime nao encontrado.' 'WARN'
    return $false
}

function Install-WebView2 {
    $destino = Join-Path $env:TEMP ('MicrosoftEdgeWebview2Setup-{0}.exe' -f ([guid]::NewGuid().ToString('N')))

    try {
        Write-Log 'Baixando o WebView2 Evergreen Bootstrapper...'
        $progressoAnterior = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -Uri $script:WebView2BootstrapperUrl -OutFile $destino -UseBasicParsing -TimeoutSec 300
        } finally {
            $ProgressPreference = $progressoAnterior
        }

        Write-Log 'Instalando o WebView2 Runtime...'
        $codigo = Invoke-ProcessoComTimeout -Caminho $destino -Argumentos @('/silent', '/install') -TimeoutSegundos 300

        if ($null -eq $codigo) {
            Write-Log 'Instalador do WebView2 nao respondeu no tempo esperado.' 'WARN'
            return $false
        }
        if ($codigo -eq 0) {
            Write-Log 'WebView2 Runtime instalado.'
            return $true
        }
        Write-Log ("Instalador do WebView2 retornou codigo {0}." -f $codigo) 'WARN'
        return $false
    } catch {
        Write-Log ("Falha ao instalar o WebView2: {0}" -f $_.Exception.Message) 'WARN'
        return $false
    } finally {
        if (Test-Path -LiteralPath $destino) {
            Remove-Item -LiteralPath $destino -Force -ErrorAction SilentlyContinue
        }
    }
}

# ---------------------------------------------------------------------------

try {
    Write-Log '=== Fire Utils: verificacao de dependencias ==='

    if (-not $SkipPyRevit) {
        if (-not (Test-PyRevitInstalled)) {
            Write-Log 'Tentando instalar o pyRevit automaticamente...'

            $ok = Install-PyRevitViaWinget
            if (-not $ok) { $ok = Install-PyRevitViaDownload }

            if (-not $ok) {
                Write-Log 'Nao foi possivel instalar o pyRevit automaticamente.' 'ERRO'
                Write-Log ("Instale manualmente por: {0}" -f $script:PyRevitReleasesPage) 'ERRO'
                exit 1
            }

            # Confirma o resultado em vez de confiar no codigo de saida: um
            # instalador pode sair com 0 sem ter registrado o .addin.
            if (-not (Test-PyRevitInstalled)) {
                Write-Log 'O instalador rodou, mas o pyRevit continua sem ser detectado.' 'ERRO'
                exit 1
            }
        }
    } else {
        Write-Log 'Verificacao do pyRevit pulada (-SkipPyRevit).'
    }

    if (-not $SkipWebView2) {
        if (-not (Test-WebView2Installed)) {
            # Sem WebView2 o plugin ainda instala e as ferramentas do Revit
            # funcionam; so o Carregador de Familias (a dockpane) fica sem
            # renderizar. Por isso isto nunca aborta a instalacao.
            if (-not (Install-WebView2)) {
                Write-Log 'Siga sem o WebView2: o Carregador de Familias pode nao abrir.' 'WARN'
            }
        }
    } else {
        Write-Log 'Verificacao do WebView2 pulada (-SkipWebView2).'
    }

    Write-Log '=== Dependencias prontas ==='
    exit 0
} catch {
    Write-Log ("Falha inesperada: {0}" -f $_.Exception.Message) 'ERRO'
    Write-Log ($_.ScriptStackTrace) 'ERRO'
    exit 2
}
