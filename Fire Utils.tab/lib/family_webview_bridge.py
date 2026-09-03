# -*- coding: utf-8 -*-
"""
family_webview_bridge.py — Fire Utils · lib/
Processa as mensagens que chegam do frontend React (webapp/) via WebView2
CoreWebView2.WebMessageReceived. Contrato de mensagens documentado em
webapp/README.md.

Fluxo de uma mensagem LOAD_FAMILIES:
  1. Download de cada .rfa pra um arquivo temporário (family_cache.py, sem
     cache persistente — ver docstring de lá pro porquê) — roda numa
     thread separada da UI, porque WebMessageReceived dispara na mesma UI
     thread do Revit/WPF, e um .rfa grande (dezenas de MB) levaria vários
     segundos via rede, travando a interface inteira nesse meio tempo.
  2. Só depois que os arquivos já estão em disco, a ação de
     Document.LoadFamily (e o posicionamento, se pedido) é enfileirada via
     ExternalEvent (family_loader_events.py), porque tocar a API do Revit
     exige contexto de API válido, que só o ExternalEvent garante.
     ExternalEvent.Raise() é seguro de chamar de qualquer thread, então a
     thread de download pode enfileirar direto.
  3. Os arquivos temporários são apagados logo depois do LoadFamily rodar
     (a família já está embutida no .rvt a partir daí) — sem esperar o
     posicionamento manual terminar, que pode levar bem mais tempo.
"""

import json
import threading

import clr
clr.AddReference(u"RevitAPI")
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import forms

from family_loader import FamilyEntry, carregar_familias, obter_symbol_de_familia
from family_cache import baixar_temporario, remover_temporario


def _montar_entrada(item_familia, caminho_local):
    return FamilyEntry(
        name=item_familia[u"name"],
        category=item_familia.get(u"categoryId") or u"Geral",
        path=caminho_local,
    )


def _carregar_e_posicionar(uiapp, entradas, posicionar, caminhos_temporarios):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        print(u"[AVISO] Nenhum documento ativo para carregar as famílias (bridge web).")
        for caminho in caminhos_temporarios:
            remover_temporario(caminho)
        return
    doc = uidoc.Document

    carregadas, ja_existentes, erros, familias_por_nome = carregar_familias(doc, entradas)
    for nome, msg in erros:
        print(u"[AVISO] Falha ao carregar '{}': {}".format(nome, msg))

    # A partir daqui a família já está embutida no documento (.rvt) — o
    # .rfa baixado não é mais necessário, mesmo que o posicionamento
    # abaixo ainda vá rodar (pode levar bem mais tempo, é interativo).
    for caminho in caminhos_temporarios:
        remover_temporario(caminho)

    if not posicionar:
        return

    nomes_prontos = set(carregadas) | set(ja_existentes)
    for entrada in entradas:
        if entrada.name not in nomes_prontos:
            print(u"[AVISO] '{}' não está pronta pra posicionar (falhou ao carregar).".format(entrada.name))
            continue
        simbolo = obter_symbol_de_familia(doc, familias_por_nome.get(entrada.name))
        if simbolo is None:
            print(u"[AVISO] Nenhum tipo (FamilySymbol) encontrado pra posicionar '{}'.".format(entrada.name))
            continue
        try:
            uidoc.PromptForFamilyInstancePlacement(simbolo)
        except OperationCanceledException:
            # PromptForFamilyInstancePlacement deixa o usuário posicionar
            # QUANTAS instâncias quiser da mesma família, e só retorna
            # quando ele aperta Esc — ou seja, o Esc aqui significa
            # "terminei com essa família", não "cancele a lista inteira".
            # `continue` (não `break`) avança pra próxima família
            # selecionada em vez de abortar o lote inteiro.
            continue
        except Exception as ex:
            # Antes isso caía num "except Exception: break" genérico, que
            # engolia silenciosamente qualquer erro real (não só o Esc
            # esperado) — por isso "carrega mas não posiciona" não dava
            # pista nenhuma do motivo.
            print(u"[ERRO] Falha ao posicionar '{}': {}".format(entrada.name, ex))
            forms.alert(
                u"Não foi possível posicionar '{}':\n{}".format(entrada.name, ex),
                title=u"Fire Utils - Carregador de Famílias",
                warn_icon=True,
            )
            break


def _baixar_em_background(familias, posicionar, fila_acoes):
    entradas = []
    caminhos_temporarios = []
    for item in familias:
        try:
            caminho_local = baixar_temporario(
                item[u"storageKey"], item[u"signedUrl"], item.get(u"sha256")
            )
        except Exception as ex:
            print(u"[AVISO] Falha ao baixar '{}' do Supabase: {}".format(item.get(u"name"), ex))
            continue
        caminhos_temporarios.append(caminho_local)
        entradas.append(_montar_entrada(item, caminho_local))

    if not entradas:
        return

    fila_acoes.enfileirar(
        lambda uiapp: _carregar_e_posicionar(uiapp, entradas, posicionar, caminhos_temporarios)
    )


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
