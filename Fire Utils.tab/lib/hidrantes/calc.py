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
  4. O método de cálculo (definido em "Classificar Sistema") diz ONDE o par
     normativo (Q, Pmin) se aplica:
       - "Válvula do Hidrante": na válvula. P de referência = Pmin.
       - "Ponta do Esguicho Regulável": na ponta do esguicho. Entre o
         esguicho e a válvula entram a mangueira e a válvula angular:
           Jm    = 8·f·Lm/(g·π²·Dm⁵)·Q²   (Darcy-Weisbach, f = 0,022)
           V     = 21,22·Q/Dm²             (velocidade na mangueira)
           Jvalv = K_v·V²/(2g)             (válvula angular, K_v = 5)
           P de referência (na válvula) = Pmin + Jm + Jvalv
     Fator K calculado APENAS no hidrante mais desfavorável, com esse P de
     referência:  K = Q / √P , com P em bar (1 bar = 10,1971 mca).
     O hidrante mais favorável (HD02) recebe pressão maior e portanto
     vazão maior:  Q_hd02 = K·√P_hd02.
  5. Comprimentos equivalentes somados POR TRECHO E POR DIÂMETRO:
     Ltotal(D) = L(D) + Leq(D).
  6. Perda de carga por Hazen-Williams, por trecho e por diâmetro:
       Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87   [m/m]
       (Q em L/min, D = diâmetro NOMINAL (DN) em mm — não o diâmetro
       interno real do tubo; ex.: DN 65 usa D=65 mm mesmo que o
       diâmetro interno medido seja 68,8 mm)
       J   = Ltotal · Jun                            [mca]
  7. Cotas altimétricas: ΔH = Hi − Hf (ponto inicial e final do trecho,
     na direção da marcha de cálculo).
  8. Equilíbrio hidráulico no Ponto A: HD01 e HD02 são calculados uma
     primeira vez com a MESMA vazão mínima Qs, e a maior pressão requerida
     no nó (P_PA) vira a pressão-alvo — o ramal dela é o GOVERNANTE e não
     muda mais. O outro ramal (mais favorável) converge iterativamente até
     sua própria P_A bater com a pressão-alvo, recalculando Hazen-Williams
     a cada passo — nunca reaproveitando a perda de carga de uma vazão
     diferente. Converge dentro da variação máxima de pressão admitida
     pela norma entre os ramais (perfil normativo ativo, chave
     "tolerancia_equilibrio_mca" — ex.: 0,50 mca na NT 22/2021 - CBMMA).
     Só depois de convergido soma-se Qt = Q_hd01 + Q_hd02.
  9. Marcha de pressões (do hidrante mais desfavorável até a RTI):
       P_PA  = P_hd01 + J ± ΔH
       P_SB  = P_PA   + J ± ΔH   (Qt = Q_hd01 + Q_hd02, já equilibradas)
       P_RTI = P_SB   + J ± ΔH   (também com Qt)
 10. Verificação de velocidade por trecho/diâmetro:
       V = 21,22 · Q / D²   [m/s]
     Limites: 2,0 m/s (sucção negativa), 3,0 m/s (sucção positiva),
              5,0 m/s (recalque/descarga).
 11. Demanda final do sistema:  Q = Qt  e  P = P_RTI.
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

# Constantes do trecho esguicho → mangueira → válvula (método "Ponta do
# Esguicho Regulável"). O coeficiente 8 da fórmula de Jm vem da própria
# substituição de Darcy-Weisbach: Jm = f·(Lm/Dm)·(Vm²/2g), com
# Vm = 4·Qi/(π·Dm²) (velocidade média na mangueira a partir da vazão
# individual do hidrante), o que dá Jm = 8·f·Lm/(g·π²·Dm⁵)·Qi² — não é uma
# constante arbitrária de documento.
F_DARCY     = 0.022   # fator de atrito da mangueira
G           = 9.81    # aceleração da gravidade, m/s²
K_VALVULA   = 5.0     # coef. de perda localizada da válvula angular
COEF_JM     = 8.0     # coeficiente da fórmula de Jm, de Darcy-Weisbach com Vm=4Qi/(πDm²)

# Equilíbrio hidráulico entre os ramais no Ponto A (ver _equilibrar_ramal).
# A variação máxima admitida entre a pressão do ramal mais favorável e a
# pressão-alvo imposta pelo ramal governante É NORMATIVA (ex.: NT 22/2021 -
# CBMMA: "para efeito de equilíbrio de pressão no ponto de derivação da
# vazão total ... é admitida a variação máxima de 0,50 mca") — por isso não
# tem default aqui: calcular_rede() exige que o chamador informe o valor do
# perfil normativo ativo (lib/normas/<UF>/hidrantes.py, chave
# "tolerancia_equilibrio_mca").
MAX_ITER_EQUILIBRIO = 30   # trava de segurança contra não-convergência (não normativo)

# Métodos de cálculo — a escolha é feita em "Classificar Sistema" e define
# ONDE o par normativo (Q, Pmin) é aplicado:
#   Válvula do Hidrante        → Q e Pmin na válvula (não há mangueira no cálculo)
#   Ponta do Esguicho Regulável → Q e Pmin na ponta do esguicho; a marcha
#                                 sobe pelo esguicho → mangueira (Jm) →
#                                 válvula (Jvalv) antes de seguir pela rede
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


def calc_potencia(qt_m3s, ht_mca, eta_decimal):
    """Potência mínima da bomba em cv: P_cv = (1000·Q·Ht)/(75·η)."""
    return (1000.0 * qt_m3s * ht_mca) / (75.0 * eta_decimal)


# ===========================================================================
# ESGUICHO → MANGUEIRA → VÁLVULA (método "Ponta do Esguicho Regulável")
# ===========================================================================

def calc_jm_mangueira(q_lmin, lm_m, dm_m, f=F_DARCY):
    """
    Perda de carga na mangueira, por Darcy-Weisbach:

        Jm = f · (Lm/Dm) · (Vm²/2g),  Vm = 4·Q/(π·Dm²)

    que, substituindo Vm, fecha em:

        Jm = 8·f·Lm / (g·π²·Dm⁵) · Q²

    Q é a vazão INDIVIDUAL da mangueira (nunca Qt nem Qt/2 — cada hidrante
    tem sua própria mangueira e sua própria vazão, que pode divergir da do
    outro hidrante depois do equilíbrio hidráulico). Q é convertida de
    L/min para m³/s; Lm e Dm em metros (a fórmula só fecha
    dimensionalmente em SI).
    """
    if lm_m <= 0 or dm_m <= 0:
        return 0.0
    q_m3s = float(q_lmin) / 60000.0
    return ((COEF_JM * f * float(lm_m))
            / (G * (math.pi ** 2) * (float(dm_m) ** 5))
            * (q_m3s ** 2))


def calc_jvalv(v_ms, k_valv=K_VALVULA):
    """
    Perda de carga localizada na válvula angular do hidrante:
        Jvalv = K · v² / (2g)
    v = velocidade do fluido na mangueira [m/s]; K = 5 (adotado em projeto).
    """
    return float(k_valv) * (float(v_ms) ** 2) / (2.0 * G)


def calc_cadeia_esguicho(q_lmin, mang_dn_mm, mang_comp_m, p_valv_mca=None,
                         p_esg_mca=None):
    """
    Resolve o trecho entre a ponta do esguicho e a válvula do hidrante.

        Jm    = 8·f·Lm/(g·π²·Dm⁵)·Q²      (perda na mangueira, Darcy-Weisbach)
        V     = 21,22·Q/Dm²                (velocidade na mangueira)
        Jvalv = K·V²/(2g)                  (perda na válvula angular)
        P_valv = P_esg + Jm + Jvalv        (marcha esguicho → válvula)

    Informe p_esg_mca para subir do esguicho até a válvula (dimensionamento
    do hidrante governante), ou p_valv_mca para descer da válvula até o
    esguicho (demais hidrantes, cuja vazão já saiu do Fator K).
    """
    dm_m  = float(mang_dn_mm) / 1000.0
    jm    = calc_jm_mangueira(q_lmin, mang_comp_m, dm_m)
    v     = calc_velocidade(q_lmin, mang_dn_mm)
    jvalv = calc_jvalv(v)

    if p_esg_mca is not None:
        p_esg  = float(p_esg_mca)
        p_valv = p_esg + jm + jvalv
    else:
        p_valv = float(p_valv_mca)
        p_esg  = p_valv - jm - jvalv

    return {
        "Q_lmin": q_lmin,
        "Jm":     jm,
        "V":      v,
        "Jvalv":  jvalv,
        "P_esg":  p_esg,
        "P_valv": p_valv,
    }


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
# EQUILÍBRIO HIDRÁULICO ENTRE RAMAIS NO PONTO A
# ===========================================================================

def _equilibrar_ramal(trecho_data, K, P_alvo, dH_ramal, C, j_inicial,
                      tolerancia_mca, max_iter=MAX_ITER_EQUILIBRIO):
    """
    Converge iterativamente a vazão do ramal MAIS FAVORÁVEL (o que não
    governa o Ponto A) até sua pressão requerida lá (P_A) coincidir com a
    pressão-alvo já fixada pelo ramal governante — P_A1 ≈ P_A2, dentro da
    variação máxima admitida pela norma (tolerancia_mca — vem do perfil
    normativo ativo, não é um número livre do código).

    O ramal governante não entra aqui: por construção (é dele que a
    pressão-alvo veio) ele já está em equilíbrio, com Q = Qs e
    P_valv = P_valv_ref.

    A cada passo:
        P_ref = P_alvo − J_atual − ∆H    (marcha inversa, com o J da passada anterior)
        Q     = K · √(P_ref / 10,1971)    (vazão pelo Fator K)
        J_novo = Hazen-Williams NESSA vazão (Jun muda porque Q mudou —
                 nunca reaproveitar a perda de carga de uma vazão diferente)
        P_A   = P_ref + J_novo + ∆H       (marcha direta, conferência)
        erro  = |P_A − P_alvo|            (= |J_novo − J_atual|, por construção)

    Converge quando erro <= tolerancia_mca. Para na trava de segurança
    max_iter sem convergir só em caso patológico (rede com geometria
    inviável) — o chamador decide o que fazer com "convergiu": False.

    Retorna dict com Q/P_ref/j/P_A/erro FINAIS e o histórico de iterações
    (uma linha por passo, cada uma já com o "j" completo — por diâmetro —
    daquele passo, não só o J total), pronto para o memorial narrar cada
    iteração (diferença de pressão → Fator K → Hazen-Williams → P_A nova).
    """
    J_atual   = j_inicial["J"]
    label     = j_inicial.get("label", u"")
    historico = []
    convergiu = False

    P_ref = P_alvo - J_atual - dH_ramal
    Q_novo = j_inicial.get("Q_lmin", 0.0)
    j_novo = j_inicial
    P_A_novo = P_alvo
    erro = 0.0

    for n in range(1, int(max_iter) + 1):
        P_ref = P_alvo - J_atual - dH_ramal
        Q_novo = vazao_por_k(K, P_ref)
        j_novo = calc_j_trecho(trecho_data, Q_novo, C, label)
        P_A_novo = P_ref + j_novo["J"] + dH_ramal
        erro = abs(P_A_novo - P_alvo)
        historico.append({
            "n":     n,
            "P_ref": P_ref,
            "Q":     Q_novo,
            "J":     j_novo["J"],
            "j":     j_novo,   # trecho completo (por diâmetro) desta iteração — memorial
            "P_A":   P_A_novo,
            "erro":  erro,
        })
        J_atual = j_novo["J"]
        if erro <= tolerancia_mca:
            convergiu = True
            break

    return {
        "Q":          Q_novo,
        "P_ref":      P_ref,
        "j":          j_novo,
        "P_A":        P_A_novo,
        "erro":       erro,
        "historico":  historico,
        "convergiu":  convergiu,
        "tolerancia": tolerancia_mca,
    }


# ===========================================================================
# RESOLUÇÃO DA REDE — MÉTODO DA MARCHA COM FATOR K
# ===========================================================================

def calcular_rede(trechos_data, Qs_lmin, Pmin, C, cotas, tolerancia_equilibrio_mca,
                  metodo=METODO_VALVULA, mang_dn_mm=None, mang_comp_m=None,
                  max_iter_equilibrio=MAX_ITER_EQUILIBRIO):
    """
    Resolve a rede de 2 hidrantes em paralelo pelo método da marcha, com
    EQUILÍBRIO HIDRÁULICO ITERATIVO entre os dois ramais no Ponto A.

    trechos_data: {"t1","t2","t3","t4"} — dicts de extrair_trecho().
        t1 = Sucção: RTI → Bomba      t2 = Bomba → Ponto A
        t3 = Ponto A → HD01           t4 = Ponto A → HD02
    Qs_lmin, Pmin: par normativo do hidrante mais desfavorável (L/min, mca).
    C: coeficiente de Hazen-Williams.
    cotas: {"z_rti","z_hd01","z_hd02","z_ponto_a","z_recalque","z_succao"} em m.
    tolerancia_equilibrio_mca: variação máxima de pressão admitida pela
        norma entre os ramais no Ponto A, após o equilíbrio (obrigatório —
        vem do perfil normativo ativo, chave "tolerancia_equilibrio_mca";
        ver _equilibrar_ramal()).
    metodo: METODO_VALVULA ou METODO_ESGUICHO — define onde (Qs, Pmin) se
        aplicam. No método do esguicho, mang_dn_mm e mang_comp_m são
        obrigatórios (mangueira entre o esguicho e a válvula).
    max_iter_equilibrio: trava de segurança (não normativa) — ver
        _equilibrar_ramal().

    Sequência:
      1. Ponto de referência do par normativo:
         - Válvula:  P_valv_ref = Pmin (não há mangueira no cálculo).
         - Esguicho: Pmin está na ponta do esguicho; sobe-se até a válvula
             Jm    = 8·f·Lm/(g·π²·Dm⁵)·Qs²
             V     = 21,22·Qs/Dm²        Jvalv = K·V²/(2g)
             P_valv_ref = Pmin + Jm + Jvalv
      2. K = Qs/√P_valv_ref — calculado só no hidrante mais desfavorável;
         é ele que dá a vazão dos demais hidrantes.
      3. Cálculo INICIAL: Hazen-Williams nos dois ramais, ambos com a
         MESMA vazão normativa Qs:
           P_PA(ramal i) = P_valv_ref + J_i ± ΔH_i
      4. Ponto A adota a MAIOR pressão requerida entre os ramais como
         pressão-alvo — o ramal dessa pressão é o GOVERNANTE e não muda
         mais (por construção, sua vazão já é Qs e sua pressão na válvula
         já é P_valv_ref, a mesma origem do Fator K):
           P_PA,alvo = max(P_PA1, P_PA2)
      5. EQUILÍBRIO: o ramal MAIS FAVORÁVEL converge iterativamente até
         sua própria P_A bater com a pressão-alvo (_equilibrar_ramal) —
         a cada passo, a vazão muda e a perda de carga é recalculada com
         essa nova vazão, nunca reaproveitada de um passo anterior:
           P_ref = P_PA,alvo − J_atual − ΔH
           Q     = K·√(P_ref / 10,1971)
           J_novo = Hazen-Williams(Q)          ← Jun muda com Q
           P_A   = P_ref + J_novo + ΔH
           erro  = |P_A − P_PA,alvo|
         Repete até erro ≤ tolerância.
      6. Só DEPOIS de convergido, soma-se a vazão: Qt = Q_hd01 + Q_hd02.
         No método do esguicho, Jm/V/Jvalv de cada hidrante são então
         recalculados com a vazão final de equilíbrio (crescem em direção
         aos pontos mais favoráveis) e a pressão no esguicho sai de
           P_esg_i = P_hd_i − Jm_i − Jvalv_i.
      7. Qt segue para o tronco: P_SB  = P_PA + J(T2, Qt) ± ΔH_t2
                                  P_RTI = P_SB + J(T1, Qt) ± ΔH_t1
      8. Demanda final: Q = Qt, P = P_RTI.
    """
    Qs   = float(Qs_lmin)
    Pmin = float(Pmin)

    esguicho = eh_metodo_esguicho(metodo)
    if esguicho and not (mang_dn_mm and mang_comp_m):
        raise ValueError(
            u"O método '{}' exige o DN e o comprimento da mangueira.".format(
                METODO_ESGUICHO))

    # ΔH = Hi − Hf por trecho, na direção da marcha de cálculo:
    #   T3/T4: hidrante → Ponto A    T2: Ponto A → saída da bomba (recalque)
    #   T1: sucção da bomba → RTI
    dH = {
        "t3": cotas["z_hd01"]   - cotas["z_ponto_a"],
        "t4": cotas["z_hd02"]   - cotas["z_ponto_a"],
        "t2": cotas["z_ponto_a"] - cotas["z_recalque"],
        "t1": cotas["z_succao"] - cotas["z_rti"],
    }

    # Ponto de referência do par normativo, na válvula do hidrante governante
    if esguicho:
        # Pmin está na ponta do esguicho: sobe esguicho → mangueira → válvula
        esg_ref = calc_cadeia_esguicho(Qs, mang_dn_mm, mang_comp_m,
                                       p_esg_mca=Pmin)
        P_valv_ref = esg_ref["P_valv"]
    else:
        esg_ref = None
        P_valv_ref = Pmin

    K = calc_fator_k(Qs, P_valv_ref)

    # Cálculo INICIAL dos dois ramais, ambos com a mesma vazão normativa Qs
    # — antes de qualquer tentativa de equilíbrio (Passo a Passo, item 3).
    # j3_inicial/j4_inicial ficam guardados à parte (nunca reatribuídos):
    # j3/j4 abaixo são sobrescritos pelo resultado FINAL (pós-equilíbrio)
    # do ramal iterado, e o memorial precisa dos dois — o "antes" (Qs) nas
    # seções 7.1/7.2 e o "depois" na narrativa do equilíbrio.
    j3 = calc_j_trecho(trechos_data["t3"], Qs, C, u"Trecho HD01 ao Ponto A")
    j4 = calc_j_trecho(trechos_data["t4"], Qs, C, u"Trecho HD02 ao Ponto A")
    j3_inicial, j4_inicial = j3, j4

    # Pressão requerida no Ponto A por cada ramal, ainda com Qs nos dois
    P_PA1 = P_valv_ref + j3["J"] + dH["t3"]
    P_PA2 = P_valv_ref + j4["J"] + dH["t4"]
    P_PA  = max(P_PA1, P_PA2)
    hid_governa = u"HD01" if P_PA1 >= P_PA2 else u"HD02"

    # EQUILÍBRIO HIDRÁULICO: o ramal governante (o de maior P_PA) fixa a
    # pressão-alvo do Ponto A e não muda — por construção, já está com
    # Q = Qs e P_valv = P_valv_ref, a mesma origem do Fator K. O ramal mais
    # favorável converge iterativamente até sua P_A bater com essa
    # pressão-alvo, recalculando Hazen-Williams a cada passo (nunca
    # reaproveitando a perda de carga de uma vazão diferente).
    if hid_governa == u"HD01":
        eq = _equilibrar_ramal(trechos_data["t4"], K, P_PA, dH["t4"], C, j4,
                               tolerancia_mca=tolerancia_equilibrio_mca,
                               max_iter=max_iter_equilibrio)
        j4 = eq["j"]
        P_hd01, Q1 = P_valv_ref, Qs
        P_hd02, Q2 = eq["P_ref"], eq["Q"]
        equilibrio = dict(ramal_iterado=u"HD02", ramal_governante=u"HD01", **eq)
    else:
        eq = _equilibrar_ramal(trechos_data["t3"], K, P_PA, dH["t3"], C, j3,
                               tolerancia_mca=tolerancia_equilibrio_mca,
                               max_iter=max_iter_equilibrio)
        j3 = eq["j"]
        P_hd02, Q2 = P_valv_ref, Qs
        P_hd01, Q1 = eq["P_ref"], eq["Q"]
        equilibrio = dict(ramal_iterado=u"HD01", ramal_governante=u"HD02", **eq)

    # Só depois de convergido o equilíbrio é que as vazões são somadas.
    Qt = Q1 + Q2

    # Método do esguicho: com a vazão final de cada hidrante, refaz-se a
    # cadeia válvula → mangueira → esguicho (valores crescem em direção aos
    # pontos mais favoráveis). No governante, P_esg volta a ser Pmin.
    if esguicho:
        esg = {
            "hd01": calc_cadeia_esguicho(Q1, mang_dn_mm, mang_comp_m,
                                         p_valv_mca=P_hd01),
            "hd02": calc_cadeia_esguicho(Q2, mang_dn_mm, mang_comp_m,
                                         p_valv_mca=P_hd02),
            "ref":  esg_ref,
            "mang_dn_mm":  mang_dn_mm,
            "mang_comp_m": mang_comp_m,
        }
    else:
        esg = None

    # Trecho Ponto A à descarga da bomba, com Qt e a maior pressão do Ponto A
    j2 = calc_j_trecho(trechos_data["t2"], Qt, C, u"Trecho Bomba ao Ponto A")
    P_SB = P_PA + j2["J"] + dH["t2"]

    # Trecho de sucção (também com Qt); P_RTI é a demanda final de pressão
    j1 = calc_j_trecho(trechos_data["t1"], Qt, C, u"Trecho de Sucção (RTI à Bomba)")
    P_RTI = P_SB + j1["J"] + dH["t1"]

    return {
        "metodo":     metodo,
        "esguicho":   esguicho,
        "K":          K,
        "P_valv_ref": P_valv_ref,
        "esg":        esg,
        "dH":         dH,
        "j":          {"t1": j1, "t2": j2, "t3": j3, "t4": j4},
        "j_inicial":  {"t3": j3_inicial, "t4": j4_inicial},
        "equilibrio": equilibrio,
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
