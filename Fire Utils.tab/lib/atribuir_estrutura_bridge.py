# -*- coding: utf-8 -*-
"""
atribuir_estrutura_bridge.py — Fire Utils · lib/
Processa ASSIGN_ESTRUTURA_SELECAO: escreve o nome de uma estrutura (das
vinculadas ao arquivo — ver project_link_bridge.py) no parâmetro
"Estrutura" (ver estrutura_param.py) de todos os elementos selecionados
no momento no Revit — disparado pelo botão "Atribuir seleção à estrutura"
da dockpane, sem abrir nenhum painel novo (o resultado volta só como
notificação).

Seleção nativa do Revit (uidoc.Selection.GetElementIds()) — a dockpane não
manda a lista de elementos, só o nome da estrutura; quem decide o que está
selecionado é o Revit, igual a qualquer pushbutton que opera "sobre a
seleção atual".
"""

from family_error_utils import texto_erro
from estrutura_param import atribuir_estrutura

_TIPO_RESPOSTA = u"ESTRUTURA_ATRIBUIDA"


def _erro(postar_mensagem, mensagem):
    postar_mensagem(_TIPO_RESPOSTA, {u"ok": False, u"erro": mensagem})


def tratar_assign_estrutura_selecao(uiapp, payload, postar_mensagem):
    try:
        _processar(uiapp, payload, postar_mensagem)
    except Exception as ex:
        _erro(postar_mensagem, u"Falha inesperada ao atribuir estrutura: {}".format(texto_erro(ex)))


def _processar(uiapp, payload, postar_mensagem):
    nome_estrutura = (payload.get(u"estruturaNome") or u"").strip()
    if not nome_estrutura:
        _erro(postar_mensagem, u"Nenhuma estrutura informada.")
        return

    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        _erro(postar_mensagem, u"Salve o projeto Revit (.rvt) antes de atribuir uma estrutura.")
        return

    ids_selecionados = list(uidoc.Selection.GetElementIds())
    if not ids_selecionados:
        _erro(postar_mensagem, u"Nenhum elemento selecionado no Revit. Selecione as famílias/ambientes e tente de novo.")
        return

    doc = uidoc.Document
    elementos = [doc.GetElement(eid) for eid in ids_selecionados]
    elementos = [e for e in elementos if e is not None]

    marcados, ignorados = atribuir_estrutura(doc, elementos, nome_estrutura)

    if marcados == 0:
        _erro(postar_mensagem, (
            u"Nenhum dos {} elemento(s) selecionado(s) tem o parâmetro Estrutura "
            u"(categorias aceitas: Proteção contra Incêndio, Dispositivos de "
            u"Segurança, Luminárias, Ambientes)."
        ).format(len(elementos)))
        return

    postar_mensagem(_TIPO_RESPOSTA, {
        u"ok": True,
        u"estruturaNome": nome_estrutura,
        u"marcados": marcados,
        u"ignorados": ignorados,
    })
