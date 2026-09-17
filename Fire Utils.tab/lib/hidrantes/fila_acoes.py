# -*- coding: utf-8 -*-
"""
fila_acoes.py — Fire Utils · lib/hidrantes/
Fila de ações executadas no contexto de API do Revit via ExternalEvent —
mesmo padrão de family_loader_events.py, cópia própria pra não acoplar o
painel de Hidrantes ao Carregador de Famílias (cada um cria sua própria
fila/ExternalEvent).

Necessária pro botão "Localizar" da janela de inconsistências de "Mapear
Trechos" (resultado_ui.py): a janela fica aberta (ShowDialog) enquanto o
usuário confere os elementos um por um, e cada clique precisa chamar a API
do Revit (selecionar/enquadrar o elemento) sem fechar a janela nem travar
o Revit — chamar a API direto de dentro do Click de uma janela modal já
causou travamento fatal antes (ver histórico de "Mostrar no Projeto"); o
ExternalEvent é o jeito seguro e reentrante de fazer isso.
"""

import clr
clr.AddReference(u"RevitAPIUI")
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent


class _FilaAcoesHandler(IExternalEventHandler):
    """Executa, uma de cada vez, funções que precisam do contexto de API."""

    def __init__(self):
        self._fila = []
        self.evento = None  # atribuído por criar_fila_acoes() logo após a criação

    def enfileirar(self, funcao):
        """
        Agenda `funcao(uiapp)` para rodar assim que o Revit liberar o
        contexto de API. Pode ser chamado várias vezes seguidas; as funções
        são executadas uma por vez, na ordem em que foram enfileiradas.
        """
        self._fila.append(funcao)
        if self.evento is not None:
            self.evento.Raise()

    def Execute(self, uiapp):
        """Chamado pelo Revit — nunca deve ser chamado diretamente."""
        if not self._fila:
            return
        funcao = self._fila.pop(0)
        try:
            funcao(uiapp)
        except Exception as ex:
            print(u"[AVISO] Ação da fila de Hidrantes falhou: {}".format(ex))
        finally:
            if self._fila:
                self.evento.Raise()

    def GetName(self):
        return u"FireUtils_Hidrantes_ExternalEvent"


def criar_fila_acoes():
    """
    Cria um novo par (handler + ExternalEvent). Deve ser chamado a partir de
    um contexto de API válido (ex.: no corpo do script que reage ao clique
    no botão da faixa de opções) — não pode ser criado depois, num handler
    de clique de uma janela.
    """
    handler = _FilaAcoesHandler()
    handler.evento = ExternalEvent.Create(handler)
    return handler
