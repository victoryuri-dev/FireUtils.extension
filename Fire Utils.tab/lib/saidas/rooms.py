# -*- coding: utf-8 -*-
# saidas/rooms.py — Fire Utils
# Funções de coleta de ambientes (Room) do modelo Revit.

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.DB import Architecture, FilteredElementCollector
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter


class FiltroAmbiente(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, Architecture.Room)
    def AllowReference(self, reference, point):
        return False


def get_rooms_for_selection(doc):
    """Pede ao usuário que selecione ambientes no modelo. Retorna lista de Room."""
    uidoc = revit.uidoc
    forms.alert(
        u"Selecione os ambientes no modelo e clique em Concluir.",
        title=u"Instrução",
        ok=True
    )
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            FiltroAmbiente(),
            u"Selecione os ambientes e pressione ENTER para confirmar"
        )
        return [doc.GetElement(ref.ElementId) for ref in refs]
    except Exception:
        forms.alert(u"Seleção cancelada!", title=u"Aviso")
        return []


def get_all_rooms(doc):
    """Retorna todos os ambientes com área > 0."""
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .ToElements()
    return [r for r in colecao if r.Area > 0]


def get_rooms_sem_grupo(doc):
    """Retorna ambientes com área > 0 que ainda não têm o parâmetro 'Grupo' preenchido."""
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .ToElements()
    resultado = []
    for r in colecao:
        if r.Area > 0:
            param = r.LookupParameter(u"Grupo")
            if param:
                valor = param.AsString()
                if not valor:   # None ou string vazia
                    resultado.append(r)
    return resultado


def get_rooms_for_level(doc):
    """Abre diálogo de seleção de níveis e retorna os ambientes dos níveis escolhidos."""
    niveis = DB.FilteredElementCollector(doc)\
               .OfClass(DB.Level)\
               .ToElements()
    niveis = sorted(niveis, key=lambda l: l.Elevation)

    if not niveis:
        forms.alert(u"Nenhum nível encontrado no projeto.")
        script.exit()

    nomes_niveis = [n.Name for n in niveis]
    niveis_selecionados = forms.SelectFromList.show(
        nomes_niveis,
        title=u"Selecione os Níveis",
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
        forms.alert(u"Nenhum ambiente encontrado nos níveis selecionados.")
        script.exit()

    return rooms_filtrados
