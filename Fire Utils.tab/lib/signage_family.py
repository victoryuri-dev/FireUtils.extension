# -*- coding: utf-8 -*-
"""
signage_family.py — Fire Utils · lib/
Define os tipos de placa de sinalização que o botão "Sinalizar
Equipamentos" pode inserir, e como localizar no modelo os equipamentos
que cada tipo sinaliza.

Cada TipoSinalizacao carrega:
  chave        : identificador curto, usado pra ligar o tipo ao CheckBox
                 correspondente em signage_opcoes.xaml (Chk_<chave>)
  rotulo       : texto exibido no painel de seleção
  arquivo_slug : nome do arquivo .rfa (sem extensão) da placa no catálogo
                 do Supabase — ver
                 family_supabase.garantir_familia_supabase_por_slug
  localizar    : function(doc) -> list[FamilyInstance] dos equipamentos já
                 inseridos no projeto que esse tipo de placa sinaliza
"""

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance

from hydrant_family import NOME_FAMILIA as NOME_FAMILIA_VALVULA
from alarm_family import NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME
from extintores.params import CATEGORIAS_EXTINTOR, PARAM_CAPACIDADE


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _todas_instancias(doc):
    return FilteredElementCollector(doc).OfClass(FamilyInstance) \
        .WhereElementIsNotElementType().ToElements()


def _instancias_por_familia(doc, nome_familia):
    return [
        e for e in _todas_instancias(doc)
        if e.Symbol is not None and e.Symbol.Family is not None
        and e.Symbol.Family.Name == nome_familia
    ]


def _instancias_extintor(doc):
    """Mesmo critério de extintores/calc.py: categoria Proteção contra
    Incêndio (OST_FireProtection) + parâmetro 'Capacidade Extintora'
    (instância ou tipo) preenchido — cobre as 5 famílias de extintor
    (A/ABC/BC/CO2/K) sem depender de um nome de família específico."""
    cat_ids = set(
        _get_id_value(doc.Settings.Categories.get_Item(bic).Id)
        for bic in CATEGORIAS_EXTINTOR
        if doc.Settings.Categories.get_Item(bic)
    )
    resultado = []
    for e in _todas_instancias(doc):
        categoria = e.Category
        if not categoria or _get_id_value(categoria.Id) not in cat_ids:
            continue
        param = e.LookupParameter(PARAM_CAPACIDADE)
        if (not param or not param.HasValue) and e.Symbol is not None:
            param = e.Symbol.LookupParameter(PARAM_CAPACIDADE)
        if param and param.HasValue:
            resultado.append(e)
    return resultado


class TipoSinalizacao(object):
    def __init__(self, chave, rotulo, arquivo_slug, localizar):
        self.chave = chave
        self.rotulo = rotulo
        self.arquivo_slug = arquivo_slug
        self.localizar = localizar


TIPOS_SINALIZACAO = [
    TipoSinalizacao(
        u"hidrante", u"Hidrantes — E8", u"placa-de-sinalizacao-e8-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_VALVULA)),
    TipoSinalizacao(
        u"sirene", u"Sirene — E1", u"placa-de-sinalizacao-e1-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ALARME)),
    TipoSinalizacao(
        u"botoeira", u"Botoeira — E2", u"placa-de-sinalizacao-e2-10m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ACIONADOR)),
    TipoSinalizacao(
        u"extintor", u"Extintores — E5", u"placa-de-sinalizacao-e5-8m",
        _instancias_extintor),
]
