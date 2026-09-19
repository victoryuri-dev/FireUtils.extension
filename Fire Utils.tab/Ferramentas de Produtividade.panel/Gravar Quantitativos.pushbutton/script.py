# -*- coding: utf-8 -*-
"""
script.py — Gravar Quantitativos
Abre uma janela de seleção com todas as medidas de quantitativo
disponíveis (Extintores, Sinalização de Emergência, ...) e, para cada uma
marcada, coleta as instâncias do modelo, grava no firedata.json (na pasta
do projeto) e envia o resultado pro site (Supabase), escopado pela
estrutura vinculada no Dashboard (dockpane).

Substitui os antigos botões "Gravar Dados de Extintores" (Extintores.panel)
e "Gravar Dados de Sinalização" (Sinalizacao.panel), que faziam a mesma
coisa isoladamente — ver quantitativos_core.py pra lógica central e o
registro de medidas.
"""

from pyrevit import script

from quantitativos_core import gravar_quantitativos

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

gravar_quantitativos(doc, output)
