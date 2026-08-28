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
    FilteredElementCollector, FamilyInstance,
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

def get_tubo_por_direcao(elem, direcoes):
    """Percorre os conectores nativos de `elem` cuja Direction esteja em
    `direcoes` (In/Out) e retorna o primeiro Pipe conectado a eles.
    Retorna None se nao houver conector com essa direcao conectado a um tubo."""
    for conn in get_conectores(elem):
        try:
            if conn.Direction not in direcoes: continue
            if not conn.IsConnected: continue
            for ref in conn.AllRefs:
                owner = ref.Owner
                if isinstance(owner, Pipe):
                    return owner
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
    tudo que a busca conseguiu percorrer, para diagnostico da quebra."""
    visitados = set([eid_ini])
    fila      = deque([(elem_ini, [eid_ini])])
    while fila:
        elem, caminho = fila.popleft()
        if get_id(elem) == eid_alvo:
            return caminho, visitados
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
            _alterou  = False
            if _p_trecho and not _p_trecho.IsReadOnly and _p_trecho.AsString():
                _p_trecho.Set(u"")
                _alterou = True
            if _p_ident and not _p_ident.IsReadOnly and _p_ident.AsString():
                _p_ident.Set(u"")
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

rti   = seleciona(u"Selecione o reservatorio (RTI).",     u"Reservatorio (RTI)",    FittingFilter())
bomba = seleciona(u"Selecione a bomba de incendio.",      u"Bomba de incendio",     FittingFilter())

output.print_md(u"RTI: ID **{}** | Bomba: ID **{}**".format(get_id(rti), get_id(bomba)))

tubo_rti = get_tubo_por_direcao(rti, (FlowDirectionType.Out,))
if not tubo_rti:
    tubo_rti = seleciona(
        u"Nao foi possivel identificar automaticamente o tubo conectado a RTI.\n"
        u"Selecione o tubo que conecta na RTI.",
        u"Tubo da RTI", PipeFilter()
    )

tubo_bomba = get_tubo_por_direcao(bomba, (FlowDirectionType.In,))
if not tubo_bomba:
    tubo_bomba = seleciona(
        u"Nao foi possivel identificar automaticamente o tubo de entrada (succao) da bomba.\n"
        u"Selecione o tubo que conecta na entrada da bomba.",
        u"Tubo succao bomba", PipeFilter()
    )

tubo_rec = get_tubo_por_direcao(bomba, (FlowDirectionType.Out,))
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
            elif eid == eid_bomba:
                set_param(elem, P_TRECHO, u"RTI - Bomba")
                set_param(elem, P_IDENTIFICADOR, u"Succao")
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