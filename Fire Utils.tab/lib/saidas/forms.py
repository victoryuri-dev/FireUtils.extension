# -*- coding: utf-8 -*-
# saidas/forms.py — Fire Utils
# Formulário WPF para configuração dos parâmetros de distância máxima.

from pyrevit import script


def form_config_distancias(normativas, ocupacao_principal=None):
    """
    Diálogo que coleta os três parâmetros complementares de distância máxima:

      - Saída única ou duas/mais saídas
      - Possui chuveiro automático
      - Possui detecção de incêndio

    A ocupação principal deve ser passada via `ocupacao_principal` (vem de
    Dados do Projeto). Se não fornecida, retorna None silenciosamente.

    Retorna dict:
        {
          "ocupacao_principal": str,   # código da ocupação (passado como parâmetro)
          "saida_unica":        bool,
          "chuveiro":           bool,
          "deteccao":           bool,
        }
    ou None se o usuário cancelar.

    Se o estado não tiver distancias_maximas, retorna None silenciosamente.
    """
    if not normativas or not ocupacao_principal:
        return None

    dist_cfg = normativas.get(u"distancias_maximas")
    if not dist_cfg:
        return None

    mapa   = dist_cfg.get(u"mapa_ocupacao", {})
    grupos = dist_cfg.get(u"grupos", {})

    resultado = [None]

    # ------------------------------------------------------------------
    # WPF
    # ------------------------------------------------------------------
    import clr
    clr.AddReference(u"PresentationFramework")
    clr.AddReference(u"PresentationCore")
    clr.AddReference(u"WindowsBase")
    import System.Windows           as SW
    import System.Windows.Controls  as SWC
    import System.Windows.Media     as SWM

    # Paleta
    C_BG       = SWM.SolidColorBrush(SWM.Color.FromRgb(245, 245, 245))
    C_CARD     = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    C_BORDA    = SWM.SolidColorBrush(SWM.Color.FromRgb(213, 213, 213))
    C_LABEL    = SWM.SolidColorBrush(SWM.Color.FromRgb(100, 100, 100))
    C_VALOR    = SWM.SolidColorBrush(SWM.Color.FromRgb(30,  30,  30))
    C_ACCENT   = SWM.SolidColorBrush(SWM.Color.FromRgb(216, 59,  1))
    C_ACCENT_L = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 235, 225))
    C_BTN_TXT  = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    C_BTN_CAN  = SWM.SolidColorBrush(SWM.Color.FromRgb(225, 225, 225))
    C_NA       = SWM.SolidColorBrush(SWM.Color.FromRgb(160, 160, 160))

    # Janela
    win = SW.Window()
    win.Title      = u"Distâncias Máximas — {}".format(normativas.get(u"nome", u""))
    win.Width      = 460
    win.Background = C_BG
    win.SizeToContent         = SW.SizeToContent.Height
    win.WindowStartupLocation = SW.WindowStartupLocation.CenterScreen
    win.ResizeMode = SW.ResizeMode.NoResize

    root = SWC.StackPanel()
    root.Margin = SW.Thickness(18, 14, 18, 14)
    win.Content = root

    # ------------------------------------------------------------------
    # Helpers de layout
    # ------------------------------------------------------------------
    def _lbl(texto, bold=False, size=11, cor=None):
        tb = SWC.TextBlock()
        tb.Text       = texto
        tb.FontSize   = size
        tb.Foreground = cor or C_LABEL
        tb.Margin     = SW.Thickness(0, 0, 0, 4)
        if bold:
            tb.FontWeight = SW.FontWeights.SemiBold
        return tb

    def _sep():
        s = SWC.Separator()
        s.Margin = SW.Thickness(0, 8, 0, 10)
        return s

    def _card(conteudo_ctrl):
        b = SWC.Border()
        b.Background      = C_CARD
        b.BorderBrush     = C_BORDA
        b.BorderThickness = SW.Thickness(1)
        b.CornerRadius    = SW.CornerRadius(5)
        b.Padding         = SW.Thickness(12, 10, 12, 10)
        b.Margin          = SW.Thickness(0, 0, 0, 12)
        b.Child           = conteudo_ctrl
        return b

    # ------------------------------------------------------------------
    # Cabeçalho — mostra a ocupação vinda dos Dados do Projeto
    # ------------------------------------------------------------------
    ocup_entry = normativas.get(u"ocupacoes", {}).get(ocupacao_principal, {})
    ocup_desc  = ocup_entry.get(u"descricao", u"")
    ocup_label = u"{}  —  {}".format(ocupacao_principal, ocup_desc) if ocup_desc else ocupacao_principal

    hdr_sp = SWC.StackPanel()
    hdr_sp.Margin = SW.Thickness(0, 0, 0, 12)
    root.Children.Add(_card(hdr_sp))

    hdr_sp.Children.Add(_lbl(u"Ocupação principal", bold=False))
    hdr_val = SWC.TextBlock()
    hdr_val.Text       = ocup_label
    hdr_val.FontSize   = 12
    hdr_val.FontWeight = SW.FontWeights.SemiBold
    hdr_val.Foreground = C_VALOR
    hdr_val.TextWrapping = SW.TextWrapping.Wrap
    hdr_sp.Children.Add(hdr_val)

    root.Children.Add(_sep())

    # ------------------------------------------------------------------
    # Seção 1 — Número de saídas
    # ------------------------------------------------------------------
    root.Children.Add(_lbl(u"Número de saídas de emergência", bold=True))

    radio_sp = SWC.StackPanel()
    radio_sp.Orientation = SWC.Orientation.Horizontal
    radio_sp.Margin      = SW.Thickness(0, 0, 0, 12)

    rb_unica = SWC.RadioButton()
    rb_unica.Content    = u"Saída única"
    rb_unica.IsChecked  = False
    rb_unica.FontSize   = 12
    rb_unica.Margin     = SW.Thickness(0, 0, 24, 0)

    rb_multi = SWC.RadioButton()
    rb_multi.Content   = u"Duas ou mais saídas"
    rb_multi.IsChecked = True
    rb_multi.FontSize  = 12

    radio_sp.Children.Add(rb_unica)
    radio_sp.Children.Add(rb_multi)
    root.Children.Add(radio_sp)

    root.Children.Add(_sep())

    # ------------------------------------------------------------------
    # Seção 3 — Sistemas de proteção (card com dois checkboxes)
    # ------------------------------------------------------------------
    root.Children.Add(_lbl(u"Sistemas de proteção", bold=True))

    prot_sp = SWC.StackPanel()

    ck_chu = SWC.CheckBox()
    ck_chu.Content    = u"Possui sistema de chuveiros automáticos (sprinklers)"
    ck_chu.FontSize   = 12
    ck_chu.IsChecked  = False
    ck_chu.Margin     = SW.Thickness(0, 0, 0, 8)

    ck_det = SWC.CheckBox()
    ck_det.Content   = u"Possui sistema de detecção de incêndio"
    ck_det.FontSize  = 12
    ck_det.IsChecked = False

    prot_sp.Children.Add(ck_chu)
    prot_sp.Children.Add(ck_det)
    root.Children.Add(_card(prot_sp))

    # ------------------------------------------------------------------
    # Seção 4 — Preview das distâncias
    # ------------------------------------------------------------------
    root.Children.Add(_lbl(u"Distâncias máximas aplicáveis (prévia)", bold=True))

    # Grid 2 colunas x 2 linhas
    dist_grid = SWC.Grid()
    for _ in range(2):
        c = SWC.ColumnDefinition()
        dist_grid.ColumnDefinitions.Add(c)
    for _ in range(2):
        r = SWC.RowDefinition()
        r.Height = SW.GridLength(SW.GridLength.Auto.Value, SW.GridUnitType.Auto)
        dist_grid.RowDefinitions.Add(r)

    def _dcell(texto, row, col, cor=None, bold=False, size=10):
        tb = SWC.TextBlock()
        tb.Text          = texto
        tb.FontSize      = size
        tb.TextAlignment = SW.TextAlignment.Center
        tb.Foreground    = cor or C_LABEL
        tb.Margin        = SW.Thickness(0, 0, 0, 2)
        if bold:
            tb.FontWeight = SW.FontWeights.SemiBold
        SWC.Grid.SetRow(tb,    row)
        SWC.Grid.SetColumn(tb, col)
        dist_grid.Children.Add(tb)
        return tb

    _dcell(u"Piso de descarga",  0, 0)
    _dcell(u"Demais pavimentos", 0, 1)
    txt_terreo = _dcell(u"—", 1, 0, cor=C_ACCENT, bold=True, size=20)
    txt_demais = _dcell(u"—", 1, 1, cor=C_ACCENT, bold=True, size=20)

    root.Children.Add(_card(dist_grid))

    # ------------------------------------------------------------------
    # Botões
    # ------------------------------------------------------------------
    btn_row = SWC.StackPanel()
    btn_row.Orientation         = SWC.Orientation.Horizontal
    btn_row.HorizontalAlignment = SW.HorizontalAlignment.Right

    def _btn(texto, bg, fg, is_default=False):
        b = SWC.Button()
        b.Content         = texto
        b.Width           = 110
        b.Height          = 30
        b.FontSize        = 12
        b.Margin          = SW.Thickness(6, 0, 0, 0)
        b.Background      = bg
        b.Foreground      = fg
        b.BorderThickness = SW.Thickness(0)
        b.IsDefault       = is_default
        return b

    btn_cancel = _btn(u"Cancelar",  C_BTN_CAN, C_VALOR)
    btn_ok     = _btn(u"Confirmar", C_ACCENT,  C_BTN_TXT, is_default=True)
    btn_row.Children.Add(btn_cancel)
    btn_row.Children.Add(btn_ok)
    root.Children.Add(btn_row)

    # ------------------------------------------------------------------
    # Lógica de atualização do preview
    # ------------------------------------------------------------------
    def _lookup(codigo, tipo_pav, saida_key, chu_key, det_key):
        nome_grupo = mapa.get(codigo)
        if not nome_grupo:
            return None
        cfg = grupos.get(nome_grupo, {})
        try:
            return cfg[tipo_pav][chu_key][saida_key][det_key]
        except (KeyError, TypeError):
            return None

    def update_preview(sender=None, e=None):
        saida_k = u"saida_unica"  if rb_unica.IsChecked else u"mais_saidas"
        chu_k   = u"com_chuveiro" if ck_chu.IsChecked   else u"sem_chuveiro"
        det_k   = u"com_deteccao" if ck_det.IsChecked   else u"sem_deteccao"

        vt = _lookup(ocupacao_principal, u"terreo", saida_k, chu_k, det_k)
        vd = _lookup(ocupacao_principal, u"demais", saida_k, chu_k, det_k)

        txt_terreo.Text       = u"{} m".format(vt) if vt is not None else u"N/A"
        txt_demais.Text       = u"{} m".format(vd) if vd is not None else u"N/A"
        txt_terreo.Foreground = C_ACCENT if vt is not None else C_NA
        txt_demais.Foreground = C_ACCENT if vd is not None else C_NA

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def on_cancel(sender, e):
        win.Close()

    def on_confirm(sender, e):
        resultado[0] = {
            u"ocupacao_principal": ocupacao_principal,
            u"saida_unica":        bool(rb_unica.IsChecked),
            u"chuveiro":           bool(ck_chu.IsChecked),
            u"deteccao":           bool(ck_det.IsChecked),
        }
        win.Close()

    rb_unica.Checked         += SW.RoutedEventHandler(update_preview)
    rb_multi.Checked         += SW.RoutedEventHandler(update_preview)
    ck_chu.Checked           += SW.RoutedEventHandler(update_preview)
    ck_chu.Unchecked         += SW.RoutedEventHandler(update_preview)
    ck_det.Checked           += SW.RoutedEventHandler(update_preview)
    ck_det.Unchecked         += SW.RoutedEventHandler(update_preview)
    btn_cancel.Click         += SW.RoutedEventHandler(on_cancel)
    btn_ok.Click             += SW.RoutedEventHandler(on_confirm)

    update_preview()
    win.ShowDialog()
    return resultado[0]
