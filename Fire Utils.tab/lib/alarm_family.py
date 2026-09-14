# -*- coding: utf-8 -*-
"""
alarm_family.py — Fire Utils · lib/
Confirma que as famílias de alarme de incêndio (Acionador Manual =
"botoeira", Avisador Sonoro e Visual = "sirene") já estão carregadas e
ativadas no documento ativo. Não baixa nem carrega nada — se faltar
alguma, orienta o usuário a carregá-la pela dockpane (Biblioteca de
Famílias). Ver family_check.py.

Uso:
    from alarm_family import (garantir_acionador, garantir_alarme_sonoro,
                               NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME)

    sim, erro = garantir_acionador(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

from family_check import garantir_familia_no_projeto

NOME_FAMILIA_ACIONADOR = u"Acionador Manual do Sistema de Detecção e Alarme"
NOME_FAMILIA_ALARME    = u"Avisador Sonoro e Visual"


def garantir_acionador(doc):
    return garantir_familia_no_projeto(doc, NOME_FAMILIA_ACIONADOR)


def garantir_alarme_sonoro(doc):
    return garantir_familia_no_projeto(doc, NOME_FAMILIA_ALARME)
