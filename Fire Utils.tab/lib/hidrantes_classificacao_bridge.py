# -*- coding: utf-8 -*-
"""
hidrantes_classificacao_bridge.py — Fire Utils · lib/
Processa a mensagem da bridge web SET_HIDRANTES_CLASSIFICACAO: recebe do
site (via dockpane, já autenticado no Supabase — ver
webapp/src/components/dashboard/DashboardEstrutura.jsx) o Tipo de sistema
de hidrantes/mangotinhos que o ETOS.FireUtils classificou pela Tabela 3 da
norma (src/components/hidrantes/FormularioSistema.jsx) e grava no Project
Information do documento ativo, no MESMO formato que o pushbutton
"Classificar Sistema de Hidrante" já grava — assim "Mapear Trechos" e
"Dimensionar Hidrantes" continuam funcionando sem nenhuma mudança neles.

O site manda só Tipo + variante (a decisão da Tabela 3, que só ele faz —
cruza área/ocupação/carga de incêndio do projeto). Os demais parâmetros da
Tabela 2 (esguicho, mangueira, vazão/pressão mínima) continuam vindo do
perfil normativo do próprio plugin (hidrantes/norm_profiles.py) — a mesma
fonte que "Classificar Sistema" já usa —, nunca do site, pra nunca ter dois
lugares dando valores potencialmente diferentes pra Tabela 2.
"""

import os

from Autodesk.Revit.DB import Transaction

from hidrantes.params import (
    create_hydrant_params, PROJECT_INFO_PARAM, PROJECT_INFO_METODO_PARAM,
)
from hidrantes.norm_profiles import get_profile, req, NormProfileError
from hidrantes.calc import METODO_VALVULA, METODO_ESGUICHO
from projeto import carregar_dados_projeto
from family_error_utils import texto_erro

# Onde a norma exige que a vazão/pressão mínima do sistema seja verificada
# (Tabela 2 de cada estado — no MA, na válvula do hidrante) — mesmo dado
# que o site guarda em normas/MA/hidrantes.js (REFERENCIA_PRESSAO_VAZAO).
# Cada lado mantém sua própria cópia normativa (mesmo padrão de
# hidrantes/db.py vs. o equivalente em normas/MA/hidrantes.js do site) —
# não é transmitido pela bridge, pra não fazer duas fontes concordarem
# através da rede.
_METODO_PADRAO_POR_UF = {u"MA": METODO_VALVULA}


def _metodo_padrao(sigla_estado):
    return _METODO_PADRAO_POR_UF.get(sigla_estado, METODO_ESGUICHO)


def tratar_set_hidrantes_classificacao(uiapp, payload, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de aplicar a classificação.",
        })
        return
    doc = uidoc.Document

    try:
        tipo = int(payload.get(u"tipo"))
    except (TypeError, ValueError):
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
            u"ok": False, u"erro": u"Tipo de sistema inválido.",
        })
        return
    try:
        variante_idx = int(payload.get(u"tipoVariante") or 0)
    except (TypeError, ValueError):
        variante_idx = 0

    projeto_dir = os.path.dirname(doc.PathName)
    dados_projeto = carregar_dados_projeto(projeto_dir) or {}
    sigla_estado = dados_projeto.get(u"uf") or u"MA"

    try:
        perfil = get_profile(sigla_estado)
    except NormProfileError as ex:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    tipo_perfil = req(perfil, u"tipos").get(tipo)
    if tipo_perfil is None:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
            u"ok": False,
            u"erro": u"O perfil normativo '{}' não define o Tipo {} de sistema de hidrante.".format(
                perfil.get(u"norma"), tipo),
        })
        return

    variantes = tipo_perfil[u"variantes"]
    if variante_idx < 0 or variante_idx >= len(variantes):
        variante_idx = 0
    dados = variantes[variante_idx]

    # Mesmo formato de string gravado pelo pushbutton "Classificar Sistema
    # de Hidrante" (Hidrantes.panel/Classificar Sistema.pushbutton/script.py)
    # — sem format spec (":g"/".1f") nos números: a Tabela 2 guarda esses
    # valores como int, e um format spec num int quebra no IronPython 2.7.
    var_txt = u" – Var. {}".format(chr(65 + variante_idx)) if len(variantes) > 1 else u""
    valor_param = u"Tipo {}{} – DN {} | {} L/min | {} mca".format(
        tipo, var_txt, dados[u"mang_dn"], dados[u"q_min"], dados[u"p_min"])
    metodo_calculo = _metodo_padrao(sigla_estado)

    try:
        create_hydrant_params(doc)

        pi = doc.ProjectInformation
        with Transaction(doc, u"FireUtils - Classificação recebida do site") as t:
            t.Start()
            param = pi.LookupParameter(PROJECT_INFO_PARAM)
            param_metodo = pi.LookupParameter(PROJECT_INFO_METODO_PARAM)
            if not param or param.IsReadOnly or not param_metodo or param_metodo.IsReadOnly:
                t.RollBack()
                postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
                    u"ok": False,
                    u"erro": u"Parâmetros de hidrante não encontrados no projeto. Reabra o Revit e tente novamente.",
                })
                return
            param.Set(valor_param)
            param_metodo.Set(metodo_calculo)
            t.Commit()
    except Exception as ex:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
        u"ok": True,
        u"valorSistema": valor_param,
        u"metodoCalculo": metodo_calculo,
    })
