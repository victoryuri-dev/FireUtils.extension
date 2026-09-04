# -*- coding: utf-8 -*-
"""
family_loader_webview_forms.py — Fire Utils · lib/
Dockable Pane que hospeda o frontend React (webapp/) num
Microsoft.Web.WebView2.Wpf.WebView2 — catálogo de famílias de combate a
incêndio consumindo o acervo do Supabase.

Substitui o antigo catálogo WPF/XAML puro (que lia a pasta local
family_library/), aposentado depois que a migração pro Supabase foi
validada de ponta a ponta (login, catálogo, download, carregamento e
posicionamento das famílias).

Reestruturado a partir de um template pyRevit+WebView2 já validado
(GUIA_DOCKPANE_PYREVIT.md), que documenta e resolve de antemão os 4 erros
mais comuns desse tipo de integração — o mais importante sendo a falta de
um DispatcherSynchronizationContext na thread de UI do Revit (ver
comentário no __init__), que fazia a inicialização do WebView2 ficar
pendurada pra sempre, sem erro nenhum.

Dependências externas que NÃO vêm com o pyRevit/Revit:

  1. Assemblies do WebView2 SDK em Fire Utils.tab/lib/webview2_runtime/
     — já commitados no repositório (ver README.md dessa pasta).
  2. Build estático do frontend em webapp/dist/ — já commitado no
     repositório (rodar `npm install && npm run build` dentro de webapp/
     só se for atualizar o frontend — ver webapp/README.md).
  3. WebView2 Runtime instalado na máquina (Windows 10/11 atualizado já
     vem com ele via Edge; senão, instalar o "Evergreen Bootstrapper" da
     Microsoft).
"""

import json
import os

import clr

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_WEBVIEW2_RUNTIME_DIR = os.path.join(_LIB_DIR, u"webview2_runtime")

# Precisa rodar ANTES de qualquer AddReference/uso do WebView2: o
# Microsoft.Web.WebView2.Core.dll (gerenciado) faz P/Invoke pro
# WebView2Loader.dll (nativo) sem caminho absoluto — carregar só o
# assembly gerenciado via AddReferenceToFileAndPath não é suficiente pro
# Windows achar a DLL nativa correspondente.
os.environ[u"PATH"] = _WEBVIEW2_RUNTIME_DIR + os.pathsep + os.environ.get(u"PATH", u"")

clr.AddReferenceToFileAndPath(os.path.join(_WEBVIEW2_RUNTIME_DIR, u"Microsoft.Web.WebView2.Core.dll"))
clr.AddReferenceToFileAndPath(os.path.join(_WEBVIEW2_RUNTIME_DIR, u"Microsoft.Web.WebView2.Wpf.dll"))

clr.AddReference(u"System")
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

import System
import System.Threading
import System.Windows.Threading
from System import Uri, Environment as DotNetEnvironment

from Microsoft.Web.WebView2.Wpf import CoreWebView2CreationProperties

from pyrevit import forms
from pyrevit.coreutils.logger import get_logger

from family_loader_events import criar_fila_acoes
from family_webview_bridge import processar_mensagem_webview
from family_error_utils import texto_erro

_mlogger = get_logger(__name__)

_XAML_PATH = os.path.join(_LIB_DIR, u"family_loader_webview.xaml")

# Fire Utils.tab/lib/ -> Fire Utils.tab/ -> raiz da extensão -> webapp/dist/
# (webapp/ fica fora de "Fire Utils.tab", na raiz do repositório).
_EXT_ROOT = os.path.dirname(os.path.dirname(_LIB_DIR))
_WEBAPP_DIST_DIR = os.path.join(_EXT_ROOT, u"webapp", u"dist")

_VIRTUAL_HOST = u"appassets"

# Pasta gravável onde o WebView2 guarda seu profile (cache, cookies) — sem
# isso, ele tenta criar essa pasta ao lado do Revit.exe (dentro de
# "Program Files") e falha por falta de permissão de escrita.
_USER_DATA_FOLDER = os.path.join(
    DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.LocalApplicationData),
    u"FireUtils", u"WebView2UserData",
)


def _valor_enum_allow(core):
    """
    Resolve o valor "Allow" do enum CoreWebView2HostResourceAccessKind a
    partir do tipo que o próprio método SetVirtualHostNameToFolderMapping
    de `core` espera (via reflection), em vez de um import estático de
    nível de módulo.

    O pyRevit roda o startup.py (que registra/instancia o painel) e o
    script.py do botão (que só localiza essa instância já existente) em
    engines IronPython separados; cada engine reimporta este módulo do
    zero e refaz os clr.AddReferenceToFileAndPath, o que pode carregar
    duas cópias distintas do assembly Microsoft.Web.WebView2.Core.dll no
    mesmo processo. Um import estático do enum aqui pode acabar vindo de
    uma cópia diferente da que o `core` em mãos realmente espera — mesmo
    nome de tipo, mas identidades .NET diferentes — causando
    "expected CoreWebView2HostResourceAccessKind, got
    CoreWebView2HostResourceAccessKind". Resolver via reflection a partir
    do método do objeto que já temos em mãos garante que é sempre a
    cópia certa.
    """
    metodo = core.GetType().GetMethod(u"SetVirtualHostNameToFolderMapping")
    tipo_enum = metodo.GetParameters()[2].ParameterType
    return System.Enum.Parse(tipo_enum, u"Allow")


class PainelCarregadorFamiliasWeb(forms.WPFPanel):

    panel_id = u"9f2f6d4a-9d63-4d3b-8c2a-9b6f8b6a1c7e"
    panel_source = _XAML_PATH
    panel_title = u"Fire Utils — Biblioteca de Famílias"

    def __init__(self):
        forms.WPFPanel.__init__(self)

        self.fila_acoes = criar_fila_acoes()

        if not os.path.isdir(_WEBAPP_DIST_DIR):
            self._erro_fatal(
                u"Build do frontend não encontrado em:\n{}\n\n"
                u"Rode `npm install && npm run build` dentro de webapp/.".format(_WEBAPP_DIST_DIR)
            )
            return  # painel abre em branco — sem WebView configurado

        if not os.path.isdir(_USER_DATA_FOLDER):
            os.makedirs(_USER_DATA_FOLDER)

        propriedades = CoreWebView2CreationProperties()
        propriedades.UserDataFolder = _USER_DATA_FOLDER
        self.WebView.CreationProperties = propriedades

        # A thread de UI do Revit nunca instala um
        # DispatcherSynchronizationContext (isso normalmente é feito por
        # System.Windows.Application, que não existe aqui — o Revit é um
        # app Win32 nativo hospedando conteúdo WPF por baixo, não uma
        # aplicação WPF "de verdade"). Sem esse contexto, a continuação
        # assíncrona de EnsureCoreWebView2Async (código gerado pelo
        # compilador C# dentro do próprio Microsoft.Web.WebView2.Wpf.dll)
        # tenta retomar numa thread do thread-pool em vez desta thread —
        # e como ela não é dona dos objetos WPF, a Task nunca completa de
        # volta (nem sucesso, nem erro): fica pendurada pra sempre, e o
        # painel simplesmente nunca mostra nada. Instalando o contexto
        # manualmente, uma vez, a continuação passa a ser despachada de
        # volta pra esta mesma thread via Dispatcher, como uma aplicação
        # WPF normal já ganharia de graça.
        contexto_atual = System.Threading.SynchronizationContext.Current
        if not isinstance(contexto_atual, System.Windows.Threading.DispatcherSynchronizationContext):
            System.Threading.SynchronizationContext.SetSynchronizationContext(
                System.Windows.Threading.DispatcherSynchronizationContext(self.Dispatcher)
            )

        # Não confiar em Source sozinho: a dockpane é instanciada no
        # registro (startup.py), no boot do pyRevit — antes de estar
        # anexada a uma janela de verdade. Atribuir Source nesse momento
        # pode ser silenciosamente descartado. Dispara a inicialização
        # explicitamente e só navega quando ela realmente terminar.
        self.WebView.CoreWebView2InitializationCompleted += self._ao_inicializar_core
        self.WebView.EnsureCoreWebView2Async(None)

    def _erro_fatal(self, mensagem):
        """Popup (forms.alert) em vez de só print — mais garantido de
        aparecer na tela do que uma print que talvez não tenha nenhuma
        output window do pyRevit visível pra ir."""
        _mlogger.error(mensagem)
        print(u"[ERRO] {}".format(mensagem))
        forms.alert(
            mensagem,
            title=u"Fire Utils - Biblioteca de Famílias",
            warn_icon=True,
        )

    def _ao_inicializar_core(self, sender, args):
        if not args.IsSuccess:
            self._erro_fatal(
                u"Falha ao inicializar o CoreWebView2: {}".format(texto_erro(args.InitializationException))
            )
            return

        try:
            core = self.WebView.CoreWebView2
            core.Settings.AreDefaultContextMenusEnabled = True
            core.Settings.AreDevToolsEnabled = True

            core.SetVirtualHostNameToFolderMapping(
                _VIRTUAL_HOST, _WEBAPP_DIST_DIR, _valor_enum_allow(core)
            )
            core.WebMessageReceived += self._ao_receber_mensagem
            core.NavigationCompleted += self._ao_navegar

            self.WebView.Source = Uri(u"https://{}/index.html".format(_VIRTUAL_HOST))
        except Exception as ex:
            self._erro_fatal(u"Falha ao configurar o CoreWebView2 após inicializar: {}".format(texto_erro(ex)))

    def _ao_receber_mensagem(self, sender, args):
        processar_mensagem_webview(args.WebMessageAsJson, self.fila_acoes, self._postar_mensagem)

    def _postar_mensagem(self, tipo, payload):
        """
        Callback passado pra bridge (Python -> JS): manda uma mensagem de
        volta pro React via CoreWebView2.PostWebMessageAsJson. Chamado a
        partir de funções enfileiradas em self.fila_acoes, que sempre rodam
        na UI thread do Revit (mesma thread dona deste WebView) — seguro
        de tocar o WebView diretamente daqui.

        `ensure_ascii=True` explícito (é o padrão do json.dumps, mas
        deixamos claro de propósito) + `unicode(...)` no resultado: o
        payload pode ter nome de família com acento (ex.: "Extintor
        Portátil - A"), e isso garante que o texto que efetivamente
        cruza pro lado .NET é sempre puro ASCII — sem isso corre o
        mesmo risco de erro de codificação do IronPython documentado em
        family_error_utils.py, só que na hora de mandar a notificação em
        vez de na hora de carregar a família.
        """
        core = self.WebView.CoreWebView2
        if core is None:
            return
        core.PostWebMessageAsJson(unicode(json.dumps({u"type": tipo, u"payload": payload}, ensure_ascii=True)))

    def _ao_navegar(self, sender, args):
        """Diagnóstico: se a navegação pro index.html falhar (ex.: caminho
        errado no SetVirtualHostNameToFolderMapping, dist/ incompleto),
        args.IsSuccess vem False com o motivo em WebErrorStatus — sem isso,
        o painel só ficaria em branco, sem nenhuma pista do porquê."""
        if not args.IsSuccess:
            self._erro_fatal(
                u"Falha ao carregar a página do Carregador de Famílias: {}".format(args.WebErrorStatus)
            )


# ---------------------------------------------------------------------------
# Entrada pública — chamada pelo botão da faixa de opções
# ---------------------------------------------------------------------------
def alternar_painel(uiapp):
    """
    Mostra/esconde o Carregador de Famílias como Dockable Pane. Um novo
    clique no botão da faixa de opções alterna entre mostrar e esconder o
    mesmo painel (com sessão/filtro/seleção intactos), em vez de recriar
    ou abrir uma nova instância.

    Com nenhum projeto aberto (ex.: tela inicial do Revit), a API às vezes
    reporta o painel como registrado mas ainda não "criado" de fato —
    GetDockablePane pode lançar exceção nesse caso; por isso a checagem de
    ActiveUIDocument acontece antes de tentar mostrar o painel.
    """
    if not forms.is_registered_dockable_panel(PainelCarregadorFamiliasWeb):
        forms.alert(
            u"O painel do Carregador de Famílias não foi registrado.\n\n"
            u"Confira o output do pyRevit na inicialização da extensão — "
            u"provavelmente falta o WebView2 SDK "
            u"(Fire Utils.tab/lib/webview2_runtime/) ou o build do "
            u"frontend (webapp/dist/).",
            title=u"Fire Utils - Biblioteca de Famílias",
            warn_icon=True,
        )
        return

    if uiapp.ActiveUIDocument is None:
        forms.alert(
            u"Abra ou crie um projeto no Revit antes de abrir o Carregador "
            u"de Famílias.",
            title=u"Fire Utils - Biblioteca de Famílias",
            warn_icon=True,
        )
        return

    try:
        painel = forms.get_dockable_panel(PainelCarregadorFamiliasWeb)
        if painel.IsShown():
            painel.Hide()
        else:
            painel.Show()
    except Exception as ex:
        forms.alert(
            u"Não foi possível abrir o painel do Carregador de Famílias "
            u"agora ({}).\n\nTente novamente; se persistir, reinicie o "
            u"Revit.".format(texto_erro(ex)),
            title=u"Fire Utils - Biblioteca de Famílias",
            warn_icon=True,
        )
