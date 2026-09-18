# -*- coding: utf-8 -*-
"""
family_check.py — Fire Utils · lib/
Confirma que uma família específica JÁ ESTÁ carregada e ativada no
documento ativo. NÃO baixa nem carrega nada — se a família estiver
ausente, orienta o usuário a carregá-la pela dockpane (FireUtils,
Fire Utils.tab/Biblioteca.panel/Carregador de Familias), que é
quem sabe buscar no catálogo do Supabase.

A comparação de Family.Name ignora acentuação (normaliza NFKD antes de
comparar): famílias carregadas antes da convenção de nomes ASCII deste
plugin podem ter o Family.Name interno do .rfa ainda acentuado (ex.:
'Válvula para Hidrante'), o que faria uma comparação literal nunca
encontrar essas instâncias.

Uso:
    from family_check import garantir_familia_no_projeto

    simbolo, erro = garantir_familia_no_projeto(doc, u"Abrigo de Mangueira para Hidrante")
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

import unicodedata

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

_MSG_CARREGUE_PELA_DOCKPANE = (
    u"Família '{}' não encontrada no projeto.\n\n"
    u"Abra o FireUtils (aba Fire Utils) e "
    u"carregue essa família antes de continuar."
)


def normalizado(texto):
    """Minúsculo e sem acento — ver docstring do módulo."""
    if not texto:
        return u""
    sem_acento = unicodedata.normalize(u"NFKD", texto)
    sem_acento = u"".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def familia_no_documento(doc, nome_familia):
    """Retorna a Family de nome `nome_familia` (comparação sem acento) já
    carregada em `doc`, ou None se não estiver."""
    alvo = normalizado(nome_familia)
    return next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if normalizado(f.Name) == alvo),
        None
    )


def garantir_familia_no_projeto(doc, nome_familia):
    """
    Confirma que `nome_familia` já está carregada no projeto e retorna o
    seu FamilySymbol ativo — ativando-o primeiro se necessário. Não
    carrega a família: se estiver ausente, retorna uma mensagem
    orientando a carregar pela dockpane.

    Retorno: (FamilySymbol, erro_msg) — erro_msg é None em caso de sucesso.
    """
    familia = familia_no_documento(doc, nome_familia)
    if familia is None:
        return None, _MSG_CARREGUE_PELA_DOCKPANE.format(nome_familia)

    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None, u"Família '{}' encontrada, mas nenhum tipo encontrado.".format(nome_familia)

    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Símbolo {}".format(nome_familia)) as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo, None
