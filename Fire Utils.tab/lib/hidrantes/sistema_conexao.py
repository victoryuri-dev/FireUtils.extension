# -*- coding: utf-8 -*-
"""
sistema_conexao.py — Fire Utils · lib/hidrantes/

Sistema de conexão (BSP roscado x Grooved ranhurado) escolhido na
dockpane, POR DIÂMETRO da rede — guardado no Project Information do
projeto (JSON no parâmetro "FireUtils - Sistema de Conexao"), no mesmo
molde que succao.py guarda altitude/temperatura.

Existe porque cotovelo/tê roscado e ranhurado têm Leq bem diferente pro
mesmo diâmetro, e isso não dá mais pra inferir da família do Revit: a
classificação do tipo de conexão (get_tipo_conexao, em rede.py) usa o
PartType nativo, que é o mesmo nos dois sistemas. O motor de cálculo
(leqConexoes.ts, repositório ETOS.FireUtils) é quem de fato escolhe a
tabela de Leq a partir do que este módulo devolve — aqui só se lê/grava
a escolha do usuário.
"""

from __future__ import absolute_import

import json

PARAM = u"FireUtils - Sistema de Conexao"

SISTEMAS_VALIDOS = (u"bsp", u"grooved")
SISTEMA_PADRAO = u"bsp"


def default_dados():
    """Nenhum diâmetro configurado — get_sistema() cai no padrão (bsp)
    pra tudo, que é o que a tabela genérica já aproximava antes desta
    funcionalidade existir."""
    return {}


def normalizar_dados(dados):
    """Converte um dict cru (JSON salvo, ou vindo da dockpane) para o
    formato canônico: {"<DN em mm, inteiro, como string>": "bsp"|"grooved"}.
    Entradas inválidas (chave não numérica, valor fora de SISTEMAS_VALIDOS)
    são descartadas silenciosamente — nunca gravam um valor que o motor não
    reconheceria."""
    out = {}
    if not isinstance(dados, dict):
        return out
    for chave, valor in dados.items():
        try:
            dn = int(round(float(chave)))
        except (TypeError, ValueError):
            continue
        if valor not in SISTEMAS_VALIDOS:
            continue
        out[u"{}".format(dn)] = valor
    return out


def get_sistema(sistema_por_diametro, d_mm):
    """Sistema ('bsp'|'grooved') configurado para o diâmetro d_mm (float,
    em mm) — SISTEMA_PADRAO se esse diâmetro não tiver escolha salva."""
    if not sistema_por_diametro or d_mm is None:
        return SISTEMA_PADRAO
    chave = u"{}".format(int(round(d_mm)))
    return sistema_por_diametro.get(chave, SISTEMA_PADRAO)


def load_dados(doc):
    """Lê o sistema de conexão por diâmetro salvo no projeto; {} se não houver."""
    param = doc.ProjectInformation.LookupParameter(PARAM)
    if not param:
        return default_dados()

    raw = param.AsString()
    if not raw or not raw.strip():
        return default_dados()

    try:
        dados = json.loads(raw)
    except Exception:
        return default_dados()

    return normalizar_dados(dados)


def save_dados(doc, dados):
    """
    Grava o sistema de conexão por diâmetro no projeto (JSON no Project
    Information). Abre e fecha a própria Transaction — ao contrário de
    succao.save_dados, não é chamado junto de outra gravação.
    """
    from Autodesk.Revit.DB import Transaction

    param = doc.ProjectInformation.LookupParameter(PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parâmetro '{}' não encontrado no projeto.".format(PARAM)

    normalizados = normalizar_dados(dados)
    with Transaction(doc, u"FireUtils - Sistema de conexão por diâmetro") as t:
        t.Start()
        param.Set(json.dumps(normalizados, ensure_ascii=True, sort_keys=True))
        t.Commit()
    return True, u"Sistema de conexão salvo no projeto."
