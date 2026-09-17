# -*- coding: utf-8 -*-
"""
hidrantes_classificacao_bridge.py — Fire Utils · lib/
Processa a mensagem da bridge web SET_HIDRANTES_CLASSIFICACAO: recebe do
site (via dockpane, já autenticado no Supabase — ver
webapp/src/components/dashboard/DashboardEstrutura.jsx) o Tipo de sistema
de hidrantes/mangotinhos que o ETOS.FireUtils classificou pela Tabela 3 da
norma (src/components/hidrantes/FormularioSistema.jsx) e grava no Project
Information do documento ativo, no MESMO formato que o extinto pushbutton
"Classificar Sistema de Hidrante" gravava — assim "Mapear Trechos" e
"Dimensionar Hidrantes" continuam funcionando sem nenhuma mudança neles.

O site manda Tipo + variante (a decisão da Tabela 3, que só ele faz —
cruza área/ocupação/carga de incêndio do projeto). Os demais parâmetros da
Tabela 2 (esguicho, mangueira, vazão/pressão mínima) continuam vindo do
perfil normativo do próprio plugin (hidrantes/norm_profiles.py) — a mesma
fonte que o extinto "Classificar Sistema" já usava —, nunca do site, pra
nunca ter dois lugares dando valores potencialmente diferentes pra
Tabela 2.

Além do Tipo/variante, o site agora também manda (o botão "Classificar
Sistema de Hidrante" foi removido — essa era a única outra forma de
gravar esses dados no projeto):
  - metodoCalculo: token u"valvula" | u"esguicho" — onde a norma do
    estado exige verificar Q/Pmin do sistema (site: state.hidrantes,
    a partir de REFERENCIA_PRESSAO_VAZAO da norma do estado do projeto).
  - succaoAltitude / succaoTemperatura: entradas do NPSH disponível
    (site: state.hidrantes) — persistidas via hidrantes.succao.save_dados.

RTI (Reserva Técnica de Incêndio) NÃO é gravado aqui: o motor de cálculo
("Dimensionar Hidrantes"/"Mapear Trechos") nunca lê RTI do Project
Information — é só um dado de registro (dimensiona o reservatório, não a
rede hidráulica), então fica só no Supabase (dados.hidrantes.rti, mesmo
lugar que o site edita e que SistemaHidrantesPage.jsx já grava direto via
salvarHidrantes()) — sem essa terceira cópia local que podia divergir das
outras duas sem ninguém perceber.
"""

import os

from Autodesk.Revit.DB import Transaction

from hidrantes.params import (
    create_hydrant_params, PROJECT_INFO_PARAM, PROJECT_INFO_METODO_PARAM,
)
from hidrantes.norm_profiles import get_profile, req, NormProfileError
from hidrantes.calc import METODO_VALVULA, METODO_ESGUICHO
from hidrantes import succao
from projeto import carregar_dados_projeto
from family_error_utils import texto_erro

# Mapeia o token normalizado que o site manda (mesmo vocabulário de
# REFERENCIA_PRESSAO_VAZAO em normas/<UF>/hidrantes.js) para a constante
# de método de cálculo do motor.
_METODOS_POR_TOKEN = {
    u"valvula":  METODO_VALVULA,
    u"esguicho": METODO_ESGUICHO,
}


def _metodo_calculo(token):
    return _METODOS_POR_TOKEN.get(token, METODO_ESGUICHO)


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
    metodo_calculo = _metodo_calculo(payload.get(u"metodoCalculo"))
    dados_succao = succao.normalizar_dados({
        u"altitude_m":    payload.get(u"succaoAltitude"),
        u"temperatura_c": payload.get(u"succaoTemperatura"),
    })

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
            ok_succao, msg_succao = succao.save_dados(doc, dados_succao)
            if not ok_succao:
                t.RollBack()
                postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {u"ok": False, u"erro": msg_succao})
                return
            t.Commit()
    except Exception as ex:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
        u"ok": True,
        u"valorSistema": valor_param,
        u"metodoCalculo": metodo_calculo,
    })
