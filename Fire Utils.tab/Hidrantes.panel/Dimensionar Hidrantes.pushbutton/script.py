# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes
Output rápido de conferência no pyRevit + salva cache para o botão Memorial.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInParameter,
    LocationCurve, LocationPoint, UnitUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from pyrevit import forms, script
import math, sys, os

try:
    from Autodesk.Revit.DB import UnitTypeId
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, DisplayUnitType.DUT_METERS)

from projeto import exigir_projeto_e_estado
from hidrantes.db import SISTEMAS_HIDRANTE
from hidrantes.calc import (
    calcular_rede, calc_hf_mangueira, calc_potencia, hesg_mca,
    extrair_trecho, salvar_cache,
    C_HW, _f, _g, _Lm,
)

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_TRECHO           = u"FireUtils - Trecho"

# Referência normativa de Pmin na cadeia de energia:
#   "esguicho" (default) — o par Q/Pmin da NT 22 já é definido na entrada do
#                           esguicho regulável; Hesg = 0 (perda já incorporada em Pmin).
#   "valvula"             — Pmin é referenciado na válvula do hidrante; Hesg é
#                           calculado por hesg_mca() e somado à cadeia de energia,
#                           com mangueira/esguicho compostos a jusante da válvula.
PMIN_REF = u"esguicho"
P_IDENTIFICADOR    = u"FireUtils - Identificador"

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

# ===========================================================================
# HELPERS REVIT
# ===========================================================================

def get_trecho(elem):
    try:
        p = elem.LookupParameter(P_TRECHO)
        return p.AsString() if p else None
    except: return None

def get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        return p.AsString() if p else None
    except: return None

def get_comprimento(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        return to_m(p.AsDouble()) if p else 0.0
    except: return 0.0

def get_diametro(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_INNER_DIAM_PARAM)
        if p and p.AsDouble() > 0: return to_m(p.AsDouble())
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        return to_m(p.AsDouble()) if p else 0.065
    except: return 0.065

def get_leq(elem):
    try:
        p = elem.LookupParameter(u"Perda de Carga")
        return p.AsDouble() if p else 0.0
    except: return 0.0

def get_nome(elem):
    try:    return elem.Symbol.Family.Name
    except: return u"(desconhecido)"

def get_z(elem, modo="mid"):
    loc = elem.Location
    if isinstance(loc, LocationCurve):
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        dz = abs(p1.Z - p0.Z)
        dh = ((p1.X - p0.X)**2 + (p1.Y - p0.Y)**2) ** 0.5
        if dz > dh and modo == "auto":
            try:
                conns = sorted(list(elem.ConnectorManager.Connectors), key=lambda c: c.Origin.Z)
                return to_m(conns[0].Origin.Z)
            except:
                return to_m(min(p0.Z, p1.Z))
        return (to_m(p0.Z) + to_m(p1.Z)) / 2.0
    if isinstance(loc, LocationPoint):
        return to_m(loc.Point.Z)
    bbox = elem.get_BoundingBox(None)
    if bbox:
        return (to_m(bbox.Min.Z) + to_m(bbox.Max.Z)) / 2.0
    return None

# ===========================================================================
# MEMORIAL DE CÁLCULO — apresentação única e completa
# ===========================================================================

def print_memorial_calculo(res, dados_sistema, valor_sistema, calculo_escolha,
                            Z_RTI, Z_HID01, Z_HID02, Hz_H1, Hz_H2,
                            Dm_mangueira_m, Hesg,
                            Pmin, C_HW, eta, pot_cv, pot_kw, timestamp):
    import math as _math

    hf_fin = res["hf"]
    hist   = res.get(u"historico", [])

    # Ponto de referência onde P_i = Ht + ΔZ_i − Hf_i − Hm_i − Hesg é de fato calculada:
    # "válvula" quando não há mangueira/esguicho no cálculo (Hm=0) ou quando Pmin
    # é referenciado na válvula (PMIN_REF="valvula"); caso contrário, a subtração
    # de Hm desloca o ponto calculado para a entrada do esguicho.
    _ponto_pmin = (u"válvula" if (Dm_mangueira_m is None or PMIN_REF == u"valvula")
                   else u"entrada do esguicho")

    def _vel(v):
        return u"✓ {:.3f} m/s".format(v) if v <= 3.0 else u"✗ {:.3f} m/s (> 3,0)".format(v)

    def _atende(v, vmin, vmax=100.0):
        if v < vmin:  return u"✗ ABAIXO DO MÍNIMO ({} mca)".format(vmin)
        if v > vmax:  return u"✗ ACIMA DO MÁXIMO ({} mca)".format(vmax)
        return u"✓ ATENDE"

    # ── Cabeçalho ─────────────────────────────────────────────────────────
    output.print_md(u"# Memorial de Cálculo — Dimensionamento Hidráulico de Hidrantes")
    output.print_md(u"**Sistema:** {} | **Método:** {} | *{}*".format(
        valor_sistema, calculo_escolha, timestamp))
    output.print_md(u"---")

    # ── 1. Dados normativos ────────────────────────────────────────────────
    output.print_md(u"## 1. Dados Normativos do Sistema")
    output.print_md(u"| Parâmetro | Valor | Referência |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Classificação | **{}** | NT 22 CBMMA |".format(valor_sistema))
    output.print_md(u"| Método de cálculo | {} | — |".format(calculo_escolha))
    output.print_md(u"| Hidrantes simultâneos | **2** | NT 22 |")
    output.print_md(u"| Vazão mínima por hidrante (Qmin) | **{} L/min = {:.6f} m³/s** | NT 22 |".format(
        dados_sistema["vazao_min"], dados_sistema["vazao_min"] / 60000.0))
    output.print_md(u"| Pressão mínima na {} (Pmin) | **{} mca** | NT 22 |".format(_ponto_pmin, Pmin))
    output.print_md(u"| Pressão máxima | **100 mca** | NT 22 |")
    output.print_md(u"| Coef. Hazen-Williams (C) | **{}** | Aço/ferro galvanizado |".format(C_HW))
    output.print_md(u"| Velocidade máxima | **3,0 m/s** | NBR 13714 |")
    if Dm_mangueira_m is not None:
        output.print_md(u"| Diâmetro da mangueira (Dm) | **{} mm ({:.4f} m)** | NT 22 |".format(
            dados_sistema["mangueira_dn"], Dm_mangueira_m))
        output.print_md(u"| Comprimento da mangueira (Lm) | **30,0 m** | NT 22 |")
    output.print_md(u"")

    # ── 2. Cotas altimétricas ──────────────────────────────────────────────
    output.print_md(u"## 2. Cotas Altimétricas e Desníveis")
    output.print_md(u"| Ponto | Cota Z (m) |")
    output.print_md(u"|---|---|")
    output.print_md(u"| RTI (Reservatório / referência) | **{:.4f}** |".format(Z_RTI))
    output.print_md(u"| HID-01 (1° mais desfavorável) | **{:.4f}** |".format(Z_HID01))
    output.print_md(u"| HID-02 (2° mais desfavorável) | **{:.4f}** |".format(Z_HID02))
    output.print_md(u"")
    output.print_md(u"**ΔZ = Z_RTI − Z_válvula** (positivo = RTI acima = favorável ao bombeamento)")
    output.print_md(u"| Percurso | ΔZ (m) | Condição |")
    output.print_md(u"|---|---|---|")
    for hz, lbl in [(Hz_H1, u"RTI → HID-01"), (Hz_H2, u"RTI → HID-02")]:
        cond = u"RTI acima — favorável" if hz > 0.05 else (u"RTI abaixo — desfavorável" if hz < -0.05 else u"Mesmo nível")
        output.print_md(u"| {} | **{:.4f}** | {} |".format(lbl, hz, cond))
    output.print_md(u"")

    # ── 3. Caracterização dos trechos ──────────────────────────────────────
    output.print_md(u"## 3. Caracterização dos Trechos")
    output.print_md(u"Fórmula de Hazen-Williams:")
    output.print_md(u"**J = 10,643 × Q^1,852 × C^−1,852 × D^−4,871** (gradiente hidráulico, mca/m)")
    output.print_md(u"**hf = J × Lt** (perda de carga total do trecho, mca)")
    output.print_md(u"**Lt = L + Σle** (comprimento total = real + equivalente de acessórios)")
    output.print_md(u"")
    _rotulos = {
        "t1": u"T1 — Sucção: RTI → Bomba",
        "t2": u"T2 — Recalque tronco: Bomba → Ponto A",
        "t3": u"T3 — Ramal: Ponto A → HID-01",
        "t4": u"T4 — Ramal: Ponto A → HID-02",
    }
    for key in ["t1", "t2", "t3", "t4"]:
        t = hf_fin[key]
        output.print_md(u"### {}".format(_rotulos[key]))
        output.print_md(u"| Parâmetro | Valor |")
        output.print_md(u"|---|---|")
        output.print_md(u"| Comprimento real (L) | {:.4f} m |".format(t["L"]))
        output.print_md(u"| Diâmetro interno médio (D) | {:.1f} mm = **{:.4f} m** |".format(
            t["D"] * 1000, t["D"]))
        output.print_md(u"| Nº de tubos no trecho | {} |".format(t["n_tubos"]))
        if t["acessorios"]:
            for ace in t["acessorios"]:
                output.print_md(u"| Acessório: {}× {} | le_unit = {:.4f} m  →  Σ = {:.4f} m |".format(
                    ace["qtd"], ace["nome"], ace["leq_unit"], ace["leq_tot"]))
        else:
            output.print_md(u"| Acessórios | Nenhum cadastrado |")
        output.print_md(u"| Comprimento equivalente total (Σle) | **{:.4f} m** |".format(t["Leq"]))
        output.print_md(u"| **Comprimento total** Lt = L + Σle | **{:.4f} + {:.4f} = {:.4f} m** |".format(
            t["L"], t["Leq"], t["Lt"]))
        output.print_md(u"")

    # ── 4. Mangueira (opcional) ────────────────────────────────────────────
    if Dm_mangueira_m is not None:
        output.print_md(u"## 4. Perda de Carga na Mangueira (Darcy-Weisbach)")
        output.print_md(u"A perda de carga na mangueira é calculada individualmente para cada "
                        u"hidrante usando a **vazão normativa especificada** Q_i = Qs_min.")
        output.print_md(u"")
        output.print_md(u"**Fórmula:** Hm = (8 × f × Lm) / (g × π² × Dm⁵) × Q²")
        output.print_md(u"")
        output.print_md(u"*Dedução:* hf = f·(L/D)·(V²/2g), com V = 4Q/(π·D²) → "
                        u"hf = 8·f·L·Q² / (g·π²·D⁵)")
        output.print_md(u"")
        _pi2 = _math.pi ** 2
        _Dm5 = Dm_mangueira_m ** 5
        _denom = 9.81 * _pi2 * _Dm5
        output.print_md(u"| Constante | Símbolo | Valor |")
        output.print_md(u"|---|---|---|")
        output.print_md(u"| Fator de atrito Darcy | f | 0,022 |")
        output.print_md(u"| Comprimento da mangueira | Lm | 30,0 m |")
        output.print_md(u"| Aceleração gravitacional | g | 9,81 m/s² |")
        output.print_md(u"| Diâmetro interno | Dm | {:.4f} m ({} mm) |".format(
            Dm_mangueira_m, dados_sistema["mangueira_dn"]))
        output.print_md(u"| π² | — | {:.6f} |".format(_pi2))
        output.print_md(u"| Dm⁵ | — | {:.4e} m⁵ |".format(_Dm5))
        output.print_md(u"| **Denominador constante** g × π² × Dm⁵ | — | **{:.6e}** |".format(_denom))
        output.print_md(u"| Numerador constante 8 × f × Lm | — | **{:.4f}** |".format(8.0 * 0.022 * 30.0))
        output.print_md(u"")
        if PMIN_REF == u"esguicho":
            output.print_md(
                u"**Modelo de demanda fixa:** adota-se o par normativo do esguicho "
                u"regulável (Q = {} L/min a P = {} mca na entrada do esguicho), de modo "
                u"que a pressão requerida do esguicho já está incorporada em Pmin e "
                u"Hesg = 0 na cadeia de energia. As vazões reais de operação serão "
                u"iguais ou superiores às normativas.".format(
                    dados_sistema["vazao_min"], Pmin))
            output.print_md(u"")
        output.print_md(u"*Os valores de Hm resultantes por hidrante são apresentados em cada ciclo abaixo.*")
        output.print_md(u"")

    # ── 5. Equilíbrio hidráulico ───────────────────────────────────────────
    sec_iter = u"5" if Dm_mangueira_m is not None else u"4"
    Qs_lmin  = dados_sistema["vazao_min"]
    tol_lmin = 0.01
    output.print_md(u"## {}. Cálculo Hidráulico da Rede".format(sec_iter))
    output.print_md(u"")
    output.print_md(u"**Modelo de demanda fixa:** cada hidrante opera com a vazão normativa mínima "
                    u"Q_i = Qs_min (demanda especificada pela norma). "
                    u"O sistema fica determinado sem coeficientes empíricos.")
    output.print_md(u"Qt = Q₁ + Q₂ = 2 × {} = **{:.2f} L/min**".format(
        Qs_lmin, Qs_lmin * 2.0))
    output.print_md(u"")
    output.print_md(u"**Topologia:** RTI → T1 → Bomba → T2 → Nó A → T3 → HID-01")
    output.print_md(u"**&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                    u"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                    u"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                    u"Nó A → T4 → HID-02**")
    output.print_md(u"")
    output.print_md(u"**Equações utilizadas:**")
    output.print_md(u"- Hazen-Williams: hf = 10,643 × Q^1,852 / (C^1,852 × D^4,871) × Lt")
    if Dm_mangueira_m is not None:
        output.print_md(u"- Darcy-Weisbach (mangueira): Hm = (8fLm)/(gπ²Dm⁵) × Q²")
    output.print_md(u"- Energia do ramal: E_i = hf_ramal_i + Hm_i + Hesg − ΔZ_i")
    output.print_md(u"- HMT: Ht = Pmin + Hf_tronco + E_gov (ramal governante = max E_i)")
    output.print_md(u"- Pressão: P_i = Ht + ΔZ_i − Hf_i − Hm_i − Hesg")
    output.print_md(u"")

    c = hist[0] if hist else {}
    Qt_m3s = c.get("Qt",    0.0) / 60000.0
    Q1_m3s = c.get("Q_h01", 0.0) / 60000.0
    Q2_m3s = c.get("Q_h02", 0.0) / 60000.0

    output.print_md(u"### Vazões (demanda normativa mínima especificada)")
    output.print_md(u"| | L/min | m³/s |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Q₁ = Q_HID01 | **{:.2f}** | **{:.6f}** |".format(c.get("Q_h01", 0.0), Q1_m3s))
    output.print_md(u"| Q₂ = Q_HID02 | **{:.2f}** | **{:.6f}** |".format(c.get("Q_h02", 0.0), Q2_m3s))
    output.print_md(u"| Qt = Q₁ + Q₂ | **{:.2f}** | **{:.6f}** |".format(c.get("Qt", 0.0), Qt_m3s))
    output.print_md(u"")

    output.print_md(u"### Hazen-Williams por trecho")
    output.print_md(u"J = 10,643 × Q^1,852 / (C^1,852 × D^4,871)  |  hf = J × Lt")
    output.print_md(u"| Trecho | Q (m³/s) | D (m) | Lt (m) | J (mca/m) | hf (mca) | V (m/s) |")
    output.print_md(u"|---|---|---|---|---|---|---|")
    _q_c = {"t1": Qt_m3s, "t2": Qt_m3s, "t3": Q1_m3s, "t4": Q2_m3s}
    _hfc = {"t1": c.get("Hf_t1", 0.0), "t2": c.get("Hf_t2", 0.0),
            "t3": c.get("Hf_t3", 0.0), "t4": c.get("Hf_t4", 0.0)}
    _vc  = {"t1": c.get("V_t1", 0.0),  "t2": c.get("V_t2", 0.0),
            "t3": c.get("V_t3", 0.0),  "t4": c.get("V_t4", 0.0)}
    for key in ["t1", "t2", "t3", "t4"]:
        t  = hf_fin[key]
        Q  = _q_c[key]; D = t["D"]; Lt = t["Lt"]
        J  = (10.643 * (Q ** 1.852) * (float(C_HW) ** -1.852) * (D ** -4.871)) if Lt > 0 and Q > 0 else 0.0
        output.print_md(u"| {} | {:.6f} | {:.4f} | {:.4f} | {:.6f} | **{:.4f}** | {} |".format(
            key.upper(), Q, D, Lt, J, _hfc[key], _vel(_vc[key])))
    output.print_md(u"| **Σhf HID-01** (T1+T2+T3) | — | — | — | — | **{:.4f}** | — |".format(
        c.get("Hf1", 0.0)))
    output.print_md(u"| **Σhf HID-02** (T1+T2+T4) | — | — | — | — | **{:.4f}** | — |".format(
        c.get("Hf2", 0.0)))
    output.print_md(u"")

    if Dm_mangueira_m is not None:
        output.print_md(u"### Darcy-Weisbach — mangueira")
        output.print_md(u"Hm = (8 × f × Lm) / (g × π² × Dm⁵) × Q²")
        output.print_md(u"| Hidrante | Q (m³/s) | Q² (m⁶/s²) | Hm (mca) |")
        output.print_md(u"|---|---|---|---|")
        output.print_md(u"| HID-01 | {:.6f} | {:.4e} | **{:.4f}** |".format(
            Q1_m3s, Q1_m3s ** 2, c.get("Hm1", 0.0)))
        output.print_md(u"| HID-02 | {:.6f} | {:.4e} | **{:.4f}** |".format(
            Q2_m3s, Q2_m3s ** 2, c.get("Hm2", 0.0)))
        output.print_md(u"")

    _E_gov = max(c.get("E1", 0.0), c.get("E2", 0.0))
    _gov   = u"HID-01" if c.get("E1", 0.0) >= c.get("E2", 0.0) else u"HID-02"
    output.print_md(u"### Energia dos ramais e ramal governante")
    output.print_md(u"E_i = hf_ramal_i + Hm_i + Hesg − ΔZ_i")
    output.print_md(u"| Ramal | hf_ramal (mca) | Hm (mca) | Hesg (mca) | −ΔZ (mca) | **E (mca)** |")
    output.print_md(u"|---|---|---|---|---|---|")
    output.print_md(u"| T3 → HID-01 | {:.4f} | {:.4f} | {:.4f} | {:.4f} | **{:.4f}** |".format(
        c.get("Hf_t3", 0.0), c.get("Hm1", 0.0), Hesg, -Hz_H1, c.get("E1", 0.0)))
    output.print_md(u"| T4 → HID-02 | {:.4f} | {:.4f} | {:.4f} | {:.4f} | **{:.4f}** |".format(
        c.get("Hf_t4", 0.0), c.get("Hm2", 0.0), Hesg, -Hz_H2, c.get("E2", 0.0)))
    output.print_md(u"**Ramal governante: {} → E_gov = {:.4f} mca**".format(_gov, _E_gov))
    output.print_md(u"")

    output.print_md(u"### HMT e pressões reais")
    output.print_md(u"Ht = Pmin + Hf_tronco + E_gov")
    output.print_md(u"Ht = {:.2f} + {:.4f} + {:.4f} = **{:.4f} mca**".format(
        float(Pmin), c.get("Hf_t1", 0.0) + c.get("Hf_t2", 0.0), _E_gov, c.get("Ht", 0.0)))
    output.print_md(u"")
    output.print_md(u"P_i = Ht + ΔZ_i − Σhf_i − Hm_i − Hesg  (ponto de cálculo: {})".format(_ponto_pmin))
    output.print_md(u"| Hidrante | Cálculo | **P real (mca)** | Q (L/min) | Verificação P | Verificação Q |")
    output.print_md(u"|---|---|---|---|---|---|")
    for lbl, hz, hf_tot, hm, p, q in [
        (u"HID-01", Hz_H1, c.get("Hf1", 0.0), c.get("Hm1", 0.0), c.get("p1", 0.0), c.get("Q_h01", 0.0)),
        (u"HID-02", Hz_H2, c.get("Hf2", 0.0), c.get("Hm2", 0.0), c.get("p2", 0.0), c.get("Q_h02", 0.0)),
    ]:
        _calc = u"{:.4f} + ({:.4f}) − {:.4f} − {:.4f} − {:.4f}".format(
            c.get("Ht", 0.0), hz, hf_tot, hm, Hesg)
        _pv = u"✓ ≥ {}".format(Pmin) if p >= float(Pmin) - 0.01 else u"✗ < {}".format(Pmin)
        _pv = _pv + (u" / ✗ > 100" if p > 100.0 else u"")
        _qv = u"✓ ≥ {}".format(Qs_lmin) if q >= Qs_lmin - tol_lmin else u"✗ < {}".format(Qs_lmin)
        output.print_md(u"| {} | {} | **{:.4f}** | **{:.2f}** | {} | {} |".format(
            lbl, _calc, p, q, _pv, _qv))
    output.print_md(u"")

    # ── 6. Resumo dos resultados ──────────────────────────────────────────
    sec_res = str(int(sec_iter) + 1)
    output.print_md(u"## {}. Resumo dos Resultados".format(sec_res))
    output.print_md(u"")
    output.print_md(u"| Grandeza | HID-01 | HID-02 | Unidade |")
    output.print_md(u"|---|---|---|---|")
    output.print_md(u"| Vazão (demanda normativa) | **{:.2f}** | **{:.2f}** | L/min |".format(
        res["Q_h01"], res["Q_h02"]))
    output.print_md(u"| Σhf percurso | {:.4f} | {:.4f} | mca |".format(
        res["Hf_Hid01"], res["Hf_Hid02"]))
    if Dm_mangueira_m is not None:
        output.print_md(u"| Hm mangueira | {:.4f} | {:.4f} | mca |".format(
            res.get("Hm_hid01", 0.0), res.get("Hm_hid02", 0.0)))
    output.print_md(u"| **Pressão real na {}** | **{:.4f}** | **{:.4f}** | mca |".format(
        _ponto_pmin,
        res["p_hid01"], res["p_hid02"]))
    _pv1 = u"✓ ATENDE" if float(Pmin) <= res["p_hid01"] <= 100.0 else u"✗ NÃO ATENDE"
    _pv2 = u"✓ ATENDE" if float(Pmin) <= res["p_hid02"] <= 100.0 else u"✗ NÃO ATENDE"
    output.print_md(u"| Verificação (P ∈ [{}, 100] mca) | **{}** | **{}** | — |".format(
        Pmin, _pv1, _pv2))
    output.print_md(u"")
    output.print_md(u"**Qt = {:.2f} + {:.2f} = {:.2f} L/min = {:.4f} m³/h**".format(
        res["Q_h01"], res["Q_h02"], res["Qt_final"], res["Qt_final"] / 1000.0 * 60))
    output.print_md(u"**Ht = {:.4f} mca** (ramal governante: {})".format(
        res["Ht"], res["hid_governa"]))
    output.print_md(u"")

    # ── 7. Bomba ──────────────────────────────────────────────────────────
    sec_bomba = str(int(sec_res) + 1)
    output.print_md(u"## {}. Dimensionamento da Bomba de Recalque".format(sec_bomba))
    output.print_md(u"")
    Qt_m3s_f = res["Qt_final"] / 60000.0
    eta_dec  = eta / 100.0
    output.print_md(u"**Fórmula:** P_cv = (1000 × Qt × Ht) / (75 × η)")
    output.print_md(u"")
    output.print_md(u"| Parâmetro | Símbolo | Valor |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Vazão total de projeto | Qt | **{:.2f} L/min = {:.6f} m³/s = {:.4f} m³/h** |".format(
        res["Qt_final"], Qt_m3s_f, res["Qt_final"] / 1000.0 * 60))
    output.print_md(u"| Altura manométrica total | Ht | **{:.4f} mca** |".format(res["Ht"]))
    output.print_md(u"| Eficiência global | η | **{:.0f}% = {:.2f}** |".format(eta, eta_dec))
    output.print_md(u"")
    output.print_md(u"**Desenvolvimento:**")
    output.print_md(u"P_cv = (1000 × {:.6f} × {:.4f}) / (75 × {:.2f})".format(
        Qt_m3s_f, res["Ht"], eta_dec))
    output.print_md(u"P_cv = {:.4f} / {:.4f}".format(
        1000.0 * Qt_m3s_f * res["Ht"], 75.0 * eta_dec))
    output.print_md(u"**P_cv = {:.2f} cv  →  {:.2f} kW**".format(pot_cv, pot_kw))
    output.print_md(u"")
    output.print_md(u"| Resultado | Valor |")
    output.print_md(u"|---|---|")
    output.print_md(u"| Ponto de operação Qt | **{:.2f} L/min / {:.4f} m³/h** |".format(
        res["Qt_final"], res["Qt_final"] / 1000.0 * 60))
    output.print_md(u"| Ponto de operação Ht | **{:.4f} mca** |".format(res["Ht"]))
    output.print_md(u"| **Potência mínima** | **{:.2f} cv / {:.2f} kW** |".format(pot_cv, pot_kw))
    output.print_md(u"")
    output.print_md(u"---")
    output.print_md(u"*Cache salvo. Use o botão **Gerar Memorial** para o relatório em HTML.*")

# ===========================================================================
# MAIN
# ===========================================================================

# --- Verificar projeto salvo e estado configurado ---
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)

# --- Etapa 1: tipo de sistema ---
param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
if not param_sistema or not param_sistema.AsString():
    forms.alert(u"Execute 'Classificar Sistema de Hidrante' primeiro.",
                title="Fire Utils", warn_icon=True)
    script.exit()

calculo_escolha = forms.SelectFromList.show(
    [u"Válvula do Hidrante", u"Ponta do Esguicho Regulável"],
    title=u"Fire Utils — Método de Cálculo",
    prompt=u"Selecione o método de cálculo:",
    multiselect=False
)
if not calculo_escolha: script.exit()

valor_sistema = param_sistema.AsString()
try:    tipo_num = int(valor_sistema.split()[1])
except:
    forms.alert(u"Não foi possível interpretar o tipo.", title="Fire Utils", warn_icon=True)
    script.exit()

variante_idx = 0
if u"Var." in valor_sistema:
    try:    variante_idx = ord(valor_sistema.split(u"Var.")[1].strip()[0]) - 65
    except: variante_idx = 0

dados_sistema = SISTEMAS_HIDRANTE[tipo_num]["variantes"][variante_idx]
Qs_lmin = dados_sistema["vazao_min"]
Qs_m3s  = Qs_lmin / 60000.0
Pmin    = dados_sistema["pressao_min"]
Dm_m    = dados_sistema["mangueira_dn"] / 1000.0

# --- Etapa 2: captura de elementos ---
TRECHOS = [u"RTI - Bomba", u"Bomba - Ponto A", u"Ponto A - Hid 01", u"Ponto A - Hid 02"]
trechos_elems = {t: [] for t in TRECHOS}
ident_map = {}; hid_map = {}

for elem in FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType().ToElements():
    t = get_trecho(elem)
    if t in trechos_elems: trechos_elems[t].append(elem)
    i = get_identificador(elem)
    if i: ident_map[i] = elem
    if isinstance(elem, FamilyInstance):
        try:
            p = elem.LookupParameter(u"FireUtils - Identificador")
            if p and p.AsString() in (u"HID-01", u"HID-02"):
                hid_map[p.AsString()] = elem
        except: pass

erros = []
for t in TRECHOS:
    if not trechos_elems[t]: erros.append(u"Trecho '{}' vazio".format(t))
for i in [u"RTI", u"Succao", u"Ponto A"]:
    if i not in ident_map: erros.append(u"Identificador '{}' não encontrado".format(i))
for h in [u"HID-01", u"HID-02"]:
    if h not in hid_map: erros.append(u"'{}' não encontrado".format(h))
if erros:
    forms.alert(u"Elementos não encontrados:\n{}\n\nExecute 'Mapear Trechos' primeiro.".format(
        u"\n".join(erros)), title="Fire Utils", warn_icon=True)
    script.exit()

# --- Etapa 3: cotas ---
Z_RTI   = get_z(ident_map[u"RTI"], modo="auto")
Z_HID01 = get_z(hid_map[u"HID-01"])
Z_HID02 = get_z(hid_map[u"HID-02"])

erros_z = [n for n, z in [(u"RTI", Z_RTI), (u"HID-01", Z_HID01), (u"HID-02", Z_HID02)] if z is None]
if erros_z:
    forms.alert(u"Não foi possível ler a elevação de:\n{}".format(u"\n".join(erros_z)),
                title="Fire Utils", warn_icon=True)
    script.exit()

Hz_H1 = Z_RTI - Z_HID01
Hz_H2 = Z_RTI - Z_HID02

# --- Etapa 4: mangueira ---
# Hm é calculado por hidrante dentro da iteração usando Q real.
# Dm_mangueira_m=None desativa (método = válvula do hidrante).
Hm_mangueira = 0.0; Hesg = 0.0; Dm_mangueira_m = None
if calculo_escolha == u"Ponta do Esguicho Regulável":
    Dm_mangueira_m = Dm_m
    if PMIN_REF == u"valvula":
        # Pmin referenciado na válvula: a perda no esguicho regulável passa a
        # ser explícita na cadeia de energia (E_i, Ht, P_i), em vez de já
        # estar incorporada em Pmin (comportamento default "esguicho").
        esguicho_dn = SISTEMAS_HIDRANTE[tipo_num].get("esguicho_dn")
        if esguicho_dn:
            Hesg = hesg_mca(Qs_lmin, d_mm=esguicho_dn)

# --- Etapa 5: extrair dados dos trechos e iterar ---
trechos_data = {
    "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome),
}

res = calcular_rede(trechos_data, Qs_lmin, Hz_H1, Hz_H2,
                    Hesg, Pmin, C_HW,
                    Dm_mangueira_m=Dm_mangueira_m)

# --- Etapa 6: eficiência e potência ---
eta_str = forms.ask_for_string(
    default="60",
    prompt=u"Eficiência global da bomba (%)\nEx: 60",
    title=u"Fire Utils — Eficiência"
)
if not eta_str:
    output.print_md(u"Cancelado."); script.exit()
try:
    eta = float(eta_str.replace(",", "."))
    if not (0 < eta <= 100): raise ValueError
except ValueError:
    forms.alert(u"Valor inválido.", title="Fire Utils", warn_icon=True)
    script.exit()

eta_dec = eta / 100.0
pot_cv  = calc_potencia(res["Qt_final"] / 60000.0, res["Ht"], eta_dec)
pot_kw  = pot_cv / 1.36

# --- Etapa 7: memorial de cálculo ---
import datetime
timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
print_memorial_calculo(
    res, dados_sistema, valor_sistema, calculo_escolha,
    Z_RTI, Z_HID01, Z_HID02, Hz_H1, Hz_H2,
    Dm_mangueira_m, Hesg,
    Pmin, C_HW, eta, pot_cv, pot_kw, timestamp,
)

# --- Etapa 8: salvar cache para o botão Memorial ---
payload_hid = {
    "res":            res,
    "dados_sistema":  dados_sistema,
    "valor_sistema":  valor_sistema,
    "calculo_escolha": calculo_escolha,
    "Z_RTI":   Z_RTI,   "Z_HID01":   Z_HID01,  "Z_HID02":   Z_HID02,
    "Hz_H1":   Hz_H1,   "Hz_H2":     Hz_H2,
    "Hm_mangueira": res.get("Hm_governa", 0.0),   # Hm do percurso governante (Q real)
    "Dm_mangueira_m": Dm_mangueira_m,
    "Hesg":    Hesg,
    "C_HW":    C_HW,
    "eta":     eta,
    "pot_cv":  pot_cv,
    "pot_kw":  pot_kw,
    "_nome_projeto": doc.Title,
}
salvar_cache(payload_hid, projeto_dir)

