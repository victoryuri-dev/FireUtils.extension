# -*- coding: utf-8 -*-
__title__ = "Inserir Comprimento de linhas"
__doc__ = "Calcula o comprimento total de linhas selecionadas ou permite nova seleção."

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    FilteredElementCollector, TextNoteType, TextNote, TextNoteOptions,
    Transaction, UnitUtils, CurveElement, HorizontalTextAlignment
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

doc = revit.doc
uidoc = revit.uidoc


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


def get_default_text_type():
    types = list(FilteredElementCollector(doc).OfClass(TextNoteType))
    if not types:
        forms.alert("Nenhum tipo de TextNote encontrado.", exitscript=True)
    return types[0].Id


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

    total_length = sum(get_length_meters(e) for e in elements)
    text_content = "L = {:.2f} m".format(total_length)

    insert_point = uidoc.Selection.PickPoint("Clique para inserir o texto")

    with Transaction(doc, "Inserir Comprimento de Linha") as t:
        t.Start()
        options = TextNoteOptions(get_default_text_type())
        options.HorizontalAlignment = HorizontalTextAlignment.Left
        TextNote.Create(doc, uidoc.ActiveView.Id, insert_point, text_content, options)
        t.Commit()

except Exception as e:
    err = str(e)
    if "Cancel" not in err and "cancel" not in err:
        forms.alert("Erro: {}".format(err))