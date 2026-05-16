# -*- coding: utf-8 -*-
"""
dimensionar_saidas_calc.py — Fire Utils · lib/
Motor de cálculo de saídas de emergência conforme IT 11 CBMSP.
Sem dependências de Revit — pode ser importado por qualquer script.
"""

import math
import json
import os
import io

UP          = 0.55   # metros por unidade de passagem
LARG_MIN_AD = 1.20   # largura mínima para acessos e descargas (m)
LARG_MIN_ER = 1.20   # largura mínima para escadas e rampas (m)

_CACHE_NOME = u"fireutils_saidas_cache.json"
_CACHE_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), _CACHE_NOME)


# ===========================================================================
# HELPERS
# ===========================================================================

def _n_up(populacao, capacidade_por_up):
    if not capacidade_por_up or capacidade_por_up <= 0:
        return None
    return int(math.ceil(populacao / float(capacidade_por_up)))


def _largura_porta(n_up_val):
    """Largura mínima e tipo de porta conforme IT 11."""
    if n_up_val is None:
        return None, u""
    if n_up_val <= 1:
        return 0.80, u"1 folha"
    elif n_up_val == 2:
        return 1.00, u"1 folha"
    elif n_up_val == 3:
        return 1.50, u"2 folhas"
    elif n_up_val == 4:
        return 2.00, u"2 folhas"
    else:
        return round(n_up_val * UP, 2), u"2 folhas"


def _bloco_nivel(rooms, nome_nivel, IT):
    """Calcula dados de um pavimento: pop, capacidades e grupos."""
    pop_total      = sum(r[u"pop"] for r in rooms)
    ad_min = er_min = pt_min = None
    grupos = []

    for r in rooms:
        dados = IT.get(r.get(u"grupo", u""))
        if not dados:
            continue
        grupos.append(r[u"grupo"])
        if dados[u"AD"] is not None:
            ad_min = dados[u"AD"] if ad_min is None else min(ad_min, dados[u"AD"])
        if dados[u"ER"] is not None:
            er_min = dados[u"ER"] if er_min is None else min(er_min, dados[u"ER"])
        if dados[u"PT"] is not None:
            pt_min = dados[u"PT"] if pt_min is None else min(pt_min, dados[u"PT"])

    return {
        u"nivel":     nome_nivel,
        u"pop":       pop_total,
        u"rooms":     rooms,
        u"grupos":    list(set(grupos)),
        u"cap_ad":    ad_min,
        u"cap_er":    er_min,
        u"cap_pt":    pt_min,
    }


# ===========================================================================
# CÁLCULO PRINCIPAL
# ===========================================================================

def calcular_saidas(rooms_data, nome_terreo=None):
    """
    rooms_data  : list de dicts {nivel, nome, grupo, area, pop}
    nome_terreo : nome do pavimento térreo (string)

    Retorna dict com as três seções normativas:

      "ad"    — list[dict] por pavimento (Acessos e Descargas)
      "er"    — dict único: pavimento de maior pop. excluindo o térreo
                            (ou térreo se edif. unifamiliar)
      "pt"    — list[dict] por pavimento (Portas)
      "nome_terreo"               : str
      "tem_multiplos_pavimentos"  : bool

    Cada dict de pavimento em "ad"/"pt" contém:
        nivel, pop, rooms, grupos, cap, n_up,
        largura_calc, largura_min, largura_adotada
        [pt também: tipo_porta]

    O dict em "er" tem a mesma estrutura + "motivo" (label explicativo).
    """
    from saidas.db import IT

    # --- Agrupar por nível, preservando ordem de elevação ---
    niveis_dict  = {}
    ordem_niveis = []
    for r in rooms_data:
        nivel = r.get(u"nivel") or u"(sem nível)"
        if nivel not in niveis_dict:
            niveis_dict[nivel] = []
            ordem_niveis.append(nivel)
        niveis_dict[nivel].append(r)

    blocos = [_bloco_nivel(niveis_dict[n], n, IT) for n in ordem_niveis]

    tem_multiplos = len(blocos) > 1

    # -----------------------------------------------------------------------
    # SEÇÃO AD — Acessos e Descargas (todos os pavimentos)
    # -----------------------------------------------------------------------
    ad = []
    for b in blocos:
        n_up_val     = _n_up(b[u"pop"], b[u"cap_ad"])
        larg_calc    = round(n_up_val * UP, 2) if n_up_val else None
        larg_adotada = max(larg_calc, LARG_MIN_AD) if larg_calc else LARG_MIN_AD
        ad.append({
            u"nivel":          b[u"nivel"],
            u"pop":            b[u"pop"],
            u"rooms":          b[u"rooms"],
            u"grupos":         b[u"grupos"],
            u"cap":            b[u"cap_ad"],
            u"n_up":           n_up_val,
            u"largura_calc":   larg_calc,
            u"largura_min":    LARG_MIN_AD,
            u"largura_adotada": larg_adotada,
        })

    # -----------------------------------------------------------------------
    # SEÇÃO ER — Escadas e Rampas (pavimento mais carregado, excl. térreo)
    # -----------------------------------------------------------------------
    if tem_multiplos and nome_terreo:
        blocos_sem_terreo = [b for b in blocos if b[u"nivel"] != nome_terreo]
    else:
        blocos_sem_terreo = blocos

    if blocos_sem_terreo:
        b_er = max(blocos_sem_terreo, key=lambda b: b[u"pop"])
    else:
        b_er = blocos[0]

    n_up_er     = _n_up(b_er[u"pop"], b_er[u"cap_er"])
    larg_er_calc = round(n_up_er * UP, 2) if n_up_er else None
    larg_er_adot = max(larg_er_calc, LARG_MIN_ER) if larg_er_calc else LARG_MIN_ER

    motivo = (
        u"Pavimento de maior população (térreo desconsiderado conforme IT 11)"
        if tem_multiplos and nome_terreo
        else u"Pavimento único"
    )

    er = {
        u"nivel":          b_er[u"nivel"],
        u"pop":            b_er[u"pop"],
        u"rooms":          b_er[u"rooms"],
        u"grupos":         b_er[u"grupos"],
        u"cap":            b_er[u"cap_er"],
        u"n_up":           n_up_er,
        u"largura_calc":   larg_er_calc,
        u"largura_min":    LARG_MIN_ER,
        u"largura_adotada": larg_er_adot,
        u"motivo":         motivo,
    }

    # -----------------------------------------------------------------------
    # SEÇÃO PT — Portas (todos os pavimentos)
    # -----------------------------------------------------------------------
    pt = []
    for b in blocos:
        n_up_val      = _n_up(b[u"pop"], b[u"cap_pt"])
        larg_min, tipo = _largura_porta(n_up_val)
        larg_calc     = round(n_up_val * UP, 2) if n_up_val else None
        larg_adotada  = max(larg_calc, larg_min) if (larg_calc and larg_min) else (larg_calc or larg_min)
        pt.append({
            u"nivel":          b[u"nivel"],
            u"pop":            b[u"pop"],
            u"rooms":          b[u"rooms"],
            u"grupos":         b[u"grupos"],
            u"cap":            b[u"cap_pt"],
            u"n_up":           n_up_val,
            u"largura_calc":   larg_calc,
            u"largura_min":    larg_min,
            u"tipo_porta":     tipo,
            u"largura_adotada": larg_adotada,
        })

    return {
        u"ad":                       ad,
        u"er":                       er,
        u"pt":                       pt,
        u"nome_terreo":              nome_terreo,
        u"tem_multiplos_pavimentos": tem_multiplos,
    }


# ===========================================================================
# CACHE JSON
# ===========================================================================

def salvar_cache_saidas(dados):
    with io.open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_cache_saidas():
    if not os.path.exists(_CACHE_PATH):
        return None
    try:
        with io.open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
