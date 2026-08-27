# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes
Dimensionamento hidráulico pelo MÉTODO DA MARCHA (passo a passo):
HID-01 → Ponto A → Saída da Bomba → RTI, com ajuste da vazão do hidrante
mais favorável pelo Fator K. Imprime o memorial de cálculo no output do
pyRevit e salva cache para os demais botões.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInParameter,
    LocationCurve, LocationPoint, UnitUtils,
)
from pyrevit import forms, script

try:
    from Autodesk.Revit.DB import UnitTypeId
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, DisplayUnitType.DUT_METERS)

from projeto import exigir_projeto_e_estado
from hidrantes.calc import (
    calcular_rede, calc_potencia, extrair_trecho, salvar_cache,
    MCA_POR_BAR,
)
from hidrantes.norm_profiles import get_profile, req
from hidrantes import custom as custom_store

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_TRECHO           = u"FireUtils - Trecho"
P_IDENTIFICADOR    = u"FireUtils - Identificador"

# Simbolos de saida no output window do pyRevit (janela de output do pyRevit
# roda em unicode e normalmente exibe ✓/✗/≤ sem problema). Se algum ambiente
# nao renderizar esses caracteres, mude _ASCII_FALLBACK para True aqui -
# unico lugar do arquivo que define esses simbolos.
_ASCII_FALLBACK = False
if _ASCII_FALLBACK:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"OK", u"X", u"<=", u">="
else:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"✓", u"✗", u"≤", u"≥"

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
# MEMORIAL DE CÁLCULO — passo a passo (método da marcha)
# ===========================================================================

def _fmt_dh(dh):
    """ΔH com sinal explícito para as equações da marcha (J ± ΔH)."""
    return (u"+ {:.4f}" if dh >= 0 else u"− {:.4f}").format(abs(dh))

def _md_cell(texto):
    """Escapa '|' para usar texto livre dentro de célula de tabela markdown."""
    return (texto or u"").replace(u"|", u"\\|")

def _tabelas_trecho(jt):
    """Tabelas de tubulação e conexões por diâmetro de um trecho (passo 5)."""
    output.print_md(u"**Tubulação por diâmetro**")
    output.print_md(u"| D interno (mm) | Nº tubos | L real (m) | Σle conexões (m) | **Ltotal = L + Σle (m)** |")
    output.print_md(u"|---|---|---|---|---|")
    for s in jt["segmentos"]:
        output.print_md(u"| {:.1f} | {} | {:.4f} | {:.4f} | **{:.4f}** |".format(
            s["d_mm"], s["n_tubos"], s["L"], s["Leq"], s["Ltotal"]))
    output.print_md(u"")

    tem_aces = any(s["acessorios"] for s in jt["segmentos"])
    output.print_md(u"**Conexões e acessórios (comprimentos equivalentes)**")
    if tem_aces:
        output.print_md(u"| Conexão / acessório | DN (mm) | Qtd | le unit (m) | Σle (m) |")
        output.print_md(u"|---|---|---|---|---|")
        for s in jt["segmentos"]:
            for a in s["acessorios"]:
                output.print_md(u"| {} | {:.1f} | {} | {:.4f} | {:.4f} |".format(
                    a["nome"], s["d_mm"], a["qtd"], a["leq_unit"], a["leq_tot"]))
    else:
        output.print_md(u"*Nenhuma conexão com comprimento equivalente cadastrado neste trecho.*")
    output.print_md(u"")

def _tabela_hazen(jt, v_limite):
    """Tabela de Jun/J/V por diâmetro de um trecho (passos 6 e 9)."""
    output.print_md(u"**Perda de carga (Hazen-Williams) — Q = {:.2f} L/min**".format(jt["Q_lmin"]))
    output.print_md(u"| D (mm) | Ltotal (m) | Jun (m/m) | J = Ltotal·Jun (mca) | V = 21,22·Q/D² (m/s) | Verificação (V {} {:.1f}) |".format(
        SIM_LE, v_limite))
    output.print_md(u"|---|---|---|---|---|---|")
    for s in jt["segmentos"]:
        vv = (u"{} {:.3f}".format(SIM_OK, s["V"]) if s["V"] <= v_limite
              else u"{} {:.3f} > {:.1f}".format(SIM_X, s["V"], v_limite))
        output.print_md(u"| {:.1f} | {:.4f} | {:.6f} | {:.4f} | {:.3f} | {} |".format(
            s["d_mm"], s["Ltotal"], s["Jun"], s["J"], s["V"], vv))
    output.print_md(u"**ΣJ do trecho = {:.4f} mca**".format(jt["J"]))
    output.print_md(u"")

def print_memorial_calculo(res, dados_sistema, valor_sistema,
                           cotas, succao, Hz_succao,
                           Qs_lmin, Pmin, C_HW,
                           eta, pot_cv, pot_kw, timestamp, perfil):
    norma           = req(perfil, u"norma")
    hidr_simult     = req(perfil, u"hidrantes_simultaneos")
    hidr_simult_ref = req(perfil, u"hidrantes_simultaneos_ref")
    tipos_ref       = req(perfil, u"tipos_ref")
    v_max_tubo      = req(perfil, u"v_max_tubulacao")
    v_max_tubo_ref  = req(perfil, u"v_max_tubulacao_ref")
    v_max_suc_pos   = req(perfil, u"v_max_succao_positiva")
    v_max_suc_neg   = req(perfil, u"v_max_succao_negativa")
    v_max_suc_ref   = req(perfil, u"v_max_succao_ref")
    hazen_c_ref     = req(perfil, u"hazen_c_ref")

    # Sistema personalizado: os valores Q/P/DN não vêm da Tabela 2, então o
    # memorial não pode citá-la como referência deles.
    if custom_store.is_custom(valor_sistema):
        tipos_ref = u"valores definidos pelo usuário (fora da {})".format(
            req(perfil, u"tipos_ref"))

    v_max_succao = v_max_suc_pos if succao == u"positiva" else v_max_suc_neg

    K  = res["K"]
    dH = res["dH"]
    j  = res["j"]

    # ── Cabeçalho ─────────────────────────────────────────────────────────
    output.print_md(u"# Memorial de Cálculo — Dimensionamento Hidráulico de Hidrantes")
    output.print_md(u"**Sistema:** {} | **Método:** marcha (passo a passo) com Fator K | "
                    u"**Norma:** {} | *{}*".format(valor_sistema, norma, timestamp))
    output.print_md(u"---")

    if perfil.get(u"_uf_efetiva") != perfil.get(u"_uf_solicitada"):
        output.print_md(
            u"> **Aviso:** o Estado do projeto ('{}') ainda não possui perfil "
            u"normativo próprio nesta extensão. Usando o perfil default "
            u"'{}' ({}).".format(
                perfil.get(u"_uf_solicitada"), perfil.get(u"_uf_efetiva"), norma))
        output.print_md(u"")

    # ── 1. Vazão e pressão de projeto ─────────────────────────────────────
    output.print_md(u"## 1. Definição da Vazão e da Pressão de Projeto")
    output.print_md(u"| Parâmetro | Valor | Referência |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Norma aplicada | **{}** | — |".format(norma))
    output.print_md(u"| Classificação do sistema | **{}** | {} |".format(
        _md_cell(valor_sistema), tipos_ref))
    output.print_md(u"| Vazão por hidrante (Q) | **{} L/min** | {} |".format(Qs_lmin, tipos_ref))
    output.print_md(u"| Hidrantes simultâneos (n) | **{}** | {} |".format(hidr_simult, hidr_simult_ref))
    output.print_md(u"| Pressão residual mínima (Pmin) | **{} mca = {:.4f} bar** | {} |".format(
        Pmin, float(Pmin) / MCA_POR_BAR, tipos_ref))
    output.print_md(u"| Coef. Hazen-Williams (C) | **{}** | {} — aço/ferro galvanizado |".format(
        C_HW, hazen_c_ref))
    output.print_md(u"| Esguicho — DN | {} mm | {} |".format(dados_sistema["esguicho_dn"], tipos_ref))
    output.print_md(u"| Mangueira — DN / comprimento | {} mm / {:.1f} m | {} |".format(
        dados_sistema["mang_dn"], dados_sistema["mang_comp"], tipos_ref))
    output.print_md(u"| Velocidade máx. — recalque/descarga | {:.1f} m/s | {} |".format(
        v_max_tubo, v_max_tubo_ref))
    output.print_md(u"| Velocidade máx. — sucção ({}) | {:.1f} m/s | {} |".format(
        succao, v_max_succao, v_max_suc_ref))
    output.print_md(u"")

    # ── 2. Hidrantes mais desfavoráveis e trechos ─────────────────────────
    output.print_md(u"## 2. Hidrantes Mais Desfavoráveis e Identificação dos Trechos")
    output.print_md(u"O cenário de cálculo representa a condição mais crítica de operação: "
                    u"os **{} hidrantes mais desfavoráveis em funcionamento simultâneo** "
                    u"(maior demanda de vazão associada às maiores perdas de carga e ao "
                    u"maior desnível geométrico).".format(hidr_simult))
    output.print_md(u"")
    output.print_md(u"A tubulação é dividida em trechos. O **Ponto A** é o ponto de "
                    u"distribuição onde as vazões dos hidrantes considerados se separam.")
    output.print_md(u"")
    output.print_md(u"| Trecho | Percurso | Vazão de cálculo |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| T1 — Sucção | RTI → Bomba | Qt |")
    output.print_md(u"| T2 — Recalque | Bomba → Ponto A | Qt |")
    output.print_md(u"| T3 — Ramal | Ponto A → HID-01 | Q₁ |")
    output.print_md(u"| T4 — Ramal | Ponto A → HID-02 | Q₂ |")
    output.print_md(u"")

    # ── 3. Fator K ────────────────────────────────────────────────────────
    output.print_md(u"## 3. Fator K")
    output.print_md(u"Calculado **apenas no hidrante mais desfavorável**, com o par "
                    u"normativo de vazão e pressão:")
    output.print_md(u"")
    output.print_md(u"**K = Q / √P**  (Q em L/min; P em bar; 1 bar = {} mca)".format(MCA_POR_BAR))
    output.print_md(u"")
    output.print_md(u"K = {} / √({} / {}) = {} / √{:.4f} = **{:.4f} L/min/bar^0,5**".format(
        Qs_lmin, Pmin, MCA_POR_BAR, Qs_lmin, float(Pmin) / MCA_POR_BAR, K))
    output.print_md(u"")
    output.print_md(u"O segundo hidrante, por estar em posição mais favorável, terá pressão "
                    u"maior e, consequentemente, vazão maior — esse ajuste é feito pelo "
                    u"Fator K: **Q₂ = K·√P_hd02**.")
    output.print_md(u"")

    # ── 4. Cotas altimétricas ─────────────────────────────────────────────
    output.print_md(u"## 4. Cotas Altimétricas")
    output.print_md(u"| Ponto | Cota Z (m) |")
    output.print_md(u"|---|---|")
    output.print_md(u"| RTI (reservatório) | **{:.4f}** |".format(cotas["z_rti"]))
    output.print_md(u"| Sucção (entrada da bomba) | **{:.4f}** |".format(cotas["z_succao"]))
    output.print_md(u"| Recalque (saída da bomba) | **{:.4f}** |".format(cotas["z_recalque"]))
    output.print_md(u"| Ponto A (derivação) | **{:.4f}** |".format(cotas["z_ponto_a"]))
    output.print_md(u"| HID-01 (mais desfavorável) | **{:.4f}** |".format(cotas["z_hd01"]))
    output.print_md(u"| HID-02 (2º mais desfavorável) | **{:.4f}** |".format(cotas["z_hd02"]))
    output.print_md(u"")
    output.print_md(u"**ΔH = Hi − Hf** (ponto inicial e final de cada trecho, na direção "
                    u"da marcha de cálculo):")
    output.print_md(u"| Trecho (marcha) | Hi (m) | Hf (m) | ΔH (m) |")
    output.print_md(u"|---|---|---|---|")
    output.print_md(u"| HID-01 → Ponto A | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_hd01"], cotas["z_ponto_a"], dH["t3"]))
    output.print_md(u"| HID-02 → Ponto A | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_hd02"], cotas["z_ponto_a"], dH["t4"]))
    output.print_md(u"| Ponto A → Saída da bomba | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_ponto_a"], cotas["z_recalque"], dH["t2"]))
    output.print_md(u"| Sucção → RTI | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_succao"], cotas["z_rti"], dH["t1"]))
    output.print_md(u"")
    output.print_md(
        u"**Condição de sucção ({}):** determinada pela cota entre a RTI e a "
        u"entrada de sucção da bomba (Z_RTI − Z_sucção = {:.4f} m) — "
        u"**sucção {}**.".format(v_max_suc_ref, Hz_succao, succao))
    output.print_md(u"")

    # ── 5. Fórmulas da marcha ─────────────────────────────────────────────
    output.print_md(u"## 5. Fórmulas Utilizadas")
    output.print_md(u"- Comprimento total por trecho/diâmetro: **Ltotal = L + Σle**")
    output.print_md(u"- Hazen-Williams (perda unitária): **Jun = 605·10⁴ · Q^1,85 · "
                    u"C^−1,85 · D^−4,87** [m/m] (Q em L/min, D interno em mm)")
    output.print_md(u"- Perda do trecho: **J = Ltotal · Jun** [mca], somada por diâmetro")
    output.print_md(u"- Velocidade: **V = 21,22 · Q / D²** [m/s]")
    output.print_md(u"- Marcha de pressões: **P_fim = P_início + J ± ΔH**")
    output.print_md(u"- Ajuste do hidrante favorável: **Q = K·√P** (P em bar)")
    output.print_md(u"")

    # ── 6. Cálculo por trecho (marcha) ────────────────────────────────────
    output.print_md(u"## 6. Cálculo Trecho a Trecho")
    output.print_md(u"")

    # 6.1 — T3: HID-01 → Ponto A
    output.print_md(u"### 6.1 Trecho HID-01 → Ponto A (T3)")
    _tabelas_trecho(j["t3"])
    _tabela_hazen(j["t3"], v_max_tubo)
    output.print_md(u"**Pressão requerida no Ponto A pelo ramal do HID-01:**")
    output.print_md(u"P_PA(1) = P_hd01 + J ± ΔH = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        float(Pmin), j["t3"]["J"], _fmt_dh(dH["t3"]), res["P_A1"]))
    output.print_md(u"")

    # 6.2 — T4: HID-02 → Ponto A, com Fator K
    output.print_md(u"### 6.2 Trecho HID-02 → Ponto A (T4) — ajuste pelo Fator K")
    _tabelas_trecho(j["t4"])
    output.print_md(u"Pressão requerida no Ponto A pelo ramal do HID-02 (com a vazão "
                    u"final Q₂ = {:.2f} L/min):".format(res["Q_h02"]))
    output.print_md(u"P_PA(2) = P_hd02,min + J ± ΔH = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        float(Pmin), j["t4"]["J"], _fmt_dh(dH["t4"]), res["P_A2"]))
    output.print_md(u"")
    output.print_md(u"**Pressão adotada no Ponto A = maior entre os ramais:** "
                    u"P_PA = max({:.4f}; {:.4f}) = **{:.4f} mca** "
                    u"(ramal governante: **{}**)".format(
                        res["P_A1"], res["P_A2"], res["P_A"], res["hid_governa"]))
    output.print_md(u"")
    output.print_md(u"Com o Ponto A nessa pressão, o hidrante mais favorável recebe "
                    u"pressão acima da mínima e a vazão é ajustada por Q = K·√P. "
                    u"Como a perda J depende da vazão, o cálculo é repetido até a "
                    u"vazão estabilizar:")
    output.print_md(u"")
    output.print_md(u"| Ciclo | Q₂ (L/min) | J(T4) (mca) | P_hd02 (mca) | Q₂ = K·√P (L/min) |")
    output.print_md(u"|---|---|---|---|---|")
    for h in res["historico"]:
        output.print_md(u"| {} | {:.2f} | {:.4f} | {:.4f} | {:.2f} |".format(
            h["ciclo"], h["Q2"], h["J4"], h["P_hd02"], h["Q2_novo"]))
    if res["convergiu"]:
        output.print_md(u"{} Convergiu em {} ciclo(s).".format(SIM_OK, res["iteracoes"]))
    else:
        output.print_md(u"{} **Não convergiu em {} ciclos — revisar a rede.**".format(
            SIM_X, res["iteracoes"]))
    output.print_md(u"")
    _tabela_hazen(j["t4"], v_max_tubo)
    output.print_md(u"**Pressões e vazões resultantes nos hidrantes:**")
    output.print_md(u"| Hidrante | P (mca) | Q (L/min) | Verificação (Q {} {} L/min) |".format(
        SIM_GE, Qs_lmin))
    output.print_md(u"|---|---|---|---|")
    for lbl, p, q in [(u"HID-01", res["P_hd01"], res["Q_h01"]),
                      (u"HID-02", res["P_hd02"], res["Q_h02"])]:
        qv = (u"{} {:.2f}".format(SIM_OK, q) if q >= float(Qs_lmin) - 0.01
              else u"{} {:.2f} < {}".format(SIM_X, q, Qs_lmin))
        output.print_md(u"| {} | {:.4f} | {:.2f} | {} |".format(lbl, p, q, qv))
    output.print_md(u"")

    # 6.3 — T2: Ponto A → saída da bomba
    output.print_md(u"### 6.3 Trecho Ponto A → Descarga da Bomba (T2)")
    output.print_md(u"Vazão de cálculo = soma das vazões dos dois hidrantes em funcionamento:")
    output.print_md(u"**Qt = Q_hd01 + Q_hd02 = {:.2f} + {:.2f} = {:.2f} L/min**".format(
        res["Q_h01"], res["Q_h02"], res["Qt"]))
    output.print_md(u"")
    _tabelas_trecho(j["t2"])
    _tabela_hazen(j["t2"], v_max_tubo)
    output.print_md(u"**Pressão na saída da bomba:**")
    output.print_md(u"P_SB = P_PA + J ± ΔH = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_A"], j["t2"]["J"], _fmt_dh(dH["t2"]), res["P_SB"]))
    output.print_md(u"")

    # 6.4 — T1: sucção
    output.print_md(u"### 6.4 Trecho de Sucção RTI → Bomba (T1)")
    output.print_md(u"Também com a vazão total Qt = {:.2f} L/min. A pressão de partida é "
                    u"a encontrada no trecho anterior (P_SB).".format(res["Qt"]))
    output.print_md(u"")
    _tabelas_trecho(j["t1"])
    _tabela_hazen(j["t1"], v_max_succao)
    output.print_md(u"**Pressão de demanda referida à RTI:**")
    output.print_md(u"P_RTI = P_SB + J ± ΔH = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_SB"], j["t1"]["J"], _fmt_dh(dH["t1"]), res["P_RTI"]))
    output.print_md(u"")

    # ── 7. Verificação de velocidades (resumo) ────────────────────────────
    output.print_md(u"## 7. Verificação das Velocidades de Escoamento")
    output.print_md(u"Limites: {:.1f} m/s (sucção {}), {:.1f} m/s (recalque/descarga) — {} / {}.".format(
        v_max_succao, succao, v_max_tubo, v_max_suc_ref, v_max_tubo_ref))
    output.print_md(u"| Trecho | D (mm) | Q (L/min) | V (m/s) | Limite (m/s) | Verificação |")
    output.print_md(u"|---|---|---|---|---|---|")
    _rotulos = {"t1": u"T1 — Sucção", "t2": u"T2 — Bomba → Ponto A",
                "t3": u"T3 — Ponto A → HID-01", "t4": u"T4 — Ponto A → HID-02"}
    velocidade_ok = True
    for key in ["t1", "t2", "t3", "t4"]:
        lim = v_max_succao if key == "t1" else v_max_tubo
        for s in j[key]["segmentos"]:
            ok = s["V"] <= lim
            if not ok:
                velocidade_ok = False
            vv = u"{} atende".format(SIM_OK) if ok else u"{} NÃO atende".format(SIM_X)
            output.print_md(u"| {} | {:.1f} | {:.2f} | {:.3f} | {:.1f} | {} |".format(
                _rotulos[key], s["d_mm"], j[key]["Q_lmin"], s["V"], lim, vv))
    if not velocidade_ok:
        output.print_md(u"")
        output.print_md(u"> {} **Velocidade acima do limite:** aumentar o diâmetro da "
                        u"tubulação do(s) trecho(s) reprovado(s) e refazer a "
                        u"verificação até atender.".format(SIM_X))
    output.print_md(u"")

    # ── 8. Demanda do sistema ─────────────────────────────────────────────
    output.print_md(u"## 8. Demanda do Sistema")
    output.print_md(u"Concluídos os cálculos e verificações, o sistema possui a demanda de:")
    output.print_md(u"")
    output.print_md(u"| Grandeza | Valor |")
    output.print_md(u"|---|---|")
    output.print_md(u"| **Q = Qt** | **{:.2f} L/min = {:.4f} m³/h** |".format(
        res["Qt"], res["Qt"] * 60.0 / 1000.0))
    output.print_md(u"| **P = P_RTI** | **{:.4f} mca = {:.4f} bar** |".format(
        res["P_RTI"], res["P_RTI"] / MCA_POR_BAR))
    output.print_md(u"")

    # ── 9. Bomba ──────────────────────────────────────────────────────────
    output.print_md(u"## 9. Dimensionamento da Bomba de Recalque")
    Qt_m3s  = res["Qt"] / 60000.0
    eta_dec = eta / 100.0
    output.print_md(u"**Fórmula:** P_cv = (1000 × Qt × Ht) / (75 × η), com Qt em m³/s "
                    u"e Ht = P_RTI.")
    output.print_md(u"")
    output.print_md(u"| Parâmetro | Símbolo | Valor |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Vazão total de projeto | Qt | **{:.2f} L/min = {:.6f} m³/s = {:.4f} m³/h** |".format(
        res["Qt"], Qt_m3s, res["Qt"] * 60.0 / 1000.0))
    output.print_md(u"| Altura manométrica (demanda) | Ht = P_RTI | **{:.4f} mca** |".format(res["P_RTI"]))
    output.print_md(u"| Eficiência global | η | **{:.0f}% = {:.2f}** |".format(eta, eta_dec))
    output.print_md(u"")
    output.print_md(u"P_cv = (1000 × {:.6f} × {:.4f}) / (75 × {:.2f}) = {:.4f} / {:.4f}".format(
        Qt_m3s, res["P_RTI"], eta_dec,
        1000.0 * Qt_m3s * res["P_RTI"], 75.0 * eta_dec))
    output.print_md(u"**P_cv = {:.2f} cv  →  {:.2f} kW**".format(pot_cv, pot_kw))
    output.print_md(u"")
    output.print_md(u"---")
    output.print_md(u"*Cache salvo em firedata.json (chave 'hidrantes').*")

# ===========================================================================
# MAIN
# ===========================================================================

# --- Verificar projeto salvo e estado configurado ---
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)

# --- Perfil normativo ativo (UF do projeto, default "MA") ---
perfil = get_profile(sigla_estado)

# --- Etapa 1: tipo de sistema ---
param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
if not param_sistema or not param_sistema.AsString():
    forms.alert(u"Execute 'Classificar Sistema de Hidrante' primeiro.",
                title="Fire Utils", warn_icon=True)
    script.exit()

valor_sistema = param_sistema.AsString()

if custom_store.is_custom(valor_sistema):
    # Sistema classificado com valores personalizados (fora da Tabela 2).
    # Os valores vêm do JSON salvo no próprio projeto, não do perfil normativo.
    _custom = custom_store.load_custom(doc)
    if not _custom:
        forms.alert(
            u"O projeto está classificado como sistema personalizado, mas os "
            u"valores não foram encontrados.\n\nExecute "
            u"'Classificar Sistema de Hidrante' novamente.",
            title="Fire Utils", warn_icon=True)
        script.exit()
    dados_sistema = custom_store.para_dados_sistema(_custom)
else:
    try:    tipo_num = int(valor_sistema.split()[1])
    except:
        forms.alert(u"Não foi possível interpretar o tipo.", title="Fire Utils", warn_icon=True)
        script.exit()

    variante_idx = 0
    if u"Var." in valor_sistema:
        try:    variante_idx = ord(valor_sistema.split(u"Var.")[1].strip()[0]) - 65
        except: variante_idx = 0

    _tipo_perfil = req(perfil, u"tipos").get(tipo_num)
    if _tipo_perfil is None:
        forms.alert(
            u"O perfil normativo '{}' não define o Tipo {} de sistema de hidrante.".format(
                perfil.get(u"norma"), tipo_num),
            title="Fire Utils", warn_icon=True)
        script.exit()

    dados_sistema = dict(_tipo_perfil["variantes"][variante_idx])
    dados_sistema["esguicho_dn"] = _tipo_perfil["esguicho_dn"]

Qs_lmin = dados_sistema["q_min"]
Pmin    = dados_sistema["p_min"]
C_HW    = req(perfil, u"hazen_c")[u"galvanizado"]

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
for i in [u"RTI", u"Succao", u"Recalque", u"Ponto A"]:
    if i not in ident_map: erros.append(u"Identificador '{}' não encontrado".format(i))
for h in [u"HID-01", u"HID-02"]:
    if h not in hid_map: erros.append(u"'{}' não encontrado".format(h))
if erros:
    forms.alert(u"Elementos não encontrados:\n{}\n\nExecute 'Mapear Trechos' primeiro.".format(
        u"\n".join(erros)), title="Fire Utils", warn_icon=True)
    script.exit()

# --- Etapa 3: cotas altimétricas de todos os pontos da marcha ---
cotas = {
    "z_rti":      get_z(ident_map[u"RTI"],      modo="auto"),
    "z_succao":   get_z(ident_map[u"Succao"],   modo="auto"),
    "z_recalque": get_z(ident_map[u"Recalque"], modo="auto"),
    "z_ponto_a":  get_z(ident_map[u"Ponto A"]),
    "z_hd01":     get_z(hid_map[u"HID-01"]),
    "z_hd02":     get_z(hid_map[u"HID-02"]),
}

_nomes_cotas = {
    "z_rti": u"RTI", "z_succao": u"Sucção", "z_recalque": u"Recalque",
    "z_ponto_a": u"Ponto A", "z_hd01": u"HID-01", "z_hd02": u"HID-02",
}
erros_z = [_nomes_cotas[k] for k, z in cotas.items() if z is None]
if erros_z:
    forms.alert(u"Não foi possível ler a elevação de:\n{}".format(u"\n".join(erros_z)),
                title="Fire Utils", warn_icon=True)
    script.exit()

# Condição de sucção — determinada automaticamente pela cota entre a RTI e o
# trecho de sucção da bomba, nunca perguntada ao usuário:
#   RTI acima da sucção (ΔZ > 0)      → sucção positiva (afogada, favorável)
#   RTI no mesmo nível ou abaixo      → sucção negativa (bomba "puxa" a água) — mais restritiva
Hz_succao = cotas["z_rti"] - cotas["z_succao"]
succao = u"positiva" if Hz_succao > 0.05 else u"negativa"

# --- Etapa 4: extrair dados dos trechos (por diâmetro) e resolver a marcha ---
trechos_data = {
    "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome),
}

res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas)

# --- Etapa 5: eficiência e potência da bomba ---
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
pot_cv  = calc_potencia(res["Qt"] / 60000.0, res["P_RTI"], eta_dec)
pot_kw  = pot_cv / 1.36

# --- Etapa 6: memorial de cálculo ---
import datetime
timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
print_memorial_calculo(
    res, dados_sistema, valor_sistema,
    cotas, succao, Hz_succao,
    Qs_lmin, Pmin, C_HW,
    eta, pot_cv, pot_kw, timestamp, perfil,
)

# --- Etapa 7: salvar cache ---
payload_hid = {
    "res":           res,
    "dados_sistema": dados_sistema,
    "valor_sistema": valor_sistema,
    "metodo":        u"marcha_fator_k",
    "cotas":         cotas,
    "Hz_succao":     Hz_succao,
    "succao":        succao,
    "C_HW":          C_HW,
    "uf":            perfil.get(u"_uf_efetiva"),
    "eta":           eta,
    "pot_cv":        pot_cv,
    "pot_kw":        pot_kw,
    "_nome_projeto": doc.Title,
}
salvar_cache(payload_hid, projeto_dir)
