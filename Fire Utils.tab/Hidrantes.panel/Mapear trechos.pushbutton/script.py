# -*- coding: utf-8 -*-
"""
script.py — Mapear Trechos de Hidrante

Não depende mais de seleção manual dos hidrantes mais desfavoráveis: a
partir da Bomba, percorre em árvore toda a rede de recalque (ramificando
em cada Tê/conexão) até achar uma instância da família "Valvula para
Hidrante" em cada folha — cada caminho completo (Bomba → válvula) é uma
rota.

Cada rota é pontuada por um cálculo simples e direto Bomba → Válvula (sem
subdividir em trechos), com a vazão nominal de um hidrante e a perda por
desnível geométrico somada — quanto maior o score, mais desfavorável.
Todas as válvulas achadas recebem "FireUtils - ID Hidrante" (H-01, H-02...)
nessa ordem, do mais desfavorável ao mais favorável.

As duas rotas mais desfavoráveis (H-01, H-02) definem o dimensionamento:
o Ponto A é o último elemento em comum entre as duas rotas, antes de
divergirem. Os parâmetros "FireUtils - Trecho"/"Identificador" continuam
sendo gravados nesses elementos — mas só para o usuário acompanhar
visualmente no Revit. O motor de cálculo ("Dimensionar Hidrantes") não lê
mais esses parâmetros: lê as listas de ElementId salvas no cache
(firedata.json, chave 'rotas'), abaixo.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, Transaction, ElementId,
    FlowDirectionType,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script
from System.Collections.Generic import List

from projeto import exigir_projeto_e_estado
from hidrantes.params import create_hydrant_params
from hidrantes.norm_profiles import get_profile, req
from hidrantes.sistema import resolver_dados_sistema
from hidrantes.calc import extrair_trecho, calc_j_trecho, salvar_cache
from hidrantes.rede import (
    get_id, get_cota_conector, get_primeiro_tubo, bfs_ate,
    percorre_rotas_hidrantes, get_pontas_abertas, diagnostico_conectores,
    get_comprimento, get_diametro, get_leq, get_nome,
)

P_TRECHO        = u"FireUtils - Trecho"
P_IDENTIFICADOR = u"FireUtils - Identificador"
P_ID_HIDRANTE   = u"FireUtils - ID Hidrante"

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

output.print_md("# Fire Utils - Mapear Trechos de Hidrante")

# ===========================================================================
# Helpers de UI
# ===========================================================================

def set_param(elem, nome, valor):
    try:
        p = elem.LookupParameter(nome)
        if p and not p.IsReadOnly:
            p.Set(valor)
            return True
    except: pass
    return False

def reporta_quebra(visitados, alvo_desc):
    """Mostra onde o rastreamento parou: quantos elementos foram
    alcancados e, se houver, os IDs com conector aberto (clicaveis
    para selecionar/mostrar no Revit)."""
    output.print_md(u"**Caminho ate {} nao encontrado.**".format(alvo_desc))
    output.print_md(u"{} elemento(s) alcancado(s) antes de parar.".format(len(visitados)))
    pontas = get_pontas_abertas(doc, visitados)
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
# 0 — Projeto/estado, sistema classificado e parâmetros
# ===========================================================================
output.print_md("---")
output.print_md("### 0 - Verificando Projeto e Sistema Classificado")

projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)
perfil = get_profile(sigla_estado)

# Precisa do sistema já classificado ("Classificar Sistema de Hidrante")
# para saber a vazão nominal de um hidrante (Qs) - usada abaixo para
# pontuar cada rota achada pela vazão simples.
_valor_sistema, _dados_sistema = resolver_dados_sistema(doc, perfil, forms, script)
Qs_lmin = _dados_sistema[u"q_min"]
C_HW    = req(perfil, u"hazen_c")[u"galvanizado"]

output.print_md(u"Sistema: **{}** | Vazão nominal: **{:g} L/min**".format(_valor_sistema, Qs_lmin))

output.print_md("---")
output.print_md("### 0b - Verificando Parametros")
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
# 0c — Reset: limpa parâmetros FireUtils de todo o modelo
# ===========================================================================
output.print_md("---")
output.print_md("### 0c - Resetando mapeamento anterior")

_todos = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
_resetados = 0
with Transaction(doc, "FireUtils - Reset Mapeamento") as _t:
    _t.Start()
    try:
        for _elem in _todos:
            _alterou = False
            for _nome_p in (P_TRECHO, P_IDENTIFICADOR, P_ID_HIDRANTE):
                _p = _elem.LookupParameter(_nome_p)
                if _p and not _p.IsReadOnly and _p.AsString():
                    _p.Set(u"")
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
# 1 — Seleciona RTI e Bomba (usa as conexões nativas de entrada/saída)
# ===========================================================================
output.print_md("---")
output.print_md("### 1 - Selecionar RTI e Bomba")

rti = seleciona(u"Selecione o reservatorio (RTI).", u"Reservatorio (RTI)", FittingFilter())
output.print_md(u"RTI: ID **{}**".format(get_id(rti)))

tubo_rti = get_primeiro_tubo(rti, (FlowDirectionType.Out,))
rti_auto_detectada = tubo_rti is not None
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

# ===========================================================================
# 2 — BFS: sucção (RTI → Bomba)
# ===========================================================================
output.print_md("---")
output.print_md("### 2 - Mapeando Succao (RTI > Bomba)")

caminho_succao, visitados_succao = bfs_ate(tubo_rti, eid_rti, eid_bomba)
if not caminho_succao:
    reporta_quebra(visitados_succao, u"entrada da bomba (succao)")
    forms.alert(u"Caminho nao encontrado entre saida RTI e entrada da bomba.",
                title="Fire Utils", warn_icon=True)
    script.exit()
ids_succao = caminho_succao
output.print_md(u"{} elemento(s) no trecho de succao".format(len(ids_succao)))

# ===========================================================================
# 3 — Percorre a árvore de recalque até todas as válvulas de hidrante
# ===========================================================================
output.print_md("---")
output.print_md("### 3 - Percorrendo a Arvore de Recalque")

rotas = percorre_rotas_hidrantes(tubo_rec, eid_rec)
if not rotas:
    forms.alert(
        u"Nenhuma valvula de hidrante ('Valvula para Hidrante') foi encontrada "
        u"percorrendo a rede a partir da saida da bomba.\n\n"
        u"Verifique se a tubulacao de recalque esta conectada ate as valvulas.",
        title="Fire Utils", warn_icon=True)
    script.exit()

output.print_md(u"{} rota(s) encontrada(s) ate uma valvula de hidrante.".format(len(rotas)))

if len(rotas) < 2:
    forms.alert(
        u"Apenas {} valvula(s) de hidrante encontrada(s) na rede de recalque.\n\n"
        u"O dimensionamento exige pelo menos 2 hidrantes (os mais desfavoraveis "
        u"em funcionamento simultaneo).".format(len(rotas)),
        title="Fire Utils", warn_icon=True)
    script.exit()

# ===========================================================================
# 4 — Pontua cada rota: perda por atrito (vazao simples) + desnivel
# ===========================================================================
output.print_md("---")
output.print_md("### 4 - Pontuando as Rotas (Bomba > Valvula, vazao simples)")

z_recalque_bomba = get_cota_conector(bomba, (FlowDirectionType.Out,))
if z_recalque_bomba is None:
    detalhes = [u"Nao foi possivel ler a elevacao de saida (recalque) da bomba:"]
    detalhes.extend(diagnostico_conectores(bomba))
    forms.alert(u"\n".join(detalhes), title="Fire Utils", warn_icon=True)
    script.exit()

candidatas = []
for rota in rotas:
    valvula = doc.GetElement(ElementId(rota[-1]))
    z_valvula = get_cota_conector(valvula)
    if z_valvula is None:
        detalhes = [u"Nao foi possivel ler a elevacao da valvula (ID {}):".format(valvula.Id)]
        detalhes.extend(diagnostico_conectores(valvula))
        forms.alert(u"\n".join(detalhes), title="Fire Utils", warn_icon=True)
        script.exit()

    elems = [doc.GetElement(ElementId(eid)) for eid in rota]
    trecho_data = extrair_trecho(elems, get_comprimento, get_diametro, get_leq, get_nome)
    jt = calc_j_trecho(trecho_data, Qs_lmin, C_HW, u"Bomba > Valvula (score)")
    score = jt["J"] + (z_valvula - z_recalque_bomba)

    candidatas.append({
        u"rota":    rota,
        u"valvula": valvula,
        u"score":   score,
    })

candidatas.sort(key=lambda c: c[u"score"], reverse=True)

output.print_md(u"| # | ID Hidrante | ID Elemento | Score (mca) |")
output.print_md(u"|---|---|---|---|")
for i, c in enumerate(candidatas):
    output.print_md(u"| {} | H-{:02d} | {} | {:.4f} |".format(
        i + 1, i + 1, c[u"valvula"].Id, c[u"score"]))

# ===========================================================================
# 5 — Grava "FireUtils - ID Hidrante" em todas as valvulas (ordem de
#     desfavorabilidade) e identifica o Ponto A entre as 2 piores
# ===========================================================================
output.print_md("---")
output.print_md("### 5 - Gravando ID Hidrante e Identificando Ponto A")

rota_h1, rota_h2 = candidatas[0][u"rota"], candidatas[1][u"rota"]
set_h2   = set(rota_h2)
comuns   = [eid for eid in rota_h1 if eid in set_h2]
if not comuns:
    forms.alert(u"Ponto A nao encontrado entre as 2 rotas mais desfavoraveis.",
                title="Fire Utils", warn_icon=True)
    script.exit()

ponto_a_id = comuns[-1]
idx_a_h1   = rota_h1.index(ponto_a_id)
idx_a_h2   = rota_h2.index(ponto_a_id)

ids_rec_comum = rota_h1[:idx_a_h1 + 1]   # Bomba -> Ponto A (inclusive)
ids_ramal_h1  = rota_h1[idx_a_h1 + 1:]   # Ponto A -> H-01 (inclusive da valvula)
ids_ramal_h2  = rota_h2[idx_a_h2 + 1:]   # Ponto A -> H-02 (inclusive da valvula)

output.print_md(u"Ponto A: ID **{}**".format(ponto_a_id))
output.print_md(u"[debug] Rec. comum: {} | Ramal H-01: {} | Ramal H-02: {} elementos".format(
    len(ids_rec_comum), len(ids_ramal_h1), len(ids_ramal_h2)))

# ===========================================================================
# 6 — Preenche parâmetros (visual — o motor de cálculo lê o cache, não isso)
# ===========================================================================
output.print_md("---")
output.print_md("### 6 - Preenchendo Parametros")

cont = {}

with Transaction(doc, "FireUtils - Mapear Trechos") as t:
    t.Start()
    try:
        # RTI e bomba - marcados direto na propria familia, para o
        # "Dimensionar Hidrantes" achar o elemento sem precisar percorrer
        # a rede e ler a cota do conector real dele. Se a RTI nao foi
        # detectada automaticamente (fallback manual: o tubo de saida foi
        # clicado, nao achado pelo conector), quem recebe o identificador
        # "RTI" e o proprio tubo, nao a familia - so um dos dois pode
        # carregar essa tag.
        if rti_auto_detectada:
            set_param(rti, P_IDENTIFICADOR, u"RTI")
        else:
            set_param(tubo_rti, P_IDENTIFICADOR, u"RTI")
        set_param(bomba, P_IDENTIFICADOR, u"Bomba")

        # ID Hidrante em TODAS as valvulas achadas, na ordem de desfavorabilidade
        for i, c in enumerate(candidatas):
            set_param(c[u"valvula"], P_ID_HIDRANTE, u"H-{:02d}".format(i + 1))

        # Sucção
        for eid in ids_succao:
            elem = doc.GetElement(ElementId(eid))
            if elem:
                set_param(elem, P_TRECHO, u"RTI - Bomba")
                cont[u"RTI - Bomba"] = cont.get(u"RTI - Bomba", 0) + 1

        # Recalque comum
        for eid in ids_rec_comum:
            elem = doc.GetElement(ElementId(eid))
            if not elem: continue
            set_param(elem, P_TRECHO, u"Bomba - Ponto A")
            if eid == ponto_a_id:
                set_param(elem, P_IDENTIFICADOR, u"Ponto A")
            cont[u"Bomba - Ponto A"] = cont.get(u"Bomba - Ponto A", 0) + 1

        # Ramal H-01
        for eid in ids_ramal_h1:
            elem = doc.GetElement(ElementId(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 01")
                cont[u"Ponto A - Hid 01"] = cont.get(u"Ponto A - Hid 01", 0) + 1

        # Ramal H-02
        for eid in ids_ramal_h2:
            elem = doc.GetElement(ElementId(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 02")
                cont[u"Ponto A - Hid 02"] = cont.get(u"Ponto A - Hid 02", 0) + 1

        t.Commit()
    except Exception as e:
        t.RollBack()
        forms.alert(u"Erro:\n{}".format(str(e)), title="Fire Utils", warn_icon=True)
        script.exit()

# ===========================================================================
# 7 — Salva a rota interna no cache (chave 'rotas'), para "Dimensionar
#     Hidrantes" ler direto por ElementId — sem depender dos parametros
# ===========================================================================
salvar_cache({
    u"t1":         list(ids_succao),
    u"t2":         list(ids_rec_comum),
    u"t3":         list(ids_ramal_h1),
    u"t4":         list(ids_ramal_h2),
    u"ponto_a_id": ponto_a_id,
}, projeto_dir, chave=u"rotas")

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
