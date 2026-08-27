# -*- coding: utf-8 -*-
"""
calc.py — Fire Utils · lib/hidrantes/
Módulo puro de cálculo hidráulico de hidrantes — MÉTODO DA MARCHA.
Sem dependências de Revit ou output — pode ser importado por qualquer script.

Passo a passo implementado (documento "Passo a Passo de Cálculo Hidráulico
de Hidrantes"):

  1. Vazão (Q) e pressão residual mínima (Pmin) de projeto vêm da norma
     vigente (perfil normativo ativo / Tabela 2).
  2. Cenário de cálculo: os 2 hidrantes mais desfavoráveis em funcionamento
     simultâneo (HD01 = mais desfavorável, HD02 = 2º mais desfavorável).
  3. Trechos: Sucção (RTI → Bomba) e Recalque, subdividido no Ponto A
     (ponto de distribuição onde as vazões dos hidrantes se separam):
       T1 = Sucção: RTI → Bomba
       T2 = Bomba → Ponto A
       T3 = Ponto A → HD01
       T4 = Ponto A → HD02
  4. Fator K calculado APENAS do par normativo (Q, Pmin) do hidrante mais
     desfavorável:  K = Q / √P , com P em bar (1 bar = 10,1971 mca).
     O hidrante mais favorável (HD02) recebe pressão maior e portanto
     vazão maior:  Q_hd02 = K·√P_hd02.
  5. Comprimentos equivalentes somados POR TRECHO E POR DIÂMETRO:
     Ltotal(D) = L(D) + Leq(D).
  6. Perda de carga por Hazen-Williams, por trecho e por diâmetro:
       Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87   [m/m]
       (Q em L/min, D = diâmetro interno em mm)
       J   = Ltotal · Jun                            [mca]
  7. Cotas altimétricas: ΔH = Hi − Hf (ponto inicial e final do trecho,
     na direção da marcha de cálculo).
  8. Marcha de pressões (do hidrante mais desfavorável até a RTI):
       P_PA  = P_hd01 + J ± ΔH
       P_SB  = P_PA   + J ± ΔH   (Qt = Q_hd01 + Q_hd02; P_PA = maior pressão
                                  requerida no Ponto A entre os ramais)
       P_RTI = P_SB   + J ± ΔH   (também com Qt)
  9. Verificação de velocidade por trecho/diâmetro:
       V = 21,22 · Q / D²   [m/s]
     Limites: 2,0 m/s (sucção negativa), 3,0 m/s (sucção positiva),
              5,0 m/s (recalque/descarga).
 10. Demanda final do sistema:  Q = Qt  e  P = P_RTI.
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
# Conversão de unidades de pressão usada pelo Fator K (1 bar = 10,1971 mca).
MCA_POR_BAR = 10.1971

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
# FÓRMULAS BÁSICAS (unidades do memorial: Q em L/min, D em mm, P em mca)
# ===========================================================================

def calc_fator_k(q_lmin, p_mca):
    """
    Fator K (coeficiente de vazão) do hidrante mais desfavorável:
        K = Q / √P      [L/min/bar^0,5]
    Q em L/min; P convertida de mca para bar (1 bar = 10,1971 mca).
    """
    p_bar = float(p_mca) / MCA_POR_BAR
    return float(q_lmin) / math.sqrt(p_bar)


def vazao_por_k(k, p_mca):
    """Vazão resultante de uma pressão disponível: Q = K·√P (P em bar)."""
    if p_mca <= 0:
        return 0.0
    return float(k) * math.sqrt(float(p_mca) / MCA_POR_BAR)


def calc_jun(q_lmin, c, d_mm):
    """
    Perda de carga unitária por Hazen-Williams [m/m]:
        Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87
    Q em L/min; D = diâmetro interno em mm; C adimensional.
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


def calc_potencia(qt_m3s, ht_mca, eta_decimal):
    """Potência mínima da bomba em cv: P_cv = (1000·Q·Ht)/(75·η)."""
    return (1000.0 * qt_m3s * ht_mca) / (75.0 * eta_decimal)


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
# RESOLUÇÃO DA REDE — MÉTODO DA MARCHA COM FATOR K
# ===========================================================================

def calcular_rede(trechos_data, Qs_lmin, Pmin, C, cotas,
                  max_iter=30, tol_lmin=0.01):
    """
    Resolve a rede de 2 hidrantes em paralelo pelo método da marcha.

    trechos_data: {"t1","t2","t3","t4"} — dicts de extrair_trecho().
        t1 = Sucção: RTI → Bomba      t2 = Bomba → Ponto A
        t3 = Ponto A → HD01           t4 = Ponto A → HD02
    Qs_lmin, Pmin: par normativo do hidrante mais desfavorável (L/min, mca).
    C: coeficiente de Hazen-Williams.
    cotas: {"z_rti","z_hd01","z_hd02","z_ponto_a","z_recalque","z_succao"} em m.

    Sequência:
      1. K = Q/√P do par normativo (calculado só no hidrante mais desfavorável).
      2. Ramais (marcha hidrante → Ponto A, ΔH = Hi − Hf):
           P_PA(ramal i) = Pmin + J_i ± ΔH_i
         A pressão no Ponto A é a MAIOR requerida entre os ramais; o ramal
         governante opera com o par normativo, o outro recebe o excedente:
           P_hd_i = P_PA − J_i ∓ ΔH_i   →   Q_hd_i = K·√P_hd_i  (≥ Q normativa)
         Como J_i depende de Q_hd_i, itera-se até a vazão estabilizar.
      3. Qt = Q_hd01 + Q_hd02;  P_SB  = P_PA + J(T2, Qt) ± ΔH_t2
      4.                        P_RTI = P_SB + J(T1, Qt) ± ΔH_t1
      5. Demanda final: Q = Qt, P = P_RTI.
    """
    Qs   = float(Qs_lmin)
    Pmin = float(Pmin)

    # ΔH = Hi − Hf por trecho, na direção da marcha de cálculo:
    #   T3/T4: hidrante → Ponto A    T2: Ponto A → saída da bomba (recalque)
    #   T1: sucção da bomba → RTI
    dH = {
        "t3": cotas["z_hd01"]   - cotas["z_ponto_a"],
        "t4": cotas["z_hd02"]   - cotas["z_ponto_a"],
        "t2": cotas["z_ponto_a"] - cotas["z_recalque"],
        "t1": cotas["z_succao"] - cotas["z_rti"],
    }

    K = calc_fator_k(Qs, Pmin)

    Q1 = Qs
    Q2 = Qs
    historico = []
    convergiu = False

    for ciclo in range(1, max_iter + 1):
        j3 = calc_j_trecho(trechos_data["t3"], Q1, C, u"Trecho HD01 ao Ponto A")
        j4 = calc_j_trecho(trechos_data["t4"], Q2, C, u"Trecho HD02 ao Ponto A")

        # Pressão requerida no Ponto A por cada ramal (com Pmin no hidrante)
        P_PA1 = Pmin + j3["J"] + dH["t3"]
        P_PA2 = Pmin + j4["J"] + dH["t4"]
        P_PA  = max(P_PA1, P_PA2)

        # Pressão real em cada hidrante com o Ponto A na maior das duas
        P_hd01 = P_PA - j3["J"] - dH["t3"]
        P_hd02 = P_PA - j4["J"] - dH["t4"]

        # Ajuste de vazão pelo Fator K (o governante volta à vazão normativa)
        Q1_novo = max(Qs, vazao_por_k(K, P_hd01))
        Q2_novo = max(Qs, vazao_por_k(K, P_hd02))

        historico.append({
            "ciclo":   ciclo,
            "Q_hd01":  Q1,       "Q_hd02":  Q2,
            "J_hd01":  j3["J"],  "J_hd02":  j4["J"],
            "P_PA1":   P_PA1,    "P_PA2":   P_PA2,   "P_PA": P_PA,
            "P_hd01":  P_hd01,   "P_hd02":  P_hd02,
            "Q_hd01_novo": Q1_novo, "Q_hd02_novo": Q2_novo,
        })

        estabilizou = (abs(Q1_novo - Q1) < tol_lmin and
                       abs(Q2_novo - Q2) < tol_lmin)
        Q1, Q2 = Q1_novo, Q2_novo
        if estabilizou:
            convergiu = True
            break

    # Trecho Ponto A à descarga da bomba, com Qt e a maior pressão do Ponto A
    Qt = Q1 + Q2
    j2 = calc_j_trecho(trechos_data["t2"], Qt, C, u"Trecho Bomba ao Ponto A")
    P_SB = P_PA + j2["J"] + dH["t2"]

    # Trecho de sucção (também com Qt); P_RTI é a demanda final de pressão
    j1 = calc_j_trecho(trechos_data["t1"], Qt, C, u"Trecho de Sucção (RTI à Bomba)")
    P_RTI = P_SB + j1["J"] + dH["t1"]

    hid_governa = u"HD01" if P_PA1 >= P_PA2 else u"HD02"

    return {
        "K":          K,
        "dH":         dH,
        "j":          {"t1": j1, "t2": j2, "t3": j3, "t4": j4},
        "Q_hd01":     Q1,
        "Q_hd02":     Q2,
        "Qt":         Qt,
        "P_PA1":      P_PA1,
        "P_PA2":      P_PA2,
        "P_PA":       P_PA,
        "P_hd01":     P_hd01,
        "P_hd02":     P_hd02,
        "P_SB":       P_SB,
        "P_RTI":      P_RTI,
        "hid_governa": hid_governa,
        "iteracoes":  len(historico),
        "convergiu":  convergiu,
        "historico":  historico,
    }


# ===========================================================================
# EXTRAÇÃO DE DADOS DO REVIT
# (chamada pelo script Dimensionar, que tem acesso ao Revit)
# ===========================================================================

def extrair_trecho(elems, get_comprimento_fn, get_diametro_fn, get_leq_fn, get_nome_fn):
    """
    Extrai os dados de um trecho AGRUPADOS POR DIÂMETRO INTERNO, como exige o
    passo a passo: um mesmo trecho pode ter variações de diâmetro, e cada
    diâmetro precisa de somatória própria (Ltotal(D) = L(D) + Leq(D)).

    Recebe as funções helper como parâmetro para manter este módulo sem
    imports Revit. Retorna:
        {
          "segmentos": [ { "d_mm", "L", "Leq", "Ltotal", "n_tubos",
                           "acessorios": [ {nome, qtd, leq_unit, leq_tot} ] } ],
          "L":   soma dos comprimentos reais,
          "Leq": soma dos comprimentos equivalentes,
        }

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
                          "n_tubos": 0, "aces": {}}
        return segs[d_mm]

    for elem in elems:
        if isinstance(elem, Pipe):
            d_mm = round(get_diametro_fn(elem) * 1000.0, 1)
            s = _seg(d_mm)
            s["L"]       += get_comprimento_fn(elem)
            s["n_tubos"] += 1
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
