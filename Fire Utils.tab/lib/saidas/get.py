# -*- coding: utf-8 -*-
# it11.py — Tabela IT 11 CBMSP
from saidas.db import IT, NOTAS_ESPECIFICAS

def get_ocupacao(key):
    return IT.get(key, None)

def get_grupo(key):
    return IT[key]["grupo"]

def notas_ocupacao(key):
    group_notes = IT[key]["notas"]
    notes_text = []
    for note in group_notes:
        notes_text.append(NOTAS_ESPECIFICAS[note])
    final_text = "\n\n".join(notes_text)

    return final_text

def get_codigos():
    return sorted(IT.keys())

def get_rate(key):
    return (IT[key]["A"], IT[key]["obs"])

def get_opcoes_exibidas():
    return [
        "{} : {}".format(k, IT[k]["obs"])
        for k in get_codigos()
]