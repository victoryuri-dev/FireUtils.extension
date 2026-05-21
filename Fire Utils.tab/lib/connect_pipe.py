# -*- coding: utf-8 -*-
"""
connect_pipe.py — Fire Utils · lib/
Conecta dois tubos com roteamento em ângulos retos.

Fluxo:
  Clique 1 — ponta do PIPE_DESC (tubo desconectado)
  Clique 2 — PIPE_REF (tubo referência): corpo → cria Tê  |  ponta → roteia até a ponta com joelhos

Etapa 1 — Extensão direta:
  Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref,
  apenas estende e conecta (tê ou joelho conforme posição).

Etapa 2 — Roteamento em L:
  pipe_desc horizontal  → tubo vertical P_start→P_knee + joelho em P_start
  pipe_desc vertical    → estende a curva do tubo até z_ref
  mesma cota            → conecta direto sem segmento vertical

Casos PIPE_REF (clique):
  corpo  → tubo horizontal P_knee→P_target + Tê (BreakCurve)
  ponta  → rota em L (seg1 paralelo ao eixo do ref + seg2 perpendicular) + joelhos
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, LocationCurve,
    BuiltInParameter, FilteredElementCollector,
    ElementId, UnitUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType, PlumbingUtils
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

# ── Tolerâncias ──────────────────────────────────────────────────────────────
TOL           = 1e-4          # geral (pés)
TOL_DZ        = _to_ft(0.01)  # 1 cm  — diferença de Z considerada "mesmo nível"
TOL_SEG       = _to_ft(0.05)  # 5 cm  — distância mínima para criar segmento
TOL_PONTA_REF = _to_ft(0.40)  # 40 cm — raio do clique para detectar ponta do PIPE_REF
TOL_CONN      = _to_ft(0.50)  # 50 cm — raio de busca de conector próximo


# ============================================================================
# HELPERS GEOMÉTRICOS
# ============================================================================

def _pipe_is_vertical(pipe):
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dx = p1.X - p0.X; dy = p1.Y - p0.Y; dz = p1.Z - p0.Z
    L  = math.sqrt(dx*dx + dy*dy + dz*dz)
    return L > TOL and math.sqrt(dx*dx + dy*dy) / L < 0.1


def _projetar_segmento(pt, pt_a, pt_b):
    """Projeta pt no segmento pt_a→pt_b (clamped). Retorna XYZ."""
    ab = pt_b - pt_a
    L  = ab.GetLength()
    if L < TOL:
        return XYZ(pt_a.X, pt_a.Y, pt_a.Z)
    n  = ab.Normalize()
    t  = max(0.0, min(L, (pt - pt_a).DotProduct(n)))
    return XYZ(pt_a.X + n.X * t, pt_a.Y + n.Y * t, pt_a.Z + n.Z * t)


def _rota_ate_endpoint(P_knee, P_target, d_ref):
    """
    Calcula a rota em L de P_knee até P_target usando d_ref como direção primária.
    seg1: P_knee → P_mid   (paralelo ao eixo de PIPE_REF)
    seg2: P_mid  → P_target (perpendicular ao eixo de PIPE_REF)
    Retorna (P_mid, needs_seg1, needs_seg2).
    """
    v = P_target - P_knee
    a = v.DotProduct(d_ref)
    P_mid = XYZ(P_knee.X + d_ref.X * a,
                P_knee.Y + d_ref.Y * a,
                P_knee.Z)
    needs_seg1 = abs(a) > TOL_SEG
    needs_seg2 = P_mid.DistanceTo(P_target) > TOL_SEG
    return P_mid, needs_seg1, needs_seg2


def _intersecao_com_pipe(P_start, d_ext, pt_A, pt_B):
    """
    Verifica se o raio (P_start + t*d_ext, t>=0) intersecta o segmento pt_A→pt_B.
    Usa fórmula de menor distância entre duas retas 3-D.
    Retorna (P_int, t, em_ponta) ou None.
    """
    TOL_SKEW  = _to_ft(0.02)   # 2 cm
    TOL_PONTA = _to_ft(0.05)   # 5 cm
    d_ref = pt_B - pt_A
    L_ref = d_ref.GetLength()
    if L_ref < TOL:
        return None
    d_ref_n = XYZ(d_ref.X / L_ref, d_ref.Y / L_ref, d_ref.Z / L_ref)
    w   = P_start - pt_A
    b   = d_ext.DotProduct(d_ref_n)
    d_  = d_ext.DotProduct(w)
    e   = d_ref_n.DotProduct(w)
    den = 1.0 - b * b
    if abs(den) < 1e-9:
        return None  # paralelo
    t = (b * e - d_) / den
    s = (e - b * d_) / den
    if t < -TOL:
        return None  # interseção ficaria atrás de P_start
    t = max(0.0, t)
    P_t = XYZ(P_start.X + d_ext.X * t, P_start.Y + d_ext.Y * t, P_start.Z + d_ext.Z * t)
    P_s = XYZ(pt_A.X + d_ref_n.X * s,  pt_A.Y + d_ref_n.Y * s,  pt_A.Z + d_ref_n.Z * s)
    if P_t.DistanceTo(P_s) > TOL_SKEW:
        return None  # retas oblíquas
    if s < -TOL_PONTA or s > L_ref + TOL_PONTA:
        return None  # fora dos limites do pipe_ref
    s_cl     = max(0.0, min(L_ref, s))
    em_ponta = s_cl < TOL_PONTA or s_cl > L_ref - TOL_PONTA
    P_int    = XYZ(pt_A.X + d_ref_n.X * s_cl,
                   pt_A.Y + d_ref_n.Y * s_cl,
                   pt_A.Z + d_ref_n.Z * s_cl)
    return P_int, t, em_ponta


# ============================================================================
# HELPERS REVIT
# ============================================================================

def _conn_near(element, pt, tol=None):
    """Conector de element mais próximo de pt."""
    tol = tol or TOL_CONN
    try:
        mgr = element.ConnectorManager
    except AttributeError:
        try:
            mgr = element.MEPModel.ConnectorManager
        except Exception:
            return None
    best, best_d = None, tol
    for c in mgr.Connectors:
        d = c.Origin.DistanceTo(pt)
        if d < best_d:
            best_d, best = d, c
    return best


def _conn_nearest(pipe, pt):
    """Conector de pipe mais próximo de pt (sem limite de distância)."""
    best, best_d = None, float('inf')
    for c in pipe.ConnectorManager.Connectors:
        d = c.Origin.DistanceTo(pt)
        if d < best_d:
            best_d, best = d, c
    return best


def _pipe_params(doc, pipe):
    """Retorna (pipe_type_id, sys_type_id, level_id, diam_ft) herdados de pipe."""
    pipe_type_id = pipe.GetTypeId()
    if pipe_type_id == ElementId.InvalidElementId:
        try:
            from Autodesk.Revit.DB.Plumbing import PipeType
            ts = FilteredElementCollector(doc).OfClass(PipeType).ToElements()
            if ts:
                pipe_type_id = ts[0].Id
        except Exception:
            pass

    sys_type_id = ElementId.InvalidElementId
    try:
        mep = pipe.MEPSystem
        if mep:
            sys_type_id = mep.GetTypeId()
    except Exception:
        pass
    if sys_type_id == ElementId.InvalidElementId:
        try:
            ts = FilteredElementCollector(doc).OfClass(PipingSystemType).ToElements()
            if ts:
                sys_type_id = ts[0].Id
        except Exception:
            pass

    try:
        level_id = pipe.ReferenceLevel.Id
    except Exception:
        level_id = ElementId.InvalidElementId

    diam_ft = _to_ft(0.065)
    for bip in [BuiltInParameter.RBS_PIPE_DIAMETER_PARAM,
                BuiltInParameter.RBS_PIPE_OUTER_DIAMETER]:
        try:
            p = pipe.get_Parameter(bip)
            if p and p.AsDouble() > 0:
                diam_ft = p.AsDouble()
                break
        except Exception:
            pass

    return pipe_type_id, sys_type_id, level_id, diam_ft


def _set_diam(pipe, diam_ft):
    for bip in [BuiltInParameter.RBS_PIPE_DIAMETER_PARAM,
                BuiltInParameter.RBS_PIPE_OUTER_DIAMETER]:
        try:
            p = pipe.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(diam_ft)
                return
        except Exception:
            pass


def _mk_pipe(doc, pa, pb, pt_id, sys_id, lvl_id, diam_ft):
    """Cria tubo de pa a pb e aplica diâmetro."""
    novo = Pipe.Create(doc, sys_id, pt_id, lvl_id, pa, pb)
    _set_diam(novo, diam_ft)
    return novo


def _elbow(doc, c1, c2):
    """Cria joelho entre c1 e c2. Falha silenciosa."""
    try:
        doc.Create.NewElbowFitting(c1, c2)
        return True
    except Exception:
        return False


def _tee(doc, pipe_ref, P_target, conn_branch):
    """
    Cria tê no corpo de pipe_ref em P_target, conectando conn_branch como ramal.
    """
    def _dir(c):
        try:
            return c.CoordinateSystem.BasisZ
        except Exception:
            return XYZ(0, 0, 1)

    new_id   = PlumbingUtils.BreakCurve(doc, pipe_ref.Id, P_target)
    pipe_sec = doc.GetElement(new_id)
    c_r1     = _conn_near(pipe_ref, P_target)
    c_r2     = _conn_near(pipe_sec,  P_target)
    if not (c_r1 and c_r2):
        return False
    conns = [c_r1, c_r2, conn_branch]
    melhor, par = -1.0, (0, 1)
    for i in range(3):
        for j in range(i + 1, 3):
            d = abs(_dir(conns[i]).DotProduct(_dir(conns[j])))
            if d > melhor:
                melhor, par = d, (i, j)
    run  = [conns[par[0]], conns[par[1]]]
    rest = [c for k, c in enumerate(conns) if k not in par]
    try:
        doc.Create.NewTeeFitting(run[0], run[1], rest[0])
        return True
    except Exception:
        return False


def _global_pt(ref):
    try:
        return ref.GlobalPoint
    except Exception:
        return None


class _FiltroPipe(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, Pipe)
    def AllowReference(self, r, p):
        return True


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

def run(doc, uidoc, output):
    # ── Clique 1: ponta do PIPE_DESC ────────────────────────────────────────
    try:
        ref1         = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroPipe(),
            u"[1/2] Clique em uma PONTA do tubo desconectado"
        )
        pipe_desc    = doc.GetElement(ref1.ElementId)
        pt_click_desc = _global_pt(ref1)
    except Exception:
        pyscript.exit()

    # ── Clique 2: PIPE_REF (corpo ou ponta) ─────────────────────────────────
    try:
        ref2         = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroPipe(),
            u"[2/2] Clique no tubo referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref2.ElementId)
        pt_click_ref = _global_pt(ref2)
    except Exception:
        pyscript.exit()

    if pipe_ref.Id == pipe_desc.Id:
        forms.alert(u"Os dois tubos selecionados são o mesmo elemento.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output)


# ============================================================================
# LÓGICA DE CONEXÃO
# ============================================================================

def _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output):

    # ── Endpoint de PIPE_DESC selecionado pelo clique ────────────────────────
    if pt_click_desc is not None:
        conn_desc = _conn_nearest(pipe_desc, pt_click_desc)
    else:
        loc_fb = pipe_ref.Location.Curve
        mid_fb = XYZ((loc_fb.GetEndPoint(0).X + loc_fb.GetEndPoint(1).X) / 2,
                     (loc_fb.GetEndPoint(0).Y + loc_fb.GetEndPoint(1).Y) / 2,
                     (loc_fb.GetEndPoint(0).Z + loc_fb.GetEndPoint(1).Z) / 2)
        conn_desc = _conn_nearest(pipe_desc, mid_fb)

    if conn_desc is None:
        forms.alert(u"Não foi possível encontrar conector no tubo desconectado.",
                    title=u"Fire Utils", warn_icon=True)
        return

    if conn_desc.IsConnected:
        forms.alert(
            u"A ponta selecionada do tubo já está conectada a outro elemento.\n"
            u"Selecione uma ponta livre (sem conexão).",
            title=u"Fire Utils – Ponta Ocupada",
            warn_icon=True
        )
        return

    P_start = conn_desc.Origin

    # ── Geometria de PIPE_REF ────────────────────────────────────────────────
    loc_ref = pipe_ref.Location.Curve
    pt_A    = loc_ref.GetEndPoint(0)
    pt_B    = loc_ref.GetEndPoint(1)
    z_ref   = (pt_A.Z + pt_B.Z) / 2.0
    d_ref   = (pt_B - pt_A).Normalize()

    # ── Modo de conexão: ponta ou corpo? ────────────────────────────────────
    if pt_click_ref is not None:
        da = pt_click_ref.DistanceTo(pt_A)
        db = pt_click_ref.DistanceTo(pt_B)
        clicou_ponta = da < TOL_PONTA_REF or db < TOL_PONTA_REF
        pt_endpoint  = pt_A if da < db else pt_B
    else:
        clicou_ponta = False
        pt_endpoint  = None

    # ── Etapa 1: extensão direta ─────────────────────────────────────────────
    # Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref,
    # apenas estende e conecta sem criar tubos extras.
    loc_desc = pipe_desc.Location.Curve
    p_desc_0 = loc_desc.GetEndPoint(0)
    p_desc_1 = loc_desc.GetEndPoint(1)
    L_desc   = p_desc_0.DistanceTo(p_desc_1)
    if L_desc > TOL:
        P_other = (p_desc_1 if p_desc_0.DistanceTo(P_start) < p_desc_1.DistanceTo(P_start)
                   else p_desc_0)
        d_ext = XYZ(
            (P_start.X - P_other.X) / L_desc,
            (P_start.Y - P_other.Y) / L_desc,
            (P_start.Z - P_other.Z) / L_desc,
        )
        resultado = _intersecao_com_pipe(P_start, d_ext, pt_A, pt_B)
        if resultado is not None:
            P_int, t_ext, em_ponta_int = resultado
            with Transaction(doc, u"FireUtils - Conectar Tubo") as t:
                t.Start()
                try:
                    if t_ext > TOL:
                        pipe_desc.Location.Curve = Line.CreateBound(P_other, P_int)
                        doc.Regenerate()
                    conn_end = _conn_near(pipe_desc, P_int)
                    if conn_end:
                        if em_ponta_int:
                            at_end_a = P_int.DistanceTo(pt_A) < _to_ft(0.05)
                            pt_ponta = pt_A if at_end_a else pt_B
                            c_ponta  = _conn_near(pipe_ref, pt_ponta)
                            if c_ponta:
                                _elbow(doc, c_ponta, conn_end)
                        else:
                            _tee(doc, pipe_ref, P_int, conn_end)
                    t.Commit()
                except Exception as ex:
                    t.RollBack()
                    forms.alert(
                        u"Erro ao estender o tubo:\n{}".format(str(ex)),
                        title=u"Fire Utils – Erro",
                        warn_icon=True)
            return

        # Caso colinear: tubos alinhados ponta a ponta
        dot_par = abs(d_ext.DotProduct(d_ref))
        if dot_par > 0.99:
            t_a = (pt_A - P_start).DotProduct(d_ext)
            t_b = (pt_B - P_start).DotProduct(d_ext)
            candidates = []
            if t_a >= -TOL:
                candidates.append((t_a, pt_A))
            if t_b >= -TOL:
                candidates.append((t_b, pt_B))
            if candidates:
                _, pt_join = min(candidates, key=lambda x: x[0])
                with Transaction(doc, u"FireUtils - Conectar Tubo") as tx:
                    tx.Start()
                    try:
                        if P_start.DistanceTo(pt_join) > TOL:
                            pipe_desc.Location.Curve = Line.CreateBound(P_other, pt_join)
                            doc.Regenerate()
                        conn_end = _conn_near(pipe_desc, pt_join)
                        c_ep     = _conn_near(pipe_ref,  pt_join)
                        if conn_end and c_ep:
                            conn_end.ConnectTo(c_ep)
                        tx.Commit()
                    except Exception as ex:
                        tx.RollBack()
                        forms.alert(
                            u"Erro ao conectar tubos colineares:\n{}".format(str(ex)),
                            title=u"Fire Utils – Erro",
                            warn_icon=True)
                return

    # ── Etapa 2: roteamento em L ─────────────────────────────────────────────
    P_knee    = XYZ(P_start.X, P_start.Y, z_ref)
    dz        = abs(P_start.Z - z_ref)
    need_vert = dz > TOL_DZ
    desc_vert = _pipe_is_vertical(pipe_desc)

    if not clicou_ponta:
        P_target   = _projetar_segmento(P_knee, pt_A, pt_B)
        dist_horiz = P_knee.DistanceTo(P_target)
        need_horiz = dist_horiz > TOL_SEG
        if not need_horiz:
            P_target = P_knee
    else:
        P_target   = None
        need_horiz = True

    if not need_vert and not need_horiz and not clicou_ponta:
        forms.alert(u"Os tubos já estão alinhados — nenhuma conexão necessária.",
                    title=u"Fire Utils")
        return

    pt_id, sys_id, _,      diam_ft = _pipe_params(doc, pipe_desc)
    _,     _,      lvl_id, _       = _pipe_params(doc, pipe_ref)

    with Transaction(doc, u"FireUtils - Conectar Tubo") as t:
        t.Start()
        try:
            _elbows_pend = []
            conn_knee    = None

            # ── SEÇÃO VERTICAL ────────────────────────────────────────────────
            if not need_vert:
                conn_knee = _conn_near(pipe_desc, P_start)

            elif desc_vert:
                # pipe_desc vertical: estende a curva até z_ref
                c  = pipe_desc.Location.Curve
                p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
                if p0.DistanceTo(P_start) < p1.DistanceTo(P_start):
                    pipe_desc.Location.Curve = Line.CreateBound(
                        XYZ(p0.X, p0.Y, z_ref), p1)
                else:
                    pipe_desc.Location.Curve = Line.CreateBound(
                        p0, XYZ(p1.X, p1.Y, z_ref))
                doc.Regenerate()
                conn_knee = _conn_near(pipe_desc, P_knee)

            else:
                # pipe_desc horizontal: cria tubo vertical P_start → P_knee
                pipe_vert = _mk_pipe(doc, P_start, P_knee, pt_id, sys_id, lvl_id, diam_ft)
                conn_knee = _conn_near(pipe_vert, P_knee)
                c_d       = _conn_near(pipe_desc,  P_start)
                c_v       = _conn_near(pipe_vert,  P_start)
                _elbows_pend.append((c_d, c_v))

            if conn_knee is None:
                forms.alert(
                    u"Não foi possível localizar o conector em P_knee.",
                    title=u"Fire Utils", warn_icon=True)
                t.RollBack()
                return

            # ── SEÇÃO HORIZONTAL — MODO CORPO (Tê) ──────────────────────────
            if not clicou_ponta:
                if need_horiz:
                    pipe_h      = _mk_pipe(doc, P_knee, P_target, pt_id, sys_id, lvl_id, diam_ft)
                    c_hk        = _conn_near(pipe_h, P_knee)
                    conn_branch = _conn_near(pipe_h, P_target)
                    _elbows_pend.append((conn_knee, c_hk))
                else:
                    conn_branch = conn_knee

                if conn_branch:
                    doc.Regenerate()
                    _TOL_PONTA_GEO = _to_ft(0.05)
                    at_end_a = P_target.DistanceTo(pt_A) < _TOL_PONTA_GEO
                    at_end_b = P_target.DistanceTo(pt_B) < _TOL_PONTA_GEO
                    if at_end_a or at_end_b:
                        pt_ponta = pt_A if at_end_a else pt_B
                        c_ponta  = _conn_near(pipe_ref, pt_ponta)
                        if c_ponta:
                            ok = _elbow(doc, c_ponta, conn_branch)
                            if not ok:
                                output.print_md(u"| Joelho na ponta | **falhou** |")
                    else:
                        ok = _tee(doc, pipe_ref, P_target, conn_branch)
                        if not ok:
                            output.print_md(u"| Tê | **falhou** — verifique se há família de tê carregada |")

                    doc.Regenerate()
                    for c1, c2 in _elbows_pend:
                        _elbow(doc, c1, c2)

            # ── SEÇÃO HORIZONTAL — MODO PONTA (joelhos) ─────────────────────
            else:
                P_end = pt_endpoint
                P_mid, needs_s1, needs_s2 = _rota_ate_endpoint(P_knee, P_end, d_ref)
                conn_cur = conn_knee

                if needs_s1:
                    seg1   = _mk_pipe(doc, P_knee, P_mid, pt_id, sys_id, lvl_id, diam_ft)
                    c_s1_k = _conn_near(seg1, P_knee)
                    c_s1_m = _conn_near(seg1, P_mid)
                    _elbows_pend.append((conn_cur, c_s1_k))
                    conn_cur = c_s1_m

                if needs_s2:
                    seg2   = _mk_pipe(doc, P_mid, P_end, pt_id, sys_id, lvl_id, diam_ft)
                    c_s2_m = _conn_near(seg2, P_mid)
                    c_s2_e = _conn_near(seg2, P_end)
                    _elbows_pend.append((conn_cur, c_s2_m))
                    conn_cur = c_s2_e

                doc.Regenerate()
                c_ref_end = _conn_near(pipe_ref, P_end)
                if c_ref_end and conn_cur:
                    ok = _elbow(doc, c_ref_end, conn_cur)
                    if not ok:
                        output.print_md(
                            u"| Joelho na ponta | **falhou** — "
                            u"verifique se o endpoint de pipe_ref está livre |")

                doc.Regenerate()
                for c1, c2 in _elbows_pend:
                    _elbow(doc, c1, c2)

            t.Commit()

        except Exception as e:
            t.RollBack()
            forms.alert(
                u"Erro ao criar a conexão:\n{}".format(str(e)),
                title=u"Fire Utils – Erro",
                warn_icon=True)
