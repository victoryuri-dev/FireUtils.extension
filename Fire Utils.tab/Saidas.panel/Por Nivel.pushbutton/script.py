# -*- coding: utf-8 -*-
__title__ = "Identificar \npor Nível"

from pyrevit import revit, DB, script, forms
from projeto import exigir_projeto_e_estado
from saidas.calc       import sincronizar_ambientes
from saidas.populacao  import garantir_parametros, set_occupancy
from saidas.ocupacao   import occupancy_forms
from saidas.rooms      import get_rooms_for_level, get_rooms_classificados

doc = revit.doc

if not garantir_parametros():
    forms.alert(
        u"Não foi possível verificar os parâmetros necessários.",
        title=u"Erro"
    )
    script.exit()

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

occupancy = occupancy_forms(estado=estado)
rooms = get_rooms_for_level(doc)

if not occupancy:
    script.exit()

if rooms:
    set_occupancy(rooms, occupancy, estado=estado)
    sincronizar_ambientes(get_rooms_classificados(doc), estado, projeto_dir)
