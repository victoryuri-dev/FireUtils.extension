# -*- coding: utf-8 -*-
"""
estados/__init__.py — Fire Utils
Registry de estados disponíveis.

Uso:
    from estados import get_estado, lista_estados

    estado = get_estado("PE")
    ocupacoes = estado["ocupacoes"]
    tabela    = estado["tabela"]
    larg_min  = estado["larguras_minimas"]
    distancias = estado["distancias_maximas"]
"""

import os
import json
import io

_CACHE_ESTADO = os.path.join(
    os.environ.get("TEMP", os.path.expanduser("~")),
    u"fireutils_estado.json"
)


def salvar_estado_ativo(sigla):
    """Persiste a sigla do estado ativo entre sessões do pyRevit."""
    with io.open(_CACHE_ESTADO, "w", encoding="utf-8") as f:
        json.dump({u"sigla": sigla.upper()}, f, ensure_ascii=False)


def carregar_estado_ativo():
    """Retorna a sigla do estado ativo salvo, ou None."""
    if not os.path.exists(_CACHE_ESTADO):
        return None
    try:
        with io.open(_CACHE_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f).get(u"sigla")
    except Exception:
        return None


def get_estado(sigla):
    """Retorna o dict ESTADO para a sigla fornecida, ou None se não encontrado."""
    sigla = sigla.upper()
    if sigla == u"MA":
        from estados.MA import ESTADO  # lib/estados/MA.py
        return ESTADO
    if sigla == u"PE":
        from estados.PE import ESTADO  # lib/estados/PE.py
        return ESTADO
    return None


def lista_estados():
    """Retorna lista de (sigla, label) para exibição em forms."""
    return [
        (u"MA", u"Maranhão — CBM-MA"),
        (u"PE", u"Pernambuco — CBMPE"),
    ]


def get_label(sigla):
    for s, label in lista_estados():
        if s == sigla:
            return label
    return sigla
