# -*- coding: utf-8 -*-
__title__ = "Identificar \npor Nível"

import math
from pyrevit import revit, DB, script, forms
from populacao.utils import garantir_parametros, set_occupancy
from populacao.forms import occupancy_forms
from populacao.rooms import get_rooms_for_level

doc = revit.doc

if not garantir_parametros():
    forms.alert(
        "Nao foi possivel verificar os parametros necessarios.",
        title="Erro"
    )
    script.exit()

occupancy = occupancy_forms()
rooms = get_rooms_for_level(doc)

if not occupancy:
    script.exit()

if rooms:
    set_occupancy(rooms, occupancy)