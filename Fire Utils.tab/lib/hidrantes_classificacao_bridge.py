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

O SITE interpreta o Tipo (decisão da Tabela 3 + parâmetros da Tabela 2 da
norma do estado, ou um sistema "Personalizado" digitado pelo RT) e manda,
além do Tipo/variante, os parâmetros já resolvidos (vazão e pressão
mínimas, esguicho, mangueira, expedições). O plugin NÃO tem tabela de Tipos
própria: só grava o que recebeu, no texto do parâmetro do projeto, que
"Mapear Trechos"/"Dimensionar Hidrantes" e o motor de cálculo interpretam
(ver hidrantes/sistema.py).

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

from Autodesk.Revit.DB import Transaction

from hidrantes.params import (
    create_hydrant_params, PROJECT_INFO_PARAM, PROJECT_INFO_METODO_PARAM,
)
from hidrantes.calc import METODO_VALVULA, METODO_ESGUICHO
from hidrantes import succao
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


def _txt(valor):
    """Número como texto, sem casas inúteis (30.0 -> "30") e sem format spec
    (um format spec num int quebra no IronPython 2.7)."""
    v = float(valor)
    return u"{}".format(int(v)) if v == int(v) else u"{}".format(v)


def _ler_parametros(payload):
    """Valida o que o site mandou. Retorna (rotulo, erro, parametros): o
    rótulo é "Tipo N", "Tipo N – Var. X" ou "Personalizado"."""
    tipo = payload.get(u"tipo")
    if tipo == u"personalizado":
        rotulo = u"Personalizado"
    else:
        try:
            numero = int(tipo)
        except (TypeError, ValueError):
            return None, u"Tipo de sistema inválido.", None
        try:
            variante_idx = int(payload.get(u"tipoVariante") or 0)
        except (TypeError, ValueError):
            variante_idx = 0
        rotulo = u"Tipo {}".format(numero)
        if variante_idx > 0:
            rotulo += u" – Var. {}".format(chr(65 + variante_idx))

    bruto = payload.get(u"parametros") or {}
    parametros = {}
    for chave in (u"vazaoMin", u"pressaoMin", u"esguicho", u"mangueiraDn", u"mangueiraComprimento"):
        try:
            valor = float(bruto.get(chave))
        except (TypeError, ValueError):
            valor = 0.0
        if valor <= 0:
            return None, (u"Parâmetros do sistema incompletos ('{}'). Atualize a "
                          u"classificação no site e tente novamente.".format(chave)), None
        parametros[chave] = valor
    expedicoes = (bruto.get(u"expedicoes") or u"").lower()
    if expedicoes not in (u"simples", u"duplo"):
        return None, u"Parâmetros do sistema incompletos ('expedicoes').", None
    parametros[u"expedicoes"] = expedicoes
    return rotulo, None, parametros


def tratar_set_hidrantes_classificacao(uiapp, payload, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de aplicar a classificação.",
        })
        return
    doc = uidoc.Document

    # O site interpreta o Tipo (Tabelas 2 e 3 da norma, ou um sistema
    # personalizado) e manda os parâmetros já resolvidos — o plugin não tem
    # tabela de Tipos: só grava o que recebeu.
    rotulo, erro_param, parametros = _ler_parametros(payload)
    if erro_param:
        postar_mensagem(u"HIDRANTES_CLASSIFICACAO_SAVED", {u"ok": False, u"erro": erro_param})
        return

    valor_param = u"{} – DN {} | {} L/min | {} mca | Esg DN {} | {} m | {}".format(
        rotulo,
        _txt(parametros[u"mangueiraDn"]), _txt(parametros[u"vazaoMin"]),
        _txt(parametros[u"pressaoMin"]), _txt(parametros[u"esguicho"]),
        _txt(parametros[u"mangueiraComprimento"]), parametros[u"expedicoes"])
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
