# -*- coding: utf-8 -*-
"""
connect_shelter_core_preview.py — Fire Utils · lib/

Versão "preview" de connect_shelter_core.py — conecta um abrigo de hidrante
existente à rede de tubulação, mas aplica a válvula e o stub ao projeto
IMEDIATAMENTE após o clique de direção, antes de rotear até o tubo principal.
Assim o usuário vê a posição real no modelo antes de comprometer com a conexão
final.

Sem caixas de diálogo de confirmação: o "confirmar" é o próprio clique nativo
do Revit. Se o usuário pressionar ESC no passo de confirmação, apenas o
roteamento final é cancelado — a válvula e o stub já aplicados permanecem no
projeto (desfaça com Ctrl+Z se não gostar da posição).

Fluxo de cliques
----------------
  1. Selecionar o abrigo de referência
  2. Clicar para indicar a direção de saída do ramal (snap 90°, relativo à face do abrigo)
     → válvula + stub são criados e APLICADOS ao projeto aqui, sem pausa/diálogo
       (tipo/sistema de tubulação: padrão do projeto — o tubo de referência
       ainda não foi escolhido nesta etapa)
  3. Clicar no tubo de referência — corpo → Tê  |  ponta → joelhos em L
  4. Clique de confirmação (em qualquer ponto) para rotear até o tubo principal
     → ESC neste passo cancela só o roteamento; válvula/stub continuam no projeto

Todo o roteamento até o tubo de referência é delegado a connect_pipe._conectar,
para que melhorias futuras no algoritmo de roteamento beneficiem este botão automaticamente.
Os segmentos de roteamento herdam tipo/sistema do próprio stub (ver connect_pipe._conectar),
não do tubo de referência — por isso a ordem dos cliques 2/3 não afeta o resultado.

Nível obtido diretamente do abrigo — sem prompt ao usuário.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, UnitUtils,
    ElementTransformUtils, FamilyInstance,
    FilteredElementCollector, ElementId,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipeType, PipingSystemType
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
from connect_pipe import _conectar, _FiltroPipe


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
# HELPER — tipo/sistema de tubulação padrão (tubo de referência ainda não escolhido)
# ===========================================================================

def _pipe_params_padrao(doc):
    """
    Primeiro PipeType e PipingSystemType encontrados no projeto.
    Usado para o stub quando o tubo de referência ainda não foi selecionado
    (mesmo fallback já usado em outros pontos do Fire Utils).
    """
    pipe_type_id = ElementId.InvalidElementId
    tipos_pipe = FilteredElementCollector(doc).OfClass(PipeType).ToElements()
    if tipos_pipe:
        pipe_type_id = tipos_pipe[0].Id

    sys_type_id = ElementId.InvalidElementId
    tipos_sys = FilteredElementCollector(doc).OfClass(PipingSystemType).ToElements()
    if tipos_sys:
        sys_type_id = tipos_sys[0].Id

    return pipe_type_id, sys_type_id


# ===========================================================================
# PONTO DE ENTRADA
# ===========================================================================

def conectar_abrigo_preview(doc, uidoc, output):

    # ── Família da válvula ───────────────────────────────────────────────
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # ── Clique 1: abrigo ────────────────────────────────────────────────
    try:
        ref    = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroAbrigo(),
            u"[1/4] Selecione o abrigo de hidrante"
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
            u"[2/4] Clique para indicar a direção de saída do ramal"
        )
    except Exception:
        pyscript.exit()

    dir_pipe = _snap_direcao(pt_abrigo, pt_dir, dir_face)

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

    # Tubo de referência ainda não foi escolhido — usa tipo/sistema padrão do projeto
    pipe_type_id, sys_type_id = _pipe_params_padrao(doc)

    # ── Transação: válvula + stub — APLICADA IMEDIATAMENTE ────────────────
    # Sem diálogo de confirmação: o usuário já vê o resultado no modelo aqui.
    # Se não gostar da posição, pode desfazer com Ctrl+Z e rodar de novo.
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

    # ── Clique 3: tubo de referência ────────────────────────────────────
    try:
        ref_p        = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipe(),
            u"[3/4] Clique no tubo de referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref_p.ElementId)
        pt_click_ref = ref_p.GlobalPoint
    except Exception:
        pyscript.exit()

    # ── Clique 4: confirmação nativa (sem diálogo) ─────────────────────────
    # Válvula e stub já estão aplicados no projeto — visíveis para conferência.
    # Qualquer clique aqui prossegue com a conexão ao tubo principal;
    # ESC cancela apenas este roteamento final (válvula/stub continuam no projeto).
    try:
        uidoc.Selection.PickPoint(
            u"[4/4] Posição aplicada. Clique para conectar ao tubo principal "
            u"(ESC cancela só a conexão final — válvula/stub ficam no projeto)"
        )
    except Exception:
        pyscript.exit()

    # ── Roteamento delegado a connect_pipe ───────────────────────────────
    # pt_stub_end identifica a ponta livre do stub para _conectar.
    # pt_click_ref distingue corpo (Tê) vs ponta (joelho) do pipe_ref.
    _conectar(doc, tubo_stub, pipe_ref, pt_stub_end, pt_click_ref, output)
