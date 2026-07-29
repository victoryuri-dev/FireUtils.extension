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
LARG_MIN_AD = 1.20   # largura mínima padrão para acessos e descargas (m)
LARG_MIN_ER = 1.20   # largura mínima padrão para escadas e rampas (m)

_CACHE_NOME    = u"firedata.json"
_LAST_PROJ_TXT = u"fireutils_last_project.txt"


def _cache_path(projeto_dir=None):
    d = projeto_dir or os.environ.get("TEMP", os.path.expanduser("~"))
    return os.path.join(d, _CACHE_NOME)


def _salvar_ponteiro_projeto(projeto_dir):
    """Grava %TEMP%/fireutils_last_project.txt para que Flask encontre o cache."""
    if not projeto_dir:
        return
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
    try:
        with io.open(os.path.join(temp, _LAST_PROJ_TXT), "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


# ===========================================================================
# HELPERS
# ===========================================================================

def _n_up(populacao, capacidade_por_up):
    if not capacidade_por_up or capacidade_por_up <= 0:
        return None
    return int(math.ceil(populacao / float(capacidade_por_up)))


def _largura_porta(n_up_val, pt_list=None):
    """Largura mínima e tipo de porta.

    pt_list : lista de dicts {n_up, largura, tipo} do estado (estado["larguras_minimas"]["PT"]).
              Se None, usa os valores padrão da IT 11 CBMSP.
    """
    if n_up_val is None:
        return None, u""

    if pt_list:
        # Percorre a lista em ordem crescente de n_up; usa a última entrada
        # cujo n_up seja <= n_up_val (ou a maior disponível).
        largura = None
        tipo    = u"2 folhas"
        for entry in sorted(pt_list, key=lambda e: e[u"n_up"]):
            if n_up_val <= entry[u"n_up"]:
                return entry[u"largura"], entry[u"tipo"]
            largura = entry[u"largura"]
            tipo    = entry[u"tipo"]
        # n_up maior que todas as entradas: calcula pela UP
        return round(n_up_val * UP, 2), tipo

    # Fallback: tabela padrão IT 11 CBMSP
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

def calcular_saidas(rooms_data, nome_terreo=None, estado=None):
    """
    rooms_data  : list de dicts {nivel, nome, grupo, area, pop}
    nome_terreo : nome do pavimento térreo (string)
    estado      : dict do estado (de estados.get_estado); se None usa IT 11 CBMSP padrão

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
    if not estado or u"tabela" not in estado:
        raise ValueError(u"calcular_saidas: estado com 'tabela' é obrigatório.")

    # Resolver tabela e larguras mínimas de acordo com o estado
    IT = estado[u"tabela"]

    larg_ad = LARG_MIN_AD
    larg_er = LARG_MIN_ER
    pt_list  = None
    if estado and u"larguras_minimas" in estado:
        lm = estado[u"larguras_minimas"]
        larg_ad = lm.get(u"AD", LARG_MIN_AD)
        larg_er = lm.get(u"ER", LARG_MIN_ER)
        pt_list  = lm.get(u"PT", None)

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
        larg_adotada = max(larg_calc, larg_ad) if larg_calc else larg_ad
        ad.append({
            u"nivel":          b[u"nivel"],
            u"pop":            b[u"pop"],
            u"rooms":          b[u"rooms"],
            u"grupos":         b[u"grupos"],
            u"cap":            b[u"cap_ad"],
            u"n_up":           n_up_val,
            u"largura_calc":   larg_calc,
            u"largura_min":    larg_ad,
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
    larg_er_adot = max(larg_er_calc, larg_er) if larg_er_calc else larg_er

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
        u"largura_min":    larg_er,
        u"largura_adotada": larg_er_adot,
        u"motivo":         motivo,
    }

    # -----------------------------------------------------------------------
    # SEÇÃO PT — Portas (todos os pavimentos)
    # -----------------------------------------------------------------------
    pt = []
    for b in blocos:
        n_up_val      = _n_up(b[u"pop"], b[u"cap_pt"])
        larg_min, tipo = _largura_porta(n_up_val, pt_list=pt_list)
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

# ===========================================================================
# CACHE — se_import (formato compacto)
# ===========================================================================

def salvar_cache_se_import(se_import, projeto_dir=None):
    """Salva se_import em firedata.json, removendo a chave legada 'saidas'."""
    se_import[u"_projeto_dir"] = projeto_dir or u""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        arquivo = {}
    arquivo[u"saidas_emergencia"] = se_import
    arquivo.pop(u"saidas", None)        # remove formato antigo
    arquivo.pop(u"se_import", None)     # remove chave legada
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)
    _salvar_ponteiro_projeto(projeto_dir)


def carregar_cache_se_import(projeto_dir=None):
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
        return arquivo.get(u"saidas_emergencia") or arquivo.get(u"se_import")
    except Exception:
        return None


# ===========================================================================
# CÁLCULO A PARTIR DE se_import
# ===========================================================================

def _se_import_to_rooms_data(se_import, estado):
    """
    Converte o formato se_import em rooms_data + nome_terreo,
    calculando a população de cada ambiente conforme popTipo.
    """
    tabela = estado.get(u"tabela", {})
    ocups  = estado.get(u"ocupacoes", {})

    rooms_data  = []
    nome_terreo = None

    for pav in se_import.get(u"pavimentos", []):
        nivel = pav[u"nome"]
        if pav.get(u"tipo") == u"descarga":
            nome_terreo = nivel

        for amb in pav.get(u"ambientes", []):
            divisao  = amb[u"divisao"]
            area     = float(amb[u"area"])
            pop_tipo = amb.get(u"popTipo", u"area")

            if pop_tipo == u"area":
                taxa_a = tabela.get(divisao, {}).get(u"A")
                pop    = int(math.ceil(area / float(taxa_a))) if (taxa_a and float(taxa_a) > 0) else 0
            elif pop_tipo == u"fixo":
                pop = int(amb.get(u"assentos", 0))
            else:   # "manual"
                pop = int(amb.get(u"popManual", 0))

            nome_amb = ocups.get(divisao, {}).get(u"descricao", divisao)

            rooms_data.append({
                u"nivel": nivel,
                u"nome":  nome_amb,
                u"grupo": divisao,
                u"area":  area,
                u"pop":   pop,
            })

    return rooms_data, nome_terreo


def calcular_saidas_from_se_import(se_import, estado):
    """
    Calcula AD/ER/PT a partir do formato se_import.

    Retorna (res, rooms_data, nome_terreo).
    """
    rooms_data, nome_terreo = _se_import_to_rooms_data(se_import, estado)
    res = calcular_saidas(rooms_data, nome_terreo=nome_terreo, estado=estado)
    return res, rooms_data, nome_terreo
