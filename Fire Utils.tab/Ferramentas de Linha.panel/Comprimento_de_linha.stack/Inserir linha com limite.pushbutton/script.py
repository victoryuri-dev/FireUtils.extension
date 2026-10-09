# -*- coding: utf-8 -*-
__title__ = "Inserir\nlinha com limite"
__doc__ = (
    "Desenha uma sequência de linhas (clique a clique) num estilo de linha "
    "escolhido, até um comprimento total máximo informado — o último "
    "segmento é encurtado automaticamente pra fechar exatamente no limite, "
    "em vez de ultrapassar."
)

from pyrevit import revit, forms
from linha_limite_core import listar_estilos_de_linha, inserir_linha_com_limite

doc = revit.doc
uidoc = revit.uidoc
view = uidoc.ActiveView

estilos = listar_estilos_de_linha(doc)
if not estilos:
    forms.alert(u"Nenhum estilo de linha encontrado no projeto.", exitscript=True)

nome_escolhido = forms.SelectFromList.show(
    sorted(estilos.keys()),
    title=u"Inserir Linha com Limite",
    prompt=u"Escolha o estilo da linha:",
    multiselect=False,
)
if not nome_escolhido:
    forms.alert(u"Nenhum estilo selecionado.", exitscript=True)

comprimento_str = forms.ask_for_string(
    default=u"10",
    prompt=u"Comprimento máximo da linha (m):",
    title=u"Inserir Linha com Limite",
)
if not comprimento_str:
    forms.alert(u"Nenhum comprimento informado.", exitscript=True)

try:
    comprimento_max = float(comprimento_str.replace(u",", u"."))
except ValueError:
    comprimento_max = -1

if comprimento_max <= 0:
    forms.alert(u"Comprimento inválido: {}".format(comprimento_str), exitscript=True)

inserir_linha_com_limite(doc, uidoc, view, estilos[nome_escolhido], comprimento_max)
