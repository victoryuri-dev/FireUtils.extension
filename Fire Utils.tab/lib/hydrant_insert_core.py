# -*- coding: utf-8 -*-
"""
hydrant_insert_core.py — Fire Utils · lib/
Lógica central de inserção da coluna de hidrante.

Chamado pelos botões:
  - Inserir Hidrante            → run(doc, uidoc, output, forcar_nivel=False)
  - Inserir Hidrante com Abrigo → run_com_abrigo(doc, uidoc, output)
  - Inserir Hidrante por Nível  → run_coluna_multilevel(doc, uidoc, output)
                                   Coluna vertical atravessando vários
                                   níveis de uma vez — reaproveita as
                                   mesmas medidas/geometria de run()
                                   (ALTURA_VALVULA_M, COMP_HORIZ_M) pra
                                   cada ramal horizontal, só que repetido
                                   em cada nível escolhido.

As 3 ferramentas usam um diálogo MODELESS com PRÉVIA AO VIVO (mesmo
padrão de connect_pipe.py/connect_shelter_core_preview.py) pra escolher a
orientação da válvula/ramal (4 botões cardeais) e, quando há abrigo, o
lado dele em relação à válvula — substituindo os antigos cliques de
direção. Ver _JanelaOpcoesHidrante, _JanelaOpcoesHidranteAbrigo e
_JanelaOpcoesColuna.
"""

import os
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
# Necessário pra System.Windows.Controls.CheckBox, criado dinamicamente em
# _JanelaOpcoesColuna.__init__ (número de níveis varia por projeto, não dá
# pra declarar um checkbox por nível direto no XAML) — pyrevit.forms já usa
# essas assemblies internamente pra qualquer WPFWindow, mas referencia
# explicitamente aqui em vez de depender disso como efeito colateral.
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import math

import System.Windows as SW

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, UnitUtils, Level,
    BuiltInParameter, FilteredElementCollector,
    ElementId, LocationCurve, ElementTransformUtils,
    FamilyInstance,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType, PlumbingUtils
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

from family_loader_events import criar_fila_acoes
from shelter_family import garantir_abrigo
from shelter_insert_core import _calcular_pt_abrigo, _inserir_abrigo_transacao

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
# Reexportados daqui (mantidos importáveis como hydrant_insert_core.X pra
# não quebrar quem já importava assim) mas definidos em hydrant_shared —
# ver docstring do módulo sobre por quê.
from hydrant_shared import (
    ALTURA_VALVULA_M, COMP_HORIZ_M, DIAM_RAMAL_M, TOL,
    _setar_diametro_ft, _angulo_entre, _conector_mais_proximo,
)

TOL_FIM          = 0.05   # metros — distância máxima ao endpoint para ser "ponta"

_LIB_DIR            = os.path.dirname(os.path.abspath(__file__))
_XAML_COLUNA_PATH   = os.path.join(_LIB_DIR, u"hydrant_coluna_opcoes.xaml")
_XAML_HIDRANTE_PATH = os.path.join(_LIB_DIR, u"hydrant_opcoes.xaml")
_XAML_ABRIGO_PATH   = os.path.join(_LIB_DIR, u"hydrant_abrigo_opcoes.xaml")


# ===========================================================================
# RASTREAMENTO DE ELEMENTOS CRIADOS (ciclos de prévia ao vivo)
# ===========================================================================
# Mesmo padrão de connect_pipe.py: em vez de comparar um snapshot do
# documento inteiro (FilteredElementCollector) antes/depois de cada ciclo —
# custo proporcional ao tamanho do projeto, repetido a CADA troca de opção
# nas janelas de prévia abaixo — os próprios pontos de criação (Pipe.Create,
# NewFamilyInstance, NewElbowFitting/NewTeeFitting/NewCrossFitting,
# _inserir_abrigo_transacao) registram o Id assim que criam, enquanto o
# rastreamento está ativo. Duplicado aqui (em vez de importado de
# connect_pipe.py) porque é um detalhe de implementação pequeno e cada
# módulo mantém seu próprio estado global independente.
_rastreador_ativo   = False
_rastreador_criados = []


def _iniciar_rastreamento():
    """Chamado no início de um ciclo de prévia — zera e liga o
    rastreamento antes de construir a coluna/ramal."""
    global _rastreador_ativo, _rastreador_criados
    _rastreador_ativo   = True
    _rastreador_criados = []


def _parar_rastreamento():
    """Desliga o rastreamento e retorna o conjunto de Ids registrados
    nesta rodada — chamado no fim do ciclo de prévia."""
    global _rastreador_ativo
    ids = set(_rastreador_criados)
    _rastreador_ativo = False
    return ids


def _rastrear(elemento):
    """Registra um elemento recém-criado, se o rastreamento estiver
    ativo — fora de um ciclo de prévia (ex.: finalização real, que já
    controla sua própria transação do jeito tradicional) é um no-op
    barato."""
    if _rastreador_ativo and elemento is not None:
        _rastreador_criados.append(elemento.Id)


# ===========================================================================
# OPÇÕES DE DIREÇÃO (4 botões cardeais — substitui o clique de direção)
# ===========================================================================
# Sem tubo/fitting de referência (modo livre): direções globais do projeto.
# Com referência: direções relativas ao eixo do tubo/fitting selecionado —
# "frente" é o próprio eixo, "direita" é _direita_de(eixo). Os nomes das
# chaves (frente/tras/esquerda/direita) são sempre os mesmos; só o RÓTULO
# exibido no botão muda conforme o modo (ver _ROTULOS_DIRECAO_*).
_ROTULOS_DIRECAO_RELATIVO = {
    u"frente": u"Frente", u"tras": u"Trás",
    u"esquerda": u"Esquerda", u"direita": u"Direita",
}
_ROTULOS_DIRECAO_GLOBAL = {
    u"frente": u"Norte", u"tras": u"Sul",
    u"esquerda": u"Oeste", u"direita": u"Leste",
}
_BOTOES_DIRECAO = {
    u"frente": u"RbDirFrente", u"tras": u"RbDirTras",
    u"esquerda": u"RbDirEsquerda", u"direita": u"RbDirDireita",
}
_BOTOES_LADO = {u"esquerda": u"RbLadoEsquerda", u"direita": u"RbLadoDireita"}


def _opcoes_direcao(modo_livre, dir_principal):
    """{chave: XYZ} com as 4 direções cardeais candidatas — globais se
    modo_livre, senão relativas a dir_principal (eixo do tubo/fitting de
    referência)."""
    if modo_livre:
        return {
            u"frente":   XYZ(0.0, 1.0, 0.0),
            u"tras":     XYZ(0.0, -1.0, 0.0),
            u"esquerda": XYZ(-1.0, 0.0, 0.0),
            u"direita":  XYZ(1.0, 0.0, 0.0),
        }
    direita = _direita_de(dir_principal)
    return {
        u"frente":   dir_principal,
        u"tras":     XYZ(-dir_principal.X, -dir_principal.Y, 0.0),
        u"esquerda": XYZ(-direita.X, -direita.Y, 0.0),
        u"direita":  direita,
    }


def _dir_abrigo_de_lado(lado, dir_saida):
    """Direção da face do abrigo a partir do lado escolhido (esquerda/
    direita) em relação a dir_saida — mesma convenção do clique 3
    original (ver Inserir Hidrante com Abrigo.pushbutton, versão antiga)."""
    direita = XYZ(dir_saida.Y, -dir_saida.X, 0.0)
    if lado == u"esquerda":
        return XYZ(-direita.X, -direita.Y, 0.0)
    return direita


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

def _preparar_insercao(doc, uidoc, forcar_nivel, com_abrigo=False):
    """
    Etapas 1-6 de run() (tudo que NÃO depende da direção de saída do
    ramal, escolhida agora no diálogo com prévia ao vivo — ver
    _JanelaOpcoesHidrante/_JanelaOpcoesHidranteAbrigo): família da
    válvula (e do abrigo, se com_abrigo), nível, seleção do elemento
    (tubo/fitting) ou ponto livre, geometria de referência (dir_principal,
    pt_A/pt_B/pt_ramal, tubo_eh_vertical) e tipo/sistema de tubulação
    herdados. Encerra o comando (pyscript.exit) em qualquer cancelamento,
    igual ao fluxo original.
    """
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    simbolo_abrigo, erro_abrigo = (None, None)
    if com_abrigo:
        simbolo_abrigo, erro_abrigo = garantir_abrigo(doc)

    nivel_pre = None
    if forcar_nivel:
        nivel_pre, erro = get_nivel(doc, uidoc, forcar_selecao=True)
        if not nivel_pre:
            pyscript.exit()

    msg_nivel = (u" Nível: {}.".format(nivel_pre.Name)
                 if nivel_pre else
                 u" O nível será detectado da vista ativa.")

    # PickObject (clique direto NUM elemento) em vez de PickPoint + detecção
    # manual por distância XY: essa detecção manual assumia uma vista em
    # planta, onde PickPoint devolve o Z do plano de corte da vista e dá pra
    # "achatar" o clique e comparar só X/Y contra o eixo de cada pipe — mas
    # numa vista 3D/isométrica essa suposição não vale (não existe um único
    # plano de corte, e o Z que o PickPoint devolve não tem relação alguma
    # com o que está visualmente sob o cursor), então o clique nunca caía
    # dentro do raio de nenhum pipe e a ferramenta sempre caía em modo
    # livre — mesmo clicando bem em cima do tubo. PickObject resolve o
    # ponto por ray-casting contra a geometria de verdade, o que funciona
    # em qualquer tipo de vista. Esc aqui não cancela o comando inteiro —
    # só pula pro modo livre (clique em ponto qualquer, próximo PickPoint).
    elem_sel  = None
    pt_clique = None
    try:
        ref_sel   = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroElemento(),
            u"Clique no tubo/fitting para conectar (Esc para posicionar "
            u"livremente).{}".format(msg_nivel)
        )
        elem_sel  = doc.GetElement(ref_sel.ElementId)
        pt_clique = ref_sel.GlobalPoint
    except Exception:
        pass

    modo_livre = (elem_sel is None)

    if modo_livre:
        try:
            pt_clique = uidoc.Selection.PickPoint(
                u"Clique no ponto onde posicionar o hidrante livremente.{}".format(msg_nivel)
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

    if forcar_nivel:
        nivel = nivel_pre
    else:
        nivel, erro = get_nivel(doc, uidoc, forcar_selecao=False)
        if not nivel:
            pyscript.exit()

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

    return {
        u"simbolo": simbolo, u"simbolo_abrigo": simbolo_abrigo, u"erro_abrigo": erro_abrigo,
        u"nivel": nivel, u"modo_livre": modo_livre,
        u"eh_fitting": eh_fitting, u"tubo_principal": tubo_principal,
        u"fitting_principal": fitting_principal, u"n_conns_fitting": n_conns_fitting,
        u"info_pipes_fitting": info_pipes_fitting, u"dir_principal": dir_principal,
        u"tubo_eh_vertical": tubo_eh_vertical, u"pt_A": pt_A, u"pt_B": pt_B,
        u"pt_ramal": pt_ramal, u"level_id": level_id, u"diam_ft": diam_ft,
        u"pipe_type_id": pipe_type_id, u"sys_type_id": sys_type_id,
    }


def _construir_hidrante(doc, ctx, dir_saida, fazer_conexao_principal):
    """
    Constrói o ramal (sub-tubo vertical, se necessário, + tubo horizontal
    + joelho + válvula), igual à Etapa 7 original de run(). Todo elemento
    criado passa por _rastrear — vira um no-op fora de um ciclo de prévia
    (ver _iniciar_rastreamento).

    fazer_conexao_principal=False (usado pelos ciclos de prévia ao vivo):
    NUNCA toca o elemento pré-existente (tubo_principal/fitting_principal)
    — só cria elementos novos, soltos, pra dar uma ideia visual da posição/
    direção. fazer_conexao_principal=True (usado só uma vez, na
    confirmação — ver _finalizar das janelas abaixo): faz a conexão real
    (delete+reconstrução do fitting, ou Tê/joelho no tubo), exatamente como
    a Etapa 7 original — mutações destrutivas num elemento do usuário não
    são reversíveis entre um ciclo de prévia e outro, por isso só acontecem
    nesta chamada final.
    """
    comp_horiz_ft = _to_ft(COMP_HORIZ_M)

    nivel              = ctx[u"nivel"]
    pt_ramal           = ctx[u"pt_ramal"]
    tubo_eh_vertical   = ctx[u"tubo_eh_vertical"]
    modo_livre         = ctx[u"modo_livre"]
    eh_fitting         = ctx[u"eh_fitting"]
    tubo_principal     = ctx[u"tubo_principal"]
    fitting_principal  = ctx[u"fitting_principal"]
    n_conns_fitting    = ctx[u"n_conns_fitting"]
    info_pipes_fitting = ctx[u"info_pipes_fitting"]
    pt_A, pt_B         = ctx[u"pt_A"], ctx[u"pt_B"]
    level_id           = ctx[u"level_id"]
    diam_ft            = ctx[u"diam_ft"]
    pipe_type_id       = ctx[u"pipe_type_id"]
    sys_type_id        = ctx[u"sys_type_id"]
    simbolo            = ctx[u"simbolo"]

    z_tubo    = pt_ramal.Z
    z_valvula = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)

    if tubo_eh_vertical:
        # Tubo principal vertical: ramal sai a 1.30 m do piso, sem sub-tubo vertical
        pt_ramal_z   = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        pt_joelho    = pt_ramal_z
        tem_vertical = False
    else:
        pt_joelho    = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        tem_vertical = abs(z_valvula - z_tubo) > TOL

    pt_valvula = XYZ(
        pt_joelho.X + dir_saida.X * comp_horiz_ft,
        pt_joelho.Y + dir_saida.Y * comp_horiz_ft,
        pt_joelho.Z
    )

    # — Fitting: deletar antes de criar os novos tubos (só na conexão real) —
    pipe_conns_livres = []
    if fazer_conexao_principal and eh_fitting:
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
        _rastrear(tubo_vert)
    else:
        tubo_vert = None

    # — Tubo horizontal —
    tubo_horiz = Pipe.Create(
        doc, sys_type_id, pipe_type_id, level_id,
        pt_joelho, pt_valvula
    )
    _setar_diametro_ft(tubo_horiz, diam_ft)
    _rastrear(tubo_horiz)

    # — Joelho entre vertical e horizontal —
    if tem_vertical and tubo_vert is not None:
        conn_v = _get_connector_at(tubo_vert,  pt_joelho)
        conn_h = _get_connector_at(tubo_horiz, pt_joelho)
        if conn_v and conn_h:
            try:
                fitting_joelho = doc.Create.NewElbowFitting(conn_v, conn_h)
                _rastrear(fitting_joelho)
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
    _rastrear(valvula)

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

    # — Conexão ao elemento principal (só na conexão real) —
    conexao_principal = None
    conexao_erro      = u""
    if fazer_conexao_principal and not modo_livre:
        doc.Regenerate()
        if tem_vertical:
            conn_ramal = _get_connector_near(tubo_vert, pt_ramal)
        else:
            conn_ramal = _get_connector_near(tubo_horiz, pt_ramal)

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

    return {
        u"valvula": valvula, u"valvula_conectada": valvula_conectada,
        u"conexao_principal": conexao_principal, u"conexao_erro": conexao_erro,
    }


def _construir_hidrante_com_abrigo(doc, ctx, dir_saida, dir_abrigo, fazer_conexao_principal):
    """_construir_hidrante + abrigo de mangueira ao lado da válvula —
    usa _inserir_abrigo_transacao (núcleo SEM transação própria de
    shelter_insert_core.py), já que esta função roda dentro da transação
    (de prévia ou de confirmação) aberta pelas janelas abaixo."""
    resultado = _construir_hidrante(doc, ctx, dir_saida, fazer_conexao_principal)
    try:
        pt_valvula = resultado[u"valvula"].Location.Point
    except Exception:
        pt_valvula = None
    if pt_valvula is not None and ctx[u"simbolo_abrigo"] is not None:
        pt_abrigo = _calcular_pt_abrigo(pt_valvula, dir_saida, ctx[u"nivel"], dir_abrigo)
        abrigo = _inserir_abrigo_transacao(doc, ctx[u"simbolo_abrigo"], pt_abrigo, dir_abrigo, ctx[u"nivel"])
        _rastrear(abrigo)
        resultado[u"abrigo"] = abrigo
    else:
        resultado[u"abrigo"] = None
    return resultado


# ============================================================================
# FORM — direção do ramal/válvula, com prévia ao vivo (Inserir Hidrante)
# ============================================================================
# Mesmo padrão de connect_pipe.py/_JanelaOpcoesRota: janela MODELESS (Show,
# não ShowDialog), cada troca de opção reconstrói a prévia numa transação
# própria (aberta E fechada ali mesmo), e toda ação que toca o documento
# passa pela fila de ExternalEvent (self.fila_acoes) — ver docstring de
# _JanelaOpcoesRota em connect_pipe.py para os detalhes completos.

_CHAVE_JANELA_HIDRANTE = u"FireUtils_InserirHidrante_JanelaAtiva"


class _JanelaOpcoesHidrante(forms.WPFWindow):

    _XAML_PATH = _XAML_HIDRANTE_PATH

    def __init__(self, doc, uidoc, ctx, output):
        forms.WPFWindow.__init__(self, self._XAML_PATH)
        self.doc    = doc
        self.uidoc  = uidoc
        self.ctx    = ctx
        self.output = output

        self.confirmado            = False
        self._preview_ok           = False
        self._finalizado           = False
        self._sincronizando        = False
        self._atualizacao_pendente = False
        self._elementos_criados    = set()
        self._direcao_atual        = u"frente"
        self.fila_acoes            = criar_fila_acoes()

        rotulos = (_ROTULOS_DIRECAO_GLOBAL if ctx[u"modo_livre"] else _ROTULOS_DIRECAO_RELATIVO)
        for chave, nome_btn in _BOTOES_DIRECAO.items():
            getattr(self, nome_btn).Content = rotulos[chave]

        self._sincronizando = True
        try:
            self.RbDirFrente.IsChecked = True
        finally:
            self._sincronizando = False

        self.TxtStatus.Text       = u"Carregando prévia…"
        self.TxtStatus.Foreground = self.Resources[u"BrushLabel"]

    def _direcao_saida_atual(self):
        return _opcoes_direcao(self.ctx[u"modo_livre"], self.ctx[u"dir_principal"])[self._direcao_atual]

    def _desfazer_elementos_criados(self):
        for eid in self._elementos_criados:
            try:
                self.doc.Delete(eid)
            except Exception:
                pass
        self._elementos_criados = set()

    def _construir(self, dir_saida, fazer_conexao_principal):
        """Ponto único de construção — sobrescrito por
        _JanelaOpcoesHidranteAbrigo pra também inserir o abrigo."""
        return _construir_hidrante(self.doc, self.ctx, dir_saida, fazer_conexao_principal)

    def _finalizar(self, confirmado):
        """Fecha a prévia de vez. Confirmado: desfaz a prévia (só
        visual, nunca tocou o elemento principal) e constrói o resultado
        REAL numa transação própria, com a conexão ao elemento principal.
        Senão: só desfaz a prévia."""
        if confirmado:
            t = Transaction(self.doc, u"FireUtils - Inserir Hidrante")
            t.Start()
            try:
                self._desfazer_elementos_criados()
                self.doc.Regenerate()
                resultado = self._construir(self._direcao_saida_atual(), True)
                t.Commit()
            except Exception as e:
                t.RollBack()
                forms.alert(
                    u"Erro ao criar o hidrante:\n{}".format(str(e)),
                    title=u"Fire Utils – Erro", warn_icon=True)
                return
            if not resultado[u"valvula_conectada"]:
                self.output.print_md(u"| Conexão válvula→tubo | **não conectada** |")
            if not self.ctx[u"modo_livre"] and not resultado[u"conexao_principal"]:
                self.output.print_md(u"| Conexão tubo principal | **falhou** — `{}` |".format(
                    resultado[u"conexao_erro"] or u"motivo desconhecido"))
            return

        t = Transaction(self.doc, u"FireUtils - Inserir Hidrante (descartar prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
        finally:
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass

    def _forcar_render(self):
        try:
            from System.Windows.Threading import DispatcherPriority
            from System import Action
            self.Dispatcher.Invoke(DispatcherPriority.Render, Action(lambda: None))
        except Exception:
            pass

    def _ciclo_preview(self):
        t = Transaction(self.doc, u"FireUtils - Inserir Hidrante (prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self.doc.Regenerate()

            _iniciar_rastreamento()
            erro = None
            try:
                self._construir(self._direcao_saida_atual(), False)
                self.doc.Regenerate()
            except Exception as ex:
                erro = u"Erro na prévia: {}".format(ex)
            self._elementos_criados = _parar_rastreamento()

            if erro is not None:
                self._desfazer_elementos_criados()
                self.doc.Regenerate()
                self._preview_ok = False
                self.TxtStatus.Text       = erro
                self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
            else:
                self._preview_ok = True
                self.TxtStatus.Text       = u""
                self.TxtStatus.Foreground = self.Resources[u"BrushOk"]
        finally:
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass
        try:
            self.uidoc.RefreshActiveView()
        except Exception:
            pass

    def _agendar_atualizacao(self):
        if self._atualizacao_pendente:
            return
        self._atualizacao_pendente = True

        def _acao(uiapp):
            self._atualizacao_pendente = False
            self._ciclo_preview()
        self.fila_acoes.enfileirar(_acao)

    def on_direcao_changed(self, sender, args):
        if self._sincronizando:
            return
        for chave, nome_btn in _BOTOES_DIRECAO.items():
            if getattr(self, nome_btn).IsChecked:
                self._direcao_atual = chave
                break
        self._agendar_atualizacao()

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self._preview_ok:
            forms.alert(
                u"Não é possível confirmar com as opções atuais:\n{}".format(self.TxtStatus.Text),
                title=u"Fire Utils", warn_icon=True)
            return
        self.confirmado = True
        self.Close()

    def on_closing(self, sender, args):
        if self._finalizado:
            return
        self._finalizado = True
        pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, None)
        confirmado = self.confirmado

        def _acao(uiapp):
            self._finalizar(confirmado)
        self.fila_acoes.enfileirar(_acao)


class _JanelaOpcoesHidranteAbrigo(_JanelaOpcoesHidrante):
    """Mesma prévia ao vivo, com uma seção extra pro lado do abrigo
    (esquerda/direita em relação à válvula) — usada por run_com_abrigo."""

    _XAML_PATH = _XAML_ABRIGO_PATH

    def __init__(self, doc, uidoc, ctx, output):
        self._lado_atual = u"direita"
        _JanelaOpcoesHidrante.__init__(self, doc, uidoc, ctx, output)
        self._sincronizando = True
        try:
            self.RbLadoDireita.IsChecked = True
        finally:
            self._sincronizando = False

    def _dir_abrigo_atual(self):
        return _dir_abrigo_de_lado(self._lado_atual, self._direcao_saida_atual())

    def _construir(self, dir_saida, fazer_conexao_principal):
        return _construir_hidrante_com_abrigo(
            self.doc, self.ctx, dir_saida, self._dir_abrigo_atual(), fazer_conexao_principal)

    def on_lado_changed(self, sender, args):
        if self._sincronizando:
            return
        for lado, nome_btn in _BOTOES_LADO.items():
            if getattr(self, nome_btn).IsChecked:
                self._lado_atual = lado
                break
        self._agendar_atualizacao()


def run(doc, uidoc, output, forcar_nivel=False):
    """
    forcar_nivel=False  → nível obtido da vista ativa (seletor como fallback)
    forcar_nivel=True   → seletor sempre exibido antes de selecionar o tubo
    """
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_HIDRANTE)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, None)

    ctx = _preparar_insercao(doc, uidoc, forcar_nivel, com_abrigo=False)

    janela = None
    try:
        janela = _JanelaOpcoesHidrante(doc, uidoc, ctx, output)
        pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, janela)
        janela.Show()
        janela._forcar_render()
        janela._ciclo_preview()
    except Exception as ex:
        if janela is not None:
            janela._finalizar(False)
        pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, None)
        forms.alert(u"Falha ao abrir o diálogo de inserção de hidrante: {}".format(ex),
                    title=u"Fire Utils – Erro", warn_icon=True)


def run_com_abrigo(doc, uidoc, output):
    """Inserir Hidrante com Abrigo: igual a run(), com uma seção extra no
    diálogo pra escolher o lado do abrigo (esquerda/direita em relação à
    válvula) — a prévia ao vivo mostra o ramal, a válvula E o abrigo
    juntos. Substitui o antigo clique 3 (direção do abrigo) feito no
    próprio script.py do botão."""
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_HIDRANTE)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, None)

    ctx = _preparar_insercao(doc, uidoc, forcar_nivel=False, com_abrigo=True)
    if ctx[u"erro_abrigo"]:
        forms.alert(ctx[u"erro_abrigo"], title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    janela = None
    try:
        janela = _JanelaOpcoesHidranteAbrigo(doc, uidoc, ctx, output)
        pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, janela)
        janela.Show()
        janela._forcar_render()
        janela._ciclo_preview()
    except Exception as ex:
        if janela is not None:
            janela._finalizar(False)
        pyscript.set_envvar(_CHAVE_JANELA_HIDRANTE, None)
        forms.alert(u"Falha ao abrir o diálogo de inserção de hidrante com abrigo: {}".format(ex),
                    title=u"Fire Utils – Erro", warn_icon=True)

# ===========================================================================
# COLUNA MULTINÍVEL — Inserir Hidrante por Nível
# ===========================================================================

def _segmento_com_topo_maior(pipe_a, pipe_b):
    """Entre dois segmentos de Pipe (pós-BreakCurve de um tubo vertical),
    retorna o que se estende mais pra CIMA — usado por
    run_coluna_multilevel pra continuar subindo a coluna depois de cada
    Tê, já que BreakCurve não documenta qual dos dois lados fica com o
    Id original."""
    def _z_max(p):
        try:
            c = p.Location.Curve
            return max(c.GetEndPoint(0).Z, c.GetEndPoint(1).Z)
        except Exception:
            return float("-inf")
    return pipe_a if _z_max(pipe_a) >= _z_max(pipe_b) else pipe_b


def _criar_fitting_generico(doc, conectores):
    """
    Cria o fitting certo pra N conectores (2 → joelho, 3 → tê, 4 →
    cruzeta) já ordenados por _ordenar_conectores — generaliza a mesma
    lógica que _construir_hidrante já usa pra reconectar o elemento
    principal, agora reusada pro ponto onde a coluna multinível
    cruza/termina um tubo de origem.
    """
    conectores = [c for c in conectores if c is not None]
    ord_ = _ordenar_conectores(conectores)
    n = len(ord_)
    if n == 2:
        doc.Create.NewElbowFitting(ord_[0], ord_[1])
    elif n == 3:
        doc.Create.NewTeeFitting(ord_[0], ord_[1], ord_[2])
    elif n == 4:
        doc.Create.NewCrossFitting(ord_[0], ord_[1], ord_[2], ord_[3])
    else:
        raise Exception(u"número de conectores não suportado ({})".format(n))


def _preparar_coluna(doc, uidoc):
    """
    Etapa 1 (família da válvula + abrigo) e Etapa 3 original de
    run_coluna_multilevel (clique no tubo de origem OU ponto livre) —
    tudo que precede o diálogo agora que ele ganhou prévia ao vivo e
    passou a incluir direção/lado do abrigo (precisa saber se há tubo
    de origem, pra decidir entre rótulos relativos e globais, ANTES de
    abrir a janela). Lista de níveis e seleção deles continuam no
    diálogo (ver _JanelaOpcoesColuna), já que mudam a cada ciclo de
    prévia.
    """
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    simbolo_abrigo, erro_abrigo = garantir_abrigo(doc)

    niveis = sorted(
        FilteredElementCollector(doc).OfClass(Level).ToElements(),
        key=lambda n: n.Elevation
    )
    if not niveis:
        forms.alert(u"Nenhum nível encontrado no projeto.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    # PickObject primeiro (igual a _preparar_insercao) — Esc não cancela
    # o comando, só pula pro modo livre (PickPoint de ponto qualquer).
    tubo_origem = None
    pt_clique   = None
    try:
        ref_sel = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroElemento(),
            u"Clique no tubo de origem pra conectar a coluna (Esc pra "
            u"posicionar livremente)"
        )
        elem_ref = doc.GetElement(ref_sel.ElementId)
        if isinstance(elem_ref, Pipe):
            tubo_origem = elem_ref
            pt_clique   = ref_sel.GlobalPoint
        # FamilyInstance (joelho/tê) como origem não é suportado aqui —
        # cai pro modo livre abaixo.
    except Exception:
        pass

    if tubo_origem is None:
        try:
            pt_clique = uidoc.Selection.PickPoint(
                u"Clique no ponto onde posicionar a coluna de hidrantes"
            )
        except Exception:
            pyscript.exit()

    # Coluna nasce exatamente sobre o eixo do tubo de origem (X/Y do
    # clique projetado nesse eixo) — não faz sentido a coluna "quase"
    # cruzar o tubo sem estar exatamente sobre o ponto de corte.
    z_origem      = None
    dir_principal = XYZ(1.0, 0.0, 0.0)
    if tubo_origem is not None:
        loc_o = tubo_origem.Location.Curve
        pt_origem = _projetar_no_eixo(pt_clique, loc_o.GetEndPoint(0), loc_o.GetEndPoint(1))
        pt_clique = XYZ(pt_origem.X, pt_origem.Y, pt_clique.Z)
        z_origem  = pt_origem.Z
        dir_principal = _direcao_horizontal(tubo_origem)

    # Tipo/sistema de tubulação: prefere herdar do PRÓPRIO tubo de
    # origem (garante compatibilidade perfeita com o sistema que a
    # coluna está entrando); sem tubo de origem, prefere qualquer Pipe
    # JÁ EXISTENTE no projeto — um PipeType que já tem tubos de verdade
    # modelados quase certamente já tem Preferências de Roteamento
    # configuradas (joelho/tê definidos pra esse tipo/tamanho). O
    # fallback final ("1º PipeType do FilteredElementCollector") pode
    # pegar um tipo NUNCA usado no projeto, sem fitting nenhum
    # configurado — daí TODO joelho/tê (até o primeiro, sem nenhum
    # BreakCurve envolvido) derrubar com "failed to insert elbow/tee.":
    # o tipo em si não tem família de joelho/tê associada, não é um
    # problema de geometria.
    pipe_existente = tubo_origem
    if pipe_existente is None:
        pipe_existente = next(iter(FilteredElementCollector(doc).OfClass(Pipe).ToElements()), None)

    pipe_type_id = ElementId.InvalidElementId
    sys_type_id  = ElementId.InvalidElementId

    if pipe_existente is not None:
        try:
            pipe_type_id = pipe_existente.GetTypeId()
        except Exception:
            pass
        try:
            mep_sys = pipe_existente.MEPSystem
            if mep_sys:
                sys_type_id = mep_sys.GetTypeId()
        except Exception:
            pass

    if pipe_type_id == ElementId.InvalidElementId:
        try:
            from Autodesk.Revit.DB.Plumbing import PipeType
            tipos_pipe = FilteredElementCollector(doc).OfClass(PipeType).ToElements()
            if tipos_pipe:
                pipe_type_id = tipos_pipe[0].Id
        except Exception:
            pass

    if sys_type_id == ElementId.InvalidElementId:
        try:
            tipos = FilteredElementCollector(doc).OfClass(PipingSystemType).ToElements()
            if tipos:
                sys_type_id = tipos[0].Id
        except Exception:
            pass

    return {
        u"simbolo": simbolo, u"simbolo_abrigo": simbolo_abrigo, u"erro_abrigo": erro_abrigo,
        u"niveis": niveis, u"tubo_origem": tubo_origem, u"pt_clique": pt_clique,
        u"z_origem": z_origem, u"dir_principal": dir_principal,
        u"modo_livre": (tubo_origem is None),
        u"pipe_type_id": pipe_type_id, u"sys_type_id": sys_type_id,
    }


def _construir_coluna(doc, ctx, niveis_sel, dir_saida, inserir_abrigo, dir_abrigo,
                       fazer_conexao_origem):
    """
    Constrói a coluna inteira — igual à Etapa 6 original de
    run_coluna_multilevel — parametrizada por niveis_sel (vem do estado
    ATUAL dos checkboxes, muda a cada ciclo de prévia) e
    fazer_conexao_origem.

    fazer_conexao_origem=False (ciclos de prévia): o evento "origem"
    nunca mexe no tubo_origem (pré-existente) — só o corte do TUBO
    VERTICAL NOVO na altura dele (se for meio de coluna) acontece, pra
    já mostrar o formato certo da coluna; a conexão real (que corta/
    estende o tubo_origem do usuário) é destrutiva e não dá pra desfazer
    entre um ciclo e outro, então só roda na confirmação (ver
    fazer_conexao_origem=True, chamado por _JanelaOpcoesColuna._finalizar).

    Levanta Exception (nunca pyscript.exit) em qualquer estado inválido
    (poucos níveis, abrigo sem família etc.) — quem chama (ciclo de
    prévia ou finalização) decide o que fazer com a mensagem.
    """
    if len(niveis_sel) < 2:
        raise Exception(u"Selecione pelo menos 2 níveis (a coluna precisa de uma base e um topo).")
    if inserir_abrigo and ctx[u"simbolo_abrigo"] is None:
        raise Exception(ctx[u"erro_abrigo"] or u"Não foi possível carregar a família do abrigo.")

    comp_horiz_ft     = _to_ft(COMP_HORIZ_M)
    altura_valvula_ft = _to_ft(ALTURA_VALVULA_M)
    diam_ft           = _to_ft(DIAM_RAMAL_M)
    tol_fim_ft         = _to_ft(TOL_FIM)

    simbolo        = ctx[u"simbolo"]
    simbolo_abrigo = ctx[u"simbolo_abrigo"]
    tubo_origem    = ctx[u"tubo_origem"]
    pt_clique      = ctx[u"pt_clique"]
    z_origem       = ctx[u"z_origem"]
    pipe_type_id   = ctx[u"pipe_type_id"]
    sys_type_id    = ctx[u"sys_type_id"]

    nivel_base = niveis_sel[0]
    nivel_topo = niveis_sel[-1]
    z_base     = nivel_base.Elevation + altura_valvula_ft
    z_topo     = nivel_topo.Elevation + altura_valvula_ft

    if z_topo - z_base < TOL:
        raise Exception(
            u"Os níveis selecionados precisam ter elevações diferentes "
            u"pra formar uma coluna vertical (pra um único nível, use "
            u"'Inserir Hidrante').")

    # Estende o intervalo da coluna pra incluir a cota do tubo de origem,
    # se ela cair fora do que os níveis selecionados já cobrem (ex.:
    # usuário só marcou níveis ACIMA do tubo de origem — o tubo de
    # origem vira a nova base da coluna).
    if z_origem is not None:
        z_base = min(z_base, z_origem)
        z_topo = max(z_topo, z_origem)

    pt_base = XYZ(pt_clique.X, pt_clique.Y, z_base)
    pt_topo = XYZ(pt_clique.X, pt_clique.Y, z_topo)

    # Eventos ordenados por cota (de baixo pra cima): um por nível
    # selecionado (ramal + válvula) e, se houver, um pro tubo de origem
    # (só a conexão, sem ramal/válvula — não é um hidrante, é onde a
    # coluna entra na rede existente). Processar tudo numa lista só, na
    # mesma ordem de baixo pra cima, mantém tubo_vert sempre apontando
    # pro segmento de cima certo, não importa a ordem relativa entre
    # níveis de hidrante e o ponto de conexão do tubo de origem.
    eventos = [{u"tipo": u"hidrante", u"z": n.Elevation + altura_valvula_ft, u"nivel": n}
               for n in niveis_sel]
    if tubo_origem is not None:
        eventos.append({u"tipo": u"origem", u"z": z_origem})
    eventos.sort(key=lambda e: e[u"z"])

    valvulas_criadas = []
    avisos           = []

    loc_o = tubo_origem.Location.Curve if tubo_origem is not None else None

    tubo_vert = Pipe.Create(doc, sys_type_id, pipe_type_id, nivel_base.Id, pt_base, pt_topo)
    _setar_diametro_ft(tubo_vert, diam_ft)
    _rastrear(tubo_vert)

    for evento in eventos:
        z = evento[u"z"]
        pt_z = XYZ(pt_clique.X, pt_clique.Y, z)
        extremo_base = abs(z - z_base) < TOL
        extremo_topo = abs(z - z_topo) < TOL

        # ── Pernas do lado da COLUNA neste ponto: 1 se for extremo (só
        # continua pra um lado), 2 se for meio da coluna (corta e
        # continua pros dois lados). O tubo vertical é sempre NOVO
        # (criado acima nesta mesma chamada) — cortá-lo não é
        # destrutivo pra nada pré-existente, roda em qualquer ciclo.
        conns_coluna = []
        if extremo_base or extremo_topo:
            pt_ref = pt_base if extremo_base else pt_topo
            conn_v = _get_connector_near(tubo_vert, pt_ref)
            if conn_v:
                conns_coluna.append(conn_v)
            else:
                avisos.append(u"z={:.2f}: conector do tubo vertical não encontrado".format(_to_m(z)))
        else:
            tubo_vert_sec = None
            try:
                new_id_v      = PlumbingUtils.BreakCurve(doc, tubo_vert.Id, pt_z)
                tubo_vert_sec = doc.GetElement(new_id_v)
                _rastrear(tubo_vert_sec)
            except Exception as e:
                avisos.append(u"z={:.2f}: corte do tubo vertical falhou ({})".format(_to_m(z), str(e)))

            if tubo_vert_sec is not None:
                conn_v1 = _get_connector_near(tubo_vert,     pt_z)
                conn_v2 = _get_connector_near(tubo_vert_sec, pt_z)
                if conn_v1 and conn_v2:
                    conns_coluna.extend([conn_v1, conn_v2])
                else:
                    avisos.append(u"z={:.2f}: conectores pós-corte da coluna não encontrados".format(_to_m(z)))
                # SEMPRE continua subindo a partir do segmento de CIMA do
                # corte, mesmo se o fitting não tiver sido criado — ver
                # docstring original de run_coluna_multilevel.
                tubo_vert = _segmento_com_topo_maior(tubo_vert, tubo_vert_sec)

        if evento[u"tipo"] == u"hidrante":
            nivel   = evento[u"nivel"]
            pt_valv = XYZ(
                pt_z.X + dir_saida.X * comp_horiz_ft,
                pt_z.Y + dir_saida.Y * comp_horiz_ft,
                pt_z.Z,
            )

            tubo_horiz = Pipe.Create(doc, sys_type_id, pipe_type_id, nivel.Id, pt_z, pt_valv)
            _setar_diametro_ft(tubo_horiz, diam_ft)
            _rastrear(tubo_horiz)
            conn_h_ini = _get_connector_at(tubo_horiz, pt_z)

            if conn_h_ini and conns_coluna:
                try:
                    _criar_fitting_generico(doc, conns_coluna + [conn_h_ini])
                except Exception as e:
                    avisos.append(u"{}: conexão do ramal falhou ({})".format(nivel.Name, str(e)))
            elif not conn_h_ini:
                avisos.append(u"{}: conector do ramal não encontrado".format(nivel.Name))

            conn_tubo_fim = _get_far_connector(tubo_horiz, pt_z)
            pos_insercao  = conn_tubo_fim.Origin if conn_tubo_fim else pt_valv

            valvula = doc.Create.NewFamilyInstance(
                pos_insercao, simbolo, nivel, StructuralType.NonStructural
            )
            _rastrear(valvula)
            angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_saida)
            if abs(angulo) > TOL:
                eixo_rot = Line.CreateBound(
                    pos_insercao,
                    XYZ(pos_insercao.X, pos_insercao.Y, pos_insercao.Z + 1.0)
                )
                ElementTransformUtils.RotateElement(doc, valvula.Id, eixo_rot, angulo)

            if conn_tubo_fim:
                conn_val = _conector_mais_proximo(valvula, pos_insercao)
                if conn_val:
                    deslocamento = conn_tubo_fim.Origin - conn_val.Origin
                    if deslocamento.GetLength() > TOL:
                        ElementTransformUtils.MoveElement(doc, valvula.Id, deslocamento)
                    try:
                        conn_tubo_fim.ConnectTo(conn_val)
                    except Exception:
                        avisos.append(u"{}: válvula não conectada ao ramal".format(nivel.Name))

            valvulas_criadas.append((valvula, nivel))

            if inserir_abrigo and simbolo_abrigo is not None:
                try:
                    pt_valvula_real = valvula.Location.Point
                except Exception:
                    pt_valvula_real = None
                if pt_valvula_real is not None:
                    pt_abrigo = _calcular_pt_abrigo(pt_valvula_real, dir_saida, nivel, dir_abrigo)
                    abrigo = _inserir_abrigo_transacao(doc, simbolo_abrigo, pt_abrigo, dir_abrigo, nivel)
                    _rastrear(abrigo)

        else:  # evento[u"tipo"] == u"origem"
            if not fazer_conexao_origem:
                continue

            # ── Pernas do lado do TUBO DE ORIGEM: 1 se o ponto de corte
            # cair perto de uma ponta (estende até lá), 2 se for no meio
            # (BreakCurve) — mutação destrutiva num elemento
            # pré-existente, por isso só roda aqui (fazer_conexao_origem
            # True), nunca num ciclo de prévia.
            p0o, p1o = loc_o.GetEndPoint(0), loc_o.GetEndPoint(1)
            dist_a = pt_z.DistanceTo(p0o)
            dist_b = pt_z.DistanceTo(p1o)
            em_ponta_origem = (dist_a < tol_fim_ft or dist_b < tol_fim_ft)

            conns_origem = []
            if em_ponta_origem:
                pt_fim_o = p0o if dist_a < dist_b else p1o
                _ajustar_endpoint(tubo_origem, pt_fim_o, pt_z)
                doc.Regenerate()
                conn_o = _get_connector_near(tubo_origem, pt_z)
                if conn_o:
                    conns_origem.append(conn_o)
                else:
                    avisos.append(u"Tubo de origem: conector da ponta não encontrado")
            else:
                tubo_origem_sec = None
                try:
                    new_id_o        = PlumbingUtils.BreakCurve(doc, tubo_origem.Id, pt_z)
                    tubo_origem_sec = doc.GetElement(new_id_o)
                except Exception as e:
                    avisos.append(u"Tubo de origem: corte falhou ({})".format(str(e)))
                if tubo_origem_sec is not None:
                    conn_o1 = _get_connector_near(tubo_origem,     pt_z)
                    conn_o2 = _get_connector_near(tubo_origem_sec, pt_z)
                    if conn_o1 and conn_o2:
                        conns_origem.extend([conn_o1, conn_o2])
                    else:
                        avisos.append(u"Tubo de origem: conectores pós-corte não encontrados")

            conns_totais = conns_origem + conns_coluna
            if len(conns_totais) >= 2:
                try:
                    _criar_fitting_generico(doc, conns_totais)
                except Exception as e:
                    avisos.append(u"Tubo de origem: conexão falhou ({})".format(str(e)))
            else:
                avisos.append(u"Tubo de origem: conectores insuficientes pra criar a conexão")

    return {u"valvulas_criadas": valvulas_criadas, u"avisos": avisos}


# ============================================================================
# FORM — níveis + abrigo + direção, com prévia ao vivo (Inserir Hidrante
# por Nível)
# ============================================================================

_CHAVE_JANELA_COLUNA = u"FireUtils_InserirHidranteColuna_JanelaAtiva"


class _JanelaOpcoesColuna(forms.WPFWindow):
    """Janela MODELESS (hydrant_coluna_opcoes.xaml) com PRÉVIA AO VIVO —
    mesmo padrão de _JanelaOpcoesHidrante: níveis (checkbox por nível,
    criados dinamicamente porque o número varia por projeto), "inserir
    abrigo" e, agora, orientação da válvula/ramal (4 botões cardeais,
    UMA só pra toda a coluna) + lado do abrigo (quando marcado) —
    qualquer troca reconstrói a coluna inteira no modelo."""

    def __init__(self, doc, uidoc, ctx, output):
        forms.WPFWindow.__init__(self, _XAML_COLUNA_PATH)
        self.doc    = doc
        self.uidoc  = uidoc
        self.ctx    = ctx
        self.output = output

        self.confirmado            = False
        self._preview_ok           = False
        self._finalizado           = False
        self._sincronizando        = False
        self._atualizacao_pendente = False
        self._elementos_criados    = set()
        self._direcao_atual        = u"frente"
        self._lado_atual           = u"direita"
        self.fila_acoes            = criar_fila_acoes()

        from System.Windows.Controls import CheckBox
        estilo = self.FindResource(u"NivelCheckStyle")
        self._checkboxes = []
        for nivel in ctx[u"niveis"]:
            cb = CheckBox()
            cb.Content = nivel.Name
            cb.Tag     = nivel
            cb.Style   = estilo
            cb.Checked   += self.on_opcao_changed
            cb.Unchecked += self.on_opcao_changed
            self.PainelNiveis.Children.Add(cb)
            self._checkboxes.append(cb)

        rotulos = (_ROTULOS_DIRECAO_GLOBAL if ctx[u"modo_livre"] else _ROTULOS_DIRECAO_RELATIVO)
        for chave, nome_btn in _BOTOES_DIRECAO.items():
            getattr(self, nome_btn).Content = rotulos[chave]

        self._sincronizando = True
        try:
            self.RbDirFrente.IsChecked  = True
            self.RbLadoDireita.IsChecked = True
            self.SecaoLadoAbrigo.Visibility = SW.Visibility.Collapsed
        finally:
            self._sincronizando = False

        self.TxtStatus.Text       = u"Carregando prévia…"
        self.TxtStatus.Foreground = self.Resources[u"BrushLabel"]

    def _niveis_selecionados(self):
        return sorted((cb.Tag for cb in self._checkboxes if cb.IsChecked),
                      key=lambda n: n.Elevation)

    def _inserir_abrigo_atual(self):
        return bool(self.ChkAbrigo.IsChecked)

    def _direcao_saida_atual(self):
        return _opcoes_direcao(self.ctx[u"modo_livre"], self.ctx[u"dir_principal"])[self._direcao_atual]

    def _dir_abrigo_atual(self):
        return _dir_abrigo_de_lado(self._lado_atual, self._direcao_saida_atual())

    def _desfazer_elementos_criados(self):
        for eid in self._elementos_criados:
            try:
                self.doc.Delete(eid)
            except Exception:
                pass
        self._elementos_criados = set()

    def _finalizar(self, confirmado):
        if confirmado:
            niveis_sel      = self._niveis_selecionados()
            inserir_abrigo  = self._inserir_abrigo_atual()
            dir_saida       = self._direcao_saida_atual()
            dir_abrigo      = self._dir_abrigo_atual()
            t = Transaction(self.doc, u"FireUtils - Inserir Coluna de Hidrantes")
            t.Start()
            try:
                self._desfazer_elementos_criados()
                self.doc.Regenerate()
                resultado = _construir_coluna(
                    self.doc, self.ctx, niveis_sel, dir_saida, inserir_abrigo, dir_abrigo,
                    fazer_conexao_origem=True)
                t.Commit()
            except Exception as e:
                t.RollBack()
                forms.alert(
                    u"Erro ao criar a coluna de hidrantes:\n{}".format(str(e)),
                    title=u"Fire Utils – Erro", warn_icon=True)
                return
            for aviso in resultado[u"avisos"]:
                self.output.print_md(u"| Aviso | {} |".format(aviso))
            return

        t = Transaction(self.doc, u"FireUtils - Inserir Coluna de Hidrantes (descartar prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
        finally:
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass

    def _forcar_render(self):
        try:
            from System.Windows.Threading import DispatcherPriority
            from System import Action
            self.Dispatcher.Invoke(DispatcherPriority.Render, Action(lambda: None))
        except Exception:
            pass

    def _ciclo_preview(self):
        t = Transaction(self.doc, u"FireUtils - Inserir Coluna de Hidrantes (prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self.doc.Regenerate()

            _iniciar_rastreamento()
            erro = None
            try:
                _construir_coluna(
                    self.doc, self.ctx, self._niveis_selecionados(),
                    self._direcao_saida_atual(), self._inserir_abrigo_atual(),
                    self._dir_abrigo_atual(), fazer_conexao_origem=False)
                self.doc.Regenerate()
            except Exception as ex:
                erro = u"{}".format(ex)
            self._elementos_criados = _parar_rastreamento()

            if erro is not None:
                self._desfazer_elementos_criados()
                self.doc.Regenerate()
                self._preview_ok = False
                self.TxtStatus.Text       = erro
                self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
            else:
                self._preview_ok = True
                self.TxtStatus.Text       = u""
                self.TxtStatus.Foreground = self.Resources[u"BrushOk"]
        finally:
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass
        try:
            self.uidoc.RefreshActiveView()
        except Exception:
            pass

    def _agendar_atualizacao(self):
        if self._atualizacao_pendente:
            return
        self._atualizacao_pendente = True

        def _acao(uiapp):
            self._atualizacao_pendente = False
            self._ciclo_preview()
        self.fila_acoes.enfileirar(_acao)

    def on_opcao_changed(self, sender, args):
        if self._sincronizando:
            return
        self._agendar_atualizacao()

    def on_direcao_changed(self, sender, args):
        if self._sincronizando:
            return
        for chave, nome_btn in _BOTOES_DIRECAO.items():
            if getattr(self, nome_btn).IsChecked:
                self._direcao_atual = chave
                break
        self._agendar_atualizacao()

    def on_lado_changed(self, sender, args):
        if self._sincronizando:
            return
        for lado, nome_btn in _BOTOES_LADO.items():
            if getattr(self, nome_btn).IsChecked:
                self._lado_atual = lado
                break
        self._agendar_atualizacao()

    def on_abrigo_changed(self, sender, args):
        self.SecaoLadoAbrigo.Visibility = (
            SW.Visibility.Visible if self.ChkAbrigo.IsChecked else SW.Visibility.Collapsed)
        if self._sincronizando:
            return
        self._agendar_atualizacao()

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self._preview_ok:
            forms.alert(
                u"Não é possível confirmar com as opções atuais:\n{}".format(self.TxtStatus.Text),
                title=u"Fire Utils", warn_icon=True)
            return
        self.confirmado = True
        self.Close()

    def on_closing(self, sender, args):
        if self._finalizado:
            return
        self._finalizado = True
        pyscript.set_envvar(_CHAVE_JANELA_COLUNA, None)
        confirmado = self.confirmado

        def _acao(uiapp):
            self._finalizar(confirmado)
        self.fila_acoes.enfileirar(_acao)


def run_coluna_multilevel(doc, uidoc, output):
    """
    Inserir Hidrante por Nível: cria uma ÚNICA coluna vertical
    atravessando vários níveis de uma vez, com um ramal horizontal +
    válvula (e, opcionalmente, abrigo de mangueira) em CADA nível
    escolhido.

    Fluxo:
      1. Clique: tubo de origem pra conectar a coluna (PickObject) OU
         Esc pra posicionar livremente (sem conexão a nada existente).
      2. Diálogo com prévia ao vivo (_JanelaOpcoesColuna): níveis a
         incluir (mín. 2), "inserir abrigo em cada hidrante" e
         orientação da válvula/ramal (+ lado do abrigo, se marcado) —
         toda troca reconstrói a coluna inteira no modelo
         (_construir_coluna) para o usuário ver antes de confirmar.
      3. Na confirmação, a coluna é reconstruída de vez numa transação
         própria, agora COM a conexão real ao tubo de origem (ver
         docstring de _construir_coluna sobre por que essa conexão só
         acontece uma vez).
    """
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_COLUNA)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_COLUNA, None)

    ctx = _preparar_coluna(doc, uidoc)

    janela = None
    try:
        janela = _JanelaOpcoesColuna(doc, uidoc, ctx, output)
        pyscript.set_envvar(_CHAVE_JANELA_COLUNA, janela)
        janela.Show()
        janela._forcar_render()
        janela._ciclo_preview()
    except Exception as ex:
        if janela is not None:
            janela._finalizar(False)
        pyscript.set_envvar(_CHAVE_JANELA_COLUNA, None)
        forms.alert(u"Falha ao abrir o diálogo da coluna de hidrantes: {}".format(ex),
                    title=u"Fire Utils – Erro", warn_icon=True)
