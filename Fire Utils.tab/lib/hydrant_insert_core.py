# -*- coding: utf-8 -*-
"""
hydrant_insert_core.py — Fire Utils · lib/
Lógica central de inserção de hidrante/coluna de hidrantes.

Chamado pelo único botão de inserção de hidrante do projeto:
  - Inserir Hidrante por Nível → run_coluna_multilevel(doc, uidoc, output)

Cobre tanto um hidrante único (1 nível marcado — ver _construir_ramal_unico,
sem erguer coluna nenhuma, igual ao antigo "Inserir Hidrante"/"Inserir
Hidrante com Abrigo", removidos por este botão já cobrir os dois casos)
quanto uma coluna vertical de verdade atravessando vários níveis de uma
vez (2+ níveis — ver _construir_coluna), com um ramal horizontal + válvula
(e, opcionalmente, abrigo de mangueira) em cada nível escolhido.

Usa um diálogo MODELESS com PRÉVIA AO VIVO (mesmo padrão de
connect_pipe.py/connect_shelter_core_preview.py) pra escolher os níveis, se
tem abrigo, a orientação da válvula/ramal e o lado do abrigo em relação à
válvula — cada opção de orientação/lado é um botão único que rotaciona pra
próxima escolha a cada clique (ver _ORDEM_DIRECAO/_ORDEM_LADO). Ver
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
    FilteredElementCollector,
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
# Reexportados daqui (mantidos importáveis como hydrant_insert_core.X pra
# não quebrar quem já importava assim) mas definidos em hydrant_shared —
# ver docstring do módulo sobre por quê.
from hydrant_shared import (
    ALTURA_VALVULA_M, COMP_HORIZ_M, DIAM_RAMAL_M, TOL,
    _setar_diametro_ft, _angulo_entre, _conector_mais_proximo,
)

TOL_FIM          = 0.05   # metros — distância máxima ao endpoint para ser "ponta"

_LIB_DIR           = os.path.dirname(os.path.abspath(__file__))
_XAML_COLUNA_PATH  = os.path.join(_LIB_DIR, u"hydrant_coluna_opcoes.xaml")


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
# OPÇÕES DE DIREÇÃO (botão único de rotação — substitui o clique de direção)
# ===========================================================================
# Sem tubo/fitting de referência (modo livre): direções globais do projeto.
# Com referência: direções relativas ao eixo do tubo/fitting selecionado —
# "frente" é o próprio eixo, "direita" é _direita_de(eixo). Os nomes das
# chaves (frente/tras/esquerda/direita) são sempre os mesmos. Um clique só
# no botão (ver on_direcao_click nas janelas abaixo) avança pra próxima
# chave de _ORDEM_DIRECAO, em vez de uma grade de 4 botões — sentido
# horário: Frente → Direita → Trás → Esquerda → Frente… O botão não mostra
# o valor atual (só o ícone) — o usuário acompanha pela prévia ao vivo.
_ORDEM_DIRECAO = [u"frente", u"direita", u"tras", u"esquerda"]
_ORDEM_LADO    = [u"direita", u"esquerda"]


def _proximo_na_lista(lista, atual):
    """Próximo item de lista após atual, voltando ao início no final —
    usada pelo botão único de rotação (direção/lado) a cada clique."""
    return lista[(lista.index(atual) + 1) % len(lista)]


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
    cruzeta) já ordenados por _ordenar_conectores — usado pelo ponto
    onde a coluna multinível cruza/termina um tubo de origem. Retorna o
    fitting criado — quem chama é responsável por _rastrear() o
    resultado (ver _construir_coluna), senão ele nunca é desfeito entre
    um ciclo de prévia e outro.
    """
    conectores = [c for c in conectores if c is not None]
    ord_ = _ordenar_conectores(conectores)
    n = len(ord_)
    if n == 2:
        return doc.Create.NewElbowFitting(ord_[0], ord_[1])
    elif n == 3:
        return doc.Create.NewTeeFitting(ord_[0], ord_[1], ord_[2])
    elif n == 4:
        return doc.Create.NewCrossFitting(ord_[0], ord_[1], ord_[2], ord_[3])
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

    # PickObject primeiro — Esc não cancela o comando, só pula pro modo
    # livre (PickPoint de ponto qualquer).
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
    nivel_ref_origem = None
    if tubo_origem is not None:
        loc_o = tubo_origem.Location.Curve
        pt_origem = _projetar_no_eixo(pt_clique, loc_o.GetEndPoint(0), loc_o.GetEndPoint(1))
        pt_clique = XYZ(pt_origem.X, pt_origem.Y, pt_clique.Z)
        z_origem  = pt_origem.Z
        dir_principal = _direcao_horizontal(tubo_origem)
        try:
            nivel_ref_origem = tubo_origem.ReferenceLevel
        except Exception:
            pass

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
        u"nivel_ref_origem": nivel_ref_origem,
        u"modo_livre": (tubo_origem is None),
        u"pipe_type_id": pipe_type_id, u"sys_type_id": sys_type_id,
    }


def _construir_ramal_unico(doc, ctx, nivel, dir_saida, inserir_abrigo, dir_abrigo):
    """
    Caso especial de _construir_coluna quando só 1 nível está marcado —
    não existe "coluna" nenhuma (base==topo não forma um tubo vertical
    de verdade): constrói um ramal único, igual ao antigo botão "Inserir
    Hidrante"/"Inserir Hidrante com Abrigo" (removidos — esta função
    cobre os dois casos agora). Sub-tubo vertical só se preciso vencer a
    diferença de cota até tubo_origem (nenhum em modo livre, ou quando
    tubo_origem já é vertical — nesse caso o ramal sai direto do corpo
    dele na altura da válvula), ramal horizontal, válvula e, se marcado,
    abrigo.

    A conexão a tubo_origem (joelho na ponta / tê no meio, via
    PlumbingUtils.BreakCurve) roda SEMPRE, inclusive durante um ciclo de
    prévia — é destrutiva num elemento pré-existente (corta/estende a
    curva dele), mas isso é seguro aqui porque quem chama (ver
    _JanelaOpcoesColuna._restaurar_curva_origem) restaura a curva
    original de tubo_origem no início de CADA ciclo, antes de chamar
    esta função de novo — mesmo padrão que connect_pipe.py já usa pra
    pipe_ref. Isso é o que permite a prévia detectar ao vivo uma falha
    de espaço/sobreposição ao criar o joelho/tê (ex.: Revit recusa por
    falta de reta livre), em vez de só descobrir na hora de confirmar —
    qualquer aviso retornado aqui bloqueia a confirmação (ver
    _JanelaOpcoesColuna._ciclo_preview).
    """
    comp_horiz_ft     = _to_ft(COMP_HORIZ_M)
    altura_valvula_ft = _to_ft(ALTURA_VALVULA_M)
    diam_ft           = _to_ft(DIAM_RAMAL_M)
    tol_fim_ft        = _to_ft(TOL_FIM)

    simbolo        = ctx[u"simbolo"]
    simbolo_abrigo = ctx[u"simbolo_abrigo"]
    tubo_origem    = ctx[u"tubo_origem"]
    pt_clique      = ctx[u"pt_clique"]
    z_origem       = ctx[u"z_origem"]
    pipe_type_id   = ctx[u"pipe_type_id"]
    sys_type_id    = ctx[u"sys_type_id"]

    z_valvula = nivel.Elevation + altura_valvula_ft

    if tubo_origem is None:
        pt_ramal         = XYZ(pt_clique.X, pt_clique.Y, z_valvula)
        tubo_eh_vertical = False
        pt_A = pt_B      = pt_ramal
    else:
        pt_ramal         = XYZ(pt_clique.X, pt_clique.Y, z_origem)
        tubo_eh_vertical = _pipe_is_vertical(tubo_origem)
        loc_o = tubo_origem.Location.Curve
        pt_A, pt_B = loc_o.GetEndPoint(0), loc_o.GetEndPoint(1)

    z_tubo = pt_ramal.Z
    if tubo_eh_vertical:
        # tubo_origem já é vertical: ramal sai direto do corpo dele na
        # altura da válvula, sem sub-tubo vertical próprio — o ponto de
        # conexão em tubo_origem passa a ser pt_joelho (mesma coluna
        # X/Y, Z = altura da válvula), não mais o pt_ramal original.
        pt_joelho    = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        tem_vertical = False
        pt_conexao   = pt_joelho
    else:
        pt_joelho    = XYZ(pt_ramal.X, pt_ramal.Y, z_valvula)
        tem_vertical = abs(z_valvula - z_tubo) > TOL
        pt_conexao   = pt_ramal

    pt_valvula = XYZ(
        pt_joelho.X + dir_saida.X * comp_horiz_ft,
        pt_joelho.Y + dir_saida.Y * comp_horiz_ft,
        pt_joelho.Z,
    )

    if tem_vertical:
        tubo_vert = Pipe.Create(doc, sys_type_id, pipe_type_id, nivel.Id, pt_ramal, pt_joelho)
        _setar_diametro_ft(tubo_vert, diam_ft)
        _rastrear(tubo_vert)
    else:
        tubo_vert = None

    tubo_horiz = Pipe.Create(doc, sys_type_id, pipe_type_id, nivel.Id, pt_joelho, pt_valvula)
    _setar_diametro_ft(tubo_horiz, diam_ft)
    _rastrear(tubo_horiz)

    if tem_vertical and tubo_vert is not None:
        conn_v = _get_connector_at(tubo_vert,  pt_joelho)
        conn_h = _get_connector_at(tubo_horiz, pt_joelho)
        if conn_v and conn_h:
            try:
                fitting_joelho = doc.Create.NewElbowFitting(conn_v, conn_h)
                _rastrear(fitting_joelho)
            except Exception:
                pass

    conn_tubo_fim = _get_far_connector(tubo_horiz, pt_joelho)
    if conn_tubo_fim is None:
        conn_tubo_fim = _get_connector_at(tubo_horiz, pt_valvula)
    pos_insercao = conn_tubo_fim.Origin if conn_tubo_fim else pt_valvula

    valvula = doc.Create.NewFamilyInstance(
        pos_insercao, simbolo, nivel, StructuralType.NonStructural
    )
    _rastrear(valvula)
    angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_saida)
    if abs(angulo) > TOL:
        eixo_rot = Line.CreateBound(
            pos_insercao, XYZ(pos_insercao.X, pos_insercao.Y, pos_insercao.Z + 1.0))
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
                pass

    avisos = []

    if inserir_abrigo and simbolo_abrigo is not None:
        try:
            pt_valvula_real = valvula.Location.Point
        except Exception:
            pt_valvula_real = None
        if pt_valvula_real is not None:
            pt_abrigo = _calcular_pt_abrigo(pt_valvula_real, dir_saida, nivel, dir_abrigo)
            abrigo = _inserir_abrigo_transacao(doc, simbolo_abrigo, pt_abrigo, dir_abrigo, nivel)
            _rastrear(abrigo)

    if tubo_origem is not None:
        doc.Regenerate()
        if tem_vertical:
            conn_ramal = _get_connector_near(tubo_vert, pt_conexao)
        else:
            conn_ramal = _get_connector_near(tubo_horiz, pt_conexao)

        if conn_ramal:
            dist_a   = pt_conexao.DistanceTo(pt_A)
            dist_b   = pt_conexao.DistanceTo(pt_B)
            em_ponta = (dist_a < tol_fim_ft or dist_b < tol_fim_ft)

            if em_ponta:
                pt_fim   = pt_A if dist_a < tol_fim_ft else pt_B
                conn_fim = _get_connector_near(tubo_origem, pt_fim)
                if conn_fim:
                    try:
                        fitting_o = doc.Create.NewElbowFitting(conn_fim, conn_ramal)
                        _rastrear(fitting_o)
                    except Exception as e:
                        avisos.append(u"Tubo de origem: conexão falhou ({})".format(str(e)))
                else:
                    avisos.append(u"Tubo de origem: conector de ponta não encontrado")
            else:
                try:
                    new_id   = PlumbingUtils.BreakCurve(doc, tubo_origem.Id, pt_conexao)
                    tubo_sec = doc.GetElement(new_id)
                    _rastrear(tubo_sec)
                    conn_p1  = _get_connector_near(tubo_origem, pt_conexao)
                    conn_p2  = _get_connector_near(tubo_sec,    pt_conexao)
                    if conn_p1 and conn_p2:
                        ord_ = _ordenar_conectores([conn_p1, conn_p2, conn_ramal])
                        fitting_o = doc.Create.NewTeeFitting(ord_[0], ord_[1], ord_[2])
                        _rastrear(fitting_o)
                    else:
                        avisos.append(u"Tubo de origem: conectores pós-corte não encontrados")
                except Exception as e:
                    avisos.append(u"Tubo de origem: conexão falhou ({})".format(str(e)))
        else:
            avisos.append(u"Tubo de origem: conector do ramal não encontrado")

    return {u"valvulas_criadas": [(valvula, nivel)], u"avisos": avisos}


def _construir_coluna(doc, ctx, niveis_sel, dir_saida, inserir_abrigo, dir_abrigo):
    """
    Constrói a coluna inteira — igual à Etapa 6 original de
    run_coluna_multilevel — parametrizada por niveis_sel (vem do estado
    ATUAL dos checkboxes, muda a cada ciclo de prévia). Com exatamente 1
    nível marcado, delega pra _construir_ramal_unico (sem coluna vertical
    nenhuma — ver docstring dela).

    A conexão com o tubo de origem (evento "origem" — corta/estende a
    curva dele, via PlumbingUtils.BreakCurve ou _ajustar_endpoint) roda
    SEMPRE, inclusive durante um ciclo de prévia: é destrutiva num
    elemento pré-existente, mas quem chama (ver
    _JanelaOpcoesColuna._restaurar_curva_origem) restaura a curva
    original de tubo_origem no início de CADA ciclo, antes de chamar
    esta função de novo — mesmo padrão que connect_pipe.py já usa pra
    pipe_ref. É isso que permite a prévia detectar ao vivo uma falha de
    espaço/sobreposição ao criar o Tê/cruzeta em qualquer ponto da
    coluna (inclusive onde ela cruza o tubo de origem), em vez de só
    descobrir na hora de confirmar — qualquer aviso retornado aqui
    bloqueia a confirmação (ver _JanelaOpcoesColuna._ciclo_preview).

    Levanta Exception (nunca pyscript.exit) em qualquer estado inválido
    (nenhum nível, abrigo sem família etc.) — quem chama (ciclo de
    prévia ou finalização) decide o que fazer com a mensagem.
    """
    if len(niveis_sel) < 1:
        raise Exception(u"Selecione pelo menos 1 nível.")
    if inserir_abrigo and ctx[u"simbolo_abrigo"] is None:
        raise Exception(ctx[u"erro_abrigo"] or u"Não foi possível carregar a família do abrigo.")

    if len(niveis_sel) == 1:
        return _construir_ramal_unico(doc, ctx, niveis_sel[0], dir_saida, inserir_abrigo, dir_abrigo)

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
            u"pra formar uma coluna vertical.")

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
                    fitting_ramal = _criar_fitting_generico(doc, conns_coluna + [conn_h_ini])
                    _rastrear(fitting_ramal)
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
            # ── Pernas do lado do TUBO DE ORIGEM: 1 se o ponto de corte
            # cair perto de uma ponta (estende até lá), 2 se for no meio
            # (BreakCurve) — mutação destrutiva num elemento
            # pré-existente, mas segura aqui porque quem chama
            # (_JanelaOpcoesColuna._restaurar_curva_origem) reseta a
            # curva de tubo_origem a cada ciclo (ver docstring de
            # _construir_coluna).
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
                    _rastrear(tubo_origem_sec)
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
                    fitting_origem = _criar_fitting_generico(doc, conns_totais)
                    _rastrear(fitting_origem)
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
    mesmo padrão de connect_pipe.py/_JanelaOpcoesRota: níveis (checkbox
    por nível, criados dinamicamente porque o número varia por projeto),
    abrigo de mangueira (toggle, ligado por padrão) e orientação da
    válvula/ramal (botão único de rotação, UMA só mesmo com vários
    níveis) + lado do abrigo (quando ligado) — qualquer troca reconstrói
    o resultado inteiro no modelo (ramal único com 1 nível marcado, ou a
    coluna inteira com 2+ — ver _construir_coluna)."""

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

        # Curva original de tubo_origem, pra restaurar a cada ciclo (ver
        # _restaurar_curva_origem) — a conexão com ele (BreakCurve /
        # _ajustar_endpoint, dentro de _construir_coluna/
        # _construir_ramal_unico) roda em TODO ciclo de prévia, não só na
        # confirmação, exatamente pra pegar ao vivo uma falha de espaço
        # do Revit ao criar o Tê/cruzeta ali — sem isso, cada ciclo
        # deixaria tubo_origem cada vez mais cortado/deslocado.
        self._tubo_origem = ctx[u"tubo_origem"]
        if self._tubo_origem is not None:
            _loc_origem = self._tubo_origem.Location.Curve
            self._p0_origem_orig = _loc_origem.GetEndPoint(0)
            self._p1_origem_orig = _loc_origem.GetEndPoint(1)
        else:
            self._p0_origem_orig = None
            self._p1_origem_orig = None

        # Nível pré-marcado: o mesmo nível de referência do tubo de
        # origem (tubo_origem.ReferenceLevel) — None em modo livre, caso
        # em que nenhum nível vem marcado (igual a antes). Marcado em
        # código, sob o mesmo guard _sincronizando do abrigo acima (ver
        # comentário logo abaixo): setar IsChecked dispara Checked
        # síncrono, e isso não pode disparar _agendar_atualizacao antes
        # do resto da janela existir.
        nivel_ref_origem = ctx[u"nivel_ref_origem"]

        from System.Windows.Controls import CheckBox
        estilo = self.FindResource(u"NivelCheckStyle")
        self._checkboxes = []
        self._sincronizando = True
        try:
            for nivel in ctx[u"niveis"]:
                cb = CheckBox()
                cb.Content = nivel.Name
                cb.Tag     = nivel
                cb.Style   = estilo
                cb.Checked   += self.on_opcao_changed
                cb.Unchecked += self.on_opcao_changed
                if nivel_ref_origem is not None and nivel.Id == nivel_ref_origem.Id:
                    cb.IsChecked = True
                self.PainelNiveis.Children.Add(cb)
                self._checkboxes.append(cb)
        finally:
            self._sincronizando = False

        # Abrigo vem ligado por padrão — setado aqui em código, não via
        # IsChecked="True" no XAML: mudar IsChecked dispara Checked tanto
        # faz a origem (clique do usuário ou o parser de XAML aplicando o
        # atributo), e isso aconteceria DENTRO de forms.WPFWindow.__init__
        # (acima), antes do resto do estado desta janela existir — daí o
        # guard _sincronizando, mesmo padrão já usado nos botões de
        # direção/lado antes da troca pro botão único de rotação.
        self._sincronizando = True
        try:
            self.ChkAbrigo.IsChecked = True
        finally:
            self._sincronizando = False
        self.SecaoLadoAbrigo.Visibility = (
            SW.Visibility.Visible if self.ChkAbrigo.IsChecked else SW.Visibility.Collapsed)

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

    def _restaurar_curva_origem(self):
        """Reseta tubo_origem pra curva original (antes de qualquer
        BreakCurve/_ajustar_endpoint do ciclo anterior) — chamada sempre
        junto de _desfazer_elementos_criados() (mesmo padrão de
        connect_pipe.py/_JanelaOpcoesRota._restaurar_curvas_originais).
        No-op se não há tubo_origem (modo livre)."""
        if self._p0_origem_orig is not None:
            try:
                self._tubo_origem.Location.Curve = Line.CreateBound(
                    self._p0_origem_orig, self._p1_origem_orig)
            except Exception:
                pass

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
                self._restaurar_curva_origem()
                self.doc.Regenerate()
                resultado = _construir_coluna(
                    self.doc, self.ctx, niveis_sel, dir_saida, inserir_abrigo, dir_abrigo)
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
            self._restaurar_curva_origem()
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
            self._restaurar_curva_origem()
            self.doc.Regenerate()

            _iniciar_rastreamento()
            erro = None
            try:
                resultado = _construir_coluna(
                    self.doc, self.ctx, self._niveis_selecionados(),
                    self._direcao_saida_atual(), self._inserir_abrigo_atual(),
                    self._dir_abrigo_atual())
                self.doc.Regenerate()
                # Falha ao criar um Tê/cruzeta/joelho (ex.: sem reta livre
                # pro Revit encaixar o fitting) não propaga como Exception
                # — _construir_coluna/_construir_ramal_unico seguem até o
                # fim e só anotam em "avisos", pra construir o máximo
                # possível mesmo com uma conexão falhando. Mas na PRÉVIA
                # isso tem que travar a confirmação (ver on_ok) — é
                # exatamente a limitação de espaço/sobreposição que o
                # usuário só descobriria com o Revit reclamando depois.
                if resultado[u"avisos"]:
                    erro = u" | ".join(resultado[u"avisos"])
            except Exception as ex:
                erro = u"{}".format(ex)
            self._elementos_criados = _parar_rastreamento()

            if erro is not None:
                self._desfazer_elementos_criados()
                self._restaurar_curva_origem()
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

    def on_direcao_click(self, sender, args):
        self._direcao_atual = _proximo_na_lista(_ORDEM_DIRECAO, self._direcao_atual)
        self._agendar_atualizacao()

    def on_lado_click(self, sender, args):
        self._lado_atual = _proximo_na_lista(_ORDEM_LADO, self._lado_atual)
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
    Inserir Hidrante por Nível: único botão de inserção de hidrante do
    projeto — com 1 nível marcado, insere um hidrante único (ramal +
    válvula, sem coluna nenhuma — ver _construir_ramal_unico); com 2+,
    cria uma ÚNICA coluna vertical atravessando os níveis escolhidos, com
    um ramal horizontal + válvula em CADA um. Em qualquer dos dois casos,
    abrigo de mangueira é opcional (toggle, ligado por padrão).

    Fluxo:
      1. Clique: tubo de origem pra conectar o ramal/coluna (PickObject)
         OU Esc pra posicionar livremente (sem conexão a nada existente).
      2. Diálogo com prévia ao vivo (_JanelaOpcoesColuna): níveis a
         incluir (mín. 1), abrigo de mangueira e orientação da
         válvula/ramal (+ lado do abrigo, se ligado) — toda troca
         reconstrói o resultado inteiro no modelo (_construir_coluna)
         para o usuário ver antes de confirmar.
      3. Na confirmação, o resultado é reconstruído de vez numa transação
         própria, agora COM a conexão real ao tubo de origem (ver
         docstring de _construir_coluna/_construir_ramal_unico sobre por
         que essa conexão só acontece uma vez).
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
