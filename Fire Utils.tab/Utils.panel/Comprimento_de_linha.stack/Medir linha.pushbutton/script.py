# -*- coding: utf-8 -*-
__title__ = "Medir comprimento de linhas"
__doc__ = "Exibe o comprimento total das linhas selecionadas."

from pyrevit import revit, forms
from Autodesk.Revit.DB import UnitUtils, CurveElement
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

doc = revit.doc
uidoc = revit.uidoc


def get_length_meters(element):
    length_feet = element.GeometryCurve.Length
    try:
        from Autodesk.Revit.DB import UnitTypeId
        return UnitUtils.ConvertFromInternalUnits(length_feet, UnitTypeId.Meters)
    except Exception:
        from Autodesk.Revit.DB import DisplayUnitType
        return UnitUtils.ConvertFromInternalUnits(length_feet, DisplayUnitType.DUT_METERS)


try:
    current_ids = uidoc.Selection.GetElementIds()
    elements = [doc.GetElement(eid) for eid in current_ids
                if isinstance(doc.GetElement(eid), CurveElement)]

    if not elements:
        forms.alert("Nenhuma linha selecionada.")
    else:
        total = sum(get_length_meters(e) for e in elements)
        qty = len(elements)
        forms.alert(
            "Comprimento total: {:.2f} m".format(total),
            title="Comprimento de Linha"
        )

except Exception as e:
    forms.alert("Erro: {}".format(str(e)))