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
  elevacao_m   : elevação (m) da placa em relação ao nível do equipamento
                 de referência — ver signage_insert_core._inserir_placa
  localizar    : function(doc) -> list[FamilyInstance] dos equipamentos já
                 inseridos no projeto que esse tipo de placa sinaliza
"""

import unicodedata

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance

from hydrant_family import NOME_FAMILIA as NOME_FAMILIA_VALVULA
from alarm_family import NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME
from alarm_insert_core import ALTURA_ACION_M, ALTURA_ALARME_M
from extintores.params import CATEGORIAS_EXTINTOR, PARAM_CAPACIDADE


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _normalizado(texto):
    """Minúsculo e sem acento — usado pra comparar Family.Name sem
    depender de acentuação exata. Existem famílias antigas do projeto
    carregadas antes da convenção de nomes ASCII deste plugin (ver
    family_cache.py) cujo Family.Name interno do .rfa ainda está
    acentuado (ex.: 'Válvula para Hidrante'), enquanto as constantes do
    código (hydrant_family.NOME_FAMILIA etc.) são ASCII — comparar direto
    fazia a busca por nome nunca encontrar essas instâncias."""
    if not texto:
        return u""
    sem_acento = unicodedata.normalize(u"NFKD", texto)
    sem_acento = u"".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def _todas_instancias(doc):
    return FilteredElementCollector(doc).OfClass(FamilyInstance) \
        .WhereElementIsNotElementType().ToElements()


def _instancias_por_familia(doc, nome_familia):
    alvo = _normalizado(nome_familia)
    return [
        e for e in _todas_instancias(doc)
        if e.Symbol is not None and e.Symbol.Family is not None
        and _normalizado(e.Symbol.Family.Name) == alvo
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
    def __init__(self, chave, rotulo, arquivo_slug, localizar, elevacao_m=0.0):
        self.chave = chave
        self.rotulo = rotulo
        self.arquivo_slug = arquivo_slug
        self.localizar = localizar
        self.elevacao_m = elevacao_m


# Elevação (m) de cada placa em relação ao nível do equipamento de
# referência. Hidrante e Extintor ficam em 0 — as próprias famílias das
# placas já têm a altura certa embutida. Sirene e Botoeira usam a MESMA
# altura da botoeira/avisador de referência (ALTURA_ACION_M/ALTURA_ALARME_M
# de alarm_insert_core.py), porque essas placas não têm altura própria
# embutida — precisam ficar na altura real do equipamento que sinalizam.
TIPOS_SINALIZACAO = [
    TipoSinalizacao(
        u"hidrante", u"Hidrantes — E8", u"placa-de-sinalizacao-e8-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_VALVULA),
        elevacao_m=0.0),
    TipoSinalizacao(
        u"sirene", u"Sirene — E1", u"placa-de-sinalizacao-e1-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ALARME),
        elevacao_m=ALTURA_ALARME_M),
    TipoSinalizacao(
        u"botoeira", u"Botoeira — E2", u"placa-de-sinalizacao-e2-10m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ACIONADOR),
        elevacao_m=ALTURA_ACION_M),
    TipoSinalizacao(
        u"extintor", u"Extintores — E5", u"placa-de-sinalizacao-e5-8m",
        _instancias_extintor,
        elevacao_m=0.0),
]
