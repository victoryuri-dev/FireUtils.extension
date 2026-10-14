# -*- coding: utf-8 -*-
__title__ = "Conectar\nAbrigo\n(Preview)"

# Trava de licenca: encerra o script se a conta nao tiver o modulo.
from licenca_guard import exigir
exigir(u"hidrantes")

from pyrevit import script
from connect_shelter_core_preview import conectar_abrigo_preview

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

conectar_abrigo_preview(doc, uidoc, output)
