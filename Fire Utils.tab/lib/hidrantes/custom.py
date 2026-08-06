# -*- coding: utf-8 -*-
"""
custom.py — Fire Utils — lib/hidrantes/

Sistema de hidrante com valores PERSONALIZADOS (fora da Tabela 2 da norma).

Os valores personalizados ficam salvos no proprio projeto (.rvt), em um
parametro de texto do Project Information no formato JSON. Assim eles
acompanham o arquivo e o usuario pode reclassificar quantas vezes quiser
naquele projeto sem redigitar nada.

Vocabulario das chaves = o mesmo usado pelo motor de calculo / perfis
normativos (q_min / p_min / mang_dn / mang_comp / esguicho_dn), para que
"Dimensionar Hidrantes" consuma o dict personalizado exatamente como
consumiria um tipo da Tabela 2.
"""

from __future__ import absolute_import

import json

# IronPython 2.7 (engine padrao do pyRevit) tem 'unicode'; CPython 3 nao.
try:
    _txt = unicode
except NameError:
    _txt = str

# Nome do parametro de Project Information que guarda o JSON personalizado
CUSTOM_PARAM = u"FireUtils - Sistema Personalizado"

# Prefixo gravado em "FireUtils - Tipo de Sistema de Hidrante" quando a
# classificacao ativa e personalizada (usado para detectar o modo na leitura).
CUSTOM_PREFIX = u"Personalizado"

CAMPOS_NUMERICOS = [
    (u"esguicho_dn", u"Esguicho DN (mm)"),
    (u"mang_dn",     u"Mangueira DN (mm)"),
    (u"mang_comp",   u"Comprimento da mangueira (m)"),
    (u"q_min",       u"Vazao minima (L/min)"),
    (u"p_min",       u"Pressao minima (mca)"),
]

# Rotulos curtos usados nas caixas do formulario (os longos acima vao nas
# mensagens de erro, onde cabe texto completo).
ROTULOS_CURTOS = {
    u"esguicho_dn": u"Esguicho DN (mm)",
    u"mang_dn":     u"Mangueira DN (mm)",
    u"mang_comp":   u"Compr. mang. (m)",
    u"q_min":       u"Vazão mín. (L/min)",
    u"p_min":       u"Pressão mín. (mca)",
}

DEFAULT_CUSTOM = {
    u"descricao":   u"Sistema personalizado",
    u"esguicho_dn": 40.0,
    u"mang_dn":     40.0,
    u"mang_comp":   30.0,
    u"expedicoes":  u"Simples",
    u"q_min":       200.0,
    u"p_min":       40.0,
}


def is_custom(valor_sistema):
    """True se a string do Project Information representa um sistema personalizado."""
    return bool(valor_sistema) and valor_sistema.strip().startswith(CUSTOM_PREFIX)


def default_custom():
    """Copia dos valores iniciais sugeridos (usado quando o projeto ainda nao tem nada salvo)."""
    return dict(DEFAULT_CUSTOM)


def validar(dados):
    """
    Valida um dict de sistema personalizado.
    Retorna lista de mensagens de erro (vazia se estiver tudo certo).
    """
    erros = []
    for chave, rotulo in CAMPOS_NUMERICOS:
        valor = dados.get(chave)
        if valor is None or valor == u"":
            erros.append(u"'{}' nao foi informado.".format(rotulo))
            continue
        try:
            num = float(valor)
        except (TypeError, ValueError):
            erros.append(u"'{}' deve ser um numero.".format(rotulo))
            continue
        if num <= 0:
            erros.append(u"'{}' deve ser maior que zero.".format(rotulo))

    if not (dados.get(u"descricao") or u"").strip():
        erros.append(u"'Descricao' nao foi informada.")

    return erros


def normalizar(dados):
    """
    Converte um dict cru (do formulario ou do JSON salvo) para o formato
    canonico, com numeros como float e texto como unicode.
    Assume que validar() ja passou; campos ausentes caem no default.
    """
    base = default_custom()
    out = {}
    for chave, _ in CAMPOS_NUMERICOS:
        valor = dados.get(chave, base[chave])
        try:
            out[chave] = float(valor)
        except (TypeError, ValueError):
            out[chave] = float(base[chave])

    desc = dados.get(u"descricao") or base[u"descricao"]
    out[u"descricao"] = _txt(desc).strip()

    exped = dados.get(u"expedicoes") or base[u"expedicoes"]
    out[u"expedicoes"] = _txt(exped).strip()

    return out


def descrever(dados):
    """String curta gravada no Project Information para um sistema personalizado."""
    d = normalizar(dados)
    return u"{} – DN {:g} | {:g} L/min | {:g} mca".format(
        CUSTOM_PREFIX, d[u"mang_dn"], d[u"q_min"], d[u"p_min"])


# ---------------------------------------------------------------------------
# Persistencia no projeto (Project Information)
# ---------------------------------------------------------------------------
def load_custom(doc):
    """
    Le os valores personalizados salvos no projeto.
    Retorna dict normalizado, ou None se o projeto nao tiver nada salvo
    (ou se o parametro ainda nao existir / estiver corrompido).
    """
    param = doc.ProjectInformation.LookupParameter(CUSTOM_PARAM)
    if not param:
        return None

    raw = param.AsString()
    if not raw or not raw.strip():
        return None

    try:
        dados = json.loads(raw)
    except Exception:
        return None

    if not isinstance(dados, dict):
        return None

    return normalizar(dados)


def save_custom(doc, dados):
    """
    Grava os valores personalizados no projeto (JSON no Project Information).

    IMPORTANTE: precisa ser chamado dentro de uma Transaction ja aberta pelo
    script chamador. Retorna (True, msg) ou (False, msg).
    """
    param = doc.ProjectInformation.LookupParameter(CUSTOM_PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parametro '{}' nao encontrado no projeto.".format(CUSTOM_PARAM)

    texto = json.dumps(normalizar(dados), ensure_ascii=True, sort_keys=True)
    param.Set(texto)
    return True, u"Valores personalizados salvos no projeto."


def para_dados_sistema(dados):
    """
    Converte o dict personalizado para o formato consumido pelo motor de
    calculo ("Dimensionar Hidrantes"): q_min / p_min / mang_dn / mang_comp /
    esguicho_dn.
    """
    d = normalizar(dados)
    return {
        u"q_min":       d[u"q_min"],
        u"p_min":       d[u"p_min"],
        u"mang_dn":     d[u"mang_dn"],
        u"mang_comp":   d[u"mang_comp"],
        u"esguicho_dn": d[u"esguicho_dn"],
    }
