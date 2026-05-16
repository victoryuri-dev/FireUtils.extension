# -*- coding: utf-8 -*-
__title__ = "Identificar \npor Ambiente"

from pyrevit import revit, script, forms
from populacao.forms import occupancy_forms
from populacao.utils import set_occupancy, garantir_parametros
from populacao.rooms import get_rooms_for_selection

doc = revit.doc

if not garantir_parametros():
    forms.alert("Nao foi possivel criar o parametro Populacao no projeto.")
    script.exit()

occupancy = occupancy_forms()
rooms = get_rooms_for_selection(doc)

if not occupancy:
    script.exit()
    
if rooms:
    set_occupancy(rooms, occupancy)