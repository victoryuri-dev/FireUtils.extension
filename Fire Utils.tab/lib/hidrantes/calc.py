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
                   get_id_fn=None, get_tipo_conexao_fn=None, get_pipe_type_fn=None):
    """
    Extrai os dados de um trecho AGRUPADOS POR DIÂMETRO NOMINAL (DN) E POR
    TIPO DE TUBO (PipeType do Revit, ver get_pipe_type_fn abaixo) — um mesmo
    trecho pode ter variações de diâmetro E de material, e cada combinação
    precisa de somatória própria (Ltotal(D) = L(D) + Leq(D)). "d_mm" nos
    segmentos abaixo é sempre o DN (get_diametro_fn deve retornar o
    diâmetro nominal do elemento, não o interno real).

    Recebe as funções helper como parâmetro para manter este módulo sem
    imports Revit. get_id_fn é opcional (deve devolver um int, o
    ElementId do tubo) — habilita o botão "Mostrar no Projeto" das
    mensagens de bloqueio da dockpane, selecionando exatamente os
    tubos do diâmetro que reprovou. Retorna:
        {
          "segmentos": [ { "d_mm", "L", "Leq", "Ltotal", "n_tubos", "ids",
                           "pipe_type_id", "pipe_type_nome",
                           "acessorios": [ {nome, qtd, leq_unit, leq_tot} ],
                           "conexoes": [ {tipo, qtd, angulo_graus, d2_mm, sistema} ] } ],
          "L":   soma dos comprimentos reais,
          "Leq": soma dos acessórios ainda dependentes do parâmetro de
                 família (ver get_leq) — o Leq das conexões em "conexoes"
                 é calculado do outro lado, pelo motor de cálculo.
        }
    "ids": lista de ElementId (int) dos tubos (Pipe) daquele diâmetro —
    vazia se get_id_fn não foi informado.

    get_tipo_conexao_fn é opcional (classifica cotovelo/tê/redução/
    tampão/união/luva Y pelo tipo nativo do Revit — ver get_tipo_conexao
    em rede.py). Quando devolve algo para um FamilyInstance, o elemento
    vai para "conexoes" (sem usar get_leq_fn: essas conexões não dependem
    mais do parâmetro "Perda de Carga"). Quando devolve None — inclusive
    se get_tipo_conexao_fn não foi passado — o elemento cai no fluxo
    antigo (get_leq_fn/"acessorios"), ainda usado por válvulas e outros
    acessórios não migrados.

    get_pipe_type_fn é opcional (devolve (pipe_type_id, pipe_type_nome) —
    ver get_pipe_type/get_pipe_type_no_trecho em rede.py). Elemento sem
    PipeType resolvível (ou get_pipe_type_fn não informado) cai no grupo
    (pipe_type_id=None) — o material desse segmento fica indefinido, e o
    motor usa o C padrão (hazen_c.galvanizado), igual ao comportamento de
    antes desta funcionalidade existir.

    Acessórios e conexões são agrupados por (nome do tipo) e (tipo,
    ângulo, d2, sistema) respectivamente, dentro de cada (diâmetro,
    pipe_type). leq_unit é a média exata dos valores acumulados
    (leq_tot / qtd), garantindo por construção que qtd × leq_unit ==
    leq_tot em toda linha do memorial.
    """
    from Autodesk.Revit.DB.Plumbing import Pipe
    from Autodesk.Revit.DB import FamilyInstance

    segs = {}

    def _seg(d_mm, pipe_type_id, pipe_type_nome):
        chave = (d_mm, pipe_type_id)
        if chave not in segs:
            segs[chave] = {"d_mm": d_mm, "pipe_type_id": pipe_type_id, "pipe_type_nome": pipe_type_nome,
                          "L": 0.0, "Leq": 0.0, "n_tubos": 0, "ids": [], "aces": {}, "conexoes": {}}
        return segs[chave]

    def _pipe_type(elem):
        if get_pipe_type_fn is None:
            return (None, None)
        return get_pipe_type_fn(elem) or (None, None)

    for elem in elems:
        if isinstance(elem, Pipe):
            d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
            pipe_type_id, pipe_type_nome = _pipe_type(elem)
            s = _seg(d_mm, pipe_type_id, pipe_type_nome)
            s["L"]       += get_comprimento_fn(elem)
            s["n_tubos"] += 1
            if get_id_fn is not None:
                s["ids"].append(get_id_fn(elem))
        elif isinstance(elem, FamilyInstance):
            d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
            pipe_type_id, pipe_type_nome = _pipe_type(elem)
            tipo_conexao = get_tipo_conexao_fn(elem, d_mm) if get_tipo_conexao_fn else None
            if tipo_conexao is not None:
                s = _seg(d_mm, pipe_type_id, pipe_type_nome)
                chave = (tipo_conexao["tipo"], tipo_conexao["angulo_graus"], tipo_conexao["d2_mm"],
                         tipo_conexao.get("sistema"))
                if chave in s["conexoes"]:
                    s["conexoes"][chave]["qtd"] += 1
                else:
                    s["conexoes"][chave] = {
                        "tipo": tipo_conexao["tipo"],
                        "angulo_graus": tipo_conexao["angulo_graus"],
                        "d2_mm": tipo_conexao["d2_mm"],
                        "sistema": tipo_conexao.get("sistema") or "bsp",
                        "qtd": 1,
                    }
                continue
            leq = get_leq_fn(elem)
            if leq > 0:
                s = _seg(d_mm, pipe_type_id, pipe_type_nome)
                s["Leq"] += leq
                nome = get_nome_fn(elem)
                if nome in s["aces"]:
                    s["aces"][nome]["qtd"]     += 1
                    s["aces"][nome]["leq_tot"] += leq
                else:
                    s["aces"][nome] = {"qtd": 1, "leq_tot": leq, "nome": nome}

    # Junta (d_mm, pipe_type_id) sem NENHUM tubo de verdade — só conexão,
    # ex. válvula/união bem na entrada da bomba, sem Pipe vizinho dentro
    # do próprio trecho (ver get_pipe_type_no_trecho em rede.py) — no
    # grupo do mesmo diâmetro que TEM tubo, quando existe só um. Esse
    # grupo "fantasma" (mesmo diâmetro, 0 m de tubo) tinha a MESMA
    # velocidade do segmento real (V só depende de Q/D) e virava uma
    # linha duplicada na verificação de velocidade e no aviso de limite,
    # sem acrescentar nada — "tipo de tubo" não identificável pra uma
    # conexão não deveria virar segmento próprio (combinacoes_pipe_type já
    # ignora essas conexões na descoberta/UI; isso alinha o cálculo).
    por_diametro = {}
    for chave in segs:
        por_diametro.setdefault(segs[chave]["d_mm"], []).append(chave)
    for d_mm, chaves in por_diametro.items():
        if len(chaves) < 2:
            continue
        com_tubo = [c for c in chaves if segs[c]["n_tubos"] > 0]
        sem_tubo = [c for c in chaves if segs[c]["n_tubos"] == 0]
        if len(com_tubo) != 1 or not sem_tubo:
            continue
        alvo = segs[com_tubo[0]]
        for chave in sem_tubo:
            origem = segs.pop(chave)
            alvo["Leq"] += origem["Leq"]
            for nome, v in origem["aces"].items():
                if nome in alvo["aces"]:
                    alvo["aces"][nome]["qtd"]     += v["qtd"]
                    alvo["aces"][nome]["leq_tot"] += v["leq_tot"]
                else:
                    alvo["aces"][nome] = dict(v)
            for chave_cx, v in origem["conexoes"].items():
                if chave_cx in alvo["conexoes"]:
                    alvo["conexoes"][chave_cx]["qtd"] += v["qtd"]
                else:
                    alvo["conexoes"][chave_cx] = dict(v)

    segmentos = []
    for chave in sorted(segs.keys(), key=lambda c: (c[0], c[1] is None, c[1] or 0)):
        s = segs[chave]
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
        conexoes = sorted(s["conexoes"].values(),
                          key=lambda c: (c["tipo"], c["angulo_graus"] or 0, c["d2_mm"] or 0, c["sistema"]))
        segmentos.append({
            "d_mm":           s["d_mm"],
            "pipe_type_id":   s["pipe_type_id"],
            "pipe_type_nome": s["pipe_type_nome"],
            "L":              s["L"],
            "Leq":            s["Leq"],
            "Ltotal":         s["L"] + s["Leq"],
            "n_tubos":        s["n_tubos"],
            "ids":            s["ids"],
            "acessorios":     acessorios,
            "conexoes":       conexoes,
        })

    return {
        "segmentos": segmentos,
        "L":   sum(s["L"]   for s in segmentos),
        "Leq": sum(s["Leq"] for s in segmentos),
    }


def combinacoes_pipe_type(elems, get_diametro_fn, get_pipe_type_fn, get_id_fn=None):
    """
    Lista, SEM calcular nada (só pra descoberta/exibição), as combinações
    (pipe_type_id, pipe_type_nome) encontradas nos TUBOS (Pipe) de `elems`
    e os diâmetros (DN, mm) de cada uma. Usado por "Mapear Trechos" pra
    informar a dockpane quais (etapa, tipo de tubo) existem de fato no
    modelo, pra ela desenhar o seletor de material/sistema de conexão
    (ver hidrantes_mapear_bridge.py, material_conexao.py).

    SÓ considera elementos Pipe — conexões/acessórios (FamilyInstance)
    são ignorados aqui de propósito, mesmo que get_pipe_type_fn consiga
    resolver um tipo pra eles (emprestado do tubo vizinho, ver
    get_pipe_type_no_trecho em rede.py): "tipo de tubo" é conceito de
    TUBO, não de conexão — uma válvula/união na entrada da bomba não deve
    aparecer como membro de um grupo nem fazer a dockpane pedir uma
    escolha extra por causa dela. extrair_trecho (cálculo de verdade)
    continua emprestando o material do vizinho pras conexões, sem
    mudança nenhuma — só esta função de descoberta/UI ficou restrita a
    Pipe.

    get_id_fn é opcional (devolve um int, o ElementId do elemento) —
    habilita o botão "Localizar" de cada grupo na dockpane.

    Retorna [ {"id", "nome", "diametros": [d_mm, ...], "eids": [...]} ],
    ordenado por id (grupo sem pipe_type, id None, por último). "eids"
    vazio se get_id_fn não foi informado.
    """
    from Autodesk.Revit.DB.Plumbing import Pipe

    grupos = {}
    ordem = []
    for elem in elems:
        if not isinstance(elem, Pipe):
            continue
        pipe_type_id, pipe_type_nome = get_pipe_type_fn(elem) or (None, None)
        if pipe_type_id not in grupos:
            grupos[pipe_type_id] = {"id": pipe_type_id, "nome": pipe_type_nome, "diametros": set(), "eids": []}
            ordem.append(pipe_type_id)
        d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
        grupos[pipe_type_id]["diametros"].add(d_mm)
        if get_id_fn is not None:
            grupos[pipe_type_id]["eids"].append(get_id_fn(elem))

    saida = [{"id": g["id"], "nome": g["nome"], "diametros": sorted(g["diametros"]), "eids": g["eids"]}
             for g in (grupos[pid] for pid in ordem)]
    saida.sort(key=lambda g: (g["id"] is None, g["id"] or 0))
    return saida


# ===========================================================================
# CACHE — salvar e carregar resultados entre botões
# ===========================================================================

_MENSAGENS_ERRO_CACHE = {
    u"hidrantes": u"Nenhum dimensionamento encontrado.\nDimensione o sistema na aba 'Sistema de Hidrantes' do painel Fire Utils primeiro.",
    u"rotas":     u"Nenhum mapeamento de rotas encontrado.\nMapeie os trechos na aba 'Sistema de Hidrantes' do painel Fire Utils primeiro.",
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
