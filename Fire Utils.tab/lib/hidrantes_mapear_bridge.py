# -*- coding: utf-8 -*-
"""
hidrantes_mapear_bridge.py — Fire Utils · lib/
Processa MAPEAR_TRECHOS e CONTINUAR_MAPEAMENTO: o antigo pushbutton "Mapear
Trechos", agora disparado pela dockpane (página "Sistema de Hidrantes").

Não depende de seleção manual dos hidrantes mais desfavoráveis: a partir da
Bomba, percorre em árvore toda a rede de recalque (ramificando em cada
Tê/conexão) até achar uma instância da família "Valvula para Hidrante" em
cada folha — cada caminho completo (Bomba -> válvula) é uma rota.

Cada rota é pontuada por um cálculo simples e direto Bomba -> Válvula (sem
subdividir em trechos), com a vazão nominal de um hidrante e a perda por
desnível geométrico somada — quanto maior o score, mais desfavorável. Todas
as válvulas achadas recebem "FireUtils - ID Hidrante" (H-01, H-02...) nessa
ordem, do mais desfavorável ao mais favorável.

As duas rotas mais desfavoráveis (H-01, H-02) definem o dimensionamento: o
Ponto A é o último elemento em comum entre as duas rotas, antes de
divergirem. Os parâmetros "FireUtils - Trecho"/"Identificador" são gravados
nesses elementos só para o usuário acompanhar visualmente no Revit; quem
alimenta o dimensionamento (hidrantes_dimensionar_bridge.py) são as listas
de ElementId salvas no cache (firedata.json, chave "rotas"), além do ranking
COMPLETO de hidrantes, que segue junto no resultado do dimensionamento.

Diferente do pushbutton, o usuário clica e escolhe elementos NO REVIT
enquanto a dockpane continua aberta ao lado. O fluxo, tudo na thread de API
(chamados via fila_acoes pelo dispatcher):

  MAPEAR_TRECHOS      -> pede RTI e Bomba no modelo (PickObject; a dockpane
                         recebe HIDRANTES_MAPEAR_PROGRESSO a cada pedido, para
                         dizer o que fazer no Revit), percorre a rede e
                         responde com HIDRANTES_MAPEAR_RESULTADO:
                           - ok, trechos          mapeado e gravado;
                           - ok, pendente, itens  achou inconsistências que o
                                                  usuário pode ignorar: o
                                                  mapeamento espera um
                                                  CONTINUAR_MAPEAMENTO;
                           - não ok, itens        inconsistência que impede o
                                                  mapeamento (sem rota nenhuma);
                           - não ok, erro         qualquer outra falha (ou
                                                  categoria "cancelado": o
                                                  usuário apertou Esc).
  CONTINUAR_MAPEAMENTO -> o usuário decidiu ignorar as inconsistências
                         pendentes: grava e responde como acima.

Os botões "Localizar" da dockpane usam SELECIONAR_TRECHO_HIDRANTE, que já
existia (hidrantes_dimensionamento_bridge.py): cada item e cada trecho traz a
lista de ElementId para selecionar e enquadrar no Revit.
"""

import os

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, Transaction, FlowDirectionType,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

import licenca
from projeto import carregar_dados_projeto, salvar_ponteiro
from hidrantes.params import create_hydrant_params
from hidrantes.norm_profiles import get_profile, req, NormProfileError
from hidrantes.sistema import resolver_dados_sistema_puro
from hidrantes.calc import extrair_trecho, calc_j_trecho, salvar_cache
from hidrantes.rede import (
    get_id, to_element_id, get_primeiro_tubo, bfs_ate,
    percorre_rotas_hidrantes, get_pontas_abertas, descricao_curta_elemento,
    todas_valvulas_hidrante, get_cota_conector, diagnostico_conectores,
    get_comprimento, get_diametro_no_trecho, get_leq, get_nome,
)
from family_error_utils import texto_erro

P_TRECHO        = u"FireUtils - Trecho"
P_IDENTIFICADOR = u"FireUtils - Identificador"
P_ID_HIDRANTE   = u"FireUtils - ID Hidrante"

_TIPO_PROGRESSO = u"HIDRANTES_MAPEAR_PROGRESSO"
_TIPO_RESULTADO = u"HIDRANTES_MAPEAR_RESULTADO"

# Mapeamento que achou inconsistências e espera a decisão do usuário. Guarda
# só ElementId (int) e números: os elementos são relidos na hora de continuar,
# porque o modelo pode ter mudado enquanto a dockpane esperava.
_pendente = None


class _Interrompido(Exception):
    """Encerra o mapeamento com uma resposta pronta para a dockpane."""

    def __init__(self, erro, categoria=u"requisito", itens=None):
        Exception.__init__(self, erro)
        self.resposta = {u"ok": False, u"erro": erro, u"categoria": categoria}
        if itens is not None:
            self.resposta[u"itens"] = itens


class _FiltroTubo(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, Pipe)

    def AllowReference(self, r, p):
        return False


class _FiltroEquipamento(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, FamilyInstance)

    def AllowReference(self, r, p):
        return False


def _selecionar(uidoc, postar_mensagem, instrucao, prompt, filtro):
    """
    Pede um elemento no modelo. A instrução vai para a dockpane (o usuário
    está olhando para ela) e o prompt para a barra de status do Revit. Esc
    cancela o mapeamento inteiro.
    """
    postar_mensagem(_TIPO_PROGRESSO, {u"instrucao": instrucao})
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, filtro, prompt)
    except OperationCanceledException:
        raise _Interrompido(u"Mapeamento cancelado.", u"cancelado")
    return uidoc.Document.GetElement(ref.ElementId)


def _itens_pontas(doc, origem, pontas, caminhos):
    """Itens {trecho, elemento, eids} da lista de inconsistências, um por
    ponta aberta encontrada em `origem` (Sucção ou Recalque). `eids` traz a
    rota COMPLETA (ponto de partida da busca até a ponta aberta, ambos
    inclusive — ver bfs_ate), não só o elemento isolado: "Localizar" na
    dockpane seleciona/enquadra o trecho inteiro no Revit, não um ponto
    solto sem contexto de onde ele está na rede."""
    itens = []
    for eid in pontas:
        elem = doc.GetElement(to_element_id(eid))
        descricao = (descricao_curta_elemento(elem) if elem is not None
                     else u"ID {} (elemento não encontrado no modelo)".format(eid))
        itens.append({u"trecho": origem, u"elemento": descricao,
                      u"eids": caminhos.get(eid, [eid])})
    return itens


def _set_param(elem, nome, valor):
    try:
        p = elem.LookupParameter(nome)
        if p and not p.IsReadOnly:
            p.Set(valor)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def tratar_mapear_trechos(uiapp, payload, fila_acoes, postar_mensagem):
    # Mesmo cuidado de hidrantes_dimensionar_bridge.py: exceção sem resposta
    # deixaria a dockpane em "Mapeando..." para sempre.
    global _pendente
    _pendente = None
    try:
        _mapear(uiapp, postar_mensagem)
    except _Interrompido as ex:
        postar_mensagem(_TIPO_RESULTADO, ex.resposta)
    except Exception as ex:
        postar_mensagem(_TIPO_RESULTADO, {
            u"ok": False, u"categoria": u"servidor",
            u"erro": u"Falha inesperada ao mapear os trechos: {}".format(texto_erro(ex)),
        })


def tratar_continuar_mapeamento(uiapp, payload, fila_acoes, postar_mensagem):
    global _pendente
    pendente, _pendente = _pendente, None
    try:
        if pendente is None:
            raise _Interrompido(
                u"Não há mapeamento esperando confirmação. Mapeie os trechos de novo.")
        resultado = _gravar(uiapp.ActiveUIDocument.Document, pendente)
        postar_mensagem(_TIPO_RESULTADO, resultado)
    except _Interrompido as ex:
        postar_mensagem(_TIPO_RESULTADO, ex.resposta)
    except Exception as ex:
        postar_mensagem(_TIPO_RESULTADO, {
            u"ok": False, u"categoria": u"servidor",
            u"erro": u"Falha inesperada ao gravar o mapeamento: {}".format(texto_erro(ex)),
        })


# ---------------------------------------------------------------------------
# Mapeamento
# ---------------------------------------------------------------------------

def _mapear(uiapp, postar_mensagem):
    global _pendente

    if not licenca.tem_acesso(u"hidrantes"):
        raise _Interrompido(
            u"Esta conta não tem o módulo Hidrantes liberado neste computador. "
            u"Abra o painel com internet para atualizar a licença.",
            u"licenca")

    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        raise _Interrompido(u"Salve o projeto Revit (.rvt) antes de mapear os trechos.")
    doc = uidoc.Document
    projeto_dir = os.path.dirname(doc.PathName)
    salvar_ponteiro(projeto_dir)

    dados_projeto = carregar_dados_projeto(projeto_dir) or {}
    # Mesmo padrão dos demais bridges de hidrantes: sem UF vinculada, MA.
    sigla_estado = dados_projeto.get(u"uf") or u"MA"

    try:
        perfil = get_profile(sigla_estado, projeto_dir)
    except NormProfileError as ex:
        raise _Interrompido(texto_erro(ex), u"norma")

    # Precisa do sistema já classificado para saber a vazão nominal de um
    # hidrante (Qs), usada para pontuar cada rota.
    erro, _valor_sistema, dados_sistema = resolver_dados_sistema_puro(doc, perfil)
    if erro:
        raise _Interrompido(erro)
    qs_lmin = dados_sistema[u"q_min"]
    c_hw = req(perfil, u"hazen_c")[u"galvanizado"]

    try:
        create_hydrant_params(doc)
    except Exception as ex:
        raise _Interrompido(u"Erro ao criar parâmetros: {}".format(texto_erro(ex)), u"servidor")

    # --- RTI e Bomba (conexões nativas de entrada/saída) -------------------
    rti = _selecionar(
        uidoc, postar_mensagem,
        u"Clique no reservatório (RTI) no Revit.",
        u"Selecione o reservatório (RTI)", _FiltroEquipamento())

    tubo_rti, interm_rti = get_primeiro_tubo(rti, (FlowDirectionType.Out,))
    rti_auto = tubo_rti is not None
    if tubo_rti is None:
        tubo_rti = _selecionar(
            uidoc, postar_mensagem,
            u"Não deu para identificar o tubo de saída da RTI. Clique nesse tubo no Revit.",
            u"Tubo de saída da RTI", _FiltroTubo())
        interm_rti = []

    bomba = _selecionar(
        uidoc, postar_mensagem,
        u"Clique na bomba de incêndio no Revit.",
        u"Selecione a bomba de incêndio", _FiltroEquipamento())

    tubo_bomba, interm_succao_bomba = get_primeiro_tubo(bomba, (FlowDirectionType.In,))
    if tubo_bomba is None:
        tubo_bomba = _selecionar(
            uidoc, postar_mensagem,
            u"Não deu para identificar o tubo de entrada (sucção) da bomba. "
            u"Clique no tubo que conecta na entrada da bomba.",
            u"Tubo de sucção da bomba", _FiltroTubo())
        interm_succao_bomba = []

    tubo_rec, interm_recalque_bomba = get_primeiro_tubo(bomba, (FlowDirectionType.Out,))
    if tubo_rec is None:
        tubo_rec = _selecionar(
            uidoc, postar_mensagem,
            u"Não deu para identificar o tubo de saída (recalque) da bomba. "
            u"Clique no tubo que conecta na saída da bomba.",
            u"Tubo de recalque da bomba", _FiltroTubo())
        interm_recalque_bomba = []

    postar_mensagem(_TIPO_PROGRESSO, {u"instrucao": u"Percorrendo a rede…"})

    eid_rti = get_id(tubo_rti)
    eid_bomba = get_id(tubo_bomba)
    eid_rec = get_id(tubo_rec)

    # Acessórios/válvulas entre a RTI/bomba e o primeiro tubo de verdade (ex.:
    # válvula de gaveta, válvula de retenção vertical instaladas direto na
    # conexão) — get_primeiro_tubo não descarta mais esses elementos; aqui
    # eles entram nos trechos correspondentes (sucção ou recalque), pra
    # contar na perda de carga (parâmetro "Perda de Carga", ver get_leq).
    ids_interm_rti = [get_id(e) for e in interm_rti]
    ids_interm_succao_bomba = [get_id(e) for e in interm_succao_bomba]
    ids_interm_recalque_bomba = [get_id(e) for e in interm_recalque_bomba]

    # --- Sucção (RTI -> Bomba) ----------------------------------------------
    caminho_succao, visitados_succao, caminhos_succao = bfs_ate(tubo_rti, eid_rti, eid_bomba)
    if not caminho_succao:
        pontas = get_pontas_abertas(doc, visitados_succao)
        if pontas:
            itens = _itens_pontas(doc, u"Sucção (RTI → Bomba)", pontas, caminhos_succao)
        else:
            itens = [{
                u"trecho": u"Sucção (RTI → Bomba)",
                u"elemento": u"{} elemento(s) alcançado(s), sem conector aberto identificado "
                             u"— categoria sem suporte a conectores?".format(len(visitados_succao)),
                u"eids": list(visitados_succao),
            }]
        raise _Interrompido(
            u"A sucção não chega da RTI até a bomba. Corrija a tubulação nos pontos abaixo.",
            u"inconsistencia", itens)
    caminho_succao = ids_interm_rti + caminho_succao + ids_interm_succao_bomba

    # --- Recalque: árvore Bomba -> válvulas -----------------------------------
    # Ramais que não levam a hidrante nenhum (dreno, teste de bomba, cavalete)
    # nunca entram em `rotas`, então não afetam o ranking.
    rotas = percorre_rotas_hidrantes(tubo_rec, eid_rec)
    rotas = [ids_interm_recalque_bomba + rota for rota in rotas]

    ids_alcancadas = set(rota[-1] for rota in rotas)
    valvulas_sem_rota = [v for v in todas_valvulas_hidrante(doc)
                         if get_id(v) not in ids_alcancadas]

    # Inconsistência de recalque = busca à parte, direcionada por válvula
    # (válvula -> bomba), só para as que a árvore não alcançou. Assim um ramal
    # legítimo sem hidrante (tubo de teste de bomba, com a ponta solta de
    # propósito) não é confundido com uma quebra de verdade.
    itens_recalque = []
    for valvula in valvulas_sem_rota:
        eid_valvula = get_id(valvula)
        caminho, visitados, caminhos = bfs_ate(valvula, eid_valvula, eid_rec)
        if caminho:
            # A árvore não passou por essa válvula, mas a busca à parte achou
            # caminho: sinal de anel fechado na modelagem (um elemento
            # compartilhado por dois galhos). Reportado à parte, sem entrar
            # no ranking — "eids" traz a rota inteira (válvula -> bomba)
            # achada pela busca, pro "Localizar" mostrar o trecho todo.
            itens_recalque.append({
                u"trecho": u"Válvula sem rota — {}".format(descricao_curta_elemento(valvula)),
                u"elemento": u"Achada por busca à parte (possível anel fechado na rede — "
                             u"revise a modelagem)",
                u"eids": caminho,
            })
            continue
        # Rota completa (válvula -> ponta desconectada), não só o ponto
        # isolado — "Localizar" na dockpane seleciona/enquadra o trecho
        # inteiro no Revit (ver _itens_pontas).
        pontas_valvula = get_pontas_abertas(doc, visitados)
        origem = u"Recalque → {}".format(descricao_curta_elemento(valvula))
        if pontas_valvula:
            itens_recalque.extend(_itens_pontas(doc, origem, pontas_valvula, caminhos))
        else:
            # Nenhum conector desconectado identificado (categoria sem
            # suporte?) — mostra toda a ilha alcançada a partir da válvula,
            # já que não há um ponto de quebra específico pra apontar.
            itens_recalque.append({
                u"trecho": origem, u"elemento": u"Sem rota até a bomba",
                u"eids": list(visitados),
            })

    if not rotas:
        if itens_recalque:
            raise _Interrompido(
                u"Nenhuma válvula de hidrante foi alcançada a partir da bomba. "
                u"Corrija a tubulação nos pontos abaixo.",
                u"inconsistencia", itens_recalque)
        raise _Interrompido(
            u"Nenhuma válvula de hidrante ('Valvula para Hidrante') foi encontrada "
            u"percorrendo a rede a partir da saída da bomba. Verifique se a tubulação "
            u"de recalque está conectada até as válvulas.")

    if len(rotas) < 2:
        raise _Interrompido(
            u"Só {} válvula(s) de hidrante encontrada(s) na rede de recalque. "
            u"O dimensionamento exige pelo menos 2 hidrantes (os mais desfavoráveis "
            u"em funcionamento simultâneo).".format(len(rotas)))

    contexto = {
        u"rotas": rotas,
        u"eid_rti": get_id(rti), u"rti_auto": rti_auto, u"eid_tubo_rti": eid_rti,
        u"eid_bomba": get_id(bomba),
        u"ids_succao": list(caminho_succao),
        u"projeto_dir": projeto_dir,
        u"qs": qs_lmin, u"c_hw": c_hw,
        u"ignorados": len(itens_recalque),
    }

    if itens_recalque:
        # A decisão de prosseguir é do usuário, tomada na dockpane
        # (CONTINUAR_MAPEAMENTO).
        _pendente = contexto
        postar_mensagem(_TIPO_RESULTADO, {
            u"ok": True, u"pendente": True,
            u"grave": bool(valvulas_sem_rota),
            u"itens": itens_recalque,
        })
        return

    postar_mensagem(_TIPO_RESULTADO, _gravar(doc, contexto))


# ---------------------------------------------------------------------------
# Pontuação, parâmetros e cache
# ---------------------------------------------------------------------------

def _gravar(doc, ctx):
    """Pontua as rotas, grava parâmetros e cache. Devolve a resposta de sucesso."""
    bomba = doc.GetElement(to_element_id(ctx[u"eid_bomba"]))
    rti = doc.GetElement(to_element_id(ctx[u"eid_rti"]))
    tubo_rti = doc.GetElement(to_element_id(ctx[u"eid_tubo_rti"]))
    ids_succao = ctx[u"ids_succao"]
    rotas = ctx[u"rotas"]

    if bomba is None or rti is None or tubo_rti is None or any(
            doc.GetElement(to_element_id(eid)) is None for rota in rotas for eid in rota):
        raise _Interrompido(
            u"O modelo mudou desde que a rede foi percorrida (algum elemento não existe mais). "
            u"Mapeie os trechos de novo.")

    z_recalque_bomba = get_cota_conector(bomba, (FlowDirectionType.Out,))
    if z_recalque_bomba is None:
        detalhes = [u"Não foi possível ler a elevação de saída (recalque) da bomba:"]
        detalhes.extend(diagnostico_conectores(bomba))
        raise _Interrompido(u"\n".join(detalhes))

    candidatas = []
    for rota in rotas:
        valvula = doc.GetElement(to_element_id(rota[-1]))
        z_valvula = get_cota_conector(valvula)
        if z_valvula is None:
            detalhes = [u"Não foi possível ler a elevação da válvula (ID {}):".format(valvula.Id)]
            detalhes.extend(diagnostico_conectores(valvula))
            raise _Interrompido(u"\n".join(detalhes))

        elems = [doc.GetElement(to_element_id(eid)) for eid in rota]
        ids_no_trecho = set(rota)
        try:
            trecho_data = extrair_trecho(
                elems, get_comprimento,
                lambda e, _ids=ids_no_trecho: get_diametro_no_trecho(e, _ids),
                get_leq, get_nome)
        except ValueError as ex:
            raise _Interrompido(texto_erro(ex))
        jt = calc_j_trecho(trecho_data, ctx[u"qs"], ctx[u"c_hw"], u"Bomba > Valvula (score)")
        dz = z_valvula - z_recalque_bomba
        candidatas.append({
            u"rota": rota, u"valvula": valvula,
            u"J": jt["J"], u"dZ": dz, u"score": jt["J"] + dz,
        })

    candidatas.sort(key=lambda c: c[u"score"], reverse=True)

    # Ranking completo (não só H-01/H-02): vai para o cache 'rotas' e, de lá,
    # para o resultado do dimensionamento, para a dockpane/o site mostrarem a
    # verificação de qual hidrante é de fato o mais desfavorável.
    ranking_hidrantes = [
        {
            u"id":          u"H-{:02d}".format(i + 1),
            u"elementId":   get_id(c[u"valvula"]),
            # Rota completa (Bomba -> válvula), para o "Localizar" do ranking.
            u"rota":        list(c[u"rota"]),
            u"J":           c[u"J"],
            u"dZ":          c[u"dZ"],
            u"score":       c[u"score"],
            u"selecionado": i < 2,
        }
        for i, c in enumerate(candidatas)
    ]

    # Ponto A: último elemento em comum entre as 2 rotas mais desfavoráveis.
    rota_h1, rota_h2 = candidatas[0][u"rota"], candidatas[1][u"rota"]
    set_h2 = set(rota_h2)
    comuns = [eid for eid in rota_h1 if eid in set_h2]
    if not comuns:
        raise _Interrompido(u"Ponto A não encontrado entre as 2 rotas mais desfavoráveis.")

    ponto_a_id = comuns[-1]
    idx_a_h1 = rota_h1.index(ponto_a_id)
    idx_a_h2 = rota_h2.index(ponto_a_id)

    ids_rec_comum = rota_h1[:idx_a_h1 + 1]   # Bomba -> Ponto A (inclusive)
    ids_ramal_h1 = rota_h1[idx_a_h1 + 1:]    # Ponto A -> H-01 (inclusive a válvula)
    ids_ramal_h2 = rota_h2[idx_a_h2 + 1:]    # Ponto A -> H-02 (inclusive a válvula)

    # Parâmetros: só visual, o dimensionamento lê o cache. O reset vem aqui
    # (e não no começo) para que um mapeamento cancelado ou barrado por
    # inconsistência não apague o anterior.
    todos = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    with Transaction(doc, u"FireUtils - Mapear Trechos") as t:
        t.Start()
        try:
            for elem in todos:
                for nome_p in (P_TRECHO, P_IDENTIFICADOR, P_ID_HIDRANTE):
                    p = elem.LookupParameter(nome_p)
                    if p and not p.IsReadOnly and p.AsString():
                        p.Set(u"")

            # RTI e bomba marcados na própria família, para o dimensionamento
            # achar o elemento sem percorrer a rede. Se a RTI não foi achada
            # pelo conector (tubo clicado), quem leva a tag "RTI" é o tubo.
            _set_param(rti if ctx[u"rti_auto"] else tubo_rti, P_IDENTIFICADOR, u"RTI")
            _set_param(bomba, P_IDENTIFICADOR, u"Bomba")

            for i, c in enumerate(candidatas):
                _set_param(c[u"valvula"], P_ID_HIDRANTE, u"H-{:02d}".format(i + 1))

            for eid in ids_succao:
                _set_param(doc.GetElement(to_element_id(eid)), P_TRECHO, u"RTI - Bomba")

            for eid in ids_rec_comum:
                elem = doc.GetElement(to_element_id(eid))
                _set_param(elem, P_TRECHO, u"Bomba - Ponto A")
                if eid == ponto_a_id:
                    _set_param(elem, P_IDENTIFICADOR, u"Ponto A")

            for eid in ids_ramal_h1:
                _set_param(doc.GetElement(to_element_id(eid)), P_TRECHO, u"Ponto A - Hid 01")
            for eid in ids_ramal_h2:
                _set_param(doc.GetElement(to_element_id(eid)), P_TRECHO, u"Ponto A - Hid 02")

            t.Commit()
        except Exception as ex:
            t.RollBack()
            raise _Interrompido(
                u"Erro ao gravar os parâmetros no modelo: {}".format(texto_erro(ex)), u"servidor")

    # Perda de carga da sucção, pelo mesmo método do score: só para a
    # conferência visual (o cálculo final da sucção é do motor na nuvem).
    elems_succao = [doc.GetElement(to_element_id(eid)) for eid in ids_succao]
    ids_succao_set = set(ids_succao)
    try:
        trecho_succao = extrair_trecho(
            elems_succao, get_comprimento,
            lambda e, _ids=ids_succao_set: get_diametro_no_trecho(e, _ids),
            get_leq, get_nome)
    except ValueError as ex:
        raise _Interrompido(texto_erro(ex))
    j_succao = calc_j_trecho(trecho_succao, ctx[u"qs"], ctx[u"c_hw"], u"RTI > Bomba (score)")

    # Trechos para a dockpane, com os ElementId de cada um (botão "Localizar"):
    # a sucção e a rota completa de todos os hidrantes, do mais ao menos
    # desfavorável (a mesma ordem que numera "ID Hidrante").
    trechos = [{u"nome": u"Sucção (RTI → Bomba)", u"eids": list(ids_succao), u"perda": j_succao[u"J"]}]
    n = len(candidatas)
    for i, c in enumerate(candidatas):
        if i == n - 1 and n > 1:
            nome = u"Hidrante mais favorável (H-{:02d})".format(i + 1)
        else:
            nome = u"{}º hidrante mais desfavorável (H-{:02d})".format(i + 1, i + 1)
        trechos.append({u"nome": nome, u"eids": list(c[u"rota"]), u"perda": c[u"J"]})

    # Cache 'rotas': lido pelo dimensionamento por ElementId, sem depender dos
    # parâmetros. `resumo` é só para a dockpane reexibir o mapeamento depois.
    salvar_cache({
        u"t1":         list(ids_succao),
        u"t2":         list(ids_rec_comum),
        u"t3":         list(ids_ramal_h1),
        u"t4":         list(ids_ramal_h2),
        u"ponto_a_id": ponto_a_id,
        u"ranking":    ranking_hidrantes,
        u"resumo":     trechos,
    }, ctx[u"projeto_dir"], chave=u"rotas")

    return {u"ok": True, u"trechos": trechos, u"ignorados": ctx[u"ignorados"]}
