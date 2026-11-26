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
from hidrantes.calc import (
    extrair_trecho, calc_j_trecho, salvar_cache, carregar_cache, combinacoes_pipe_type,
)
from hidrantes.rede import (
    get_id, to_element_id, get_primeiro_tubo, bfs_ate,
    percorre_rotas_hidrantes, get_pontas_abertas, descricao_curta_elemento,
    todas_valvulas_hidrante, get_cota_conector, diagnostico_conectores,
    get_comprimento, get_diametro_no_trecho, get_leq, get_nome,
    get_pipe_type_no_trecho, eh_acessorio_tubulacao, ID_HIDRANTE_PENDENTE,
    tem_id_hidrante,
)
from family_error_utils import texto_erro

P_TRECHO        = u"FireUtils - Trecho"
P_IDENTIFICADOR = u"FireUtils - Identificador"
P_ID_HIDRANTE   = u"FireUtils - ID Hidrante"

_CHAVE_FAMILIAS = u"familias_valvula"
_CHAVE_REFERENCIAS = u"referencias"
_TIPO_REFERENCIAS = u"HIDRANTES_REFERENCIAS"

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


class _FiltroEquipamentoOuTubo(ISelectionFilter):
    """Primeira seleção da RTI: o reservatório ou o tubo de saída dele."""
    def AllowElement(self, e):
        return isinstance(e, (FamilyInstance, Pipe))

    def AllowReference(self, r, p):
        return False


class _FiltroEquipamento(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, FamilyInstance)

    def AllowReference(self, r, p):
        return False


class _FiltroAcessorio(ISelectionFilter):
    """Só Acessórios de tubulação (categoria onde mora 'ID Hidrante')."""
    def AllowElement(self, e):
        return isinstance(e, FamilyInstance) and eh_acessorio_tubulacao(e)

    def AllowReference(self, r, p):
        return False


def _nome_familia(elem):
    try:
        return elem.Symbol.Family.Name
    except Exception:
        return None


def _familias_salvas(projeto_dir):
    """Nomes das famílias que o usuário já indicou como válvula de hidrante
    neste projeto (cache firedata.json, chave 'familias_valvula')."""
    dados, _erro = carregar_cache(projeto_dir, chave=_CHAVE_FAMILIAS)
    return list((dados or {}).get(u"nomes") or [])


def _marcar_instancias_das_familias(doc, nomes):
    """Grava o ID Hidrante provisório (H-?) em TODAS as instâncias, Acessórios
    de tubulação, das famílias `nomes` que ainda não têm o parâmetro
    preenchido — inclusive válvulas inseridas depois da escolha. O parâmetro
    é de instância (não existe 'gravar na família'), por isso marca-se cada
    instância. Devolve a lista das que não aceitaram o parâmetro."""
    nomes = set(nomes)
    if not nomes:
        return []
    alvos = [
        e for e in FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements()
        if eh_acessorio_tubulacao(e) and _nome_familia(e) in nomes
        and not tem_id_hidrante(e)
    ]
    if not alvos:
        return []
    sem_param = []
    with Transaction(doc, u"FireUtils - Marcar Válvulas de Hidrante") as t:
        t.Start()
        try:
            for v in alvos:
                if not _set_param(v, P_ID_HIDRANTE, ID_HIDRANTE_PENDENTE):
                    sem_param.append(v)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            raise _Interrompido(
                u"Erro ao marcar as válvulas: {}".format(texto_erro(ex)), u"servidor")
    return sem_param


def _escolher_familias_valvula(uidoc, postar_mensagem, projeto_dir):
    """O projeto não tem nenhuma válvula identificada: pede para o usuário
    clicar em UMA válvula de cada família de hidrante presente (normalmente
    uma só; várias se o projeto tem famílias distintas). A partir das
    selecionadas, marca todas as instâncias de cada família e guarda os
    nomes das famílias para os próximos mapeamentos. Esc cancela."""
    doc = uidoc.Document
    _progresso(
        postar_mensagem,
        u"Nenhuma válvula de hidrante foi identificada no projeto. No Revit, clique em UMA "
        u"válvula de cada família de hidrante (normalmente é uma só) e depois em Concluir.",
        u"Identifique as válvulas de hidrante", u"selecao",
        u"Só Acessórios de tubulação podem ser selecionados. Se houver famílias de válvula "
        u"diferentes, clique em uma de cada. Ao terminar, clique em Concluir na barra do Revit.")
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, _FiltroAcessorio(),
            u"Selecione uma válvula de cada família de hidrante e clique em Concluir")
    except OperationCanceledException:
        raise _Interrompido(u"Mapeamento cancelado.", u"cancelado")

    _progresso(postar_mensagem, u"Válvulas selecionadas. Marcando as famílias no projeto…",
               u"Identificando as válvulas", u"processando")
    nomes = sorted(set(
        n for n in (_nome_familia(doc.GetElement(r.ElementId)) for r in refs) if n))
    if not nomes:
        raise _Interrompido(u"Nenhuma válvula foi selecionada.")

    sem_param = _marcar_instancias_das_familias(doc, nomes)
    salvar_cache({u"nomes": sorted(set(_familias_salvas(projeto_dir)) | set(nomes))},
                 projeto_dir, chave=_CHAVE_FAMILIAS)
    if sem_param:
        raise _Interrompido(
            u"Não foi possível gravar '{}' em {} válvula(s) (ex.: ID {}). "
            u"Verifique se o parâmetro está vinculado a Acessórios de tubulação "
            u"e não é somente leitura.".format(
                P_ID_HIDRANTE, len(sem_param), sem_param[0].Id))


def _progresso(postar_mensagem, instrucao, titulo=None, acao=u"processando", dica=None):
    """Passo do mapeamento para o popup da dockpane. `acao`: "clique" (o
    usuário deve clicar UM elemento no Revit), "selecao" (vários elementos,
    depois Concluir) ou "processando" (o plugin está trabalhando)."""
    postar_mensagem(_TIPO_PROGRESSO, {
        u"instrucao": instrucao, u"titulo": titulo or u"", u"acao": acao,
        u"dica": dica or u""})


def _selecionar(uidoc, postar_mensagem, instrucao, prompt, filtro, titulo=None, dica=None):
    """
    Pede um elemento no modelo. A instrução vai para a dockpane (o usuário
    está olhando para ela) e o prompt para a barra de status do Revit. Esc
    cancela o mapeamento inteiro.
    """
    _progresso(postar_mensagem, instrucao, titulo, u"clique", dica)
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, filtro, prompt)
    except OperationCanceledException:
        raise _Interrompido(u"Mapeamento cancelado.", u"cancelado")
    # Fecha o popup da dockpane até o próximo passo chegar.
    _progresso(postar_mensagem, u"Elemento selecionado. Continuando…", titulo, u"processando")
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
# Referências salvas (RTI e bomba)
# ---------------------------------------------------------------------------

def _ler_referencias(projeto_dir):
    dados, _erro = carregar_cache(projeto_dir, chave=_CHAVE_REFERENCIAS)
    return dict(dados or {})


def _gravar_referencias(projeto_dir, refs):
    payload = dict((k, v) for k, v in refs.items()
                   if k in (u"rti", u"bomba") and v)
    salvar_cache(payload, projeto_dir, chave=_CHAVE_REFERENCIAS)


def _elem(doc, eid):
    if eid is None:
        return None
    try:
        return doc.GetElement(to_element_id(eid))
    except Exception:
        return None


def _montar_rti(uidoc, postar_mensagem, ref):
    """RTI e tubo de saída. `ref` é a referência salva (ou None para pedir
    ao usuário). A primeira seleção aceita o reservatório OU o tubo dele;
    se o reservatório não estiver conectado a nenhum tubo, pede o tubo.
    Devolve (rti, tubo_rti, intermediarios, rti_auto, ref_para_salvar);
    quando o usuário clica direto no tubo, `rti` é o próprio tubo."""
    doc = uidoc.Document
    ref = ref or {}
    rti = _elem(doc, ref.get(u"eid"))
    if rti is None:
        if ref:
            _progresso(postar_mensagem,
                       u"A RTI salva não existe mais no modelo. Selecione de novo.",
                       u"Reservatório (RTI)")
        ref = {}
        rti = _selecionar(
            uidoc, postar_mensagem,
            u"No Revit, clique no reservatório (RTI) ou no tubo de saída dele.",
            u"Selecione a RTI ou o tubo de saída da RTI", _FiltroEquipamentoOuTubo(),
            u"Selecione o reservatório (RTI)",
            u"Pode clicar direto no tubo que sai do reservatório. Se o reservatório não estiver "
            u"conectado a nenhum tubo, o próximo passo pede o tubo.")

    if isinstance(rti, Pipe):
        return rti, rti, [], False, {
            u"eid": get_id(rti), u"eid_tubo": None,
            u"descricao": descricao_curta_elemento(rti)}

    tubo, interm = get_primeiro_tubo(rti, (FlowDirectionType.Out,))
    rti_auto = tubo is not None
    eid_tubo = None
    if tubo is None:
        interm = []
        tubo = _elem(doc, ref.get(u"eid_tubo"))
        if not isinstance(tubo, Pipe):
            tubo = _selecionar(
                uidoc, postar_mensagem,
                u"A RTI não está conectada a nenhum tubo. No Revit, clique no tubo de saída da RTI.",
                u"Tubo de saída da RTI", _FiltroTubo(),
                u"Selecione o tubo de saída da RTI")
        eid_tubo = get_id(tubo)
    return rti, tubo, interm, rti_auto, {
        u"eid": get_id(rti), u"eid_tubo": eid_tubo,
        u"descricao": descricao_curta_elemento(rti)}


def _montar_bomba(uidoc, postar_mensagem, ref):
    """Bomba e tubos de sucção/recalque. Mesma ideia de _montar_rti: usa a
    referência salva, ou pede ao usuário. Devolve (bomba, tubo_succao,
    interm_succao, tubo_recalque, interm_recalque, ref_para_salvar)."""
    doc = uidoc.Document
    ref = ref or {}
    bomba = _elem(doc, ref.get(u"eid"))
    if bomba is None:
        if ref:
            _progresso(postar_mensagem,
                       u"A bomba salva não existe mais no modelo. Selecione de novo.",
                       u"Bomba de incêndio")
        ref = {}
        bomba = _selecionar(
            uidoc, postar_mensagem,
            u"No Revit, clique na bomba de incêndio.",
            u"Selecione a bomba de incêndio", _FiltroEquipamento(),
            u"Selecione a bomba de incêndio")

    tubo_s, interm_s = get_primeiro_tubo(bomba, (FlowDirectionType.In,))
    eid_s = None
    if tubo_s is None:
        interm_s = []
        tubo_s = _elem(doc, ref.get(u"eid_tubo_succao"))
        if not isinstance(tubo_s, Pipe):
            tubo_s = _selecionar(
                uidoc, postar_mensagem,
                u"Não deu para identificar o tubo de entrada (sucção) da bomba. "
                u"No Revit, clique no tubo que conecta na entrada da bomba.",
                u"Tubo de sucção da bomba", _FiltroTubo(),
                u"Selecione o tubo de sucção da bomba")
        eid_s = get_id(tubo_s)

    tubo_r, interm_r = get_primeiro_tubo(bomba, (FlowDirectionType.Out,))
    eid_r = None
    if tubo_r is None:
        interm_r = []
        tubo_r = _elem(doc, ref.get(u"eid_tubo_recalque"))
        if not isinstance(tubo_r, Pipe):
            tubo_r = _selecionar(
                uidoc, postar_mensagem,
                u"Não deu para identificar o tubo de saída (recalque) da bomba. "
                u"No Revit, clique no tubo que conecta na saída da bomba.",
                u"Tubo de recalque da bomba", _FiltroTubo(),
                u"Selecione o tubo de recalque da bomba")
        eid_r = get_id(tubo_r)

    return bomba, tubo_s, interm_s, tubo_r, interm_r, {
        u"eid": get_id(bomba), u"eid_tubo_succao": eid_s,
        u"eid_tubo_recalque": eid_r,
        u"descricao": descricao_curta_elemento(bomba)}


def _payload_referencias(doc, projeto_dir):
    """O que a dockpane mostra: RTI, bomba e famílias de válvula salvas."""
    refs = _ler_referencias(projeto_dir)

    def item(ref):
        if not ref:
            return None
        elem = _elem(doc, ref.get(u"eid"))
        ids = [ref.get(u"eid")] + [
            ref.get(k) for k in (u"eid_tubo", u"eid_tubo_succao", u"eid_tubo_recalque")]
        return {
            u"existe": elem is not None,
            u"descricao": (descricao_curta_elemento(elem) if elem is not None
                           else ref.get(u"descricao") or u""),
            u"eids": [i for i in ids if i is not None and _elem(doc, i) is not None],
        }

    return {
        u"ok": True,
        u"rti": item(refs.get(u"rti")),
        u"bomba": item(refs.get(u"bomba")),
        u"familiasValvula": _familias_salvas(projeto_dir),
    }


def _doc_e_pasta(uiapp):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        raise _Interrompido(u"Salve o projeto Revit (.rvt) antes de mapear os trechos.")
    return uidoc, os.path.dirname(uidoc.Document.PathName)


def tratar_get_referencias(uiapp, payload, fila_acoes, postar_mensagem):
    try:
        uidoc, projeto_dir = _doc_e_pasta(uiapp)
        postar_mensagem(_TIPO_REFERENCIAS, _payload_referencias(uidoc.Document, projeto_dir))
    except _Interrompido:
        # Projeto ainda não salvo: nada salvo para mostrar.
        postar_mensagem(_TIPO_REFERENCIAS, {
            u"ok": True, u"rti": None, u"bomba": None, u"familiasValvula": []})
    except Exception as ex:
        postar_mensagem(_TIPO_REFERENCIAS, {
            u"ok": False, u"categoria": u"servidor",
            u"erro": u"Não foi possível ler as referências: {}".format(texto_erro(ex))})


def tratar_atualizar_referencia(uiapp, payload, fila_acoes, postar_mensagem):
    """Troca só a RTI ou só a bomba (payload {qual: 'rti'|'bomba'}) pedindo
    a nova seleção no Revit; a outra referência é mantida."""
    try:
        if not licenca.tem_acesso(u"hidrantes"):
            raise _Interrompido(
                u"Esta conta não tem o módulo Hidrantes liberado neste computador.", u"licenca")
        qual = (payload or {}).get(u"qual")
        if qual not in (u"rti", u"bomba"):
            raise _Interrompido(u"Referência desconhecida: {}".format(qual))
        uidoc, projeto_dir = _doc_e_pasta(uiapp)
        refs = _ler_referencias(projeto_dir)
        if qual == u"rti":
            refs[u"rti"] = _montar_rti(uidoc, postar_mensagem, None)[4]
        else:
            refs[u"bomba"] = _montar_bomba(uidoc, postar_mensagem, None)[5]
        _gravar_referencias(projeto_dir, refs)
        resposta = _payload_referencias(uidoc.Document, projeto_dir)
        resposta[u"atualizado"] = qual
        postar_mensagem(_TIPO_REFERENCIAS, resposta)
    except _Interrompido as ex:
        postar_mensagem(_TIPO_REFERENCIAS, ex.resposta)
    except Exception as ex:
        postar_mensagem(_TIPO_REFERENCIAS, {
            u"ok": False, u"categoria": u"servidor",
            u"erro": u"Falha ao atualizar a referência: {}".format(texto_erro(ex))})


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
    # Pontos de referência que quase nunca mudam entre um mapeamento e outro
    # (o que muda é a quantidade de hidrantes): ficam salvos no projeto e são
    # reaproveitados. A dockpane mostra o que está salvo e permite trocar só
    # a RTI ou só a bomba (ATUALIZAR_REFERENCIA_HIDRANTE).
    refs = _ler_referencias(projeto_dir)
    if refs.get(u"rti") and refs.get(u"bomba"):
        _progresso(postar_mensagem, u"Usando a RTI e a bomba salvas no projeto.",
                   u"Preparando o mapeamento")

    rti, tubo_rti, interm_rti, rti_auto, ref_rti = _montar_rti(
        uidoc, postar_mensagem, refs.get(u"rti"))
    bomba, tubo_bomba, interm_succao_bomba, tubo_rec, interm_recalque_bomba, ref_bomba = \
        _montar_bomba(uidoc, postar_mensagem, refs.get(u"bomba"))
    _gravar_referencias(projeto_dir, {u"rti": ref_rti, u"bomba": ref_bomba})

    # Válvulas de hidrante: identificadas por 'ID Hidrante' (Acessórios de
    # tubulação), não mais só pela família. Sem nenhuma, o usuário clica.
    # Famílias já escolhidas antes: marca as instâncias novas (inseridas
    # depois) antes de procurar.
    sem_param = _marcar_instancias_das_familias(doc, _familias_salvas(projeto_dir))
    if sem_param:
        raise _Interrompido(
            u"Não foi possível gravar '{}' em {} válvula(s) (ex.: ID {}).".format(
                P_ID_HIDRANTE, len(sem_param), sem_param[0].Id))
    if not todas_valvulas_hidrante(doc):
        _escolher_familias_valvula(uidoc, postar_mensagem, projeto_dir)

    _progresso(postar_mensagem,
               u"Percorrendo a tubulação da bomba até cada válvula de hidrante, "
               u"calculando as perdas de carga e numerando os hidrantes. Aguarde.",
               u"Mapeando a rede")

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
            u"Nenhuma válvula de hidrante (Acessório com 'FireUtils - ID Hidrante') foi encontrada "
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
                        # 'ID Hidrante' de um Acessório é o que o identifica
                        # como válvula: nunca zera, só volta a "pendente"
                        # (o ranking abaixo renumera as alcançadas).
                        if nome_p == P_ID_HIDRANTE and eh_acessorio_tubulacao(elem):
                            p.Set(ID_HIDRANTE_PENDENTE)
                        else:
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

    # Combinações (tipo de tubo, diâmetros) por etapa — pra dockpane desenhar
    # o seletor de material (ver material_conexao.py).
    # Mesmos 4 conjuntos de elementos que "Dimensionar" vai usar depois
    # (payload_rotas.t1-t4 na próxima chamada são exatamente estes ids).
    def _combinacoes(ids):
        elems = [doc.GetElement(to_element_id(eid)) for eid in ids]
        ids_set = set(ids)
        return combinacoes_pipe_type(
            elems,
            lambda e, _ids=ids_set: get_diametro_no_trecho(e, _ids),
            lambda e, _ids=ids_set: get_pipe_type_no_trecho(e, _ids),
            get_id,
        )

    pipe_types_por_etapa = {
        u"t1": _combinacoes(ids_succao),
        u"t2": _combinacoes(ids_rec_comum),
        u"t3": _combinacoes(ids_ramal_h1),
        u"t4": _combinacoes(ids_ramal_h2),
    }

    # Cache 'rotas': lido pelo dimensionamento por ElementId, sem depender dos
    # parâmetros. `resumo`/`pipe_types_por_etapa` são só para a dockpane
    # reexibir o mapeamento (e o seletor de material/conexão) depois de
    # reabrir, sem precisar mapear de novo.
    salvar_cache({
        u"t1":                  list(ids_succao),
        u"t2":                  list(ids_rec_comum),
        u"t3":                  list(ids_ramal_h1),
        u"t4":                  list(ids_ramal_h2),
        u"ponto_a_id":          ponto_a_id,
        u"ranking":             ranking_hidrantes,
        u"resumo":              trechos,
        u"pipe_types_por_etapa": pipe_types_por_etapa,
    }, ctx[u"projeto_dir"], chave=u"rotas")

    return {
        u"ok": True, u"trechos": trechos, u"ignorados": ctx[u"ignorados"],
        u"pipe_types_por_etapa": pipe_types_por_etapa,
    }
