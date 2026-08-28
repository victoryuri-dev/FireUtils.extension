# -*- coding: utf-8 -*-
"""
hydrant_sistem_forms.py
Formulário WPF para seleção do Tipo de Sistema de Hidrante (NT 22 CBMMA).
Exibe a Tabela 2 completa e permite que o usuário selecione o tipo desejado.
Para Tipo 4 (duas variantes de DN), exibe sub-seleção.
"""

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import (
    Window, Thickness, HorizontalAlignment, VerticalAlignment,
    ResizeMode, WindowStartupLocation, TextWrapping
)
from System.Windows.Controls import (
    Grid, StackPanel, Label, ComboBox, ComboBoxItem, TextBox, CheckBox,
    Button, DataGrid, DataGridTextColumn, ScrollViewer, ScrollBarVisibility,
    Border, Orientation, DataGridSelectionMode, DataGridSelectionUnit,
    Expander, TextBlock, DockPanel, Dock
)
from System.Windows import GridLength, GridUnitType
from System.Windows.Media import SolidColorBrush, Color
from System.Collections.ObjectModel import ObservableCollection
from System import String

from hidrantes.db import SISTEMAS_HIDRANTE, get_todos_tipos
from hidrantes import custom as custom_store
from hidrantes import succao as succao_calc
from hidrantes import npshd as npshd_calc

# Opções de método de cálculo — a lista canônica vive no motor (calc.py),
# que é quem interpreta a escolha para saber onde o par normativo (Q, Pmin)
# se aplica: na válvula do hidrante ou na ponta do esguicho regulável.
from hidrantes.calc import METODOS_CALCULO


# ---------------------------------------------------------------------------
# Modelo de linha para o DataGrid
# ---------------------------------------------------------------------------
class SistemaRow(object):
    def __init__(self, tipo, esguicho_dn, mangueira_dn, comprimento,
                 expedicoes, vazao, pressao, obs=""):
        self.Tipo        = str(tipo)
        self.EsguichoDN  = str(esguicho_dn)
        self.MangueiraDN = str(mangueira_dn)
        self.Comprimento = str(comprimento)
        self.Expedicoes  = str(expedicoes)
        self.Vazao       = str(vazao)
        self.Pressao     = str(pressao)
        self.Obs         = obs  # ex.: "Var. A" / "Var. B" para tipo 4


def _build_rows():
    rows = ObservableCollection[object]()
    for tipo in get_todos_tipos():
        dados = SISTEMAS_HIDRANTE[tipo]
        variantes = dados["variantes"]
        for i, v in enumerate(variantes):
            obs = ""
            if len(variantes) > 1:
                obs = "Var. {}".format(chr(65 + i))  # A, B, C…
            rows.Add(SistemaRow(
                tipo         = tipo,
                esguicho_dn  = dados["esguicho_dn"],
                mangueira_dn = v["mangueira_dn"],
                comprimento  = v["mangueira_comp"],
                expedicoes   = v["num_expedicoes"],
                vazao        = v["vazao_min"],
                pressao      = v["pressao_min"],
                obs          = obs,
            ))
    return rows


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class HydrantSystemForm(Window):

    def __init__(self, custom_inicial=None, metodo_inicial=None, succao_inicial=None):
        self.Title  = "Fire Utils – Tipo de Sistema de Hidrante (NT 22)"
        self.Width  = 800
        self.Height = 680
        self.ResizeMode = ResizeMode.CanResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen

        self.selected_tipo     = None
        self.selected_variante = None

        # Valores personalizados já salvos neste projeto (ou None)
        self._custom_inicial = custom_inicial

        self._build_ui(succao_inicial)

        # Se o projeto já tem valores personalizados salvos, pré-carrega os
        # campos e deixa o modo personalizado ligado — o usuário pode
        # reclassificar quantas vezes quiser sem redigitar.
        if custom_inicial:
            self._preencher_custom(custom_inicial)
            self._chk_custom.IsChecked = True

        # Método de cálculo já salvo neste projeto (ou None → 1ª opção)
        if metodo_inicial in METODOS_CALCULO:
            self._cmb_metodo.SelectedIndex = METODOS_CALCULO.index(metodo_inicial)

    # ------------------------------------------------------------------
    def _build_ui(self, succao_inicial=None):
        moldura = DockPanel()
        moldura.LastChildFill = True
        moldura.Margin = Thickness(14)

        root = StackPanel()

        # Título
        title = Label()
        title.Content  = "Tabela 2 – Tipos de sistemas de proteção por hidrante ou mangotinho"
        title.FontSize = 13
        title.FontWeight = System_FontWeights_Bold()
        title.Margin   = Thickness(0, 0, 0, 8)
        root.Children.Add(title)

        # DataGrid (somente leitura)
        self._grid = DataGrid()
        self._grid.Height              = 220
        self._grid.AutoGenerateColumns = False
        self._grid.IsReadOnly          = True
        self._grid.SelectionMode       = DataGridSelectionMode.Single
        self._grid.SelectionUnit       = DataGridSelectionUnit.FullRow
        self._grid.Margin              = Thickness(0, 0, 0, 10)
        self._grid.SelectionChanged   += self._on_grid_selection

        for header, binding in [
            ("Tipo",              "Tipo"),
            ("Esguicho DN (mm)",  "EsguichoDN"),
            ("Mangueira DN (mm)", "MangueiraDN"),
            ("Comprimento (m)",   "Comprimento"),
            ("Expedições",        "Expedicoes"),
            ("Vazão mín. (L/min)","Vazao"),
            ("Pressão mín. (mca)","Pressao"),
            ("Obs.",              "Obs"),
        ]:
            col = DataGridTextColumn()
            col.Header  = header
            col.Binding = _make_binding(binding)
            col.Width   = DataGridLength(1, DataGridLengthUnitType_Star())
            self._grid.Columns.Add(col)

        self._grid.ItemsSource = _build_rows()
        root.Children.Add(self._grid)

        # Label de feedback
        self._lbl_sel = Label()
        self._lbl_sel.Content  = "Nenhum tipo selecionado."
        self._lbl_sel.FontSize = 11
        self._lbl_sel.Margin   = Thickness(0, 0, 0, 6)
        root.Children.Add(self._lbl_sel)

        # Bloco de valores personalizados
        root.Children.Add(self._build_custom_panel())

        # Bloco de método de cálculo
        root.Children.Add(self._build_metodo_panel())

        # Configurações avançadas (hoje só o NPSH disponível) — colapsado por
        # padrão, logo após o sistema personalizado.
        root.Children.Add(self._build_avancado_panel(succao_inicial))

        # Botões — fixos no rodapé, fora da área rolável, para não sumirem
        # quando "Configurações Avançadas" está expandido e o conteúdo
        # passa da altura da janela.
        btn_panel = StackPanel()
        btn_panel.Orientation = Orientation.Horizontal
        btn_panel.HorizontalAlignment = HorizontalAlignment.Right
        btn_panel.Margin = Thickness(0, 10, 0, 0)

        btn_ok = Button()
        btn_ok.Content = "Confirmar"
        btn_ok.Width   = 100
        btn_ok.Height  = 30
        btn_ok.Margin  = Thickness(0, 0, 8, 0)
        btn_ok.Click  += self._on_confirm

        btn_cancel = Button()
        btn_cancel.Content = "Cancelar"
        btn_cancel.Width   = 100
        btn_cancel.Height  = 30
        btn_cancel.Click  += self._on_cancel

        btn_panel.Children.Add(btn_ok)
        btn_panel.Children.Add(btn_cancel)
        DockPanel.SetDock(btn_panel, Dock.Bottom)
        moldura.Children.Add(btn_panel)

        rolagem = ScrollViewer()
        rolagem.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        rolagem.Content = root
        moldura.Children.Add(rolagem)

        self.Content = moldura

    # ------------------------------------------------------------------
    # Painel de valores personalizados
    # ------------------------------------------------------------------
    def _build_custom_panel(self):
        box = Border()
        box.BorderBrush     = SolidColorBrush(Color.FromRgb(170, 170, 170))
        box.BorderThickness = Thickness(1)
        box.Padding         = Thickness(10)
        box.Margin          = Thickness(0, 0, 0, 10)

        painel = StackPanel()

        self._chk_custom = CheckBox()
        self._chk_custom.Content    = u"Usar valores personalizados (fora da Tabela 2)"
        self._chk_custom.FontWeight = System_FontWeights_Bold()
        self._chk_custom.Margin     = Thickness(0, 0, 0, 8)
        self._chk_custom.Checked   += self._on_custom_toggle
        self._chk_custom.Unchecked += self._on_custom_toggle
        painel.Children.Add(self._chk_custom)

        padrao = custom_store.default_custom()

        # Linha 1 — descrição + expedições
        linha1 = StackPanel()
        linha1.Orientation = Orientation.Horizontal
        linha1.Margin      = Thickness(0, 0, 0, 6)

        campo_desc, self._txt_descricao = _campo_texto(
            u"Descrição", 330, padrao[u"descricao"])
        linha1.Children.Add(campo_desc)

        campo_exp = StackPanel()
        campo_exp.Margin = Thickness(0, 0, 10, 0)
        lbl_exp = Label()
        lbl_exp.Content  = u"Expedições"
        lbl_exp.FontSize = 11
        lbl_exp.Padding  = Thickness(0, 0, 0, 2)
        campo_exp.Children.Add(lbl_exp)

        self._cmb_expedicoes = ComboBox()
        self._cmb_expedicoes.Width = 130
        for opcao in (u"Simples", u"Duplo"):
            item = ComboBoxItem()
            item.Content = opcao
            self._cmb_expedicoes.Items.Add(item)
        self._cmb_expedicoes.SelectedIndex = 0
        campo_exp.Children.Add(self._cmb_expedicoes)
        linha1.Children.Add(campo_exp)

        painel.Children.Add(linha1)

        # Linha 2 — campos numéricos
        linha2 = StackPanel()
        linha2.Orientation = Orientation.Horizontal

        self._txt_numericos = {}
        for chave, rotulo in custom_store.CAMPOS_NUMERICOS:
            campo, txt = _campo_texto(
                custom_store.ROTULOS_CURTOS.get(chave, rotulo),
                128, u"{:g}".format(padrao[chave]))
            self._txt_numericos[chave] = txt
            linha2.Children.Add(campo)

        painel.Children.Add(linha2)

        self._campos_custom = (
            [self._txt_descricao, self._cmb_expedicoes] +
            list(self._txt_numericos.values())
        )
        self._set_custom_enabled(False)

        box.Child = painel
        return box

    # ------------------------------------------------------------------
    # Painel de método de cálculo
    # ------------------------------------------------------------------
    def _build_metodo_panel(self):
        box = Border()
        box.BorderBrush     = SolidColorBrush(Color.FromRgb(170, 170, 170))
        box.BorderThickness = Thickness(1)
        box.Padding         = Thickness(10)
        box.Margin          = Thickness(0, 0, 0, 10)

        painel = StackPanel()
        painel.Orientation = Orientation.Horizontal

        lbl = Label()
        lbl.Content     = u"Método de Cálculo"
        lbl.FontWeight  = System_FontWeights_Bold()
        lbl.VerticalContentAlignment = VerticalAlignment.Center
        lbl.Margin      = Thickness(0, 0, 10, 0)
        painel.Children.Add(lbl)

        self._cmb_metodo = ComboBox()
        self._cmb_metodo.Width = 260
        for opcao in METODOS_CALCULO:
            item = ComboBoxItem()
            item.Content = opcao
            self._cmb_metodo.Items.Add(item)
        self._cmb_metodo.SelectedIndex = 0
        painel.Children.Add(self._cmb_metodo)

        box.Child = painel
        return box

    # ------------------------------------------------------------------
    # Configurações avançadas — NPSH disponível
    # ------------------------------------------------------------------
    def _build_avancado_panel(self, succao_inicial):
        d = succao_calc.normalizar_dados(succao_inicial or {})

        expander = Expander()
        expander.Header      = u"Configurações Avançadas"
        expander.FontWeight  = System_FontWeights_Bold()
        expander.Margin      = Thickness(0, 0, 0, 10)
        # Só abre sozinho quando já há algo salvo — o usuário não precisa
        # entrar aqui em toda classificação de rotina.
        expander.IsExpanded  = bool(d[u"npshr_m"])

        raiz = StackPanel()
        raiz.Margin = Thickness(10, 8, 10, 4)

        sub = Label()
        sub.Content    = u"NPSH"
        sub.FontWeight = System_FontWeights_Bold()
        sub.Margin     = Thickness(0, 0, 0, 2)
        raiz.Children.Add(sub)

        _nota(raiz,
              u"Usado no cálculo do NPSH disponível, exigido só quando a "
              u"condição de sucção resultar negativa. Altitude e temperatura "
              u"já vêm com o valor usual — trocar só pelas opções das "
              u"tabelas de referência.")

        self._opc_altitude = [(alt, rot) for alt, _ha, rot
                              in npshd_calc.opcoes_altitude()]
        self._cmb_altitude = _combo(
            raiz, u"Altitude do local (pressão atmosférica, Ha)",
            self._opc_altitude,
            d[u"altitude_m"] if d[u"altitude_m"] is not None
            else npshd_calc.ALTITUDE_PADRAO)

        self._opc_temperatura = [(t, rot) for t, _h, rot
                                 in npshd_calc.opcoes_temperatura()]
        self._cmb_temperatura = _combo(
            raiz, u"Temperatura da água (pressão de vapor, Hvp)",
            self._opc_temperatura,
            d[u"temperatura_c"] if d[u"temperatura_c"] is not None
            else npshd_calc.TEMPERATURA_PADRAO)

        self._txt_npshr = _campo(
            raiz, u"NPSH requerido pela bomba — NPSHr (mca)", d[u"npshr_m"],
            u"Dado de catálogo do fabricante. Sem bomba definida ainda, "
            u"deixe em branco: o memorial mostra o NPSHd e marca a "
            u"comparação como pendente.")

        expander.Content = raiz
        return expander

    def _ler_succao(self, erros):
        """Lê o bloco de NPSH; acrescenta a erros quando o NPSHr digitado é
        inválido, e sempre devolve o dict normalizado (com npshr_m=None
        quando o campo está vazio ou inválido)."""
        bruto = (self._txt_npshr.Text or u"").strip().replace(u",", u".")
        npshr = None
        if bruto:
            try:
                npshr = float(bruto)
                if npshr <= 0:
                    raise ValueError
            except ValueError:
                erros.append(u"'NPSH requerido pela bomba' deve ser um número maior que zero.")

        return succao_calc.normalizar_dados({
            u"altitude_m":    self._opc_altitude[self._cmb_altitude.SelectedIndex][0],
            u"temperatura_c": self._opc_temperatura[self._cmb_temperatura.SelectedIndex][0],
            u"npshr_m":       npshr,
        })

    def _set_custom_enabled(self, ativo):
        for c in self._campos_custom:
            c.IsEnabled = ativo

    def _on_custom_toggle(self, sender, args):
        ativo = bool(self._chk_custom.IsChecked)
        self._set_custom_enabled(ativo)
        if ativo:
            # Modo personalizado ignora a seleção da Tabela 2
            self._grid.SelectedItem = None
            self._lbl_sel.Content = u"Modo personalizado: os valores da tabela serão ignorados."
        else:
            self._lbl_sel.Content = u"Nenhum tipo selecionado."

    def _preencher_custom(self, dados):
        d = custom_store.normalizar(dados)
        self._txt_descricao.Text = d[u"descricao"]
        for chave, _ in custom_store.CAMPOS_NUMERICOS:
            self._txt_numericos[chave].Text = u"{:g}".format(d[chave])
        idx = 1 if d[u"expedicoes"].lower().startswith(u"dup") else 0
        self._cmb_expedicoes.SelectedIndex = idx

    def _ler_custom(self):
        """Lê os campos do painel personalizado como dict cru (strings)."""
        dados = {
            u"descricao":  self._txt_descricao.Text,
            u"expedicoes": self._cmb_expedicoes.SelectedItem.Content
                           if self._cmb_expedicoes.SelectedItem else u"Simples",
        }
        for chave, _ in custom_store.CAMPOS_NUMERICOS:
            dados[chave] = self._txt_numericos[chave].Text.strip().replace(",", ".")
        return dados

    # ------------------------------------------------------------------
    def _on_grid_selection(self, sender, args):
        row = self._grid.SelectedItem
        if row is None:
            self._lbl_sel.Content = "Nenhum tipo selecionado."
            self.selected_tipo     = None
            self.selected_variante = None
            return

        # Escolher uma linha da tabela desliga o modo personalizado
        chk = getattr(self, "_chk_custom", None)
        if chk is not None and chk.IsChecked:
            chk.IsChecked = False

        tipo = int(row.Tipo)
        dados = SISTEMAS_HIDRANTE[tipo]
        variantes = dados["variantes"]

        # Descobre qual variante pela obs
        variante_idx = 0
        if row.Obs and row.Obs.startswith("Var. "):
            letra = row.Obs[-1]  # 'A', 'B', …
            variante_idx = ord(letra) - 65

        self.selected_tipo     = tipo
        self.selected_variante = variante_idx

        v = variantes[variante_idx]
        obs_txt = " ({})".format(row.Obs) if row.Obs else ""
        self._lbl_sel.Content = (
            u"Selecionado: Tipo {}{} — "
            u"Vazão: {} L/min | Pressão: {} mca | Mangueira DN {}".format(
                tipo, obs_txt,
                v["vazao_min"], v["pressao_min"], v["mangueira_dn"]
            )
        )

    # ------------------------------------------------------------------
    def _on_confirm(self, sender, args):
        erros_succao = []
        self._dados_succao = self._ler_succao(erros_succao)
        if erros_succao:
            alert(u"Corrija as Configurações Avançadas:\n\n– {}".format(
                u"\n– ".join(erros_succao)))
            return

        if self._chk_custom.IsChecked:
            erros = custom_store.validar(self._ler_custom())
            if erros:
                alert(u"Corrija os valores personalizados:\n\n– {}".format(
                    u"\n– ".join(erros)))
                return
            self.DialogResult = True
            self.Close()
            return

        if self.selected_tipo is None:
            alert(u"Selecione um tipo de sistema na tabela ou marque "
                  u"'Usar valores personalizados'.")
            return
        self.DialogResult = True
        self.Close()

    def _on_cancel(self, sender, args):
        self.selected_tipo     = None
        self.selected_variante = None
        self._cancelado        = True
        self.DialogResult = False
        self.Close()

    # ------------------------------------------------------------------
    def get_result(self):
        """
        Retorna dict com os dados do sistema escolhido, ou None se cancelado.

        Tabela 2:
        {
            "custom": False,
            "tipo": int,
            "variante_idx": int,
            "dados": dict,      # variante completa de SISTEMAS_HIDRANTE
            "descricao": unicode,
            "metodo_calculo": unicode,   # um de METODOS_CALCULO
            "dados_succao": dict,        # Configurações Avançadas > NPSH
        }

        Personalizado:
        {
            "custom": True,
            "tipo": None,
            "variante_idx": 0,
            "custom_dados": dict,   # vocabulário de hidrantes/custom.py
            "dados": dict,          # mesmas chaves de SISTEMAS_HIDRANTE
            "descricao": unicode,
            "metodo_calculo": unicode,   # um de METODOS_CALCULO
            "dados_succao": dict,        # Configurações Avançadas > NPSH
        }
        """
        if getattr(self, "_cancelado", False):
            return None

        metodo_calculo = (self._cmb_metodo.SelectedItem.Content
                          if self._cmb_metodo.SelectedItem else METODOS_CALCULO[0])
        dados_succao = self._dados_succao

        if self._chk_custom.IsChecked:
            d = custom_store.normalizar(self._ler_custom())
            return {
                "custom":       True,
                "tipo":         None,
                "variante_idx": 0,
                "custom_dados": d,
                "dados": {
                    "mangueira_dn":   d[u"mang_dn"],
                    "mangueira_comp": d[u"mang_comp"],
                    "num_expedicoes": d[u"expedicoes"],
                    "vazao_min":      d[u"q_min"],
                    "pressao_min":    d[u"p_min"],
                    "esguicho_dn":    d[u"esguicho_dn"],
                },
                "descricao": d[u"descricao"],
                "metodo_calculo": metodo_calculo,
                "dados_succao": dados_succao,
            }

        if self.selected_tipo is None:
            return None
        dados = SISTEMAS_HIDRANTE[self.selected_tipo]
        return {
            "custom":       False,
            "tipo":         self.selected_tipo,
            "variante_idx": self.selected_variante,
            "dados":        dados["variantes"][self.selected_variante],
            "descricao":    dados["descricao"],
            "metodo_calculo": metodo_calculo,
            "dados_succao": dados_succao,
        }


# ---------------------------------------------------------------------------
# Helpers de WPF (contornam limitações de import direto no IronPython)
# ---------------------------------------------------------------------------
def _make_binding(path):
    from System.Windows.Data import Binding
    b = Binding(path)
    return b


def _nota(painel, texto, recuo=0, base=10):
    """Linha de observação em corpo menor, abaixo de um campo/bloco."""
    bloco = TextBlock()
    bloco.Text     = texto
    bloco.FontSize = base
    bloco.Opacity  = 0.7
    bloco.TextWrapping = TextWrapping.Wrap
    bloco.Margin   = Thickness(recuo, 0, 0, 10)
    painel.Children.Add(bloco)
    return bloco


def _combo(painel, rotulo, opcoes, selecionado, dica=u""):
    """
    Combo de escolha entre linhas de tabela. opcoes: [(valor, rótulo)].
    Usado onde o valor NÃO pode ser digitado livre — Ha e Hvp só valem se
    vierem das tabelas de referência.
    """
    lbl = Label()
    lbl.Content  = rotulo
    lbl.FontSize = 11
    lbl.Padding  = Thickness(0, 0, 0, 2)
    painel.Children.Add(lbl)

    cmb = ComboBox()
    cmb.Height = 23
    cmb.Margin = Thickness(0, 0, 0, 2)
    for _valor, texto in opcoes:
        item = ComboBoxItem()
        item.Content = texto
        cmb.Items.Add(item)
    cmb.SelectedIndex = next(
        (i for i, (v, _t) in enumerate(opcoes) if v == selecionado), 0)
    painel.Children.Add(cmb)
    if dica:
        _nota(painel, dica)
    return cmb


def _campo(painel, rotulo, valor, dica=u""):
    """Campo de texto simples com rótulo acima e nota opcional abaixo."""
    lbl = Label()
    lbl.Content  = rotulo
    lbl.FontSize = 11
    lbl.Padding  = Thickness(0, 0, 0, 2)
    painel.Children.Add(lbl)

    txt = TextBox()
    txt.Height  = 23
    txt.Padding = Thickness(3, 2, 3, 2)
    txt.Margin  = Thickness(0, 0, 0, 2)
    txt.Text    = u"" if valor is None else u"{:g}".format(valor)
    painel.Children.Add(txt)
    if dica:
        _nota(painel, dica)
    return txt


def _campo_texto(rotulo, largura, valor_inicial=u""):
    """Retorna (container, TextBox) com um rótulo acima da caixa de texto."""
    campo = StackPanel()
    campo.Margin = Thickness(0, 0, 10, 0)

    lbl = Label()
    lbl.Content  = rotulo
    lbl.FontSize = 11
    lbl.Padding  = Thickness(0, 0, 0, 2)
    campo.Children.Add(lbl)

    txt = TextBox()
    txt.Width   = largura
    txt.Height  = 22
    txt.Text    = custom_store._txt(valor_inicial)
    txt.Padding = Thickness(3, 2, 3, 2)
    campo.Children.Add(txt)

    return campo, txt

def System_FontWeights_Bold():
    from System.Windows import FontWeights
    return FontWeights.Bold

class DataGridLength(object):
    """Wrapper leve para DataGridLength."""
    def __new__(cls, value, unit):
        from System.Windows.Controls import DataGridLength as _DGL
        return _DGL(value, unit)

class DataGridLengthUnitType_Star(object):
    def __new__(cls):
        from System.Windows.Controls import DataGridLengthUnitType
        return DataGridLengthUnitType.Star


# ---------------------------------------------------------------------------
# Função de alerta simples
# ---------------------------------------------------------------------------
def alert(msg):
    from System.Windows import MessageBox
    MessageBox.Show(msg, "Fire Utils", 0, 0)


# ---------------------------------------------------------------------------
# Função pública de uso no script principal
# ---------------------------------------------------------------------------
def show_system_selection_form(custom_inicial=None, metodo_inicial=None,
                               succao_inicial=None):
    """
    Abre o formulário de seleção de tipo de sistema.

    custom_inicial: dict de valores personalizados já salvos no projeto
                    (hidrantes.custom.load_custom) — pré-carrega os campos
                    e liga o modo personalizado.
    metodo_inicial: método de cálculo já salvo no projeto (um de
                    METODOS_CALCULO) — pré-seleciona o combo.
    succao_inicial: dict de dados de NPSH já salvos no projeto
                    (hidrantes.succao.load_dados) — pré-carrega o bloco
                    "Configurações Avançadas > NPSH".

    Retorna o dict descrito em HydrantSystemForm.get_result(), ou None se
    cancelado.
    """
    form = HydrantSystemForm(custom_inicial=custom_inicial,
                             metodo_inicial=metodo_inicial,
                             succao_inicial=succao_inicial)
    form.ShowDialog()
    return form.get_result()