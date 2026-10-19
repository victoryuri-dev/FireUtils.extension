# -*- coding: utf-8 -*-
"""
calc.py — Fire Utils · lib/hidrantes/
O que sobrou do cálculo de hidrantes dentro do plugin: extração dos trechos
do Revit por diâmetro, perda de carga de um trecho (usada só no ranking de
"Mapear Trechos") e o cache entre botões.

O DIMENSIONAMENTO em si — método da marcha, Fator K, equilíbrio hidráulico
no Ponto A, verificação de sucção/NPSH e as verificações normativas — roda
no servidor (Edge Function motor-hidrantes, repositório ETOS.FireUtils) e é
chamado por hidrantes_dimensionar_bridge.py via motor_nuvem.py. Não
reimplemente aqui: o plugin é código que fica no computador do usuário,
e é exatamente por isso que o motor saiu daqui.

Sem dependências de Revit além de extrair_trecho(), que importa o que
precisa dentro da função.
"""

import json
import os
import io
import datetime

from sync import enviar as enviar_sync

# Métodos de cálculo — a escolha é feita em "Classificar Sistema" e define
# ONDE o par normativo (Q, Pmin) é aplicado (o cálculo em si é do motor):
#   Válvula do Hidrante         → Q e Pmin na válvula
#   Ponta do Esguicho Regulável → Q e Pmin na ponta do esguicho
METODO_VALVULA  = u"Válvula do Hidrante"
METODO_ESGUICHO = u"Ponta do Esguicho Regulável"
METODOS_CALCULO = [METODO_VALVULA, METODO_ESGUICHO]

_CACHE_NOME    = u"firedata.json"
_LAST_PROJ_TXT = u"fireutils_last_project.txt"


def eh_metodo_esguicho(metodo):
    """True se o método de cálculo referencia o par normativo no esguicho."""
    return (metodo or u"").strip() == METODO_ESGUICHO


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
# FÓRMULAS BÁSICAS (unidades do memorial: Q em L/min, D em mm, P em mca)
# ===========================================================================

def calc_jun(q_lmin, c, d_mm):
    """
    Perda de carga unitária por Hazen-Williams [m/m]:
        Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87
    Q em L/min; D = diâmetro NOMINAL (DN) em mm (não o diâmetro interno
    real); C adimensional.
    """
    if q_lmin <= 0 or d_mm <= 0:
        return 0.0
    return (605.0 * (10.0 ** 4)
            * (float(q_lmin) ** 1.85)
            * (float(c) ** -1.85)
            * (float(d_mm) ** -4.87))


def calc_velocidade(q_lmin, d_mm):
    """Velocidade de escoamento [m/s]: V = 21,22 · Q / D² (Q em L/min, D em mm)."""
    if d_mm <= 0:
        return 0.0
    return 21.22 * float(q_lmin) / (float(d_mm) ** 2)


# ===========================================================================
# PERDA DE CARGA DE UM TRECHO (por diâmetro)
# ===========================================================================

def calc_j_trecho(trecho_data, q_lmin, c, label=u""):
    """
    Aplica Hazen-Williams a um trecho, POR SEGMENTO DE DIÂMETRO, e soma:
        J_trecho = Σ [ Ltotal(D) · Jun(Q, C, D) ]

    trecho_data: dict de extrair_trecho() — {"segmentos": [...], "L", "Leq"}.
    Retorna dict com os segmentos calculados (Jun, J e V por diâmetro),
    a perda total J e a maior velocidade encontrada no trecho.
    """
    segmentos = []
    J_total = 0.0
    V_max   = 0.0
    for seg in trecho_data["segmentos"]:
        jun = calc_jun(q_lmin, c, seg["d_mm"])
        j   = jun * seg["Ltotal"]
        v   = calc_velocidade(q_lmin, seg["d_mm"])
        J_total += j
        if v > V_max:
            V_max = v
        s = dict(seg)
        s["Jun"] = jun
        s["J"]   = j
        s["V"]   = v
        segmentos.append(s)
    return {
        "label":     label,
        "Q_lmin":    q_lmin,
        "segmentos": segmentos,
        "J":         J_total,
        "V_max":     V_max,
        "L":         trecho_data["L"],
        "Leq":       trecho_data["Leq"],
    }


# ===========================================================================
# EXTRAÇÃO DE DADOS DO REVIT
# (chamada pelo script Dimensionar, que tem acesso ao Revit)
# ===========================================================================

def extrair_trecho(elems, get_comprimento_fn, get_diametro_fn, get_leq_fn, get_nome_fn,
                   get_id_fn=None):
    """
    Extrai os dados de um trecho AGRUPADOS POR DIÂMETRO NOMINAL (DN), como
    exige o passo a passo: um mesmo trecho pode ter variações de diâmetro, e
    cada diâmetro precisa de somatória própria (Ltotal(D) = L(D) + Leq(D)).
    "d_mm" nos segmentos abaixo é sempre o DN (get_diametro_fn deve
    retornar o diâmetro nominal do elemento, não o interno real).

    Recebe as funções helper como parâmetro para manter este módulo sem
    imports Revit. get_id_fn é opcional (deve devolver um int, o
    ElementId do tubo) — habilita o botão "Mostrar no Projeto" das
    janelas de bloqueio (resultado_ui.py), selecionando exatamente os
    tubos do diâmetro que reprovou. Retorna:
        {
          "segmentos": [ { "d_mm", "L", "Leq", "Ltotal", "n_tubos", "ids",
                           "acessorios": [ {nome, qtd, leq_unit, leq_tot} ] } ],
          "L":   soma dos comprimentos reais,
          "Leq": soma dos comprimentos equivalentes,
        }
    "ids": lista de ElementId (int) dos tubos (Pipe) daquele diâmetro —
    vazia se get_id_fn não foi informado.

    Acessórios são agrupados por nome do tipo dentro de cada diâmetro.
    le_unit é a média exata dos valores acumulados (leq_tot / qtd), garantindo
    por construção que qtd × le_unit == leq_tot em toda linha do memorial.
    """
    from Autodesk.Revit.DB.Plumbing import Pipe
    from Autodesk.Revit.DB import FamilyInstance

    segs = {}

    def _seg(d_mm):
        if d_mm not in segs:
            segs[d_mm] = {"d_mm": d_mm, "L": 0.0, "Leq": 0.0,
                          "n_tubos": 0, "ids": [], "aces": {}}
        return segs[d_mm]

    for elem in elems:
        if isinstance(elem, Pipe):
            d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
            s = _seg(d_mm)
            s["L"]       += get_comprimento_fn(elem)
            s["n_tubos"] += 1
            if get_id_fn is not None:
                s["ids"].append(get_id_fn(elem))
        elif isinstance(elem, FamilyInstance):
            leq = get_leq_fn(elem)
            if leq > 0:
                d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
                s = _seg(d_mm)
                s["Leq"] += leq
                nome = get_nome_fn(elem)
                if nome in s["aces"]:
                    s["aces"][nome]["qtd"]     += 1
                    s["aces"][nome]["leq_tot"] += leq
                else:
                    s["aces"][nome] = {"qtd": 1, "leq_tot": leq, "nome": nome}

    segmentos = []
    for d_mm in sorted(segs.keys()):
        s = segs[d_mm]
        acessorios = []
        for v in s["aces"].values():
            leq_unit = v["leq_tot"] / float(v["qtd"])
            acessorios.append({
                "nome":     v["nome"],
                "qtd":      v["qtd"],
                "leq_unit": leq_unit,
                "leq_tot":  v["leq_tot"],
            })
        acessorios.sort(key=lambda a: a["nome"])
        segmentos.append({
            "d_mm":       s["d_mm"],
            "L":          s["L"],
            "Leq":        s["Leq"],
            "Ltotal":     s["L"] + s["Leq"],
            "n_tubos":    s["n_tubos"],
            "ids":        s["ids"],
            "acessorios": acessorios,
        })

    return {
        "segmentos": segmentos,
        "L":   sum(s["L"]   for s in segmentos),
        "Leq": sum(s["Leq"] for s in segmentos),
    }


# ===========================================================================
# CACHE — salvar e carregar resultados entre botões
# ===========================================================================

_MENSAGENS_ERRO_CACHE = {
    u"hidrantes": u"Nenhum dimensionamento encontrado.\nDimensione o sistema na aba 'Sistema de Hidrantes' do painel Fire Utils primeiro.",
    u"rotas":     u"Nenhum mapeamento de rotas encontrado.\nExecute 'Mapear Trechos' primeiro.",
}


def salvar_cache(payload, projeto_dir=None, chave=u"hidrantes"):
    """Salva `payload` na chave indicada (`hidrantes` = resultado do
    dimensionamento; `rotas` = mapeamento de trechos salvo por "Mapear
    Trechos") do arquivo unificado firedata.json. Só a chave 'hidrantes'
    é enviada ao site (sync) — 'rotas' é puramente interna, IDs de
    elemento do Revit sem sentido fora do próprio projeto."""
    payload["_timestamp"]   = datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S")
    payload["_projeto_dir"] = projeto_dir or u""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
    except Exception:
        dados = {}
    dados[chave] = payload
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    _salvar_ponteiro_projeto(projeto_dir)

    if chave == u"hidrantes":
        enviar_sync(u"hidrantes", payload, projeto_dir)

    return path


def carregar_cache(projeto_dir=None, chave=u"hidrantes"):
    """Retorna (payload, erro). Se erro não for None, payload é None."""
    mensagem_erro = _MENSAGENS_ERRO_CACHE.get(chave, _MENSAGENS_ERRO_CACHE[u"hidrantes"])
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return None, mensagem_erro
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
        payload = dados.get(chave)
        if payload is None:
            return None, mensagem_erro
        return payload, None
    except Exception as e:
        return None, u"Erro ao ler cache: {}".format(str(e))


def cache_existe(projeto_dir=None, chave=u"hidrantes"):
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return False
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return chave in json.loads(f.read())
    except Exception:
        return False
