# -*- coding: utf-8 -*-
"""
succao_form.py — Fire Utils · lib/hidrantes/

Formulário WPF dos dados do reservatório usados na verificação da condição
de sucção pelo nível X (NT 22/2021, Anexo B.3 e item C.1.10).

Só entra aqui o que NÃO dá para ler da geometria do modelo. As cotas da
tomada e do eixo do rotor saem dos identificadores "RTI" e "Succao", o DN da
sucção sai do tubo, e o tipo de tomada é detectado da orientação do tubo e
de qual das suas pontas está aberta para a água — o combo de tipo de tomada
existe só para sobrepor essa leitura quando o desenho não representa a
tomada real.
"""

from __future__ import absolute_import

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import (
    Window, Thickness, HorizontalAlignment, ResizeMode, WindowStartupLocation
)
from System.Windows.Controls import (
    StackPanel, Label, TextBox, CheckBox, Button, ComboBox, ComboBoxItem,
    Orientation, TextBlock
)

from hidrantes import succao as succao_calc


_AUTO = u"Detectar pela geometria do modelo (recomendado)"

_OPCOES_TOMADA = [
    (None,                          _AUTO),
    (succao_calc.TOMADA_LATERAL,    u"Lateral — pela parede (Fig. B.1/B.2)"),
    (succao_calc.TOMADA_SUPERIOR,   u"Superior — por cima, tubo mergulhado"),
    (succao_calc.TOMADA_INFERIOR,   u"Inferior — pelo fundo (Fig. B.3)"),
]


def _rotulo(texto, tamanho=11, negrito=False):
    lbl = Label()
    lbl.Content  = texto
    lbl.FontSize = tamanho
    lbl.Padding  = Thickness(0, 0, 0, 2)
    if negrito:
        from System.Windows import FontWeights
        lbl.FontWeight = FontWeights.Bold
    return lbl


def _campo(painel, rotulo, valor, dica=u""):
    painel.Children.Add(_rotulo(rotulo))
    txt = TextBox()
    txt.Height  = 23
    txt.Padding = Thickness(3, 2, 3, 2)
    txt.Margin  = Thickness(0, 0, 0, 2)
    txt.Text    = u"" if valor is None else u"{:g}".format(valor)
    painel.Children.Add(txt)
    if dica:
        nota = TextBlock()
        nota.Text     = dica
        nota.FontSize = 10
        nota.Opacity  = 0.7
        nota.Margin   = Thickness(0, 0, 0, 10)
        nota.TextWrapping = 1   # TextWrapping.Wrap
        painel.Children.Add(nota)
    return txt


class SuccaoForm(Window):

    def __init__(self, dados_iniciais=None):
        self.resultado = None
        d = succao_calc.normalizar_dados(dados_iniciais or {})

        self.Title = u"Fire Utils — Condição de Sucção (Anexo B, NT 22)"
        self.Width  = 470
        self.SizeToContent = 2              # SizeToContent.Height
        self.ResizeMode = ResizeMode.NoResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen

        raiz = StackPanel()
        raiz.Margin = Thickness(16, 12, 16, 14)

        raiz.Children.Add(_rotulo(u"Dados do reservatório", 13, negrito=True))
        intro = TextBlock()
        intro.Text = (u"Usados para achar o nível X — o nível mínimo de água "
                      u"antes da formação de vórtice. As cotas da tomada e do "
                      u"eixo do rotor, o DN da sucção e o tipo de tomada saem "
                      u"da geometria do modelo.")
        intro.FontSize = 10
        intro.Opacity  = 0.75
        intro.TextWrapping = 1
        intro.Margin = Thickness(0, 0, 0, 12)
        raiz.Children.Add(intro)

        self.txt_fundo = _campo(
            raiz, u"Cota do fundo do reservatório (m)",
            d[u"cota_fundo_reservatorio"],
            u"Referência das cotas do projeto; normalmente 0.")

        self.txt_volume = _campo(
            raiz, u"Volume total do reservatório (m³)", d[u"volume_total_m3"],
            u"Opcional. Sem ele não dá para calcular a capacidade efetiva "
            u"(B.3.3) nem a tolerância do item C.1.10 — a verificação fica "
            u"no lado conservador.")

        self.txt_area = _campo(
            raiz, u"Área em planta do reservatório (m²)", d[u"area_planta_m2"],
            u"Opcional, mesma observação do volume.")

        raiz.Children.Add(_rotulo(u"Tipo de tomada de sucção"))
        self.cmb_tomada = ComboBox()
        self.cmb_tomada.Height = 23
        self.cmb_tomada.Margin = Thickness(0, 0, 0, 2)
        for _valor, rotulo in _OPCOES_TOMADA:
            item = ComboBoxItem()
            item.Content = rotulo
            self.cmb_tomada.Items.Add(item)
        self.cmb_tomada.SelectedIndex = next(
            (i for i, (v, _r) in enumerate(_OPCOES_TOMADA) if v == d[u"tipo_tomada"]), 0)
        raiz.Children.Add(self.cmb_tomada)

        nota_tomada = TextBlock()
        nota_tomada.Text = (u"Só mude se o desenho não representar a tomada "
                            u"real — a escolha manual tem precedência sobre a "
                            u"geometria.")
        nota_tomada.FontSize = 10
        nota_tomada.Opacity  = 0.7
        nota_tomada.TextWrapping = 1
        nota_tomada.Margin = Thickness(0, 0, 0, 12)
        raiz.Children.Add(nota_tomada)

        self.chk_antivortice = CheckBox()
        self.chk_antivortice.Content = u"Possui dispositivo antivórtice"
        self.chk_antivortice.IsChecked = d[u"possui_antivortice"]
        self.chk_antivortice.Margin = Thickness(0, 0, 0, 2)
        raiz.Children.Add(self.chk_antivortice)

        nota_av = TextBlock()
        nota_av.Text = (u"Dispensa a dimensão A da Tabela B.1, mas a norma só "
                        u"admite isso na tomada inferior (B.3.5/B.3.6).")
        nota_av.FontSize = 10
        nota_av.Opacity  = 0.7
        nota_av.TextWrapping = 1
        nota_av.Margin = Thickness(20, 0, 0, 10)
        raiz.Children.Add(nota_av)

        self.chk_poco = CheckBox()
        self.chk_poco.Content = u"Possui poço de sucção"
        self.chk_poco.IsChecked = d[u"possui_poco_succao"]
        self.chk_poco.Margin = Thickness(0, 0, 0, 16)
        raiz.Children.Add(self.chk_poco)

        botoes = StackPanel()
        botoes.Orientation = Orientation.Horizontal
        botoes.HorizontalAlignment = HorizontalAlignment.Right

        btn_ok = Button()
        btn_ok.Content = u"OK"
        btn_ok.Width, btn_ok.Height = 88, 26
        btn_ok.Margin = Thickness(0, 0, 8, 0)
        btn_ok.IsDefault = True
        btn_ok.Click += self._ok
        botoes.Children.Add(btn_ok)

        btn_cancel = Button()
        btn_cancel.Content = u"Cancelar"
        btn_cancel.Width, btn_cancel.Height = 88, 26
        btn_cancel.IsCancel = True
        btn_cancel.Click += self._cancelar
        botoes.Children.Add(btn_cancel)

        raiz.Children.Add(botoes)
        self.Content = raiz

    # -----------------------------------------------------------------
    def _numero(self, texto, rotulo, obrigatorio, erros):
        bruto = (texto or u"").strip().replace(u",", u".")
        if not bruto:
            if obrigatorio:
                erros.append(u"'{}' não foi informado.".format(rotulo))
            return None
        try:
            valor = float(bruto)
        except ValueError:
            erros.append(u"'{}' deve ser um número.".format(rotulo))
            return None
        if not obrigatorio and valor <= 0:
            erros.append(u"'{}' deve ser maior que zero.".format(rotulo))
            return None
        return valor

    def _ok(self, sender, args):
        erros = []
        fundo  = self._numero(self.txt_fundo.Text,  u"Cota do fundo do reservatório", True, erros)
        volume = self._numero(self.txt_volume.Text, u"Volume total do reservatório", False, erros)
        area   = self._numero(self.txt_area.Text,   u"Área em planta do reservatório", False, erros)

        if (volume is None) != (area is None):
            erros.append(u"Volume e área devem ser informados juntos — a "
                         u"capacidade efetiva depende dos dois.")

        if erros:
            from System.Windows import MessageBox
            MessageBox.Show(u"\n".join(erros), u"Fire Utils", 0, 0)
            return

        self.resultado = succao_calc.normalizar_dados({
            u"cota_fundo_reservatorio": fundo,
            u"volume_total_m3":         volume,
            u"area_planta_m2":          area,
            u"possui_antivortice":      bool(self.chk_antivortice.IsChecked),
            u"possui_poco_succao":      bool(self.chk_poco.IsChecked),
            u"tipo_tomada":             _OPCOES_TOMADA[self.cmb_tomada.SelectedIndex][0],
        })
        self.Close()

    def _cancelar(self, sender, args):
        self.resultado = None
        self.Close()


def show_succao_form(dados_iniciais=None):
    """Abre o formulário. Retorna o dict normalizado, ou None se cancelado."""
    form = SuccaoForm(dados_iniciais=dados_iniciais)
    form.ShowDialog()
    return form.resultado
