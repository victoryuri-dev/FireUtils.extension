# -*- coding: utf-8 -*-
"""
script.py — Inserir Válvula do Hidrante
Carrega a família e ativa a inserção nativa no cursor do Revit.
"""

__title__ = "Inserir Valvula\ndo Hidrante"

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.UI import RevitCommandId, PostableCommand
from pyrevit import forms, script

from hydrant_family import garantir_valvula

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
uiapp = __revit__

# ---------------------------------------------------------------------------
# Garante que a família está carregada e ativa
# ---------------------------------------------------------------------------
simbolo, erro = garantir_valvula(doc)
if erro:
    forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
    script.exit()

# ---------------------------------------------------------------------------
# Dispara inserção nativa — família fica no cursor para o usuário posicionar
# ---------------------------------------------------------------------------
try:
    uiapp.PostCommand(
        RevitCommandId.LookupPostableCommandId(PostableCommand.PlaceComponent)
    )
except Exception:
    try:
        uidoc.PromptForFamilyInstancePlacement(simbolo)
    except Exception:
        pass  # Esc pressionado — encerra normalmente
