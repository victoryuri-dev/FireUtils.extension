# -*- coding: utf-8 -*-
__title__ = u"Memorial\nDescritivo"

import os
from pyrevit import forms, script
from projeto import exigir_projeto_e_estado

doc = __revit__.ActiveUIDocument.Document
exigir_projeto_e_estado(doc, forms, script)

os.startfile(u"http://127.0.0.1:5000/dashboard")
