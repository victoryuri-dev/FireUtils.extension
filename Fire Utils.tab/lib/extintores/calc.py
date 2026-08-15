# -*- coding: utf-8 -*-
"""
extintores/calc.py
Coleta instâncias de extintor no modelo e grava os dados na chave
'extintores' do firedata.json (arquivo único, ao lado do .rvt).

Uma instância é considerada extintor quando:
  - sua categoria está em params.CATEGORIAS_EXTINTOR (Proteção contra
    Incêndio); e
  - o parâmetro "Capacidade Extintora" (instância ou tipo) está preenchido.
"""

import json
import os
import io
import re
import datetime

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, StorageType,
)

from extintores.params import CATEGORIAS_EXTINTOR, PARAM_CAPACIDADE
from sync import enviar as enviar_sync

_CACHE_NOME = u"firedata.json"


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _lookup(elem, nome_param):
    """Procura o parâmetro na instância; se não achar (ou vier vazio),
    procura no Tipo (Symbol) — cobre parâmetros de Tipo definidos na família,
    como e' o caso de Tipo/Formato/Capacidade Extintora/Carga."""
    param = elem.LookupParameter(nome_param)
    if param and param.HasValue:
        return param
    simbolo = getattr(elem, "Symbol", None)
    if simbolo:
        param = simbolo.LookupParameter(nome_param)
        if param and param.HasValue:
            return param
    return None


def _texto_exibido(param):
    """Valor de exibição do parâmetro, qualquer que seja o StorageType."""
    if param.StorageType == StorageType.String:
        return param.AsString() or u""
    texto = param.AsValueString()
    if texto:
        return texto
    if param.StorageType == StorageType.Double:
        return unicode(param.AsDouble())
    if param.StorageType == StorageType.Integer:
        return unicode(param.AsInteger())
    return u""


def _get_texto(elem, nome_param):
    param = _lookup(elem, nome_param)
    if not param:
        return u""
    return _texto_exibido(param)


def _get_numero(elem, nome_param):
    param = _lookup(elem, nome_param)
    if not param:
        return None
    if param.StorageType == StorageType.Double:
        return param.AsDouble()
    if param.StorageType == StorageType.Integer:
        return float(param.AsInteger())
    # Texto (ex.: "10 L") — extrai o primeiro número exibido.
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", _texto_exibido(param))
    return float(m.group().replace(u",", u".")) if m else None


def _get_pavimento(doc, elem):
    level_id = getattr(elem, "LevelId", None)
    if not level_id or level_id == ElementId.InvalidElementId:
        return u""
    nivel = doc.GetElement(level_id)
    return nivel.Name if nivel else u""


def coletar_itens(doc):
    """Varre o modelo e retorna a lista de itens de extintor encontrados."""
    cat_ids = set(
        _get_id_value(doc.Settings.Categories.get_Item(bic).Id)
        for bic in CATEGORIAS_EXTINTOR
        if doc.Settings.Categories.get_Item(bic)
    )

    instancias = FilteredElementCollector(doc) \
        .OfClass(FamilyInstance) \
        .WhereElementIsNotElementType() \
        .ToElements()

    itens = []
    for elem in instancias:
        categoria = elem.Category
        if not categoria or _get_id_value(categoria.Id) not in cat_ids:
            continue

        capacidade = _get_texto(elem, PARAM_CAPACIDADE)
        if not capacidade.strip():
            continue

        itens.append({
            u"estrutura":   _get_texto(elem, u"Estrutura"),
            u"pavimento":   _get_pavimento(doc, elem),
            u"ambiente":    _get_texto(elem, u"Ambiente"),
            u"tipo":        _get_texto(elem, u"Tipo"),
            u"formato":     _get_texto(elem, u"Formato"),
            u"capacidade":  capacidade,
            u"carga":       _get_numero(elem, u"Carga"),
        })

    return itens


def salvar_cache(itens, projeto_dir):
    """Grava os itens de extintor na chave 'extintores' do firedata.json."""
    payload = {
        u"_timestamp": datetime.datetime.utcnow().strftime(u"%Y-%m-%dT%H:%M:%SZ"),
        u"itens":      itens,
    }

    path = _cache_path(projeto_dir)
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
    except Exception:
        dados = {}

    dados[u"extintores"] = payload
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    enviar_sync(u"extintores", payload, projeto_dir)

    return path
