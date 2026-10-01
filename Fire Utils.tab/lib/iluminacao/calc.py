# -*- coding: utf-8 -*-
"""
iluminacao/calc.py
Coleta instâncias de equipamento de aclaramento (iluminação de emergência)
no modelo e grava o quantitativo na chave 'iluminacao' do firedata.json
(arquivo único, ao lado do .rvt).

Uma instância é considerada equipamento de aclaramento do Fire Utils
quando:
  - sua categoria é "Luminárias" (OST_LightingFixtures) — mesma categoria de
    qualquer luminária comum do projeto; e
  - o parâmetro de TIPO "Tipo Base Iluminação" está preenchido (ver
    iluminacao/params.py) — é o que distingue um bloco/luminária de
    emergência de uma luminária decorativa/funcional qualquer.

"Fluxo Luminoso Nominal" e "Tipo de Lâmpada" também são parâmetros de Tipo
(ver params.py) — lidos direto da família, sem exigir preenchimento (ficam
vazios se o RT não tiver cadastrado na família ainda; o site completa
potência/tensão/autonomia casando o fluxo com um preset do catálogo, se
houver — ver resolverImportacaoIluminacao em IluminacaoPage.jsx).

Granularidade até pavimento (sem ambiente, como o dimensionamento no site)
— o quantitativo já sai agregado por pavimento + tipo base + fluxo + tipo
de lâmpada, somando todas as instâncias equivalentes do modelo (ver
agrupar_por_pavimento).
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, StorageType,
)

from iluminacao.params import PARAM_TIPO_BASE, PARAM_FLUXO, PARAM_LAMPADA, CATEGORIAS_ILUMINACAO
from sync import gravar_e_enviar, config_sync


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _lookup_tipo(elem, nome_param):
    """Os três parâmetros são de TIPO — procura primeiro no Symbol (Tipo) da
    instância; cai pra instância só por robustez (mesmo padrão de
    sinalizacao/calc.py._lookup_tipo), embora não deva haver override de
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
    if param.StorageType == StorageType.Double:
        return unicode(param.AsDouble())
    if param.StorageType == StorageType.Integer:
        return unicode(param.AsInteger())
    return u""


def _get_texto(elem, nome_param):
    param = _lookup_tipo(elem, nome_param)
    if not param:
        return u""
    return _texto_exibido(param)


def _get_pavimento(doc, elem):
    level_id = getattr(elem, "LevelId", None)
    if not level_id or level_id == ElementId.InvalidElementId:
        return u""
    nivel = doc.GetElement(level_id)
    return nivel.Name if nivel else u""


def coletar_itens(doc):
    """Varre o modelo e retorna a lista de itens de aclaramento encontrados,
    uma entrada por instância — o agrupamento por pavimento/tipo fica a
    cargo de agrupar_por_pavimento."""
    cat_ids = set(
        _get_id_value(doc.Settings.Categories.get_Item(bic).Id)
        for bic in CATEGORIAS_ILUMINACAO
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

        tipo_base = _get_texto(elem, PARAM_TIPO_BASE).strip()
        if not tipo_base:
            continue

        itens.append({
            u"pavimento":       _get_pavimento(doc, elem),
            u"tipoBase":        tipo_base,
            u"fluxoLuminosoLm": _get_texto(elem, PARAM_FLUXO).strip(),
            u"tipoLampada":     _get_texto(elem, PARAM_LAMPADA).strip(),
        })

    return itens


def agrupar_por_pavimento(itens):
    """Agrega os itens brutos (um por instância, ver coletar_itens) em
    {pavimento, tipoBase, fluxoLuminosoLm, tipoLampada, quantidade} — soma
    as instâncias equivalentes (mesmo pavimento + tipo base + fluxo + tipo
    de lâmpada)."""
    contagem = {}
    ordem = []
    for it in itens:
        chave = (it[u"pavimento"], it[u"tipoBase"], it[u"fluxoLuminosoLm"], it[u"tipoLampada"])
        if chave not in contagem:
            contagem[chave] = 0
            ordem.append(chave)
        contagem[chave] += 1
    return [
        {
            u"pavimento":       chave[0],
            u"tipoBase":        chave[1],
            u"fluxoLuminosoLm": chave[2],
            u"tipoLampada":     chave[3],
            u"quantidade":      contagem[chave],
        }
        for chave in ordem
    ]


def salvar_cache(itens_agrupados, projeto_dir):
    """Grava os itens de iluminação (já agregados por pavimento/tipo — ver
    agrupar_por_pavimento) na chave 'iluminacao' do firedata.json e envia
    pro site — ver sync.gravar_e_enviar (compartilhado com as demais
    medidas de quantitativo, ver quantitativos_core.py), escopado pela
    estrutura vinculada no plugin (ver sync.config_sync)."""
    estrutura_id = config_sync(projeto_dir).get(u"estruturaId")
    return gravar_e_enviar(u"iluminacao", itens_agrupados, projeto_dir, estruturaId=estrutura_id)
