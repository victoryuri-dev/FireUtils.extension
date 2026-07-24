# -*- coding: utf-8 -*-
"""
family_loader_forms.py — Fire Utils · lib/
Janela WPF customizada (identidade visual Fire Utils — escura, com destaque
vermelho) para o Carregador de Famílias, em formato de catálogo: pesquisa por
texto, categorias em destaque, cartões de família selecionáveis por clique e
carregamento em lote no documento ativo.

A janela é modeless (fica aberta sem travar o Revit) e é reaproveitada entre
uma abertura e outra via cache de sessão do pyRevit (script.get_envvar) — um
novo clique no botão só traz a janela existente para frente, sem reconstruir
nada. Como a janela pode ficar aberta enquanto o usuário trabalha no Revit,
qualquer ação que precise da API (carregar família, gerar thumbnail) é
despachada através de um ExternalEvent (family_loader_events.py), nunca
chamada diretamente a partir de um clique.

Se a interface customizada falhar por qualquer motivo (ambiente WPF
divergente, etc.), o módulo cai automaticamente para o formulário padrão do
pyRevit (forms.SelectFromList), que já é funcional e testado — nesse caso a
janela volta a ser modal.
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
from System.Windows.Interop import WindowInteropHelper

from pyrevit import forms, script

from family_loader import listar_familias, listar_categorias, carregar_familias
from family_thumbnails import obter_thumb_cacheada, gerar_thumb
from family_loader_events import criar_fila_acoes

_CHAVE_JANELA = u"FireUtils_CarregadorFamilias_Janela"
_CHAVE_FILA = u"FireUtils_CarregadorFamilias_Fila"

_TODAS = u"Todas"

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))

# Ordem de preferência para a logo do cabeçalho. O primeiro arquivo
# encontrado é usado; se nenhum existir, mostra-se um espaço reservado.
_LOGO_CANDIDATOS = [
    os.path.join(_LIB_DIR, u"assets", u"logo.png"),
    os.path.join(_LIB_DIR, u"assets", u"etos-logo-hor.png"),
    os.path.join(_LIB_DIR, u"assets", u"etos-logo-vert.png"),
]


# ---------------------------------------------------------------------------
# Paleta — identidade Fire Utils (fundo escuro + vermelho de destaque)
# ---------------------------------------------------------------------------
def _cor(r, g, b):
    return SWM.SolidColorBrush(SWM.Color.FromRgb(r, g, b))


def _cor_alfa(a, r, g, b):
    return SWM.SolidColorBrush(SWM.Color.FromArgb(a, r, g, b))


C_BG          = _cor(18,  18,  20)
C_BG2         = _cor(28,  29,  33)
C_BG3         = _cor(38,  39,  44)
C_BORDER      = _cor(52,  54,  60)
C_BORDER2     = _cor(70,  72,  80)
C_TEXT        = _cor(240, 240, 242)
C_TEXT2       = _cor(162, 165, 172)
C_TEXT3       = _cor(112, 115, 124)
C_ACCENT      = _cor(224, 58,  46)
C_ACCENT_TINT = _cor_alfa(50, 224, 58, 46)
C_WHITE       = _cor(255, 255, 255)
C_TRANSPARENT = SWM.Brushes.Transparent


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


# ---------------------------------------------------------------------------
# Resumo de carregamento (compartilhado entre a UI custom e o fallback)
# ---------------------------------------------------------------------------
def _carregar_e_avisar(doc, entradas_selecionadas):
    carregadas, ja_existentes, erros = carregar_familias(doc, entradas_selecionadas)

    linhas = []
    if carregadas:
        linhas.append(u"Carregadas ({}):".format(len(carregadas)))
        linhas.extend(u"  - {}".format(n) for n in carregadas)
    if ja_existentes:
        linhas.append(u"")
        linhas.append(u"Já existiam no projeto ({}):".format(len(ja_existentes)))
        linhas.extend(u"  - {}".format(n) for n in ja_existentes)
    if erros:
        linhas.append(u"")
        linhas.append(u"Falhas ({}):".format(len(erros)))
        linhas.extend(u"  - {}: {}".format(nome, msg) for nome, msg in erros)

    forms.alert(
        u"\n".join(linhas) if linhas else u"Nada foi carregado.",
        title=u"Fire Utils - Carregador de Famílias",
    )


# ---------------------------------------------------------------------------
# Fallback — formulário padrão do pyRevit (já testado e funcional)
# ---------------------------------------------------------------------------
def _mostrar_fallback(doc, entradas):
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

    _carregar_e_avisar(doc, selecionadas)


# ---------------------------------------------------------------------------
# Interface customizada — catálogo (modeless)
# ---------------------------------------------------------------------------
def _construir_janela(uiapp, entradas_iniciais):
    todas_entradas = list(entradas_iniciais)
    selecionadas_paths = {}    # path -> FamilyEntry
    categoria_atual = [_TODAS]
    tiles_categoria = {}       # categoria -> (icone_border, icone_txt, rotulo)
    cartoes_pendentes = {}     # path -> (icone_tile_border, [icone_txt_ou_None])
    geracao_atual = [0]        # token — invalida filas de thumb de filtros antigos

    fila_acoes = criar_fila_acoes()

    # ------------------------------------------------------------------
    # Janela e grid raiz
    # ------------------------------------------------------------------
    win = SW.Window()
    win.Title = u"Fire Utils — Carregador de Famílias"
    win.Width = 760
    win.Height = 700
    win.MinWidth = 600
    win.MinHeight = 480
    win.Background = C_BG
    win.ResizeMode = SW.ResizeMode.CanResize
    win.WindowStartupLocation = SW.WindowStartupLocation.CenterScreen
    win.ShowInTaskbar = True

    try:
        WindowInteropHelper(win).Owner = uiapp.MainWindowHandle
    except Exception:
        pass  # Owner é só um refinamento; segue sem ele se não disponível

    root = SWC.Grid()
    root.Margin = SW.Thickness(26, 22, 26, 20)
    win.Content = root

    _AUTO = SW.GridLength(SW.GridLength.Auto.Value, SW.GridUnitType.Auto)
    _STAR = SW.GridLength(1, SW.GridUnitType.Star)
    for altura in (_AUTO, _AUTO, _AUTO, _STAR, _AUTO, _AUTO):
        rd = SWC.RowDefinition()
        rd.Height = altura
        root.RowDefinitions.Add(rd)

    # ------------------------------------------------------------------
    # Cabeçalho — logo (espaço reservado) + títulos
    # ------------------------------------------------------------------
    header = SWC.Grid()
    header.Margin = SW.Thickness(0, 0, 0, 18)
    col_logo = SWC.ColumnDefinition()
    col_logo.Width = _AUTO
    col_titulos = SWC.ColumnDefinition()
    col_titulos.Width = _STAR
    header.ColumnDefinitions.Add(col_logo)
    header.ColumnDefinitions.Add(col_titulos)

    logo_border = SWC.Border()
    logo_border.Width = 170
    logo_border.Height = 48
    logo_border.CornerRadius = SW.CornerRadius(8)
    logo_border.Background = C_BG2
    logo_border.BorderBrush = C_BORDER
    logo_border.BorderThickness = SW.Thickness(1)
    logo_border.Margin = SW.Thickness(0, 0, 18, 0)

    logo_bitmap = _localizar_logo()
    if logo_bitmap is not None:
        logo_img = SWC.Image()
        logo_img.Source = logo_bitmap
        logo_img.Stretch = SWM.Stretch.Uniform
        logo_img.Margin = SW.Thickness(10, 8, 10, 8)
        logo_border.Child = logo_img
    else:
        logo_placeholder = SWC.TextBlock()
        logo_placeholder.Text = u"LOGO"
        logo_placeholder.FontSize = 10
        logo_placeholder.FontWeight = SW.FontWeights.SemiBold
        logo_placeholder.Foreground = C_TEXT3
        logo_placeholder.HorizontalAlignment = SW.HorizontalAlignment.Center
        logo_placeholder.VerticalAlignment = SW.VerticalAlignment.Center
        logo_border.Child = logo_placeholder

    SWC.Grid.SetColumn(logo_border, 0)
    header.Children.Add(logo_border)

    titulos_panel = SWC.StackPanel()
    titulos_panel.VerticalAlignment = SW.VerticalAlignment.Center
    SWC.Grid.SetColumn(titulos_panel, 1)

    eyebrow = SWC.TextBlock()
    eyebrow.Text = u"FIRE UTILS   ·   BIBLIOTECA"
    eyebrow.FontSize = 10
    eyebrow.FontWeight = SW.FontWeights.SemiBold
    eyebrow.Foreground = C_ACCENT
    eyebrow.Margin = SW.Thickness(0, 0, 0, 4)
    titulos_panel.Children.Add(eyebrow)

    titulo = SWC.TextBlock()
    titulo.Text = u"Carregador de Famílias"
    titulo.FontSize = 22
    titulo.FontWeight = SW.FontWeights.Light
    titulo.Foreground = C_TEXT
    titulos_panel.Children.Add(titulo)

    subtitulo = SWC.TextBlock()
    subtitulo.Text = u"Combate a incêndio — pesquise, filtre por categoria e carregue no projeto"
    subtitulo.FontSize = 11
    subtitulo.Foreground = C_TEXT2
    subtitulo.Margin = SW.Thickness(0, 4, 0, 0)
    titulos_panel.Children.Add(subtitulo)

    header.Children.Add(titulos_panel)
    SWC.Grid.SetRow(header, 0)
    root.Children.Add(header)

    # ------------------------------------------------------------------
    # Busca — barra arredondada com ícone
    # ------------------------------------------------------------------
    search_container = SWC.Border()
    search_container.Background = C_BG2
    search_container.BorderBrush = C_BORDER
    search_container.BorderThickness = SW.Thickness(1)
    search_container.CornerRadius = SW.CornerRadius(18)
    search_container.Padding = SW.Thickness(14, 0, 14, 0)
    search_container.Height = 38
    search_container.Margin = SW.Thickness(0, 0, 0, 18)

    search_grid = SWC.Grid()
    col_icone = SWC.ColumnDefinition()
    col_icone.Width = _AUTO
    col_txt = SWC.ColumnDefinition()
    col_txt.Width = _STAR
    search_grid.ColumnDefinitions.Add(col_icone)
    search_grid.ColumnDefinitions.Add(col_txt)

    search_icone = SWC.TextBlock()
    search_icone.Text = u"⌕"
    search_icone.FontSize = 15
    search_icone.FontWeight = SW.FontWeights.Bold
    search_icone.Foreground = C_TEXT3
    search_icone.VerticalAlignment = SW.VerticalAlignment.Center
    search_icone.Margin = SW.Thickness(0, 0, 10, 0)
    SWC.Grid.SetColumn(search_icone, 0)
    search_grid.Children.Add(search_icone)

    txt_overlay = SWC.Grid()
    SWC.Grid.SetColumn(txt_overlay, 1)

    txt_busca = SWC.TextBox()
    txt_busca.Background = C_TRANSPARENT
    txt_busca.Foreground = C_TEXT
    txt_busca.BorderThickness = SW.Thickness(0)
    txt_busca.FontSize = 12
    txt_busca.VerticalContentAlignment = SW.VerticalAlignment.Center
    txt_busca.CaretBrush = C_TEXT

    placeholder_busca = SWC.TextBlock()
    placeholder_busca.Text = u"Pesquisar famílias..."
    placeholder_busca.Foreground = C_TEXT3
    placeholder_busca.FontSize = 12
    placeholder_busca.IsHitTestVisible = False
    placeholder_busca.VerticalAlignment = SW.VerticalAlignment.Center

    txt_overlay.Children.Add(placeholder_busca)
    txt_overlay.Children.Add(txt_busca)
    search_grid.Children.Add(txt_overlay)

    search_container.Child = search_grid
    SWC.Grid.SetRow(search_container, 1)
    root.Children.Add(search_container)

    # ------------------------------------------------------------------
    # Categorias — cabeçalho (rótulo + atualizar) e tiles com ícone
    # ------------------------------------------------------------------
    categorias_container = SWC.StackPanel()
    categorias_container.Margin = SW.Thickness(0, 0, 0, 18)

    cat_header_grid = SWC.Grid()
    cat_header_grid.Margin = SW.Thickness(0, 0, 0, 10)
    col_lbl = SWC.ColumnDefinition()
    col_lbl.Width = _STAR
    col_btn = SWC.ColumnDefinition()
    col_btn.Width = _AUTO
    cat_header_grid.ColumnDefinitions.Add(col_lbl)
    cat_header_grid.ColumnDefinitions.Add(col_btn)

    categorias_label = SWC.TextBlock()
    categorias_label.Text = u"CATEGORIAS"
    categorias_label.FontSize = 10
    categorias_label.FontWeight = SW.FontWeights.SemiBold
    categorias_label.Foreground = C_TEXT3
    categorias_label.VerticalAlignment = SW.VerticalAlignment.Center
    SWC.Grid.SetColumn(categorias_label, 0)
    cat_header_grid.Children.Add(categorias_label)

    btn_atualizar = SWC.Button()
    btn_atualizar.Content = u"↻  Atualizar pasta"
    btn_atualizar.FontSize = 10
    btn_atualizar.Foreground = C_ACCENT
    btn_atualizar.Background = C_TRANSPARENT
    btn_atualizar.BorderThickness = SW.Thickness(0)
    btn_atualizar.Padding = SW.Thickness(0)
    btn_atualizar.Cursor = SWI.Cursors.Hand
    SWC.Grid.SetColumn(btn_atualizar, 1)
    cat_header_grid.Children.Add(btn_atualizar)

    categorias_container.Children.Add(cat_header_grid)

    tiles_panel = SWC.WrapPanel()
    tiles_panel.Orientation = SWC.Orientation.Horizontal
    categorias_container.Children.Add(tiles_panel)

    SWC.Grid.SetRow(categorias_container, 2)
    root.Children.Add(categorias_container)

    def _icone_categoria(nome_categoria):
        if nome_categoria == _TODAS:
            return u"▦"
        limpo = nome_categoria.strip()
        return limpo[0].upper() if limpo else u"?"

    def _estilizar_tile(nome_categoria, ativo):
        icone_border, icone_txt, rotulo = tiles_categoria[nome_categoria]
        icone_border.Background = C_ACCENT if ativo else C_BG2
        icone_border.BorderBrush = C_ACCENT if ativo else C_BORDER
        icone_txt.Foreground = C_WHITE if ativo else C_TEXT2
        rotulo.Foreground = C_ACCENT if ativo else C_TEXT2
        rotulo.FontWeight = SW.FontWeights.SemiBold if ativo else SW.FontWeights.Normal

    def _criar_tile_categoria(nome_categoria):
        ativo = (nome_categoria == categoria_atual[0])

        externo = SWC.StackPanel()
        externo.Margin = SW.Thickness(0, 0, 18, 10)
        externo.Width = 68
        externo.Cursor = SWI.Cursors.Hand
        externo.Background = C_TRANSPARENT  # garante hit-test em toda a área

        icone_border = SWC.Border()
        icone_border.Width = 48
        icone_border.Height = 48
        icone_border.CornerRadius = SW.CornerRadius(24)
        icone_border.HorizontalAlignment = SW.HorizontalAlignment.Center
        icone_border.BorderThickness = SW.Thickness(1)
        icone_border.Background = C_ACCENT if ativo else C_BG2
        icone_border.BorderBrush = C_ACCENT if ativo else C_BORDER

        icone_txt = SWC.TextBlock()
        icone_txt.Text = _icone_categoria(nome_categoria)
        icone_txt.FontSize = 16
        icone_txt.FontWeight = SW.FontWeights.SemiBold
        icone_txt.Foreground = C_WHITE if ativo else C_TEXT2
        icone_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
        icone_txt.VerticalAlignment = SW.VerticalAlignment.Center
        icone_border.Child = icone_txt

        rotulo = SWC.TextBlock()
        rotulo.Text = nome_categoria
        rotulo.FontSize = 10
        rotulo.Foreground = C_ACCENT if ativo else C_TEXT2
        rotulo.FontWeight = SW.FontWeights.SemiBold if ativo else SW.FontWeights.Normal
        rotulo.TextAlignment = SW.TextAlignment.Center
        rotulo.TextWrapping = SW.TextWrapping.Wrap
        rotulo.Margin = SW.Thickness(0, 6, 0, 0)

        externo.Children.Add(icone_border)
        externo.Children.Add(rotulo)

        return externo, icone_border, icone_txt, rotulo

    def _on_tile_click(nome_categoria):
        def _handler(sender, args):
            categoria_atual[0] = nome_categoria
            for outro_nome in tiles_categoria:
                _estilizar_tile(outro_nome, outro_nome == nome_categoria)
            _atualizar_lista()
        return _handler

    def _reconstruir_categorias():
        tiles_panel.Children.Clear()
        tiles_categoria.clear()
        categoria_atual[0] = _TODAS

        nomes = [_TODAS] + listar_categorias(todas_entradas)
        for nome in nomes:
            externo, icone_border, icone_txt, rotulo = _criar_tile_categoria(nome)
            tiles_categoria[nome] = (icone_border, icone_txt, rotulo)
            externo.MouseLeftButtonDown += SWI.MouseButtonEventHandler(_on_tile_click(nome))
            tiles_panel.Children.Add(externo)

    # ------------------------------------------------------------------
    # Catálogo — seções por categoria, cartões em grade
    # ------------------------------------------------------------------
    scroll = SWC.ScrollViewer()
    scroll.VerticalScrollBarVisibility = SWC.ScrollBarVisibility.Auto
    scroll.Padding = SW.Thickness(0, 0, 6, 0)

    lista_panel = SWC.StackPanel()
    scroll.Content = lista_panel

    SWC.Grid.SetRow(scroll, 3)
    root.Children.Add(scroll)

    def _secoes_visiveis():
        texto = (txt_busca.Text or u"").strip().lower()
        categoria_filtro = categoria_atual[0]

        por_categoria = {}
        for entrada in todas_entradas:
            if categoria_filtro != _TODAS and entrada.category != categoria_filtro:
                continue
            if texto and texto not in entrada.name.lower():
                continue
            por_categoria.setdefault(entrada.category, []).append(entrada)

        for lista_cat in por_categoria.values():
            lista_cat.sort(key=lambda e: e.name)

        return sorted(por_categoria.items())

    def _entradas_filtradas():
        resultado = []
        for _categoria, entradas_categoria in _secoes_visiveis():
            resultado.extend(entradas_categoria)
        return resultado

    def _criar_cartao_familia(entrada):
        selecionado = entrada.path in selecionadas_paths

        cartao = SWC.Border()
        cartao.Width = 138
        cartao.Height = 150
        cartao.Background = C_BG2
        cartao.BorderBrush = C_ACCENT if selecionado else C_BORDER
        cartao.BorderThickness = SW.Thickness(2 if selecionado else 1)
        cartao.CornerRadius = SW.CornerRadius(10)
        cartao.Padding = SW.Thickness(10)
        cartao.Margin = SW.Thickness(0, 0, 12, 12)
        cartao.Cursor = SWI.Cursors.Hand

        overlay = SWC.Grid()

        conteudo = SWC.StackPanel()

        icone_tile = SWC.Border()
        icone_tile.Height = 78
        icone_tile.CornerRadius = SW.CornerRadius(8)
        icone_tile.ClipToBounds = True
        icone_tile.Background = C_ACCENT_TINT if selecionado else C_BG3

        # icone_txt_ref[0] é None quando o cartão já mostra a miniatura real
        # (usado por _alternar para saber se ainda deve tingir o monograma).
        icone_txt_ref = [None]

        thumb_cacheada = obter_thumb_cacheada(entrada.path)
        thumb_bitmap = _carregar_bitmap(thumb_cacheada) if thumb_cacheada else None

        if thumb_bitmap is not None:
            thumb_img = SWC.Image()
            thumb_img.Source = thumb_bitmap
            thumb_img.Stretch = SWM.Stretch.UniformToFill
            icone_tile.Child = thumb_img
        else:
            icone_txt = SWC.TextBlock()
            icone_txt.Text = _monograma(entrada.name)
            icone_txt.FontSize = 22
            icone_txt.FontWeight = SW.FontWeights.Bold
            icone_txt.Foreground = C_ACCENT if selecionado else C_TEXT3
            icone_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
            icone_txt.VerticalAlignment = SW.VerticalAlignment.Center
            icone_tile.Child = icone_txt
            icone_txt_ref[0] = icone_txt
            cartoes_pendentes[entrada.path] = (icone_tile, icone_txt_ref)

        conteudo.Children.Add(icone_tile)

        nome_txt = SWC.TextBlock()
        nome_txt.Text = entrada.name
        nome_txt.FontSize = 11
        nome_txt.FontWeight = SW.FontWeights.SemiBold
        nome_txt.Foreground = C_TEXT
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
        badge.Background = C_ACCENT
        badge.HorizontalAlignment = SW.HorizontalAlignment.Right
        badge.VerticalAlignment = SW.VerticalAlignment.Top
        badge.Margin = SW.Thickness(0, -4, -4, 0)
        badge.Visibility = SW.Visibility.Visible if selecionado else SW.Visibility.Collapsed

        badge_txt = SWC.TextBlock()
        badge_txt.Text = u"✓"
        badge_txt.FontSize = 10
        badge_txt.FontWeight = SW.FontWeights.Bold
        badge_txt.Foreground = C_WHITE
        badge_txt.HorizontalAlignment = SW.HorizontalAlignment.Center
        badge_txt.VerticalAlignment = SW.VerticalAlignment.Center
        badge.Child = badge_txt
        overlay.Children.Add(badge)

        cartao.Child = overlay

        def _alternar(sender, args):
            novo_estado = entrada.path not in selecionadas_paths
            if novo_estado:
                selecionadas_paths[entrada.path] = entrada
            else:
                del selecionadas_paths[entrada.path]

            cartao.BorderBrush = C_ACCENT if novo_estado else C_BORDER
            cartao.BorderThickness = SW.Thickness(2 if novo_estado else 1)
            if icone_txt_ref[0] is not None:
                icone_tile.Background = C_ACCENT_TINT if novo_estado else C_BG3
                icone_txt_ref[0].Foreground = C_ACCENT if novo_estado else C_TEXT3
            badge.Visibility = SW.Visibility.Visible if novo_estado else SW.Visibility.Collapsed
            _atualizar_status()

        cartao.MouseLeftButtonDown += SWI.MouseButtonEventHandler(_alternar)

        return cartao

    def _aplicar_thumb_no_cartao(caminho, destino):
        visual = cartoes_pendentes.get(caminho)
        if visual is None:
            return
        icone_tile, icone_txt_ref = visual
        bmp = _carregar_bitmap(destino)
        if bmp is None:
            return
        img = SWC.Image()
        img.Source = bmp
        img.Stretch = SWM.Stretch.UniformToFill
        icone_tile.Child = img
        icone_txt_ref[0] = None

    def _enfileirar_geracao_thumb(caminho, token):
        def _acao(uiapp_exec):
            if token != geracao_atual[0]:
                return  # filtro/categoria mudou nesse meio tempo; descarta
            destino = gerar_thumb(uiapp_exec.Application, caminho)
            if token == geracao_atual[0] and destino:
                _aplicar_thumb_no_cartao(caminho, destino)

        fila_acoes.enfileirar(_acao)

    def _atualizar_lista(sender=None, args=None):
        placeholder_busca.Visibility = (
            SW.Visibility.Collapsed if txt_busca.Text else SW.Visibility.Visible
        )

        geracao_atual[0] += 1
        token = geracao_atual[0]
        cartoes_pendentes.clear()

        lista_panel.Children.Clear()
        secoes = _secoes_visiveis()

        if not secoes:
            vazio = SWC.TextBlock()
            vazio.Text = u"Nenhuma família encontrada com esse filtro."
            vazio.Foreground = C_TEXT3
            vazio.FontSize = 12
            vazio.Margin = SW.Thickness(4, 20, 0, 0)
            lista_panel.Children.Add(vazio)
        else:
            primeira = True
            for categoria, entradas_categoria in secoes:
                secao_header = SWC.TextBlock()
                secao_header.Text = u"{}   ({})".format(categoria, len(entradas_categoria))
                secao_header.FontSize = 12
                secao_header.FontWeight = SW.FontWeights.SemiBold
                secao_header.Foreground = C_TEXT2
                secao_header.Margin = SW.Thickness(0, 0 if primeira else 16, 0, 10)
                lista_panel.Children.Add(secao_header)
                primeira = False

                grade = SWC.WrapPanel()
                grade.Orientation = SWC.Orientation.Horizontal
                for entrada in entradas_categoria:
                    grade.Children.Add(_criar_cartao_familia(entrada))
                lista_panel.Children.Add(grade)

        _atualizar_status()

        for caminho_pendente in list(cartoes_pendentes.keys()):
            _enfileirar_geracao_thumb(caminho_pendente, token)

    # ------------------------------------------------------------------
    # Status + ações
    # ------------------------------------------------------------------
    lbl_status = SWC.TextBlock()
    lbl_status.FontSize = 11
    lbl_status.Foreground = C_TEXT3
    lbl_status.Margin = SW.Thickness(0, 10, 0, 10)
    SWC.Grid.SetRow(lbl_status, 4)
    root.Children.Add(lbl_status)

    def _atualizar_status():
        total = len(todas_entradas)
        visiveis = len(_entradas_filtradas())
        marcadas = len(selecionadas_paths)
        lbl_status.Text = u"{} selecionada(s)   ·   {} exibida(s) de {} no total".format(
            marcadas, visiveis, total
        )

    def _botao_outline(texto):
        botao = SWC.Button()
        botao.Content = texto
        botao.Height = 32
        botao.Padding = SW.Thickness(14, 0, 14, 0)
        botao.FontSize = 11
        botao.Background = C_BG
        botao.Foreground = C_TEXT2
        botao.BorderBrush = C_BORDER2
        botao.BorderThickness = SW.Thickness(1)
        return botao

    botoes_row = SWC.Grid()
    botoes_row.Margin = SW.Thickness(0, 4, 0, 0)
    col_esq = SWC.ColumnDefinition()
    col_esq.Width = _STAR
    col_dir = SWC.ColumnDefinition()
    col_dir.Width = _AUTO
    botoes_row.ColumnDefinitions.Add(col_esq)
    botoes_row.ColumnDefinitions.Add(col_dir)

    esq_panel = SWC.StackPanel()
    esq_panel.Orientation = SWC.Orientation.Horizontal
    SWC.Grid.SetColumn(esq_panel, 0)

    btn_marcar = _botao_outline(u"Marcar todos (filtrados)")
    btn_desmarcar = _botao_outline(u"Desmarcar todos")
    btn_desmarcar.Margin = SW.Thickness(8, 0, 0, 0)
    esq_panel.Children.Add(btn_marcar)
    esq_panel.Children.Add(btn_desmarcar)
    botoes_row.Children.Add(esq_panel)

    dir_panel = SWC.StackPanel()
    dir_panel.Orientation = SWC.Orientation.Horizontal
    dir_panel.HorizontalAlignment = SW.HorizontalAlignment.Right
    SWC.Grid.SetColumn(dir_panel, 1)

    btn_fechar = _botao_outline(u"Fechar")

    btn_carregar = SWC.Button()
    btn_carregar.Content = u"Carregar selecionadas"
    btn_carregar.Height = 34
    btn_carregar.Padding = SW.Thickness(18, 0, 18, 0)
    btn_carregar.Margin = SW.Thickness(10, 0, 0, 0)
    btn_carregar.FontSize = 12
    btn_carregar.FontWeight = SW.FontWeights.SemiBold
    btn_carregar.Background = C_ACCENT
    btn_carregar.Foreground = C_WHITE
    btn_carregar.BorderThickness = SW.Thickness(0)

    dir_panel.Children.Add(btn_fechar)
    dir_panel.Children.Add(btn_carregar)
    botoes_row.Children.Add(dir_panel)

    SWC.Grid.SetRow(botoes_row, 5)
    root.Children.Add(botoes_row)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _on_atualizar_pasta(sender, args):
        todas_entradas[:] = listar_familias()

        caminhos_atuais = set(e.path for e in todas_entradas)
        for caminho_antigo in list(selecionadas_paths.keys()):
            if caminho_antigo not in caminhos_atuais:
                del selecionadas_paths[caminho_antigo]

        _reconstruir_categorias()
        _atualizar_lista()

    def _on_marcar_todos(sender, args):
        for entrada in _entradas_filtradas():
            selecionadas_paths[entrada.path] = entrada
        _atualizar_lista()

    def _on_desmarcar_todos(sender, args):
        for entrada in _entradas_filtradas():
            if entrada.path in selecionadas_paths:
                del selecionadas_paths[entrada.path]
        _atualizar_lista()

    def _on_fechar(sender, args):
        win.Hide()

    def _on_closing(sender, args):
        # Nunca fecha de verdade — só esconde, pra poder reaproveitar a
        # mesma janela (com filtro/seleção intactos) na próxima abertura.
        args.Cancel = True
        win.Hide()

    def _on_carregar(sender, args):
        if not selecionadas_paths:
            forms.alert(
                u"Selecione ao menos uma família para carregar.",
                title=u"Fire Utils - Carregador de Famílias",
            )
            return

        entradas_para_carregar = list(selecionadas_paths.values())

        def _acao(uiapp_exec):
            uidoc_ativo = uiapp_exec.ActiveUIDocument
            if uidoc_ativo is None:
                print(u"[AVISO] Nenhum documento ativo para carregar as famílias.")
                return
            _carregar_e_avisar(uidoc_ativo.Document, entradas_para_carregar)

        fila_acoes.enfileirar(_acao)

    txt_busca.TextChanged += SWC.TextChangedEventHandler(_atualizar_lista)
    btn_atualizar.Click += SW.RoutedEventHandler(_on_atualizar_pasta)
    btn_marcar.Click += SW.RoutedEventHandler(_on_marcar_todos)
    btn_desmarcar.Click += SW.RoutedEventHandler(_on_desmarcar_todos)
    btn_fechar.Click += SW.RoutedEventHandler(_on_fechar)
    btn_carregar.Click += SW.RoutedEventHandler(_on_carregar)
    win.Closing += _on_closing

    # ------------------------------------------------------------------
    # Estado inicial
    # ------------------------------------------------------------------
    _reconstruir_categorias()
    _atualizar_lista()

    return win, fila_acoes


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------
def obter_ou_criar_janela(uiapp):
    """
    Mostra o Carregador de Famílias como janela modeless — fica aberta sem
    travar o Revit, então você pode continuar clicando/editando o projeto com
    ela aberta. Um novo clique no botão da faixa de opções só traz a mesma
    janela para frente (com o filtro e a seleção de antes intactos), em vez
    de abrir uma nova.
    """
    janela_existente = script.get_envvar(_CHAVE_JANELA)
    if janela_existente is not None:
        try:
            janela_existente.Show()
            janela_existente.Activate()
            return
        except Exception:
            pass  # janela foi descartada por algum motivo; cria uma nova abaixo

    entradas = listar_familias()
    if not entradas:
        forms.alert(
            u"Nenhuma família encontrada na biblioteca.\n\n"
            u"Coloque arquivos .rfa em subpastas de:\n"
            u"Fire Utils.tab/lib/family_library/<Categoria>/",
            title=u"Fire Utils - Carregador de Famílias",
            warn_icon=True,
        )
        return

    try:
        janela, fila_acoes = _construir_janela(uiapp, entradas)
    except Exception as ex:
        print(
            u"[AVISO] Interface modeless do Carregador de Famílias falhou "
            u"({}), usando formulário padrão do pyRevit (modal).".format(ex)
        )
        uidoc_ativo = uiapp.ActiveUIDocument
        if uidoc_ativo is not None:
            _mostrar_fallback(uidoc_ativo.Document, entradas)
        return

    script.set_envvar(_CHAVE_JANELA, janela)
    script.set_envvar(_CHAVE_FILA, fila_acoes)
    janela.Show()
