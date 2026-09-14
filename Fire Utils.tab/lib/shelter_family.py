# -*- coding: utf-8 -*-
"""
shelter_family.py — Fire Utils · lib/
Confirma que a família 'Abrigo de Mangueira para Hidrante' já está
carregada e ativada no documento ativo. Não baixa nem carrega nada — se
faltar, orienta o usuário a carregá-la pela dockpane (Biblioteca de
Famílias). Ver family_check.py.

Uso:
    from shelter_family import garantir_abrigo, NOME_FAMILIA_ABRIGO

    simbolo, erro = garantir_abrigo(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

from family_check import garantir_familia_no_projeto

NOME_FAMILIA_ABRIGO = u"Abrigo de Mangueira para Hidrante"


def garantir_abrigo(doc):
    """
    Confirma que 'Abrigo de Mangueira para Hidrante' já está carregada e
    ativada.

    Retorno
    -------
    (simbolo, erro_msg)
        simbolo  : FamilySymbol ativo, ou None se houver erro
        erro_msg : str com descrição do problema, ou None em caso de sucesso
    """
    return garantir_familia_no_projeto(doc, NOME_FAMILIA_ABRIGO)
