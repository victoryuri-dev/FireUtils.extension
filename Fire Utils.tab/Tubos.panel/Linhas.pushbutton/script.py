# -*- coding: utf-8 -*-
__title__ = "Linhas"
__doc__ = (
    "Abre (ou fecha) a barra flutuante com as ferramentas de linha: inserir "
    "linha com limite, medir comprimento de linhas e configurar."
)

# Trava de licenca: as Ferramentas de Linha fazem parte do FireUtils BIM,
# exclusivo do PRO.
from licenca_guard import exigir
exigir(u"pro")

from ferramentas_flutuantes import alternar_pelo_botao

alternar_pelo_botao(__revit__, u"linha")
