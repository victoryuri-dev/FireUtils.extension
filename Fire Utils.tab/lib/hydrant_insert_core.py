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
    FamilyInstance,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType, PlumbingUtils
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
DIAM_RAMAL_M     = 0.065
TOL              = 1e-4
TOL_FIM          = 0.05   # metros — distância máxima ao endpoint para ser "ponta"


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


def _pipe_is_vertical(pipe):
    loc = pipe.Location
    if isinstance(loc, LocationCurve):
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        dz = p1.Z - p0.Z
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length > TOL:
            return math.sqrt(dx*dx + dy*dy) / length < 0.1
    return False



def _angulo_entre(v_de, v_para):
    return math.atan2(v_para.Y, v_para.X) - math.atan2(v_de.Y, v_de.X)


def _get_connector_at(pipe, pt):
    for conn in pipe.ConnectorManager.Connectors:
        if conn.Origin.IsAlmostEqualTo(pt, TOL):
            return conn
    return None


def _get_connector_near(pipe, pt, max_dist_ft=0.2):
    """Como _get_connector_at mas com tolerância maior — útil após delete/BreakCurve."""
    best, best_dist = None, max_dist_ft
    for conn in pipe.ConnectorManager.Connectors:
        d = conn.Origin.DistanceTo(pt)
        if d < best_dist:
            best_dist = d
            best = conn
    return best


def _get_open_connector(pipe):
    """Retorna o primeiro conector livre (não conectado) do tubo."""
    for conn in pipe.ConnectorManager.Connectors:
        if not conn.IsConnected:
            return conn
    return None


def _get_far_connector(pipe, pt_near):
    """Retorna o conector de pipe mais distante de pt_near (= lado da válvula)."""
    best, max_dist = None, -1.0
    for conn in pipe.ConnectorManager.Connectors:
        d = conn.Origin.DistanceTo(pt_near)
        if d > max_dist:
            max_dist = d
            best = conn
    return best


def _ajustar_endpoint(pipe, old_pt, new_target):
    """
    Estende/encurta o endpoint do pipe mais próximo de old_pt até o ponto
    onde o EIXO do pipe passa mais perto de new_target.
    Preserva a direção original do pipe — nunca inclina.
    """
    try:
        loc   = pipe.Location
        curve = loc.Curve
        end0  = curve.GetEndPoint(0)
        end1  = curve.GetEndPoint(1)
        d     = end1 - end0
        L     = d.GetLength()
        if L < TOL:
            return
        dn = XYZ(d.X / L, d.Y / L, d.Z / L)

        # Projeta new_target no eixo infinito do pipe
        t = (new_target - end0).DotProduct(dn)
        pt_eixo = XYZ(end0.X + dn.X * t,
                      end0.Y + dn.Y * t,
                      end0.Z + dn.Z * t)

        if end0.DistanceTo(old_pt) < end1.DistanceTo(old_pt):
            if pt_eixo.DistanceTo(end1) > TOL:
                loc.Curve = Line.CreateBound(pt_eixo, end1)
        else:
            if pt_eixo.DistanceTo(end0) > TOL:
                loc.Curve = Line.CreateBound(end0, pt_eixo)
    except Exception:
        pass


def _pt_intersecao_pipes(pipe1, pipe2):
    """
    Ponto de interseção (ou mais próximo) entre os eixos infinitos de dois pipes.
    Retorna None se paralelos.
    """
    try:
        loc1 = pipe1.Location.Curve
        p1   = loc1.GetEndPoint(0)
        dv1  = loc1.GetEndPoint(1) - p1
        l1   = dv1.GetLength()
        if l1 < TOL: return None
        d1   = XYZ(dv1.X / l1, dv1.Y / l1, dv1.Z / l1)

        loc2 = pipe2.Location.Curve
        p2   = loc2.GetEndPoint(0)
        dv2  = loc2.GetEndPoint(1) - p2
        l2   = dv2.GetLength()
        if l2 < TOL: return None
        d2   = XYZ(dv2.X / l2, dv2.Y / l2, dv2.Z / l2)

        d1d2  = d1.DotProduct(d2)
        denom = 1.0 - d1d2 * d1d2
        if abs(denom) < 1e-9: return None   # paralelas

        b  = p2 - p1
        t  = (b.DotProduct(d1) - d1d2 * b.DotProduct(d2)) / denom
        return XYZ(p1.X + d1.X * t, p1.Y + d1.Y * t, p1.Z + d1.Z * t)
    except Exception:
        return None


def _conector_mais_proximo(familia_inst, pt):
    """Retorna o conector MEP da família mais próximo de pt."""
    try:
        mgr = familia_inst.MEPModel.ConnectorManager
    except Exception:
        return None
    melhor, menor_dist = None, float('inf')
    for conn in mgr.Connectors:
        d = conn.Origin.DistanceTo(pt)
        if d < menor_dist:
            menor_dist = d
            melhor = conn
    return melhor


def _dir_conn(conn):
    """Direção do conector (BasisZ do seu sistema de coordenadas)."""
    try:
        return conn.CoordinateSystem.BasisZ
    except Exception:
        return XYZ(0.0, 0.0, 1.0)


def _ordenar_conectores(conns):
    """
    Reordena N conectores para uso em NewTeeFitting / NewCrossFitting.
    Os dois primeiros da lista retornada são os mais colineares (through-run);
    os demais são branches.
    """
    if len(conns) < 2:
        return list(conns)
    melhor, par = -1.0, (0, 1)
    for i in range(len(conns)):
        for j in range(i + 1, len(conns)):
            d = abs(_dir_conn(conns[i]).DotProduct(_dir_conn(conns[j])))
            if d > melhor:
                melhor, par = d, (i, j)
    run = [conns[par[0]], conns[par[1]]]
    rest = [c for k, c in enumerate(conns) if k not in par]
    return run + rest


def _posicao_fitting(fitting):
    """Centro do fitting: tenta Location.Point, fallback média dos conectores."""
    try:
        return fitting.Location.Point
    except AttributeError:
        pass
    conns = list(fitting.MEPModel.ConnectorManager.Connectors)
    n = len(conns)
    if n:
        return XYZ(
            sum(c.Origin.X for c in conns) / n,
            sum(c.Origin.Y for c in conns) / n,
            sum(c.Origin.Z for c in conns) / n,
        )
    return None


def _dir_de_fitting(doc, fitting):
    """Direção horizontal do fitting: usa o primeiro Pipe conectado."""
    for conn in fitting.MEPModel.ConnectorManager.Connectors:
        for ref in conn.AllRefs:
            try:
                elem = doc.GetElement(ref.Owner.Id)
                if isinstance(elem, Pipe):
                    return _direcao_horizontal(elem)
            except Exception:
                pass
    return XYZ(1.0, 0.0, 0.0)


def _coletar_info_fitting(doc, fitting):
    """
    Para cada conector do fitting ligado a um Pipe, retorna
    (ElementId_do_pipe, XYZ_origem_do_conector).
    """
    info = []
    for conn in fitting.MEPModel.ConnectorManager.Connectors:
        for ref in conn.AllRefs:
            try:
                elem = doc.GetElement(ref.Owner.Id)
                if isinstance(elem, Pipe):
                    info.append((elem.Id,
                                 XYZ(conn.Origin.X, conn.Origin.Y, conn.Origin.Z)))
                    break
            except Exception:
                pass
    return info


class _FiltroElemento(ISelectionFilter):
    """Aceita Pipe ou FamilyInstance com 2-3 conectores MEP (Joelho / Tê)."""
    def AllowElement(self, e):
        if isinstance(e, Pipe):
            return True
        if isinstance(e, FamilyInstance):
            try:
                n = e.MEPModel.ConnectorManager.Connectors.Size
                return 2 <= n <= 3
            except Exception:
                pass
        return False
    def AllowReference(self, r, p): return True


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

    # PickPoint aceita qualquer clique — no vazio OU sobre elemento.
    # Em seguida, detectamos automaticamente se há tubo/fitting próximo.
    try:
        pt_clique = uidoc.Selection.PickPoint(
            u"Clique no tubo/fitting para conectar — ou em ponto livre para posicionar"
        )
    except Exception:
        pyscript.exit()

    # Raio de detecção automática (metros → pés internos)
    _RAIO_AUTO_FT = _to_ft(0.25)
    elem_sel      = None

    # Detecção em XY apenas — PickPoint retorna o Z do plano de corte da vista,
    # não o Z real do elemento, então distância 3D seria sempre grande demais.
    def _dist_xy_pt(a, b):
        return math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2)

    # 1) Pipes próximos: distância XY do clique ao eixo do pipe
    for _p in FilteredElementCollector(doc).OfClass(Pipe).ToElements():
        try:
            _loc = _p.Location.Curve
            _p0  = _loc.GetEndPoint(0)
            _p1  = _loc.GetEndPoint(1)
            # Projeta o clique no eixo do pipe usando o mesmo Z do pipe
            _pt_flat = XYZ(pt_clique.X, pt_clique.Y, _p0.Z)
            _proj    = _projetar_no_eixo(_pt_flat, _p0, _p1)
            if _dist_xy_pt(pt_clique, _proj) < _RAIO_AUTO_FT:
                elem_sel  = _p
                pt_clique = _proj   # ancora o clique no eixo do tubo
                break
        except Exception:
            pass

    # 2) Fittings próximos (joelho / tê — 2 ou 3 conectores) — distância XY
    if elem_sel is None:
        for _fi in FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements():
            try:
                _n = _fi.MEPModel.ConnectorManager.Connectors.Size
                if 2 <= _n <= 3:
                    _pos = _posicao_fitting(_fi)
                    if _pos and _dist_xy_pt(pt_clique, _pos) < _RAIO_AUTO_FT:
                        elem_sel = _fi
                        break
            except Exception:
                pass

    modo_livre = (elem_sel is None)

    try:
        pt_dir = uidoc.Selection.PickPoint(
            u"Clique para indicar a direção de saída do ramal"
        )
    except Exception:
        pyscript.exit()

    if modo_livre:
        eh_fitting         = False
        tubo_principal     = None
        fitting_principal  = None
        n_conns_fitting    = 0
        info_pipes_fitting = []
    else:
        eh_fitting = isinstance(elem_sel, FamilyInstance)
        if eh_fitting:
            fitting_principal  = elem_sel
            tubo_principal     = None
            n_conns_fitting    = fitting_principal.MEPModel.ConnectorManager.Connectors.Size
            if n_conns_fitting > 3:
                forms.alert(
                    u"Este fitting já tem {} conexões (cruzeta) e não pode receber mais ramais.".format(
                        n_conns_fitting),
                    title=u"Fire Utils", warn_icon=True)
                pyscript.exit()
            info_pipes_fitting = _coletar_info_fitting(doc, fitting_principal)
        elif isinstance(elem_sel, Pipe):
            tubo_principal     = elem_sel
            fitting_principal  = None
            n_conns_fitting    = 0
            info_pipes_fitting = []
        else:
            forms.alert(u"Elemento selecionado não é um tubo nem um fitting suportado.",
                        title=u"Fire Utils", warn_icon=True)
            pyscript.exit()

    # ── Etapa 4 — Nível ──────────────────────────────────────────────────
    if forcar_nivel:
        nivel = nivel_pre
    else:
        nivel, erro = get_nivel(doc, uidoc, forcar_selecao=False)
        if not nivel:
            pyscript.exit()

    # ── Etapa 5 — Geometria da coluna ────────────────────────────────────
    comp_horiz_ft = _to_ft(COMP_HORIZ_M)

    if modo_livre:
        dir_principal    = XYZ(1.0, 0.0, 0.0)   # referência para snapping global
        tubo_eh_vertical = False
        z_livre          = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)
        pt_ramal         = XYZ(pt_clique.X, pt_clique.Y, z_livre)
        pt_A = pt_B      = pt_ramal
    elif eh_fitting:
        dir_principal    = _dir_de_fitting(doc, fitting_principal)
        tubo_eh_vertical = False
        # pt_ramal = interseção real dos eixos dos pipes conectados (canto virtual).
        # Isso garante que todos os endpoints, após ajuste, estarão no mesmo ponto.
        # Tenta todos os pares de pipes para encontrar a interseção real dos eixos.
        # O par de passagem (through-run) é anti-paralelo → _pt_intersecao_pipes
        # retorna None. O par passagem+ramal dá a posição correta do centro do fitting.
        pt_ramal = None
        _pipes_info = [(doc.GetElement(pid), orig)
                       for pid, orig in info_pipes_fitting]
        _pipes_validos = [p for p, _ in _pipes_info if p]
        for _i in range(len(_pipes_validos)):
            for _j in range(_i + 1, len(_pipes_validos)):
                pt_ramal = _pt_intersecao_pipes(_pipes_validos[_i], _pipes_validos[_j])
                if pt_ramal is not None:
                    break
            if pt_ramal is not None:
                break
        if pt_ramal is None:
            pt_ramal = (info_pipes_fitting[0][1] if info_pipes_fitting
                        else _posicao_fitting(fitting_principal))
        if pt_ramal is None:
            forms.alert(u"Não foi possível determinar a posição do fitting.",
                        title=u"Fire Utils", warn_icon=True)
            pyscript.exit()
        pt_A = pt_B = pt_ramal
    else:
        dir_principal    = _direcao_horizontal(tubo_principal)
        tubo_eh_vertical = _pipe_is_vertical(tubo_principal)
        loc_p = tubo_principal.Location
        pt_A  = loc_p.Curve.GetEndPoint(0)
        pt_B  = loc_p.Curve.GetEndPoint(1)
        pt_ramal = _projetar_no_eixo(pt_clique, pt_A, pt_B)

    # Direção de saída: snapping a 90°.
    # Calcula o vetor bruto pt_ramal→pt_dir e escolhe a direção cardinal
    # (frente/trás/esquerda/direita em relação ao tubo) com maior projeção.
    _dx = pt_dir.X - pt_ramal.X
    _dy = pt_dir.Y - pt_ramal.Y
    _dlen = math.sqrt(_dx * _dx + _dy * _dy)
    if _dlen > _to_ft(0.05):
        _v = XYZ(_dx / _dlen, _dy / _dlen, 0.0)
        if modo_livre:
            _opcoes = [XYZ(1,0,0), XYZ(-1,0,0), XYZ(0,1,0), XYZ(0,-1,0)]
        else:
            _direita = _direita_de(dir_principal)
            _opcoes  = [dir_principal,
                        XYZ(-dir_principal.X, -dir_principal.Y, 0.0),
                        _direita,
                        XYZ(-_direita.X, -_direita.Y, 0.0)]
        dir_saida = max(_opcoes, key=lambda d: _v.DotProduct(d))
    else:
        dir_saida = XYZ(1,0,0) if modo_livre else _direita_de(dir_principal)

    z_tubo    = pt_ramal.Z
    z_valvula = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)

    if tubo_eh_vertical:
        # Tubo principal vertical: ramal sai a 1.30 m do piso, sem sub-tubo vertical
        pt_ramal     = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        pt_joelho    = pt_ramal
        tem_vertical = False
    else:
        pt_joelho    = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        tem_vertical = abs(z_valvula - z_tubo) > TOL

    pt_valvula = XYZ(
        pt_joelho.X + dir_saida.X * comp_horiz_ft,
        pt_joelho.Y + dir_saida.Y * comp_horiz_ft,
        pt_joelho.Z
    )

    # ── Etapa 6 — Parâmetros herdados do tubo ────────────────────────────
    level_id = nivel.Id
    diam_ft  = _to_ft(DIAM_RAMAL_M)

    # Para fittings, herda tipo e sistema do primeiro pipe conectado
    ref_pipe = (doc.GetElement(info_pipes_fitting[0][0])
                if eh_fitting and info_pipes_fitting else tubo_principal)

    pipe_type_id = ref_pipe.GetTypeId() if ref_pipe else ElementId.InvalidElementId

    if pipe_type_id == ElementId.InvalidElementId:
        try:
            from Autodesk.Revit.DB.Plumbing import PipeType
            tipos_pipe = FilteredElementCollector(doc).OfClass(PipeType).ToElements()
            if tipos_pipe:
                pipe_type_id = tipos_pipe[0].Id
        except Exception:
            pass

    sys_type_id = ElementId.InvalidElementId
    try:
        mep_sys = ref_pipe.MEPSystem if ref_pipe else None
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
            # — Fitting: deletar antes de criar os novos tubos —
            pipe_conns_livres = []
            if eh_fitting:
                doc.Delete(fitting_principal.Id)
                doc.Regenerate()
                # Estende cada pipe ao longo do seu próprio eixo até pt_ramal
                # (interseção real dos eixos). Nenhum pipe é inclinado.
                for (pid, origin) in info_pipes_fitting:
                    p = doc.GetElement(pid)
                    if p:
                        _ajustar_endpoint(p, origin, pt_ramal)
                doc.Regenerate()
                for (pid, _) in info_pipes_fitting:
                    p = doc.GetElement(pid)
                    if not p:
                        continue
                    # Após deletar o fitting, cada pipe tem exatamente um conector
                    # livre (o que estava no fitting). Pega o mais próximo de pt_ramal
                    # sem raio fixo — evita perder o ramal do Tê que pode estar
                    # ligeiramente fora da tolerância padrão de _get_connector_near.
                    melhor, menor_d = None, float('inf')
                    for conn in p.ConnectorManager.Connectors:
                        if not conn.IsConnected:
                            d = conn.Origin.DistanceTo(pt_ramal)
                            if d < menor_d:
                                menor_d, melhor = d, conn
                    if melhor:
                        pipe_conns_livres.append(melhor)

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

            # — Joelho entre vertical e horizontal —
            joelho_criado = False
            if tem_vertical and tubo_vert is not None:
                conn_v = _get_connector_at(tubo_vert,  pt_joelho)
                conn_h = _get_connector_at(tubo_horiz, pt_joelho)
                if conn_v and conn_h:
                    try:
                        doc.Create.NewElbowFitting(conn_v, conn_h)
                        joelho_criado = True
                    except Exception:
                        pass  # família de fitting ausente; tubos ficam sem fitting

            # — Válvula —
            # Usa IsConnected para encontrar a ponta livre do tubo_horiz
            # (evita depender de pt_valvula, que pode deslocar após o joelho).
            conn_tubo_fim = _get_far_connector(tubo_horiz, pt_ramal)
            if conn_tubo_fim is None:
                conn_tubo_fim = _get_connector_at(tubo_horiz, pt_valvula)

            pos_insercao = conn_tubo_fim.Origin if conn_tubo_fim else pt_valvula

            valvula = doc.Create.NewFamilyInstance(
                pos_insercao, simbolo, nivel, StructuralType.NonStructural
            )

            # Rotacionar para a direção do ramal
            angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_saida)
            if abs(angulo) > TOL:
                eixo_rot = Line.CreateBound(
                    pos_insercao,
                    XYZ(pos_insercao.X, pos_insercao.Y, pos_insercao.Z + 1.0)
                )
                ElementTransformUtils.RotateElement(doc, valvula.Id, eixo_rot, angulo)

            # Alinhar conector da válvula com o conector do tubo e conectar
            valvula_conectada = False
            if conn_tubo_fim:
                conn_val = _conector_mais_proximo(valvula, pos_insercao)
                if conn_val:
                    # Move a válvula para que seu conector coincida exatamente
                    deslocamento = conn_tubo_fim.Origin - conn_val.Origin
                    if deslocamento.GetLength() > TOL:
                        ElementTransformUtils.MoveElement(
                            doc, valvula.Id, deslocamento
                        )
                    try:
                        conn_tubo_fim.ConnectTo(conn_val)
                        valvula_conectada = True
                    except Exception:
                        pass

            # — Conexão ao elemento principal —
            doc.Regenerate()
            if tem_vertical:
                conn_ramal = _get_connector_near(tubo_vert, pt_ramal)
            else:
                conn_ramal = _get_connector_near(tubo_horiz, pt_ramal)

            conexao_principal = None
            conexao_erro      = u""
            if not modo_livre:
                if conn_ramal:
                    if eh_fitting:
                        # Recriar fitting baseado no total de conectores resultantes:
                        # pipes do fitting original (livres após delete) + novo ramal.
                        # Usa len(todos) — não n_conns_fitting — para suportar fittings
                        # com conectores parcialmente livres (ex.: tê com 1 ramal vago).
                        try:
                            todos = pipe_conns_livres + [conn_ramal]
                            ord_  = _ordenar_conectores(todos)
                            n     = len(todos)
                            _nomes_fitting = {2: u"joelho", 3: u"tê", 4: u"cruzeta"}
                            _orig = _nomes_fitting.get(n_conns_fitting, u"fitting")
                            if n == 2:
                                doc.Create.NewElbowFitting(ord_[0], ord_[1])
                            elif n == 3:
                                doc.Create.NewTeeFitting(ord_[0], ord_[1], ord_[2])
                            elif n == 4:
                                doc.Create.NewCrossFitting(
                                    ord_[0], ord_[1], ord_[2], ord_[3])
                            else:
                                conexao_erro = u"número de conectores não suportado ({})".format(n)
                            if not conexao_erro:
                                novo = _nomes_fitting.get(n, u"fitting")
                                conexao_principal = (u"{} (era {})".format(novo, _orig)
                                                     if novo != _orig else novo)
                        except Exception as e:
                            conexao_erro = str(e)
                    else:
                        # Tubo: Tê no meio / Joelho na ponta
                        tol_fim_ft = _to_ft(TOL_FIM)
                        dist_a     = pt_ramal.DistanceTo(pt_A)
                        dist_b     = pt_ramal.DistanceTo(pt_B)
                        em_ponta   = (dist_a < tol_fim_ft or dist_b < tol_fim_ft)

                        if em_ponta:
                            pt_fim   = pt_A if dist_a < tol_fim_ft else pt_B
                            conn_fim = _get_connector_near(tubo_principal, pt_fim)
                            if conn_fim:
                                try:
                                    doc.Create.NewElbowFitting(conn_fim, conn_ramal)
                                    conexao_principal = u"joelho"
                                except Exception as e:
                                    conexao_erro = str(e)
                            else:
                                conexao_erro = u"conector de ponta não encontrado"
                        else:
                            try:
                                new_id   = PlumbingUtils.BreakCurve(
                                    doc, tubo_principal.Id, pt_ramal
                                )
                                tubo_sec = doc.GetElement(new_id)
                                conn_p1  = _get_connector_near(tubo_principal, pt_ramal)
                                conn_p2  = _get_connector_near(tubo_sec,       pt_ramal)
                                if conn_p1 and conn_p2:
                                    ord_ = _ordenar_conectores([conn_p1, conn_p2, conn_ramal])
                                    doc.Create.NewTeeFitting(ord_[0], ord_[1], ord_[2])
                                    conexao_principal = u"tê"
                                else:
                                    conexao_erro = u"conectores pós-BreakCurve não encontrados"
                            except Exception as e:
                                conexao_erro = str(e)
                else:
                    conexao_erro = u"conector inferior do ramal não encontrado em pt_ramal"

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

    if not modo_livre and not valvula_conectada:
        output.print_md(u"| Conexão válvula→tubo | **não conectada** |")
    if not modo_livre and not conexao_principal:
        output.print_md(u"| Conexão tubo principal | **falhou** — `{}` |".format(conexao_erro or u"motivo desconhecido"))

    return {u"valvula": valvula, u"dir_saida": dir_saida, u"nivel": nivel}