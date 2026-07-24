# -*- coding: utf-8 -*-
"""
hydrant_family.py — Fire Utils · lib/
Garante que a família 'Valvula para Hidrante' está carregada e ativada no projeto.

Uso:
    from hydrant_family import garantir_valvula

    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, ...)
        script.exit()
    # simbolo é o FamilySymbol ativo, pronto para uso
"""

import clr
clr.AddReference("RevitAPI")

import os
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
NOME_FAMILIA = u"Valvula para Hidrante"


def _caminho_padrao():
    """
    Resolve o caminho padrão do .rfa relativo a este arquivo.
    lib/ → family_library/Hidrantes/ (biblioteca única de famílias da extensão)
    """
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(lib_dir, u"family_library", u"Hidrantes",
                     NOME_FAMILIA + u".rfa")
    )


def garantir_valvula(doc, familia_path=None):
    """
    Garante que 'Valvula para Hidrante' está carregada e ativada no projeto.

    Parâmetros
    ----------
    doc         : Revit Document
    familia_path: caminho completo do .rfa (opcional; usa o padrão da extensão)

    Retorno
    -------
    (simbolo, erro_msg)
        simbolo  : FamilySymbol ativo, ou None se houver erro
        erro_msg : str com descrição do problema, ou None em caso de sucesso
    """
    if familia_path is None:
        familia_path = _caminho_padrao()

    # 1 — Verifica o arquivo .rfa em disco
    if not os.path.exists(familia_path):
        return None, (u"Família não encontrada em:\n{}\n\n"
                      u"Verifique se o arquivo existe na pasta "
                      u"lib/family_library/Hidrantes/ da extensão.".format(familia_path))

    # 2 — Procura família já carregada no documento
    familia = next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if f.Name == NOME_FAMILIA),
        None
    )

    # 3 — Carrega do disco se ainda não está no projeto
    if familia is None:
        with Transaction(doc, u"FireUtils - Carregar Valvula de Hidrante") as t:
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

    # 4 — Pega o primeiro tipo (FamilySymbol)
    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None, u"Família carregada, mas nenhum tipo encontrado."

    # 5 — Ativa o tipo se necessário
    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Simbolo da Valvula") as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo, None
