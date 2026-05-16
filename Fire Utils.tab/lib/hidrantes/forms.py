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
    ResizeMode, WindowStartupLocation
)
from System.Windows.Controls import (
    Grid, StackPanel, Label, ComboBox, ComboBoxItem,
    Button, DataGrid, DataGridTextColumn, ScrollViewer,
    Orientation, DataGridSelectionMode, DataGridSelectionUnit
)
from System.Windows import GridLength, GridUnitType
from System.Windows.Media import SolidColorBrush, Color
from System.Collections.ObjectModel import ObservableCollection
from System import String

from hidrantes.db import SISTEMAS_HIDRANTE, get_todos_tipos


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

    def __init__(self):
        self.Title  = "Fire Utils – Tipo de Sistema de Hidrante (NT 22)"
        self.Width  = 780
        self.Height = 460
        self.ResizeMode = ResizeMode.CanResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen

        self.selected_tipo     = None
        self.selected_variante = None

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = StackPanel()
        root.Margin = Thickness(14)

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
        self._lbl_sel.Margin   = Thickness(0, 0, 0, 10)
        root.Children.Add(self._lbl_sel)

        # Botões
        btn_panel = StackPanel()
        btn_panel.Orientation = Orientation.Horizontal
        btn_panel.HorizontalAlignment = HorizontalAlignment.Right

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
        root.Children.Add(btn_panel)

        self.Content = root

    # ------------------------------------------------------------------
    def _on_grid_selection(self, sender, args):
        row = self._grid.SelectedItem
        if row is None:
            self._lbl_sel.Content = "Nenhum tipo selecionado."
            self.selected_tipo     = None
            self.selected_variante = None
            return

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
        if self.selected_tipo is None:
            alert("Selecione um tipo de sistema antes de confirmar.")
            return
        self.DialogResult = True
        self.Close()

    def _on_cancel(self, sender, args):
        self.selected_tipo     = None
        self.selected_variante = None
        self.DialogResult = False
        self.Close()

    # ------------------------------------------------------------------
    def get_result(self):
        """
        Retorna dict com os dados do sistema escolhido, ou None se cancelado.
        {
            "tipo": int,
            "variante_idx": int,
            "dados": dict   # variante completa de SISTEMAS_HIDRANTE
        }
        """
        if self.selected_tipo is None:
            return None
        dados = SISTEMAS_HIDRANTE[self.selected_tipo]
        return {
            "tipo":         self.selected_tipo,
            "variante_idx": self.selected_variante,
            "dados":        dados["variantes"][self.selected_variante],
        }


# ---------------------------------------------------------------------------
# Helpers de WPF (contornam limitações de import direto no IronPython)
# ---------------------------------------------------------------------------
def _make_binding(path):
    from System.Windows.Data import Binding
    b = Binding(path)
    return b

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
def show_system_selection_form():
    """
    Abre o formulário de seleção de tipo de sistema.
    Retorna dict com {tipo, variante_idx, dados} ou None se cancelado.
    """
    form = HydrantSystemForm()
    form.ShowDialog()
    return form.get_result()