# -*- coding: utf-8 -*-
__title__ = "Inserir\nHidrante"

# Trava de licenca: encerra o script se a conta nao tiver o modulo.
from licenca_guard import exigir
exigir(u"hidrantes")

from pyrevit import script
from hydrant_insert_core import run

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

run(doc, uidoc, output, forcar_nivel=False)
