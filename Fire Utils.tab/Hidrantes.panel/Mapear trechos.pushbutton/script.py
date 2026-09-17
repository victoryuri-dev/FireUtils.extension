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
    FilteredElementCollector, FamilyInstance, Transaction,
    FlowDirectionType,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script

from projeto import exigir_projeto_e_estado
from hidrantes.params import create_hydrant_params
from hidrantes.norm_profiles import get_profile, req
from hidrantes.sistema import resolver_dados_sistema
from hidrantes.calc import extrair_trecho, calc_j_trecho, salvar_cache
from hidrantes.rede import (
    get_id, to_element_id, get_cota_conector, get_primeiro_tubo, bfs_ate,
    percorre_rotas_hidrantes, get_pontas_abertas, diagnostico_conectores,
    descricao_curta_elemento, todas_valvulas_hidrante, mostrar_no_revit,
    get_comprimento, get_diametro, get_leq, get_nome,
)
from hidrantes.resultado_ui import mostrar_inconsistencias_mapeamento
from hidrantes.fila_acoes import criar_fila_acoes

P_TRECHO        = u"FireUtils - Trecho"
P_IDENTIFICADOR = u"FireUtils - Identificador"
P_ID_HIDRANTE   = u"FireUtils - ID Hidrante"

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument

# Fila de ExternalEvent pro botao "Localizar" das janelas de inconsistencia
# (mostrar_inconsistencias_mapeamento) - criada aqui, no corpo do script
# (contexto de API valido), nao dentro de um handler de clique.
fila_acoes = criar_fila_acoes()

def _ao_localizar(uiapp, eid):
    mostrar_no_revit(uiapp.ActiveUIDocument, [eid])

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

def _itens_pontas(origem, pontas):
    """Monta os itens {trecho, elemento, eid} pra janela de
    inconsistências, um por ponta aberta encontrada em `origem`
    (Sucção ou Recalque)."""
    itens = []
    for eid in pontas:
        elem = doc.GetElement(to_element_id(eid))
        descricao = (descricao_curta_elemento(elem) if elem is not None
                     else u"ID {} (elemento não encontrado no modelo)".format(eid))
        itens.append({u"trecho": origem, u"elemento": descricao, u"eid": eid})
    return itens

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
        script.exit()

# ===========================================================================
# 0 — Projeto/estado, sistema classificado e parâmetros
# ===========================================================================
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)
perfil = get_profile(sigla_estado)

# Precisa do sistema já classificado ("Classificar Sistema de Hidrante")
# para saber a vazão nominal de um hidrante (Qs) - usada abaixo para
# pontuar cada rota achada pela vazão simples.
_valor_sistema, _dados_sistema = resolver_dados_sistema(doc, perfil, forms, script)
Qs_lmin = _dados_sistema[u"q_min"]
C_HW    = req(perfil, u"hazen_c")[u"galvanizado"]

try:
    create_hydrant_params(doc)
except Exception as e:
    forms.alert(u"Erro ao criar parametros:\n{}".format(str(e)), title="Fire Utils", warn_icon=True)
    script.exit()

# ===========================================================================
# 0c — Reset: limpa parâmetros FireUtils de todo o modelo
# ===========================================================================
_todos = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
with Transaction(doc, "FireUtils - Reset Mapeamento") as _t:
    _t.Start()
    try:
        for _elem in _todos:
            for _nome_p in (P_TRECHO, P_IDENTIFICADOR, P_ID_HIDRANTE):
                _p = _elem.LookupParameter(_nome_p)
                if _p and not _p.IsReadOnly and _p.AsString():
                    _p.Set(u"")
        _t.Commit()
    except Exception as _e:
        _t.RollBack()
        forms.alert(u"Erro ao resetar mapeamento:\n{}".format(str(_e)),
                    title="Fire Utils", warn_icon=True)
        script.exit()

# ===========================================================================
# 1 — Seleciona RTI e Bomba (usa as conexões nativas de entrada/saída)
# ===========================================================================
rti = seleciona(u"Selecione o reservatorio (RTI).", u"Reservatorio (RTI)", FittingFilter())

tubo_rti = get_primeiro_tubo(rti, (FlowDirectionType.Out,))
rti_auto_detectada = tubo_rti is not None
if not tubo_rti:
    tubo_rti = seleciona(
        u"Nao foi possivel identificar o tubo de saida da RTI.\n"
        u"Clique no tubo de saida da RTI.",
        u"Tubo de saida da RTI", PipeFilter()
    )

bomba = seleciona(u"Selecione a bomba de incendio.", u"Bomba de incendio", FittingFilter())

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

# ===========================================================================
# 2 — BFS: sucção (RTI → Bomba)
# ===========================================================================
caminho_succao, visitados_succao = bfs_ate(tubo_rti, eid_rti, eid_bomba)
if not caminho_succao:
    pontas = get_pontas_abertas(doc, visitados_succao)
    if pontas:
        itens = _itens_pontas(u"Sucção (RTI → Bomba)", pontas)
    else:
        itens = [{u"trecho":   u"Sucção (RTI → Bomba)",
                  u"elemento": u"{} elemento(s) alcançado(s), sem conector aberto "
                               u"identificado — categoria sem suporte a conectores?".format(
                                   len(visitados_succao)),
                  u"eid":      eid_rti}]
    mostrar_inconsistencias_mapeamento(itens, bloqueante=True,
                                       fila_acoes=fila_acoes, ao_localizar=_ao_localizar)
    script.exit()
ids_succao = caminho_succao

# ===========================================================================
# 3 — Percorre a árvore de recalque até todas as válvulas de hidrante
# ===========================================================================
rotas, pontas_recalque = percorre_rotas_hidrantes(tubo_rec, eid_rec)

# Só bloqueia o mapeamento se alguma valvula de hidrante que existe no
# projeto ficou de fora - nao por qualquer beco sem saida (dreno, ramal
# morto etc.), que e so um aviso pro usuario revisar.
ids_valvulas_alcancadas = set(rota[-1] for rota in rotas)
valvulas_sem_rota = [v for v in todas_valvulas_hidrante(doc)
                     if get_id(v) not in ids_valvulas_alcancadas]

itens_recalque = [
    {u"trecho": u"Válvula sem rota", u"elemento": descricao_curta_elemento(v), u"eid": get_id(v)}
    for v in valvulas_sem_rota
]
itens_recalque.extend(_itens_pontas(u"Recalque (Bomba → Válvulas)", pontas_recalque))

if itens_recalque:
    bloqueante = bool(valvulas_sem_rota)
    mostrar_inconsistencias_mapeamento(itens_recalque, bloqueante=bloqueante,
                                       fila_acoes=fila_acoes, ao_localizar=_ao_localizar)
    if bloqueante:
        script.exit()

if not rotas:
    forms.alert(
        u"Nenhuma valvula de hidrante ('Valvula para Hidrante') foi encontrada "
        u"percorrendo a rede a partir da saida da bomba.\n\n"
        u"Verifique se a tubulacao de recalque esta conectada ate as valvulas.",
        title="Fire Utils", warn_icon=True)
    script.exit()

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
z_recalque_bomba = get_cota_conector(bomba, (FlowDirectionType.Out,))
if z_recalque_bomba is None:
    detalhes = [u"Nao foi possivel ler a elevacao de saida (recalque) da bomba:"]
    detalhes.extend(diagnostico_conectores(bomba))
    forms.alert(u"\n".join(detalhes), title="Fire Utils", warn_icon=True)
    script.exit()

candidatas = []
for rota in rotas:
    valvula = doc.GetElement(to_element_id(rota[-1]))
    z_valvula = get_cota_conector(valvula)
    if z_valvula is None:
        detalhes = [u"Nao foi possivel ler a elevacao da valvula (ID {}):".format(valvula.Id)]
        detalhes.extend(diagnostico_conectores(valvula))
        forms.alert(u"\n".join(detalhes), title="Fire Utils", warn_icon=True)
        script.exit()

    elems = [doc.GetElement(to_element_id(eid)) for eid in rota]
    try:
        trecho_data = extrair_trecho(elems, get_comprimento, get_diametro, get_leq, get_nome)
    except ValueError as _e:
        forms.alert(u"{}".format(_e), title="Fire Utils", warn_icon=True)
        script.exit()
    jt = calc_j_trecho(trecho_data, Qs_lmin, C_HW, u"Bomba > Valvula (score)")
    score = jt["J"] + (z_valvula - z_recalque_bomba)

    candidatas.append({
        u"rota":    rota,
        u"valvula": valvula,
        u"score":   score,
    })

candidatas.sort(key=lambda c: c[u"score"], reverse=True)

# ===========================================================================
# 5 — Grava "FireUtils - ID Hidrante" em todas as valvulas (ordem de
#     desfavorabilidade) e identifica o Ponto A entre as 2 piores
# ===========================================================================
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

# ===========================================================================
# 6 — Preenche parâmetros (visual — o motor de cálculo lê o cache, não isso)
# ===========================================================================
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
            elem = doc.GetElement(to_element_id(eid))
            if elem:
                set_param(elem, P_TRECHO, u"RTI - Bomba")

        # Recalque comum
        for eid in ids_rec_comum:
            elem = doc.GetElement(to_element_id(eid))
            if not elem: continue
            set_param(elem, P_TRECHO, u"Bomba - Ponto A")
            if eid == ponto_a_id:
                set_param(elem, P_IDENTIFICADOR, u"Ponto A")

        # Ramal H-01
        for eid in ids_ramal_h1:
            elem = doc.GetElement(to_element_id(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 01")

        # Ramal H-02
        for eid in ids_ramal_h2:
            elem = doc.GetElement(to_element_id(eid))
            if elem:
                set_param(elem, P_TRECHO, u"Ponto A - Hid 02")

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
