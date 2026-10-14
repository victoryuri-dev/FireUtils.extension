# -*- coding: utf-8 -*-
__title__ = "Inserir Hidrante\npor Nível"
__doc__ = (
    "Cria uma coluna de hidrantes atravessando vários níveis de uma vez: "
    "escolha os níveis (e se quer abrigo de mangueira em cada um) num "
    "diálogo, clique a posição e a direção dos ramais, e a coluna inteira "
    "é criada numa tacada só."
)

from pyrevit import script
from hydrant_insert_core import run_coluna_multilevel

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

run_coluna_multilevel(doc, uidoc, output)
