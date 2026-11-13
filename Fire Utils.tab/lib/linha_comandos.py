# -*- coding: utf-8 -*-
"""
linha_comandos.py — Fire Utils · lib/
Comandos das Ferramentas de Linha (Comprimento de Linhas), em funções para que
o botão da faixa de opções e a barra flutuante (ferramentas_flutuantes.py)
rodem exatamente o mesmo código. Antes o corpo vivia nos script.py dos botões.

As funções encerram com SystemExit quando o usuário cancela/erra (forms.alert
com exitscript=True), como qualquer script do pyRevit; quem chama fora de um
script (a barra) trata isso.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os

from pyrevit import forms
from tema_dialogos import JanelaFireUtils, mensagem
from Autodesk.Revit.DB import (
    TextNote, TextNoteOptions, Transaction, UnitUtils, CurveElement,
    HorizontalTextAlignment
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

from linha_limite_core import listar_estilos_de_linha, inserir_linha_com_limite
from comprimento_linha_config import (
    carregar as carregar_config, resolver_tipo_texto, abrir_configuracao,
)


_XAML_LINHA_LIMITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"linha_limite_opcoes.xaml")


class _JanelaLinhaLimite(JanelaFireUtils):
    """Estilo da linha (só se não houver um padrão salvo em Configurar) e
    comprimento máximo, numa janela só — antes eram duas caixas nativas."""

    def __init__(self, nomes_estilos, estilo_padrao):
        JanelaFireUtils.__init__(self, _XAML_LINHA_LIMITE)
        self.resultado = None
        for nome in nomes_estilos:
            self.CmbEstilo.Items.Add(nome)
        self.CmbEstilo.SelectedIndex = 0
        if estilo_padrao:
            # Padrão salvo: não pergunta de novo, como antes.
            from System.Windows import Visibility
            self.CmbEstilo.SelectedItem = estilo_padrao
            self.SecaoEstilo.Visibility = Visibility.Collapsed
        self.TxtComprimento.Text = u"10"
        self.BtnCancelar.Click += lambda s, a: self.Close()
        self.BtnOk.Click += self._ao_confirmar
        self.TxtComprimento.Focus()
        self.TxtComprimento.SelectAll()

    def _ao_confirmar(self, sender, args):
        try:
            comprimento = float((self.TxtComprimento.Text or u"").replace(u",", u".").strip())
        except ValueError:
            comprimento = -1
        if comprimento <= 0:
            self.TxtErro.Text = u"Comprimento inválido: {}".format(self.TxtComprimento.Text)
            return
        self.resultado = (self.CmbEstilo.SelectedItem, comprimento)
        self.Close()


def inserir_linha_com_limite_comando(doc, uidoc):
    view = uidoc.ActiveView

    estilos = listar_estilos_de_linha(doc)
    if not estilos:
        mensagem(u"Nenhum estilo de linha encontrado no projeto.", aviso=True, sair=True)

    estilo_padrao, _prefixo_nao_usado, _tipo_texto_nao_usado = carregar_config(doc)
    if not (estilo_padrao and estilo_padrao in estilos):
        estilo_padrao = None

    janela = _JanelaLinhaLimite(sorted(estilos.keys()), estilo_padrao)
    janela.ShowDialog()
    if janela.resultado is None:
        return  # cancelado

    nome_escolhido, comprimento_max = janela.resultado
    inserir_linha_com_limite(doc, uidoc, view, estilos[nome_escolhido], comprimento_max)


_XAML_LINHA_MEDIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"linha_medida_opcoes.xaml")


class _JanelaLinhaMedida(JanelaFireUtils):
    """Mostra só o comprimento medido. Inserir segue para colocar o texto no
    desenho; Cancelar encerra sem inserir (quem só queria saber o valor)."""

    def __init__(self, comprimento_m):
        JanelaFireUtils.__init__(self, _XAML_LINHA_MEDIDA)
        self.inserir = False
        self.TxtComprimento.Text = u"{:.2f} m".format(comprimento_m)
        self.BtnCancelar.Click += lambda s, a: self.Close()
        self.BtnInserir.Click += self._ao_inserir

    def _ao_inserir(self, sender, args):
        self.inserir = True
        self.Close()


class LineSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, CurveElement)

    def AllowReference(self, reference, point):
        return True


def get_length_meters(element):
    length_feet = element.GeometryCurve.Length
    try:
        from Autodesk.Revit.DB import UnitTypeId
        return UnitUtils.ConvertFromInternalUnits(length_feet, UnitTypeId.Meters)
    except Exception:
        from Autodesk.Revit.DB import DisplayUnitType
        return UnitUtils.ConvertFromInternalUnits(length_feet, DisplayUnitType.DUT_METERS)


def medir_e_inserir_texto_comando(doc, uidoc):
    try:
        # Verifica seleção prévia
        current_ids = uidoc.Selection.GetElementIds()
        pre_selected = [doc.GetElement(eid) for eid in current_ids
                        if isinstance(doc.GetElement(eid), CurveElement)]

        if pre_selected:
            elements = pre_selected
        else:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, LineSelectionFilter(),
                "Selecione as linhas (ENTER para confirmar)"
            )
            if not refs:
                mensagem(u"Nenhuma linha selecionada.", aviso=True, sair=True)
            elements = [doc.GetElement(r.ElementId) for r in refs]

        _, prefixo, tipo_texto_nome = carregar_config(doc)
        tipo_texto_id = resolver_tipo_texto(doc, tipo_texto_nome)
        if tipo_texto_id is None:
            mensagem(u"Nenhum estilo de texto (TextNoteType) encontrado.", aviso=True, sair=True)

        total_length = sum(get_length_meters(e) for e in elements)
        text_content = u"{}{:.2f} m".format(prefixo, total_length)

        medida = _JanelaLinhaMedida(total_length)
        medida.ShowDialog()
        if not medida.inserir:
            return

        insert_point = uidoc.Selection.PickPoint("Clique para inserir o texto")

        with Transaction(doc, "Inserir Comprimento de Linha") as t:
            t.Start()
            options = TextNoteOptions(tipo_texto_id)
            options.HorizontalAlignment = HorizontalTextAlignment.Left
            TextNote.Create(doc, uidoc.ActiveView.Id, insert_point, text_content, options)
            t.Commit()

    except Exception as e:
        err = str(e)
        if "Cancel" not in err and "cancel" not in err:
            mensagem(u"Erro: {}".format(err), aviso=True)


def configurar_comando(doc, uidoc=None):
    abrir_configuracao(doc)
