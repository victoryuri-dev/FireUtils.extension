# -*- coding: utf-8 -*-
"""
script.py — Gravar Dados de Sinalização
Varre o modelo, identifica instâncias de placa de sinalização de
emergência (categoria "Dispositivos de Segurança" com o parâmetro de tipo
"Código da Placa" preenchido) e grava o quantitativo — por código de
placa, agregado por toda a estrutura, sem separar por pavimento — na
chave 'sinalizacao' do firedata.json, na pasta do projeto. Também envia o
resultado pro site (best-effort), escopado pela estrutura vinculada no
Dashboard (dockpane).

As famílias de sinalização deste escritório já trazem "Código da Placa"
embutido como parâmetro de Tipo — diferente do fluxo de Extintores,
nenhum parâmetro precisa ser criado/vinculado por este botão.

Fluxo:
  1. Coletar as instâncias de placa de sinalização
  2. Agregar por código de placa
  3. Gravar o resultado no firedata.json e enviar pro site
"""

import os

from pyrevit import forms, script

from sinalizacao.calc import coletar_itens, agrupar_por_placa, salvar_cache

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

output.print_md("# Fire Utils – Gravar Dados de Sinalização")

# ===========================================================================
# Pré-requisito — projeto salvo em disco
# ===========================================================================
if not doc.PathName:
    forms.alert(
        u"O projeto Revit não está salvo.\n\n"
        u"Salve o arquivo (.rvt) antes de prosseguir — os dados\n"
        u"de sinalização são gravados na pasta do projeto.",
        title=u"Fire Utils — Salve o projeto",
        warn_icon=True,
    )
    script.exit()

projeto_dir = os.path.dirname(doc.PathName)

# ===========================================================================
# ETAPA 1 — Coletar instâncias de placa de sinalização
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 1 — Coleta")

itens = coletar_itens(doc)

if not itens:
    forms.alert(
        u"Nenhuma placa de sinalização de emergência encontrada.\n\n"
        u"Verifique se as instâncias estão na categoria 'Dispositivos de "
        u"Segurança' e se o parâmetro de tipo 'Código da Placa' está "
        u"preenchido.",
        title=u"Fire Utils — Nenhuma placa encontrada",
        warn_icon=True,
    )
    script.exit()

agrupados = agrupar_por_placa(itens)
output.print_md(
    u"✔ {} placa(s) encontrada(s) — {} código(s) distinto(s).".format(
        len(itens), len(agrupados)
    )
)

# ===========================================================================
# ETAPA 2 — Gravar no firedata.json e enviar pro site
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 2 — firedata.json")

path = salvar_cache(agrupados, projeto_dir)
output.print_md(u"✔ Dados gravados em `{}`".format(path))

# ===========================================================================
# RESUMO FINAL
# ===========================================================================
output.print_md("---")
output.print_md(u"### ✔ Concluído")
for item in agrupados:
    output.print_md(u"- **{}** — {}".format(item[u"tipoPlaca"], item[u"quantidade"]))
