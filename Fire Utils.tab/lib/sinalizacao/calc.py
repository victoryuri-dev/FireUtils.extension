# -*- coding: utf-8 -*-
"""
sinalizacao/calc.py
Coleta instâncias de placa de sinalização de emergência no modelo e grava
o quantitativo na chave 'sinalizacao' do firedata.json (arquivo único, ao
lado do .rvt).

Uma instância é considerada placa de sinalização de emergência quando:
  - sua categoria é "Dispositivos de Segurança" (OST_SecurityDevices); e
  - o parâmetro de TIPO "Código da Placa" está preenchido (ex.: "S1",
    "E5", "A2"...).

"Código da Placa" já vem embutido nas famílias de sinalização deste
escritório (parâmetro de Tipo definido na própria família) — diferente do
fluxo de Extintores, nenhum parâmetro precisa ser criado/vinculado aqui.

Granularidade só até estrutura (sem pavimento nem ambiente): cada arquivo
Revit sincroniza os dados da estrutura vinculada no Dashboard (ver
sync.config_sync) — o quantitativo já sai agregado por código de placa,
somando todas as instâncias do modelo (ver agrupar_por_placa).
"""

import json
import os
import io
import datetime

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInCategory, StorageType,
)

from sync import enviar as enviar_sync, config_sync

_CACHE_NOME = u"firedata.json"

CATEGORIA_SINALIZACAO = BuiltInCategory.OST_SecurityDevices
PARAM_CODIGO_PLACA    = u"Código da Placa"


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _lookup_tipo(elem, nome_param):
    """"Código da Placa" é parâmetro de TIPO — procura primeiro no Symbol
    (Tipo) da instância; cai pra instância só por robustez (mesmo padrão de
    extintores/calc.py._lookup), embora não deva haver override de
    instância num parâmetro de tipo."""
    simbolo = getattr(elem, "Symbol", None)
    if simbolo:
        param = simbolo.LookupParameter(nome_param)
        if param and param.HasValue:
            return param
    param = elem.LookupParameter(nome_param)
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
    if param.StorageType == StorageType.Integer:
        return unicode(param.AsInteger())
    return u""


def coletar_itens(doc):
    """Varre o modelo e retorna a lista de códigos de placa encontrados,
    uma entrada por instância — o agrupamento por código fica a cargo de
    agrupar_por_placa."""
    categoria = doc.Settings.Categories.get_Item(CATEGORIA_SINALIZACAO)
    if not categoria:
        return []
    cat_id = _get_id_value(categoria.Id)

    instancias = FilteredElementCollector(doc) \
        .OfClass(FamilyInstance) \
        .WhereElementIsNotElementType() \
        .ToElements()

    itens = []
    for elem in instancias:
        elem_categoria = elem.Category
        if not elem_categoria or _get_id_value(elem_categoria.Id) != cat_id:
            continue

        param = _lookup_tipo(elem, PARAM_CODIGO_PLACA)
        if not param:
            continue

        codigo = _texto_exibido(param).strip()
        if not codigo:
            continue

        itens.append({u"tipoPlaca": codigo})

    return itens


def agrupar_por_placa(itens):
    """Agrega os itens brutos (um por instância, ver coletar_itens) em
    {tipoPlaca, quantidade} — soma as instâncias com o mesmo código."""
    contagem = {}
    ordem = []
    for it in itens:
        codigo = it[u"tipoPlaca"]
        if codigo not in contagem:
            contagem[codigo] = 0
            ordem.append(codigo)
        contagem[codigo] += 1
    return [{u"tipoPlaca": codigo, u"quantidade": contagem[codigo]} for codigo in ordem]


def salvar_cache(itens_agrupados, projeto_dir):
    """Grava os itens de sinalização (já agregados por código — ver
    agrupar_por_placa) na chave 'sinalizacao' do firedata.json e envia
    (best-effort) pro site, escopado pela estrutura vinculada no plugin
    (ver sync.config_sync)."""
    payload = {
        u"_timestamp": datetime.datetime.utcnow().strftime(u"%Y-%m-%dT%H:%M:%SZ"),
        u"itens":      itens_agrupados,
    }

    path = _cache_path(projeto_dir)
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            dados = json.loads(f.read())
    except Exception:
        dados = {}

    dados[u"sinalizacao"] = payload
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    estrutura_id = config_sync(projeto_dir).get(u"estruturaId")
    enviar_sync(u"sinalizacao", payload, projeto_dir, estruturaId=estrutura_id)

    return path
