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
  arquivo_slug : nome do arquivo .rfa (sem extensão) da placa, no mesmo
                 formato do slugify() abaixo — usado pra achar a família
                 já carregada no projeto pelo nome (ver
                 signage_insert_core._familia_placa_carregada), já que a
                 família não é baixada automaticamente por este plugin
                 (precisa ser carregada antes pela dockpane)
  elevacao_m   : elevação (m) da placa em relação ao nível do equipamento
                 de referência — ver signage_insert_core._inserir_placa
  localizar    : function(doc) -> list[FamilyInstance] dos equipamentos já
                 inseridos no projeto que esse tipo de placa sinaliza
"""

import re
import unicodedata

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance

from alarm_family import NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME
from shelter_family import NOME_FAMILIA_ABRIGO
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


def slugify(texto):
    """'Placa de Sinalização E8 - 8m' -> 'placa-de-sinalizacao-e8-8m' —
    MESMO algoritmo de migration/generate_catalog.py (usado lá pra gerar
    o storage_key/nome de arquivo de cada família no catálogo). Usado
    aqui ao contrário: dado o Family.Name de uma família já carregada no
    projeto, confirma se ela corresponde ao TipoSinalizacao.arquivo_slug
    esperado (ver signage_insert_core._familia_placa_carregada)."""
    if not texto:
        return u"item"
    sem_acento = unicodedata.normalize(u"NFKD", texto)
    sem_acento = sem_acento.encode(u"ascii", u"ignore").decode(u"ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", u"-", sem_acento).strip(u"-").lower()
    return slug or u"item"


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


def _nivel_por_equipamento(doc, equipamento):
    """Padrão: usa o LevelId do próprio equipamento sinalizado."""
    return doc.GetElement(equipamento.LevelId)


def _nivel_por_abrigo_mais_proximo(doc, equipamento):
    """Usa o nível do ABRIGO DE MANGUEIRA mais próximo, em vez do LevelId
    do próprio equipamento — Sirene e Botoeira são sempre inseridos a uma
    distância fixa de um abrigo (ver alarm_insert_core.py), e é o nível
    do abrigo (não o do próprio dispositivo) que deve servir de
    referência pra placa, pro mesmo pavimento valer pros dois."""
    try:
        pt = equipamento.Location.Point
    except Exception:
        return _nivel_por_equipamento(doc, equipamento)

    abrigos = _instancias_por_familia(doc, NOME_FAMILIA_ABRIGO)
    mais_proximo = None
    menor_distancia = None
    for abrigo in abrigos:
        try:
            distancia = pt.DistanceTo(abrigo.Location.Point)
        except Exception:
            continue
        if menor_distancia is None or distancia < menor_distancia:
            menor_distancia = distancia
            mais_proximo = abrigo

    if mais_proximo is None:
        return _nivel_por_equipamento(doc, equipamento)
    return doc.GetElement(mais_proximo.LevelId)


class TipoSinalizacao(object):
    def __init__(self, chave, rotulo, arquivo_slug, localizar, elevacao_m=0.0,
                 nivel_referencia=None):
        self.chave = chave
        self.rotulo = rotulo
        self.arquivo_slug = arquivo_slug
        self.localizar = localizar
        self.elevacao_m = elevacao_m
        self.nivel_referencia = nivel_referencia or _nivel_por_equipamento


# Elevação (m) de cada placa em relação ao seu nível de referência
# (TipoSinalizacao.nivel_referencia) — SEMPRE 0 nos quatro tipos: todas
# as famílias de placa já têm a altura real (1,80m do piso) embutida
# internamente, então "elevação 0" já posiciona a placa na altura
# correta. O que importa acertar é o NÍVEL de referência: pra Hidrante
# é o do próprio abrigo (o equipamento localizado já É o abrigo); pra
# Sirene/Botoeira é o do abrigo mais próximo (não o do próprio
# dispositivo, que pode estar em outro nível de referência — ver
# alarm_insert_core._forcar_nivel_referencia); pra Extintor é o do
# próprio extintor.
TIPOS_SINALIZACAO = [
    # A sinalização do hidrante é do ABRIGO DE MANGUEIRA, não da válvula
    # — fica no ponto e no nível do próprio abrigo.
    TipoSinalizacao(
        u"hidrante", u"Hidrantes — E8", u"placa-de-sinalizacao-e8-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ABRIGO)),
    TipoSinalizacao(
        u"sirene", u"Sirene — E1", u"placa-de-sinalizacao-e1-8m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ALARME),
        nivel_referencia=_nivel_por_abrigo_mais_proximo),
    TipoSinalizacao(
        u"botoeira", u"Botoeira — E2", u"placa-de-sinalizacao-e2-10m",
        lambda doc: _instancias_por_familia(doc, NOME_FAMILIA_ACIONADOR),
        nivel_referencia=_nivel_por_abrigo_mais_proximo),
    TipoSinalizacao(
        u"extintor", u"Extintores — E5", u"placa-de-sinalizacao-e5-8m",
        _instancias_extintor),
]
