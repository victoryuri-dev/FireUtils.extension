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
from family_error_utils import texto_erro, print_seguro

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


def _string_para_unicode_seguro(valor):
    """`str` (bytes) acentuado vindo de qualquer lugar do payload (ex.: um
    nome de família lido de volta do documento) pode não estar em UTF-8 —
    decodificar direto travaria o json.dumps mais na frente com o mesmo
    erro de codificação do IronPython documentado em family_error_utils.py.
    Tenta UTF-8, cai pra latin-1 (nunca falha, todo byte tem correspondente)
    e, no limite, substitui o que não decodificar."""
    if isinstance(valor, unicode):
        return valor
    try:
        return valor.decode(u"utf-8")
    except Exception:
        try:
            return valor.decode(u"latin-1")
        except Exception:
            return valor.decode(u"ascii", u"replace")


def _sanitizar_payload_para_json(valor):
    """Percorre o payload (dict/list/tuple aninhados) garantindo que toda
    string vire unicode de verdade antes de chegar no json.dumps — ver
    _string_para_unicode_seguro. Sem isso, um único nome de família com
    encoding inesperado no meio de uma lista de dezenas derruba a
    mensagem INTEIRA (inclusive as famílias que carregaram sem problema
    nenhum), que é exatamente o sintoma de "carregou no projeto mas a
    dockpane mostra erro de reportar o resultado"."""
    if isinstance(valor, dict):
        return dict(
            (_sanitizar_payload_para_json(k), _sanitizar_payload_para_json(v))
            for k, v in valor.items()
        )
    if isinstance(valor, (list, tuple)):
        return [_sanitizar_payload_para_json(v) for v in valor]
    if isinstance(valor, str):
        return _string_para_unicode_seguro(valor)
    return valor


def _forcar_ascii(valor):
    """Última rede de segurança: substitui todo caractere não-ASCII
    (acentos, ç, etc.) por '?', em vez de tentar preservá-lo. Só entra em
    ação se até o serializador manual (_json_dumps_seguro, abaixo) falhar
    por algum motivo inesperado — perder a acentuação no texto que chega
    no React é um preço bem menor que a notificação inteira sumir (ver
    _postar_mensagem)."""
    if isinstance(valor, dict):
        return dict((_forcar_ascii(k), _forcar_ascii(v)) for k, v in valor.items())
    if isinstance(valor, (list, tuple)):
        return [_forcar_ascii(v) for v in valor]
    if isinstance(valor, unicode):
        return valor.encode(u"ascii", u"replace").decode(u"ascii")
    if isinstance(valor, str):
        return _string_para_unicode_seguro(valor).encode(u"ascii", u"replace").decode(u"ascii")
    return valor


# json.dumps(ensure_ascii=True) da stdlib NÃO é confiável aqui: na prática,
# um nome de família como "Painel de controle da bomba de incêndio" (o "ê"
# na posição 34) faz o PostWebMessageAsJson falhar com o mesmo erro de
# "codec desconhecido" do IronPython documentado em family_error_utils.py
# — mesmo depois de garantir que a string de entrada já era unicode de
# verdade. O suspeito é o próprio módulo json (portado do CPython, cheio
# de concatenação de literais `str`) fazendo, em algum ponto interno, uma
# mistura implícita de `str`/`unicode` que dispara o bug — não uma questão
# de UTF-8 vs. latin-1 na entrada. Pra não depender de entender exatamente
# ONDE dentro do json.dumps isso acontece, este serializador substitui o
# json.dumps inteiramente pra este uso: pequeno, escrito à mão, e usando
# só operações puramente unicode (iteração de caractere, ord(), u"".join),
# que nunca misturam str com unicode em lugar nenhum.
_ESCAPES_JSON = {
    u'"': u'\\"',
    u"\\": u"\\\\",
    u"\b": u"\\b",
    u"\f": u"\\f",
    u"\n": u"\\n",
    u"\r": u"\\r",
    u"\t": u"\\t",
}


def _json_string_literal(texto):
    """Monta o literal de string JSON (com aspas) caractere a caractere —
    todo caractere fora do intervalo ASCII imprimível vira um \\uXXXX
    explícito, então o resultado final é sempre puro ASCII."""
    pedacos = [u'"']
    for caractere in texto:
        substituto = _ESCAPES_JSON.get(caractere)
        if substituto is not None:
            pedacos.append(substituto)
            continue
        codepoint = ord(caractere)
        if codepoint < 0x20 or codepoint > 0x7e:
            pedacos.append(u"\\u%04x" % codepoint)
        else:
            pedacos.append(caractere)
    pedacos.append(u'"')
    return u"".join(pedacos)


def _chave_para_unicode(chave):
    if isinstance(chave, unicode):
        return chave
    if isinstance(chave, str):
        return _string_para_unicode_seguro(chave)
    return unicode(chave)


def _json_dumps_seguro(valor):
    """Serializa `valor` (dict/list/tuple/unicode/str/int/long/float/bool/
    None aninhados — os únicos tipos que este bridge realmente manda pro
    JS) pra texto JSON, sempre unicode e sempre ASCII puro. Ver o
    comentário acima de _ESCAPES_JSON pro motivo de não usar json.dumps."""
    if valor is None:
        return u"null"
    if valor is True:
        return u"true"
    if valor is False:
        return u"false"
    if isinstance(valor, (int, long)):
        return unicode(valor)
    if isinstance(valor, float):
        return unicode(repr(valor))
    if isinstance(valor, unicode):
        return _json_string_literal(valor)
    if isinstance(valor, str):
        return _json_string_literal(_string_para_unicode_seguro(valor))
    if isinstance(valor, dict):
        pares = [
            u"{}:{}".format(_json_string_literal(_chave_para_unicode(k)), _json_dumps_seguro(v))
            for k, v in valor.items()
        ]
        return u"{" + u",".join(pares) + u"}"
    if isinstance(valor, (list, tuple)):
        return u"[" + u",".join(_json_dumps_seguro(v) for v in valor) + u"]"
    # Tipo inesperado num payload que só devia ter os tipos acima — melhor
    # um texto genérico do que deixar a serialização inteira quebrar.
    return _json_string_literal(unicode(repr(valor)))


class PainelCarregadorFamiliasWeb(forms.WPFPanel):

    panel_id = u"9f2f6d4a-9d63-4d3b-8c2a-9b6f8b6a1c7e"
    panel_source = _XAML_PATH
    panel_title = u"Fire Utils — Biblioteca de Famílias"

    # Instância viva de verdade, guardada assim que o Revit a cria (no
    # registro, startup.py) — forms.get_dockable_panel() NÃO devolve isso:
    # devolve o wrapper Autodesk.Revit.UI.DockablePane (só tem Show/Hide/
    # IsShown, nenhum dos nossos métodos/atributos - WebView, fila_acoes,
    # _postar_mensagem etc.). Quem precisa falar com o WebView2 de fora
    # desta classe (abrir_secao_hidrantes, abrir_dashboard) usa esta
    # referência, não get_dockable_panel().
    _instancia_ativa = None

    def __init__(self):
        forms.WPFPanel.__init__(self)
        PainelCarregadorFamiliasWeb._instancia_ativa = self

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
            core.NewWindowRequested += self._ao_pedir_nova_janela

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

        Usa `_json_dumps_seguro` (serializador escrito à mão, ver comentário
        acima de _ESCAPES_JSON) em vez do json.dumps da stdlib: na prática,
        um nome de família como "Painel de controle da bomba de incêndio"
        (o "ê") fazia o PostWebMessageAsJson falhar com o erro de "codec
        desconhecido" do IronPython (family_error_utils.py) mesmo com
        ensure_ascii=True e a string de entrada já sendo unicode de
        verdade — sinal de que o bug estava dentro do próprio módulo
        json.dumps sob esse IronPython específico, não na codificação da
        entrada. `_sanitizar_payload_para_json` continua rodando antes,
        garantindo que toda string do payload é unicode de verdade (uma
        `str`/bytes solta faria o serializador quebrar de outro jeito);
        `_json_dumps_seguro` já devolve texto puro ASCII, então não precisa
        de nenhum passo de ensure_ascii separado.

        Mesmo assim, o resultado inteiro (serializar + postar) fica num
        try/except: se algo desse jeito ainda falhar, cai num último
        fallback que força ASCII puro no payload (troca acento por '?')
        antes de tentar de novo — garante que a notificação chega, ainda
        que sem a acentuação, em vez de sumir e cair no catch genérico de
        family_webview_bridge.py ("Falha ao reportar o resultado").
        """
        core = self.WebView.CoreWebView2
        if core is None:
            return
        payload_seguro = _sanitizar_payload_para_json(payload)
        try:
            texto_json = _json_dumps_seguro({u"type": tipo, u"payload": payload_seguro})
            core.PostWebMessageAsJson(texto_json)
            return
        except Exception as e:
            print_seguro(u"[AVISO] Falha ao postar mensagem '{}' (tentando fallback ASCII): {}".format(tipo, texto_erro(e)))

        try:
            payload_ascii = _forcar_ascii(payload_seguro)
            texto_json = _json_dumps_seguro({u"type": tipo, u"payload": payload_ascii})
            core.PostWebMessageAsJson(texto_json)
        except Exception as e2:
            print_seguro(u"[AVISO] Fallback ASCII também falhou pra mensagem '{}': {}".format(tipo, texto_erro(e2)))

    def _ao_pedir_nova_janela(self, sender, args):
        """Um <a target="_blank"> do React (ex.: "abrir no site" do
        Dashboard) dispara isso — sem tratar, o WebView2 abriria uma janela
        popup própria, sem barra de endereço nem forma fácil de fechar.
        Cancela o comportamento padrão e abre no navegador padrão do
        sistema em vez disso."""
        args.Handled = True
        try:
            info = System.Diagnostics.ProcessStartInfo(args.Uri)
            info.UseShellExecute = True
            System.Diagnostics.Process.Start(info)
        except Exception as ex:
            _mlogger.warning(u"Falha ao abrir link externo ({}): {}".format(args.Uri, texto_erro(ex)))

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


def _postar_para_painel(tipo):
    """Posta uma mensagem (sem payload) pro React via a instância viva do
    painel (PainelCarregadorFamiliasWeb._instancia_ativa, ver __init__) —
    nunca via forms.get_dockable_panel(), que devolve só o wrapper
    Autodesk.Revit.UI.DockablePane (Show/Hide/IsShown), sem
    _postar_mensagem nem nenhum outro atributo nosso. Não faz nada
    (silencioso) se a instância ainda não existir por algum motivo — quem
    chama já mostrou/tentou mostrar o painel antes."""
    painel = PainelCarregadorFamiliasWeb._instancia_ativa
    if painel is not None:
        painel._postar_mensagem(tipo, {})


def abrir_secao_hidrantes(uiapp):
    """
    Mostra a dockpane (se estiver escondida) e manda o React trocar pra a
    aba "Sistema de Hidrantes" do Dashboard (mensagem ABRIR_HIDRANTES, ver
    webapp/src/lib/bridge.js) — chamada por "Dimensionar Hidrantes" ao
    final de um dimensionamento bem-sucedido, pra o RT já cair direto nos
    resultados na dockpane, sem precisar abrir o painel e navegar até lá
    manualmente.

    Deliberadamente silenciosa (sem popup, só um aviso no output do
    pyRevit): "Dimensionar Hidrantes" já fez o trabalho principal (mostrou
    o resultado, salvou o cache) antes de chegar aqui — abrir a dockpane é
    só uma conveniência extra, nunca motivo pra interromper esse fluxo com
    um erro. Isso inclui o caso da toda primeira vez que o painel é
    mostrado nesta sessão do Revit: o CoreWebView2 ainda pode estar
    inicializando de forma assíncrona (ver __init__ acima) quando
    _postar_mensagem roda logo em seguida — a mensagem some sem erro
    (core is None), e o RT só precisa clicar em "Hidrantes" na sidebar
    dessa vez.
    """
    if not forms.is_registered_dockable_panel(PainelCarregadorFamiliasWeb):
        return
    if uiapp.ActiveUIDocument is None:
        return
    try:
        painel = forms.get_dockable_panel(PainelCarregadorFamiliasWeb)
        if not painel.IsShown():
            painel.Show()
        _postar_para_painel(u"ABRIR_HIDRANTES")
    except Exception as ex:
        _mlogger.warning(u"Falha ao abrir a dockpane na seção de hidrantes: {}".format(texto_erro(ex)))


def abrir_dashboard(uiapp):
    """
    Mostra a dockpane (se estiver escondida) e manda o React ir direto pra
    a aba "Dashboard" (mensagem ABRIR_DASHBOARD, ver webapp/src/lib/
    bridge.js) — de onde o RT vincula o projeto Revit ativo a um projeto/
    estrutura do site (ConectarProjeto/SelecionarEstrutura, ver App.jsx e
    DashboardEstrutura.jsx). Chamada pelo botão "Vincular Projeto"
    (Biblioteca.panel), próprio pra isso porque nem todo RT quer passar
    pela Biblioteca de Famílias (aba inicial padrão) só pra chegar lá.

    Ao contrário de abrir_secao_hidrantes (conveniência ao final de outro
    comando, silenciosa), abrir o Dashboard É o propósito do clique nesse
    botão — falhas aparecem em alert, como alternar_painel, em vez de
    silenciosas.
    """
    if not forms.is_registered_dockable_panel(PainelCarregadorFamiliasWeb):
        forms.alert(
            u"O painel do Dashboard não foi registrado.\n\n"
            u"Confira o output do pyRevit na inicialização da extensão — "
            u"provavelmente falta o WebView2 SDK "
            u"(Fire Utils.tab/lib/webview2_runtime/) ou o build do "
            u"frontend (webapp/dist/).",
            title=u"Fire Utils - Dashboard",
            warn_icon=True,
        )
        return

    if uiapp.ActiveUIDocument is None:
        forms.alert(
            u"Abra ou crie um projeto no Revit antes de abrir o Dashboard.",
            title=u"Fire Utils - Dashboard",
            warn_icon=True,
        )
        return

    try:
        painel = forms.get_dockable_panel(PainelCarregadorFamiliasWeb)
        if not painel.IsShown():
            painel.Show()
        _postar_para_painel(u"ABRIR_DASHBOARD")
    except Exception as ex:
        forms.alert(
            u"Não foi possível abrir o Dashboard agora ({}).\n\nTente "
            u"novamente; se persistir, reinicie o Revit.".format(texto_erro(ex)),
            title=u"Fire Utils - Dashboard",
            warn_icon=True,
        )
