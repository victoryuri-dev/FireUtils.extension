# -*- coding: utf-8 -*-
"""
family_loader_forms.py — Fire Utils · lib/
Code-behind (identidade visual Fire Utils — escura, com destaque vermelho)
do Carregador de Famílias, em formato de catálogo: pesquisa por texto,
categorias em destaque, cartões de família selecionáveis por clique e
carregamento em lote no documento ativo.

O layout estático (cores, grid, botões) vive em family_loader_forms.xaml e é
carregado via pyrevit.forms.WPFPanel — só o conteúdo dinâmico (tiles de
categoria, cartões de família, que dependem dos dados da biblioteca) é
montado aqui em código, dentro dos containers nomeados (x:Name) definidos no
XAML.

A janela é um Dockable Pane (painel de encaixe) da API do Revit: fica
acoplada à interface do Revit (ou flutuando, se o usuário preferir) e não
trava o app enquanto está aberta. Painéis de encaixe só podem ser
registrados junto do Revit durante o startup do add-in — por isso o registro
(forms.register_dockable_panel) acontece em startup.py, na raiz da extensão,
e não aqui. Este módulo só define a classe do painel; o botão da faixa de
opções (script.py) apenas mostra/esconde a instância já registrada.

Como o painel pode ficar visível o tempo todo enquanto o usuário trabalha no
Revit, qualquer ação que precise da API (carregar família) é despachada
através de um ExternalEvent (family_loader_events.py), nunca chamada
diretamente a partir de um clique.

Se a interface XAML falhar por qualquer motivo (ambiente WPF divergente,
XAML inválido etc.), o registro do painel falha silenciosamente em
startup.py e o botão da faixa de opções cai para o formulário padrão do
pyRevit (forms.SelectFromList), que já é funcional e testado — nesse caso a
janela é modal.

Preview (miniatura) das famílias: os cartões mostram a imagem em
family_library/.previews/<Categoria>/<Nome>.png quando ela existe (ver
family_loader.py), lida direto do disco — leve e instantânea. Esse .png é
adicionado manualmente pelo gestor da biblioteca (não há geração
automática); famílias sem preview continuam mostrando o monograma de duas
letras.
"""

import os

import clr
clr.AddReference(u"System")
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")
import System.Windows as SW
import System.Windows.Controls as SWC
import System.Windows.Media as SWM
import System.Windows.Media.Imaging as SWMI
import System.Windows.Input as SWI
from System import Uri, UriKind

from pyrevit import forms

from family_loader import (
    listar_familias, listar_categorias, carregar_familias,
    obter_symbol_para_posicionar, preview_valido,
)
from family_loader_events import criar_fila_acoes

_TODAS = u"Todas"

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_XAML_PATH = os.path.join(_LIB_DIR, u"family_loader_forms.xaml")

# Ordem de preferência para a logo do cabeçalho. O primeiro arquivo
# encontrado é usado; se nenhum existir, mantém-se o placeholder "LOGO" já
# definido no XAML.
_LOGO_CANDIDATOS = [
    os.path.join(_LIB_DIR, u"assets", u"logo.png"),
    os.path.join(_LIB_DIR, u"assets", u"etos-logo-hor.png"),
    os.path.join(_LIB_DIR, u"assets", u"etos-logo-vert.png"),
]


def _carregar_bitmap(caminho):
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        bmp = SWMI.BitmapImage()
        bmp.BeginInit()
        bmp.UriSource = Uri(caminho, UriKind.Absolute)
        bmp.CacheOption = SWMI.BitmapCacheOption.OnLoad
        bmp.EndInit()
        return bmp
    except Exception:
        return None


def _localizar_logo():
    for caminho in _LOGO_CANDIDATOS:
        bmp = _carregar_bitmap(caminho)
        if bmp is not None:
            return bmp
    return None


def _monograma(nome):
    """Duas letras usadas como 'miniatura' do cartão (não há preview do .rfa)."""
    palavras = [p for p in nome.replace(u"-", u" ").replace(u"_", u" ").split() if p]
    if not palavras:
        return u"?"
    if len(palavras) == 1:
        return palavras[0][:2].upper()
    return (palavras[0][0] + palavras[1][0]).upper()


def _icone_categoria(nome_categoria):
    if nome_categoria == _TODAS:
        return u"▦"
    limpo = nome_categoria.strip()
    return limpo[0].upper() if limpo else u"?"


# ---------------------------------------------------------------------------
# Carregamento silencioso (compartilhado entre a UI custom e o fallback) —
# sem popups; falhas só vão para o console do pyRevit, pra não travar o
# fluxo do usuário com uma mensagem a cada família carregada.
# ---------------------------------------------------------------------------
def _carregar_familias_silenciosamente(doc, entradas_selecionadas):
    carregadas, ja_existentes, erros = carregar_familias(doc, entradas_selecionadas)
    for nome, msg in erros:
        print(u"[AVISO] Falha ao carregar '{}': {}".format(nome, msg))
    return carregadas, ja_existentes, erros


# ---------------------------------------------------------------------------
# Fallback — formulário padrão do pyRevit (já testado e funcional)
# ---------------------------------------------------------------------------
def _mostrar_fallback(doc, entradas):
    if not entradas:
        forms.alert(
            u"Nenhuma família encontrada na biblioteca.\n\n"
            u"Coloque arquivos .rfa em subpastas de:\n"
            u"Fire Utils.tab/lib/family_library/<Categoria>/",
            title=u"Fire Utils - Carregador de Famílias",
            warn_icon=True,
        )
        return

    grupos = {}
    for entrada in entradas:
        grupos.setdefault(entrada.category, []).append(entrada)
    for lista_categoria in grupos.values():
        lista_categoria.sort(key=lambda e: e.name)

    selecionadas = forms.SelectFromList.show(
        grupos,
        title=u"Carregador de Famílias - Combate a Incêndio",
        button_name=u"Carregar selecionadas",
        multiselect=True,
        name_attr=u"name",
        group_selector_title=u"Categoria",
    )
    if not selecionadas:
        return

    _carregar_familias_silenciosamente(doc, selecionadas)


# ---------------------------------------------------------------------------
# Interface — catálogo, layout em family_loader_forms.xaml, como Dockable
# Pane (painel de encaixe) da API do Revit
# ---------------------------------------------------------------------------
class PainelCarregadorFamilias(forms.WPFPanel):

    panel_id = u"0ff990a6-98c0-4244-9e22-689d09941e47"
    panel_source = _XAML_PATH
    panel_title = u"Fire Utils — Carregador de Famílias"

    def __init__(self):
        forms.WPFPanel.__init__(self)

        self.todas_entradas = list(listar_familias())
        self.selecionadas_paths = {}   # path -> FamilyEntry
        self.categoria_atual = _TODAS
        self.tiles_categoria = {}      # categoria -> (icone_border, icone_txt, rotulo)
        self.fila_acoes = criar_fila_acoes()

        # Brushes definidas em family_loader_forms.xaml (Page.Resources) —
        # reaproveitadas aqui para os tiles/cartões montados dinamicamente,
        # mantendo uma única fonte de verdade para a paleta de cores.
        self.C_BG2         = self.Resources[u"BrushBg2"]
        self.C_BG3         = self.Resources[u"BrushBg3"]
        self.C_BORDER      = self.Resources[u"BrushBorder"]
        self.C_TEXT        = self.Resources[u"BrushText"]
        self.C_TEXT2       = self.Resources[u"BrushText2"]
        self.C_TEXT3       = self.Resources[u"BrushText3"]
        self.C_ACCENT      = self.Resources[u"BrushAccent"]
        self.C_ACCENT_TINT = self.Resources[u"BrushAccentTint"]
        self.C_WHITE       = self.Resources[u"BrushWhite"]
        self.C_TRANSPARENT = SWM.Brushes.Transparent

        # path -> BitmapImage já decodificado, pra não reler/redecodificar o
        # .png do disco a cada _atualizar_lista() (ex.: a cada tecla digitada
        # na busca).
        self._cache_bitmaps_preview = {}

        logo_bitmap = _localizar_logo()
        if logo_bitmap is not None:
            self.LogoImage.Source = logo_bitmap
            self.LogoImage.Visibility = SW.Visibility.Visible
            self.LogoPlaceholder.Visibility = SW.Visibility.Collapsed

        self._reconstruir_categorias()
        self._atualizar_lista()

    # ------------------------------------------------------------------
    # Categorias — tiles com ícone
    # ------------------------------------------------------------------
    def _estilizar_tile(self, nome_categoria, ativo):
        icone_border, icone_txt, rotulo = self.tiles_categoria[nome_categoria]
        icone_border.Background = self.C_ACCENT if ativo else self.C_BG2
        icone_border.BorderBrush = self.C_ACCENT if ativo else self.C_BORDER
        icone_txt.Foreground = self.C_WHITE if ativo else self.C_TEXT2
        rotulo.Foreground = self.C_ACCENT if ativo else self.C_TEXT2
        rotulo.FontWeight = SW.FontWeights.SemiBold if ativo else SW.FontWeights.Normal

    def _criar_tile_categoria(self, nome_categoria):
        ativo = (nome_categoria == self.categoria_atual)

        externo = SWC.StackPanel()
        externo.Margin = SW.Thickness(0, 0, 18, 10)
        externo.Width = 68
        externo.Cursor = SWI.Cursors.Hand
        externo.Background = self.C_TRANSPARENT  # garante hit-test em toda a área

        icone_border = SWC.Border()
        icone_border.Width = 48
        icone_border.Height = 48
        icone_border.CornerRadius = SW.CornerRadius(24)
        icone_border.HorizontalAlignment = SW.HorizontalAlignment.Center
        icone_border.BorderThickness = SW.Thickness(1)
        icone_border.Background = self.C_ACCENT if ativo else self.C_BG2
        icone_border.BorderBrush = self.C_ACCENT if ativo else self.C_BORDER

        icone_txt = SWC.TextBlock()
        icone_txt.Text = _icone_categoria(nome_categoria)
        icone_txt.FontSize = 16
        icone_txt.FontWeight = SW.FontWeights.SemiBold
        icone_txt.Foreground = self.C_WHITE if ativo else self.C_TEXT2
        icone_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
        icone_txt.VerticalAlignment = SW.VerticalAlignment.Center
        icone_border.Child = icone_txt

        rotulo = SWC.TextBlock()
        rotulo.Text = nome_categoria
        rotulo.FontSize = 10
        rotulo.Foreground = self.C_ACCENT if ativo else self.C_TEXT2
        rotulo.FontWeight = SW.FontWeights.SemiBold if ativo else SW.FontWeights.Normal
        rotulo.TextAlignment = SW.TextAlignment.Center
        rotulo.TextWrapping = SW.TextWrapping.Wrap
        rotulo.Margin = SW.Thickness(0, 6, 0, 0)

        externo.Children.Add(icone_border)
        externo.Children.Add(rotulo)

        return externo, icone_border, icone_txt, rotulo

    def _on_tile_click(self, nome_categoria):
        def _handler(sender, args):
            self.categoria_atual = nome_categoria
            for outro_nome in self.tiles_categoria:
                self._estilizar_tile(outro_nome, outro_nome == nome_categoria)
            self._atualizar_lista()
        return _handler

    def _reconstruir_categorias(self):
        self.TilesPanel.Children.Clear()
        self.tiles_categoria.clear()
        self.categoria_atual = _TODAS

        nomes = [_TODAS] + listar_categorias(self.todas_entradas)
        for nome in nomes:
            externo, icone_border, icone_txt, rotulo = self._criar_tile_categoria(nome)
            self.tiles_categoria[nome] = (icone_border, icone_txt, rotulo)
            externo.MouseLeftButtonDown += SWI.MouseButtonEventHandler(self._on_tile_click(nome))
            self.TilesPanel.Children.Add(externo)

    # ------------------------------------------------------------------
    # Catálogo — seções por categoria, cartões em grade
    # ------------------------------------------------------------------
    def _secoes_visiveis(self):
        texto = (self.TxtBusca.Text or u"").strip().lower()
        categoria_filtro = self.categoria_atual

        por_categoria = {}
        for entrada in self.todas_entradas:
            if categoria_filtro != _TODAS and entrada.category != categoria_filtro:
                continue
            if texto and texto not in entrada.name.lower():
                continue
            por_categoria.setdefault(entrada.category, []).append(entrada)

        for lista_cat in por_categoria.values():
            lista_cat.sort(key=lambda e: e.name)

        return sorted(por_categoria.items())

    def _entradas_filtradas(self):
        resultado = []
        for _categoria, entradas_categoria in self._secoes_visiveis():
            resultado.extend(entradas_categoria)
        return resultado

    def _obter_bitmap_preview(self, entrada):
        caminho_png = preview_valido(entrada)
        if not caminho_png:
            self._cache_bitmaps_preview.pop(entrada.path, None)
            return None
        if entrada.path not in self._cache_bitmaps_preview:
            self._cache_bitmaps_preview[entrada.path] = _carregar_bitmap(caminho_png)
        return self._cache_bitmaps_preview[entrada.path]

    def _criar_cartao_familia(self, entrada):
        selecionado = entrada.path in self.selecionadas_paths

        cartao = SWC.Border()
        cartao.Width = 138
        cartao.Height = 190
        cartao.Background = self.C_BG2
        cartao.BorderBrush = self.C_ACCENT if selecionado else self.C_BORDER
        cartao.BorderThickness = SW.Thickness(2 if selecionado else 1)
        cartao.CornerRadius = SW.CornerRadius(10)
        cartao.Padding = SW.Thickness(10)
        cartao.Margin = SW.Thickness(0, 0, 12, 12)
        cartao.Cursor = SWI.Cursors.Hand

        overlay = SWC.Grid()

        conteudo = SWC.StackPanel()

        # Quadrado (118x118 = largura útil do cartão, já descontado o
        # padding de 10 de cada lado) — imagem de preview em cima, nome
        # embaixo, igual ao card de referência.
        icone_tile = SWC.Border()
        icone_tile.Height = 118
        icone_tile.CornerRadius = SW.CornerRadius(8)
        icone_tile.ClipToBounds = True
        icone_tile.Background = self.C_ACCENT_TINT if selecionado else self.C_BG3

        # Preview manual (family_library/.previews/*.png) tem prioridade;
        # sem preview, cai no monograma de sempre.
        preview_bitmap = self._obter_bitmap_preview(entrada)

        if preview_bitmap is not None:
            icone_txt = None
            imagem_preview = SWC.Image()
            imagem_preview.Source = preview_bitmap
            imagem_preview.Stretch = SWM.Stretch.UniformToFill
            icone_tile.Child = imagem_preview
        else:
            icone_txt = SWC.TextBlock()
            icone_txt.Text = _monograma(entrada.name)
            icone_txt.FontSize = 22
            icone_txt.FontWeight = SW.FontWeights.Bold
            icone_txt.Foreground = self.C_ACCENT if selecionado else self.C_TEXT3
            icone_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
            icone_txt.VerticalAlignment = SW.VerticalAlignment.Center
            icone_tile.Child = icone_txt

        conteudo.Children.Add(icone_tile)

        nome_txt = SWC.TextBlock()
        nome_txt.Text = entrada.name
        nome_txt.FontSize = 11
        nome_txt.FontWeight = SW.FontWeights.SemiBold
        nome_txt.Foreground = self.C_TEXT
        nome_txt.TextWrapping = SW.TextWrapping.Wrap
        nome_txt.TextAlignment = SW.TextAlignment.Center
        nome_txt.MaxHeight = 34
        nome_txt.Margin = SW.Thickness(0, 8, 0, 0)
        conteudo.Children.Add(nome_txt)

        overlay.Children.Add(conteudo)

        badge = SWC.Border()
        badge.Width = 18
        badge.Height = 18
        badge.CornerRadius = SW.CornerRadius(9)
        badge.Background = self.C_ACCENT
        badge.HorizontalAlignment = SW.HorizontalAlignment.Right
        badge.VerticalAlignment = SW.VerticalAlignment.Top
        badge.Margin = SW.Thickness(0, -4, -4, 0)
        badge.Visibility = SW.Visibility.Visible if selecionado else SW.Visibility.Collapsed

        badge_txt = SWC.TextBlock()
        badge_txt.Text = u"✓"
        badge_txt.FontSize = 10
        badge_txt.FontWeight = SW.FontWeights.Bold
        badge_txt.Foreground = self.C_WHITE
        badge_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
        badge_txt.VerticalAlignment = SW.VerticalAlignment.Center
        badge.Child = badge_txt
        overlay.Children.Add(badge)

        cartao.Child = overlay

        def _alternar(sender, args):
            novo_estado = entrada.path not in self.selecionadas_paths
            if novo_estado:
                self.selecionadas_paths[entrada.path] = entrada
            else:
                del self.selecionadas_paths[entrada.path]

            cartao.BorderBrush = self.C_ACCENT if novo_estado else self.C_BORDER
            cartao.BorderThickness = SW.Thickness(2 if novo_estado else 1)
            if icone_txt is not None:
                # Sem preview real (monograma): tile e texto acompanham a
                # seleção. Com preview real, a imagem cobre o tile inteiro —
                # a borda do cartão e o selo no canto já comunicam a seleção.
                icone_tile.Background = self.C_ACCENT_TINT if novo_estado else self.C_BG3
                icone_txt.Foreground = self.C_ACCENT if novo_estado else self.C_TEXT3
            badge.Visibility = SW.Visibility.Visible if novo_estado else SW.Visibility.Collapsed
            self._atualizar_status()

        cartao.MouseLeftButtonDown += SWI.MouseButtonEventHandler(_alternar)

        return cartao

    def _atualizar_lista(self, sender=None, args=None):
        self.PlaceholderBusca.Visibility = (
            SW.Visibility.Collapsed if self.TxtBusca.Text else SW.Visibility.Visible
        )

        self.ListaPanel.Children.Clear()
        secoes = self._secoes_visiveis()

        if not secoes:
            vazio = SWC.TextBlock()
            vazio.Text = (
                u"Nenhuma família encontrada na biblioteca."
                if not self.todas_entradas
                else u"Nenhuma família encontrada com esse filtro."
            )
            vazio.Foreground = self.C_TEXT3
            vazio.FontSize = 12
            vazio.TextWrapping = SW.TextWrapping.Wrap
            vazio.Margin = SW.Thickness(4, 20, 0, 0)
            self.ListaPanel.Children.Add(vazio)
        else:
            primeira = True
            for categoria, entradas_categoria in secoes:
                secao_header = SWC.TextBlock()
                secao_header.Text = u"{}   ({})".format(categoria, len(entradas_categoria))
                secao_header.FontSize = 12
                secao_header.FontWeight = SW.FontWeights.SemiBold
                secao_header.Foreground = self.C_TEXT2
                secao_header.Margin = SW.Thickness(0, 0 if primeira else 16, 0, 10)
                self.ListaPanel.Children.Add(secao_header)
                primeira = False

                grade = SWC.WrapPanel()
                grade.Orientation = SWC.Orientation.Horizontal
                for entrada in entradas_categoria:
                    grade.Children.Add(self._criar_cartao_familia(entrada))
                self.ListaPanel.Children.Add(grade)

        self._atualizar_status()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _atualizar_status(self):
        total = len(self.todas_entradas)
        visiveis = len(self._entradas_filtradas())
        marcadas = len(self.selecionadas_paths)
        self.LblStatus.Text = u"{} selecionada(s)   ·   {} exibida(s) de {} no total".format(
            marcadas, visiveis, total
        )

    # ------------------------------------------------------------------
    # Handlers — referenciados por nome no XAML (Click="...", TextChanged="...")
    # ------------------------------------------------------------------
    def on_busca_changed(self, sender, args):
        self._atualizar_lista()

    def on_atualizar_pasta(self, sender, args):
        self.todas_entradas[:] = listar_familias()

        caminhos_atuais = set(e.path for e in self.todas_entradas)
        for caminho_antigo in list(self.selecionadas_paths.keys()):
            if caminho_antigo not in caminhos_atuais:
                del self.selecionadas_paths[caminho_antigo]

        self._reconstruir_categorias()
        self._atualizar_lista()

    def on_marcar_todos(self, sender, args):
        for entrada in self._entradas_filtradas():
            self.selecionadas_paths[entrada.path] = entrada
        self._atualizar_lista()

    def on_desmarcar_todos(self, sender, args):
        for entrada in self._entradas_filtradas():
            if entrada.path in self.selecionadas_paths:
                del self.selecionadas_paths[entrada.path]
        self._atualizar_lista()

    def on_fechar(self, sender, args):
        forms.close_dockable_panel(PainelCarregadorFamilias)

    def on_carregar(self, sender, args):
        if not self.selecionadas_paths:
            return

        entradas_para_carregar = list(self.selecionadas_paths.values())

        def _acao(uiapp_exec):
            uidoc_ativo = uiapp_exec.ActiveUIDocument
            if uidoc_ativo is None:
                print(u"[AVISO] Nenhum documento ativo para carregar as famílias.")
                return
            _carregar_familias_silenciosamente(uidoc_ativo.Document, entradas_para_carregar)

        self.fila_acoes.enfileirar(_acao)

    def on_carregar_posicionar(self, sender, args):
        if not self.selecionadas_paths:
            return

        entradas_para_carregar = list(self.selecionadas_paths.values())

        def _acao(uiapp_exec):
            uidoc_ativo = uiapp_exec.ActiveUIDocument
            if uidoc_ativo is None:
                print(u"[AVISO] Nenhum documento ativo para carregar as famílias.")
                return
            doc = uidoc_ativo.Document

            carregadas, ja_existentes, _erros = _carregar_familias_silenciosamente(
                doc, entradas_para_carregar
            )
            nomes_prontos = set(carregadas) | set(ja_existentes)

            forms.close_dockable_panel(PainelCarregadorFamilias)

            for entrada in entradas_para_carregar:
                if entrada.name not in nomes_prontos:
                    continue
                simbolo = obter_symbol_para_posicionar(doc, entrada.name)
                if simbolo is None:
                    continue
                try:
                    uidoc_ativo.PromptForFamilyInstancePlacement(simbolo)
                except Exception:
                    break  # Esc pressionado — encerra o posicionamento

        self.fila_acoes.enfileirar(_acao)


# ---------------------------------------------------------------------------
# Entrada pública — chamada pelo botão da faixa de opções
# ---------------------------------------------------------------------------
def alternar_painel(uiapp):
    """
    Mostra/esconde o Carregador de Famílias como Dockable Pane (painel de
    encaixe) — fica acoplado à interface do Revit (ou flutuando) sem travar
    o app, então dá pra continuar clicando/editando o projeto com ele
    visível. Um novo clique no botão da faixa de opções alterna entre
    mostrar e esconder o mesmo painel (com filtro/seleção intactos), em vez
    de abrir uma nova janela.

    Se o painel não foi registrado com sucesso no startup da extensão
    (ambiente WPF divergente, XAML inválido etc.), cai para o formulário
    padrão do pyRevit (forms.SelectFromList), modal, pontual.

    Com nenhum projeto aberto (ex.: tela inicial do Revit), a API às vezes
    reporta o painel como registrado mas ainda não "criado" de fato —
    GetDockablePane lança Autodesk.Revit.Exceptions.ArgumentException nesse
    caso. Como não travar o Revit com um traceback cru, tratamos isso com um
    aviso pedindo pra abrir um projeto antes.
    """
    if not forms.is_registered_dockable_panel(PainelCarregadorFamilias):
        print(
            u"[AVISO] Dockable Pane do Carregador de Famílias não foi "
            u"registrado no startup da extensão; usando formulário padrão "
            u"do pyRevit (modal)."
        )
        uidoc_ativo = uiapp.ActiveUIDocument
        if uidoc_ativo is not None:
            _mostrar_fallback(uidoc_ativo.Document, listar_familias())
        return

    if uiapp.ActiveUIDocument is None:
        forms.alert(
            u"Abra ou crie um projeto no Revit antes de abrir o Carregador "
            u"de Famílias.",
            title=u"Fire Utils - Carregador de Famílias",
            warn_icon=True,
        )
        return

    try:
        painel = forms.get_dockable_panel(PainelCarregadorFamilias)
        if painel.IsShown():
            painel.Hide()
        else:
            painel.Show()
    except Exception as ex:
        forms.alert(
            u"Não foi possível abrir o painel do Carregador de Famílias "
            u"agora ({}).\n\nTente novamente; se persistir, reinicie o "
            u"Revit.".format(ex),
            title=u"Fire Utils - Carregador de Famílias",
            warn_icon=True,
        )
