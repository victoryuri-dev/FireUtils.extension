# -*- coding: utf-8 -*-
__title__ = "Inserir Hidrante\npor Nível"

from pyrevit import script
from hydrant_insert_core import run

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

run(doc, uidoc, output, forcar_nivel=True)
