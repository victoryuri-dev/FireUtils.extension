# -*- coding: utf-8 -*-
__title__ = "Inserir\nlinha com limite"
__doc__ = (
    "Desenha uma sequência de linhas (clique a clique) num estilo de linha "
    "escolhido, até um comprimento total máximo informado — o último "
    "segmento é encurtado automaticamente pra fechar exatamente no limite, "
    "em vez de ultrapassar. Usa o estilo pré-configurado em \"Configurar\" "
    "quando houver um salvo; senão pede pra escolher, como antes."
)

# Trava de licenca: as Ferramentas de Linha fazem parte do FireUtils BIM,
# exclusivo do PRO.
from licenca_guard import exigir
exigir(u"pro")

from linha_comandos import inserir_linha_com_limite_comando
from pyrevit import revit

inserir_linha_com_limite_comando(revit.doc, revit.uidoc)
