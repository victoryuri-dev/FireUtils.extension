# -*- coding: utf-8 -*-
"""
family_webview_bridge.py — Fire Utils · lib/
Fase 3/4 do plano de migração: processa as mensagens que chegam do frontend
React (webapp/) via WebView2 CoreWebView2.WebMessageReceived. Contrato de
mensagens documentado em webapp/README.md.

Fluxo de uma mensagem LOAD_FAMILIES:
  1. Download de cada .rfa (com cache, family_cache.py) — roda numa thread
     separada da UI, porque WebMessageReceived dispara na mesma UI thread
     do Revit/WPF, e um .rfa grande (dezenas de MB) levaria vários segundos
     via rede, travando a interface inteira nesse meio tempo.
  2. Só depois que os arquivos já estão em disco, a ação de
     Document.LoadFamily (e o posicionamento, se pedido) é enfileirada via
     ExternalEvent (family_loader_events.py) — igual ao painel WPF antigo,
     porque tocar a API do Revit exige contexto de API válido, que só o
     ExternalEvent garante. ExternalEvent.Raise() é seguro de chamar de
     qualquer thread, então a thread de download pode enfileirar direto.
"""

import json
import threading

from family_loader import FamilyEntry, carregar_familias, obter_symbol_para_posicionar
from family_cache import obter_ou_baixar


def _montar_entrada(item_familia, caminho_local):
    return FamilyEntry(
        name=item_familia[u"name"],
        category=item_familia.get(u"categoryId") or u"Geral",
        path=caminho_local,
    )


def _carregar_e_posicionar(uiapp, entradas, posicionar):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        print(u"[AVISO] Nenhum documento ativo para carregar as famílias (bridge web).")
        return
    doc = uidoc.Document

    carregadas, ja_existentes, erros = carregar_familias(doc, entradas)
    for nome, msg in erros:
        print(u"[AVISO] Falha ao carregar '{}': {}".format(nome, msg))

    if not posicionar:
        return

    nomes_prontos = set(carregadas) | set(ja_existentes)
    for entrada in entradas:
        if entrada.name not in nomes_prontos:
            continue
        simbolo = obter_symbol_para_posicionar(doc, entrada.name)
        if simbolo is None:
            continue
        try:
            uidoc.PromptForFamilyInstancePlacement(simbolo)
        except Exception:
            break  # Esc pressionado — encerra o posicionamento em lote


def _baixar_em_background(familias, posicionar, fila_acoes):
    entradas = []
    for item in familias:
        try:
            caminho_local = obter_ou_baixar(
                item[u"storageKey"], item[u"signedUrl"], item.get(u"sha256")
            )
        except Exception as ex:
            print(u"[AVISO] Falha ao baixar '{}' do Supabase: {}".format(item.get(u"name"), ex))
            continue
        entradas.append(_montar_entrada(item, caminho_local))

    if not entradas:
        return

    fila_acoes.enfileirar(lambda uiapp: _carregar_e_posicionar(uiapp, entradas, posicionar))


def processar_mensagem_webview(mensagem_json, fila_acoes):
    """
    `mensagem_json`: string JSON crua recebida em
    CoreWebView2.WebMessageReceived (args.WebMessageAsJson).
    `fila_acoes`: instância de family_loader_events.criar_fila_acoes(),
    criada junto do painel (precisa de contexto de API válido pra existir).
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
        posicionar = bool(payload.get(u"posicionar"))
        threading.Thread(
            target=_baixar_em_background,
            args=(familias, posicionar, fila_acoes),
        ).start()
    else:
        print(u"[AVISO] Tipo de mensagem da bridge web desconhecido: {}".format(tipo))
