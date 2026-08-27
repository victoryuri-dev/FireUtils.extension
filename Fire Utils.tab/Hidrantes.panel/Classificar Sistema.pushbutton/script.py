# -*- coding: utf-8 -*-
"""
script.py — Classificar Sistema de Hidrante
Configuração inicial do sistema de hidrantes no projeto.

Fluxo:
  1. Criar e vincular os Shared Parameters no projeto
  2. Abrir formulário de seleção do Tipo de Sistema (Tabela 2 NT 22) ou de
     valores personalizados (fora da tabela)
  3. Selecionar o método de cálculo (Válvula do Hidrante / Ponta do
     Esguicho Regulável) — por enquanto só registrado; o motor de cálculo
     ('Dimensionar Hidrantes') ainda usa sempre o método da marcha com
     Fator K, independente dessa escolha
  4. Salvar tudo no Project Information — inclusive os valores
     personalizados (JSON), que ficam guardados no projeto para permitir
     reclassificar quantas vezes for preciso sem redigitar
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import Transaction
from pyrevit import forms, script

from hidrantes.params import (
    create_hydrant_params, PROJECT_INFO_PARAM, PROJECT_INFO_METODO_PARAM,
)
from hidrantes.forms import show_system_selection_form
from hidrantes.db import SISTEMAS_HIDRANTE
from hidrantes import custom as custom_store

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

# Valores personalizados já salvos neste projeto (se houver) pré-carregam o
# formulário, permitindo reclassificar sem redigitar tudo de novo.
custom_salvo = custom_store.load_custom(doc)
if custom_salvo:
    output.print_md(u"ℹ Valores personalizados encontrados no projeto — "
                    u"formulário pré-carregado.")

resultado = show_system_selection_form(custom_inicial=custom_salvo)

if resultado is None:
    output.print_md(u"⚠ Seleção cancelada pelo usuário.")
    script.exit()

tipo      = resultado["tipo"]
variante  = resultado["variante_idx"]
dados     = resultado["dados"]
descricao = resultado["descricao"]
eh_custom = resultado["custom"]

if eh_custom:
    valor_param = custom_store.descrever(resultado["custom_dados"])
else:
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
# ETAPA 3 — Selecionar método de cálculo
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 3 — Método de Cálculo")

METODOS_CALCULO = [u"Válvula do Hidrante", u"Ponta do Esguicho Regulável"]

metodo_param_atual = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
metodo_salvo = metodo_param_atual.AsString() if metodo_param_atual else None
if metodo_salvo:
    output.print_md(u"ℹ Método salvo atualmente neste projeto: **{}**".format(metodo_salvo))

metodo_calculo = forms.SelectFromList.show(
    METODOS_CALCULO,
    title=u"Fire Utils — Método de Cálculo",
    prompt=u"Selecione o método de cálculo do sistema de hidrantes:",
    multiselect=False
)
if not metodo_calculo:
    output.print_md(u"⚠ Seleção cancelada pelo usuário.")
    script.exit()

output.print_md(u"✔ Método selecionado: **{}**".format(metodo_calculo))
output.print_md(
    u"\nℹ _Por enquanto este valor é apenas registrado — o motor de cálculo "
    u"usado em **Dimensionar Hidrantes** ainda aplica sempre o método da "
    u"marcha com Fator K, independente da escolha acima._")

# ===========================================================================
# ETAPA 4 — Salvar no Project Information
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 4 — Project Information")

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

        param_metodo = pi.LookupParameter(PROJECT_INFO_METODO_PARAM)
        if param_metodo and not param_metodo.IsReadOnly:
            param_metodo.Set(metodo_calculo)
            output.print_md(u"✔ Método de cálculo salvo em Project Information.")
        else:
            output.print_md(
                u"⚠ Parâmetro '{}' não encontrado. "
                u"Reabra o projeto e execute novamente.".format(PROJECT_INFO_METODO_PARAM)
            )

        # Valores personalizados ficam gravados no projeto (JSON) para poder
        # reclassificar depois sem redigitar. Só sobrescreve quando a
        # classificação atual é personalizada — assim o custom anterior é
        # preservado mesmo que o usuário volte para um tipo da Tabela 2.
        if eh_custom:
            ok_custom, msg_custom = custom_store.save_custom(
                doc, resultado["custom_dados"])
            output.print_md(u"{} {}".format(u"✔" if ok_custom else u"⚠", msg_custom))

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
output.print_md(u"**Método de cálculo:** {}".format(metodo_calculo))
output.print_md(u"**Descrição:** {}".format(descricao))
output.print_md(u"**Vazão mín.:** {} L/min".format(dados["vazao_min"]))
output.print_md(u"**Pressão mín.:** {} mca".format(dados["pressao_min"]))
output.print_md(u"**Expedições:** {}".format(dados["num_expedicoes"]))
if eh_custom:
    output.print_md(u"**Esguicho DN:** {:g} mm".format(dados["esguicho_dn"]))
    output.print_md(u"**Comprimento da mangueira:** {:g} m".format(dados["mangueira_comp"]))
    output.print_md(
        u"\n⚠ _Classificação **fora da Tabela 2** da norma. Os valores acima "
        u"ficam salvos neste projeto e podem ser reeditados a qualquer momento "
        u"executando novamente este comando._")
output.print_md(u"\n_Próximo passo: executar **Identificar Esguiços**._")