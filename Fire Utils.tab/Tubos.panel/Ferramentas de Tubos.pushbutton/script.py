# -*- coding: utf-8 -*-
__title__ = "Ferramentas\nde Tubos"
__doc__ = (
    "Abre (ou fecha) a barra flutuante com as ferramentas de tubos: inserir "
    "hidrante por nível, conectar abrigo e conectar tubo. A barra fica acima "
    "do Revit, pode ser arrastada e reduzida a só ícones."
)

# Trava de licenca: Ferramentas de Tubos sao parte do FireUtils BIM.
from licenca_guard import exigir
exigir(u"pro")

from ferramentas_flutuantes import alternar_pelo_botao

alternar_pelo_botao(__revit__, u"tubos")
