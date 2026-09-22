; Fire Utils - instalador para Autodesk Revit (pyRevit extension)
;
; Compile com o Inno Setup 6 (ISCC.exe). Nao compile este arquivo
; diretamente: rode `installer\build.ps1`, que monta a pasta payload\ com
; os arquivos corretos da extensao antes de chamar o compilador.
;
; A extensao e instalada por usuario, em %APPDATA%, para nao exigir
; privilegio de administrador. A pasta de destino precisa terminar em
; ".extension" -- e assim que o pyRevit reconhece uma extensao.

#define AppName        "Fire Utils"
#define AppPublisher   "Fire Utils"
#define AppUrl         "https://github.com/victoryuri-dev/FireUtils.extension"
#define ExtensionDir   "FireUtils.extension"

; Sobrescrito por build.ps1 via /DAppVersion=...
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
; Nao altere o AppId: e ele que faz uma nova versao substituir a anterior
; em vez de instalar duas vezes lado a lado.
AppId={{8B4F2E91-7C3D-4A56-9E18-2D5F6A0B3C74}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}

DefaultDirName={userappdata}\pyRevit\Extensions\{#ExtensionDir}
DefaultGroupName={#AppName}

; O pyRevit so enxerga a extensao na pasta dele, entao deixar o usuario
; escolher o destino so criaria instalacoes que nao carregam.
DisableDirPage=yes
DisableProgramGroupPage=yes

; Instalacao por usuario: sem UAC, sem prompt de administrador.
PrivilegesRequired=lowest

; Saída em installer\output\ (ignorada pelo git). Não use dist\ na raiz:
; confunde com webapp\dist\, que é versionado de propósito.
OutputDir=output
OutputBaseFilename=FireUtils-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; Geradas por scripts\gerar-imagens.ps1 a partir da logo do repositório
; (build.ps1 chama sozinho quando faltam). O desinstalador herda o ícone do
; SetupIconFile, então não precisa de UninstallDisplayIcon.
SetupIconFile=assets\fireutils.ico
WizardImageFile=assets\wizard-large.bmp
WizardSmallImageFile=assets\wizard-small.bmp

; Sem diretiva de arquitetura de proposito: a instalacao so copia arquivos
; para %APPDATA%, sem tocar em Program Files nem no registro, entao nada
; aqui depende de 32/64 bits. Evita tambem a incompatibilidade entre
; ArchitecturesAllowed=x64 (Inno <= 6.2) e x64compatible (Inno >= 6.3).

UninstallDisplayName={#AppName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; Verificador de dependencias: extraido para a pasta temporaria e executado
; em PrepareToInstall, antes de qualquer arquivo ser copiado.
Source: "scripts\ensure-deps.ps1"; Flags: dontcopy

; A extensao em si. build.ps1 monta payload\ a partir do repositorio.
Source: "payload\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[UninstallDelete]
; Remove o que o plugin gera em tempo de execucao (.pyc, caches) e que
; portanto nao esta na lista de arquivos instalados.
Type: filesandordirs; Name: "{app}"

[Messages]
brazilianportuguese.FinishedLabel=A instalação do [name] foi concluída.%n%nReinicie o Revit para que a aba Fire Utils apareça na faixa de opções.

[Code]

const
  DEPS_OK               = 0;
  DEPS_SEM_PYREVIT      = 1;
  URL_PYREVIT_RELEASES  = 'https://github.com/pyrevitlabs/pyRevit/releases/latest';

{ Procura qualquer instalacao do Revit para avisar cedo o usuario que
  instalou o plugin na maquina errada. Nao bloqueia: alguem pode estar
  preparando a maquina antes de instalar o Revit. }
function RevitEncontrado(): Boolean;
begin
  Result := DirExists(ExpandConstant('{userappdata}\Autodesk\Revit')) or
            DirExists(ExpandConstant('{commonappdata}\Autodesk\Revit'));
end;

{ Instalações feitas por git clone ficam registradas no pyRevit como
  caminho de extensão customizado. Se uma dessas continuar ativa, o cliente
  passa a ter duas cópias do Fire Utils carregando ao mesmo tempo -- com
  abas duplicadas e versões diferentes do código. Todos os clientes que
  instalaram antes deste instalador caem nesse caso, então vale avisar. }
function TemCaminhoDeExtensaoCustomizado(): Boolean;
var
  Config: String;
  Linhas: TArrayOfString;
  Linha: String;
  i: Integer;
begin
  Result := False;

  Config := ExpandConstant('{userappdata}\pyRevit\pyRevit_config.ini');
  if not FileExists(Config) then
    Exit;

  if not LoadStringsFromFile(Config, Linhas) then
    Exit;

  for i := 0 to GetArrayLength(Linhas) - 1 do
  begin
    Linha := Trim(LowerCase(Linhas[i]));

    if Pos('userextensions', Linha) = 1 then
    begin
      { Quando não há nenhum caminho, a chave aparece como: userextensions = [] }
      if Pos('[]', Linha) = 0 then
        Result := True;

      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;

  if TemCaminhoDeExtensaoCustomizado() then
  begin
    if MsgBox('O pyRevit deste computador tem pelo menos uma pasta de extensões ' +
              'configurada manualmente.' + #13#10#13#10 +
              'Se o Fire Utils já estiver instalado por lá (por exemplo, por uma ' +
              'cópia feita com git), o Revit vai carregar as duas versões ao mesmo ' +
              'tempo e a aba pode aparecer duplicada.' + #13#10#13#10 +
              'Remova a instalação antiga em pyRevit > Settings > Custom Extension ' +
              'Directories antes de usar o plugin.' + #13#10#13#10 +
              'Deseja continuar com a instalação?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;

  if not RevitEncontrado() then
  begin
    if MsgBox('Não encontramos uma instalação do Autodesk Revit neste computador.' + #13#10#13#10 +
              'O Fire Utils é uma extensão do Revit e não funciona sozinho.' + #13#10#13#10 +
              'Deseja continuar mesmo assim?',
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

{ Roda ensure-deps.ps1 antes de copiar qualquer arquivo. Retornar string
  vazia libera a instalação; qualquer outro texto aborta e é exibido ao
  usuário. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  CaminhoScript: String;
  CodigoSaida: Integer;
begin
  Result := '';

  WizardForm.PreparingLabel.Caption :=
    'Verificando o pyRevit e o WebView2. Se algum estiver faltando, ' +
    'ele será baixado e instalado agora — isso pode levar alguns minutos.';
  WizardForm.Refresh();

  ExtractTemporaryFile('ensure-deps.ps1');
  CaminhoScript := ExpandConstant('{tmp}\ensure-deps.ps1');

  { -ExecutionPolicy Bypass evita que a política do computador do cliente
    bloqueie o script. Vale só para esta execução. }
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              '-NoProfile -ExecutionPolicy Bypass -File "' + CaminhoScript + '"',
              '', SW_HIDE, ewWaitUntilTerminated, CodigoSaida) then
  begin
    Result := 'Não foi possível executar a verificação de dependências.' + #13#10#13#10 +
              'Instale o pyRevit manualmente e rode este instalador de novo:' + #13#10 +
              URL_PYREVIT_RELEASES;
    Exit;
  end;

  if CodigoSaida = DEPS_SEM_PYREVIT then
  begin
    Result := 'O pyRevit é necessário para o Fire Utils funcionar, e não foi ' +
              'possível instalá-lo automaticamente.' + #13#10#13#10 +
              'Instale o pyRevit por este endereço e rode este instalador de novo:' + #13#10 +
              URL_PYREVIT_RELEASES + #13#10#13#10 +
              'Detalhes em: ' + ExpandConstant('{%TEMP}') + '\FireUtils-install.log';
    Exit;
  end;

  if CodigoSaida <> DEPS_OK then
  begin
    Result := 'A verificação de dependências falhou (código ' +
              IntToStr(CodigoSaida) + ').' + #13#10#13#10 +
              'Detalhes em: ' + ExpandConstant('{%TEMP}') + '\FireUtils-install.log';
    Exit;
  end;
end;
