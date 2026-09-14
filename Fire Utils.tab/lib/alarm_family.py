# -*- coding: utf-8 -*-
"""
alarm_family.py — Fire Utils · lib/
Garante que as famílias de alarme de incêndio (Acionador Manual =
"botoeira", Avisador Sonoro e Visual = "sirene") estão carregadas e
ativadas no documento ativo — baixando do catálogo do Supabase (o mesmo
acervo do Carregador de Famílias da dockpane) quando ainda não estiverem
no projeto. Ver family_supabase.py pro fluxo de download/carga.

Uso:
    from alarm_family import (garantir_acionador, garantir_alarme_sonoro,
                               NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME)

    sim, erro = garantir_acionador(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

from family_supabase import garantir_familia_supabase

NOME_FAMILIA_ACIONADOR = u"Acionador Manual do Sistema de Detecção e Alarme"
NOME_FAMILIA_ALARME    = u"Avisador Sonoro e Visual"


def garantir_acionador(doc):
    return garantir_familia_supabase(doc, NOME_FAMILIA_ACIONADOR)


def garantir_alarme_sonoro(doc):
    return garantir_familia_supabase(doc, NOME_FAMILIA_ALARME)
