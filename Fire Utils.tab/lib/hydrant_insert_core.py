# -*- coding: utf-8 -*-
"""
hydrant_insert_core.py — Fire Utils · lib/
Lógica central de inserção da coluna de hidrante.

Chamado pelos botões:
  - Inserir Hidrante           → run(doc, uidoc, output, forcar_nivel=False)
  - Inserir Hidrante por Nível → run(doc, uidoc, output, forcar_nivel=True)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, UnitUtils,
    BuiltInParameter, FilteredElementCollector,
    ElementId, LocationCurve, ElementTransformUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_m(v):  return UnitUtils.ConvertFromInternalUnits(v, UnitTypeId.Meters)
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_m(v):  return UnitUtils.ConvertFromInternalUnits(v, DisplayUnitType.DUT_METERS)
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

from hydrant_family import garantir_valvula
from hydrant_level  import get_nivel

ALTURA_VALVULA_M = 1.30
COMP_HORIZ_M     = 0.20
TOL              = 1e-4


# ===========================================================================
# HELPERS
# ===========================================================================

def _projetar_no_eixo(pt, pt_a, pt_b):
    ab = pt_b - pt_a
    ab_len = ab.GetLength()
    if ab_len < TOL:
        return pt_a
    ab_norm = ab.Normalize()
    t = max(0.0, min(ab_len, (pt - pt_a).DotProduct(ab_norm)))
    return XYZ(pt_a.X + ab_norm.X * t,
               pt_a.Y + ab_norm.Y * t,
               pt_a.Z + ab_norm.Z * t)


def _get_diametro_ft(pipe):
    for bip in [BuiltInParameter.RBS_PIPE_OUTER_DIAMETER,
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM]:
        try:
            p = pipe.get_Parameter(bip)
            if p and p.AsDouble() > 0:
                return p.AsDouble()
        except Exception:
            pass
    return _to_ft(0.065)


def _setar_diametro_ft(pipe, d_ft):
    for bip in [BuiltInParameter.RBS_PIPE_OUTER_DIAMETER,
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM]:
        try:
            p = pipe.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(d_ft)
                return True
        except Exception:
            pass
    return False


def _direcao_horizontal(pipe):
    loc = pipe.Location
    if isinstance(loc, LocationCurve):
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        length = math.sqrt(dx * dx + dy * dy)
        if length > TOL:
            return XYZ(dx / length, dy / length, 0.0)
    return XYZ(1.0, 0.0, 0.0)


def _direita_de(d):
    return XYZ(d.Y, -d.X, 0.0)


def _angulo_entre(v_de, v_para):
    return math.atan2(v_para.Y, v_para.X) - math.atan2(v_de.Y, v_de.X)


class _FiltroPipe(ISelectionFilter):
    def AllowElement(self, e):       return isinstance(e, Pipe)
    def AllowReference(self, r, p):  return True


# ===========================================================================
# FUNÇÃO PRINCIPAL
# ===========================================================================

def run(doc, uidoc, output, forcar_nivel=False):
    """
    forcar_nivel=False  → nível obtido da vista ativa (seletor como fallback)
    forcar_nivel=True   → seletor sempre exibido antes de selecionar o tubo
    """

    # ── Etapa 1 — Garantir família da válvula ────────────────────────────
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # ── Etapa 2 — Nível (se forçado, pergunta ANTES do tubo) ─────────────
    nivel_pre = None
    if forcar_nivel:
        nivel_pre, erro = get_nivel(doc, uidoc, forcar_selecao=True)
        if not nivel_pre:
            pyscript.exit()

    # ── Etapa 3 — Selecionar ponto no tubo ───────────────────────────────
    msg_nivel = (u" Nível: {}.".format(nivel_pre.Name)
                 if nivel_pre else
                 u" O nível será detectado da vista ativa.")

    forms.alert(
        u"Clique num ponto do tubo de onde a coluna de hidrante deve sair.\n"
        u"O trecho vertical vai até {:.2f} m acima do piso.{}".format(
            ALTURA_VALVULA_M, msg_nivel),
        title=u"Fire Utils – Inserir Hidrante"
    )

    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipe(),
            u"Selecione um ponto no tubo principal"
        )
    except Exception:
        pyscript.exit()

    tubo_principal = doc.GetElement(ref.ElementId)
    if not isinstance(tubo_principal, Pipe):
        forms.alert(u"Elemento selecionado não é um tubo.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    pt_clique = ref.GlobalPoint

    # ── Etapa 4 — Nível ──────────────────────────────────────────────────
    if forcar_nivel:
        nivel = nivel_pre
    else:
        nivel, erro = get_nivel(doc, uidoc, forcar_selecao=False)
        if not nivel:
            pyscript.exit()

    # ── Etapa 5 — Geometria da coluna ────────────────────────────────────
    dir_principal = _direcao_horizontal(tubo_principal)
    dir_saida     = _direita_de(dir_principal)
    comp_horiz_ft = _to_ft(COMP_HORIZ_M)

    loc_p = tubo_principal.Location
    pt_A  = loc_p.Curve.GetEndPoint(0)
    pt_B  = loc_p.Curve.GetEndPoint(1)

    pt_ramal  = _projetar_no_eixo(pt_clique, pt_A, pt_B)
    z_tubo    = pt_ramal.Z
    z_valvula = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)

    pt_joelho  = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
    pt_valvula = XYZ(
        pt_joelho.X + dir_saida.X * comp_horiz_ft,
        pt_joelho.Y + dir_saida.Y * comp_horiz_ft,
        pt_joelho.Z
    )

    tem_vertical = abs(z_valvula - z_tubo) > TOL

    # ── Etapa 6 — Parâmetros herdados do tubo ────────────────────────────
    pipe_type_id = tubo_principal.GetTypeId()
    level_id     = nivel.Id
    diam_ft      = _get_diametro_ft(tubo_principal)

    sys_type_id = ElementId.InvalidElementId
    try:
        mep_sys = tubo_principal.MEPSystem
        if mep_sys:
            sys_type_id = mep_sys.GetTypeId()
    except Exception:
        pass

    if sys_type_id == ElementId.InvalidElementId:
        try:
            tipos = FilteredElementCollector(doc).OfClass(PipingSystemType).ToElements()
            if tipos:
                sys_type_id = tipos[0].Id
        except Exception:
            pass

    # ── Etapa 7 — Criar elementos (transação única) ───────────────────────
    with Transaction(doc, u"FireUtils - Inserir Hidrante") as t:
        t.Start()
        try:
            # — Tubo vertical —
            if tem_vertical:
                tubo_vert = Pipe.Create(
                    doc, sys_type_id, pipe_type_id, level_id,
                    pt_ramal, pt_joelho
                )
                _setar_diametro_ft(tubo_vert, diam_ft)
            else:
                tubo_vert = None

            # — Tubo horizontal —
            tubo_horiz = Pipe.Create(
                doc, sys_type_id, pipe_type_id, level_id,
                pt_joelho, pt_valvula
            )
            _setar_diametro_ft(tubo_horiz, diam_ft)

            # — Válvula —
            valvula = doc.Create.NewFamilyInstance(
                pt_valvula, simbolo, nivel, StructuralType.NonStructural
            )

            angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_saida)
            if abs(angulo) > TOL:
                eixo_rot = Line.CreateBound(
                    pt_valvula,
                    XYZ(pt_valvula.X, pt_valvula.Y, pt_valvula.Z + 1.0)
                )
                ElementTransformUtils.RotateElement(doc, valvula.Id, eixo_rot, angulo)

            t.Commit()

        except Exception as e:
            t.RollBack()
            forms.alert(
                u"Erro ao criar a coluna de hidrante:\n{}".format(str(e)),
                title=u"Fire Utils – Erro",
                warn_icon=True
            )
            pyscript.exit()

    # ── Etapa 8 — Relatório ───────────────────────────────────────────────
    output.print_md(u"# Fire Utils — Inserir Hidrante")
    output.print_md(u"---")
    output.print_md(u"### ✔ Coluna de hidrante criada")
    output.print_md(u"| Item | Valor |")
    output.print_md(u"|---|---|")
    if tem_vertical:
        dz = _to_m(abs(z_valvula - z_tubo))
        sentido = u"sobe" if z_valvula > z_tubo else u"desce"
        output.print_md(u"| Trecho vertical ({}) | {:.0f} mm · {:.3f} m |".format(
            sentido, _to_m(diam_ft) * 1000, dz))
    else:
        output.print_md(u"| Trecho vertical | *não necessário* |")
    output.print_md(u"| Trecho horizontal | {:.0f} mm · {:.0f} mm |".format(
        _to_m(diam_ft) * 1000, COMP_HORIZ_M * 1000))
    output.print_md(u"| Elevação da válvula | {:.2f} m — nível `{}` |".format(
        ALTURA_VALVULA_M, nivel.Name))
    output.print_md(u"| Válvula | {} |".format(simbolo.Family.Name))
