# -*- coding: utf-8 -*-
__title__ = "Posicionar\nAbrigos"

from pyrevit import script
from shelter_insert_core import posicionar_todos_abrigos

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

posicionar_todos_abrigos(doc, uidoc, output)
