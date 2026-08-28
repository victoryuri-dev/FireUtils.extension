# -*- coding: utf-8 -*-
"""
succao_form.py — Fire Utils · lib/hidrantes/

Formulário WPF dos dados usados no cálculo do NPSH disponível — a única
verificação de sucção que precisa de dado que não vem da geometria do
modelo nem da tabela de Cotas Altimétricas. A condição de sucção em si
(positiva/negativa) é decidida direto pela diferença entre a cota da RTI e
a cota de sucção da bomba, sem formulário próprio.
"""

from __future__ import absolute_import

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import (
    Window, Thickness, HorizontalAlignment, ResizeMode, WindowStartupLocation,
    SizeToContent, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, Label, TextBox, Button, ComboBox, ComboBoxItem,
    Orientation, TextBlock, ScrollViewer, ScrollBarVisibility, DockPanel, Dock
)

from hidrantes import succao as succao_calc
from hidrantes import npshd as npshd_calc


def _nota(painel, texto, recuo=0, base=10):
    """Linha de observação em corpo menor, abaixo de um campo."""
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
    painel.Children.Add(_rotulo(rotulo))
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
        _nota(painel, dica)
    return txt


class SuccaoForm(Window):

    def __init__(self, dados_iniciais=None):
        self.resultado = None
        d = succao_calc.normalizar_dados(dados_iniciais or {})

        self.Title = u"Fire Utils — NPSH Disponível"
        self.Width  = 490
        self.SizeToContent = SizeToContent.Height
        self.MaxHeight = 760
        self.ResizeMode = ResizeMode.NoResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen

        moldura = DockPanel()
        moldura.LastChildFill = True

        raiz = StackPanel()
        raiz.Margin = Thickness(16, 12, 16, 4)

        raiz.Children.Add(_rotulo(u"NPSH disponível", 13, negrito=True))
        intro = TextBlock()
        intro.Text = (u"Só é calculado quando a condição de sucção resultar "
                      u"negativa — cota de sucção da bomba acima da cota da "
                      u"RTI. Altitude e temperatura já vêm com o valor "
                      u"usual — trocar só pelas opções das tabelas de "
                      u"referência.")
        intro.FontSize = 10
        intro.Opacity  = 0.75
        intro.TextWrapping = TextWrapping.Wrap
        intro.Margin = Thickness(0, 0, 0, 12)
        raiz.Children.Add(intro)

        self.opc_altitude = [(alt, rot) for alt, _ha, rot
                             in npshd_calc.opcoes_altitude()]
        self.cmb_altitude = _combo(
            raiz, u"Altitude do local (pressão atmosférica, Ha)",
            self.opc_altitude,
            d[u"altitude_m"] if d[u"altitude_m"] is not None
            else npshd_calc.ALTITUDE_PADRAO)

        self.opc_temperatura = [(t, rot) for t, _h, rot
                                in npshd_calc.opcoes_temperatura()]
        self.cmb_temperatura = _combo(
            raiz, u"Temperatura da água (pressão de vapor, Hvp)",
            self.opc_temperatura,
            d[u"temperatura_c"] if d[u"temperatura_c"] is not None
            else npshd_calc.TEMPERATURA_PADRAO)

        self.txt_npshr = _campo(
            raiz, u"NPSH requerido pela bomba — NPSHr (mca)", d[u"npshr_m"],
            u"Dado de catálogo do fabricante. Sem bomba definida ainda, deixe "
            u"em branco: o memorial mostra o NPSHd e marca a comparação como "
            u"pendente.")

        botoes = StackPanel()
        botoes.Orientation = Orientation.Horizontal
        botoes.HorizontalAlignment = HorizontalAlignment.Right
        botoes.Margin = Thickness(16, 10, 16, 14)

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

        # Os botões ficam no rodapé, fora da área rolável, para não sumirem
        # quando a lista de campos passa da altura máxima da janela.
        DockPanel.SetDock(botoes, Dock.Bottom)
        moldura.Children.Add(botoes)

        rolagem = ScrollViewer()
        rolagem.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        rolagem.Content = raiz
        moldura.Children.Add(rolagem)

        self.Content = moldura

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
        npshr = self._numero(self.txt_npshr.Text, u"NPSH requerido pela bomba", False, erros)

        if erros:
            from System.Windows import MessageBox
            MessageBox.Show(u"\n".join(erros), u"Fire Utils", 0, 0)
            return

        self.resultado = succao_calc.normalizar_dados({
            u"altitude_m":    self.opc_altitude[self.cmb_altitude.SelectedIndex][0],
            u"temperatura_c": self.opc_temperatura[self.cmb_temperatura.SelectedIndex][0],
            u"npshr_m":       npshr,
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
