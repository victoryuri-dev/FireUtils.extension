# -*- coding: utf-8 -*-
"""
script.py — Gravar Dados de Extintores
Varre o modelo, identifica instâncias de extintor (categoria Proteção
contra Incêndio com o parâmetro "Capacidade Extintora" preenchido — de
instância ou de tipo) e grava os dados na chave 'extintores' do
firedata.json, na pasta do projeto.

Fluxo:
  1. Criar e vincular os Shared Parameters que ainda faltam (Estrutura,
     Ambiente) — os demais (Tipo, Formato, Capacidade Extintora, Carga) já
     existem nas famílias de extintor
  2. Coletar as instâncias identificadas como extintor
  3. Gravar o resultado no firedata.json
"""

import os

from pyrevit import forms, script

from extintores.params import create_extinguisher_params
from extintores.calc import coletar_itens, salvar_cache

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

output.print_md("# Fire Utils – Gravar Dados de Extintores")

# ===========================================================================
# Pré-requisito — projeto salvo em disco
# ===========================================================================
if not doc.PathName:
    forms.alert(
        u"O projeto Revit não está salvo.\n\n"
        u"Salve o arquivo (.rvt) antes de prosseguir — os dados\n"
        u"de extintores são gravados na pasta do projeto.",
        title=u"Fire Utils — Salve o projeto",
        warn_icon=True,
    )
    script.exit()

projeto_dir = os.path.dirname(doc.PathName)

# ===========================================================================
# ETAPA 1 — Criar parâmetros
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 1 — Parâmetros")

try:
    log = create_extinguisher_params(doc)
    for nome, status in log:
        icon = u"✔" if status == "criado" else u"–"
        output.print_md(u"  {} `{}` → *{}*".format(icon, nome, status))
except Exception as e:
    forms.alert(
        u"Erro ao criar parâmetros:\n{}".format(str(e)),
        title="Fire Utils – Erro",
        warn_icon=True
    )
    script.exit()

# ===========================================================================
# ETAPA 2 — Coletar instâncias de extintor
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 2 — Coleta")

itens = coletar_itens(doc)

if not itens:
    forms.alert(
        u"Nenhum extintor encontrado.\n\n"
        u"Verifique se as instâncias estão na categoria 'Proteção contra "
        u"Incêndio' e se o parâmetro 'Capacidade Extintora' (instância ou "
        u"tipo) está preenchido.",
        title=u"Fire Utils — Nenhum extintor encontrado",
        warn_icon=True,
    )
    script.exit()

output.print_md(u"✔ {} extintor(es) encontrado(s).".format(len(itens)))

# ===========================================================================
# ETAPA 3 — Gravar no firedata.json
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 3 — firedata.json")

path = salvar_cache(itens, projeto_dir)
output.print_md(u"✔ Dados gravados em `{}`".format(path))

# ===========================================================================
# RESUMO FINAL
# ===========================================================================
output.print_md("---")
output.print_md(u"### ✔ Concluído")
for item in itens:
    output.print_md(
        u"- **{}** | {} | {} | {} {}".format(
            item[u"pavimento"] or u"(sem pavimento)",
            item[u"ambiente"] or u"(sem ambiente)",
            item[u"tipo"] or u"(sem tipo)",
            item[u"capacidade"],
            u"({} kg)".format(item[u"carga"]) if item[u"carga"] is not None else u"",
        )
    )
