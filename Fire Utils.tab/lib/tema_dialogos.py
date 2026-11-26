# -*- coding: utf-8 -*-
"""
tema_dialogos.py — Fire Utils · lib/
Visual único para as caixas de diálogo WPF do plugin (mesmo das barras
flutuantes e do seletor de ocupação): fundo escuro azulado, moldura própria
sem a barra branca do Windows, campos e botões escuros.

Em vez de reescrever cada XAML, JanelaFireUtils lê o XAML original, troca as
cores das brushes que todos eles compartilham (BrushCard, BrushBorder...),
injeta os estilos escuros de ComboBox/TextBox e o template plano dos botões
(tema_dialogos_estilos.xaml) e, depois de carregar, embrulha o conteúdo numa
moldura com cabeçalho arrastável e botão fechar. Os handlers (on_ok,
on_closing...) e os elementos nomeados continuam os mesmos — as classes só
trocam a base forms.WPFWindow por JanelaFireUtils.

mensagem() substitui forms.alert por um aviso no mesmo visual.
"""

import os
import re
import sys
import tempfile

import clr
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

from pyrevit import forms

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_ESTILOS_PATH = os.path.join(_LIB_DIR, u"tema_dialogos_estilos.xaml")
_MENSAGEM_XAML = os.path.join(_LIB_DIR, u"mensagem_tema.xaml")

# Brushes dos XAMLs antigos (tema claro) -> cores escuras. BrushBranco fica
# branco: é o texto sobre o botão vermelho.
_CORES = {
    u"BrushCard": u"#17171C",
    u"BrushBorder": u"#2C2C33",
    u"BrushLabel": u"#87878D",
    u"BrushValor": u"#F5F5F7",
    u"BrushAccent": u"#C0152A",
    u"BrushCancela": u"#1D1E24",
    u"BrushOk": u"#3FB26B",
    u"BrushWarn": u"#E5604F",
}

# Template plano para os estilos de botão dos XAMLs antigos (Foreground e
# Background continuam vindo de cada botão; só some o visual nativo).
_TEMPLATE_BOTAO = (
    u'<Setter Property="Cursor" Value="Hand"/>'
    u'<Setter Property="Template"><Setter.Value>'
    u'<ControlTemplate TargetType="Button">'
    u'<Border x:Name="BdTema" Background="{TemplateBinding Background}" '
    u'BorderBrush="#2C2C33" BorderThickness="1">'
    u'<ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>'
    u'</Border><ControlTemplate.Triggers>'
    u'<Trigger Property="IsMouseOver" Value="True">'
    u'<Setter TargetName="BdTema" Property="BorderBrush" Value="#C0152A"/></Trigger>'
    u'<Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.4"/></Trigger>'
    u'</ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>'
)


def _ler(caminho):
    with open(caminho, u"rb") as arquivo:
        return arquivo.read().decode(u"utf-8")


def _tematizar(xaml):
    # Cores das brushes compartilhadas.
    for chave, cor in _CORES.items():
        xaml = re.sub(
            u'(<SolidColorBrush x:Key="{}"\\s+Color=")#[0-9A-Fa-f]{{6}}(")'.format(chave),
            lambda m, cor=cor: m.group(1) + cor + m.group(2), xaml)
    # Opção em formato de botão: fundo branco -> campo escuro.
    xaml = xaml.replace(u'<Border x:Name="Bd" Background="{StaticResource BrushBranco}"',
                        u'<Border x:Name="Bd" Background="{StaticResource BrushCard}"')
    # Janela sem moldura nativa e transparente (a moldura vem do Python).
    xaml = xaml.replace(u"<Window ", u'<Window WindowStyle="None" AllowsTransparency="True" ', 1)
    xaml = re.sub(u'(<Window\\b[^>]*?)Background="#[0-9A-Fa-f]{6}"', u'\\1Background="Transparent"', xaml, 1)
    # Botões planos.
    xaml = re.sub(u'(<Style x:Key="[A-Za-z]*Bot[A-Za-z]*Style" TargetType="Button">)',
                  lambda m: m.group(1) + _TEMPLATE_BOTAO, xaml)
    # Estilos escuros de ComboBox/TextBox.
    estilos = _ler(_ESTILOS_PATH)
    return xaml.replace(u"<Window.Resources>", u"<Window.Resources>" + estilos, 1)


class JanelaFireUtils(forms.WPFWindow):
    """forms.WPFWindow com o visual do plugin. `xaml_path` é o XAML original
    (tema claro); nada nele precisa mudar."""

    def __init__(self, xaml_path):
        xaml = _tematizar(_ler(xaml_path))
        fd, temporario = tempfile.mkstemp(suffix=u".xaml")
        try:
            os.write(fd, xaml.encode(u"utf-8"))
            os.close(fd)
            forms.WPFWindow.__init__(self, temporario)
        finally:
            try:
                os.remove(temporario)
            except Exception:
                pass
        self._aplicar_moldura()

    def _aplicar_moldura(self):
        from System.Windows import Thickness, HorizontalAlignment, VerticalAlignment, FontWeights
        from System.Windows.Controls import Border, Button, DockPanel, TextBlock, Dock
        from System.Windows.Media import SolidColorBrush, Color, Brushes
        from System.Windows.Input import Cursors

        def cor(texto):
            return SolidColorBrush(Color.FromRgb(int(texto[1:3], 16), int(texto[3:5], 16), int(texto[5:7], 16)))

        raiz = self.Content
        self.Content = None

        cabecalho = DockPanel()
        cabecalho.Background = Brushes.Transparent
        cabecalho.Cursor = Cursors.SizeAll
        cabecalho.Margin = Thickness(0, 0, 0, 0)

        fechar = Button()
        fechar.Content = u"✕"
        fechar.Width = 34
        fechar.Height = 30
        fechar.Background = Brushes.Transparent
        fechar.BorderThickness = Thickness(0)
        fechar.Foreground = cor(u"#F5F5F7")
        fechar.Cursor = Cursors.Hand
        fechar.ToolTip = u"Fechar"
        fechar.Click += lambda s, a: self.Close()
        DockPanel.SetDock(fechar, Dock.Right)
        cabecalho.Children.Add(fechar)

        titulo = TextBlock()
        titulo.Text = self.Title
        titulo.Foreground = cor(u"#87878D")
        titulo.FontSize = 11
        titulo.FontWeight = FontWeights.SemiBold
        titulo.VerticalAlignment = VerticalAlignment.Center
        titulo.Margin = Thickness(14, 0, 0, 0)
        cabecalho.Children.Add(titulo)

        def arrastar(sender, args):
            try:
                self.DragMove()
            except Exception:
                pass
        cabecalho.MouseLeftButtonDown += arrastar

        corpo = DockPanel()
        DockPanel.SetDock(cabecalho, Dock.Top)
        corpo.Children.Add(cabecalho)
        corpo.Children.Add(raiz)

        moldura = Border()
        moldura.Background = cor(u"#101014")
        moldura.BorderBrush = cor(u"#2C2C33")
        moldura.BorderThickness = Thickness(1)
        moldura.Child = corpo
        self.Content = moldura


class _JanelaMensagem(JanelaFireUtils):
    def __init__(self, texto, titulo, aviso):
        JanelaFireUtils.__init__(self, _MENSAGEM_XAML)
        self.Title = titulo
        self.TxtMensagem.Text = texto
        self.BtnOk.Click += lambda s, a: self.Close()


def mensagem(texto, titulo=u"FireUtils", aviso=False, sair=False):
    """Aviso modal no visual do plugin (no lugar de forms.alert). `sair`
    encerra o script em seguida, como forms.alert(exitscript=True)."""
    try:
        janela = _JanelaMensagem(texto, titulo, aviso)
        janela.ShowDialog()
    except Exception:
        forms.alert(texto, title=titulo, warn_icon=aviso)
    if sair:
        sys.exit()
