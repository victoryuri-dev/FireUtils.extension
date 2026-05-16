# -*- coding: utf-8 -*-
# occupancy_forms.py — Forms

from saidas.get import get_opcoes_exibidas, notas_ocupacao
from pyrevit import forms, script

options = get_opcoes_exibidas()

def occupancy_forms():
    choice = forms.ask_for_one_item(
        options,
        default=options[0],
        prompt="Escolha uma opção: ",
        title="Ocupações"
    )

    if not choice:
        return script.exit()
    
    group = choice.split(" : ")[0]
    group_notes = notas_ocupacao(group)

    if group_notes:
        forms.alert(group_notes, title="Notas específicas:", warn_icon=True)

    return group