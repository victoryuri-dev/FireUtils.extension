# -*- coding: utf-8 -*-
__title__ = "Dados do\nProjeto"

import io
import os
import json
import datetime

from pyrevit import forms, script

_ESTADOS = [
    {u"nome": u"Maranhão",   u"uf": u"MA"},
    {u"nome": u"Pernambuco", u"uf": u"PE"},
]

_CACHE_NOME = u"firedata.json"
_TEMP       = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
_LAST_PROJ  = os.path.join(_TEMP, u"fireutils_last_project.txt")


def _salvar_ponteiro(projeto_dir):
    try:
        with io.open(_LAST_PROJ, "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def _carregar_projeto(projeto_dir):
    try:
        with io.open(_cache_path(projeto_dir), u"r", encoding=u"utf-8") as f:
            return json.loads(f.read()).get(u"dados_projeto")
    except Exception:
        return None


def _salvar_projeto(projeto_dir, identificador, estado_nome, uf, ocupacao_principal,
                    area_construida, area_terreno):
    dados = {
        u"identificador":       identificador,
        u"estado":              estado_nome,
        u"uf":                  uf,
        u"ocupacao_principal":  ocupacao_principal,
        u"area_construida":     area_construida,
        u"area_terreno":        area_terreno,
        u"_timestamp":          datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"),
    }
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        arquivo = {}
    arquivo[u"dados_projeto"] = dados
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)
    _salvar_ponteiro(projeto_dir)
    return path


def _carregar_estado(uf):
    """Carrega o dict do estado a partir da sigla. Retorna None se não encontrado."""
    try:
        from normas import get_estado
        return get_estado(uf)
    except Exception:
        return None


def _opcoes_ocupacao(estado):
    """Lista de (codigo, label) para o ComboBox de ocupação principal."""
    if not estado:
        return []
    tabela = estado.get(u"tabela", {})
    ocups  = estado.get(u"ocupacoes", {})
    opcoes = []
    for codigo in sorted(tabela.keys()):
        desc = ocups.get(codigo, {}).get(u"descricao", u"")
        label = u"{}  —  {}".format(codigo, desc) if desc else codigo
        opcoes.append((codigo, label))
    return opcoes


# =============================================================================
# VERIFICAR PROJETO SALVO
# =============================================================================

doc = __revit__.ActiveUIDocument.Document

if not doc.PathName:
    forms.alert(
        u"O projeto Revit não está salvo.\n\n"
        u"Salve o arquivo (.rvt) antes de configurar os Dados do Projeto.",
        title=u"Fire Utils — Salve o projeto",
        warn_icon=True,
    )
    script.exit()

projeto_dir = os.path.dirname(doc.PathName)


# =============================================================================
# FORMULÁRIO WPF
# =============================================================================

def _form_wpf(projeto_dir):
    import clr
    clr.AddReference(u"PresentationFramework")
    clr.AddReference(u"PresentationCore")
    clr.AddReference(u"WindowsBase")
    import System.Windows as SW
    import System.Windows.Controls as SWC
    import System.Windows.Media as SWM

    existente = _carregar_projeto(projeto_dir) or {}
    existente.setdefault(u"identificador", existente.get(u"nome", u""))
    resultado = [None]

    # Pré-carregar estado salvo
    uf_salva  = existente.get(u"uf", u"")
    idx_estado_inicial = 0
    for i, e in enumerate(_ESTADOS):
        if e[u"uf"] == uf_salva or e[u"nome"] == existente.get(u"estado", u""):
            idx_estado_inicial = i
            break

    estado_inicial = _carregar_estado(_ESTADOS[idx_estado_inicial][u"uf"])
    opcoes_ocup    = _opcoes_ocupacao(estado_inicial)  # [(codigo, label), ...]

    COR_BG      = SWM.SolidColorBrush(SWM.Color.FromRgb(245, 245, 245))
    COR_CARD    = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    COR_BORDA   = SWM.SolidColorBrush(SWM.Color.FromRgb(213, 213, 213))
    COR_LABEL   = SWM.SolidColorBrush(SWM.Color.FromRgb(100, 100, 100))
    COR_VALOR   = SWM.SolidColorBrush(SWM.Color.FromRgb(30,  30,  30))
    COR_LARANJA = SWM.SolidColorBrush(SWM.Color.FromRgb(216, 59,  1))
    COR_BRANCO  = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 255, 255))
    COR_CAN     = SWM.SolidColorBrush(SWM.Color.FromRgb(225, 225, 225))

    win = SW.Window()
    win.Title                 = u"Fire Utils — Dados do Projeto"
    win.Width                 = 420
    win.Background            = COR_BG
    win.SizeToContent         = SW.SizeToContent.Height
    win.WindowStartupLocation = SW.WindowStartupLocation.CenterScreen
    win.ResizeMode            = SW.ResizeMode.NoResize

    root = SWC.StackPanel()
    root.Margin = SW.Thickness(22, 18, 22, 18)

    def _label(texto):
        tb = SWC.TextBlock()
        tb.Text       = texto
        tb.FontSize   = 11
        tb.Foreground = COR_LABEL
        tb.Margin     = SW.Thickness(0, 0, 0, 4)
        return tb

    titulo = SWC.TextBlock()
    titulo.Text       = u"Dados do Projeto"
    titulo.FontSize   = 15
    titulo.FontWeight = SW.FontWeights.SemiBold
    titulo.Foreground = COR_LARANJA
    titulo.Margin     = SW.Thickness(0, 0, 0, 16)
    root.Children.Add(titulo)

    card = SWC.Border()
    card.Background      = COR_CARD
    card.BorderBrush     = COR_BORDA
    card.BorderThickness = SW.Thickness(1)
    card.CornerRadius    = SW.CornerRadius(5)
    card.Padding         = SW.Thickness(16, 14, 16, 14)
    card.Margin          = SW.Thickness(0, 0, 0, 16)

    campos = SWC.StackPanel()

    # ---- Nome do projeto ------------------------------------------------
    campos.Children.Add(_label(u"Nome do projeto"))
    txt_nome = SWC.TextBox()
    txt_nome.Text       = existente.get(u"identificador", u"")
    txt_nome.FontSize   = 13
    txt_nome.Padding    = SW.Thickness(8, 6, 8, 6)
    txt_nome.Margin     = SW.Thickness(0, 0, 0, 14)
    txt_nome.Background = COR_BRANCO
    campos.Children.Add(txt_nome)

    # ---- Estado ---------------------------------------------------------
    campos.Children.Add(_label(u"Estado"))
    cb_estado = SWC.ComboBox()
    cb_estado.FontSize = 12
    cb_estado.Height   = 28
    cb_estado.Margin   = SW.Thickness(0, 0, 0, 4)
    for e in _ESTADOS:
        item         = SWC.ComboBoxItem()
        item.Content = e[u"nome"]
        cb_estado.Items.Add(item)
    cb_estado.SelectedIndex = idx_estado_inicial
    cb_estado.Margin        = SW.Thickness(0, 0, 0, 14)
    campos.Children.Add(cb_estado)

    # ---- Separador ------------------------------------------------------
    sep = SWC.Separator()
    sep.Margin = SW.Thickness(0, 0, 0, 12)
    campos.Children.Add(sep)

    # ---- Áreas ----------------------------------------------------------
    area_row = SWC.Grid()
    area_row.Margin = SW.Thickness(0, 0, 0, 14)
    col_a = SWC.ColumnDefinition()
    col_b = SWC.ColumnDefinition()
    col_s = SWC.ColumnDefinition()
    col_s.Width = SW.GridLength(12)
    area_row.ColumnDefinitions.Add(col_a)
    area_row.ColumnDefinitions.Add(col_s)
    area_row.ColumnDefinitions.Add(col_b)
    for _ in range(2):
        r = SWC.RowDefinition()
        r.Height = SW.GridLength(SW.GridLength.Auto.Value, SW.GridUnitType.Auto)
        area_row.RowDefinitions.Add(r)

    def _area_label(texto, col):
        tb = _label(texto)
        SWC.Grid.SetRow(tb, 0)
        SWC.Grid.SetColumn(tb, col)
        return tb

    def _area_box(valor_salvo, col):
        tb = SWC.TextBox()
        tb.Text       = u"{}".format(valor_salvo) if valor_salvo is not None else u""
        tb.FontSize   = 13
        tb.Padding    = SW.Thickness(8, 6, 8, 6)
        tb.Background = COR_BRANCO
        SWC.Grid.SetRow(tb, 1)
        SWC.Grid.SetColumn(tb, col)
        return tb

    area_row.Children.Add(_area_label(u"Área construída (m²)", 0))
    area_row.Children.Add(_area_label(u"Área do terreno (m²)", 2))

    txt_area_const  = _area_box(existente.get(u"area_construida"), 0)
    txt_area_terr   = _area_box(existente.get(u"area_terreno"),    2)
    area_row.Children.Add(txt_area_const)
    area_row.Children.Add(txt_area_terr)
    campos.Children.Add(area_row)

    # ---- Separador 2 ----------------------------------------------------
    sep2 = SWC.Separator()
    sep2.Margin = SW.Thickness(0, 0, 0, 12)
    campos.Children.Add(sep2)

    # ---- Ocupação principal ---------------------------------------------
    campos.Children.Add(_label(u"Ocupação principal da edificação"))
    cb_ocup = SWC.ComboBox()
    cb_ocup.FontSize = 12
    cb_ocup.Height   = 28
    cb_ocup.Margin   = SW.Thickness(0, 0, 0, 0)

    # Container mutável para a lista de opções (atualizada quando o estado muda)
    _ocup_state = [opcoes_ocup]

    def _preencher_cb_ocup(opcoes, preselect=None):
        cb_ocup.Items.Clear()
        del _ocup_state[0]
        _ocup_state.insert(0, opcoes)
        for codigo, label in opcoes:
            item         = SWC.ComboBoxItem()
            item.Content = label
            item.Tag     = codigo
            cb_ocup.Items.Add(item)
        # Tentar pré-selecionar: pelo código salvo ou pelo primeiro item
        idx_sel = 0
        if preselect:
            for i, (cod, _) in enumerate(opcoes):
                if cod == preselect:
                    idx_sel = i
                    break
        if cb_ocup.Items.Count > 0:
            cb_ocup.SelectedIndex = idx_sel

    _preencher_cb_ocup(opcoes_ocup, preselect=existente.get(u"ocupacao_principal"))
    campos.Children.Add(cb_ocup)

    card.Child = campos
    root.Children.Add(card)

    # ---- Botões ---------------------------------------------------------
    btn_row = SWC.StackPanel()
    btn_row.Orientation         = SWC.Orientation.Horizontal
    btn_row.HorizontalAlignment = SW.HorizontalAlignment.Right

    def _btn(texto, bg, fg, is_default=False):
        b = SWC.Button()
        b.Content         = texto
        b.Width           = 100
        b.Height          = 30
        b.FontSize        = 12
        b.Margin          = SW.Thickness(8, 0, 0, 0)
        b.Background      = bg
        b.Foreground      = fg
        b.BorderThickness = SW.Thickness(0)
        b.IsDefault       = is_default
        return b

    btn_cancel = _btn(u"Cancelar", COR_CAN,    COR_VALOR)
    btn_salvar = _btn(u"Salvar",   COR_LARANJA, COR_BRANCO, is_default=True)
    btn_row.Children.Add(btn_cancel)
    btn_row.Children.Add(btn_salvar)
    root.Children.Add(btn_row)

    win.Content = root

    # ---- Handlers -------------------------------------------------------
    def on_estado_changed(sender, e):
        idx = cb_estado.SelectedIndex
        if 0 <= idx < len(_ESTADOS):
            est = _carregar_estado(_ESTADOS[idx][u"uf"])
            _preencher_cb_ocup(_opcoes_ocupacao(est))

    def on_cancel(sender, e):
        win.Close()

    def _parse_area(txt):
        """Converte texto para float, aceitando vírgula ou ponto. Retorna None se vazio."""
        s = txt.strip().replace(u",", u".")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def on_salvar(sender, e):
        nome   = txt_nome.Text.strip()
        idx_e  = cb_estado.SelectedIndex
        idx_o  = cb_ocup.SelectedIndex
        opcoes = _ocup_state[0]

        if not nome:
            forms.alert(u"Informe o nome do projeto.", title=u"Fire Utils")
            return
        if idx_e < 0 or idx_e >= len(_ESTADOS):
            forms.alert(u"Selecione o Estado.", title=u"Fire Utils")
            return
        if idx_o < 0 or idx_o >= len(opcoes):
            forms.alert(u"Selecione a ocupação principal.", title=u"Fire Utils")
            return

        estado_sel         = _ESTADOS[idx_e]
        ocupacao_principal = opcoes[idx_o][0]
        area_construida    = _parse_area(txt_area_const.Text)
        area_terreno       = _parse_area(txt_area_terr.Text)

        resultado[0] = (nome, estado_sel[u"nome"], estado_sel[u"uf"],
                        ocupacao_principal, area_construida, area_terreno)
        win.Close()

    cb_estado.SelectionChanged += SWC.SelectionChangedEventHandler(on_estado_changed)
    btn_cancel.Click           += SW.RoutedEventHandler(on_cancel)
    btn_salvar.Click           += SW.RoutedEventHandler(on_salvar)

    win.ShowDialog()
    return resultado[0]


# =============================================================================
# ENTRY POINT
# =============================================================================

output = script.get_output()

try:
    resultado = _form_wpf(projeto_dir)
except Exception as ex:
    forms.alert(u"Erro ao abrir formulário: {}".format(ex), title=u"Fire Utils", warn_icon=True)
    script.exit()

if not resultado:
    script.exit()

identificador, estado_nome, uf, ocupacao_principal, area_construida, area_terreno = resultado

try:
    path = _salvar_projeto(projeto_dir, identificador, estado_nome, uf,
                           ocupacao_principal, area_construida, area_terreno)
except Exception as ex:
    forms.alert(u"Erro ao salvar dados: {}".format(ex), title=u"Fire Utils", warn_icon=True)
    script.exit()

output.print_md(u"# Dados do Projeto salvos")
output.print_md(u"| Campo              | Valor |")
output.print_md(u"|--------------------|-------|")
output.print_md(u"| Identificador      | {} |".format(identificador))
output.print_md(u"| Estado             | {} ({}) |".format(estado_nome, uf))
output.print_md(u"| Ocupação principal | **{}** |".format(ocupacao_principal))
if area_construida is not None:
    output.print_md(u"| Área construída    | {} m² |".format(area_construida))
if area_terreno is not None:
    output.print_md(u"| Área do terreno    | {} m² |".format(area_terreno))
output.print_md(u"")
output.print_md(u"_Arquivo:_ `{}`".format(path))
