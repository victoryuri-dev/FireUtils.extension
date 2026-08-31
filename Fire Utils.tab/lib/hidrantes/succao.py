# -*- coding: utf-8 -*-
"""
succao.py — Fire Utils · lib/hidrantes/

Verificação da CONDIÇÃO DE SUCÇÃO pelo método direto de diferença de cotas
(conservador) — compara a cota da RTI com a cota de sucção da bomba, ambas já
lidas e exibidas em "Cotas Altimétricas" no memorial, sem depender de nível
mínimo de água, dimensão de tomada ou tipo de captação:

    ∆H_succao = cota_RTI − cota_succao_bomba

    ∆H_succao ≥ 0  → sucção POSITIVA (RTI na cota igual ou acima da sucção)
    ∆H_succao <  0  → sucção NEGATIVA; |Hs| = cota_succao_bomba − cota_RTI

Sucção negativa aciona o cálculo de NPSH disponível (hidrantes/npshd.py),
com a vazão nominal do sistema majorada pelo fator normativo.

Módulo puro: sem dependência de Revit ou de output.
"""

from __future__ import absolute_import

import json

# IronPython 2.7 (engine do pyRevit) tem 'unicode'; CPython 3 não.
try:
    _txt = unicode
except NameError:
    _txt = str


# Fator de majoração da vazão na verificação de NPSH — normativo: o valor
# abaixo é só o default geral, e o perfil do estado ativo (npshd_fator_vazao)
# tem precedência.
FATOR_VAZAO_NPSH = 1.5

# Veredictos possíveis da verificação.
COND_POSITIVA = u"POSITIVA"
COND_NEGATIVA = u"NEGATIVA"

# Folga de 1 mm na comparação de cotas, só para não virar o veredicto por
# ruído de arredondamento quando as duas cotas são, na prática, iguais.
EPS_M = 0.001

# Parâmetro de Project Information que guarda (em JSON) os dados que a
# verificação de NPSH precisa e que não existem na geometria.
SUCCAO_PARAM = u"FireUtils - Dados de Succao"


# ===========================================================================
# Verificação principal
# ===========================================================================

def verificar_condicao_succao(cota_rti, cota_succao_bomba,
                              q_nominal_lmin=None,
                              fator_vazao_npsh=FATOR_VAZAO_NPSH):
    """
    Verificação direta e conservadora da condição de sucção: compara a cota
    da RTI com a cota de sucção da bomba.

    Retorna um dict com o veredicto e — na sucção negativa — a altura de
    elevação |Hs| e a vazão majorada para o NPSH disponível.
    """
    cota_rti_f   = float(cota_rti)
    cota_bomba_f = float(cota_succao_bomba)
    dH = cota_rti_f - cota_bomba_f   # >= 0 = RTI na cota igual ou acima da sucção

    if dH >= -EPS_M:
        condicao = COND_POSITIVA
        hs_abs = None
        justificativa = (
            u"Cota da RTI ({:.4f} m) igual ou acima da cota de sucção da "
            u"bomba ({:.4f} m), com folga de {:.4f} m — sucção "
            u"afogada.".format(cota_rti_f, cota_bomba_f, dH))
    else:
        condicao = COND_NEGATIVA
        hs_abs = cota_bomba_f - cota_rti_f
        justificativa = (
            u"Cota da RTI ({:.4f} m) abaixo da cota de sucção da bomba "
            u"({:.4f} m) — elevação de {:.4f} m, exige o cálculo do NPSH "
            u"disponível, com a vazão nominal do sistema majorada em "
            u"{:g}×.".format(cota_rti_f, cota_bomba_f, hs_abs, fator_vazao_npsh))

    exige_npsh = (condicao == COND_NEGATIVA)
    vazao_npsh_lmin = None
    if exige_npsh and q_nominal_lmin is not None:
        vazao_npsh_lmin = float(fator_vazao_npsh) * float(q_nominal_lmin)

    return {
        u"cota_rti":          cota_rti_f,
        u"cota_succao_bomba": cota_bomba_f,
        u"dH":                dH,
        u"hs_abs":            hs_abs,
        u"condicao":          condicao,
        u"justificativa":     justificativa,
        u"succao_simples":    succao_simples(condicao),
        u"exige_npsh":        exige_npsh,
        u"vazao_npsh_lmin":   vazao_npsh_lmin,
        u"fator_vazao_npsh":  float(fator_vazao_npsh),
    }


def succao_simples(condicao):
    """
    Reduz o veredicto a "positiva"/"negativa" — é essa forma que o resto do
    motor consome para escolher o limite de velocidade do trecho de sucção.
    """
    return u"negativa" if condicao == COND_NEGATIVA else u"positiva"


# ===========================================================================
# Dados que não vêm da geometria — só o que o NPSH disponível precisa
# ===========================================================================

DEFAULT_DADOS = {
    # Entradas do NPSH disponível. Altitude e temperatura são escolhidas
    # entre as linhas das tabelas de hidrantes/npshd.py — por isso já vêm
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
    # só valem se existirem na tabela — quem valida é hidrantes/npshd.py.
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
