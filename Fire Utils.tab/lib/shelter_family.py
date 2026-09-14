# -*- coding: utf-8 -*-
"""
shelter_family.py — Fire Utils · lib/
Garante que a família 'Abrigo de Mangueira para Hidrante' está carregada e
ativada no documento ativo — baixando do catálogo do Supabase (o mesmo
acervo do Carregador de Famílias da dockpane) quando ela ainda não
estiver no projeto. Ver family_supabase.py pro fluxo de download/carga.

Uso:
    from shelter_family import garantir_abrigo, NOME_FAMILIA_ABRIGO

    simbolo, erro = garantir_abrigo(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

from family_supabase import garantir_familia_supabase

NOME_FAMILIA_ABRIGO = u"Abrigo de Mangueira para Hidrante"


def garantir_abrigo(doc):
    """
    Garante que 'Abrigo de Mangueira para Hidrante' está carregada e ativada.

    Retorno
    -------
    (simbolo, erro_msg)
        simbolo  : FamilySymbol ativo, ou None se houver erro
        erro_msg : str com descrição do problema, ou None em caso de sucesso
    """
    return garantir_familia_supabase(doc, NOME_FAMILIA_ABRIGO)
