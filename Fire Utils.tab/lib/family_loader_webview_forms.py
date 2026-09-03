# -*- coding: utf-8 -*-
"""
family_loader_webview_forms.py — Fire Utils · lib/
Fase 3 do plano de migração: Dockable Pane que hospeda o frontend React
(webapp/) num Microsoft.Web.WebView2.Wpf.WebView2, substituindo aos poucos
o catálogo WPF/XAML puro (family_loader_forms.py).

Convive lado a lado com o painel antigo durante a migração — botão
separado na faixa de opções ("Carregador de Famílias (Web)"), pra não
quebrar o fluxo em produção enquanto Supabase/webapp ainda são validados.
Quando a migração estiver 100% validada, o botão antigo pode ser removido.

Dependências externas que NÃO vêm com o pyRevit/Revit (se qualquer uma
faltar, o registro do painel falha e é reportado no console do startup,
igual ao painel antigo — ver startup.py):

  1. Assemblies do WebView2 SDK em Fire Utils.tab/lib/webview2_runtime/
     — ver o README.md dessa pasta pra como obtê-los.
  2. Build estático do frontend em webapp/dist/ (rodar `npm install &&
     npm run build` dentro de webapp/ — ver webapp/README.md).
  3. WebView2 Runtime instalado na máquina (já vem por padrão no Windows
     10/11 com o Edge atualizado; em máquinas mais antigas precisa
     instalar o "Evergreen Bootstrapper" da Microsoft).

AVISO: a inicialização do WebView2 (EnsureCoreWebView2Async) não pôde ser
testada de ponta a ponta no ambiente onde este código foi escrito (sem
Windows/Revit/WebView2 disponíveis) — validar na prática assim que os itens
1-3 acima estiverem prontos.
"""

import os

import clr
clr.AddReference(u"System")
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

from pyrevit import forms
from pyrevit.coreutils.logger import get_logger

from family_loader_events import criar_fila_acoes
from family_webview_bridge import processar_mensagem_webview

_mlogger = get_logger(__name__)

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_XAML_PATH = os.path.join(_LIB_DIR, u"family_loader_webview.xaml")
_WEBVIEW2_RUNTIME_DIR = os.path.join(_LIB_DIR, u"webview2_runtime")

# Fire Utils.tab/lib/ -> Fire Utils.tab/ -> raiz da extensão -> webapp/dist/
# (webapp/ fica fora de "Fire Utils.tab", na raiz do repositório).
_EXT_ROOT = os.path.dirname(os.path.dirname(_LIB_DIR))
_WEBAPP_DIST_DIR = os.path.join(_EXT_ROOT, u"webapp", u"dist")

_VIRTUAL_HOST = u"appassets"
_ASSEMBLIES_WEBVIEW2 = (u"Microsoft.Web.WebView2.Core.dll", u"Microsoft.Web.WebView2.Wpf.dll")

_webview2_carregado = False


def _carregar_assemblies_webview2():
    """clr.AddReferenceToFileAndPath em vez de clr.AddReference — os
    assemblies do WebView2 não estão no GAC nem em nenhum diretório que o
    IronPython resolva sozinho, então precisam do caminho absoluto. Tem que
    rodar ANTES de forms.WPFPanel.__init__ (que carrega e interpreta o
    XAML) — o XAML referencia o namespace Microsoft.Web.WebView2.Wpf, que
    só existe depois desse AddReference."""
    global _webview2_carregado
    if _webview2_carregado:
        return
    for nome_dll in _ASSEMBLIES_WEBVIEW2:
        caminho = os.path.join(_WEBVIEW2_RUNTIME_DIR, nome_dll)
        if not os.path.isfile(caminho):
            raise IOError(
                u"Assembly do WebView2 não encontrado: {}\n"
                u"Baixe o pacote NuGet Microsoft.Web.WebView2 e copie os "
                u".dll pra essa pasta — ver "
                u"Fire Utils.tab/lib/webview2_runtime/README.md".format(caminho)
            )
        clr.AddReferenceToFileAndPath(caminho)
    _webview2_carregado = True


def _obter_user_data_dir():
    """
    Pasta gravável em %LOCALAPPDATA% pro WebView2 guardar seus dados
    (cache, cookies, perfil).

    Sem configurar isso, o WebView2 tenta criar essa pasta ao lado do
    executável do processo host — Revit.exe, dentro de "Program Files" —
    e falha com UnauthorizedAccessException/E_ACCESSDENIED, porque o
    usuário normalmente não tem permissão de escrita lá.
    """
    from System import Environment as DotNetEnvironment

    caminho = os.path.join(
        DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.LocalApplicationData),
        u"FireUtils", u"WebView2UserData",
    )
    if not os.path.isdir(caminho):
        os.makedirs(caminho)
    return caminho


class PainelCarregadorFamiliasWeb(forms.WPFPanel):

    panel_id = u"9f2f6d4a-9d63-4d3b-8c2a-9b6f8b6a1c7e"
    panel_source = _XAML_PATH
    panel_title = u"Fire Utils — Carregador de Famílias (Web)"

    def __init__(self):
        _carregar_assemblies_webview2()
        forms.WPFPanel.__init__(self)

        self.fila_acoes = criar_fila_acoes()

        if not os.path.isdir(_WEBAPP_DIST_DIR):
            self._erro_fatal(
                u"Build do frontend não encontrado em:\n{}\n\n"
                u"Rode `npm install && npm run build` dentro de webapp/.".format(_WEBAPP_DIST_DIR)
            )
            return  # painel abre em branco — sem WebView configurado

        # EnsureCoreWebView2Async é assíncrono (retorna uma Task) e o
        # IronPython 2.7 não tem await — em vez de esperar o resultado,
        # reagimos ao evento CoreWebView2InitializationCompleted, que
        # dispara tanto pro caminho síncrono quanto assíncrono da
        # inicialização, sem precisar lidar com Task nenhuma.
        #
        # A pasta de dados é configurada via CreationProperties do próprio
        # controle (não criando um CoreWebView2Environment manualmente) —
        # criar o Environment "na mão" causa
        # "expected CoreWebView2Environment, got CoreWebView2Environment"
        # quando o assembly Microsoft.Web.WebView2.Core.dll acaba carregado
        # em dois contextos diferentes (um pela nossa criação manual, outro
        # pelo próprio WebView2Base internamente); CreationProperties deixa
        # o controle criar o Environment sozinho, sem esse conflito.
        try:
            from Microsoft.Web.WebView2.Wpf import CoreWebView2CreationProperties

            propriedades = CoreWebView2CreationProperties()
            propriedades.UserDataFolder = _obter_user_data_dir()
            self.WebView.CreationProperties = propriedades

            self.WebView.CoreWebView2InitializationCompleted += self._ao_inicializar_core
            self.WebView.EnsureCoreWebView2Async(None)
        except Exception as ex:
            self._erro_fatal(u"Falha ao iniciar o CoreWebView2: {}".format(ex))

    def _erro_fatal(self, mensagem):
        """Popup (forms.alert) em vez de só print — um print dentro de um
        callback assíncrono (como CoreWebView2InitializationCompleted, que
        dispara bem depois do script do botão já ter retornado) pode não
        ter uma output window do pyRevit visível pra aparecer. Um alert
        sempre aparece na tela, garantido."""
        _mlogger.error(mensagem)
        print(u"[ERRO] {}".format(mensagem))
        forms.alert(
            mensagem,
            title=u"Fire Utils - Carregador de Famílias (Web)",
            warn_icon=True,
        )

    def _ao_inicializar_core(self, sender, args):
        try:
            if not args.IsSuccess:
                self._erro_fatal(
                    u"Falha ao inicializar o CoreWebView2: {}".format(args.InitializationException)
                )
                return

            from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind
            from System import Uri

            core = self.WebView.CoreWebView2

            # Normalmente já vêm True por padrão, mas alguma política do
            # sistema/versão do runtime pode ter mudado isso — setar
            # explícito garante que o botão direito e o DevTools funcionem.
            core.Settings.AreDefaultContextMenusEnabled = True
            core.Settings.AreDevToolsEnabled = True

            core.SetVirtualHostNameToFolderMapping(
                _VIRTUAL_HOST, _WEBAPP_DIST_DIR, CoreWebView2HostResourceAccessKind.Allow
            )
            core.WebMessageReceived += self._ao_receber_mensagem
            core.NavigationCompleted += self._ao_navegar

            # TEMPORÁRIO (fase de depuração): abre o DevTools sozinho, sem
            # depender de clique com botão direito no painel (que não
            # reage a cliques quando hospedado dentro do Dockable Pane do
            # Revit). Remover essa linha quando o carregamento estiver
            # validado ponta a ponta.
            core.OpenDevToolsWindow()

            self.WebView.Source = Uri(u"https://{}/index.html".format(_VIRTUAL_HOST))
        except Exception as ex:
            self._erro_fatal(u"Falha ao configurar o CoreWebView2 após inicializar: {}".format(ex))

    def _ao_receber_mensagem(self, sender, args):
        processar_mensagem_webview(args.WebMessageAsJson, self.fila_acoes)

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
    """Mostra/esconde o painel web — mesmo padrão de
    family_loader_forms.alternar_painel (ver aquele módulo pros comentários
    completos sobre o motivo de cada checagem)."""
    if not forms.is_registered_dockable_panel(PainelCarregadorFamiliasWeb):
        forms.alert(
            u"O painel web do Carregador de Famílias não foi registrado.\n\n"
            u"Confira o output do pyRevit na inicialização da extensão — "
            u"provavelmente falta o WebView2 SDK "
            u"(Fire Utils.tab/lib/webview2_runtime/) ou o build do "
            u"frontend (webapp/dist/).",
            title=u"Fire Utils - Carregador de Famílias (Web)",
            warn_icon=True,
        )
        return

    if uiapp.ActiveUIDocument is None:
        forms.alert(
            u"Abra ou crie um projeto no Revit antes de abrir o Carregador "
            u"de Famílias.",
            title=u"Fire Utils - Carregador de Famílias (Web)",
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
            u"Não foi possível abrir o painel web do Carregador de "
            u"Famílias agora ({}).\n\nTente novamente; se persistir, "
            u"reinicie o Revit.".format(ex),
            title=u"Fire Utils - Carregador de Famílias (Web)",
            warn_icon=True,
        )
