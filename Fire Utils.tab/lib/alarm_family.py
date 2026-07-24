# -*- coding: utf-8 -*-
"""
alarm_family.py — Fire Utils · lib/
Garante que as famílias de alarme de incêndio estão carregadas e ativadas.

Uso:
    from alarm_family import (garantir_acionador, garantir_alarme_sonoro,
                               NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME)

    sim, erro = garantir_acionador(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

import clr
clr.AddReference("RevitAPI")

import os
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

NOME_FAMILIA_ACIONADOR = u"Acionador Manual do Sistema de Detecção e Alarme"
NOME_FAMILIA_ALARME    = u"Avisador Sonoro e Visual"

_FAMILIAS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 u"family_library", u"Alarmes e Detecção")
)


def _garantir_familia(doc, nome):
    """
    Garante que a família `nome` está carregada e ativada.

    Retorno
    -------
    (FamilySymbol, erro_msg)
    """
    familia_path = os.path.join(_FAMILIAS_DIR, nome + u".rfa")

    if not os.path.exists(familia_path):
        return None, (u"Família não encontrada em:\n{}\n\n"
                      u"Verifique se o arquivo .rfa existe na pasta "
                      u"lib/family_library/Alarmes e Detecção/ da extensão.".format(familia_path))

    familia = next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if f.Name == nome),
        None
    )

    if familia is None:
        with Transaction(doc, u"FireUtils - Carregar {}".format(nome)) as t:
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
        return None, (u"Não foi possível localizar '{}' no projeto "
                      u"após o carregamento.".format(nome))

    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None, u"Família '{}' carregada, mas nenhum tipo encontrado.".format(nome)

    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Símbolo {}".format(nome)) as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo, None


def garantir_acionador(doc):
    return _garantir_familia(doc, NOME_FAMILIA_ACIONADOR)


def garantir_alarme_sonoro(doc):
    return _garantir_familia(doc, NOME_FAMILIA_ALARME)
