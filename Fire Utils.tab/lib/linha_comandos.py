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

from pyrevit import forms
from Autodesk.Revit.DB import (
    TextNote, TextNoteOptions, Transaction, UnitUtils, CurveElement,
    HorizontalTextAlignment
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

from linha_limite_core import listar_estilos_de_linha, inserir_linha_com_limite
from comprimento_linha_config import (
    carregar as carregar_config, resolver_tipo_texto, abrir_configuracao,
)


def inserir_linha_com_limite_comando(doc, uidoc):
    view = uidoc.ActiveView

    estilos = listar_estilos_de_linha(doc)
    if not estilos:
        forms.alert(u"Nenhum estilo de linha encontrado no projeto.", exitscript=True)

    estilo_padrao, _prefixo_nao_usado, _tipo_texto_nao_usado = carregar_config(doc)
    if estilo_padrao and estilo_padrao in estilos:
        nome_escolhido = estilo_padrao
    else:
        nome_escolhido = forms.SelectFromList.show(
            sorted(estilos.keys()),
            title=u"Inserir Linha com Limite",
            prompt=u"Escolha o estilo da linha:",
            multiselect=False,
        )
        if not nome_escolhido:
            forms.alert(u"Nenhum estilo selecionado.", exitscript=True)

    comprimento_str = forms.ask_for_string(
        default=u"10",
        prompt=u"Comprimento máximo da linha (m):",
        title=u"Inserir Linha com Limite",
    )
    if not comprimento_str:
        forms.alert(u"Nenhum comprimento informado.", exitscript=True)

    try:
        comprimento_max = float(comprimento_str.replace(u",", u"."))
    except ValueError:
        comprimento_max = -1

    if comprimento_max <= 0:
        forms.alert(u"Comprimento inválido: {}".format(comprimento_str), exitscript=True)

    inserir_linha_com_limite(doc, uidoc, view, estilos[nome_escolhido], comprimento_max)


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
                forms.alert("Nenhuma linha selecionada.", exitscript=True)
            elements = [doc.GetElement(r.ElementId) for r in refs]

        _, prefixo, tipo_texto_nome = carregar_config(doc)
        tipo_texto_id = resolver_tipo_texto(doc, tipo_texto_nome)
        if tipo_texto_id is None:
            forms.alert("Nenhum estilo de texto (TextNoteType) encontrado.", exitscript=True)

        total_length = sum(get_length_meters(e) for e in elements)
        text_content = u"{}{:.2f} m".format(prefixo, total_length)

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
            forms.alert("Erro: {}".format(err))


def configurar_comando(doc, uidoc=None):
    abrir_configuracao(doc)
