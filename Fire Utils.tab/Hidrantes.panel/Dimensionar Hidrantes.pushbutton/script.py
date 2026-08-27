# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes
Dimensionamento hidráulico pelo MÉTODO DA MARCHA (passo a passo):
HD01 → Ponto A → Descarga da Bomba → RTI, com ajuste da vazão do hidrante
mais favorável pelo Fator K. Imprime o memorial de cálculo no output do
pyRevit e salva cache para os demais botões.
(Nos elementos do Revit os identificadores gravados por 'Mapear Trechos'
continuam sendo "HID-01"/"HID-02"; no memorial a nomenclatura é HD01/HD02.)
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
    MCA_POR_BAR, METODO_VALVULA, METODOS_CALCULO,
    F_DARCY, K_VALVULA, COEF_JM, G,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
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
    """
    Diâmetro NOMINAL (DN) do elemento — não o diâmetro interno real medido
    pelo schedule/material. Ex.: um tubo DN 65 pode ter diâmetro interno
    de 68,8 mm; o cálculo (Jun, J, V) usa o nominal, como no dimensionamento
    de referência. RBS_PIPE_DIAMETER_PARAM é o parâmetro "Diâmetro" do tubo
    (o tamanho nominal da lista de segmentos/tipos de tubo do Revit).
    """
    try:
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if p and p.AsDouble() > 0: return to_m(p.AsDouble())
        # Fallback: elemento sem "Diâmetro" nominal (ex.: acessório atípico)
        # usa o diâmetro interno, melhor que nada.
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_INNER_DIAM_PARAM)
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
    """
    Tabelas de tubulação e de conexões/acessórios por diâmetro, exibidas
    antes do cálculo de cada trecho (levantamento dos comprimentos
    equivalentes: Ltotal = L + Leq, por diâmetro).
    """
    output.print_md(u"**Quantitativo de tubulação por diâmetro**")
    output.print_md(u"| DN nominal (mm) | Nº tubos | L (m) | Leq (m) | **Ltotal = L + Leq (m)** |")
    output.print_md(u"|---|---|---|---|---|")
    for s in jt["segmentos"]:
        output.print_md(u"| {:.1f} | {} | {:.4f} | {:.4f} | **{:.4f}** |".format(
            s["d_mm"], s["n_tubos"], s["L"], s["Leq"], s["Ltotal"]))
    output.print_md(u"")

    tem_aces = any(s["acessorios"] for s in jt["segmentos"])
    output.print_md(u"**Conexões e acessórios por diâmetro (comprimentos equivalentes)**")
    if tem_aces:
        output.print_md(u"| Conexão / acessório | DN (mm) | Qtd | Leq unitário (m) | Leq total (m) |")
        output.print_md(u"|---|---|---|---|---|")
        for s in jt["segmentos"]:
            for a in s["acessorios"]:
                output.print_md(u"| {} | {:.1f} | {} | {:.4f} | {:.4f} |".format(
                    a["nome"], s["d_mm"], a["qtd"], a["leq_unit"], a["leq_tot"]))
    else:
        output.print_md(u"*Nenhuma conexão com comprimento equivalente cadastrado neste trecho.*")
    output.print_md(u"")

def _tabela_hazen(jt, v_limite):
    """Tabela de Jun/J/V por diâmetro de um trecho."""
    output.print_md(u"**Perda de carga (Hazen-Williams) — Q = {:.2f} L/min**".format(jt["Q_lmin"]))
    output.print_md(u"| DN (mm) | Ltotal (m) | Jun (m/m) | J = Ltotal·Jun (mca) | V = 21,22·Q/D² (m/s) | Verificação (V {} {:.1f}) |".format(
        SIM_LE, v_limite))
    output.print_md(u"|---|---|---|---|---|---|")
    for s in jt["segmentos"]:
        vv = (u"{} {:.3f}".format(SIM_OK, s["V"]) if s["V"] <= v_limite
              else u"{} {:.3f} > {:.1f}".format(SIM_X, s["V"], v_limite))
        output.print_md(u"| {:.1f} | {:.4f} | {:.6f} | {:.4f} | {:.3f} | {} |".format(
            s["d_mm"], s["Ltotal"], s["Jun"], s["J"], s["V"], vv))
    output.print_md(u"**J do trecho (soma dos diâmetros) = {:.4f} mca**".format(jt["J"]))
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

    K        = res["K"]
    dH       = res["dH"]
    j        = res["j"]
    metodo   = res["metodo"]
    esguicho = res["esguicho"]
    esg      = res["esg"]

    # Ponto de aplicação do par normativo (Q, Pmin), conforme o método
    ponto_ref = u"ponta do esguicho" if esguicho else u"válvula do hidrante"

    # Numeração dinâmica de seções: o método do esguicho acrescenta as
    # seções de perda na mangueira e na válvula antes do Fator K.
    _sec = {"n": 0}
    def sec(titulo):
        _sec["n"] += 1
        output.print_md(u"## {}. {}".format(_sec["n"], titulo))
        return _sec["n"]

    # ── Cabeçalho ─────────────────────────────────────────────────────────
    output.print_md(u"# Memorial de Cálculo — Dimensionamento Hidráulico de Hidrantes")
    output.print_md(u"**Sistema:** {} | **Método:** {} | **Norma:** {} | *{}*".format(
        valor_sistema, metodo, norma, timestamp))
    output.print_md(u"---")

    if perfil.get(u"_uf_efetiva") != perfil.get(u"_uf_solicitada"):
        output.print_md(
            u"> **Aviso:** o Estado do projeto ('{}') ainda não possui perfil "
            u"normativo próprio nesta extensão. Usando o perfil default "
            u"'{}' ({}).".format(
                perfil.get(u"_uf_solicitada"), perfil.get(u"_uf_efetiva"), norma))
        output.print_md(u"")

    # ── Vazão e pressão de projeto ────────────────────────────────────────
    sec(u"Definição da Vazão e da Pressão de Projeto")
    output.print_md(u"| Parâmetro | Valor | Referência |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Norma aplicada | **{}** | — |".format(norma))
    output.print_md(u"| Classificação do sistema | **{}** | {} |".format(
        _md_cell(valor_sistema), tipos_ref))
    output.print_md(u"| Método de cálculo | **{}** | — |".format(metodo))
    output.print_md(u"| Ponto de aplicação de Q e Pmin | **{}** | método de cálculo |".format(
        ponto_ref))
    output.print_md(u"| Vazão por hidrante (Q) | **{:g} L/min** | {} |".format(Qs_lmin, tipos_ref))
    output.print_md(u"| Hidrantes simultâneos (n) | **{}** | {} |".format(hidr_simult, hidr_simult_ref))
    output.print_md(u"| Pressão residual mínima (Pmin) | **{:g} mca = {:.4f} bar** | {} |".format(
        Pmin, float(Pmin) / MCA_POR_BAR, tipos_ref))
    output.print_md(u"| Coef. Hazen-Williams (C) | **{}** | {} — aço/ferro galvanizado |".format(
        C_HW, hazen_c_ref))
    output.print_md(u"| Esguicho — DN | {:g} mm | {} |".format(dados_sistema["esguicho_dn"], tipos_ref))
    output.print_md(u"| Mangueira — DN / comprimento | {:g} mm / {:.1f} m | {} |".format(
        dados_sistema["mang_dn"], dados_sistema["mang_comp"], tipos_ref))
    output.print_md(u"| Velocidade máx. — recalque/descarga | {:.1f} m/s | {} |".format(
        v_max_tubo, v_max_tubo_ref))
    output.print_md(u"| Velocidade máx. — sucção ({}) | {:.1f} m/s | {} |".format(
        succao, v_max_succao, v_max_suc_ref))
    output.print_md(u"")

    # ── 2. Hidrantes mais desfavoráveis ───────────────────────────────────
    sec(u"Identificação dos Hidrantes Mais Desfavoráveis em "
        u"Funcionamento Simultâneo")
    output.print_md(u"O cenário de cálculo representa a condição mais crítica de operação "
                    u"do sistema: os **{} hidrantes mais desfavoráveis em funcionamento "
                    u"simultâneo**, ou seja, aquela que resulta na maior demanda de vazão "
                    u"total associada às maiores perdas de carga e ao maior desnível "
                    u"geométrico.".format(hidr_simult))
    output.print_md(u"")

    # ── 3. Identificação dos trechos ──────────────────────────────────────
    sec(u"Identificação dos Trechos")
    output.print_md(u"Para fins de organização e como facilitador de cálculo, a tubulação "
                    u"é dividida em trechos. O **Ponto A** é o ponto de distribuição onde "
                    u"há a separação das vazões que vão rumo aos hidrantes desfavoráveis "
                    u"considerados.")
    output.print_md(u"")
    output.print_md(u"| Trecho | Percurso | Vazão de cálculo |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Sucção | RTI → Bomba | Qt |")
    output.print_md(u"| Recalque — Bomba ao Ponto A | Bomba → Ponto A | Qt |")
    output.print_md(u"| Recalque — Ponto A ao HD01 | Ponto A → HD01 | Q_hd01 |")
    output.print_md(u"| Recalque — Ponto A ao HD02 | Ponto A → HD02 | Q_hd02 |")
    output.print_md(u"")

    # ── Esguicho e mangueira / válvula (só no método do esguicho) ─────────
    if esguicho:
        _ref     = esg["ref"]
        _dm_mm   = esg["mang_dn_mm"]
        _lm      = esg["mang_comp_m"]
        _dm_m    = float(_dm_mm) / 1000.0

        sec(u"Perda de Carga no Esguicho e na Mangueira")
        output.print_md(u"A perda de carga no esguicho é igual à **pressão mínima exigida "
                        u"em projeto (Pmin = {:g} mca)**, aplicada na ponta do esguicho.".format(Pmin))
        output.print_md(u"")
        output.print_md(u"A perda de carga na mangueira é dada pela equação de "
                        u"**Darcy-Weisbach**:")
        output.print_md(u"")
        output.print_md(u"**Jm = {:g}·f·Lm / (g·π²·Dm⁵) · Q²**".format(COEF_JM))
        output.print_md(u"")
        output.print_md(u"Onde:")
        output.print_md(u"- **Jm** — Perda de carga na mangueira, em mca")
        output.print_md(u"- **f** = {:g}".format(F_DARCY))
        output.print_md(u"- **Lm** — Comprimento da mangueira = {:g} m".format(_lm))
        output.print_md(u"- **g** = {:g} m/s²".format(G))
        output.print_md(u"- **Dm** — Diâmetro da mangueira = {:g} mm = {:.4f} m".format(
            _dm_mm, _dm_m))
        output.print_md(u"")
        output.print_md(u"Em seguida calcula-se a velocidade do fluido na mangueira:")
        output.print_md(u"")
        output.print_md(u"**V = 21,22 · Q / Dm²**")
        output.print_md(u"")
        output.print_md(u"Para o hidrante mais desfavorável, com a vazão normativa "
                        u"Q = {:g} L/min:".format(Qs_lmin))
        output.print_md(u"")
        output.print_md(u"| Grandeza | Valor |")
        output.print_md(u"|---|---|")
        output.print_md(u"| Perda no esguicho (= Pmin) | **{:g} mca** |".format(Pmin))
        output.print_md(u"| Jm — perda na mangueira | **{:.4f} mca** |".format(_ref["Jm"]))
        output.print_md(u"| V — velocidade na mangueira | **{:.4f} m/s** |".format(_ref["V"]))
        output.print_md(u"")

        sec(u"Perda de Carga na Válvula do Hidrante")
        output.print_md(u"Com a velocidade do fluido na mangueira, calcula-se a perda de "
                        u"carga na válvula angular do hidrante:")
        output.print_md(u"")
        output.print_md(u"**Jvalv = K · V² / (2g)**")
        output.print_md(u"")
        output.print_md(u"Onde:")
        output.print_md(u"- **Jvalv** — Perda de carga na válvula, em mca")
        output.print_md(u"- **K** — Fator K da válvula, adotado como **{:g}** no "
                        u"dimensionamento".format(K_VALVULA))
        output.print_md(u"- **V** — Velocidade do fluido na mangueira, em m/s")
        output.print_md(u"- **g** = {:g} m/s²".format(G))
        output.print_md(u"")
        output.print_md(u"Jvalv = {:g} · {:.4f}² / (2 · {:g}) = **{:.4f} mca**".format(
            K_VALVULA, _ref["V"], G, _ref["Jvalv"]))
        output.print_md(u"")

    # ── Fator K ───────────────────────────────────────────────────────────
    sec(u"Cálculo do Fator K")
    output.print_md(u"Calculado **apenas no hidrante mais desfavorável**, com a vazão "
                    u"normativa e a pressão na válvula do hidrante:")
    output.print_md(u"")
    output.print_md(u"**K = Q / √P**")
    output.print_md(u"")
    output.print_md(u"Onde:")
    output.print_md(u"- **K** — Coeficiente de escoamento ou de vazão, em L/min/bar^0,5")
    output.print_md(u"- **Q** — Vazão do hidrante, em L/min")
    output.print_md(u"- **P** — Pressão na válvula do hidrante, em bar "
                    u"(1 bar = {} mca)".format(MCA_POR_BAR))
    output.print_md(u"")
    P_ref = res["P_valv_ref"]
    if esguicho:
        output.print_md(u"Como o par normativo está referido à ponta do esguicho, a "
                        u"pressão na válvula soma as perdas da mangueira e da válvula:")
        output.print_md(u"")
        output.print_md(u"P = Pmin + Jm + Jvalv = {:g} + {:.4f} + {:.4f} = "
                        u"**{:.4f} mca**".format(
                            Pmin, esg["ref"]["Jm"], esg["ref"]["Jvalv"], P_ref))
        output.print_md(u"")
    output.print_md(u"K = {:g} / √({:.4f} / {}) = {:g} / √{:.4f} = "
                    u"**{:.4f} L/min/bar^0,5**".format(
                        Qs_lmin, P_ref, MCA_POR_BAR, Qs_lmin,
                        P_ref / MCA_POR_BAR, K))
    output.print_md(u"")
    output.print_md(u"Esse cálculo se faz necessário para realizar corretamente o "
                    u"equilíbrio hidráulico entre o primeiro e o segundo hidrante: o "
                    u"segundo hidrante, por estar numa posição mais favorável, terá maior "
                    u"pressão e, consequentemente, maior vazão — esse ajuste é feito pelo "
                    u"Fator K: **Q_hd02 = K·√P_hd02**.")
    output.print_md(u"")

    # ── 5. Cotas altimétricas ─────────────────────────────────────────────
    sec(u"Cotas Altimétricas")
    output.print_md(u"| Ponto | Cota H (m) |")
    output.print_md(u"|---|---|")
    output.print_md(u"| RTI (reservatório) | **{:.4f}** |".format(cotas["z_rti"]))
    output.print_md(u"| Sucção (entrada da bomba) | **{:.4f}** |".format(cotas["z_succao"]))
    output.print_md(u"| Descarga da bomba | **{:.4f}** |".format(cotas["z_recalque"]))
    output.print_md(u"| Ponto A (distribuição) | **{:.4f}** |".format(cotas["z_ponto_a"]))
    output.print_md(u"| HD01 (mais desfavorável) | **{:.4f}** |".format(cotas["z_hd01"]))
    output.print_md(u"| HD02 (2º mais desfavorável) | **{:.4f}** |".format(cotas["z_hd02"]))
    output.print_md(u"")
    output.print_md(u"**∆H = Hi − Hf** (posição dos pontos inicial e final de cada trecho, "
                    u"na direção da marcha de cálculo):")
    output.print_md(u"| Trecho | Hi (m) | Hf (m) | ∆H (m) |")
    output.print_md(u"|---|---|---|---|")
    output.print_md(u"| HD01 ao Ponto A | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_hd01"], cotas["z_ponto_a"], dH["t3"]))
    output.print_md(u"| HD02 ao Ponto A | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_hd02"], cotas["z_ponto_a"], dH["t4"]))
    output.print_md(u"| Ponto A à descarga da bomba | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_ponto_a"], cotas["z_recalque"], dH["t2"]))
    output.print_md(u"| Sucção (Bomba à RTI) | {:.4f} | {:.4f} | **{:.4f}** |".format(
        cotas["z_succao"], cotas["z_rti"], dH["t1"]))
    output.print_md(u"")
    output.print_md(
        u"**Condição de sucção ({}):** determinada pela cota entre a RTI e a "
        u"entrada de sucção da bomba (H_RTI − H_sucção = {:.4f} m) — "
        u"**sucção {}**.".format(v_max_suc_ref, Hz_succao, succao))
    output.print_md(u"")

    # ── 6. Fórmulas da marcha ─────────────────────────────────────────────
    sec(u"Fórmulas Utilizadas")
    output.print_md(u"- Comprimento total por trecho/diâmetro: **Ltotal = L + Leq** "
                    u"(L = comprimento real; Leq = comprimento equivalente das conexões)")
    output.print_md(u"- Perda de carga unitária (Hazen-Williams): "
                    u"**Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87** [m/m]")
    output.print_md(u"  - **Q**: vazão no trecho, em L/min (da sucção ao Ponto A é Qt; "
                    u"do Ponto A aos hidrantes só Q)")
    output.print_md(u"  - **C**: coeficiente de rugosidade, adimensional ({} para "
                    u"galvanizado)".format(C_HW))
    output.print_md(u"  - **D**: diâmetro nominal (DN) da tubulação, em mm")
    output.print_md(u"- Perda de carga do trecho: **J = Ltotal · Jun** [mca], somada por "
                    u"diâmetro")
    output.print_md(u"- Velocidade: **V = 21,22 · Q / D²** [m/s]")
    if esguicho:
        output.print_md(u"- Perda na mangueira (Darcy-Weisbach): "
                        u"**Jm = {:g}·f·Lm/(g·π²·Dm⁵)·Q²** [mca]".format(COEF_JM))
        output.print_md(u"- Perda na válvula angular: **Jvalv = K·V²/(2g)** [mca], "
                        u"com K = {:g}".format(K_VALVULA))
        output.print_md(u"- Esguicho → válvula: **P_valv = Pmin + Jm + Jvalv**")
    output.print_md(u"- Marcha de pressões: **P = P_anterior + J ± ∆H**")
    output.print_md(u"- Ajuste do hidrante favorável: **Q = K·√P** (P em bar)")
    output.print_md(u"")

    # ── Cálculo por trecho (marcha) ───────────────────────────────────────
    n7 = sec(u"Cálculo Trecho a Trecho")
    output.print_md(u"")

    _P_ref_lbl = u"P_valv" if esguicho else u"P_hd01"

    # HD01 ao Ponto A
    output.print_md(u"### {}.1 Trecho HD01 ao Ponto A".format(n7))
    _tabelas_trecho(j["t3"])
    _tabela_hazen(j["t3"], v_max_tubo)
    output.print_md(u"**Pressão necessária no Ponto A pelo ramal do HD01:**")
    output.print_md(u"P_PA = {} + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        _P_ref_lbl, P_ref, j["t3"]["J"], _fmt_dh(dH["t3"]), res["P_PA1"]))
    output.print_md(u"")

    # HD02 ao Ponto A
    output.print_md(u"### {}.2 Trecho HD02 ao Ponto A".format(n7))
    _tabelas_trecho(j["t4"])
    _tabela_hazen(j["t4"], v_max_tubo)
    output.print_md(u"**Pressão necessária no Ponto A pelo ramal do HD02** (com a vazão "
                    u"normativa Q = {:g} L/min, mesma vazão usada no ramal do HD01):".format(
                        Qs_lmin))
    output.print_md(u"P_PA = {} + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        _P_ref_lbl.replace(u"hd01", u"hd02"), P_ref, j["t4"]["J"],
        _fmt_dh(dH["t4"]), res["P_PA2"]))
    output.print_md(u"")

    # Ponto A e vazões finais pelo Fator K (sem ciclo)
    output.print_md(u"### {}.3 Pressão no Ponto A e Vazões Finais (Fator K)".format(n7))
    output.print_md(u"**Pressão adotada no Ponto A = maior pressão calculada entre os "
                    u"dois trechos:** P_PA = max({:.4f}; {:.4f}) = **{:.4f} mca** "
                    u"(ramal governante: **{}**)".format(
                        res["P_PA1"], res["P_PA2"], res["P_PA"], res["hid_governa"]))
    output.print_md(u"")
    output.print_md(u"Com o Ponto A nessa pressão, a pressão na válvula de cada hidrante "
                    u"é P_hd = P_PA − J ∓ ∆H (o ramal governante retorna, por construção, "
                    u"exatamente à pressão de referência):")
    output.print_md(u"")
    output.print_md(u"P_hd01 = {:.4f} {} {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], u"−", j["t3"]["J"], _fmt_dh(-dH["t3"]), res["P_hd01"]))
    output.print_md(u"P_hd02 = {:.4f} {} {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], u"−", j["t4"]["J"], _fmt_dh(-dH["t4"]), res["P_hd02"]))
    output.print_md(u"")
    output.print_md(u"**Q = K·√P**")
    output.print_md(u"")
    output.print_md(u"Q_hd01 = {:.4f} · √({:.4f} / {}) = **{:.2f} L/min**".format(
        K, res["P_hd01"], MCA_POR_BAR, res["Q_hd01"]))
    output.print_md(u"Q_hd02 = {:.4f} · √({:.4f} / {}) = **{:.2f} L/min**".format(
        K, res["P_hd02"], MCA_POR_BAR, res["Q_hd02"]))
    output.print_md(u"")
    output.print_md(u"**Qt = Q_hd01 + Q_hd02 = {:.2f} + {:.2f} = {:.2f} L/min**".format(
        res["Q_hd01"], res["Q_hd02"], res["Qt"]))
    output.print_md(u"")

    if esguicho:
        output.print_md(u"Com a vazão final de cada hidrante, recalculam-se a velocidade "
                        u"na mangueira e a perda na válvula angular — valores que aumentam "
                        u"conforme o traçado hidráulico caminha em direção aos pontos mais "
                        u"favoráveis. A pressão no esguicho sai de "
                        u"**P_esg = P_hd − Jm − Jvalv**:")
        output.print_md(u"")
        output.print_md(u"| Hidrante | Q (L/min) | V mangueira (m/s) | Jm (mca) | "
                        u"Jvalv (mca) | P_válvula (mca) | **P_esguicho (mca)** |")
        output.print_md(u"|---|---|---|---|---|---|---|")
        for lbl, e in [(u"HD01", esg["hd01"]), (u"HD02", esg["hd02"])]:
            output.print_md(u"| {} | {:.2f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | "
                            u"**{:.4f}** |".format(
                                lbl, e["Q_lmin"], e["V"], e["Jm"], e["Jvalv"],
                                e["P_valv"], e["P_esg"]))
        output.print_md(u"")

    output.print_md(u"**Pressões e vazões resultantes nos hidrantes:**")
    _col_p = u"P esguicho (mca)" if esguicho else u"P válvula (mca)"
    output.print_md(u"| Hidrante | {} | Q (L/min) | Verificação (P {} {:g} mca e "
                    u"Q {} {:g} L/min) |".format(_col_p, SIM_GE, Pmin, SIM_GE, Qs_lmin))
    output.print_md(u"|---|---|---|---|")
    if esguicho:
        _linhas = [(u"HD01", esg["hd01"]["P_esg"], res["Q_hd01"]),
                   (u"HD02", esg["hd02"]["P_esg"], res["Q_hd02"])]
    else:
        _linhas = [(u"HD01", res["P_hd01"], res["Q_hd01"]),
                   (u"HD02", res["P_hd02"], res["Q_hd02"])]
    for lbl, p, q in _linhas:
        _ok = (p >= float(Pmin) - 0.01 and q >= float(Qs_lmin) - 0.01)
        ver = (u"{} atende".format(SIM_OK) if _ok
               else u"{} NÃO atende".format(SIM_X))
        output.print_md(u"| {} | {:.4f} | {:.2f} | {} |".format(lbl, p, q, ver))
    output.print_md(u"")

    # Ponto A à descarga da bomba
    output.print_md(u"### {}.4 Trecho do Ponto A à Descarga da Bomba".format(n7))
    output.print_md(u"Nesse trecho a vazão a ser considerada é a soma das vazões dos dois "
                    u"hidrantes em funcionamento, e a pressão inicial é a maior pressão "
                    u"calculada entre os dois trechos anteriores:")
    output.print_md(u"**Qt = Q_hd01 + Q_hd02 = {:.2f} + {:.2f} = {:.2f} L/min**".format(
        res["Q_hd01"], res["Q_hd02"], res["Qt"]))
    output.print_md(u"")
    _tabelas_trecho(j["t2"])
    _tabela_hazen(j["t2"], v_max_tubo)
    output.print_md(u"**Pressão na saída da bomba:**")
    output.print_md(u"P_SB = P_PA + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], j["t2"]["J"], _fmt_dh(dH["t2"]), res["P_SB"]))
    output.print_md(u"")

    # 7.4 — sucção
    output.print_md(u"### {}.5 Trecho de Sucção (RTI à Bomba)".format(n7))
    output.print_md(u"A pressão a ser utilizada agora é a encontrada no trecho anterior "
                    u"(Ponto A à descarga da bomba). Aqui utiliza-se para o cálculo de "
                    u"Jun também a vazão total Qt = {:.2f} L/min.".format(res["Qt"]))
    output.print_md(u"")
    _tabelas_trecho(j["t1"])
    _tabela_hazen(j["t1"], v_max_succao)
    output.print_md(u"**Pressão de demanda referida à RTI:**")
    output.print_md(u"P_RTI = P_SB + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_SB"], j["t1"]["J"], _fmt_dh(dH["t1"]), res["P_RTI"]))
    output.print_md(u"")

    # ── 8. Verificação de velocidades (resumo) ────────────────────────────
    sec(u"Verificação da Velocidade de Escoamento")
    output.print_md(u"**V = 21,22 · Q / D²** — limites máximos recomendados: {:.1f} m/s "
                    u"(sucção {}), {:.1f} m/s (trecho de descarga) — {} / {}.".format(
                        v_max_succao, succao, v_max_tubo, v_max_suc_ref, v_max_tubo_ref))
    output.print_md(u"| Trecho | DN (mm) | Q (L/min) | V (m/s) | Limite (m/s) | Verificação |")
    output.print_md(u"|---|---|---|---|---|---|")
    _rotulos = {"t1": u"Sucção", "t2": u"Bomba ao Ponto A",
                "t3": u"Ponto A ao HD01", "t4": u"Ponto A ao HD02"}
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

    # ── 9. Demanda do sistema ─────────────────────────────────────────────
    sec(u"Demanda do Sistema")
    output.print_md(u"Concluídos os cálculos e verificações, o sistema possui a demanda de:")
    output.print_md(u"")
    output.print_md(u"| Grandeza | Valor |")
    output.print_md(u"|---|---|")
    output.print_md(u"| **Q = Qt** | **{:.2f} L/min = {:.4f} m³/h** |".format(
        res["Qt"], res["Qt"] * 60.0 / 1000.0))
    output.print_md(u"| **P = P_RTI** | **{:.4f} mca = {:.4f} bar** |".format(
        res["P_RTI"], res["P_RTI"] / MCA_POR_BAR))
    output.print_md(u"")

    # ── 10. Bomba ─────────────────────────────────────────────────────────
    sec(u"Dimensionamento da Bomba de Recalque")
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

# A Tabela 2 (hidrantes/db.py) guarda esses valores como int. O IronPython
# 2.7 do Revit (diferente do CPython) lança ValueError em "{:.1f}".format(x)
# quando x é int — então normalizamos tudo para float aqui, no único ponto
# de entrada dos dois caminhos (Tabela 2 e personalizado; este último já
# vem normalizado de custom_store, mas o float() abaixo é inofensivo).
for _chave in (u"q_min", u"p_min", u"mang_dn", u"mang_comp", u"esguicho_dn"):
    dados_sistema[_chave] = float(dados_sistema[_chave])

Qs_lmin = dados_sistema["q_min"]
Pmin    = dados_sistema["p_min"]
C_HW    = req(perfil, u"hazen_c")[u"galvanizado"]

# --- Etapa 1b: método de cálculo (define ONDE Qs/Pmin se aplicam) ---
# Gravado por "Classificar Sistema". Projetos classificados antes desse
# parâmetro existir caem no método da válvula (comportamento anterior).
_param_metodo = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
metodo_calculo = _param_metodo.AsString() if _param_metodo else None
if metodo_calculo not in METODOS_CALCULO:
    if metodo_calculo:
        forms.alert(
            u"Método de cálculo desconhecido no projeto:\n'{}'\n\n"
            u"Execute 'Classificar Sistema de Hidrante' novamente.".format(
                metodo_calculo),
            title="Fire Utils", warn_icon=True)
        script.exit()
    metodo_calculo = METODO_VALVULA

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

# Condição de sucção — determinada automaticamente pela cota entre a RTI
# (tomada de água) e a sucção da bomba, nunca perguntada ao usuário:
#   Tomada de água NO NÍVEL ou ACIMA da sucção da bomba (ΔZ >= 0) → positiva
#   Tomada de água ABAIXO da sucção da bomba (ΔZ < 0)             → negativa
# Tolerância de 1 mm só para não classificar como negativa por ruído de
# arredondamento quando as duas cotas são, na prática, iguais.
Hz_succao = cotas["z_rti"] - cotas["z_succao"]
succao = u"negativa" if Hz_succao < -0.001 else u"positiva"

# --- Etapa 4: extrair dados dos trechos (por diâmetro) e resolver a marcha ---
trechos_data = {
    "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome),
}

res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas,
                    metodo=metodo_calculo,
                    mang_dn_mm=dados_sistema["mang_dn"],
                    mang_comp_m=dados_sistema["mang_comp"])

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
    "metodo":        metodo_calculo,
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
