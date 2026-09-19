# -*- coding: utf-8 -*-
__title__ = "Inserir\nAlarme"

from pyrevit import script
from alarm_insert_core import inserir_alarmes

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

inserir_alarmes(doc, uidoc, output)
