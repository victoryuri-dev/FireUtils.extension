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

BASE NORMATIVA CENTRAL — desde esta versão, get_estado() tenta primeiro
buscar as chaves de saídas de emergência (ocupacoes/tabela/notas/
larguras_minimas/distancias_maximas) na tabela `normas_dados` do Supabase
(mesma base que o site lê — ver supabase/migrations/*normas_dados* em
ETOS.FireUtils e src/lib/normasRemote.js lá), com cache em memória
(por sessão do Revit) e em disco (entre sessões, offline) por cima disso.
Os módulos locais (normas/<UF>/saidas.py) viram só o fallback de última
instância — usados quando não há rede E não há cache em disco ainda (ex.:
instalação nova, nunca conectou). "hidrantes" ainda não foi migrado pra
base central, então continua vindo sempre do módulo local.
"""

import os
import json
import io


_CACHE_ESTADO = os.path.join(
    os.environ.get("TEMP", os.path.expanduser("~")),
    u"fireutils_estado.json"
)

# Cache em disco da última resposta bem-sucedida da base normativa central,
# por (uf, sistema) — permite o plugin continuar funcionando offline depois
# da primeira busca (a máquina do engenheiro pode não ter internet na hora
# de rodar "Dimensionar Saídas" em campo).
_CACHE_NORMAS = os.path.join(
    os.environ.get("TEMP", os.path.expanduser("~")),
    u"fireutils_normas_cache.json"
)

# Chaves do domínio "saídas" que a base central pode sobrescrever no
# ESTADO local — "hidrantes" nunca entra aqui porque ainda não foi
# migrado pra base central (ver Fire Utils.tab/lib/normas/MA/hidrantes.py).
_CHAVES_SAIDAS = (
    u"sigla", u"nome", u"corpo", u"norma_ocupacoes", u"norma_saidas",
    u"ocupacoes", u"tabela", u"notas", u"larguras_minimas",
    u"distancias_maximas", u"_pendencias",
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


def _ler_cache_normas():
    if not os.path.exists(_CACHE_NORMAS):
        return {}
    try:
        with io.open(_CACHE_NORMAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar_cache_normas(uf, sistema, dados):
    cache = _ler_cache_normas()
    cache.setdefault(uf, {})[sistema] = dados
    try:
        with io.open(_CACHE_NORMAS, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass  # cache é só otimização — falha ao gravar não deve travar nada


# Cache em memória do processo — enquanto o engine do pyRevit continuar
# carregado (normalmente o caso entre cliques de botão na mesma sessão do
# Revit), a rede só é consultada UMA vez por uf: sem isso, cada clique em
# "Dimensionar Saídas"/"Identificar Ambiente" pagaria de novo o custo de
# rede (até o timeout de 5s de sync.buscar_norma, se estiver offline) só
# pra buscar a mesma coisa de novo. Valor None (chave ausente) = ainda não
# buscado nesta sessão; False = já tentou e não achou nem rede nem cache
# em disco (também não tenta de novo até a sessão do Revit reiniciar).
_SESSION_CACHE = {}


def _buscar_saidas(uf):
    """
    Busca a fatia de saídas de emergência na base normativa central, com
    fallback pro cache em disco se a rede falhar — e um cache em memória
    por cima dos dois pra só pagar esse custo (rede ou disco) uma vez por
    sessão do Revit, não a cada clique de botão. Retorna um dict com as
    chaves de _CHAVES_SAIDAS já presentes na resposta, ou None se não há
    nem resposta de rede nem cache (quem chama cai pro módulo local).
    """
    if uf in _SESSION_CACHE:
        return _SESSION_CACHE[uf] or None

    from sync import buscar_norma

    dados, erro = buscar_norma(uf, u"saida_emergencia")
    if dados:
        _gravar_cache_normas(uf, u"saida_emergencia", dados)
        _SESSION_CACHE[uf] = dados
        return dados

    dados = _ler_cache_normas().get(uf, {}).get(u"saida_emergencia")
    _SESSION_CACHE[uf] = dados or False
    return dados


def get_estado(sigla):
    """Retorna o dict ESTADO para a sigla fornecida, ou None se não encontrado.

    As chaves de saídas de emergência vêm preferencialmente da base
    normativa central (com cache em memória/disco); "hidrantes" e qualquer
    chave ausente na resposta central continuam vindo do módulo local.
    """
    sigla = sigla.upper()
    if sigla == u"MA":
        from normas.MA import ESTADO  # lib/normas/MA/__init__.py
    elif sigla == u"PE":
        from normas.PE import ESTADO  # lib/normas/PE/__init__.py
    else:
        return None

    estado = dict(ESTADO)
    remoto = _buscar_saidas(sigla)
    if remoto:
        for chave in _CHAVES_SAIDAS:
            if chave in remoto:
                estado[chave] = remoto[chave]
    return estado


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
