# -*- coding: utf-8 -*-
__title__ = "Conectar\nAbrigo"

from pyrevit import script
from connect_shelter_core import conectar_abrigo

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

conectar_abrigo(doc, uidoc, output)
