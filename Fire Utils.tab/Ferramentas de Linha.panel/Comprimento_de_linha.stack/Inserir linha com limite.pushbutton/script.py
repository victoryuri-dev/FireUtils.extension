# -*- coding: utf-8 -*-
__title__ = "Inserir\nlinha com limite"
__doc__ = (
    "Abre um painel (não bloqueia a view do projeto) para escolher o "
    "estilo de linha e o comprimento máximo do trecho. Depois de "
    "confirmar, desenhe as linhas normalmente com a ferramenta padrão do "
    "Revit — o painel acompanha o comprimento total em tempo real e "
    "permite Cancelar (desfaz tudo), Finalizar (mantém como está) ou "
    "Finalizar e Limitar (encurta o último trecho pra fechar exatamente "
    "no limite configurado)."
)

from pyrevit import revit
from linha_limite_core import abrir_painel_linha_com_limite

abrir_painel_linha_com_limite(revit.doc, revit.uidoc)
