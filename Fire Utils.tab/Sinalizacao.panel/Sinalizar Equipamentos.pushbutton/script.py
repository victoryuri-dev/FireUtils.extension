# -*- coding: utf-8 -*-
__title__ = "Sinalizar\nEquipamentos"
__doc__ = (
    "Abre um painel de seleção com os tipos de placa de sinalização "
    "(Hidrantes - E8, Sirene - E1, Botoeira - E2, Extintores - E5) e "
    "insere a placa correspondente na mesma posição de cada equipamento "
    "já presente no projeto que ainda não estiver sinalizado. As "
    "famílias das placas vêm do catálogo do Supabase, carregadas apenas "
    "quando ainda não estiverem no projeto."
)

from pyrevit import script
from signage_insert_core import sinalizar_equipamentos

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

sinalizar_equipamentos(doc, uidoc, output)
