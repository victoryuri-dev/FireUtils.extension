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

from hidrantes.db import SISTEMAS_HIDRANTE
from hidrantes.calc import (
    iterar_vazoes, calc_hf_mangueira, calc_potencia,
    extrair_trecho, salvar_cache,
    C_HW, _f, _g, _Lm,
)

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_TRECHO           = u"FireUtils - Trecho"
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
# OUTPUT RÁPIDO — apenas resultados objetivos
# ===========================================================================

def _ok(v, minimo, maximo=None):
    if v < minimo:   return u"✗ ABAIXO ({} mca)".format(minimo)
    if maximo and v > maximo: return u"✗ ACIMA ({} mca)".format(maximo)
    return u"✓"

def _vel(v):
    return u"✓" if v <= 3.0 else u"✗ {:.2f} m/s".format(v)

def print_conferencia(res, Hz_H1, Hz_H2, Pmin, pot_cv, pot_kw, eta, timestamp):
    output.print_md(u"# Fire Utils — Dimensionamento de Hidrantes")
    output.print_md(u"*Calculado em {}*".format(timestamp))
    output.print_md(u"---")

    # Bloco 1: Altura manométrica
    output.print_md(u"### Altura Manométrica")
    output.print_md(u"| Parcela | Valor | Condição |")
    output.print_md(u"|---|---|---|")
    output.print_md(u"| Σhf percurso crítico ({}) | **{:.4f} mca** | — |".format(
        res["hid_governa"], res["Hf_governa"]))
    _hz = res["Hz_governa"]
    _cond = u"RTI acima — favorável" if _hz > 0.05 else (u"RTI abaixo — desfavorável" if _hz < -0.05 else u"Mesmo nível")
    output.print_md(u"| ΔZ | **{:.4f} m** | {} |".format(_hz, _cond))
    output.print_md(u"| Pmin | **{} mca** | — |".format(Pmin))
    output.print_md(u"| **Ht** | **{:.4f} mca** | — |".format(res["Ht"]))
    output.print_md(u"")

    # Bloco 2: Trechos — só velocidade e hf
    output.print_md(u"### Trechos")
    output.print_md(u"| Trecho | Q (L/min) | D (mm) | V (m/s) | hf (mca) | V ok? |")
    output.print_md(u"|---|---|---|---|---|---|")
    for key in ["t1","t2","t3","t4"]:
        t = res["hf"][key]
        output.print_md(u"| {} | {:.1f} | {:.1f} | {:.3f} | {:.4f} | {} |".format(
            t["label"], t["Q_lmin"], t["D"]*1000,
            t["V"], t["Hf"], _vel(t["V"])))
    output.print_md(u"")

    # Bloco 3: Hidrantes
    output.print_md(u"### Hidrantes")
    output.print_md(u"| Hidrante | P (mca) | Q (L/min) | Status |")
    output.print_md(u"|---|---|---|---|")
    output.print_md(u"| HID-01 ({}°) | **{:.4f}** | **{:.1f}** | {} |".format(
        u"1", res["p_hid01"], res["Q_h01"], _ok(res["p_hid01"], Pmin, 100.0)))
    output.print_md(u"| HID-02 ({}°) | **{:.4f}** | **{:.1f}** | {} |".format(
        u"2", res["p_hid02"], res["Q_h02"], _ok(res["p_hid02"], Pmin, 100.0)))
    output.print_md(u"| ΔP entre hidrantes | **{:.4f} mca** | — | — |".format(
        abs(res["p_hid02"] - res["p_hid01"])))
    output.print_md(u"")

    # Bloco 4: Bomba
    output.print_md(u"### Bomba")
    output.print_md(u"| Parâmetro | Valor |")
    output.print_md(u"|---|---|")
    output.print_md(u"| Qt total | **{:.2f} L/min ({:.2f} m³/h)** |".format(
        res["Qt_final"], res["Qt_final"]/1000.0*60))
    output.print_md(u"| Ht | **{:.4f} mca** |".format(res["Ht"]))
    output.print_md(u"| η | **{}%** |".format(eta))
    output.print_md(u"| **Potência mínima** | **{:.2f} cv / {:.2f} kW** |".format(pot_cv, pot_kw))
    output.print_md(u"")
    output.print_md(u"---")
    output.print_md(u"*Cache salvo. Use o botão **Gerar Memorial** para o relatório completo.*")

# ===========================================================================
# MAIN
# ===========================================================================

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
Hm_mangueira = 0.0; Hesg = 0.0
if calculo_escolha == u"Ponta do Esguicho Regulável":
    Hm_mangueira = calc_hf_mangueira(Qs_m3s, Dm_m)

# --- Etapa 5: extrair dados dos trechos e iterar ---
trechos_data = {
    "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome),
}

res = iterar_vazoes(trechos_data, Qs_lmin, Hz_H1, Hz_H2, Hm_mangueira, Hesg, Pmin, C_HW)

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

# --- Etapa 7: output rápido ---
import datetime
timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
print_conferencia(res, Hz_H1, Hz_H2, Pmin, pot_cv, pot_kw, eta, timestamp)

# --- Etapa 8: salvar cache para o botão Memorial ---
payload_hid = {
    "res":            res,
    "dados_sistema":  dados_sistema,
    "valor_sistema":  valor_sistema,
    "calculo_escolha": calculo_escolha,
    "Z_RTI":  Z_RTI,  "Z_HID01": Z_HID01, "Z_HID02": Z_HID02,
    "Hz_H1":  Hz_H1,  "Hz_H2":   Hz_H2,
    "Hm_mangueira": Hm_mangueira,
    "Hesg":   Hesg,
    "C_HW":   C_HW,
    "eta":    eta,
    "pot_cv": pot_cv,
    "pot_kw": pot_kw,
}
salvar_cache(payload_hid)

# --- Etapa 9: enviar ao servidor local (se ativo) ---
try:
    from server.client import servidor_ativo, enviar_hidrantes
    if servidor_ativo():
        enviado = enviar_hidrantes(payload_hid)
        if enviado:
            output.print_md(u"✅ *Dados enviados ao servidor local — memorial atualizado.*")
except Exception:
    pass  # servidor inativo ou não instalado — silencioso