# -*- coding: utf-8 -*-
"""
quantitativos_bridge.py — Fire Utils · lib/
Processa GRAVAR_QUANTITATIVOS: roda o mesmo motor do antigo botão "Gravar
Quantitativos" (quantitativos_core.py — Extintores, Sinalização de
Emergência, Iluminação de Emergência), disparado por um único clique na
dockpane em vez de um botão de faixa de opções. Sem janela de seleção —
grava TODAS as medidas sempre — e sem abrir o output window do pyRevit: o
resultado volta pra dockpane virar uma notificação (ToastStack.jsx).

Duas etapas, cada uma no contexto certo (mesmo motivo de
family_webview_bridge.py:_baixar_em_background ser uma thread separada):
  1. coletar_todos(doc) — toca a API do Revit, roda aqui mesmo (já estamos
     na UI thread, chamados via fila_acoes.enfileirar pelo dispatcher).
  2. salvar_todos(...) — grava o firedata.json e envia pro site; cada
     medida tem até ~5s de timeout de rede, e 3 medidas em série
     travariam a UI do Revit por até ~15s se rodassem aqui — por isso vai
     pra uma thread separada, que ao terminar reenfileira só a resposta
     final (postar_mensagem só é seguro a partir da UI thread — ver
     family_loader_webview_forms.py:_postar_mensagem).
"""

import os
import threading

from quantitativos_core import coletar_todos, salvar_todos
from family_error_utils import texto_erro, print_seguro

_TIPO_RESPOSTA = u"QUANTITATIVOS_GRAVADOS"


def _erro(postar_mensagem, mensagem):
    postar_mensagem(_TIPO_RESPOSTA, {u"ok": False, u"erro": mensagem})


def tratar_gravar_quantitativos(uiapp, fila_acoes, postar_mensagem):
    # Mesma rede de segurança dos demais bridges (ver
    # hidrantes_dimensionar_bridge.py): sem isso, uma exceção não prevista
    # sobe até o ExternalEvent, que só loga no console do pyRevit, e a
    # dockpane fica esperando a resposta pra sempre.
    try:
        _processar(uiapp, fila_acoes, postar_mensagem)
    except Exception as ex:
        _erro(postar_mensagem, u"Falha inesperada ao gravar quantitativos: {}".format(texto_erro(ex)))


def _processar(uiapp, fila_acoes, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        _erro(postar_mensagem, u"Salve o projeto Revit (.rvt) antes de gravar quantitativos.")
        return
    doc = uidoc.Document
    projeto_dir = os.path.dirname(doc.PathName)

    resultados_coleta = coletar_todos(doc)

    threading.Thread(
        target=_salvar_em_background,
        args=(resultados_coleta, projeto_dir, fila_acoes, postar_mensagem),
    ).start()


def _salvar_em_background(resultados_coleta, projeto_dir, fila_acoes, postar_mensagem):
    try:
        resumo = salvar_todos(resultados_coleta, projeto_dir)
    except Exception as ex:
        mensagem = u"Falha inesperada ao gravar/enviar: {}".format(texto_erro(ex))
        print_seguro(u"[AVISO] {}".format(mensagem))
        fila_acoes.enfileirar(lambda uiapp: _erro(postar_mensagem, mensagem))
        return

    fila_acoes.enfileirar(
        lambda uiapp: postar_mensagem(_TIPO_RESPOSTA, {u"ok": True, u"medidas": resumo})
    )
