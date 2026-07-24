# -*- coding: utf-8 -*-
"""
shelter_family.py — Fire Utils · lib/
Garante que a família 'Abrigo de Mangueira para Hidrante' está carregada e ativada.

Uso:
    from shelter_family import garantir_abrigo, NOME_FAMILIA_ABRIGO

    simbolo, erro = garantir_abrigo(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

import clr
clr.AddReference("RevitAPI")

import os
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

NOME_FAMILIA_ABRIGO = u"Abrigo de Mangueira para Hidrante"


def _caminho_padrao():
    """
    Resolve o caminho padrão do .rfa relativo a este arquivo.
    lib/ → family_library/Hidrantes/ (biblioteca única de famílias da extensão)
    """
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(lib_dir, u"family_library", u"Hidrantes",
                     NOME_FAMILIA_ABRIGO + u".rfa")
    )


def garantir_abrigo(doc, familia_path=None):
    """
    Garante que 'Abrigo de Mangueira para Hidrante' está carregada e ativada.

    Retorno
    -------
    (simbolo, erro_msg)
        simbolo  : FamilySymbol ativo, ou None se houver erro
        erro_msg : str com descrição do problema, ou None em caso de sucesso
    """
    if familia_path is None:
        familia_path = _caminho_padrao()

    if not os.path.exists(familia_path):
        return None, (u"Família não encontrada em:\n{}\n\n"
                      u"Verifique se o arquivo existe na pasta "
                      u"lib/family_library/Hidrantes/ da extensão.".format(familia_path))

    familia = next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if f.Name == NOME_FAMILIA_ABRIGO),
        None
    )

    if familia is None:
        with Transaction(doc, u"FireUtils - Carregar Abrigo de Hidrante") as t:
            t.Start()
            try:
                ref_fam = clr.Reference[Family]()
                if doc.LoadFamily(familia_path, ref_fam):
                    familia = ref_fam.Value
                t.Commit()
            except Exception as e:
                t.RollBack()
                return None, u"Erro ao carregar família:\n{}".format(str(e))

    if familia is None:
        return None, (u"Não foi possível localizar a família no projeto "
                      u"após o carregamento.")

    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None, u"Família carregada, mas nenhum tipo encontrado."

    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Simbolo do Abrigo") as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo, None
