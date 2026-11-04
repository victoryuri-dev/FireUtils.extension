# -*- coding: utf-8 -*-
"""
hidrantes_sistema_conexao_bridge.py — Fire Utils · lib/
Processa as mensagens da bridge web GET_SISTEMA_CONEXAO/SET_SISTEMA_CONEXAO:
o sistema de conexão (BSP roscado x Grooved ranhurado) escolhido na
dockpane, por diâmetro, pra decidir a tabela de Leq de cotovelo/tê no
motor de cálculo (ver hidrantes/sistema_conexao.py e leqConexoes.ts).
"""

from hidrantes import sistema_conexao
from hidrantes.params import create_hydrant_params
from family_error_utils import texto_erro


def tratar_get_sistema_conexao(uiapp, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"SISTEMA_CONEXAO", {u"ok": True, u"sistemaPorDiametro": {}})
        return
    try:
        dados = sistema_conexao.load_dados(uidoc.Document)
    except Exception as ex:
        postar_mensagem(u"SISTEMA_CONEXAO", {u"ok": False, u"erro": texto_erro(ex)})
        return
    postar_mensagem(u"SISTEMA_CONEXAO", {u"ok": True, u"sistemaPorDiametro": dados})


def tratar_set_sistema_conexao(uiapp, payload, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"SISTEMA_CONEXAO_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de escolher o sistema de conexão.",
        })
        return
    doc = uidoc.Document

    sistema_por_diametro = sistema_conexao.normalizar_dados(payload.get(u"sistemaPorDiametro") or {})

    try:
        create_hydrant_params(doc)
        ok, msg = sistema_conexao.save_dados(doc, sistema_por_diametro)
    except Exception as ex:
        postar_mensagem(u"SISTEMA_CONEXAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    if not ok:
        postar_mensagem(u"SISTEMA_CONEXAO_SAVED", {u"ok": False, u"erro": msg})
        return

    postar_mensagem(u"SISTEMA_CONEXAO_SAVED", {u"ok": True, u"sistemaPorDiametro": sistema_por_diametro})
