# -*- coding: utf-8 -*-
"""
hydrant_level.py — Fire Utils · lib/
Utilitários para obtenção do nível de referência para inserção de hidrantes.

Uso:
    from hydrant_level import get_nivel

    nivel, erro = get_nivel(doc, uidoc, forcar_selecao=False)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import FilteredElementCollector, Level
from pyrevit import forms


def selecionar_nivel(doc):
    """
    Exibe um seletor com todos os níveis do projeto (ordenados por elevação).
    Retorna (Level, None) em caso de sucesso ou (None, mensagem) se cancelado/erro.
    """
    niveis = sorted(
        FilteredElementCollector(doc).OfClass(Level).ToElements(),
        key=lambda l: l.Elevation
    )
    if not niveis:
        return None, u"Nenhum nível encontrado no projeto."

    nivel_map = {n.Name: n for n in niveis}
    nomes     = [n.Name for n in niveis]

    escolha = forms.SelectFromList.show(
        nomes,
        title=u"Fire Utils — Nível de Referência",
        prompt=u"Selecione o nível do piso (referência para 1,30 m do hidrante):",
        multiselect=False
    )

    if not escolha:
        return None, u"cancelado"

    return nivel_map[escolha], None


def get_nivel(doc, uidoc, forcar_selecao=False):
    """
    Retorna (Level, None) ou (None, erro_msg).

    forcar_selecao=False
        Tenta obter o GenLevel da vista ativa.
        Se não encontrar, abre o seletor como fallback.

    forcar_selecao=True
        Sempre abre o seletor — ignora a vista ativa.
    """
    if not forcar_selecao:
        try:
            nivel = doc.GetElement(uidoc.ActiveView.GenLevel.Id)
            if nivel:
                return nivel, None
        except Exception:
            pass
        # Fallback: abre o seletor
        return selecionar_nivel(doc)

    return selecionar_nivel(doc)
