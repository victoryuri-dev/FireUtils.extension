# -*- coding: utf-8 -*-
"""
family_webview_bridge.py — Fire Utils · lib/
Processa as mensagens que chegam do frontend React (webapp/) via WebView2
CoreWebView2.WebMessageReceived, e as respostas que vão de volta via
CoreWebView2.PostWebMessageAsJson. Contrato de mensagens documentado em
webapp/README.md.

Fluxo de uma mensagem LOAD_FAMILIES:
  1. Download de cada .rfa pra um arquivo temporário (family_cache.py, sem
     cache persistente — ver docstring de lá pro porquê) — roda numa
     thread separada da UI, porque WebMessageReceived dispara na mesma UI
     thread do Revit/WPF, e um .rfa grande (dezenas de MB) levaria vários
     segundos via rede, travando a interface inteira nesse meio tempo.
  2. Só depois que os arquivos já estão em disco, a ação de
     Document.LoadFamily é enfileirada via ExternalEvent
     (family_loader_events.py), porque tocar a API do Revit exige contexto
     de API válido, que só o ExternalEvent garante. ExternalEvent.Raise()
     é seguro de chamar de qualquer thread, então a thread de download pode
     enfileirar direto. Não há posicionamento automático (PromptForFamily-
     InstancePlacement) — só carrega a família no documento; posicionar é
     manual, fora deste app.
  3. Os arquivos temporários são apagados logo depois do LoadFamily rodar
     (a família já está embutida no .rvt a partir daí).
  4. Em seguida, manda de volta um LOAD_RESULT (o que carregou, o que já
     existia e o que falhou) — o frontend usa isso pras notificações e pra
     tirar da seleção as famílias já resolvidas.
"""

import json
import threading

from family_loader import FamilyEntry, carregar_familias
from family_cache import baixar_temporario, remover_temporario
from family_error_utils import texto_erro


def _montar_entrada(item_familia, caminho_local):
    return FamilyEntry(
        name=item_familia[u"name"],
        category=item_familia.get(u"categoryId") or u"Geral",
        path=caminho_local,
    )


def _formatar_erros(erros):
    return [{u"name": nome, u"mensagem": msg} for nome, msg in erros]


def _carregar(uiapp, entradas, caminhos_temporarios, erros_download, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        print(u"[AVISO] Nenhum documento ativo para carregar as famílias (bridge web).")
        for caminho in caminhos_temporarios:
            remover_temporario(caminho)
        erros_sem_doc = [(e.name, u"Nenhum documento ativo no Revit.") for e in entradas]
        postar_mensagem(u"LOAD_RESULT", {
            u"carregadas": [],
            u"jaExistentes": [],
            u"erros": _formatar_erros(erros_sem_doc + erros_download),
        })
        return
    doc = uidoc.Document

    carregadas, ja_existentes, erros, _familias_por_nome = carregar_familias(doc, entradas)
    for nome, msg in erros:
        print(u"[AVISO] Falha ao carregar '{}': {}".format(nome, msg))

    # A partir daqui a família já está embutida no documento (.rvt) — o
    # .rfa baixado não é mais necessário.
    for caminho in caminhos_temporarios:
        remover_temporario(caminho)

    postar_mensagem(u"LOAD_RESULT", {
        u"carregadas": carregadas,
        u"jaExistentes": ja_existentes,
        u"erros": _formatar_erros(erros + erros_download),
    })


def _baixar_em_background(familias, fila_acoes, postar_mensagem):
    entradas = []
    caminhos_temporarios = []
    erros_download = []
    for item in familias:
        try:
            caminho_local = baixar_temporario(
                item[u"storageKey"], item[u"signedUrl"], item[u"name"], item.get(u"sha256")
            )
        except Exception as ex:
            mensagem_ex = texto_erro(ex)
            print(u"[AVISO] Falha ao baixar '{}' do Supabase: {}".format(item.get(u"name"), mensagem_ex))
            erros_download.append((item.get(u"name") or u"?", mensagem_ex))
            continue
        caminhos_temporarios.append(caminho_local)
        entradas.append(_montar_entrada(item, caminho_local))

    if not entradas:
        if erros_download:
            fila_acoes.enfileirar(lambda uiapp: postar_mensagem(u"LOAD_RESULT", {
                u"carregadas": [],
                u"jaExistentes": [],
                u"erros": _formatar_erros(erros_download),
            }))
        return

    fila_acoes.enfileirar(
        lambda uiapp: _carregar(uiapp, entradas, caminhos_temporarios, erros_download, postar_mensagem)
    )


def processar_mensagem_webview(mensagem_json, fila_acoes, postar_mensagem):
    """
    `mensagem_json`: string JSON crua recebida em
    CoreWebView2.WebMessageReceived (args.WebMessageAsJson).
    `fila_acoes`: instância de family_loader_events.criar_fila_acoes(),
    criada junto do painel (precisa de contexto de API válido pra existir).
    `postar_mensagem(tipo, payload)`: callback do painel que manda uma
    mensagem de volta pro React via CoreWebView2.PostWebMessageAsJson.
    """
    try:
        mensagem = json.loads(mensagem_json)
    except ValueError:
        print(u"[AVISO] Mensagem da bridge web não é JSON válido: {}".format(mensagem_json))
        return

    tipo = mensagem.get(u"type")
    payload = mensagem.get(u"payload") or {}

    if tipo == u"LOAD_FAMILIES":
        familias = payload.get(u"familias") or []
        if not familias:
            return
        threading.Thread(
            target=_baixar_em_background,
            args=(familias, fila_acoes, postar_mensagem),
        ).start()
    else:
        print(u"[AVISO] Tipo de mensagem da bridge web desconhecido: {}".format(tipo))
