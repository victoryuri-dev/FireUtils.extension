# -*- coding: utf-8 -*-
__title__ = "População"
__doc__ = (
    "Abre (ou fecha) a barra flutuante com as ferramentas de ocupação e "
    "população dos ambientes: identificar por ambiente, por nível, todos sem "
    "ocupação e sincronizar ambientes."
)

# A licença do módulo Saídas é conferida pela própria ferramenta ao rodar
# (saidas_ocupacao_bridge), com o aviso de cada situação.
from ferramentas_flutuantes import alternar_pelo_botao

alternar_pelo_botao(__revit__, u"saidas")
