# -*- coding: utf-8 -*-
# get_rooms.py - Rooms

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.DB import Architecture, FilteredElementCollector
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

class FiltroAmbiente(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, Architecture.Room)
    def AllowReference(self, reference, point):
        return False

def get_rooms_for_selection(doc):
    
    uidoc = revit.uidoc
    
    forms.alert(
        "Selecione os ambientes no modelo e clique em Concluir.",
        title="Instrução",
        ok=True
    )
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            FiltroAmbiente(),
            "Selecione os ambientes e pressione ENTER para confirmar"
        )
        return [doc.GetElement(ref.ElementId) for ref in refs]
    
    except Exception:
        forms.alert("Seleção cancelada!", title="Aviso")
        return []

def get_all_rooms(doc):
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .ToElements()

    return [r for r in colecao if r.Area > 0]

def get_rooms_sem_grupo(doc):
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .ToElements()

    rooms_sem_grupo = []

    for r in colecao:
        if r.Area > 0:
            param = r.LookupParameter("Grupo")
            
            # Verifica se o parâmetro existe e está vazio
            if param:
                valor = param.AsString()
                if not valor:  # None ou string vazia
                    rooms_sem_grupo.append(r)

    return rooms_sem_grupo

def get_rooms_for_level(doc):
    niveis = DB.FilteredElementCollector(doc)\
           .OfClass(DB.Level)\
           .ToElements()

    niveis = sorted(niveis, key=lambda l: l.Elevation)

    if not niveis:
        forms.alert("Nenhum nivel encontrado no projeto.")
        script.exit()

    nomes_niveis = [n.Name for n in niveis]
    niveis_selecionados = forms.SelectFromList.show(
        nomes_niveis,
        title="Selecione os Niveis",
        multiselect=True
    )
    if not niveis_selecionados:
        script.exit()
    todos_rooms = DB.FilteredElementCollector(doc)\
            .OfCategory(DB.BuiltInCategory.OST_Rooms)\
            .ToElements()
    rooms_filtrados = []
    for room in todos_rooms:
        area = room.get_Parameter(DB.BuiltInParameter.ROOM_AREA).AsDouble()
        if area == 0:
            continue
        if room.Level and room.Level.Name in niveis_selecionados:
            rooms_filtrados.append(room)
    if not rooms_filtrados:
        forms.alert(
            "Nenhum ambiente encontrado nos niveis selecionados."
        )
        script.exit()
    
    return rooms_filtrados

