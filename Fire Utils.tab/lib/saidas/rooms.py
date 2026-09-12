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


def get_rooms_com_grupo(doc):
    """Retorna ambientes com área > 0 e o parâmetro 'Grupo' já preenchido —
    usado por populacao.recalcular_populacao pra reaplicar a taxa
    normativa ATUAL (útil quando a norma/UF do projeto muda depois que os
    ambientes já foram classificados: a população gravada nos parâmetros
    fica com o valor antigo até alguém rodar esse recálculo)."""
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .ToElements()
    resultado = []
    for r in colecao:
        if r.Area > 0:
            param = r.LookupParameter(u"Grupo")
            if param and param.AsString():
                resultado.append(r)
    return resultado


def get_rooms_classificados(doc):
    """Retorna todos os ambientes com área > 0 e o parâmetro 'Grupo'
    preenchido, já no formato pronto pra sincronizar com o site (ver
    saidas.calc.montar_payload_ambientes): dicts {nivel, nome, grupo,
    area (m²), pop, uid}.

    `uid` é o Room.UniqueId do Revit — persiste mesmo se o ambiente for
    renomeado/renumerado (reclassificação) ou tiver a área alterada depois.
    O site/dockpane casa ambientes primeiro por esse id (ver
    resolverImportacaoSaidas), então uma reclassificação ou uma edição de
    área no Revit sempre ATUALIZA o mesmo ambiente lá — nunca cria um
    duplicado nem perde a posição dele na árvore de Acessos/Saídas."""
    colecao = FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Rooms)\
        .WhereElementIsNotElementType()\
        .ToElements()

    resultado = []
    for room in colecao:
        try:
            if room.Area == 0:
                continue

            p_grupo = room.LookupParameter(u"Grupo")
            grupo   = p_grupo.AsString() if (p_grupo and p_grupo.HasValue) else None
            if not grupo:
                continue

            p_pop  = room.LookupParameter(u"População")
            p_nome = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME)
            p_area = room.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
            nivel  = room.Level.Name if room.Level else u"(sem nível)"

            resultado.append({
                u"nivel": nivel,
                u"nome":  p_nome.AsString() if (p_nome and p_nome.HasValue) else u"(sem nome)",
                u"grupo": grupo,
                u"area":  round(p_area.AsDouble() * 0.092903, 3) if p_area else 0.0,
                u"pop":   int(p_pop.AsInteger()) if (p_pop and p_pop.HasValue) else 0,
                u"uid":   room.UniqueId,
            })
        except Exception:
            continue

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
