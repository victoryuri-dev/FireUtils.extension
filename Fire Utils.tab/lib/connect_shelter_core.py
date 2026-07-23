# -*- coding: utf-8 -*-
"""
connect_shelter_core.py — Fire Utils · lib/

Conecta um abrigo de hidrante existente à rede de tubulação.

Fluxo de cliques
----------------
  1. Selecionar o abrigo de referência
  2. Clicar para indicar a direção de saída do ramal (snap 90°, relativo à face do abrigo)
  3. Clicar no tubo de referência — corpo → Tê  |  ponta → joelhos em L

O script cria:
  - Válvula na posição XY do abrigo, Z = nível do abrigo + 1,30 m
  - Tubo horizontal stub (20 cm) saindo da válvula na direção selecionada

Todo o roteamento até o tubo de referência é delegado a connect_pipe._conectar,
para que melhorias futuras no algoritmo de roteamento beneficiem este botão automaticamente.

Nível obtido diretamente do abrigo — sem prompt ao usuário.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, UnitUtils,
    ElementTransformUtils, FamilyInstance,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

from hydrant_family      import garantir_valvula
from shelter_family      import NOME_FAMILIA_ABRIGO
from hydrant_insert_core import (
    ALTURA_VALVULA_M, COMP_HORIZ_M, DIAM_RAMAL_M, TOL,
    _angulo_entre, _conector_mais_proximo, _setar_diametro_ft,
)
from connect_pipe import _conectar, _FiltroPipe, _pipe_params


# ===========================================================================
# FILTRO — abrigo de hidrante
# ===========================================================================

class _FiltroAbrigo(ISelectionFilter):
    def AllowElement(self, e):
        if isinstance(e, FamilyInstance):
            try:
                return e.Symbol.Family.Name == NOME_FAMILIA_ABRIGO
            except Exception:
                pass
        return False
    def AllowReference(self, r, p): return True


# ===========================================================================
# HELPER — snap de direção
# ===========================================================================

def _snap_direcao(pt_ref, pt_click, dir_face):
    """
    Restringe a direção a APENAS esquerda ou direita da face do abrigo
    (perpendicular ao FacingOrientation, paralelo ao plano da face).
    """
    dx   = pt_click.X - pt_ref.X
    dy   = pt_click.Y - pt_ref.Y
    dlen = math.sqrt(dx * dx + dy * dy)
    # Perpendiculares à face (esquerda / direita)
    dir_dir  = XYZ(-dir_face.Y,  dir_face.X, 0.0)   # 90° CCW da face
    dir_esq  = XYZ( dir_face.Y, -dir_face.X, 0.0)   # 90° CW  da face
    if dlen < 1e-3:
        return dir_dir                                # fallback: direita
    v = XYZ(dx / dlen, dy / dlen, 0.0)
    return max([dir_dir, dir_esq], key=lambda d: v.DotProduct(d))


# ===========================================================================
# PONTO DE ENTRADA
# ===========================================================================

def conectar_abrigo(doc, uidoc, output):

    # ── Família da válvula ───────────────────────────────────────────────
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # ── Clique 1: abrigo ────────────────────────────────────────────────
    try:
        ref    = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroAbrigo(),
            u"Selecione o abrigo de hidrante"
        )
        abrigo = doc.GetElement(ref.ElementId)
    except Exception:
        pyscript.exit()

    try:
        pt_abrigo = abrigo.Location.Point
    except Exception:
        forms.alert(u"Não foi possível obter a posição do abrigo.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    # Nível lido do próprio abrigo — sem prompt ao usuário
    nivel = doc.GetElement(abrigo.LevelId)
    if nivel is None:
        forms.alert(u"Não foi possível determinar o nível do abrigo.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    try:
        face     = abrigo.FacingOrientation
        dir_face = XYZ(face.X, face.Y, 0.0)
    except Exception:
        dir_face = XYZ(0.0, 1.0, 0.0)

    # ── Clique 2: direção do ramal ─────────────────────────────────────
    try:
        pt_dir = uidoc.Selection.PickPoint(
            u"Clique para indicar a direção de saída do ramal"
        )
    except Exception:
        pyscript.exit()

    dir_pipe = _snap_direcao(pt_abrigo, pt_dir, dir_face)

    # ── Clique 3: tubo de referência ────────────────────────────────────
    try:
        ref_p        = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipe(),
            u"Clique no tubo de referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref_p.ElementId)
        pt_click_ref = ref_p.GlobalPoint
    except Exception:
        pyscript.exit()

    # ── Geometria do stub ────────────────────────────────────────────────
    z_val   = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)
    comp_ft = _to_ft(COMP_HORIZ_M)
    diam_ft = _to_ft(DIAM_RAMAL_M)

    # Posição da válvula: inverso do offset de _calcular_pt_abrigo.
    # No fluxo original: pt_abrigo = pt_valvula + 0.18·dir_saida − 0.085·dir_face
    # Aqui dir_pipe = −dir_saida (aponta de válvula→rede), logo:
    #   pt_valvula = pt_abrigo + 0.18·dir_pipe + 0.085·dir_face
    pt_valvula = XYZ(
        pt_abrigo.X + _to_ft(0.18) * dir_pipe.X - _to_ft(0.085) * dir_face.X,
        pt_abrigo.Y + _to_ft(0.18) * dir_pipe.Y - _to_ft(0.085) * dir_face.Y,
        z_val,
    )

    pt_stub_end = XYZ(
        pt_valvula.X + dir_pipe.X * comp_ft,
        pt_valvula.Y + dir_pipe.Y * comp_ft,
        z_val,
    )

    # Herda tipo e sistema do tubo de referência
    pipe_type_id, sys_type_id, _, _ = _pipe_params(doc, pipe_ref)

    # ── Transação: válvula + stub ────────────────────────────────────────
    tubo_stub = None
    with Transaction(doc, u"FireUtils - Válvula e Stub do Abrigo") as t:
        t.Start()
        try:
            tubo_stub = Pipe.Create(
                doc, sys_type_id, pipe_type_id, nivel.Id,
                pt_valvula, pt_stub_end
            )
            _setar_diametro_ft(tubo_stub, diam_ft)

            valvula = doc.Create.NewFamilyInstance(
                pt_valvula, simbolo, nivel, StructuralType.NonStructural
            )

            # Rotação: + π porque dir_pipe aponta para a rede;
            # a face da válvula fica voltada para o lado do abrigo
            angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_pipe) + math.pi
            if abs(angulo) > TOL:
                eixo = Line.CreateBound(
                    pt_valvula,
                    XYZ(pt_valvula.X, pt_valvula.Y, pt_valvula.Z + 1.0)
                )
                ElementTransformUtils.RotateElement(doc, valvula.Id, eixo, angulo)

            doc.Regenerate()

            # Conectar válvula ao conector próximo do stub em pt_valvula
            best_d, conn_stub_val = float('inf'), None
            for c in tubo_stub.ConnectorManager.Connectors:
                d = c.Origin.DistanceTo(pt_valvula)
                if d < best_d:
                    best_d, conn_stub_val = d, c

            if conn_stub_val:
                conn_val = _conector_mais_proximo(valvula, pt_valvula)
                if conn_val:
                    desl = conn_stub_val.Origin - conn_val.Origin
                    if desl.GetLength() > TOL:
                        ElementTransformUtils.MoveElement(doc, valvula.Id, desl)
                    try:
                        conn_stub_val.ConnectTo(conn_val)
                    except Exception:
                        pass

            t.Commit()
        except Exception as e:
            t.RollBack()
            forms.alert(
                u"Erro ao criar válvula e stub:\n{}".format(str(e)),
                title=u"Fire Utils – Erro", warn_icon=True
            )
            pyscript.exit()

    # ── Roteamento delegado a connect_pipe ───────────────────────────────
    # pt_stub_end identifica a ponta livre do stub para _conectar.
    # pt_click_ref distingue corpo (Tê) vs ponta (joelho) do pipe_ref.
    _conectar(doc, tubo_stub, pipe_ref, pt_stub_end, pt_click_ref, output)
