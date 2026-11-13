# -*- coding: utf-8 -*-
"""
ferramentas_flutuantes.py — Fire Utils · lib/
Barra flutuante de ferramentas: janela WPF modeless, estreita e vertical, com
um botão por ferramenta de um grupo (hoje só "saidas"). Abre a partir da
sidebar da dockpane (ícone abaixo do divisor), fica acima do Revit, é
arrastável pela barra de título e fecha quando o usuário quiser. Não grava
posição nem estado: a cada sessão do Revit começa fechada e no canto padrão.

Mesmo padrão das janelas de prévia do plugin (forms.WPFWindow com Show(), não
ShowDialog()), com uma diferença deliberada: os botões NÃO executam a
ferramenta aqui. Cada clique manda FERRAMENTA_FLUTUANTE para a dockpane, que
já tem os seletores (estrutura, ocupação, níveis), o envio ao site e as
notificações das ferramentas — reaproveitar essa UI evita uma segunda cópia
dela em WPF. Por isso o clique também mostra a dockpane se ela estiver
escondida.

Contexto de API: um clique numa janela modeless acontece fora do contexto
válido do Revit, então o que depende da API (mostrar o DockablePane, pegar o
handle da janela do Revit para ser dona desta) vai por fila_acoes
(family_loader_events — ExternalEvent), nunca direto do evento de clique.

Mensagens (contrato em webapp/src/lib/bridge.js):
  ABRIR_JANELA_FERRAMENTAS {grupo}  JS -> Python: abre/fecha a barra do grupo.
  JANELA_FERRAMENTAS_ESTADO {grupo, aberta}  Python -> JS: o ícone da sidebar
      fica ativo enquanto a barra está aberta (inclusive quando ela é fechada
      pelo X da própria janela).
  FERRAMENTA_FLUTUANTE {grupo, acao}  Python -> JS: botão clicado.
"""

import os

import clr
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

from pyrevit import forms

from family_error_utils import texto_erro, print_seguro

_XAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"ferramentas_flutuantes.xaml")

_TIPO_ESTADO = u"JANELA_FERRAMENTAS_ESTADO"
_TIPO_CLIQUE = u"FERRAMENTA_FLUTUANTE"

# Largura da janela (XAML) e folga deixada à direita para a dockpane no
# posicionamento inicial.
_LARGURA = 196
_FOLGA_DOCKPANE = 470

# grupo -> título e ferramentas (acao, texto do botão). As ações são as que a
# dockpane entende em webapp/src/components/dashboard/SaidasFerramentas.jsx.
GRUPOS = {
    u"saidas": {
        u"titulo": u"SAÍDAS DE EMERGÊNCIA",
        u"ferramentas": [
            (u"selecao", u"Identificar por ambiente"),
            (u"niveis", u"Identificar por nível"),
            (u"todos", u"Identificar todos sem ocupação"),
            (u"sincronizar", u"Sincronizar ambientes"),
        ],
    },
}

# Uma janela por grupo, enquanto aberta. Vive no engine do dockpane (a bridge
# é importada de lá), então sobrevive entre mensagens.
_janelas = {}


def _mostrar_dockpane():
    """Garante a dockpane visível: o seletor da ferramenta mora nela."""
    try:
        from family_loader_webview_forms import PainelCarregadorFamiliasWeb
        painel = forms.get_dockable_panel(PainelCarregadorFamiliasWeb)
        if not painel.IsShown():
            painel.Show()
    except Exception as ex:
        print_seguro(u"[AVISO] Não foi possível mostrar a dockpane: {}".format(texto_erro(ex)))


class _JanelaFerramentas(forms.WPFWindow):
    def __init__(self, grupo, definicao, ao_clicar):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.grupo = grupo
        self.TxtTitulo.Text = definicao[u"titulo"]
        for acao, texto in definicao[u"ferramentas"]:
            self.Botoes.Children.Add(self._criar_botao(acao, texto, ao_clicar))

    def _criar_botao(self, acao, texto, ao_clicar):
        from System.Windows.Controls import Button
        botao = Button()
        botao.Content = texto
        botao.Style = self.FindResource(u"BotaoFerramenta")
        botao.ToolTip = texto
        # O lambda fica dentro deste método (não direto no laço de __init__):
        # cada chamada tem a sua `acao`, sem o bug do closure compartilhado.
        botao.Click += lambda sender, args: ao_clicar(acao)
        return botao


def _posicionar(janela):
    from System.Windows import SystemParameters
    area = SystemParameters.WorkArea
    janela.Left = max(area.Left, area.Right - _LARGURA - _FOLGA_DOCKPANE)
    janela.Top = area.Top + 140


def _definir_dona(janela, uiapp):
    """Dona = janela do Revit: a barra fica sempre acima dele e some junto ao
    minimizar, sem cobrir outros programas (Topmost global cobriria)."""
    try:
        from System.Windows.Interop import WindowInteropHelper
        WindowInteropHelper(janela).Owner = uiapp.MainWindowHandle
    except Exception as ex:
        print_seguro(u"[AVISO] Barra flutuante sem janela dona (usando Topmost): {}".format(texto_erro(ex)))
        janela.Topmost = True


def alternar(uiapp, grupo, fila_acoes, postar_mensagem):
    """Abre a barra do grupo, ou fecha se já estiver aberta. Chamar na thread
    de API (via fila_acoes), de onde há o uiapp para pegar o handle do Revit."""
    existente = _janelas.get(grupo)
    if existente is not None:
        existente.Close()  # o evento Closed limpa _janelas e avisa a dockpane
        return

    definicao = GRUPOS.get(grupo)
    if definicao is None:
        print_seguro(u"[AVISO] Grupo de ferramentas desconhecido: {}".format(grupo))
        return

    def ao_clicar(acao):
        def executar(_uiapp):
            _mostrar_dockpane()
            postar_mensagem(_TIPO_CLIQUE, {u"grupo": grupo, u"acao": acao})
        fila_acoes.enfileirar(executar)

    janela = _JanelaFerramentas(grupo, definicao, ao_clicar)
    _definir_dona(janela, uiapp)
    _posicionar(janela)

    def ao_fechar(sender, args):
        _janelas.pop(grupo, None)
        try:
            postar_mensagem(_TIPO_ESTADO, {u"grupo": grupo, u"aberta": False})
        except Exception as ex:
            print_seguro(u"[AVISO] Falha ao avisar o fechamento da barra: {}".format(texto_erro(ex)))

    janela.Closed += ao_fechar
    _janelas[grupo] = janela
    janela.Show()
    postar_mensagem(_TIPO_ESTADO, {u"grupo": grupo, u"aberta": True})


def tratar_abrir_janela(uiapp, payload, fila_acoes, postar_mensagem):
    """ABRIR_JANELA_FERRAMENTAS. Rede de segurança como nas outras bridges:
    sem ela, uma exceção só apareceria no console do pyRevit."""
    try:
        alternar(uiapp, (payload or {}).get(u"grupo"), fila_acoes, postar_mensagem)
    except Exception as ex:
        print_seguro(u"[AVISO] Falha ao abrir a barra de ferramentas: {}".format(texto_erro(ex)))
        postar_mensagem(_TIPO_ESTADO, {u"grupo": (payload or {}).get(u"grupo"), u"aberta": False})
