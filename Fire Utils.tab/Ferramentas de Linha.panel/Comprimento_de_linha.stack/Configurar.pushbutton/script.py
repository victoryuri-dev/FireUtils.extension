# -*- coding: utf-8 -*-
__title__ = "Configurar"
__doc__ = (
    "Pré-configura o estilo de linha padrão usado por \"Inserir Linha com "
    "Limite\" (pra não precisar escolher toda vez) e o texto inserido "
    "antes do valor do comprimento por \"Medir e Inserir Texto\" (hoje "
    "fixo em \"L = \")."
)

# Trava de licenca: as Ferramentas de Linha fazem parte do FireUtils BIM,
# exclusivo do PRO.
from licenca_guard import exigir
exigir(u"pro")

from pyrevit import revit
from comprimento_linha_config import abrir_configuracao

abrir_configuracao(revit.doc)
