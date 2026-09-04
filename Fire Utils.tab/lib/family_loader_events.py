# -*- coding: utf-8 -*-
"""
family_loader_events.py — Fire Utils · lib/
Fila de ações executadas no contexto de API do Revit via ExternalEvent.

Necessária porque o Carregador de Famílias é uma janela modeless (fica
aberta sem travar o Revit): cliques nos seus botões acontecem fora do
contexto de API válido do Revit, então qualquer ação que toque a API
(carregar família, abrir documento para gerar thumbnail etc.) precisa ser
"pedida" ao Revit através de um ExternalEvent, que a executa assim que
possível — normalmente quase instantaneamente.
"""

import clr
clr.AddReference(u"RevitAPIUI")
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

from family_error_utils import texto_erro


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
            resultado = self.evento.Raise()
            if str(resultado) != u"Accepted":
                print(
                    u"[AVISO] ExternalEvent do Carregador de Famílias "
                    u"retornou '{}' ao tentar disparar.".format(resultado)
                )

    def Execute(self, uiapp):
        """Chamado pelo Revit — nunca deve ser chamado diretamente."""
        if not self._fila:
            return
        funcao = self._fila.pop(0)
        try:
            funcao(uiapp)
        except Exception as ex:
            print(u"[AVISO] Ação do Carregador de Famílias falhou: {}".format(texto_erro(ex)))
        finally:
            if self._fila:
                self.evento.Raise()

    def GetName(self):
        return u"FireUtils_CarregadorDeFamilias_ExternalEvent"


def criar_fila_acoes():
    """
    Cria um novo par (handler + ExternalEvent). Deve ser chamado a partir de
    um contexto de API válido (ex.: dentro do script que reage ao clique no
    botão da faixa de opções) — não pode ser criado depois, num handler de
    clique da janela modeless.
    """
    handler = _FilaAcoesHandler()
    handler.evento = ExternalEvent.Create(handler)
    return handler
