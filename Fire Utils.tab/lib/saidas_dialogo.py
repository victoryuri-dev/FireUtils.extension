# -*- coding: utf-8 -*-
"""
saidas_dialogo.py — Fire Utils · lib/
Seletor de ocupação das ferramentas de Saídas em janela WPF própria: o mesmo
conteúdo do modal da dockpane (SaidasFerramentas.jsx — estrutura, grupo, tipo
com taxa/capacidades/notas e, por nível, a lista de níveis), mas sem depender
da dockpane aberta. Usado pela barra flutuante (ferramentas_flutuantes.py).

`pedir_ocupacao` é modal (ShowDialog): chamar na thread de API (a barra o faz
dentro da fila de ações) e devolve o pedido já no formato de
IDENTIFICAR_AMBIENTES (saidas_ocupacao_bridge.py), ou None se cancelado.
"""

import os

import clr
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

from pyrevit import forms

_XAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"saidas_dialogo.xaml")


class _JanelaOcupacao(forms.WPFWindow):
    def __init__(self, titulo, ajuda, opcoes, estruturas, pede_niveis):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.resultado = None
        self._grupos = opcoes.get(u"grupos") or []
        self._estruturas = estruturas
        self._checks_niveis = []
        self._notas = []

        self.TxtTitulo.Text = titulo
        self.TxtAjuda.Text = u"{} Ocupação ({}):".format(ajuda, opcoes.get(u"estadoNome", u""))

        for estrutura in estruturas:
            self.CbEstrutura.Items.Add(estrutura.get(u"nome") or u"")
        self.CbEstrutura.SelectedIndex = 0

        for grupo in self._grupos:
            self.CbGrupo.Items.Add(grupo[u"uso"])
        self.CbGrupo.SelectionChanged += self._ao_trocar_grupo
        self.CbTipo.SelectionChanged += self._ao_trocar_tipo
        self.CbTaxa.SelectionChanged += self._ao_trocar_taxa
        self._taxas = []
        self.CbGrupo.SelectedIndex = 0

        if pede_niveis:
            from System.Windows import Visibility
            from System.Windows.Controls import CheckBox
            from System.Windows import Thickness
            self.PainelNiveis.Visibility = Visibility.Visible
            niveis = opcoes.get(u"niveis") or []
            if not niveis:
                from System.Windows.Controls import TextBlock
                vazio = TextBlock()
                vazio.Text = u"Nenhum nível no projeto."
                self.ListaNiveis.Children.Add(vazio)
            for nome in niveis:
                caixa = CheckBox()
                caixa.Content = nome
                caixa.Foreground = self.FindResource(u"BrushTexto")
                caixa.Margin = Thickness(0, 2, 0, 2)
                self.ListaNiveis.Children.Add(caixa)
                self._checks_niveis.append(caixa)
        self._pede_niveis = pede_niveis

        self.TxtTitulo.MouseLeftButtonDown += self._ao_arrastar
        self.BtnCancelar.Click += lambda s, a: self.Close()
        self.BtnOk.Click += self._ao_confirmar
        self.BtnNotas.Click += self._ao_alternar_notas

    def _ao_arrastar(self, sender, args):
        try:
            self.DragMove()
        except Exception:
            pass

    def _itens_do_grupo(self):
        indice = self.CbGrupo.SelectedIndex
        return self._grupos[indice][u"itens"] if 0 <= indice < len(self._grupos) else []

    def _ao_trocar_grupo(self, sender, args):
        self.CbTipo.Items.Clear()
        for item in self._itens_do_grupo():
            descricao = item.get(u"descricao")
            self.CbTipo.Items.Add(u"{}  —  {}".format(item[u"codigo"], descricao) if descricao else item[u"codigo"])
        if self.CbTipo.Items.Count > 0:
            self.CbTipo.SelectedIndex = 0

    def _item_atual(self):
        itens = self._itens_do_grupo()
        indice = self.CbTipo.SelectedIndex
        return itens[indice] if 0 <= indice < len(itens) else None

    def _ao_trocar_tipo(self, sender, args):
        """Trocou a divisão: recarrega as taxas normativas dela e as notas."""
        item = self._item_atual()
        if item is None:
            return
        from System.Windows import Visibility
        self._taxas = item.get(u"taxas") or []
        self.CbTaxa.Items.Clear()
        for taxa in self._taxas:
            self.CbTaxa.Items.Add(taxa[u"rotulo"])
        if self.CbTaxa.Items.Count > 0:
            self.CbTaxa.SelectedIndex = 0

        self._notas = item.get(u"notas") or []
        self.BtnNotas.Visibility = Visibility.Visible if self._notas else Visibility.Collapsed
        self.TxtNotas.Text = u"\n\n".join(self._notas)
        self.TxtNotas.Visibility = Visibility.Collapsed
        self._atualizar_botao_notas()

    def _tipo_de_taxa(self):
        indice = self.CbTaxa.SelectedIndex
        return self._taxas[indice][u"tipo"] if 0 <= indice < len(self._taxas) else u"area"

    def _ao_trocar_taxa(self, sender, args):
        """Por área: a área vem do ambiente (campo travado). Assentos e
        população estimada não dependem da área: campo livre."""
        tipo = self._tipo_de_taxa()
        self.TxtValor.Text = u""
        if tipo == u"area":
            self.LblValor.Text = u"ÁREA (M²)"
            self.TxtValor.Text = u"Automática (do ambiente)"
            self.TxtValor.IsEnabled = False
        else:
            self.LblValor.Text = u"ASSENTOS (POR AMBIENTE)" if tipo == u"fixo" else u"POPULAÇÃO ESTIMADA (POR AMBIENTE)"
            self.TxtValor.IsEnabled = True

    def _atualizar_botao_notas(self):
        from System.Windows import Visibility
        aberta = self.TxtNotas.Visibility == Visibility.Visible
        self.BtnNotas.Content = u"{} Notas específicas ({})".format(u"▾" if aberta else u"▸", len(self._notas))

    def _ao_alternar_notas(self, sender, args):
        from System.Windows import Visibility
        aberta = self.TxtNotas.Visibility == Visibility.Visible
        self.TxtNotas.Visibility = Visibility.Collapsed if aberta else Visibility.Visible
        self._atualizar_botao_notas()

    def _ao_confirmar(self, sender, args):
        item = self._item_atual()
        indice = self.CbEstrutura.SelectedIndex
        if item is None or indice < 0:
            return
        tipo = self._tipo_de_taxa()
        populacao = None
        if tipo != u"area":
            texto = (self.TxtValor.Text or u"").strip()
            if not texto.isdigit():
                forms.alert(u"Informe um número inteiro (zero ou mais) no campo de valor.",
                            title=u"FireUtils", warn_icon=True)
                return
            populacao = int(texto)
        niveis = [c.Content for c in self._checks_niveis if c.IsChecked]
        if self._pede_niveis and not niveis:
            forms.alert(u"Escolha pelo menos um nível.", title=u"FireUtils", warn_icon=True)
            return
        self.resultado = {
            u"ocupacao": item[u"codigo"],
            u"estruturaNome": self._estruturas[indice].get(u"nome"),
            u"niveis": niveis,
            u"popTipo": tipo,
            u"populacao": populacao,
        }
        self.Close()


def pedir_ocupacao(uiapp, titulo, ajuda, opcoes, estruturas, pede_niveis):
    """Mostra o seletor (modal). Devolve {ocupacao, estruturaNome, niveis} ou
    None se o usuário cancelou."""
    janela = _JanelaOcupacao(titulo, ajuda, opcoes, estruturas, pede_niveis)
    try:
        from System.Windows.Interop import WindowInteropHelper
        WindowInteropHelper(janela).Owner = uiapp.MainWindowHandle
    except Exception:
        pass  # sem dona, a janela só não acompanha o Revit ao minimizar
    janela.ShowDialog()
    return janela.resultado
