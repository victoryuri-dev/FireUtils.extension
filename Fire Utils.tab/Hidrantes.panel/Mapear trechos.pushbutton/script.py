# -*- coding: utf-8 -*-
"""
script.py — Mapear Trechos de Hidrante
O usuário identifica manualmente os dois hidrantes mais desfavoráveis.
O script rastreia os trechos e preenche os parâmetros FireUtils.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInCategory,
    BuiltInParameter, Transaction, UnitUtils, ElementId, FlowDirectionType,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script
from collections import deque
from System.Collections.Generic import List

try:
    from Autodesk.Revit.DB import UnitTypeId
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, DisplayUnitType.DUT_METERS)

from hidrantes.params import create_hydrant_params

P_TRECHO        = u"FireUtils - Trecho"
P_IDENTIFICADOR = u"FireUtils - Identificador"
P_COTA          = u"FireUtils - Cota"

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

output.print_md("# Fire Utils - Mapear Trechos de Hidrante")

# ===========================================================================
# Helpers
# ===========================================================================
def get_id(elem):
    try:    return elem.Id.Value
    except: return elem.Id.IntegerValue

def get_conectores(elem):
    try:
        if hasattr(elem, 'ConnectorManager'):
            return list(elem.ConnectorManager.Connectors)
        mep = elem.MEPModel
        if mep and mep.ConnectorManager:
            return list(mep.ConnectorManager.Connectors)
    except: pass
    return []

_CATS_EQUIPAMENTO = None
def eh_equipamento(elem):
    """True se `elem` for um equipamento (bomba, RTI, etc.) - categoria
    Mechanical/Plumbing Equipment. Esses elementos tem lados fisicamente
    distintos (ex.: succao x recalque de uma bomba) e NAO devem ser
    atravessados como se fossem uma conexao/te qualquer: entrar por um
    conector e sair por outro conector do mesmo equipamento salta
    indevidamente de um trecho hidraulico para outro."""
    global _CATS_EQUIPAMENTO
    if _CATS_EQUIPAMENTO is None:
        _CATS_EQUIPAMENTO = set()
        for bic_nome in ("OST_MechanicalEquipment", "OST_PlumbingEquipment"):
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

def get_cota_conector(elem, direcoes):
    """Cota (Z, em metros) do primeiro conector nativo e conectado de
    `elem` (RTI ou bomba) cuja Direction esteja em `direcoes`. Essa e a
    cota real do ponto onde o equipamento se conecta a rede - mais precisa
    que estimar pela geometria do tubo marcado (vertical/horizontal).
    Retorna None se nao houver conector nessa direcao conectado."""
    for conn in get_conectores(elem):
        try:
            if conn.Direction not in direcoes: continue
            if not conn.IsConnected: continue
            return to_m(conn.Origin.Z)
        except: continue
    return None

def get_lt(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        return to_m(p.AsDouble()) if p else 0.0
    except: return 0.0

def get_leq(elem):
    try:
        p = elem.LookupParameter(u"Perda de Carga")
        return p.AsDouble() if p else 0.0
    except: return 0.0

def set_param(elem, nome, valor):
    try:
        p = elem.LookupParameter(nome)
        if p and not p.IsReadOnly:
            p.Set(valor)
            return True
    except: pass
    return False

def bfs_ate(elem_ini, eid_ini, eid_alvo):
    """BFS de elem_ini ate eid_alvo. Retorna (caminho, visitados).
    Se o alvo nao for alcancado, caminho vem vazio e visitados guarda
    tudo que a busca conseguiu percorrer, para diagnostico da quebra.
    Nao atravessa equipamentos (bombas, RTI etc.) encontrados pelo
    caminho - ver eh_equipamento."""
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

def get_pontas_abertas(visitados):
    """Dentre os elementos alcancados pelo BFS, retorna os que tem
    conector desconectado - candidatos ao ponto onde a rede quebrou."""
    pontas = []
    for eid in visitados:
        elem = doc.GetElement(ElementId(eid))
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

def reporta_quebra(visitados, alvo_desc):
    """Mostra onde o rastreamento parou: quantos elementos foram
    alcancados e, se houver, os IDs com conector aberto (clicaveis
    para selecionar/mostrar no Revit)."""
    output.print_md(u"**Caminho ate {} nao encontrado.**".format(alvo_desc))
    output.print_md(u"{} elemento(s) alcancado(s) antes de parar.".format(len(visitados)))
    pontas = get_pontas_abertas(visitados)
    if pontas:
        output.print_md(u"Possivel(is) ponto(s) de quebra (conector desconectado):")
        for eid in pontas:
            try:
                link = output.linkify(ElementId(eid), title=u"Mostrar ID {}".format(eid))
            except:
                link = u"ID {}".format(eid)
            output.print_md(u"- {}".format(link))
        try:
            uidoc.Selection.SetElementIds(List[ElementId]([ElementId(eid) for eid in pontas]))
        except: pass
    else:
        output.print_md(
            u"Nenhum conector aberto encontrado no trecho alcancado. "
            u"A quebra pode ser um elemento sem ConnectorManager "
            u"(categoria nao suportada) logo apos o ultimo elemento acima."
        )

class PipeFilter(ISelectionFilter):
    def AllowElement(self, e): return isinstance(e, Pipe)
    def AllowReference(self, r, p): return False

class FittingFilter(ISelectionFilter):
    def AllowElement(self, e): return isinstance(e, FamilyInstance)
    def AllowReference(self, r, p): return False

def seleciona(msg_alert, msg_pick, filtro):
    forms.alert(msg_alert, title="Fire Utils")
    try:
        ref  = uidoc.Selection.PickObject(ObjectType.Element, filtro, msg_pick)
        return doc.GetElement(ref.ElementId)
    except:
        output.print_md(u"Selecao cancelada.")
        script.exit()

def seleciona_opcional(msg_alert, msg_pick, filtro):
    """Como `seleciona`, mas retorna None em vez de encerrar o script
    se a selecao for cancelada (ex.: usuario clica fora de um elemento)."""
    forms.alert(msg_alert, title="Fire Utils")
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, filtro, msg_pick)
        return doc.GetElement(ref.ElementId)
    except:
        return None

# ===========================================================================
# 0 — Garante parâmetros
# ===========================================================================
output.print_md("---")
output.print_md("### 0 - Verificando Parametros")
try:
    log = create_hydrant_params(doc)
    for nome, status in log:
        if status in ("criado", "atualizado"):
            output.print_md(u"  [{}] {}".format(status, nome))
    output.print_md(u"Parametros verificados.")
except Exception as e:
    forms.alert(u"Erro ao criar parametros:\n{}".format(str(e)), title="Fire Utils", warn_icon=True)
    script.exit()

# ===========================================================================
# 0b — Reset: limpa parâmetros FireUtils de todo o modelo
# ===========================================================================
output.print_md("---")
output.print_md("### 0b - Resetando mapeamento anterior")

_todos = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
_resetados = 0
with Transaction(doc, "FireUtils - Reset Mapeamento") as _t:
    _t.Start()
    try:
        for _elem in _todos:
            _p_trecho = _elem.LookupParameter(P_TRECHO)
            _p_ident  = _elem.LookupParameter(P_IDENTIFICADOR)
            _p_cota   = _elem.LookupParameter(P_COTA)
            _alterou  = False
            if _p_trecho and not _p_trecho.IsReadOnly and _p_trecho.AsString():
                _p_trecho.Set(u"")
                _alterou = True
            if _p_ident and not _p_ident.IsReadOnly and _p_ident.AsString():
                _p_ident.Set(u"")
                _alterou = True
            if _p_cota and not _p_cota.IsReadOnly and _p_cota.HasValue:
                _p_cota.Set(0.0)
                _alterou = True
            if _alterou:
                _resetados += 1
        _t.Commit()
    except Exception as _e:
        _t.RollBack()
        forms.alert(u"Erro ao resetar mapeamento:\n{}".format(str(_e)),
                    title="Fire Utils", warn_icon=True)
        script.exit()

output.print_md(u"{} elemento(s) com parametros resetados.".format(_resetados))

# ===========================================================================
# 1 — Usuário seleciona os dois hidrantes mais desfavoráveis
# ===========================================================================
output.print_md("---")
output.print_md("### 1 - Selecionar Hidrantes Mais Desfavoraveis")

hid01 = seleciona(
    u"Selecione o hidrante MAIS desfavoravel (HID-01).",
    u"Clique no HID-01", FittingFilter()
)
hid02 = seleciona(
    u"Selecione o SEGUNDO hidrante mais desfavoravel (HID-02).",
    u"Clique no HID-02", FittingFilter()
)

eid_h1 = get_id(hid01)
eid_h2 = get_id(hid02)
output.print_md(u"HID-01: ID **{}** | HID-02: ID **{}**".format(eid_h1, eid_h2))

# ===========================================================================
# 2 — Seleciona RTI e Bomba (usa as conexões nativas de entrada/saída)
# ===========================================================================
output.print_md("---")
output.print_md("### 2 - Selecionar RTI e Bomba")

rti = seleciona_opcional(u"Selecione o reservatorio (RTI).", u"Reservatorio (RTI)", FittingFilter())

tubo_rti = None
if rti:
    output.print_md(u"RTI: ID **{}**".format(get_id(rti)))
    tubo_rti = get_primeiro_tubo(rti, (FlowDirectionType.Out,))
else:
    output.print_md(u"Nenhuma RTI selecionada.")

if not tubo_rti:
    tubo_rti = seleciona(
        u"Nao foi possivel identificar o tubo de saida da RTI.\n"
        u"Clique no tubo de saida da RTI.",
        u"Tubo de saida da RTI", PipeFilter()
    )

bomba = seleciona(u"Selecione a bomba de incendio.", u"Bomba de incendio", FittingFilter())
output.print_md(u"Bomba: ID **{}**".format(get_id(bomba)))

tubo_bomba = get_primeiro_tubo(bomba, (FlowDirectionType.In,))
if not tubo_bomba:
    tubo_bomba = seleciona(
        u"Nao foi possivel identificar automaticamente o tubo de entrada (succao) da bomba.\n"
        u"Selecione o tubo que conecta na entrada da bomba.",
        u"Tubo succao bomba", PipeFilter()
    )

tubo_rec = get_primeiro_tubo(bomba, (FlowDirectionType.Out,))
if not tubo_rec:
    tubo_rec = seleciona(
        u"Nao foi possivel identificar automaticamente o tubo de saida (recalque) da bomba.\n"
        u"Selecione o tubo que conecta na saida da bomba.",
        u"Tubo recalque bomba", PipeFilter()
    )

eid_rti   = get_id(tubo_rti)
eid_bomba = get_id(tubo_bomba)
eid_rec   = get_id(tubo_rec)

output.print_md(u"Saida RTI: ID **{}** | Entrada bomba (succao): ID **{}** | Saida bomba (recalque): ID **{}**".format(
    eid_rti, eid_bomba, eid_rec
))

# Cota real dos conectores de RTI/bomba - gravada em "FireUtils - Cota" no
# passo 6 para o "Dimensionar Hidrantes" usar direto, em vez de estimar a
# cota pela geometria do tubo marcado (vertical/horizontal).
cota_rti      = get_cota_conector(rti, (FlowDirectionType.Out,)) if rti else None
cota_succao   = get_cota_conector(bomba, (FlowDirectionType.In,))
cota_recalque = get_cota_conector(bomba, (FlowDirectionType.Out,))

output.print_md(u"Cota RTI: {} | Cota succao: {} | Cota recalque: {}".format(
    u"{:.4f} m".format(cota_rti) if cota_rti is not None else u"n/d",
    u"{:.4f} m".format(cota_succao) if cota_succao is not None else u"n/d",
    u"{:.4f} m".format(cota_recalque) if cota_recalque is not None else u"n/d",
))

# ===========================================================================
# 3 — BFS: sucção (RTI → Bomba)
# ===========================================================================
output.print_md("---")
output.print_md("### 3 - Mapeando Succao (RTI > Bomba)")

caminho_succao, visitados_succao = bfs_ate(tubo_rti, eid_rti, eid_bomba)
if not caminho_succao:
    reporta_quebra(visitados_succao, u"entrada da bomba (succao)")
    forms.alert(u"Caminho nao encontrado entre saida RTI e entrada da bomba.",
                title="Fire Utils", warn_icon=True)
    script.exit()
ids_succao = set(caminho_succao)
output.print_md(u"{} elemento(s) no trecho de succao".format(len(ids_succao)))

# ===========================================================================
# 4 — BFS: recalque até HID-01 e HID-02
# ===========================================================================
output.print_md("---")
output.print_md("### 4 - Mapeando Recalque")

caminho_h1, visitados_h1 = bfs_ate(tubo_rec, eid_rec, eid_h1)
caminho_h2, visitados_h2 = bfs_ate(tubo_rec, eid_rec, eid_h2)

if not caminho_h1:
    reporta_quebra(visitados_h1, u"HID-01")
    forms.alert(u"Caminho nao encontrado ate HID-01.", title="Fire Utils", warn_icon=True)
    script.exit()
if not caminho_h2:
    reporta_quebra(visitados_h2, u"HID-02")
    forms.alert(u"Caminho nao encontrado ate HID-02.", title="Fire Utils", warn_icon=True)
    script.exit()

output.print_md(u"[debug] Caminho HID-01: {} elementos".format(len(caminho_h1)))
output.print_md(u"[debug] Caminho HID-02: {} elementos".format(len(caminho_h2)))

# ===========================================================================
# 5 — Ponto A (último elemento comum aos dois caminhos)
# ===========================================================================
output.print_md("---")
output.print_md("### 5 - Identificando Ponto A")

set_h2 = set(caminho_h2)
comuns  = [eid for eid in caminho_h1 if eid in set_h2]

if not comuns:
    forms.alert(u"Ponto A nao encontrado.", title="Fire Utils", warn_icon=True)
    script.exit()

ponto_a_id = comuns[-1]
output.print_md(u"Ponto A: ID **{}**".format(ponto_a_id))

idx_a_h1 = caminho_h1.index(ponto_a_id)
idx_a_h2 = caminho_h2.index(ponto_a_id)

ids_rec_comum = set(caminho_h1[:idx_a_h1 + 1])  # Bomba → Ponto A (inclusive)
ids_ramal_h1  = set(caminho_h1[idx_a_h1 + 1:])  # Ponto A → HID-01
ids_ramal_h2  = set(caminho_h2[idx_a_h2 + 1:])  # Ponto A → HID-02

output.print_md(u"[debug] Rec. comum: {} | Ramal H1: {} | Ramal H2: {} elementos".format(
    len(ids_rec_comum), len(ids_ramal_h1), len(ids_ramal_h2)
))

# ===========================================================================
# 6 — Preenche parâmetros
# ===========================================================================
output.print_md("---")
output.print_md("### 6 - Preenchendo Parametros")

cont = {}

with Transaction(doc, "FireUtils - Mapear Trechos") as t:
    t.Start()
    try:
        # Sucção
        for eid in ids_succao:
            elem = doc.GetElement(ElementId(eid))
            if not elem: continue
            if eid == eid_rti:
                set_param(elem, P_TRECHO, u"RTI - Bomba")
                set_param(elem, P_IDENTIFICADOR, u"RTI")
                if cota_rti is not None:
                    set_param(elem, P_COTA, cota_rti)
            elif eid == eid_bomba:
                set_param(elem, P_TRECHO, u"RTI - Bomba")
                set_param(elem, P_IDENTIFICADOR, u"Succao")
                if cota_succao is not None:
                    set_param(elem, P_COTA, cota_succao)
            else:
                set_param(elem, P_TRECHO, u"RTI - Bomba")
            cont[u"RTI - Bomba"] = cont.get(u"RTI - Bomba", 0) + 1

        # Recalque comum
        for eid in ids_rec_comum:
            elem = doc.GetElement(ElementId(eid))
            if not elem: continue
            if eid == eid_rec:
                set_param(elem, P_TRECHO, u"Bomba - Ponto A")
                set_param(elem, P_IDENTIFICADOR, u"Recalque")
                if cota_recalque is not None:
                    set_param(elem, P_COTA, cota_recalque)
            elif eid == ponto_a_id:
                set_param(elem, P_TRECHO, u"Bomba - Ponto A")
                set_param(elem, P_IDENTIFICADOR, u"Ponto A")
            else:
                set_param(elem, P_TRECHO, u"Bomba - Ponto A")
            cont[u"Bomba - Ponto A"] = cont.get(u"Bomba - Ponto A", 0) + 1

        # Ramal HID-01
        for eid in ids_ramal_h1:
            elem = doc.GetElement(ElementId(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 01")
                cont[u"Ponto A - Hid 01"] = cont.get(u"Ponto A - Hid 01", 0) + 1

        # Ramal HID-02
        for eid in ids_ramal_h2:
            elem = doc.GetElement(ElementId(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 02")
                cont[u"Ponto A - Hid 02"] = cont.get(u"Ponto A - Hid 02", 0) + 1

        # HID-01 e HID-02
        set_param(hid01, P_TRECHO, u"Ponto A - Hid 01")
        set_param(hid01, P_IDENTIFICADOR, u"HID-01")
        set_param(hid02, P_TRECHO, u"Ponto A - Hid 02")
        set_param(hid02, P_IDENTIFICADOR, u"HID-02")

        t.Commit()
    except Exception as e:
        t.RollBack()
        forms.alert(u"Erro:\n{}".format(str(e)), title="Fire Utils", warn_icon=True)
        script.exit()

# ===========================================================================
# Resumo
# ===========================================================================
output.print_md("---")
output.print_md(u"### Mapeamento concluido")
output.print_md(u"| Trecho | Elementos |")
output.print_md(u"|---|---|")
for trecho, qtd in sorted(cont.items()):
    output.print_md(u"| {} | {} |".format(trecho, qtd))
output.print_md(u"\n_Proximo passo: Dimensionar Hidrantes._")