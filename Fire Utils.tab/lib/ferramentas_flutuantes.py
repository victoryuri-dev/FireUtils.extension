# -*- coding: utf-8 -*-
"""
ferramentas_flutuantes.py — Fire Utils · lib/
Barra flutuante de ferramentas: janela WPF modeless, estreita e vertical, com
um botão por ferramenta de um grupo ("saidas", "tubos"). Abre a partir da
sidebar da dockpane (ícones abaixo do divisor), fica acima do Revit, é
arrastável pelo cabeçalho (moldura própria, sem barra nativa) e fecha quando o
usuário quiser. Pode ser reduzida a só ícones. Não grava posição nem estado: a
cada sessão do Revit começa fechada e no canto padrão.

Mesmo padrão das janelas de prévia do plugin (forms.WPFWindow com Show(), não
ShowDialog()). Para onde vai o clique depende do grupo (GRUPOS[...]["destino"]):
  "dockpane"  Saídas: o clique manda FERRAMENTA_FLUTUANTE para a dockpane, que
              já tem os seletores (estrutura, ocupação, níveis), o envio ao
              site e as notificações — reaproveitar essa UI evita uma segunda
              cópia dela em WPF. O clique também mostra a dockpane escondida.
  "python"    Tubos: a ferramenta roda aqui, como o botão da faixa de opções.

Contexto de API: um clique numa janela modeless acontece fora do contexto
válido do Revit, então o que depende da API (rodar a ferramenta, mostrar o
DockablePane, pegar o handle da janela do Revit para ser dona desta) vai por
fila_acoes (family_loader_events — ExternalEvent), nunca direto do clique.

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

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_XAML_PATH = os.path.join(_LIB_DIR, u"ferramentas_flutuantes.xaml")
# PNGs dos ícones, renderizados dos mesmos SVGs da dockpane
# (webapp/src/assets/icons/*-icon.svg) com o claro do duotone em #F5F5F7, a
# cor que o tema escuro dá a eles lá. O WPF não lê SVG com máscara.
_ICONES_DIR = os.path.join(_LIB_DIR, u"assets", u"ferramentas")

_TIPO_ESTADO = u"JANELA_FERRAMENTAS_ESTADO"
_TIPO_CLIQUE = u"FERRAMENTA_FLUTUANTE"

# Largura da janela (XAML) e folga deixada à direita para a dockpane no
# posicionamento inicial.
_LARGURA = 220
_LARGURA_REDUZIDA = 84
_FOLGA_DOCKPANE = 470

# grupo -> título, destino e ferramentas (acao, texto do botão, arquivo do
# ícone em assets/ferramentas/).
#   destino "dockpane": o clique vai para a dockpane, que tem os seletores da
#     ferramenta (webapp/src/components/dashboard/SaidasFerramentas.jsx).
#   destino "python": a ferramenta roda aqui mesmo (ver _rodar_comando_tubos),
#     como o botão equivalente da faixa de opções.
GRUPOS = {
    u"saidas": {
        u"titulo": u"SAÍDAS DE EMERGÊNCIA",
        u"destino": u"dockpane",
        u"ferramentas": [
            (u"selecao", u"Identificar por ambiente", u"ocupacao"),
            (u"niveis", u"Identificar por nível", u"pornivel"),
            (u"todos", u"Identificar todos sem ocupação", u"todos"),
            (u"sincronizar", u"Sincronizar ambientes", u"sincronizar-ambiente"),
        ],
    },
    u"tubos": {
        u"titulo": u"TUBOS",
        u"destino": u"python",
        u"ferramentas": [
            (u"hidrante", u"Inserir hidrante por nível", u"tubos-hidrante"),
            (u"abrigo", u"Conectar abrigo", u"tubos-abrigo"),
            (u"tubo", u"Conectar tubo", u"tubos-tubo"),
        ],
    },
}

# Reduzida (só ícones) ou expandida: lembrado só enquanto o Revit estiver
# aberto, para a barra reaberta manter o modo que o usuário deixou.
_estado = {u"reduzida": False}

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
        # Partes que mudam entre os modos (preenchidas por _criar_botao).
        self._colunas_icone = []
        self._colunas_texto = []
        self._imagens = []
        self._botoes = []
        self._rotulos = []
        for acao, texto, icone in definicao[u"ferramentas"]:
            self.Botoes.Children.Add(self._criar_botao(acao, texto, icone, ao_clicar))
        self.BtnReduzir.Click += self._ao_alternar_reducao
        self.BtnFechar.Click += lambda sender, args: self.Close()
        # Sem barra de título nativa, o cabeçalho é a alça de arrastar. Os
        # botões tratam o próprio clique, então não iniciam o arrasto.
        self.Cabecalho.MouseLeftButtonDown += self._ao_arrastar
        self._aplicar_reducao(_estado[u"reduzida"])

    def _ao_arrastar(self, sender, args):
        try:
            self.DragMove()
        except Exception:
            pass  # DragMove lança se o botão já foi solto; sem importância.

    def _ao_alternar_reducao(self, sender, args):
        _estado[u"reduzida"] = not _estado[u"reduzida"]
        self._aplicar_reducao(_estado[u"reduzida"])

    def _aplicar_reducao(self, reduzida):
        """Reduzida: só os ícones (centralizados, nome fica no tooltip).
        Expandida: ícone + nome."""
        from System import Double
        from System.Windows import GridLength, GridUnitType, HorizontalAlignment, Visibility
        from System.Windows.Controls import Grid

        for coluna in self._colunas_icone:
            coluna.Width = GridLength(1, GridUnitType.Star) if reduzida else GridLength(26)
        for coluna in self._colunas_texto:
            coluna.Width = GridLength(0) if reduzida else GridLength(1, GridUnitType.Star)
        for imagem in self._imagens:
            imagem.HorizontalAlignment = HorizontalAlignment.Center if reduzida else HorizontalAlignment.Left
        # Reduzida: botões quadrados (52x52) e ícone maior; expandida: botão
        # na largura toda, altura do conteúdo (NaN = automático).
        for botao in self._botoes:
            botao.Width = 52 if reduzida else Double.NaN
            botao.Height = 52 if reduzida else Double.NaN
            botao.HorizontalAlignment = HorizontalAlignment.Center if reduzida else HorizontalAlignment.Stretch
        for imagem in self._imagens:
            imagem.Width = 28 if reduzida else 20
            imagem.Height = 28 if reduzida else 20
        for rotulo in self._rotulos:
            rotulo.Visibility = Visibility.Collapsed if reduzida else Visibility.Visible

        self.TxtTitulo.Visibility = Visibility.Collapsed if reduzida else Visibility.Visible
        Grid.SetColumnSpan(self.PainelBotoesTopo, 2 if reduzida else 1)
        self.PainelBotoesTopo.HorizontalAlignment = HorizontalAlignment.Center if reduzida else HorizontalAlignment.Right
        self.BtnReduzir.Content = u"»" if reduzida else u"«"
        self.BtnReduzir.ToolTip = u"Expandir (ícones e nomes)" if reduzida else u"Reduzir (só ícones)"
        self.Width = _LARGURA_REDUZIDA if reduzida else _LARGURA

    def _criar_botao(self, acao, texto, icone, ao_clicar):
        from System import Uri, UriKind
        from System.Windows import GridLength, GridUnitType, TextWrapping, Thickness, VerticalAlignment
        from System.Windows.Controls import Button, ColumnDefinition, Grid, Image, TextBlock
        from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage

        botao = Button()
        botao.Style = self.FindResource(u"BotaoFerramenta")
        botao.ToolTip = texto
        self._botoes.append(botao)

        conteudo = Grid()
        coluna_icone = ColumnDefinition()
        coluna_icone.Width = GridLength(26)
        coluna_texto = ColumnDefinition()
        coluna_texto.Width = GridLength(1, GridUnitType.Star)
        conteudo.ColumnDefinitions.Add(coluna_icone)
        self._colunas_icone.append(coluna_icone)
        self._colunas_texto.append(coluna_texto)
        conteudo.ColumnDefinitions.Add(coluna_texto)

        caminho = os.path.join(_ICONES_DIR, icone + u".png")
        if os.path.isfile(caminho):
            imagem_fonte = BitmapImage()
            imagem_fonte.BeginInit()
            imagem_fonte.UriSource = Uri(caminho, UriKind.Absolute)
            # OnLoad: lê o arquivo na hora e solta — sem isso o PNG ficaria
            # travado enquanto a janela existe (atrapalha atualizar o plugin).
            imagem_fonte.CacheOption = BitmapCacheOption.OnLoad
            imagem_fonte.EndInit()
            imagem = Image()
            imagem.Source = imagem_fonte
            imagem.Width = 20
            imagem.Height = 20
            imagem.VerticalAlignment = VerticalAlignment.Center
            Grid.SetColumn(imagem, 0)
            self._imagens.append(imagem)
            conteudo.Children.Add(imagem)

        # TextBlock próprio: é ele que quebra a linha (TextWrapping não é
        # propriedade anexável, então não dá para pôr no ContentPresenter).
        rotulo = TextBlock()
        rotulo.Text = texto
        rotulo.TextWrapping = TextWrapping.Wrap
        rotulo.VerticalAlignment = VerticalAlignment.Center
        rotulo.Margin = Thickness(0, 0, 0, 0)
        Grid.SetColumn(rotulo, 1)
        self._rotulos.append(rotulo)
        conteudo.Children.Add(rotulo)
        botao.Content = conteudo

        # O lambda fica dentro deste método (não direto no laço de __init__):
        # cada chamada tem a sua `acao`, sem o bug do closure compartilhado.
        botao.Click += lambda sender, args: ao_clicar(acao)
        return botao


def _rodar_comando_tubos(uiapp, acao):
    """Roda a ferramenta de tubos como o botão da faixa de opções roda (os
    script.py de Fire Utils.tab/Tubos.panel são só estas chamadas), já no
    contexto de API desta fila. As ferramentas abrem as próprias janelas
    modeless e pedem seleção no modelo, o que o ExternalEvent permite."""
    from pyrevit import script

    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        forms.alert(u"Abra um projeto no Revit antes de usar esta ferramenta.",
                    title=u"FireUtils", warn_icon=True)
        return
    try:
        # Mesma trava de licença dos botões da faixa: exigir() encerra o
        # "script" com SystemExit, que aqui só pode encerrar a ferramenta —
        # deixá-lo subir chegaria ao Revit como exceção de ExternalEvent.
        from licenca_guard import exigir
        exigir(u"pro")

        if acao == u"hidrante":
            from hydrant_insert_core import run_coluna_multilevel as executar
        elif acao == u"abrigo":
            from connect_shelter_core_preview import conectar_abrigo_preview as executar
        elif acao == u"tubo":
            from connect_pipe import run as executar
        else:
            print_seguro(u"[AVISO] Ferramenta de tubos desconhecida: {}".format(acao))
            return
        executar(uidoc.Document, uidoc, script.get_output())
    except SystemExit:
        pass  # pyscript.exit() / exigir(): fim normal da ferramenta


def _posicionar(janela):
    from System.Windows import SystemParameters
    area = SystemParameters.WorkArea
    largura = _LARGURA_REDUZIDA if _estado[u"reduzida"] else _LARGURA
    # Cada barra já aberta empurra a nova um pouco para a esquerda, para não
    # nascerem uma em cima da outra.
    deslocamento = len(_janelas) * (largura + 12)
    janela.Left = max(area.Left, area.Right - largura - _FOLGA_DOCKPANE - deslocamento)
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
        if definicao[u"destino"] == u"python":
            fila_acoes.enfileirar(lambda uiapp: _rodar_comando_tubos(uiapp, acao))
            return

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
