# -*- coding: utf-8 -*-
"""
hidrantes_material_conexao_bridge.py — Fire Utils · lib/
Processa as mensagens da bridge web GET_MATERIAL_CONEXAO/SET_MATERIAL_CONEXAO:
material da tubulação + sistema de conexão (BSP roscado x Grooved
ranhurado) escolhidos na dockpane, por (etapa, tipo de tubo) — ver
hidrantes/material_conexao.py e leqConexoes.ts/dimensionar.ts (motor).
"""

from hidrantes import material_conexao
from hidrantes.params import create_hydrant_params
from family_error_utils import texto_erro


def tratar_get_material_conexao(uiapp, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"MATERIAL_CONEXAO", {u"ok": True, u"porEtapa": material_conexao.default_dados()})
        return
    try:
        dados = material_conexao.load_dados(uidoc.Document)
    except Exception as ex:
        postar_mensagem(u"MATERIAL_CONEXAO", {u"ok": False, u"erro": texto_erro(ex)})
        return
    postar_mensagem(u"MATERIAL_CONEXAO", {u"ok": True, u"porEtapa": dados})


def tratar_set_material_conexao(uiapp, payload, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(u"MATERIAL_CONEXAO_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de escolher material/sistema de conexão.",
        })
        return
    doc = uidoc.Document

    dados = material_conexao.normalizar_dados(payload.get(u"porEtapa") or {})

    try:
        create_hydrant_params(doc)
        ok, msg = material_conexao.save_dados(doc, dados)
    except Exception as ex:
        postar_mensagem(u"MATERIAL_CONEXAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    if not ok:
        postar_mensagem(u"MATERIAL_CONEXAO_SAVED", {u"ok": False, u"erro": msg})
        return

    postar_mensagem(u"MATERIAL_CONEXAO_SAVED", {u"ok": True, u"porEtapa": dados})
