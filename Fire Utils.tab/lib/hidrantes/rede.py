# -*- coding: utf-8 -*-
"""
rede.py — Fire Utils · lib/hidrantes/
Helpers Revit da rede de tubulação de hidrantes, compartilhados entre
"Mapear Trechos" e "Dimensionar Hidrantes": leitura de conectores/cotas,
travessia da rede (sucção RTI→Bomba e a árvore de recalque até as válvulas
de hidrante) e extração de comprimento/diâmetro/Leq dos elementos de um
trecho.

Depende do Revit (Connector, Pipe, FamilyInstance) — não é um módulo puro
como calc.py.
"""

import clr
clr.AddReference("RevitAPI")

from collections import deque

from Autodesk.Revit.DB import (
    FamilyInstance, BuiltInCategory, BuiltInParameter, ElementId,
    ConnectorType, LocationCurve, LocationPoint, UnitUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from System import Int64

from hydrant_family import NOME_FAMILIA as _NOME_FAMILIA_VALVULA

try:
    from Autodesk.Revit.DB import UnitTypeId
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, DisplayUnitType.DUT_METERS)

# Teto de elementos por galho na travessia em árvore (percorre_rotas_hidrantes)
# - so um reforco de seguranca contra modelagem com anel fechado por engano;
# o criterio real de parada de ciclo e o proprio conjunto de visitados.
PROFUNDIDADE_MAX = 500


# ===========================================================================
# Identificação de elementos
# ===========================================================================

def get_id(elem):
    """ElementId como int nativo do Python — para gravar no cache (JSON,
    que não serializa o Int64/Int32 do .NET direto) e para reconstruir o
    ElementId depois com to_element_id()."""
    try:    return int(elem.Id.Value)
    except: return int(elem.Id.IntegerValue)


def to_element_id(eid):
    """ElementId a partir de um int puro do Python. ElementId(int) é
    ambíguo no IronPython nas versões do Revit que também têm
    ElementId(BuiltInParameter)/ElementId(BuiltInCategory) (2024+) —
    Int64(eid) força o overload certo."""
    return ElementId(Int64(eid))


def get_conectores(elem):
    try:
        if hasattr(elem, 'ConnectorManager') and elem.ConnectorManager:
            return list(elem.ConnectorManager.Connectors)
        mep = elem.MEPModel
        if mep and mep.ConnectorManager:
            return list(mep.ConnectorManager.Connectors)
    except: pass
    return []


_CATS_EQUIPAMENTO = None
def eh_equipamento(elem):
    """True se `elem` for um equipamento (bomba, RTI, etc.) - categoria
    Mechanical/Plumbing Equipment ou Peca Hidrossanitaria (a RTI costuma
    vir como Plumbing Fixture). Esses elementos tem lados fisicamente
    distintos (ex.: succao x recalque de uma bomba) e NAO devem ser
    atravessados como se fossem uma conexao/te qualquer: entrar por um
    conector e sair por outro conector do mesmo equipamento salta
    indevidamente de um trecho hidraulico para outro."""
    global _CATS_EQUIPAMENTO
    if _CATS_EQUIPAMENTO is None:
        _CATS_EQUIPAMENTO = set()
        for bic_nome in ("OST_MechanicalEquipment", "OST_PlumbingEquipment",
                         "OST_PlumbingFixtures"):
            bic = getattr(BuiltInCategory, bic_nome, None)
            if bic is not None:
                _CATS_EQUIPAMENTO.add(int(bic))
    try:
        cat = elem.Category
        if not cat: return False
        cat_id = cat.Id
        cat_int = cat_id.Value if hasattr(cat_id, "Value") else cat_id.IntegerValue
        return cat_int in _CATS_EQUIPAMENTO
    except: return False


def eh_valvula_hidrante(elem):
    """True se `elem` for uma instância da família 'Valvula para Hidrante'
    (lib/family_library/Hidrantes/) - fim de uma rota de recalque na
    travessia em árvore (percorre_rotas_hidrantes)."""
    if not isinstance(elem, FamilyInstance):
        return False
    try:
        return elem.Symbol.Family.Name == _NOME_FAMILIA_VALVULA
    except: return False


# ===========================================================================
# Cotas — sempre lidas ao vivo pelos conectores nativos, nunca gravadas
# ===========================================================================

def get_cota_conector(elem, direcoes=None):
    """Cota (Z, em metros) de um conector nativo e conectado de `elem`.
    Se `direcoes` for informado (RTI/bomba), usa o primeiro conector com
    essa Direction; senao (valvula do hidrante), prioriza um conector
    conectado e cai no primeiro conector que existir. None se nao
    encontrar - sem nenhum fallback por geometria."""
    conns = get_conectores(elem)
    if direcoes is not None:
        for conn in conns:
            try:
                if conn.ConnectorType == ConnectorType.Logical: continue
                if conn.Direction not in direcoes: continue
                if not conn.IsConnected: continue
                return to_m(conn.Origin.Z)
            except: continue
        return None
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            if conn.IsConnected:
                return to_m(conn.Origin.Z)
        except: continue
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            return to_m(conn.Origin.Z)
        except: continue
    return None


def get_cota_rti(elem):
    """Cota da RTI: le a elevacao de um conector fisico de `elem` (o
    elemento marcado "RTI" pelo "Mapear Trechos" - familia da RTI ou, no
    fallback manual, o proprio tubo). Preferencia pela ponta solta (conector
    nao Logical e nao conectado a nada) - normalmente e ela que fica virada
    para dentro do reservatorio. Mas nem todo modelo tem uma ponta solta ali
    (o elemento pode estar plenamente conectado nos dois lados da rede, com
    a cota do RTI vindo so da posicao dele) - nesse caso cai para qualquer
    conector fisico, mesmo criterio de get_cota_conector() para os demais
    pontos (succao/recalque/hidrantes). None so se nao achar conector
    nenhum."""
    cm = None
    if hasattr(elem, "ConnectorManager") and elem.ConnectorManager:
        cm = elem.ConnectorManager
    elif hasattr(elem, "MEPModel") and elem.MEPModel and elem.MEPModel.ConnectorManager:
        cm = elem.MEPModel.ConnectorManager
    if not cm:
        return None
    conns = list(cm.Connectors)
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            if not conn.IsConnected:
                return to_m(conn.Origin.Z)
        except: continue
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            return to_m(conn.Origin.Z)
        except: continue
    return None


# ===========================================================================
# Travessia da rede
# ===========================================================================

def get_primeiro_tubo(elem_ini, direcoes_ini):
    """A partir dos conectores de `elem_ini` (RTI ou bomba) cuja Direction
    esteja em `direcoes_ini`, anda pela rede - pulando acessorios/conexoes
    que nao sejam Pipe (ex.: luva de reducao, valvula) - e retorna o
    primeiro Pipe encontrado. Nao atravessa outros equipamentos (ex.: uma
    segunda bomba) pelo caminho. Retorna None se a rede nao alcancar
    nenhum tubo nessa direcao."""
    eid_ini = get_id(elem_ini)
    visitados = set([eid_ini])
    fila = deque()
    for conn in get_conectores(elem_ini):
        try:
            if conn.Direction not in direcoes_ini: continue
            if not conn.IsConnected: continue
            for ref in conn.AllRefs:
                viz = ref.Owner
                vid = get_id(viz)
                if vid not in visitados:
                    visitados.add(vid)
                    fila.append(viz)
        except: continue

    while fila:
        elem = fila.popleft()
        if isinstance(elem, Pipe):
            return elem
        if eh_equipamento(elem): continue
        for conn in get_conectores(elem):
            try:
                if not conn.IsConnected: continue
                for ref in conn.AllRefs:
                    viz = ref.Owner
                    vid = get_id(viz)
                    if vid not in visitados:
                        visitados.add(vid)
                        fila.append(viz)
            except: continue
    return None


def bfs_ate(elem_ini, eid_ini, eid_alvo):
    """BFS de elem_ini ate eid_alvo. Retorna (caminho, visitados).
    Se o alvo nao for alcancado, caminho vem vazio e visitados guarda
    tudo que a busca conseguiu percorrer, para diagnostico da quebra.
    Nao atravessa equipamentos (bombas, RTI etc.) encontrados pelo
    caminho - ver eh_equipamento. Usado para a succao (RTI -> Bomba),
    que e sempre um caminho unico ponto-a-ponto, sem ramificacao."""
    visitados = set([eid_ini])
    fila      = deque([(elem_ini, [eid_ini])])
    while fila:
        elem, caminho = fila.popleft()
        if get_id(elem) == eid_alvo:
            return caminho, visitados
        if eh_equipamento(elem) and get_id(elem) != eid_ini:
            continue
        for conn in get_conectores(elem):
            try:
                if not conn.IsConnected: continue
                for ref in conn.AllRefs:
                    viz = ref.Owner
                    vid = get_id(viz)
                    if vid not in visitados:
                        visitados.add(vid)
                        fila.append((viz, caminho + [vid]))
            except: continue
    return [], visitados


def percorre_rotas_hidrantes(elem_ini, eid_ini):
    """
    Percorre a árvore de tubulação de recalque a partir de `elem_ini` (tubo
    de saída da bomba), ramificando em cada Tê/conexão, até achar uma
    instância da família 'Valvula para Hidrante' em cada folha - cada
    caminho completo (elem_ini até a válvula, ambos inclusive) vira uma
    rota completa.

    Não atravessa outro equipamento pelo caminho (ex.: uma segunda bomba -
    ver eh_equipamento) nem revisita elemento já visitado em outro galho:
    a rede de recalque é uma árvore (sem anéis), então nenhum elemento
    deveria aparecer em mais de um galho por construção; se aparecer (anel
    fechado por engano na modelagem), aquele galho simplesmente para ali,
    sem erro. PROFUNDIDADE_MAX é um reforço de segurança extra contra o
    mesmo cenário. Galhos que não terminam em válvula (ramal morto, dreno,
    tubulação auxiliar) também são ignorados silenciosamente.

    Retorna lista de rotas; cada rota é uma lista de ElementId.Value
    (get_id), de elem_ini até a válvula, ambos inclusive.
    """
    rotas = []
    visitados = set([eid_ini])
    pilha = [(elem_ini, [eid_ini])]
    while pilha:
        elem, caminho = pilha.pop()
        if eh_valvula_hidrante(elem):
            rotas.append(caminho)
            continue
        if len(caminho) >= PROFUNDIDADE_MAX:
            continue
        if eh_equipamento(elem) and get_id(elem) != eid_ini:
            continue
        for conn in get_conectores(elem):
            try:
                if not conn.IsConnected: continue
                for ref in conn.AllRefs:
                    viz = ref.Owner
                    vid = get_id(viz)
                    if vid not in visitados:
                        visitados.add(vid)
                        pilha.append((viz, caminho + [vid]))
            except: continue
    return rotas


def get_pontas_abertas(doc, visitados):
    """Dentre os elementos alcancados por uma travessia (bfs_ate ou
    percorre_rotas_hidrantes), retorna os que tem conector desconectado -
    candidatos ao ponto onde a rede quebrou. Usado so para diagnostico."""
    pontas = []
    for eid in visitados:
        elem = doc.GetElement(to_element_id(eid))
        if not elem: continue
        conns = get_conectores(elem)
        if not conns: continue
        for conn in conns:
            try:
                if not conn.IsConnected:
                    pontas.append(eid)
                    break
            except: continue
    return pontas


# ===========================================================================
# Extração de atributos dos elementos (para extrair_trecho/calc_j_trecho)
# ===========================================================================

def get_comprimento(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        return to_m(p.AsDouble()) if p else 0.0
    except: return 0.0


def get_diametro(elem):
    """
    Diâmetro NOMINAL (DN) do elemento — não o diâmetro interno real medido
    pelo schedule/material. Ex.: um tubo DN 65 pode ter diâmetro interno
    de 68,8 mm; o cálculo (Jun, J, V) usa o nominal, como no dimensionamento
    de referência. RBS_PIPE_DIAMETER_PARAM é o parâmetro "Diâmetro" do tubo
    (o tamanho nominal da lista de segmentos/tipos de tubo do Revit).

    Para um Pipe o diâmetro TEM que ser lido com sucesso: um fallback
    silencioso aqui faria dois tubos de tamanhos diferentes caírem no
    mesmo valor "adivinhado" e a pontuação da rota (ou o dimensionamento)
    perderia a diferença real sem avisar. Por isso lança erro em vez de
    chutar — o chamador mostra qual elemento é. Só um acessório
    (FamilyInstance sem "Diâmetro" cadastrado, ex.: conexão atípica) usa
    o diâmetro interno e, na falta dele, um valor padrão.
    """
    try:
        p = elem.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if p and p.AsDouble() > 0:
            return to_m(p.AsDouble())
    except Exception: pass
    if isinstance(elem, Pipe):
        raise ValueError(
            u"Não foi possível ler o diâmetro nominal do tubo ID {} "
            u"(parâmetro 'Diâmetro' ausente ou zerado). Verifique o tipo "
            u"de tubo/segmento desse trecho no Revit.".format(elem.Id))
    try:
        p = elem.get_Parameter(BuiltInParameter.RBS_PIPE_INNER_DIAM_PARAM)
        return to_m(p.AsDouble()) if p and p.AsDouble() > 0 else 0.065
    except Exception: return 0.065


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


def diagnostico_conectores(elem):
    """Linhas com id/tipo/categoria de `elem` e Direction/IsConnected/Z de
    cada conector dele - usado so para montar o alerta quando uma cota
    nao e lida, pra mostrar exatamente por que (em vez de um "nao foi
    possivel" generico). Nao usa get_conectores (que engole excecoes) -
    aqui o erro real, se houver, aparece no alerta."""
    linhas = []
    try:    id_txt = u"{}".format(elem.Id)
    except: id_txt = u"?"
    try:    tipo = type(elem).__name__
    except: tipo = u"?"
    try:    eh_pipe = isinstance(elem, Pipe)
    except Exception as e: eh_pipe = u"erro ({})".format(e)
    try:    cat = elem.Category.Name if elem.Category else u"(sem categoria)"
    except: cat = u"?"
    try:    tem_cm = hasattr(elem, "ConnectorManager")
    except: tem_cm = u"?"
    linhas.append(u"    Id={} tipo={} isinstance(Pipe)={}".format(id_txt, tipo, eh_pipe))
    linhas.append(u"    categoria={} hasattr(ConnectorManager)={}".format(cat, tem_cm))

    conns = None
    erro = None
    try:
        cm = elem.ConnectorManager if hasattr(elem, "ConnectorManager") else None
        linhas.append(u"    elem.ConnectorManager = {}".format(cm))
        if cm is not None:
            conns = list(cm.Connectors)
        else:
            mep = elem.MEPModel
            if mep and mep.ConnectorManager:
                conns = list(mep.ConnectorManager.Connectors)
    except Exception as e:
        erro = e

    if erro is not None:
        linhas.append(u"    erro ao ler ConnectorManager: {}".format(erro))
        return linhas
    if not conns:
        linhas.append(u"    ConnectorManager nao encontrou nenhum conector")
        return linhas

    for i, conn in enumerate(conns):
        try:    direcao = conn.Direction
        except: direcao = u"?"
        try:    conectado = conn.IsConnected
        except: conectado = u"?"
        try:    z = u"{:.4f} m".format(to_m(conn.Origin.Z))
        except: z = u"?"
        linhas.append(u"    {}. Direction={} IsConnected={} Z={}".format(
            i + 1, direcao, conectado, z))
    return linhas
