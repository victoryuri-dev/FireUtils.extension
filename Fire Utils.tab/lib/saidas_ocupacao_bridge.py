# -*- coding: utf-8 -*-
"""
saidas_ocupacao_bridge.py — Fire Utils · lib/
As ferramentas de ocupação e população (ex-painel "Saídas" da faixa do Revit),
agora disparadas pela página "Saídas de Emergência" da dockpane. Todas trocam
dados com o site, então só fazem sentido com internet — por isso saíram da
faixa, que ficou só com a modelagem que funciona offline.

Mensagens (contrato em webapp/src/lib/bridge.js):
  GET_SAIDAS_OPCOES        -> SAIDAS_OPCOES
      As ocupações da norma do estado (agrupadas por uso, com taxa e notas) e
      os níveis do modelo: o que os antigos formulários WPF mostravam, para a
      página montar os seletores.
  IDENTIFICAR_AMBIENTES    -> SAIDAS_AMBIENTES_PROGRESSO*, SAIDAS_AMBIENTES_RESULTADO
      {modo: "selecao" | "niveis" | "todos", ocupacao, niveis?}. Grava a
      ocupação nos ambientes escolhidos e sincroniza com o site.
        selecao  ambientes clicados no Revit (os 3 modos eram 3 botões:
                 Identificar por Ambiente / por Nível / Todos sem Ocupação)
        niveis   todos os ambientes dos níveis informados (nomes)
        todos    todos os ambientes que ainda não têm "Grupo"
  SINCRONIZAR_AMBIENTES    -> SAIDAS_AMBIENTES_RESULTADO
      Revit -> site (nome/grupo/área) e site -> Revit (população e taxa).

Rodam na thread de API (chamados via fila_acoes). A parte de rede do envio ao
site vai para uma thread de fundo; a resposta volta pela thread de API, a única
onde postar_mensagem é seguro. Os módulos `saidas.*` são importados só aqui
dentro, na hora: importá-los no topo faria a bridge inteira depender de haver
um documento aberto quando o Revit sobe.
"""

import os
import sys
import threading

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, FilteredElementCollector, Level,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType

import licenca
from projeto import carregar_dados_projeto
from family_error_utils import texto_erro

_TIPO_OPCOES = u"SAIDAS_OPCOES"
_TIPO_PROGRESSO = u"SAIDAS_AMBIENTES_PROGRESSO"
_TIPO_RESULTADO = u"SAIDAS_AMBIENTES_RESULTADO"

_MODOS = (u"selecao", u"niveis", u"todos")


class _Falha(Exception):
    """Falha com texto pronto para o usuário."""


def _capturando_saida(funcao, *args, **kwargs):
    """Roda `funcao` guardando o que ela imprime. set_occupancy avisa com
    print os ambientes sem taxa por área; numa ação da dockpane isso abriria a
    janela de saída do pyRevit, então o texto vai para a resposta."""
    try:
        from StringIO import StringIO
    except ImportError:  # pragma: no cover
        from io import StringIO
    anterior = sys.stdout
    buffer = StringIO()
    sys.stdout = buffer
    try:
        resultado = funcao(*args, **kwargs)
    finally:
        sys.stdout = anterior
    return resultado, buffer.getvalue()


def _contexto(uiapp):
    """(doc, projeto_dir, estado) do documento ativo, ou _Falha."""
    if not licenca.tem_acesso(u"saidas"):
        raise _Falha(u"Esta conta não tem o módulo Saídas liberado neste computador. "
                     u"Abra o painel com internet para atualizar a licença.")
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        raise _Falha(u"Salve o projeto Revit (.rvt) antes de usar as ferramentas de ocupação.")
    doc = uidoc.Document
    projeto_dir = os.path.dirname(doc.PathName)

    from normas import get_estado
    sigla = (carregar_dados_projeto(projeto_dir) or {}).get(u"uf") or u"MA"
    estado = get_estado(sigla, projeto_dir)
    if not estado or not estado.get(u"tabela"):
        raise _Falha(u"Não há norma de saídas de emergência cadastrada para o estado "
                     u"'{}'.".format(sigla))
    return doc, projeto_dir, estado


def _responder(fila_acoes, postar_mensagem, tipo, mensagem):
    fila_acoes.enfileirar(lambda _uiapp: postar_mensagem(tipo, mensagem))


# ---------------------------------------------------------------------------
# Opções (ocupações da norma + níveis do modelo)
# ---------------------------------------------------------------------------

def _notas(estado, codigo):
    notas = estado.get(u"notas", {})
    chaves = estado.get(u"tabela", {}).get(codigo, {}).get(u"notas", [])
    return [notas[c] for c in chaves if c in notas]


def _grupos_de_ocupacao(estado):
    """Ocupações agrupadas por uso, como o antigo formulário WPF."""
    tabela = estado.get(u"tabela", {})
    ocups = estado.get(u"ocupacoes", {})
    grupos = {}
    for codigo in sorted(tabela.keys()):
        entrada = tabela[codigo]
        ocup = ocups.get(codigo, {})
        uso = ocup.get(u"uso", u"Outros")
        grupos.setdefault(uso, []).append({
            u"codigo": codigo,
            u"descricao": ocup.get(u"descricao", u""),
            u"taxa": entrada.get(u"obs", u"—"),
            u"ad": u"{}".format(entrada.get(u"AD") or u"—"),
            u"er": u"{}".format(entrada.get(u"ER") or u"—"),
            u"pt": u"{}".format(entrada.get(u"PT") or u"—"),
            u"notas": _notas(estado, codigo),
        })
    return [{u"uso": uso, u"itens": grupos[uso]} for uso in sorted(grupos.keys())]


def tratar_get_saidas_opcoes(uiapp, postar_mensagem):
    try:
        doc, _projeto_dir, estado = _contexto(uiapp)
        niveis = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                        key=lambda n: n.Elevation)
        postar_mensagem(_TIPO_OPCOES, {
            u"ok": True,
            u"estadoNome": estado.get(u"nome", u""),
            u"grupos": _grupos_de_ocupacao(estado),
            u"niveis": [n.Name for n in niveis],
        })
    except _Falha as ex:
        postar_mensagem(_TIPO_OPCOES, {u"ok": False, u"erro": u"{}".format(ex)})
    except Exception as ex:
        postar_mensagem(_TIPO_OPCOES, {
            u"ok": False, u"erro": u"Falha ao ler as ocupações: {}".format(texto_erro(ex))})


# ---------------------------------------------------------------------------
# Escolha dos ambientes
# ---------------------------------------------------------------------------

def _ambientes_com_area(doc):
    colecao = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).ToElements()
    resultado = []
    for room in colecao:
        p_area = room.get_Parameter(BuiltInParameter.ROOM_AREA)
        if p_area is not None and p_area.AsDouble() > 0:
            resultado.append(room)
    return resultado


def _ambientes_do_modo(uidoc, modo, niveis, postar_mensagem):
    doc = uidoc.Document
    if modo == u"selecao":
        from saidas.rooms import FiltroAmbiente
        postar_mensagem(_TIPO_PROGRESSO, {
            u"instrucao": u"Selecione os ambientes no Revit e clique em Concluir (Esc cancela)."})
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, FiltroAmbiente(),
                u"Selecione os ambientes e clique em Concluir")
        except OperationCanceledException:
            raise _Falha(u"Seleção cancelada.")
        return [doc.GetElement(r.ElementId) for r in refs]

    if modo == u"niveis":
        escolhidos = set(niveis or [])
        if not escolhidos:
            raise _Falha(u"Escolha pelo menos um nível.")
        return [r for r in _ambientes_com_area(doc) if r.Level is not None and r.Level.Name in escolhidos]

    # todos: os que ainda não têm "Grupo".
    resultado = []
    for room in _ambientes_com_area(doc):
        p = room.LookupParameter(u"Grupo")
        if p is not None and not p.AsString():
            resultado.append(room)
    return resultado


# ---------------------------------------------------------------------------
# Identificar ambientes
# ---------------------------------------------------------------------------

def tratar_identificar_ambientes(uiapp, payload, fila_acoes, postar_mensagem):
    try:
        resposta = _identificar(uiapp, payload or {}, fila_acoes, postar_mensagem)
    except _Falha as ex:
        resposta = {u"ok": False, u"acao": u"identificar", u"erro": u"{}".format(ex)}
    except Exception as ex:
        resposta = {u"ok": False, u"acao": u"identificar",
                    u"erro": u"Falha inesperada ao identificar os ambientes: {}".format(texto_erro(ex))}
    if resposta is not None:
        postar_mensagem(_TIPO_RESULTADO, resposta)


def _identificar(uiapp, payload, fila_acoes, postar_mensagem):
    from saidas.populacao import garantir_parametros, set_occupancy
    from saidas.rooms import get_rooms_classificados

    modo = payload.get(u"modo")
    codigo = payload.get(u"ocupacao")
    if modo not in _MODOS:
        raise _Falha(u"Modo de identificação inválido.")

    doc, projeto_dir, estado = _contexto(uiapp)
    if codigo not in estado[u"tabela"]:
        raise _Falha(u"A ocupação '{}' não existe na norma deste estado.".format(codigo))

    if not garantir_parametros(doc):
        raise _Falha(u"Não foi possível criar os parâmetros de população no projeto.")

    rooms = _ambientes_do_modo(uiapp.ActiveUIDocument, modo, payload.get(u"niveis"), postar_mensagem)
    if not rooms:
        return {u"ok": True, u"acao": u"identificar", u"ambientes": 0,
                u"resumo": u"Nenhum ambiente encontrado para identificar."}

    ok, saida = _capturando_saida(set_occupancy, rooms, codigo, estado, doc)
    if not ok:
        raise _Falha(u"Não foi possível gravar a ocupação nos ambientes.")
    manuais = [linha.strip() for linha in saida.splitlines() if u"[POP MANUAL]" in linha]

    _enviar_em_background(
        get_rooms_classificados(doc), estado, projeto_dir, fila_acoes, postar_mensagem,
        base={u"ok": True, u"acao": u"identificar", u"ambientes": len(rooms),
              u"populacaoManual": manuais})
    return None


# ---------------------------------------------------------------------------
# Sincronizar (Revit <-> site)
# ---------------------------------------------------------------------------

def tratar_sincronizar_ambientes(uiapp, fila_acoes, postar_mensagem):
    try:
        _sincronizar(uiapp, fila_acoes, postar_mensagem)
    except _Falha as ex:
        postar_mensagem(_TIPO_RESULTADO, {u"ok": False, u"acao": u"sincronizar", u"erro": u"{}".format(ex)})
    except Exception as ex:
        postar_mensagem(_TIPO_RESULTADO, {
            u"ok": False, u"acao": u"sincronizar",
            u"erro": u"Falha inesperada ao sincronizar: {}".format(texto_erro(ex))})


def _sincronizar(uiapp, fila_acoes, postar_mensagem):
    from saidas.populacao import garantir_parametros, puxar_populacao_do_site
    from saidas.rooms import get_rooms_classificados

    doc, projeto_dir, estado = _contexto(uiapp)
    if not garantir_parametros(doc):
        raise _Falha(u"Não foi possível verificar os parâmetros de população no projeto.")

    dados = get_rooms_classificados(doc)

    def depois_do_envio(resultado_envio, base):
        # 2) Site -> Revit: grava na thread de API (escreve nos ambientes).
        def puxar(_uiapp):
            try:
                atualizados, nao_encontrados, erro_pop = puxar_populacao_do_site(doc, projeto_dir)
                resposta = dict(base)
                resposta[u"populacao"] = {
                    u"atualizados": atualizados, u"naoEncontrados": nao_encontrados, u"erro": erro_pop}
            except Exception as ex:
                resposta = dict(base)
                resposta[u"populacao"] = {
                    u"atualizados": 0, u"naoEncontrados": 0, u"erro": texto_erro(ex)}
            postar_mensagem(_TIPO_RESULTADO, resposta)
        fila_acoes.enfileirar(puxar)

    _enviar_em_background(dados, estado, projeto_dir, fila_acoes, postar_mensagem,
                          base={u"ok": True, u"acao": u"sincronizar", u"ambientes": len(dados)},
                          depois=depois_do_envio)


# ---------------------------------------------------------------------------
# Envio ao site
# ---------------------------------------------------------------------------

def _enviar_em_background(dados, estado, projeto_dir, fila_acoes, postar_mensagem, base, depois=None):
    """Revit -> site numa thread de fundo (rede). `dados` são dicts já lidos
    do modelo — nada aqui toca a API do Revit. Se `depois` existe, ele cuida
    da resposta; senão a resposta sai daqui."""
    def trabalho():
        from saidas.calc import sincronizar_ambientes, resumo_texto
        try:
            resultado = sincronizar_ambientes(dados, estado, projeto_dir)
            resposta = dict(base)
            resposta[u"resumo"] = resumo_texto(resultado)
            resposta[u"erroEnvio"] = resultado.get(u"erro")
        except Exception as ex:
            resposta = dict(base)
            resposta[u"resumo"] = u"Falha ao enviar ao site: {}".format(texto_erro(ex))
            resposta[u"erroEnvio"] = texto_erro(ex)
        if depois is not None:
            depois(None, resposta)
        else:
            _responder(fila_acoes, postar_mensagem, _TIPO_RESULTADO, resposta)

    threading.Thread(target=trabalho).start()
