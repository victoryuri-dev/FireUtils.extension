# -*- coding: utf-8 -*-
__title__ = "Conectar\nTubo"

# Trava de licenca: Ferramentas de Tubos sao parte do FireUtils BIM.
from licenca_guard import exigir
exigir(u"pro")

from pyrevit import script
from connect_pipe import run

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

run(doc, uidoc, output)
