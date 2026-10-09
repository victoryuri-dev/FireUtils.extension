# -*- coding: utf-8 -*-
"""
connect_pipe.py — Fire Utils · lib/
Conecta dois tubos com roteamento em ângulos retos.

Fluxo:
  Clique 1 — ponta do PIPE_DESC (tubo desconectado)
  Clique 2 — PIPE_REF (tubo referência): o CLIQUE só marca a posição no
             corpo (usada se o modo "corpo" for escolhido); corpo vs ponta
             não é mais adivinhado pela distância do clique — ver form abaixo.
  Form     — janela WPF MODELESS (connect_pipe_opcoes.xaml, classe
             _JanelaOpcoesRota) — fica aberta sem travar o Revit, então dá
             pra continuar orbitando/aproximando/afastando a câmera no
             modelo com ela aberta. Reúne as preferências de rota E mostra
             PRÉVIA AO VIVO no modelo a cada mudança de opção (cada troca
             roda sua própria transação, aberta e já comitada no mesmo
             ciclo — ver docstring de _JanelaOpcoesRota):
             • onde conectar em pipe_ref: ponto clicado no corpo (Tê,
               padrão) ou ponta livre — se houver (ver modo_conexao_ref em
               _construir_conexao)
             • ordem dos até 3 trechos retos da rota (Vertical/Z, Paralelo
               e Perpendicular ao eixo de pipe_ref) — livre, escolhida pelo
               usuário; só os eixos que realmente precisam de ajuste
               aparecem como opção (ver ordem_eixos/_eixos_disponiveis)
             Por ser modeless, qualquer clique na janela acontece fora do
             contexto de API válido do Revit — toda ação que toca o
             documento (atualizar a prévia, confirmar, descartar) é
             despachada através de uma fila de ExternalEvent
             (family_loader_events.criar_fila_acoes), nunca chamada direto
             do clique. Se essa janela falhar por qualquer motivo, cai para
             diálogos forms.SelectFromList em sequência + fluxo sem prévia
             (_escolher_opcoes_rota_fallback + _conectar) — esse fallback
             continua modal (sem prévia, sem navegação no modelo).

Etapa 1 — Extensão direta:
  Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref
  E as retas forem REALMENTE colineares (não só paralelas), apenas estende
  e conecta (tê ou joelho conforme posição).

Etapa 2 — Roteamento genérico em até 3 trechos retos:
  A rota vai de P_start (ponta livre de pipe_desc) até P_final (ponto no
  corpo ou ponta livre de pipe_ref) fechando, em sequência, cada um dos
  eixos que realmente precisam de ajuste — z (vertical), par (paralelo ao
  eixo de pipe_ref) e perp (perpendicular a ele). A ORDEM é escolhida pelo
  usuário via ordem_eixos (ver _JanelaOpcoesRota) — qualquer uma das até
  3! permutações possíveis, ex.: (z, par, perp) [padrão/histórico: sobe/
  desce logo na saída, depois ajusta paralelo, depois perpendicular] ou
  (par, perp, z) [roteia tudo na horizontal primeiro, sobe/desce só no
  fim] — não fica mais travado a "só no começo ou só no fim".
  _eixos_necessarios decide quais dos 3 eixos entram de verdade na rota
  (um já alinhado não gera trecho nenhum) — ver também
  _eixos_disponiveis, usado pra só oferecer ao usuário as opções cabíveis.

  1º trecho "colinear com pipe_desc": antes de criar o 1º trecho como
    tubo novo, tenta prolongar o próprio pipe_desc até lá em vez de criar
    tubo + joelho: _tenta_estender_colinear (trechos par/perp) ou extensão
    direta da curva (trecho z, quando pipe_desc já é vertical). Só se
    aplica ao trecho que é de fato o primeiro da rota.

  Corpo + a ordem escolhida fecha o trecho perpendicular ANTES do
  paralelo (com o vertical já resolvido antes, ou nem necessário): o
  ponto onde o perpendicular termina cai, por construção, EXATAMENTE
  sobre a reta infinita de pipe_ref — _ajustar_alvo_corpo_invertido decide
  o que fazer com isso ANTES de criar o trecho paralelo (que rodaria por
  cima do próprio pipe_ref):
    ponto dentro do corpo físico → conecta ali mesmo (Tê), dispensa o
      trecho paralelo e o ponto clicado original.
    ponto fora do corpo físico  → cai para a ponta LIVRE mais próxima de
      pipe_ref e recalcula a rota pra esse novo alvo (modo joelho,
      clicou_ponta passa a True).

Casos PIPE_REF (modo_conexao_ref):
  corpo  → Tê no ponto final da rota (BreakCurve)
  ponta  → joelho na ponta livre de pipe_ref

PIPE_REF nem sempre é outro Pipe: o clique 2 também aceita um FITTING de
MEP (joelho, tê, válvula etc.) que tenha algum conector LIVRE — ex.: um
joelho com uma ponta solta. Nesse caso só o modo "ponta" existe (um
fitting não tem corpo pra abrir Tê) e a conexão é feita direto nesse
conector livre, como se fosse a ponta de um Pipe (ver _FiltroPipeRef,
_conector_livre_mais_proximo e o branch "não é Pipe" em
_preparar_alvo_nominal/_construir_conexao).
"""

import os

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import math

import System.Windows as SW

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, LocationCurve,
    BuiltInParameter, FilteredElementCollector,
    ElementId, UnitUtils, FamilyInstance,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType, PlumbingUtils
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

from family_loader_events import criar_fila_acoes

_XAML_OPCOES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"connect_pipe_opcoes.xaml")

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
TOL_PONTA_REF = _to_ft(0.40)  # 40 cm — teto do raio do clique p/ detectar ponta do PIPE_REF
                               # (raio efetivo é limitado a 25% do comprimento de pipe_ref)
TOL_CONN      = _to_ft(0.50)  # 50 cm — raio de busca de conector próximo
TOL_COLINEAR  = _to_ft(0.02)  # 2 cm  — desvio perpendicular máx. p/ considerar 2 retas paralelas como a MESMA reta


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


def _perp_horizontal(d_ref):
    """
    Direção unitária no plano horizontal, perpendicular ao eixo de
    pipe_ref (d_ref). Renormaliza a projeção horizontal de d_ref antes de
    girar 90° — necessário porque d_ref pode ter uma componente em Z (se
    pipe_ref tiver alguma inclinação), e nesse caso XYZ(d_ref.X, d_ref.Y)
    sozinho não tem módulo 1.
    """
    d_horiz = XYZ(d_ref.X, d_ref.Y, 0.0)
    L_h     = d_horiz.GetLength()
    if L_h > TOL:
        d_horiz = XYZ(d_horiz.X / L_h, d_horiz.Y / L_h, 0.0)
    return XYZ(-d_horiz.Y, d_horiz.X, 0.0)


def _rota_ate_endpoint(P_knee, P_target, d_ref, inverter_eixos=False):
    """
    Calcula a rota em L de P_knee até P_target.
    inverter_eixos=False (padrão): usa d_ref (eixo de PIPE_REF) como direção
      primária — seg1: P_knee → P_mid (paralelo ao eixo de PIPE_REF),
      seg2: P_mid → P_target (perpendicular ao eixo de PIPE_REF).
    inverter_eixos=True: usa o eixo perpendicular (no plano horizontal) a
      d_ref como direção primária — inverte a ordem dos ajustes X/Y.
    Retorna (P_mid, needs_seg1, needs_seg2).
    """
    d_prim = _perp_horizontal(d_ref) if inverter_eixos else d_ref

    v = P_target - P_knee
    a = v.DotProduct(d_prim)
    P_mid = XYZ(P_knee.X + d_prim.X * a,
                P_knee.Y + d_prim.Y * a,
                P_knee.Z)
    needs_seg1 = abs(a) > TOL_SEG
    needs_seg2 = P_mid.DistanceTo(P_target) > TOL_SEG
    if not needs_seg2:
        # P_mid já está "perto o suficiente" de P_target (dentro de
        # TOL_SEG) — sem isso, quem chama usaria P_mid como ponto final
        # de verdade (já que seg2 é dispensado), deixando uma folga de
        # até TOL_SEG entre o tubo e o alvo. ConnectTo não reclama dessa
        # folga (ao contrário de NewElbowFitting), então ela passava
        # despercebida: sem erro, mas sem encostar de fato. Encaixa exato.
        P_mid = P_target
    return P_mid, needs_seg1, needs_seg2


# ── Roteamento em até 3 trechos retos, ordem livre (Z / paralelo / perpendicular) ──

_NOME_EIXO = {u"z": u"Vertical (Z)", u"par": u"Paralelo", u"perp": u"Perpendicular"}


def _eixos_necessarios(P_start, P_final, d_ref):
    """
    Quais dos 3 eixos (z = vertical, par = paralelo ao eixo de pipe_ref,
    perp = perpendicular a ele) realmente precisam de ajuste pra ir de
    P_start até P_final. Um eixo já alinhado (dentro da tolerância) não
    entra na lista — o usuário não escolhe a ordem de um trecho que nem
    vai existir. Retorna uma lista com os códigos necessários, SEM ordem
    definida (a ordem de execução é decidida pelo usuário — ver ordem_eixos
    em _construir_conexao).
    """
    d_perp = _perp_horizontal(d_ref)
    dz     = P_final.Z - P_start.Z
    v_h    = XYZ(P_final.X - P_start.X, P_final.Y - P_start.Y, 0.0)
    a_par  = v_h.DotProduct(d_ref)
    a_perp = v_h.DotProduct(d_perp)
    necessarios = []
    if abs(dz) > TOL_DZ:
        necessarios.append(u"z")
    if abs(a_par) > TOL_SEG:
        necessarios.append(u"par")
    if abs(a_perp) > TOL_SEG:
        necessarios.append(u"perp")
    return necessarios


def _preparar_alvo_nominal(pipe_ref, pt_click_ref, modo_conexao_ref):
    """
    Alvo NOMINAL da conexão em pipe_ref — antes de qualquer redirecionamento
    por sobreposição (que só é decidido depois, já com a ordem escolhida —
    ver o bloco de _ajustar_alvo_corpo_invertido em _construir_conexao).
    Retorna (P_final, d_ref). Propaga _ConexaoError se modo "ponta" e
    nenhuma ponta de pipe_ref estiver livre, ou se pipe_ref for um
    FITTING (joelho/tê/válvula) sem nenhum conector livre.

    Se pipe_ref não for um Pipe (ex.: joelho com uma ponta solta), só
    "ponta" faz sentido — não há corpo pra abrir Tê — e o alvo é o
    conector livre mais próximo do clique, com d_ref = direção desse
    conector (a direção que um tubo conectado ali seguiria).
    """
    if not isinstance(pipe_ref, Pipe):
        conn = _conector_livre_mais_proximo(pipe_ref, pt_click_ref)
        if conn is None:
            raise _ConexaoError(
                u"O elemento de referência não tem nenhum conector livre para conectar.")
        return conn.Origin, _conn_dir(conn)

    loc_ref = pipe_ref.Location.Curve
    pt_A    = loc_ref.GetEndPoint(0)
    pt_B    = loc_ref.GetEndPoint(1)
    d_ref   = (pt_B - pt_A).Normalize()
    if modo_conexao_ref == u"ponta":
        P_final = _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref)
    else:
        ref_proj = pt_click_ref if pt_click_ref is not None else pt_A
        P_final  = _projetar_segmento(ref_proj, pt_A, pt_B)
    return P_final, d_ref


def _eixos_disponiveis(pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, modo_conexao_ref):
    """
    Igual a _eixos_necessarios, mas calculando P_start/P_final a partir dos
    próprios elementos — usado tanto pela prévia ao vivo (pra só oferecer
    ao usuário os botões dos eixos que realmente vão existir na rota)
    quanto pelo fallback sem prévia (pra decidir quantas perguntas de
    ordem fazer). Nunca levanta exceção — se não conseguir decidir (ex.:
    modo "ponta" sem nenhuma ponta livre), libera os 3 eixos; o erro de
    verdade aparece depois, quando _construir_conexao rodar pra valer.
    """
    conn_desc = None
    if pt_click_desc is not None:
        conn_desc = _conn_nearest(pipe_desc, pt_click_desc)
    P_start = conn_desc.Origin if conn_desc is not None else pipe_desc.Location.Curve.GetEndPoint(0)
    try:
        P_final, d_ref = _preparar_alvo_nominal(pipe_ref, pt_click_ref, modo_conexao_ref)
    except _ConexaoError:
        return [u"z", u"par", u"perp"]
    return _eixos_necessarios(P_start, P_final, d_ref)


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


def _extremo_oposto(curve, pt):
    """Endpoint de curve mais distante de pt (o outro extremo)."""
    p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
    return p1 if p0.DistanceTo(pt) < p1.DistanceTo(pt) else p0


def _tenta_estender_colinear(doc, pipe, P_fixo, P_atual, P_alvo):
    """
    Se `pipe` (indo de P_fixo até P_atual) já aponta, em linha reta e no
    mesmo sentido, para P_alvo, PROLONGA pipe até P_alvo (move só o
    endpoint P_atual, mantém P_fixo) em vez de deixar quem chamou criar um
    tubo novo + joelho ali. Retorna True se estendeu, False se não é
    colinear (quem chamou deve criar o tubo novo normalmente).
    """
    if P_atual.DistanceTo(P_alvo) < TOL:
        return False

    d_pipe = P_atual - P_fixo
    L_pipe = d_pipe.GetLength()
    if L_pipe < TOL:
        return False
    d_pipe = XYZ(d_pipe.X / L_pipe, d_pipe.Y / L_pipe, d_pipe.Z / L_pipe)

    d_want = P_alvo - P_atual
    L_want = d_want.GetLength()
    d_want = XYZ(d_want.X / L_want, d_want.Y / L_want, d_want.Z / L_want)

    if d_pipe.DotProduct(d_want) < 0.999:
        return False  # não é o mesmo sentido/direção — precisa de joelho

    # Confere colinearidade de verdade (desvio perpendicular), não só
    # direções paralelas — mesma checagem usada na Etapa 1.
    w      = P_alvo - P_fixo
    w_proj = w.DotProduct(d_pipe)
    perp   = XYZ(w.X - d_pipe.X * w_proj,
                w.Y - d_pipe.Y * w_proj,
                w.Z - d_pipe.Z * w_proj)
    if perp.GetLength() > TOL_COLINEAR:
        return False

    pipe.Location.Curve = Line.CreateBound(P_fixo, P_alvo)
    doc.Regenerate()
    return True


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


def _free_connectors(element):
    """Conectores LIVRES (sem conexão) de element — Pipe ou FamilyInstance
    de MEP (joelho, tê, válvula etc., via MEPModel.ConnectorManager)."""
    try:
        mgr = element.ConnectorManager
    except AttributeError:
        try:
            mgr = element.MEPModel.ConnectorManager
        except Exception:
            return []
    return [c for c in mgr.Connectors if not c.IsConnected]


def _conector_livre_mais_proximo(element, pt_click):
    """Conector livre de element mais próximo de pt_click (ou qualquer um,
    se pt_click for None ou só houver um). None se não houver conector
    livre — usado pra permitir conectar pipe_desc direto num conector
    livre de um FITTING (ex.: joelho com uma ponta solta), não só na
    ponta/corpo de outro Pipe."""
    livres = _free_connectors(element)
    if not livres:
        return None
    if pt_click is None:
        return livres[0]
    return min(livres, key=lambda c: c.Origin.DistanceTo(pt_click))


def _achar_pipe_conectado(elemento, max_profundidade=6):
    """
    Busca em largura, pela rede de CONEXÕES (conectores já conectados) de
    `elemento`, o Pipe de verdade mais próximo — atravessando outros
    fittings (joelhos, tês, válvulas) no caminho, se precisar (ex.:
    joelho -> joelho -> Pipe). Usado quando pipe_ref é um FITTING sem
    Pipe próprio (conectado por um conector livre, não outro Pipe): sem
    isso, o tubo/roteamento criado herdaria um PipeType/PipingSystemType
    arbitrário (o 1º do projeto, sem relação nenhuma com o sistema de
    verdade — ver _pipe_params) em vez do tipo que o sistema realmente
    está usando ali.

    Retorna o elemento Pipe encontrado, ou None se nenhum Pipe estiver
    acessível dentro de max_profundidade saltos (ex.: fitting
    completamente isolado, sem nada conectado).
    """
    # ElementId em si (não .IntegerValue/.Value) como chave de set/dict —
    # funciona em qualquer versão do Revit (.IntegerValue foi removido no
    # Revit 2024+, substituído por .Value; ElementId já implementa
    # Equals/GetHashCode corretamente, então comparar o objeto direto
    # evita depender de qual das duas propriedades existe nesta versão).
    visitados = set([elemento.Id])
    fila = [(elemento, 0)]
    while fila:
        atual, profundidade = fila.pop(0)
        if profundidade >= max_profundidade:
            continue
        try:
            mgr = atual.ConnectorManager
        except AttributeError:
            try:
                mgr = atual.MEPModel.ConnectorManager
            except Exception:
                continue
        for c in mgr.Connectors:
            if not c.IsConnected:
                continue
            try:
                refs = c.AllRefs
            except Exception:
                continue
            for c_outro in refs:
                vizinho = c_outro.Owner
                if vizinho is None or vizinho.Id in visitados:
                    continue
                visitados.add(vizinho.Id)
                if isinstance(vizinho, Pipe):
                    return vizinho
                fila.append((vizinho, profundidade + 1))
    return None


def _pipe_params(doc, pipe):
    """Retorna (pipe_type_id, sys_type_id, level_id, diam_ft) herdados de pipe."""
    from Autodesk.Revit.DB.Plumbing import PipeType

    if not isinstance(pipe, Pipe):
        # pipe pode ser um FITTING (joelho/tê/válvula) sem PipeType
        # próprio — ex.: pipe_ref conectado por um conector livre, não
        # um Pipe de verdade (ver _FiltroPipeRef). Em vez de cair direto
        # no fallback arbitrário abaixo (1º PipeType do projeto), caça
        # primeiro um Pipe de verdade já conectado à rede desse fitting
        # e herda TUDO dele (tipo, sistema, nível, diâmetro) — é o tipo
        # que o sistema de tubulação REAL está usando ali, não um tipo
        # qualquer sem relação nenhuma com o sistema.
        pipe_conectado = _achar_pipe_conectado(pipe)
        if pipe_conectado is not None:
            return _pipe_params(doc, pipe_conectado)

    pipe_type_id = pipe.GetTypeId()
    # GetTypeId() nunca é "Invalid" pra um FamilyInstance (ex.: pipe é um
    # fitting — pipe_ref conectado por um conector livre, não um Pipe de
    # verdade) — só que o tipo que ele devolve é o da família do fitting
    # (ex.: "Joelho - Genérico 90°"), não um PipeType de verdade. Usar
    # esse Id direto em Pipe.Create derruba com "pipeTypeId is not valid
    # pipe type" — por isso confirma o TIPO do elemento resolvido, não só
    # se o Id é válido, antes de aceitar pipe_type_id como está.
    tipo_el = doc.GetElement(pipe_type_id) if pipe_type_id != ElementId.InvalidElementId else None
    if not isinstance(tipo_el, PipeType):
        pipe_type_id = ElementId.InvalidElementId

    if pipe_type_id == ElementId.InvalidElementId:
        try:
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
    if level_id == ElementId.InvalidElementId:
        # Fallback pra elementos sem ReferenceLevel (ex.: FamilyInstance de
        # fitting, quando pipe_ref é um conector livre de joelho/tê em vez
        # de outro Pipe) — LevelId existe em FamilyInstance normalmente.
        try:
            level_id = pipe.LevelId
        except Exception:
            pass

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


def _conn_dir(c):
    try:
        return c.CoordinateSystem.BasisZ
    except Exception:
        return None


def _juntar(doc, c1, c2):
    """
    Junta dois conectores que já estão no mesmo ponto (ex.: fim da rota
    encostando bem na ponta de pipe_ref). Se apontam um pro outro em linha
    reta (colineares), NewElbowFitting falha — não é uma curva de verdade,
    é uma continuação reta — então conecta direto (ConnectTo). Caso
    contrário, cria joelho normalmente. Retorna True se conseguiu (por
    qualquer um dos dois métodos).
    """
    d1, d2 = _conn_dir(c1), _conn_dir(c2)
    if d1 is not None and d2 is not None and d1.DotProduct(d2) < -0.999:
        try:
            c1.ConnectTo(c2)
            return True
        except Exception:
            pass  # cai pro joelho abaixo como última tentativa
    return _elbow(doc, c1, c2)


def _mesclar_colinear(doc, pipe_ref, pipe_desc, c_ref_end, conn_final, elbows_pend):
    """
    Se c_ref_end (ponta de pipe_ref) e conn_final (conector do último tubo
    da rota) estão colineares — de frente um pro outro, na mesma reta —
    MESCLA os dois num tubo só: estende pipe_ref até a ponta livre do
    último tubo e apaga esse tubo. ConnectTo (usado em _juntar) só liga os
    conectores logicamente; os tubos ficam dois elementos separados só
    "encostados" — o que aparecia como "o último tubo vai até o ponto do
    conector mas não conecta". Mesclar num elemento único de verdade,
    igual a Etapa 1 já faz pra pipe_desc, resolve isso pra pipe_ref.

    elbows_pend é a lista (mutável) de joelhos pendentes ainda não criados
    — se algum deles apontar pro conector "do outro lado" do tubo que vai
    ser apagado (o lado que segue pro resto da rota já construída), é
    atualizado in-place pra apontar pro novo conector de pipe_ref, senão
    aquela pendência ficaria referenciando um conector de um elemento
    apagado.

    Nunca apaga pipe_desc (mesmo que ele acabe sendo o "último tubo" via
    _tenta_estender_colinear): diferente dos segmentos criados nesta
    operação — cujas duas pontas são 100% rastreadas por elbows_pend —
    pipe_desc pode ter uma conexão pré-existente do lado oposto (fora
    desta operação) que não teríamos como recuperar depois de apagá-lo.

    Retorna True se mesclou (quem chamou não deve mais tentar
    joelho/ConnectTo — já está tudo resolvido aqui). False se não são
    colineares (ou é pipe_desc/pipe_ref) — segue o fluxo normal (joelho/Tê).
    """
    if not isinstance(pipe_ref, Pipe):
        # Fitting (joelho/tê/válvula) não é "esticável" — não tem
        # Location.Curve pra estender. Segue pro joelho normal.
        return False
    d1, d2 = _conn_dir(c_ref_end), _conn_dir(conn_final)
    if d1 is None or d2 is None or d1.DotProduct(d2) >= -0.999:
        return False

    pipe_last = conn_final.Owner
    if pipe_last.Id == pipe_ref.Id or pipe_last.Id == pipe_desc.Id:
        return False  # segurança: nunca mesclar pipe_ref/pipe_desc apagando-os

    # Conector do outro lado de pipe_last — o que segue pro resto da rota
    # já construída (None se pipe_last só tiver o próprio conn_final, ex.:
    # tubo degenerado/sem outra ponta).
    conn_outro = None
    for c in pipe_last.ConnectorManager.Connectors:
        if c.Origin.DistanceTo(conn_final.Origin) > TOL:
            conn_outro = c
            break

    p_ref_fixo = _extremo_oposto(pipe_ref.Location.Curve, c_ref_end.Origin)
    alvo = conn_outro.Origin if conn_outro is not None else conn_final.Origin
    pipe_ref.Location.Curve = Line.CreateBound(p_ref_fixo, alvo)
    doc.Regenerate()

    if conn_outro is not None:
        novo_conn = _conn_near(pipe_ref, alvo)
        if novo_conn is not None:
            for i, (pc1, pc2) in enumerate(elbows_pend):
                nc1 = novo_conn if (pc1.Owner.Id == pipe_last.Id) else pc1
                nc2 = novo_conn if (pc2.Owner.Id == pipe_last.Id) else pc2
                if nc1 is not pc1 or nc2 is not pc2:
                    elbows_pend[i] = (nc1, nc2)

    doc.Delete(pipe_last.Id)
    return True


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


_TOL_LINHA_CENTRAL = _to_ft(0.03)  # 3 cm — clique só é aceito perto da
                                    # linha central do tubo; conectores
                                    # (pontas, ramais de tê) já ficam sobre
                                    # ela, então são cobertos automaticamente


class _FiltroPipe(ISelectionFilter):
    """Só permite Pipe — e, dentro do tubo, só clique perto da linha
    central (ou de um ponto de conexão, que sempre está sobre ela), em vez
    de qualquer ponto da superfície visível do tubo (clique/pointer normal).
    doc é opcional só por compatibilidade; sem ele, cai no comportamento
    antigo (qualquer ponto do tubo é aceito)."""
    def __init__(self, doc=None):
        self.doc = doc

    def AllowElement(self, e):
        return isinstance(e, Pipe)

    def AllowReference(self, r, p):
        if self.doc is None:
            return True
        try:
            curve = self.doc.GetElement(r.ElementId).Location.Curve
            return curve.Project(p).Distance <= _TOL_LINHA_CENTRAL
        except Exception:
            return True


class _FiltroPipeRef(ISelectionFilter):
    """Filtro do clique de referência (2º clique): tudo que _FiltroPipe já
    aceita (Pipe, só perto da linha central) MAIS qualquer FamilyInstance
    de MEP com pelo menos um conector LIVRE — um joelho, tê ou válvula com
    uma ponta solta, por exemplo. Permite conectar o tubo desconectado
    direto nesse conector, sem precisar que a referência seja
    necessariamente outro Pipe. doc é obrigatório (precisa consultar o
    elemento pra checar conectores livres)."""
    def __init__(self, doc):
        self.doc = doc

    def AllowElement(self, e):
        if isinstance(e, Pipe):
            return True
        if isinstance(e, FamilyInstance):
            return bool(_free_connectors(e))
        return False

    def AllowReference(self, r, p):
        el = self.doc.GetElement(r.ElementId)
        if isinstance(el, Pipe):
            try:
                return el.Location.Curve.Project(p).Distance <= _TOL_LINHA_CENTRAL
            except Exception:
                return True
        return True  # fitting: qualquer clique nele vale (sem linha central)


def _snapshot_ids(doc):
    """
    IDs de todos os Pipe e FamilyInstance do documento — usado pra
    descobrir que elementos uma rodada de prévia criou (diff antes/depois
    de construir a conexão). Necessário porque, numa janela modeless, cada
    ciclo de prévia precisa abrir E FECHAR (Commit) sua própria transação —
    o Revit reclama de "transação aberta mas não fechada" assim que o
    comando externo (ou o ExternalEvent) que a abriu retorna, então não dá
    mais pra manter uma transação só "pendurada" entre uma troca de opção
    e a próxima, esperando o usuário decidir. Sem esse diff não teria como
    saber o que desfazer (apagar) no próximo ciclo.

    Restrito a Pipe/FamilyInstance (tubos, joelhos, tês, válvulas) — os
    únicos tipos que esse módulo cria — em vez do documento inteiro, pra
    não pesar em projetos grandes.
    """
    ids = set()
    for cls in (Pipe, FamilyInstance):
        for eid in FilteredElementCollector(doc).OfClass(cls).ToElementIds():
            ids.add(eid)
    return ids


# ============================================================================
# FORM — preferências de roteamento (altura + ordem dos eixos X/Y)
# ============================================================================

class _JanelaOpcoesRota(forms.WPFWindow):
    """Janela WPF MODELESS (connect_pipe_opcoes.xaml) com PRÉVIA AO VIVO: a
    cada troca de opção (onde conectar / ordem dos eixos), o tubo é
    reconstruído no modelo para o usuário ver o resultado antes de
    confirmar.

    Cada troca roda um ciclo completo (_ciclo_preview) que abre E FECHA
    (Commit) sua PRÓPRIA transação — o Revit não permite deixar uma
    transação "pendurada" entre uma troca de opção e a próxima (reclama de
    "transação aberta mas não fechada" assim que o comando externo que a
    abriu retorna), diferente de uma janela modal onde a mesma transação
    podia ficar aberta do início ao fim. Por isso não existe mais
    RollBack/Commit de uma transação única: cada ciclo primeiro DESFAZ
    manualmente o que o ciclo anterior criou/mudou (_elementos_criados +
    curvas originais de pipe_desc/pipe_ref, guardadas no __init__) e só
    depois constrói e já comita a prévia nova. "Cancelar" ou fechar sem
    confirmar roda esse mesmo desfazer uma última vez; "OK" não precisa
    fazer nada no documento — o que já está comitado da última prévia bem
    sucedida já É o resultado final.

    Por ser modeless (Show(), não ShowDialog() — ver run()), o Revit
    continua respondendo normalmente: dá pra orbitar, aproximar/afastar e
    girar a câmera no modelo com a janela aberta. Em compensação, qualquer
    clique nela (mudar opção, OK, Cancelar) acontece FORA do contexto de
    API válido do Revit — toda ação que toca o documento (self.fila_acoes,
    de family_loader_events.criar_fila_acoes) é enfileirada e executada
    assim que o Revit libera o contexto via ExternalEvent, nunca chamada
    direto do evento de clique.

    Ordem dos eixos: até 3 trechos retos (z = vertical, par = paralelo ao
    eixo de pipe_ref, perp = perpendicular a ele) — só os que realmente
    precisam de ajuste aparecem como opção (ver _eixos_disponiveis). O
    usuário escolhe livremente a ordem entre eles ("1º eixo" / "2º eixo";
    o que sobra é sempre o último, mostrado só como informação)."""

    _BOTOES_ORDEM1 = {u"z": u"RbO1Z", u"par": u"RbO1Par", u"perp": u"RbO1Perp"}
    _BOTOES_ORDEM2 = {u"z": u"RbO2Z", u"par": u"RbO2Par", u"perp": u"RbO2Perp"}

    def __init__(self, doc, uidoc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
                 clicou_ponta_exata=False):
        forms.WPFWindow.__init__(self, _XAML_OPCOES_PATH)
        self.doc           = doc
        self.uidoc         = uidoc
        self.pipe_desc     = pipe_desc
        self.pipe_ref      = pipe_ref
        self.pt_click_desc = pt_click_desc
        self.pt_click_ref  = pt_click_ref
        self.output        = output

        self.confirmado        = False
        self._preview_ok       = False
        self._finalizado       = False
        self._sincronizando    = False
        self._ordem_pref       = [u"z", u"par", u"perp"]
        self._elementos_criados = set()
        self.fila_acoes        = criar_fila_acoes()

        # Estado original de pipe_desc/pipe_ref (antes de qualquer prévia) —
        # cada ciclo restaura isso antes de construir a prévia nova, já que
        # _construir_conexao pode estender/quebrar essas curvas.
        loc_desc = pipe_desc.Location.Curve
        self._p0_desc_orig = loc_desc.GetEndPoint(0)
        self._p1_desc_orig = loc_desc.GetEndPoint(1)
        # pipe_ref pode ser um FITTING (joelho/tê/válvula com conector
        # livre) em vez de outro Pipe — sem Location.Curve pra guardar; a
        # prévia nunca mexe na geometria dele nesse caso (só cria
        # elementos novos em volta), então não há nada pra restaurar.
        if isinstance(pipe_ref, Pipe):
            loc_ref = pipe_ref.Location.Curve
            self._p0_ref_orig = loc_ref.GetEndPoint(0)
            self._p1_ref_orig = loc_ref.GetEndPoint(1)
        else:
            self._p0_ref_orig = None
            self._p1_ref_orig = None

        # Se o clique já caiu exatamente na ponta de pipe_ref, a resposta
        # já é óbvia (ponta) — esconde a pergunta e força a opção, em vez
        # de fazer o usuário confirmar algo que ele já decidiu com o clique.
        if clicou_ponta_exata:
            self.SecaoRef.Visibility = SW.Visibility.Collapsed

        # Marcado com _sincronizando=True: IsChecked dispara o evento
        # Checked já aqui, de forma síncrona (mesmo com a janela ainda não
        # exibida), e on_opcao_changed enfileiraria uma rodada extra de
        # _ciclo_preview via ExternalEvent — redundante (a prévia real já
        # roda logo abaixo, direto) e é a causa do aviso "ExternalEvent ...
        # retornou 'Pending'" (um 2º Raise() emendado no 1º antes do Revit
        # sequer ter devolvido o contexto de API pro fim do __init__).
        self._sincronizando = True
        try:
            if clicou_ponta_exata:
                self.RbRefPonta.IsChecked = True
            else:
                self.RbRefCorpo.IsChecked = True
        finally:
            self._sincronizando = False

        try:
            self._ciclo_preview()
        except Exception:
            # _ciclo_preview já trata os erros esperados internamente (e
            # sempre fecha a própria transação, mesmo em erro); isto é só
            # uma rede de segurança pra desfazer qualquer coisa que tenha
            # escapado antes de propagar, o que travaria o fallback (uma
            # transação por vez no documento).
            self._finalizar(False)
            raise

    def _desfazer_elementos_criados(self):
        for eid in self._elementos_criados:
            try:
                self.doc.Delete(eid)
            except Exception:
                pass
        self._elementos_criados = set()

    def _restaurar_curvas_originais(self):
        try:
            self.pipe_desc.Location.Curve = Line.CreateBound(self._p0_desc_orig, self._p1_desc_orig)
        except Exception:
            pass
        if self._p0_ref_orig is not None:
            try:
                self.pipe_ref.Location.Curve = Line.CreateBound(self._p0_ref_orig, self._p1_ref_orig)
            except Exception:
                pass

    def _finalizar(self, confirmado):
        """Fecha a prévia de vez: se confirmado, não mexe em nada — o que
        já está comitado no documento (da última prévia bem sucedida) já É
        o resultado final. Senão, desfaz tudo numa transação própria,
        aberta e fechada aqui mesmo. Chamado tanto de dentro da fila de
        ações (fechar a janela modeless) quanto direto, já num contexto de
        API válido (ex.: __init__/run(), se algo falhar antes da janela
        aparecer de verdade)."""
        if confirmado:
            return
        t = Transaction(self.doc, u"FireUtils - Conectar Tubo (descartar prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self._restaurar_curvas_originais()
        finally:
            # Sempre fecha a transação antes de sair daqui — nunca pode
            # ficar aberta, nem em erro inesperado (ver _snapshot_ids).
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass

    def _modo_conexao_ref_atual(self):
        return u"ponta" if self.RbRefPonta.IsChecked else u"corpo"

    def _ordem1_atual(self):
        for eixo, nome_btn in self._BOTOES_ORDEM1.items():
            if getattr(self, nome_btn).IsChecked:
                return eixo
        return None

    def _ordem2_atual(self):
        for eixo, nome_btn in self._BOTOES_ORDEM2.items():
            if getattr(self, nome_btn).IsChecked:
                return eixo
        return None

    def _sincronizar_ordem(self):
        """Recalcula quais eixos ainda precisam de ajuste (dado o modo de
        conexão atual) e mostra só os botões cabíveis em "1º eixo"/"2º
        eixo" — o resto (0 ou 1 eixo necessário) não precisa de escolha
        nenhuma, então a seção some. Preserva ao máximo a preferência já
        escolhida pelo usuário (self._ordem_pref)."""
        necessarios = _eixos_disponiveis(
            self.pipe_desc, self.pipe_ref, self.pt_click_desc, self.pt_click_ref,
            self._modo_conexao_ref_atual())

        ordem = [e for e in self._ordem_pref if e in necessarios]
        for e in necessarios:
            if e not in ordem:
                ordem.append(e)
        self._ordem_pref = ordem

        n = len(ordem)
        self._sincronizando = True
        try:
            self.SecaoOrdem.Visibility = (SW.Visibility.Visible if n >= 1
                                           else SW.Visibility.Collapsed)

            mostrar1 = SW.Visibility.Visible if n >= 2 else SW.Visibility.Collapsed
            self.LinhaOrdem1.Visibility = mostrar1
            self.LblOrdem1.Visibility   = mostrar1
            if n >= 2:
                for eixo, nome_btn in self._BOTOES_ORDEM1.items():
                    getattr(self, nome_btn).Visibility = (
                        SW.Visibility.Visible if eixo in ordem else SW.Visibility.Collapsed)
                getattr(self, self._BOTOES_ORDEM1[ordem[0]]).IsChecked = True

            mostrar2 = SW.Visibility.Visible if n >= 3 else SW.Visibility.Collapsed
            self.LinhaOrdem2.Visibility = mostrar2
            self.LblOrdem2.Visibility   = mostrar2
            if n >= 3:
                restantes = ordem[1:]
                for eixo, nome_btn in self._BOTOES_ORDEM2.items():
                    getattr(self, nome_btn).Visibility = (
                        SW.Visibility.Visible if eixo in restantes else SW.Visibility.Collapsed)
                getattr(self, self._BOTOES_ORDEM2[ordem[1]]).IsChecked = True

            if n == 0:
                self.TxtOrdemInfo.Text = u""
            elif n == 1:
                self.TxtOrdemInfo.Text = u"Único ajuste necessário: {}".format(_NOME_EIXO[ordem[0]])
            else:
                self.TxtOrdemInfo.Text = u"Por último: {}".format(_NOME_EIXO[ordem[-1]])
        finally:
            self._sincronizando = False

    def _ciclo_preview(self):
        """Um ciclo completo de prévia, numa transação própria aberta E
        fechada aqui mesmo (nunca deixada pendurada — ver docstring da
        classe): desfaz o que o ciclo anterior criou/mudou, sincroniza as
        opções de ordem disponíveis e reconstrói a conexão com as opções
        atuais. Em erro de validação/inesperado, desfaz de novo (deixa o
        modelo em branco, sem a prévia) e mostra o aviso em TxtStatus."""
        t = Transaction(self.doc, u"FireUtils - Conectar Tubo")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self._restaurar_curvas_originais()
            self.doc.Regenerate()
            self._sincronizar_ordem()

            ids_antes = _snapshot_ids(self.doc)
            erro = None
            try:
                _construir_conexao(
                    self.doc, self.pipe_desc, self.pipe_ref,
                    self.pt_click_desc, self.pt_click_ref, self.output,
                    ordem_eixos=self._ordem_pref,
                    modo_conexao_ref=self._modo_conexao_ref_atual(),
                )
                self.doc.Regenerate()
            except _ConexaoError as ex:
                erro = u"{}".format(ex)
            except Exception as ex:
                erro = u"Erro na prévia: {}".format(ex)
            self._elementos_criados = _snapshot_ids(self.doc) - ids_antes

            if erro is not None:
                self._desfazer_elementos_criados()
                self._restaurar_curvas_originais()
                self.doc.Regenerate()
                self._preview_ok = False
                self.TxtStatus.Text       = erro
                self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
            else:
                self._preview_ok = True
                self.TxtStatus.Text       = u""
                self.TxtStatus.Foreground = self.Resources[u"BrushOk"]
        finally:
            # Sempre fecha a transação antes de sair daqui — nunca pode
            # ficar aberta, nem em erro inesperado (ver _snapshot_ids).
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
        """Pede pro Revit rodar _ciclo_preview assim que liberar o contexto
        de API — toca o documento (transação), então não pode rodar direto
        do evento de clique numa janela modeless."""
        def _acao(uiapp):
            self._ciclo_preview()
        self.fila_acoes.enfileirar(_acao)

    def on_opcao_changed(self, sender, args):
        if self._sincronizando:
            return
        self._agendar_atualizacao()

    def on_ordem1_changed(self, sender, args):
        if self._sincronizando:
            return
        novo = self._ordem1_atual()
        if novo is not None:
            self._ordem_pref = [novo] + [e for e in self._ordem_pref if e != novo]
        self._agendar_atualizacao()

    def on_ordem2_changed(self, sender, args):
        if self._sincronizando:
            return
        novo2 = self._ordem2_atual()
        if novo2 is not None and self._ordem_pref:
            primeiro = self._ordem_pref[0]
            self._ordem_pref = ([primeiro, novo2] +
                                 [e for e in self._ordem_pref if e not in (primeiro, novo2)])
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
        """Sempre finaliza a prévia ao fechar — mantém o resultado comitado
        só se o usuário clicou OK; qualquer outro fechamento desfaz tudo.
        Fechar a janela em si (Close/Hide) é só WPF, não precisa de contexto
        de API — mas desfazer toca o documento, então vai pra fila de ações
        em vez de rodar direto aqui."""
        if self._finalizado:
            return
        self._finalizado = True
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        confirmado = self.confirmado

        def _acao(uiapp):
            self._finalizar(confirmado)
        self.fila_acoes.enfileirar(_acao)


def _escolher_opcoes_rota_fallback(pipe_desc, pipe_ref, pt_click_desc, pt_click_ref,
                                    clicou_ponta_exata=False):
    if clicou_ponta_exata:
        # Clique já caiu exatamente na ponta de pipe_ref — resposta óbvia,
        # pula a pergunta em vez de fazer o usuário confirmar o óbvio.
        modo_conexao_ref = u"ponta"
    else:
        escolha_ref = forms.SelectFromList.show(
            [u"Ponto clicado", u"Ponta livre"],
            title=u"Fire Utils — Conectar Tubo",
            prompt=u"Onde conectar no tubo de referência?",
            multiselect=False
        )
        if not escolha_ref:
            return None
        modo_conexao_ref = u"ponta" if escolha_ref.startswith(u"Ponta") else u"corpo"

    # Só pergunta a ordem dos eixos que realmente vão existir na rota —
    # um tubo já alinhado num eixo não aparece como escolha.
    necessarios = _eixos_disponiveis(pipe_desc, pipe_ref, pt_click_desc, pt_click_ref,
                                      modo_conexao_ref)
    ordem_eixos = [u"z", u"par", u"perp"]

    if len(necessarios) >= 2:
        escolha1 = forms.SelectFromList.show(
            [_NOME_EIXO[e] for e in necessarios],
            title=u"Fire Utils — Conectar Tubo",
            prompt=u"Qual eixo alinhar primeiro?",
            multiselect=False
        )
        if not escolha1:
            return None
        primeiro  = [e for e in necessarios if _NOME_EIXO[e] == escolha1][0]
        restantes = [e for e in necessarios if e != primeiro]

        if len(restantes) >= 2:
            escolha2 = forms.SelectFromList.show(
                [_NOME_EIXO[e] for e in restantes],
                title=u"Fire Utils — Conectar Tubo",
                prompt=u"E depois?",
                multiselect=False
            )
            if not escolha2:
                return None
            segundo   = [e for e in restantes if _NOME_EIXO[e] == escolha2][0]
            terceiro  = [e for e in restantes if e != segundo][0]
            ordem_eixos = [primeiro, segundo, terceiro]
        else:
            ordem_eixos = [primeiro] + restantes

    return ordem_eixos, modo_conexao_ref


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

_CHAVE_JANELA_ATIVA = u"FireUtils_ConectarTubo_JanelaAtiva"


def run(doc, uidoc, output):
    # Janela de prévia é modeless (Show, não ShowDialog) — nada impede o
    # usuário de chamar o comando de novo com a anterior ainda aberta; como
    # o Revit só permite uma transação aberta por documento, uma segunda
    # instância pisaria na transação da primeira. Só traz a existente pra
    # frente em vez de abrir outra.
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_ATIVA)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)

    # ── Clique 1: ponta do PIPE_DESC ────────────────────────────────────────
    try:
        ref1         = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipe(doc),
            u"[1/2] Clique em uma PONTA do tubo desconectado"
        )
        pipe_desc    = doc.GetElement(ref1.ElementId)
        pt_click_desc = _global_pt(ref1)
    except Exception:
        pyscript.exit()

    # ── Clique 2: PIPE_REF (corpo, ponta, ou conector livre de um fitting) ──
    try:
        ref2         = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipeRef(doc),
            u"[2/2] Clique no tubo referência (corpo para Tê, ponta para "
            u"joelho) ou no conector livre de um joelho/tê/válvula"
        )
        pipe_ref     = doc.GetElement(ref2.ElementId)
        pt_click_ref = _global_pt(ref2)
    except Exception:
        pyscript.exit()

    if pipe_ref.Id == pipe_desc.Id:
        forms.alert(u"Os dois tubos selecionados são o mesmo elemento.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    # Clique caiu exatamente numa ponta de pipe_ref (ou pipe_ref é um
    # FITTING, que só tem o modo "ponta" — conector livre, sem corpo pra
    # Tê)? Se sim, a resposta pra "onde conectar no tubo de referência?"
    # já é óbvia — pula a pergunta.
    if not isinstance(pipe_ref, Pipe):
        clicou_ponta_exata = True
    else:
        clicou_ponta_exata = False
        if pt_click_ref is not None:
            loc_ref_click = pipe_ref.Location.Curve
            pt_a_click = loc_ref_click.GetEndPoint(0)
            pt_b_click = loc_ref_click.GetEndPoint(1)
            clicou_ponta_exata = (pt_click_ref.DistanceTo(pt_a_click) < TOL_SEG or
                                   pt_click_ref.DistanceTo(pt_b_click) < TOL_SEG)

    # ── Preferências de roteamento, com prévia ao vivo no modelo ────────────
    # Show() (modeless), não ShowDialog() — deixa o Revit responder
    # normalmente (orbitar/zoom/pan) com a janela aberta. Ver docstring de
    # _JanelaOpcoesRota sobre como isso afeta o toque no documento.
    janela = None
    try:
        janela = _JanelaOpcoesRota(doc, uidoc, pipe_desc, pipe_ref,
                                    pt_click_desc, pt_click_ref, output,
                                    clicou_ponta_exata=clicou_ponta_exata)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, janela)
        janela.Show()
        return
    except Exception as ex:
        # Se falhar depois da janela já ter aberto (ex.: erro ao exibir),
        # garante que a transação da prévia não fique presa — senão o
        # fallback abaixo não conseguiria abrir a dele (só uma por vez).
        if janela is not None:
            janela._finalizar(False)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        print(u"[AVISO] Formulário WPF com prévia de Conectar Tubo falhou ({}), "
              u"usando formulário padrão do pyRevit (sem prévia).".format(ex))

    opcoes = _escolher_opcoes_rota_fallback(pipe_desc, pipe_ref, pt_click_desc, pt_click_ref,
                                             clicou_ponta_exata=clicou_ponta_exata)
    if opcoes is None:
        pyscript.exit()
    ordem_eixos, modo_conexao_ref = opcoes

    _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
               ordem_eixos=ordem_eixos, modo_conexao_ref=modo_conexao_ref)


# ============================================================================
# LÓGICA DE CONEXÃO
# ============================================================================

class _ConexaoError(Exception):
    """Falha de validação/criação conhecida — mensagem já pronta para o
    usuário (alerta no fluxo sem prévia, texto de status no fluxo com
    prévia). Erros inesperados propagam como Exception normal."""
    pass


def _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref):
    """
    Escolhe a ponta LIVRE (sem conexão) de pipe_ref pra conectar via joelho.
    Se as duas pontas estiverem livres, usa a mais próxima do clique (ou de
    pt_A, se não houver clique). Levanta _ConexaoError se nenhuma ponta
    estiver livre. Retorna o XYZ da ponta escolhida.
    """
    c_a = _conn_near(pipe_ref, pt_A)
    c_b = _conn_near(pipe_ref, pt_B)
    livre_a = c_a is not None and not c_a.IsConnected
    livre_b = c_b is not None and not c_b.IsConnected

    if livre_a and livre_b:
        ref = pt_click_ref if pt_click_ref is not None else pt_A
        return pt_A if ref.DistanceTo(pt_A) < ref.DistanceTo(pt_B) else pt_B
    if livre_a:
        return pt_A
    if livre_b:
        return pt_B
    raise _ConexaoError(
        u"O tubo de referência não tem nenhuma ponta livre para conectar — "
        u"as duas pontas já estão conectadas a outros elementos.")


def _ajustar_alvo_corpo_invertido(pipe_ref, pt_A, pt_B, d_ref, P_mid, pt_click_ref):
    """
    Corpo (Tê) + ordem invertida + ainda sobra 2º trecho: o 1º trecho, ao
    fechar o desvio perpendicular inteiro, sempre termina EXATAMENTE sobre
    a reta infinita de pipe_ref (matemática garantida, não depende de onde
    foi o clique) — só falta saber se esse ponto (P_mid) cai dentro do
    corpo FÍSICO de pipe_ref (entre pt_A e pt_B) ou fora dele:

      dentro → já tem tubo ali pra conectar: usa o próprio P_mid como
               alvo do Tê, dispensando o 2º trecho (que rodaria por cima
               do próprio pipe_ref até o ponto clicado originalmente).
      fora   → não tem tubo naquele ponto da reta; cai para a ponta LIVRE
               mais próxima de pipe_ref (rota recalculada para esse novo
               alvo, agora em modo joelho).

    Retorna ("corpo", P_mid) ou ("ponta", pt_endpoint).
    """
    L_ref = pt_A.DistanceTo(pt_B)
    t_mid = (P_mid - pt_A).DotProduct(d_ref)
    if -TOL <= t_mid <= L_ref + TOL:
        return u"corpo", P_mid
    return u"ponta", _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref)


def _construir_conexao(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
                        ordem_eixos=(u"z", u"par", u"perp"),
                        modo_conexao_ref=u"auto"):
    """
    Lógica pura de conexão — NÃO abre/fecha transação (fica a cargo de
    quem chama: _conectar, no fluxo direto, ou a janela de prévia, que
    reconstrói isso a cada mudança de opção dentro da MESMA transação).

    ordem_eixos : ordem de preferência em que os até 3 trechos retos da
                              rota são fechados — "z" (vertical), "par"
                              (paralelo ao eixo de pipe_ref) e "perp"
                              (perpendicular a ele), ex.:
                              (u"z", u"par", u"perp"). Só os eixos
                              realmente necessários (ver _eixos_necessarios)
                              entram na rota de verdade — os demais
                              elementos de ordem_eixos, se houver, são
                              ignorados. O trecho executado primeiro tenta
                              prolongar o próprio pipe_desc em vez de criar
                              tubo + joelho, se pipe_desc já apontar
                              naquela direção (ver _tenta_estender_colinear,
                              ou a extensão direta de tubo vertical, se
                              pipe_desc já for vertical e o 1º eixo for
                              "z").
    modo_conexao_ref : escolhe ponta vs corpo em pipe_ref — decisão do
                              usuário, não mais adivinhada pela distância do
                              clique (raio de tolerância dava falso positivo
                              em pipe_ref curto).
                        "ponta" → força joelho na ponta LIVRE de pipe_ref
                              (a mais próxima do clique, se as duas
                              estiverem livres); _ConexaoError se nenhuma
                              ponta estiver livre.
                        "corpo" → força Tê no ponto clicado (projetado no
                              corpo de pipe_ref), mesmo perto de uma ponta.
                        "auto"  (compatibilidade, sem diálogo) → heurística
                              antiga por proximidade do clique.
    """

    eh_fitting_ref = not isinstance(pipe_ref, Pipe)

    # ── Endpoint de PIPE_DESC selecionado pelo clique ────────────────────────
    if pt_click_desc is not None:
        conn_desc = _conn_nearest(pipe_desc, pt_click_desc)
    elif eh_fitting_ref:
        conn_ref_fb = _conector_livre_mais_proximo(pipe_ref, None)
        mid_fb = (conn_ref_fb.Origin if conn_ref_fb is not None
                  else pipe_desc.Location.Curve.GetEndPoint(0))
        conn_desc = _conn_nearest(pipe_desc, mid_fb)
    else:
        loc_fb = pipe_ref.Location.Curve
        mid_fb = XYZ((loc_fb.GetEndPoint(0).X + loc_fb.GetEndPoint(1).X) / 2,
                     (loc_fb.GetEndPoint(0).Y + loc_fb.GetEndPoint(1).Y) / 2,
                     (loc_fb.GetEndPoint(0).Z + loc_fb.GetEndPoint(1).Z) / 2)
        conn_desc = _conn_nearest(pipe_desc, mid_fb)

    if conn_desc is None:
        raise _ConexaoError(u"Não foi possível encontrar conector no tubo desconectado.")

    if conn_desc.IsConnected:
        raise _ConexaoError(
            u"A ponta selecionada do tubo já está conectada a outro elemento.\n"
            u"Selecione uma ponta livre (sem conexão).")

    P_start = conn_desc.Origin

    # ── Geometria de PIPE_REF ────────────────────────────────────────────────
    # pipe_ref pode ser um FITTING (joelho/tê/válvula) com conector livre em
    # vez de outro Pipe — nesse caso só "ponta" faz sentido (sem corpo pra
    # abrir Tê) e o alvo já é o próprio conector livre, não uma projeção
    # num segmento (ver _preparar_alvo_nominal).
    if eh_fitting_ref:
        modo_conexao_ref = u"ponta"
        conn_ref_livre = _conector_livre_mais_proximo(pipe_ref, pt_click_ref)
        if conn_ref_livre is None:
            raise _ConexaoError(
                u"O elemento de referência não tem nenhum conector livre para conectar.")
        pt_A = pt_B = conn_ref_livre.Origin
        d_ref        = _conn_dir(conn_ref_livre)
        clicou_ponta = True
        pt_endpoint  = pt_A
    else:
        loc_ref = pipe_ref.Location.Curve
        pt_A    = loc_ref.GetEndPoint(0)
        pt_B    = loc_ref.GetEndPoint(1)
        d_ref   = (pt_B - pt_A).Normalize()

        # ── Modo de conexão: ponta ou corpo? ────────────────────────────────
        # Decisão explícita do usuário via diálogo, por padrão — não é mais
        # adivinhada por um raio de tolerância (dava falso positivo em
        # pipe_ref curto: corpo inteiro "parecia" ponta).
        if modo_conexao_ref == u"ponta":
            clicou_ponta = True
            pt_endpoint  = _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref)
        elif modo_conexao_ref == u"corpo":
            clicou_ponta = False
            pt_endpoint  = None
        elif pt_click_ref is not None:
            # "auto" (compatibilidade, sem diálogo) — heurística antiga por
            # proximidade do clique, com raio proporcional ao comprimento de
            # pipe_ref (até o teto de TOL_PONTA_REF).
            L_ref          = pt_A.DistanceTo(pt_B)
            tol_ponta_ref  = min(TOL_PONTA_REF, L_ref * 0.25)
            da = pt_click_ref.DistanceTo(pt_A)
            db = pt_click_ref.DistanceTo(pt_B)
            clicou_ponta = da < tol_ponta_ref or db < tol_ponta_ref
            pt_endpoint  = pt_A if da < db else pt_B
        else:
            clicou_ponta = False
            pt_endpoint  = None

    # ── Etapa 1: extensão direta ─────────────────────────────────────────────
    # Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref,
    # apenas estende e conecta sem criar tubos extras. Só roda no modo "auto"
    # (compatibilidade, sem diálogo) — com ponta/corpo escolhidos
    # explicitamente pelo usuário, pular esse atalho evita que o resultado
    # saia "silenciosamente" diferente do que foi pedido no diálogo. Nunca
    # roda pra pipe_ref fitting (sempre "ponta", nunca "auto").
    loc_desc = pipe_desc.Location.Curve
    p_desc_0 = loc_desc.GetEndPoint(0)
    p_desc_1 = loc_desc.GetEndPoint(1)
    L_desc   = p_desc_0.DistanceTo(p_desc_1)
    if not eh_fitting_ref and modo_conexao_ref == u"auto" and L_desc > TOL:
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
                        _juntar(doc, c_ponta, conn_end)
                else:
                    _tee(doc, pipe_ref, P_int, conn_end)
            return

        # Caso colinear: tubos alinhados ponta a ponta.
        # dot_par só confirma que as direções são PARALELAS — dois tubos
        # paralelos porém em retas diferentes (ex.: alturas/afastamentos
        # distintos) NÃO são colineares. Sem checar o desvio perpendicular,
        # o trecho abaixo ligaria P_other direto a pt_A/pt_B criando um
        # tubo diagonal (fora de esquadro) em vez de rotear em ângulo reto.
        dot_par = abs(d_ext.DotProduct(d_ref))
        if dot_par > 0.99:
            w      = pt_A - P_start
            w_proj = w.DotProduct(d_ext)
            perp   = XYZ(w.X - d_ext.X * w_proj,
                        w.Y - d_ext.Y * w_proj,
                        w.Z - d_ext.Z * w_proj)
            if perp.GetLength() > TOL_COLINEAR:
                dot_par = 0.0  # paralelo mas não colinear → cai para o roteamento em L
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
                if P_start.DistanceTo(pt_join) > TOL:
                    pipe_desc.Location.Curve = Line.CreateBound(P_other, pt_join)
                    doc.Regenerate()
                conn_end = _conn_near(pipe_desc, pt_join)
                c_ep     = _conn_near(pipe_ref,  pt_join)
                if conn_end and c_ep:
                    conn_end.ConnectTo(c_ep)
                return

    # ── Etapa 2: roteamento genérico em até 3 trechos retos ───────────────────
    # Alvo NOMINAL da conexão em pipe_ref (antes de qualquer redirecionamento
    # por sobreposição, decidido mais abaixo já com a ordem escolhida).
    if not clicou_ponta:
        ref_proj = pt_click_ref if pt_click_ref is not None else P_start
        P_target = _projetar_segmento(ref_proj, pt_A, pt_B)
    else:
        P_target = None
    P_final = pt_endpoint if clicou_ponta else P_target

    if (not clicou_ponta and P_start.DistanceTo(P_final) <= TOL_SEG
            and abs(P_start.Z - P_final.Z) <= TOL_DZ):
        raise _ConexaoError(u"Os tubos já estão alinhados — nenhuma conexão necessária.")

    necessarios = _eixos_necessarios(P_start, P_final, d_ref)
    ordem_ativa = [e for e in ordem_eixos if e in necessarios]
    for e in necessarios:
        if e not in ordem_ativa:
            ordem_ativa.append(e)

    # Corpo + a ordem escolhida fecha o trecho perpendicular ANTES do
    # paralelo, já na cota de pipe_ref (sem outro trecho de Z pelo meio): o
    # ponto onde o perpendicular termina cai, por construção, EXATAMENTE
    # sobre a reta infinita de pipe_ref — se isso acontece antes do
    # paralelo, o trecho paralelo posterior rodaria por cima do próprio
    # pipe_ref. _ajustar_alvo_corpo_invertido decide o que fazer com isso
    # ANTES de criar o trecho paralelo: ponto dentro do corpo físico →
    # conecta ali mesmo (Tê), dispensa o paralelo; fora → cai pra ponta
    # LIVRE mais próxima (modo joelho).
    if modo_conexao_ref == u"corpo" and not clicou_ponta and u"perp" in ordem_ativa and u"par" in ordem_ativa:
        i_perp  = ordem_ativa.index(u"perp")
        i_par   = ordem_ativa.index(u"par")
        z_antes = u"z" not in ordem_ativa or ordem_ativa.index(u"z") < i_perp
        if i_perp < i_par and z_antes:
            P_mid_check, _, _ = _rota_ate_endpoint(
                XYZ(P_start.X, P_start.Y, P_final.Z), P_final, d_ref, inverter_eixos=True)
            modo_resultado, alvo = _ajustar_alvo_corpo_invertido(
                pipe_ref, pt_A, pt_B, d_ref, P_mid_check, pt_click_ref)
            if modo_resultado == u"corpo":
                P_final = alvo
            else:
                clicou_ponta = True
                P_final = alvo
            necessarios = _eixos_necessarios(P_start, P_final, d_ref)
            ordem_ativa = [e for e in ordem_eixos if e in necessarios]
            for e in necessarios:
                if e not in ordem_ativa:
                    ordem_ativa.append(e)

    pt_id, sys_id, _,      diam_ft = _pipe_params(doc, pipe_desc)
    _,     _,      lvl_id, _       = _pipe_params(doc, pipe_ref)

    _elbows_pend   = []
    conn_cur       = conn_desc
    P_cur          = P_start
    primeira_perna = True
    d_perp         = _perp_horizontal(d_ref)
    dirs_horiz     = {u"par": d_ref, u"perp": d_perp}

    for eixo in ordem_ativa:
        if eixo == u"z":
            P_next  = XYZ(P_cur.X, P_cur.Y, P_final.Z)
            tol_leg = TOL_DZ
        else:
            d_eixo = dirs_horiz[eixo]
            delta  = (P_final.X - P_cur.X) * d_eixo.X + (P_final.Y - P_cur.Y) * d_eixo.Y
            P_next = XYZ(P_cur.X + d_eixo.X * delta, P_cur.Y + d_eixo.Y * delta, P_cur.Z)
            tol_leg = TOL_SEG

        if P_cur.DistanceTo(P_next) <= tol_leg:
            continue

        estendeu = False
        if primeira_perna and eixo == u"z" and _pipe_is_vertical(pipe_desc):
            # pipe_desc já é vertical: estende/encolhe a própria curva até
            # a nova cota (só move a ponta livre) em vez de criar tubo +
            # joelho — o sentido (subir ou descer) não importa aqui, só a
            # coordenada final.
            c = pipe_desc.Location.Curve
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            if p0.DistanceTo(P_cur) < p1.DistanceTo(P_cur):
                pipe_desc.Location.Curve = Line.CreateBound(XYZ(p0.X, p0.Y, P_next.Z), p1)
            else:
                pipe_desc.Location.Curve = Line.CreateBound(p0, XYZ(p1.X, p1.Y, P_next.Z))
            doc.Regenerate()
            conn_cur = _conn_near(pipe_desc, P_next)
            estendeu = True
        elif primeira_perna:
            # Se pipe_desc já aponta reto para P_next, prolonga o próprio
            # tubo em vez de criar um segmento novo + joelho desnecessário.
            P_other_desc = _extremo_oposto(pipe_desc.Location.Curve, P_cur)
            estendeu = _tenta_estender_colinear(doc, pipe_desc, P_other_desc, P_cur, P_next)
            if estendeu:
                conn_cur = _conn_near(pipe_desc, P_next)

        if not estendeu:
            seg   = _mk_pipe(doc, P_cur, P_next, pt_id, sys_id, lvl_id, diam_ft)
            c_ini = _conn_near(seg, P_cur)
            c_fim = _conn_near(seg, P_next)
            _elbows_pend.append((conn_cur, c_ini))
            conn_cur = c_fim

        P_cur          = P_next
        primeira_perna = False

    conn_final = conn_cur

    # ── Conexão final a pipe_ref: Tê (modo corpo) ou joelho (modo ponta) ──────
    if not clicou_ponta:
        if conn_final:
            doc.Regenerate()
            _TOL_PONTA_GEO = _to_ft(0.05)
            at_end_a = P_final.DistanceTo(pt_A) < _TOL_PONTA_GEO
            at_end_b = P_final.DistanceTo(pt_B) < _TOL_PONTA_GEO
            if at_end_a or at_end_b:
                pt_ponta = pt_A if at_end_a else pt_B
                c_ponta  = _conn_near(pipe_ref, pt_ponta)
                if c_ponta:
                    # Colinear (reta contínua): mescla os dois tubos num só
                    # em vez de só ConnectTo (que deixava dois elementos
                    # separados, só "encostados", sem virar um segmento
                    # único de verdade). Se não for colinear, _juntar cria
                    # o joelho normalmente.
                    ok = _mesclar_colinear(doc, pipe_ref, pipe_desc, c_ponta, conn_final, _elbows_pend)
                    if not ok:
                        ok = _juntar(doc, c_ponta, conn_final)
                    if not ok:
                        output.print_md(u"| Conexão na ponta | **falhou** |")
            else:
                ok = _tee(doc, pipe_ref, P_final, conn_final)
                if not ok:
                    output.print_md(u"| Tê | **falhou** — verifique se há família de tê carregada |")

            doc.Regenerate()
            for c1, c2 in _elbows_pend:
                _juntar(doc, c1, c2)

    else:
        doc.Regenerate()
        c_ref_end = _conn_near(pipe_ref, P_final)
        if c_ref_end and conn_final:
            # Idem: colinear vira mescla (um tubo só), não ConnectTo nem
            # joelho — ver _mesclar_colinear/_juntar.
            ok = _mesclar_colinear(doc, pipe_ref, pipe_desc, c_ref_end, conn_final, _elbows_pend)
            if not ok:
                ok = _juntar(doc, c_ref_end, conn_final)
            if not ok:
                output.print_md(
                    u"| Conexão na ponta | **falhou** — "
                    u"verifique se o endpoint de pipe_ref está livre |")

        doc.Regenerate()
        for c1, c2 in _elbows_pend:
            _juntar(doc, c1, c2)


def _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
              ordem_eixos=(u"z", u"par", u"perp"), modo_conexao_ref=u"auto"):
    """Fluxo direto (sem prévia) — abre/fecha a transação e mostra alerta em
    caso de falha. Usado como fallback quando a janela de prévia falha."""
    with Transaction(doc, u"FireUtils - Conectar Tubo") as t:
        t.Start()
        try:
            _construir_conexao(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref,
                                output, ordem_eixos=ordem_eixos,
                                modo_conexao_ref=modo_conexao_ref)
            t.Commit()
        except _ConexaoError as ex:
            t.RollBack()
            forms.alert(u"{}".format(ex), title=u"Fire Utils", warn_icon=True)
        except Exception as ex:
            t.RollBack()
            forms.alert(
                u"Erro ao criar a conexão:\n{}".format(str(ex)),
                title=u"Fire Utils – Erro",
                warn_icon=True)
