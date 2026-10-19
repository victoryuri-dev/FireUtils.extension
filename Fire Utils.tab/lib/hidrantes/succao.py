# -*- coding: utf-8 -*-
"""
succao.py — Fire Utils · lib/hidrantes/

Dados de sucção que NÃO vêm da geometria — altitude e temperatura da água,
que o NPSH disponível precisa — guardados no Project Information do projeto
(JSON no parâmetro "FireUtils - Dados de Succao").

A verificação da condição de sucção (diferença de cotas RTI × sucção da
bomba) e o NPSH disponível rodam no servidor, junto do resto do
dimensionamento (Edge Function motor-hidrantes, repositório ETOS.FireUtils;
ver motor_nuvem.py). Este módulo só lê e grava esses dois números.
"""

from __future__ import absolute_import

import json

# Parâmetro de Project Information que guarda (em JSON) os dados que a
# verificação de NPSH precisa e que não existem na geometria.
SUCCAO_PARAM = u"FireUtils - Dados de Succao"


# ===========================================================================
# Dados que não vêm da geometria — só o que o NPSH disponível precisa
# ===========================================================================

DEFAULT_DADOS = {
    # Entradas do NPSH disponível. Altitude e temperatura são escolhidas
    # entre as linhas das tabelas do motor (servidor) — por isso já vêm
    # preenchidas com o valor usual.
    u"altitude_m":    None,
    u"temperatura_c": None,
}


def default_dados():
    return dict(DEFAULT_DADOS)


def normalizar_dados(dados):
    """Converte um dict cru (formulário ou JSON salvo) para o formato canônico."""
    base = default_dados()
    out  = dict(base)

    # Altitude e temperatura são chaves das tabelas de Ha/Hvp: inteiros, e
    # só valem se existirem na tabela — quem valida é o motor (servidor).
    for chave in (u"altitude_m", u"temperatura_c"):
        valor = dados.get(chave, base[chave])
        if valor is None or valor == u"":
            out[chave] = base[chave]
            continue
        try:
            out[chave] = int(round(float(valor)))
        except (TypeError, ValueError):
            out[chave] = base[chave]

    return out


def load_dados(doc):
    """Lê os dados de sucção salvos no projeto; None se não houver."""
    param = doc.ProjectInformation.LookupParameter(SUCCAO_PARAM)
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

    return normalizar_dados(dados)


def save_dados(doc, dados):
    """
    Grava os dados de sucção no projeto (JSON no Project Information).
    Precisa ser chamado dentro de uma Transaction já aberta pelo chamador.
    """
    param = doc.ProjectInformation.LookupParameter(SUCCAO_PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parâmetro '{}' não encontrado no projeto.".format(SUCCAO_PARAM)

    param.Set(json.dumps(normalizar_dados(dados), ensure_ascii=True, sort_keys=True))
    return True, u"Dados de sucção salvos no projeto."
