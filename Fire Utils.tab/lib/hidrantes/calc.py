# -*- coding: utf-8 -*-
"""
dimensionar_hidrantes_calc.py — Fire Utils · lib/
Módulo puro de cálculo hidráulico de hidrantes.
Sem dependências de Revit ou output — pode ser importado por qualquer script.
"""

import math
import json
import os
import io
import datetime

# ===========================================================================
# Constantes
# ===========================================================================
C_HW       = 120
_f         = 0.022
_g         = 9.81
_Lm        = 30.0
MAX_ITER   = 20
TOLERANCIA = 1.0   # L/min

# Caminho do arquivo de cache (resultados salvos entre botões)
_CACHE_NOME = u"fireutils_hidrantes_cache.json"
_CACHE_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), _CACHE_NOME)


# ===========================================================================
# CÁLCULO HIDRÁULICO
# ===========================================================================

def calc_hf_trecho(elems_data, Q_m3s, C, label):
    """
    Calcula perda de carga de um trecho por Hazen-Williams.
    elems_data: dict com chaves L, D, Leq, acessorios (já extraídos do Revit).
    """
    L          = elems_data["L"]
    D          = elems_data["D"]
    Leq        = elems_data["Leq"]
    acessorios = elems_data["acessorios"]
    n_tubos    = elems_data["n_tubos"]

    Lt = L + Leq
    J  = 10.643 * (Q_m3s ** 1.852) * (C ** -1.852) * (D ** -4.871) if Lt > 0 else 0.0
    Hf = J * Lt
    V  = Q_m3s / (math.pi * D * D / 4.0) if D > 0 else 0.0

    return {
        "label":      label,
        "Q_m3s":      Q_m3s,
        "Q_lmin":     Q_m3s * 60000.0,
        "L":          L,
        "Leq":        Leq,
        "Lt":         Lt,
        "D":          D,
        "J":          J,
        "Hf":         Hf,
        "V":          V,
        "acessorios": acessorios,
        "n_tubos":    n_tubos,
        "n_aces":     len(acessorios),
    }


def calc_hf_mangueira(Q_m3s, Dm_m):
    """Perda de carga na mangueira por Darcy-Weisbach."""
    return (2.0 * _f * _Lm) / (_g * (math.pi ** 2) * (Dm_m ** 5)) * (Q_m3s ** 2)


def calc_pressao(Ht, Hz, Hf_percurso):
    """Pressão residual na válvula do hidrante."""
    return Ht + Hz - Hf_percurso


def calc_potencia(Qt_m3s, Ht, eta_decimal):
    """Potência da bomba em cv."""
    return (1000.0 * Qt_m3s * Ht) / (75.0 * eta_decimal)


def iterar_vazoes(trechos_data, Qs_lmin, Hz_H1, Hz_H2,
                  Hm_mangueira, Hesg, Pmin, C):
    """
    Laço de iteração de vazão.
    trechos_data: dict com chaves t1..t4, cada uma contendo L, D, Leq, acessorios, n_tubos.
    Retorna dict completo com resultados convergidos.
    """
    Q_h01 = Qs_lmin
    Q_h02 = Qs_lmin
    K     = None

    hf = {}
    Hf1 = Hf2 = Ht = p1 = p2 = 0.0
    hid_governa = u"HID-01"
    Hf_gov = Hz_gov = 0.0
    iteracoes = 0

    for i in range(MAX_ITER):
        iteracoes = i + 1
        Qt = (Q_h01 + Q_h02) / 60000.0
        Q1 = Q_h01 / 60000.0
        Q2 = Q_h02 / 60000.0

        hf = {
            "t1": calc_hf_trecho(trechos_data["t1"], Qt, C, u"RTI → Bomba"),
            "t2": calc_hf_trecho(trechos_data["t2"], Qt, C, u"Bomba → Ponto A"),
            "t3": calc_hf_trecho(trechos_data["t3"], Q1, C, u"Ponto A → HID-01"),
            "t4": calc_hf_trecho(trechos_data["t4"], Q2, C, u"Ponto A → HID-02"),
        }

        Hf1 = hf["t1"]["Hf"] + hf["t2"]["Hf"] + hf["t3"]["Hf"]
        Hf2 = hf["t1"]["Hf"] + hf["t2"]["Hf"] + hf["t4"]["Hf"]

        nec1 = Pmin + Hf1 - Hz_H1 + Hm_mangueira + Hesg
        nec2 = Pmin + Hf2 - Hz_H2 + Hm_mangueira + Hesg
        Ht   = max(nec1, nec2)

        if nec1 >= nec2:
            hid_governa = u"HID-01"; Hf_gov = Hf1; Hz_gov = Hz_H1
        else:
            hid_governa = u"HID-02"; Hf_gov = Hf2; Hz_gov = Hz_H2

        p1 = calc_pressao(Ht, Hz_H1, Hf1)
        p2 = calc_pressao(Ht, Hz_H2, Hf2)

        if i == 0:
            K = Qs_lmin / (min(p1, p2) ** 0.5)

        Q_h01_novo = K * (p1 ** 0.5)
        Q_h02_novo = K * (p2 ** 0.5)

        if abs(Q_h01_novo - Q_h01) <= TOLERANCIA and abs(Q_h02_novo - Q_h02) <= TOLERANCIA:
            Q_h01 = Q_h01_novo; Q_h02 = Q_h02_novo
            break

        Q_h01 = Q_h01_novo; Q_h02 = Q_h02_novo

    return {
        "hf":          hf,
        "Hf_Hid01":    Hf1,
        "Hf_Hid02":    Hf2,
        "Ht":          Ht,
        "p_hid01":     p1,
        "p_hid02":     p2,
        "Q_h01":       Q_h01,
        "Q_h02":       Q_h02,
        "Qt_final":    Q_h01 + Q_h02,
        "K":           K,
        "hid_governa": hid_governa,
        "Hf_governa":  Hf_gov,
        "Hz_governa":  Hz_gov,
        "iteracoes":   iteracoes,
    }


# ===========================================================================
# EXTRAÇÃO DE DADOS DO REVIT
# (chamada pelo script Dimensionar, que tem acesso ao Revit)
# ===========================================================================

def extrair_trecho(elems, get_comprimento_fn, get_diametro_fn, get_leq_fn, get_nome_fn):
    """
    Extrai L, D, Leq e acessórios agrupados de uma lista de elementos Revit.
    Recebe as funções helper como parâmetro para manter este módulo sem imports Revit.
    """
    from Autodesk.Revit.DB.Plumbing import Pipe
    from Autodesk.Revit.DB import FamilyInstance

    L = 0.0; Leq = 0.0; D_list = []; aces_raw = {}

    for elem in elems:
        if isinstance(elem, Pipe):
            L += get_comprimento_fn(elem)
            D_list.append(get_diametro_fn(elem))
        elif isinstance(elem, FamilyInstance):
            leq = get_leq_fn(elem)
            Leq += leq
            if leq > 0:
                nome = get_nome_fn(elem)
                if nome in aces_raw:
                    aces_raw[nome]["qtd"]     += 1
                    aces_raw[nome]["leq_tot"] += leq
                else:
                    aces_raw[nome] = {"qtd": 1, "leq_unit": leq, "leq_tot": leq}

    acessorios = [
        {"nome": n, "qtd": v["qtd"], "leq_unit": v["leq_unit"], "leq_tot": v["leq_tot"]}
        for n, v in aces_raw.items()
    ]

    return {
        "L":          L,
        "D":          sum(D_list) / len(D_list) if D_list else 0.065,
        "Leq":        Leq,
        "acessorios": acessorios,
        "n_tubos":    len(D_list),
    }


# ===========================================================================
# CACHE — salvar e carregar resultados entre botões
# ===========================================================================

def salvar_cache(payload):
    """Salva o resultado do dimensionamento como JSON em disco."""
    payload["_timestamp"] = datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S")
    with io.open(_CACHE_PATH, "w", encoding="utf-8") as f:
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        f.write(unicode(data) if hasattr(__builtins__, 'unicode') else data)
    return _CACHE_PATH


def carregar_cache():
    """
    Carrega o cache do último dimensionamento.
    Retorna (payload, erro). Se erro não for None, payload é None.
    """
    if not os.path.exists(_CACHE_PATH):
        return None, u"Nenhum dimensionamento encontrado.\nExecute 'Dimensionar Hidrantes' primeiro."
    try:
        with io.open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.loads(f.read()), None
    except Exception as e:
        return None, u"Erro ao ler cache: {}".format(str(e))


def cache_existe():
    return os.path.exists(_CACHE_PATH)