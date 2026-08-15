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

from sync import enviar as enviar_sync

# ===========================================================================
# Constantes
# ===========================================================================
# C_HW nao existe mais como constante fixa aqui: o coeficiente de Hazen-Williams
# e um parametro normativo (Tabela 1) e vem do perfil ativo
# (hidrantes.norm_profiles) via script.py. _f, _g e _Lm sao constantes fisicas
# / geometricas internas da formula de Darcy-Weisbach da mangueira, nao valores
# normativos por estado - permanecem aqui.
_f   = 0.022
_g   = 9.81
_Lm  = 30.0

_CACHE_NOME    = u"firedata.json"
_LAST_PROJ_TXT = u"fireutils_last_project.txt"


def _cache_path(projeto_dir=None):
    d = projeto_dir or os.environ.get("TEMP", os.path.expanduser("~"))
    return os.path.join(d, _CACHE_NOME)


def _salvar_ponteiro_projeto(projeto_dir):
    """Grava %TEMP%/fireutils_last_project.txt para rastrear o último projeto usado."""
    if not projeto_dir:
        return
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
    try:
        with io.open(os.path.join(temp, _LAST_PROJ_TXT), "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


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
    """
    Perda de carga na mangueira por Darcy-Weisbach, em função da vazão.

    Dedução: hf = f·(L/D)·(V²/2g), com V = Q/A = 4Q/(π·D²)
      → V² = 16·Q² / (π²·D⁴)
      → hf = f·L/D × 16·Q² / (2g·π²·D⁴) = 8·f·L·Q² / (g·π²·D⁵)
    """
    return (8.0 * _f * _Lm) / (_g * (math.pi ** 2) * (Dm_m ** 5)) * (Q_m3s ** 2)


def calc_pressao(Ht, Hz, Hf_percurso):
    """Pressão residual na válvula do hidrante."""
    return Ht + Hz - Hf_percurso


def calc_potencia(Qt_m3s, Ht, eta_decimal):
    """Potência da bomba em cv."""
    return (1000.0 * Qt_m3s * Ht) / (75.0 * eta_decimal)


def hesg_mca(q_lmin, k=None, d_mm=None, cd=0.97):
    """
    Pressao requerida no esguicho (mca), para uso quando Pmin e referenciada
    na valvula do hidrante (pmin_ref = "valvula") e a perda no esguicho
    regulavel precisa ser somada explicitamente na cadeia de energia.

    k    : fator de vazao de catalogo do esguicho regulavel (Q = K*sqrt(P)).
    d_mm : diametro do requinte, para jato solido (Q = 0,2087*cd*d^2*sqrt(H)).
    """
    if k:
        return (q_lmin / float(k)) ** 2
    return (q_lmin / (0.2087 * cd * float(d_mm) ** 2)) ** 2


def verificar_equilibrio_no(E1, E2, limite):
    """
    Verifica o equilibrio de pressoes requeridas no no de derivacao entre os
    dois ramais mais desfavoraveis (referencia normativa: limite recebido do
    perfil ativo, ex. NT 22 item 5.8.15).

    No modelo de demanda fixa, o desequilibrio entre os ramais e:
        desequilibrio = abs(E1 - E2)
    onde E1/E2 sao as energias dos ramais ja calculadas por calcular_rede().

    Retorna dict com desequilibrio, limite, margem (limite - desequilibrio,
    negativa se reprovado) e atende (bool).
    """
    desequilibrio = abs(E1 - E2)
    return {
        u"desequilibrio": desequilibrio,
        u"limite":        limite,
        u"margem":        limite - desequilibrio,
        u"atende":        desequilibrio <= limite,
    }


# ===========================================================================
# RESOLUÇÃO DA REDE HIDRÁULICA — MODELO DE DEMANDA FIXA
# ===========================================================================

def calcular_rede(trechos_data, Qs_lmin, Hz_H1, Hz_H2,
                  Hesg, Pmin, C,
                  Dm_mangueira_m=None,
                  **kwargs):
    """
    Calcula a rede hidráulica de dois hidrantes em paralelo.

    Modelo de demanda fixa: cada hidrante opera com a vazão normativa mínima
    Q_i = Qs_lmin (demanda especificada pela norma). Isso determina o sistema
    completamente — sem coeficiente empírico, sem igualdade artificial de energia
    entre ramais. As pressões resultam das equações hidráulicas; não são impostas.

    Sequência de cálculo (ordem física da rede):
      1. Q1 = Q2 = Qs_lmin → Qt = Q1 + Q2
      2. Hazen-Williams em cada trecho com as vazões especificadas
      3. Darcy-Weisbach na mangueira de cada hidrante: Hm = (8fLm)/(gπ²Dm⁵) × Q²
      4. Energia de cada ramal: E_i = hf_ramal_i + Hm_i + Hesg − ΔZ_i
      5. Ramal governante: argmax(E1, E2) → determina a HMT mínima da bomba
      6. HMT: Ht = Pmin + Hf_tronco + E_gov
      7. Pressões reais (P1 ≠ P2 em geral): P_i = Ht + ΔZ_i − Hf_i − Hm_i − Hesg
         O ramal governante tem P = Pmin; o outro tem P = Pmin + (E_gov − E_i) > Pmin.

    Hipótese de projeto: demanda fixa é a modelagem padrão em dimensionamento
    de sistemas de proteção contra incêndio (analogia ao fire flow analysis no EPANET:
    demanda nodal especificada → solver calcula pressões).
    """
    Qs = Qs_lmin / 60000.0   # m³/s

    # Demandas especificadas pela norma (vazão mínima em cada hidrante)
    Q1 = Qs
    Q2 = Qs
    Qt = Q1 + Q2

    # Hazen-Williams em cada trecho com as respectivas vazões
    hf = {
        "t1": calc_hf_trecho(trechos_data["t1"], Qt, C, u"RTI → Bomba"),
        "t2": calc_hf_trecho(trechos_data["t2"], Qt, C, u"Bomba → Ponto A"),
        "t3": calc_hf_trecho(trechos_data["t3"], Q1, C, u"Ponto A → HID-01"),
        "t4": calc_hf_trecho(trechos_data["t4"], Q2, C, u"Ponto A → HID-02"),
    }

    Hf_tronco = hf["t1"]["Hf"] + hf["t2"]["Hf"]
    Hf1       = Hf_tronco + hf["t3"]["Hf"]
    Hf2       = Hf_tronco + hf["t4"]["Hf"]

    # Darcy-Weisbach na mangueira de cada hidrante
    Hm1 = calc_hf_mangueira(Q1, Dm_mangueira_m) if Dm_mangueira_m else 0.0
    Hm2 = calc_hf_mangueira(Q2, Dm_mangueira_m) if Dm_mangueira_m else 0.0

    # Energia de cada ramal vista do Nó A (demanda energética do ramal, sem Pmin)
    E1 = hf["t3"]["Hf"] + Hm1 + Hesg - Hz_H1
    E2 = hf["t4"]["Hf"] + Hm2 + Hesg - Hz_H2

    # Ramal governante: o mais exigente define a HMT mínima da bomba
    E_gov = max(E1, E2)
    Ht    = float(Pmin) + Hf_tronco + E_gov

    # Pressões reais em cada hidrante (resultado das equações — não impostas)
    p1 = Ht + Hz_H1 - Hf1 - Hm1 - Hesg
    p2 = Ht + Hz_H2 - Hf2 - Hm2 - Hesg

    norm_ok = (p1 >= float(Pmin) - 0.01 and p2 >= float(Pmin) - 0.01)

    historico = [{
        "ciclo":   1,
        "Qt":      Qt * 60000.0,
        "Q_h01":   Q1 * 60000.0,
        "Q_h02":   Q2 * 60000.0,
        "Hf_t1":   hf["t1"]["Hf"],
        "Hf_t2":   hf["t2"]["Hf"],
        "Hf_t3":   hf["t3"]["Hf"],
        "Hf_t4":   hf["t4"]["Hf"],
        "Hf1":     Hf1,
        "Hf2":     Hf2,
        "Hm1":     Hm1,
        "Hm2":     Hm2,
        "E1":      E1,
        "E2":      E2,
        "Ht":      Ht,
        "p1":      p1,
        "p2":      p2,
        "V_t1":    hf["t1"]["V"],
        "V_t2":    hf["t2"]["V"],
        "V_t3":    hf["t3"]["V"],
        "V_t4":    hf["t4"]["V"],
        "norm_ok": norm_ok,
    }]

    if E1 >= E2:
        hid_governa = u"HID-01"; Hf_gov = Hf1; Hz_gov = Hz_H1; Hm_gov = Hm1
    else:
        hid_governa = u"HID-02"; Hf_gov = Hf2; Hz_gov = Hz_H2; Hm_gov = Hm2

    return {
        "hf":          hf,
        "Hf_Hid01":    Hf1,
        "Hf_Hid02":    Hf2,
        "Ht":          Ht,
        "p_hid01":     p1,
        "p_hid02":     p2,
        "Q_h01":       Q1 * 60000.0,
        "Q_h02":       Q2 * 60000.0,
        "Qt_final":    Qt * 60000.0,
        "hid_governa": hid_governa,
        "Hf_governa":  Hf_gov,
        "Hz_governa":  Hz_gov,
        "Hm_governa":  Hm_gov,
        "Hm_hid01":    Hm1,
        "Hm_hid02":    Hm2,
        "iteracoes":   1,
        "historico":   historico,
    }


# ===========================================================================
# EXTRAÇÃO DE DADOS DO REVIT
# (chamada pelo script Dimensionar, que tem acesso ao Revit)
# ===========================================================================

def extrair_trecho(elems, get_comprimento_fn, get_diametro_fn, get_leq_fn, get_nome_fn):
    """
    Extrai L, D, Leq e acessórios agrupados de uma lista de elementos Revit.
    Recebe as funções helper como parâmetro para manter este módulo sem imports Revit.

    Acessórios são agrupados por (nome do tipo, diâmetro nominal) — nunca apenas
    pelo nome — pois um mesmo tipo de acessório (ex.: "Tê") pode ocorrer em
    diâmetros diferentes dentro do mesmo trecho, cada um com Leq unitário próprio.
    Dentro de cada grupo, le_unit é a média exata dos valores acumulados
    (leq_tot_grupo / qtd_grupo), garantindo por construção que
    qtd × le_unit == leq_tot em toda linha exibida no memorial.
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
                nome  = get_nome_fn(elem)
                dn_mm = int(round(get_diametro_fn(elem) * 1000.0))
                chave = (nome, dn_mm)
                if chave in aces_raw:
                    aces_raw[chave]["qtd"]     += 1
                    aces_raw[chave]["leq_tot"] += leq
                else:
                    aces_raw[chave] = {"qtd": 1, "leq_tot": leq, "nome": nome, "dn_mm": dn_mm}

    acessorios = []
    for v in aces_raw.values():
        leq_unit = v["leq_tot"] / float(v["qtd"])  # média exata: qtd*leq_unit == leq_tot sempre
        assert abs(v["qtd"] * leq_unit - v["leq_tot"]) < 0.001
        acessorios.append({
            "nome":     u"{} DN{}".format(v["nome"], v["dn_mm"]),
            "qtd":      v["qtd"],
            "leq_unit": leq_unit,
            "leq_tot":  v["leq_tot"],
        })

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

def salvar_cache(payload, projeto_dir=None):
    """Salva o resultado do dimensionamento na chave 'hidrantes' do arquivo unificado."""
    payload["_timestamp"]   = datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S")
    payload["_projeto_dir"] = projeto_dir or u""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
    except Exception:
        dados = {}
    dados[u"hidrantes"] = payload
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    _salvar_ponteiro_projeto(projeto_dir)

    enviar_sync(u"hidrantes", payload, projeto_dir)

    return path


def carregar_cache(projeto_dir=None):
    """Retorna (payload, erro). Se erro não for None, payload é None."""
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return None, u"Nenhum dimensionamento encontrado.\nExecute 'Dimensionar Hidrantes' primeiro."
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
        payload = dados.get(u"hidrantes")
        if payload is None:
            return None, u"Nenhum dimensionamento encontrado.\nExecute 'Dimensionar Hidrantes' primeiro."
        return payload, None
    except Exception as e:
        return None, u"Erro ao ler cache: {}".format(str(e))


def cache_existe(projeto_dir=None):
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return False
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return u"hidrantes" in json.loads(f.read())
    except Exception:
        return False