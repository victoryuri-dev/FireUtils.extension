# -*- coding: utf-8 -*-
"""
normas/__init__.py — Fire Utils
Centro normativo unificado: um pacote por estado, um arquivo por fonte
normativa (saidas.py, hidrantes.py, ...) dentro da pasta de cada estado.

Uso:
    from normas import get_estado, lista_estados

    estado = get_estado("MA")
    ocupacoes = estado["ocupacoes"]           # domínio saídas (chaves planas)
    tabela    = estado["tabela"]
    larg_min  = estado["larguras_minimas"]
    distancias = estado["distancias_maximas"]
    hidrantes = estado.get("hidrantes")       # domínio hidrantes (pode não existir)

Para adicionar um estado novo: criar a pasta normas/<UF>/ com um arquivo por
fonte normativa (ex.: saidas.py, hidrantes.py) e um __init__.py que monte o
ESTADO combinando essas fontes (ver normas/MA/__init__.py como referência).
Depois, registrar a sigla em get_estado() e lista_estados() abaixo.
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
        from normas.MA import ESTADO  # lib/normas/MA/__init__.py
        return ESTADO
    if sigla == u"PE":
        from normas.PE import ESTADO  # lib/normas/PE/__init__.py
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
