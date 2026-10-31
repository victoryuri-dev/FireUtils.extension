# -*- coding: utf-8 -*-
__title__ = "Inserir Hidrante\ncom Abrigo"

# Trava de licenca: Ferramentas de Tubos sao parte do FireUtils BIM.
from licenca_guard import exigir
exigir(u"pro")

from pyrevit import script
from hydrant_insert_core import run_com_abrigo

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

# Cliques (origem + direção) e diálogo de opções (orientação da válvula/
# ramal + lado do abrigo, com prévia ao vivo) acontecem dentro de
# run_com_abrigo(). A transação de criação também ocorre lá.
run_com_abrigo(doc, uidoc, output)
