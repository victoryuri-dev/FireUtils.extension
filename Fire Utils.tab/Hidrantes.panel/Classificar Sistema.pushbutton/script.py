# -*- coding: utf-8 -*-
"""
script.py — Classificar Sistema de Hidrante
Configuração inicial do sistema de hidrantes no projeto.

Fluxo:
  1. Criar e vincular os Shared Parameters no projeto
  2. Abrir formulário de seleção do Tipo de Sistema (Tabela 2 NT 22)
  3. Salvar o tipo escolhido no Project Information
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import Transaction
from pyrevit import forms, script

from hidrantes.params import create_hydrant_params, PROJECT_INFO_PARAM
from hidrantes.forms import show_system_selection_form
from hidrantes.db import SISTEMAS_HIDRANTE

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

output.print_md("# Fire Utils – Classificar Sistema de Hidrante")

# ===========================================================================
# ETAPA 1 — Criar parâmetros
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 1 — Parâmetros")

try:
    log = create_hydrant_params(doc)
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
# ETAPA 2 — Selecionar tipo de sistema
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 2 — Tipo de Sistema")

resultado = show_system_selection_form()

if resultado is None:
    output.print_md(u"⚠ Seleção cancelada pelo usuário.")
    script.exit()

tipo      = resultado["tipo"]
variante  = resultado["variante_idx"]
dados     = resultado["dados"]
descricao = SISTEMAS_HIDRANTE[tipo]["descricao"]

if len(SISTEMAS_HIDRANTE[tipo]["variantes"]) > 1:
    var_txt = u" – Var. {}".format(chr(65 + variante))
else:
    var_txt = u""

valor_param = u"Tipo {}{} – DN {} | {} L/min | {} mca".format(
    tipo, var_txt,
    dados["mangueira_dn"],
    dados["vazao_min"],
    dados["pressao_min"],
)

output.print_md(u"✔ Selecionado: **{}**".format(valor_param))

# ===========================================================================
# ETAPA 3 — Salvar no Project Information
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 3 — Project Information")

pi = doc.ProjectInformation

with Transaction(doc, "FireUtils - Definir Tipo de Sistema de Hidrante") as t:
    t.Start()
    try:
        param = pi.LookupParameter(PROJECT_INFO_PARAM)
        if param and not param.IsReadOnly:
            param.Set(valor_param)
            output.print_md(u"✔ Parâmetro salvo em Project Information.")
        else:
            output.print_md(
                u"⚠ Parâmetro '{}' não encontrado. "
                u"Reabra o projeto e execute novamente.".format(PROJECT_INFO_PARAM)
            )
        t.Commit()
    except Exception as e:
        t.RollBack()
        forms.alert(
            u"Erro ao salvar o tipo de sistema:\n{}".format(str(e)),
            title="Fire Utils – Erro",
            warn_icon=True
        )
        script.exit()

# ===========================================================================
# RESUMO FINAL
# ===========================================================================
output.print_md("---")
output.print_md(u"### ✔ Classificação concluída")
output.print_md(u"**Sistema:** {}".format(valor_param))
output.print_md(u"**Descrição:** {}".format(descricao))
output.print_md(u"**Vazão mín.:** {} L/min".format(dados["vazao_min"]))
output.print_md(u"**Pressão mín.:** {} mca".format(dados["pressao_min"]))
output.print_md(u"**Expedições:** {}".format(dados["num_expedicoes"]))
output.print_md(u"\n_Próximo passo: executar **Identificar Esguiços**._")