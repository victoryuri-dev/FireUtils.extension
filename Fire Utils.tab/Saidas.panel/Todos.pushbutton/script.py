# -*- coding: utf-8 -*-
__title__ = "Identificar Todos\nsem Ocupação"

from pyrevit import revit, script, forms
from projeto import exigir_projeto_e_estado
from saidas.calc       import sincronizar_ambientes
from saidas.ocupacao   import occupancy_forms
from saidas.populacao  import set_occupancy, garantir_parametros
from saidas.rooms      import get_rooms_sem_grupo, get_rooms_classificados

doc = revit.doc

if not garantir_parametros():
    forms.alert(u"Não foi possível criar o parâmetro População no projeto.")
    script.exit()

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

occupancy = occupancy_forms(estado=estado)
rooms = get_rooms_sem_grupo(doc)

if not occupancy:
    script.exit()

if rooms:
    set_occupancy(rooms, occupancy, estado=estado)
    sincronizar_ambientes(get_rooms_classificados(doc), estado, projeto_dir)
