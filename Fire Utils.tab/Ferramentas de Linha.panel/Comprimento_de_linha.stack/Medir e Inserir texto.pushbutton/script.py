# -*- coding: utf-8 -*-
__title__ = "Inserir Comprimento de linhas"
__doc__ = "Calcula o comprimento total de linhas selecionadas ou permite nova seleção."

# Trava de licenca: as Ferramentas de Linha fazem parte do FireUtils BIM,
# exclusivo do PRO.
from licenca_guard import exigir
exigir(u"pro")

from linha_comandos import medir_e_inserir_texto_comando
from pyrevit import revit

medir_e_inserir_texto_comando(revit.doc, revit.uidoc)
