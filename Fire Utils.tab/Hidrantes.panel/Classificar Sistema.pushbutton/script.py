# -*- coding: utf-8 -*-
"""
script.py — Classificar Sistema de Hidrante
Configuração inicial do sistema de hidrantes no projeto.

Fluxo:
  1. Criar e vincular os Shared Parameters no projeto
  2. Abrir formulário único de classificação (hidrantes/forms.py): tipo de
     sistema (Tabela 2 NT 22) ou valores personalizados, e método de
     cálculo (Válvula do Hidrante / Ponta do Esguicho Regulável) — este
     último por enquanto só registrado; o motor de cálculo ('Dimensionar
     Hidrantes') ainda usa sempre o método da marcha com Fator K,
     independente dessa escolha
  3. Salvar tudo no Project Information — inclusive os valores
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
from hidrantes.succao_form import show_succao_form
from hidrantes.db import SISTEMAS_HIDRANTE
from hidrantes import custom as custom_store
from hidrantes import succao as succao_calc

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
# ETAPA 2 — Selecionar tipo de sistema e método de cálculo
# ===========================================================================
output.print_md("---")
output.print_md("### Etapa 2 — Tipo de Sistema e Método de Cálculo")

# Valores personalizados e método de cálculo já salvos neste projeto (se
# houver) pré-carregam o formulário, permitindo reclassificar sem
# redigitar/reselecionar tudo de novo.
custom_salvo = custom_store.load_custom(doc)
if custom_salvo:
    output.print_md(u"ℹ Valores personalizados encontrados no projeto — "
                    u"formulário pré-carregado.")

metodo_param_atual = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
metodo_salvo = metodo_param_atual.AsString() if metodo_param_atual else None

resultado = show_system_selection_form(custom_inicial=custom_salvo,
                                       metodo_inicial=metodo_salvo)

if resultado is None:
    output.print_md(u"⚠ Seleção cancelada pelo usuário.")
    script.exit()

tipo           = resultado["tipo"]
variante       = resultado["variante_idx"]
dados          = resultado["dados"]
descricao      = resultado["descricao"]
eh_custom      = resultado["custom"]
metodo_calculo = resultado["metodo_calculo"]

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
output.print_md(u"✔ Método de cálculo: **{}**".format(metodo_calculo))
output.print_md(
    u"\nℹ _Por enquanto o método de cálculo é apenas registrado — o motor "
    u"usado em **Dimensionar Hidrantes** ainda aplica sempre o método da "
    u"marcha com Fator K, independente da escolha acima._")

# ===========================================================================
# ETAPA 2b — Dados do NPSH disponível
# ===========================================================================
output.print_md("---")
output.print_md(u"### Etapa 2b — NPSH Disponível")

# A condição de sucção (positiva/negativa) é decidida em "Dimensionar
# Hidrantes" pela diferença direta entre a cota da RTI e a cota de sucção da
# bomba — não depende de dado nenhum daqui. Só entra aqui o que o cálculo do
# NPSH disponível precisa e que não vem da geometria.
succao_salvo = succao_calc.load_dados(doc)
dados_succao = show_succao_form(dados_iniciais=succao_salvo)

if dados_succao is None:
    # Pular aqui não invalida a classificação — o cálculo do NPSH
    # simplesmente roda com o que já estava salvo (ou com os padrões).
    dados_succao = succao_salvo
    output.print_md(u"⚠ Dados de NPSH não informados — será usado o que já "
                    u"estava salvo no projeto.")
else:
    output.print_md(u"✔ Altitude do local: **{:g} m**".format(
        dados_succao["altitude_m"]))
    output.print_md(u"✔ Temperatura da água: **{:g} °C**".format(
        dados_succao["temperatura_c"]))
    output.print_md(u"✔ NPSHr da bomba: **{}**".format(
        u"{:g} mca".format(dados_succao["npshr_m"])
        if dados_succao["npshr_m"] is not None else u"não informado"))

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

        if dados_succao is not None:
            ok_succao, msg_succao = succao_calc.save_dados(doc, dados_succao)
            output.print_md(u"{} {}".format(u"✔" if ok_succao else u"⚠", msg_succao))

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