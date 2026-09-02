# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Memorial de Cálculo
Regera o memorial de cálculo completo (passo a passo, método da marcha) a
partir do cache salvo pelo "Dimensionar Hidrantes" — sem recalcular nada
nem tocar no modelo do Revit. Execute "Dimensionar Hidrantes" primeiro.
Grava o memorial como arquivo .html na pasta do projeto e abre em janela
separada; não imprime no console do pyRevit.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from pyrevit import forms, script

from projeto import exigir_projeto_e_estado
from hidrantes.calc import carregar_cache
from hidrantes.norm_profiles import get_profile
from hidrantes.memorial import gerar_memorial_calculo

doc = __revit__.ActiveUIDocument.Document

# --- Verificar projeto salvo e estado configurado (mesmo pré-requisito de
# "Dimensionar Hidrantes" — é onde o firedata.json do projeto mora) ---
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)

# --- Carrega o resultado salvo por "Dimensionar Hidrantes" ---
payload, erro = carregar_cache(projeto_dir)
if erro:
    forms.alert(erro, title="Fire Utils", warn_icon=True)
    script.exit()

# Perfil normativo reconstruído a partir da UF gravada no cache — os
# valores em si (Q, Pmin, limites de velocidade etc.) já vieram junto no
# payload; o perfil aqui só é usado para textos/citações do memorial.
perfil = get_profile(payload.get(u"uf"))

dados_sistema = payload[u"dados_sistema"]
Qs_lmin = dados_sistema[u"q_min"]
Pmin    = dados_sistema[u"p_min"]

caminho = gerar_memorial_calculo(
    payload[u"res"], dados_sistema, payload[u"valor_sistema"],
    payload[u"cotas"], payload[u"succao"], payload[u"verif_succao"],
    payload.get(u"verif_npshd"), payload.get(u"erro_npshd"),
    payload.get(u"j_succao_npsh"),
    Qs_lmin, Pmin, payload[u"C_HW"],
    payload[u"eta"], payload[u"pot_cv"], payload[u"pot_kw"],
    payload.get(u"timestamp") or u"", perfil,
    projeto_dir=projeto_dir,
    nome_projeto=payload.get(u"_nome_projeto") or doc.Title,
)
if not caminho:
    forms.alert(u"Não foi possível gravar o arquivo do memorial de cálculo "
                u"em '{}'.".format(projeto_dir), title="Fire Utils", warn_icon=True)
    script.exit()
