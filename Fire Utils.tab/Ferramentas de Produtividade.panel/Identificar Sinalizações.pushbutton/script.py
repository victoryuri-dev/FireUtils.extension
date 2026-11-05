# -*- coding: utf-8 -*-
__title__ = "Identificar\nSinalizações"
__doc__ = (
    "Faz o mesmo que o \"Identificar todos\" nativo do Revit, mas a "
    "chamada de detalhe (leader) de cada identificador sai na direção da "
    "face da sinalização, no sentido da face, em vez de sempre pra cima. "
    "Permite escolher as categorias, a família do identificador de cada "
    "uma, a distância e se vale só pra vista ativa ou pro projeto todo. "
    "Elementos já identificados são pulados."
)

# Trava de licenca: as Ferramentas de Produtividade sao exclusivas do PRO.
from licenca_guard import exigir
exigir(u"pro")

from pyrevit import script
from tag_signage_core import identificar_sinalizacoes

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

identificar_sinalizacoes(doc, uidoc, output)
