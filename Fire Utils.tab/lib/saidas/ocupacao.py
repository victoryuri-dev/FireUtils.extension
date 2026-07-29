# -*- coding: utf-8 -*-
# saidas/ocupacao.py — Fire Utils
# Formulário WPF de seleção de ocupação (Grupo → Tipo em cascata).
# Faz parte do módulo de saídas de emergência; dados vêm de estados/<UF>.py.

from pyrevit import forms, script


# =============================================================================
# HELPERS INTERNOS
# =============================================================================

def _opcoes_de_estado(estado):
    """Monta lista 'CODIGO : descrição — obs' a partir do dict de estado."""
    tabela = estado.get(u"tabela", {})
    ocups  = estado.get(u"ocupacoes", {})
    opcoes = []
    for codigo in sorted(tabela.keys()):
        obs  = tabela[codigo].get(u"obs", u"")
        desc = ocups.get(codigo, {}).get(u"descricao", u"")
        if desc:
            opcoes.append(u"{} : {} — {}".format(codigo, desc, obs))
        else:
            opcoes.append(u"{} : {}".format(codigo, obs))
    return opcoes



def _notas_de_estado(estado, codigo):
    """Retorna texto das notas para um código dentro de um estado."""
    tabela = estado.get(u"tabela", {})
    notas  = estado.get(u"notas",  {})
    entry  = tabela.get(codigo, {})
    chaves = entry.get(u"notas", [])
    textos = [notas[ch] for ch in chaves if ch in notas]
    return u"\n\n".join(textos)


# =============================================================================
# FORMULÁRIO LEGADO (fallback) — ask_for_one_item simples
# =============================================================================

def _form_legado(estado):
    """Formato fallback: dropdown simples com os dados do estado."""
    options = _opcoes_de_estado(estado)

    if not options:
        forms.alert(
            u"Nenhuma ocupação disponível para o estado selecionado.",
            title=u"Fire Utils", warn_icon=True
        )
        return script.exit()

    choice = forms.ask_for_one_item(
        options,
        default=options[0],
        prompt=u"Escolha uma ocupação:",
        title=u"Ocupações"
    )
    if not choice:
        return script.exit()

    codigo = choice.split(u" : ")[0].strip()
    notas_txt = _notas_de_estado(estado, codigo)
    if notas_txt:
        forms.alert(notas_txt, title=u"Notas específicas:", warn_icon=True)

    return codigo


# =============================================================================
# FORMULÁRIO WPF — comboboxes em cascata + painel dinâmico
# =============================================================================

def _form_wpf(estado):
    """
    Janela WPF com:
      - ComboBox de Grupo  (agrupado por 'uso' de estado["ocupacoes"])
      - ComboBox de Tipo   (filtrado pelo grupo selecionado)
      - Painel de info     (descrição, taxa, AD/ER/PT por UP)
      - Botões Cancelar / Confirmar
    """
    import clr
    clr.AddReference(u"PresentationFramework")
    clr.AddReference(u"PresentationCore")
    clr.AddReference(u"WindowsBase")
    import System.Windows as SW
    import System.Windows.Controls as SWC
    import System.Windows.Media as SWM

    tabela = estado.get(u"tabela", {})
    ocups  = estado.get(u"ocupacoes", {})

    # --- Montar estrutura de dados agrupada --------------------------------
    # grupos_data: { uso: [ (codigo, desc, obs, ad, er, pt), ... ] }
    grupos_data = {}
    for codigo in sorted(tabela.keys()):
        entry = tabela[codigo]
        ocup  = ocups.get(codigo, {})
        uso   = ocup.get(u"uso", u"Outros")
        desc  = ocup.get(u"descricao", u"")
        obs   = entry.get(u"obs", u"—")
        ad    = str(entry.get(u"AD") or u"—")
        er    = str(entry.get(u"ER") or u"—")
        pt    = str(entry.get(u"PT") or u"—")
        grupos_data.setdefault(uso, []).append((codigo, desc, obs, ad, er, pt))

    usos_lista = sorted(grupos_data.keys())
    resultado  = [None]   # container mutável para capturar resultado no closure

    # --- Cores e estilos ---------------------------------------------------
    COR_BG       = SWM.SolidColorBrush(SWM.Color.FromRgb(245, 245, 245))
    COR_CARD     = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    COR_BORDA    = SWM.SolidColorBrush(SWM.Color.FromRgb(213, 213, 213))
    COR_LABEL    = SWM.SolidColorBrush(SWM.Color.FromRgb(100, 100, 100))
    COR_VALOR    = SWM.SolidColorBrush(SWM.Color.FromRgb(30,  30,  30))
    COR_DESTAQUE = SWM.SolidColorBrush(SWM.Color.FromRgb(216, 59,  1))
    COR_BTN_OK   = SWM.SolidColorBrush(SWM.Color.FromRgb(216, 59,  1))
    COR_BTN_TXT  = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    COR_BTN_CAN  = SWM.SolidColorBrush(SWM.Color.FromRgb(225, 225, 225))

    # --- Janela ------------------------------------------------------------
    win = SW.Window()
    win.Title      = u"Ocupações — {}".format(estado.get(u"nome", u""))
    win.Width      = 460
    win.Height     = 390
    win.Background = COR_BG
    win.WindowStartupLocation = SW.WindowStartupLocation.CenterScreen
    win.ResizeMode = SW.ResizeMode.NoResize

    # --- Layout raiz -------------------------------------------------------
    root = SWC.StackPanel()
    root.Margin = SW.Thickness(18, 14, 18, 14)

    def _label(texto, bold=False):
        tb = SWC.TextBlock()
        tb.Text       = texto
        tb.FontSize   = 11
        tb.Foreground = COR_LABEL
        tb.Margin     = SW.Thickness(0, 0, 0, 3)
        if bold:
            tb.FontWeight = SW.FontWeights.SemiBold
        return tb

    def _combo(margin_bottom=10):
        cb = SWC.ComboBox()
        cb.Margin    = SW.Thickness(0, 0, 0, margin_bottom)
        cb.FontSize  = 12
        cb.Height    = 28
        return cb

    # --- Grupo -------------------------------------------------------------
    root.Children.Add(_label(u"Grupo"))
    cb_grupo = _combo(margin_bottom=10)
    for uso in usos_lista:
        item         = SWC.ComboBoxItem()
        item.Content = uso
        cb_grupo.Items.Add(item)
    if usos_lista:
        cb_grupo.SelectedIndex = 0
    root.Children.Add(cb_grupo)

    # --- Tipo --------------------------------------------------------------
    root.Children.Add(_label(u"Tipo"))
    cb_tipo = _combo(margin_bottom=12)
    root.Children.Add(cb_tipo)

    # --- Card de informações -----------------------------------------------
    borda = SWC.Border()
    borda.Background       = COR_CARD
    borda.BorderBrush      = COR_BORDA
    borda.BorderThickness  = SW.Thickness(1)
    borda.CornerRadius     = SW.CornerRadius(5)
    borda.Padding          = SW.Thickness(12, 10, 12, 10)
    borda.Margin           = SW.Thickness(0, 0, 0, 14)

    info = SWC.StackPanel()

    # Descrição
    txt_desc = SWC.TextBlock()
    txt_desc.FontSize     = 12
    txt_desc.FontWeight   = SW.FontWeights.SemiBold
    txt_desc.Foreground   = COR_VALOR
    txt_desc.TextWrapping = SW.TextWrapping.Wrap
    txt_desc.Margin       = SW.Thickness(0, 0, 0, 6)
    info.Children.Add(txt_desc)

    # Taxa
    txt_taxa = SWC.TextBlock()
    txt_taxa.FontSize     = 11
    txt_taxa.Foreground   = COR_LABEL
    txt_taxa.TextWrapping = SW.TextWrapping.Wrap
    txt_taxa.Margin       = SW.Thickness(0, 0, 0, 8)
    info.Children.Add(txt_taxa)

    # Linha separadora fina
    sep = SWC.Separator()
    sep.Margin = SW.Thickness(0, 0, 0, 8)
    info.Children.Add(sep)

    # Grid AD / ER / PT
    caps_grid = SWC.Grid()
    for _ in range(3):
        col = SWC.ColumnDefinition()
        caps_grid.ColumnDefinitions.Add(col)
    for _ in range(2):
        row = SWC.RowDefinition()
        row.Height = SW.GridLength(SW.GridLength.Auto.Value, SW.GridUnitType.Auto)
        caps_grid.RowDefinitions.Add(row)

    def _cell(texto, row, col, cor=None, bold=False, size=10):
        tb = SWC.TextBlock()
        tb.Text          = texto
        tb.FontSize      = size
        tb.TextAlignment = SW.TextAlignment.Center
        tb.Foreground    = cor or COR_LABEL
        if bold:
            tb.FontWeight = SW.FontWeights.SemiBold
        SWC.Grid.SetRow(tb,    row)
        SWC.Grid.SetColumn(tb, col)
        caps_grid.Children.Add(tb)
        return tb

    _cell(u"AD / UP", 0, 0)
    _cell(u"ER / UP", 0, 1)
    _cell(u"PT / UP", 0, 2)

    txt_ad = _cell(u"—", 1, 0, cor=COR_DESTAQUE, bold=True, size=13)
    txt_er = _cell(u"—", 1, 1, cor=COR_DESTAQUE, bold=True, size=13)
    txt_pt = _cell(u"—", 1, 2, cor=COR_DESTAQUE, bold=True, size=13)

    info.Children.Add(caps_grid)
    borda.Child = info
    root.Children.Add(borda)

    # --- Botões ------------------------------------------------------------
    btn_row = SWC.StackPanel()
    btn_row.Orientation         = SWC.Orientation.Horizontal
    btn_row.HorizontalAlignment = SW.HorizontalAlignment.Right

    def _btn(texto, bg, fg, is_default=False):
        b = SWC.Button()
        b.Content         = texto
        b.Width           = 100
        b.Height          = 30
        b.FontSize        = 12
        b.Margin          = SW.Thickness(6, 0, 0, 0)
        b.Background      = bg
        b.Foreground      = fg
        b.BorderThickness = SW.Thickness(0)
        b.IsDefault       = is_default
        return b

    btn_cancel = _btn(u"Cancelar",  COR_BTN_CAN, COR_VALOR)
    btn_ok     = _btn(u"Confirmar", COR_BTN_OK,  COR_BTN_TXT, is_default=True)
    btn_row.Children.Add(btn_cancel)
    btn_row.Children.Add(btn_ok)
    root.Children.Add(btn_row)

    win.Content = root

    # --- Lógica de atualização em cascata ----------------------------------

    def _itens_do_grupo(uso):
        return grupos_data.get(uso, [])

    def update_tipos(sender=None, e=None):
        cb_tipo.Items.Clear()
        idx = cb_grupo.SelectedIndex
        if idx < 0 or idx >= len(usos_lista):
            return
        uso_sel = usos_lista[idx]
        for codigo, desc, obs, ad, er, pt in _itens_do_grupo(uso_sel):
            item         = SWC.ComboBoxItem()
            item.Content = u"{}  —  {}".format(codigo, desc) if desc else codigo
            item.Tag     = codigo
            cb_tipo.Items.Add(item)
        if cb_tipo.Items.Count > 0:
            cb_tipo.SelectedIndex = 0

    def update_info(sender=None, e=None):
        idx_g = cb_grupo.SelectedIndex
        idx_t = cb_tipo.SelectedIndex
        if idx_g < 0 or idx_t < 0:
            txt_desc.Text = u""
            txt_taxa.Text = u""
            return
        uso_sel = usos_lista[idx_g]
        itens   = _itens_do_grupo(uso_sel)
        if idx_t >= len(itens):
            return
        codigo, desc, obs, ad, er, pt = itens[idx_t]
        txt_desc.Text = desc or codigo
        txt_taxa.Text = u"Taxa:  " + obs
        txt_ad.Text   = ad
        txt_er.Text   = er
        txt_pt.Text   = pt

    def on_cancel(sender, e):
        win.Close()

    def on_confirm(sender, e):
        idx_g = cb_grupo.SelectedIndex
        idx_t = cb_tipo.SelectedIndex
        if idx_g >= 0 and idx_t >= 0:
            uso_sel = usos_lista[idx_g]
            itens   = _itens_do_grupo(uso_sel)
            if idx_t < len(itens):
                resultado[0] = itens[idx_t][0]   # código selecionado
        win.Close()

    cb_grupo.SelectionChanged += SWC.SelectionChangedEventHandler(update_tipos)
    cb_tipo.SelectionChanged  += SWC.SelectionChangedEventHandler(update_info)
    btn_cancel.Click += SW.RoutedEventHandler(on_cancel)
    btn_ok.Click     += SW.RoutedEventHandler(on_confirm)

    # Popular tipo e info com o primeiro item
    update_tipos()

    win.ShowDialog()
    return resultado[0]


# =============================================================================
# ENTRADA PÚBLICA
# =============================================================================

def occupancy_forms(estado, usar_legado=False):
    """
    Exibe o formulário de seleção de ocupação.

    estado      : dict retornado por estados.get_estado() — obrigatório.
    usar_legado : se True, força o dropdown simples em vez do WPF.
    Retorna o código da ocupação selecionada (str) ou encerra o script.
    """
    if usar_legado:
        codigo = _form_legado(estado)
    else:
        try:
            codigo = _form_wpf(estado)
        except Exception as ex:
            print(u"[AVISO] Formulário WPF falhou ({}), usando formato legado.".format(ex))
            codigo = _form_legado(estado)

    if not codigo:
        return script.exit()

    notas_txt = _notas_de_estado(estado, codigo)
    if notas_txt:
        forms.alert(notas_txt, title=u"Notas específicas:", warn_icon=True)

    return codigo
