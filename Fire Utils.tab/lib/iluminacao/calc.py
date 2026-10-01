# -*- coding: utf-8 -*-
"""
iluminacao/calc.py
Coleta instâncias de equipamento de aclaramento (iluminação de emergência)
no modelo e grava o quantitativo na chave 'iluminacao' do firedata.json
(arquivo único, ao lado do .rvt).

"Tipo de Luminaria", "Fluxo Luminoso" e "Lampada" já vêm embutidos nas
famílias de iluminação de emergência deste escritório (parâmetros de Tipo,
seção "Dados") — igual ao fluxo de Sinalização, nenhum parâmetro precisa
ser criado/vinculado aqui.

Categoria: Luminárias (OST_LightingFixtures) — mesma categoria de qualquer
luminária comum do projeto. Uma instância é considerada equipamento de
aclaramento do Fire Utils quando "Tipo de Luminaria" tem um dos dois
valores reconhecidos (ver MAPA_TIPO_LUMINARIA); qualquer outro valor (ou
vazio) é ignorado — é o que distingue um bloco/luminária de emergência de
uma luminária decorativa/funcional qualquer que também esteja na categoria.

  - "SLIM"      -> luminária de emergência 30 LEDs (tipoBase luminaria_30leds)
  - "2 FAROIS"  -> bloco de iluminação de emergência (tipoBase bloco_emergencia)

"Fluxo Luminoso" vem com a unidade embutida no texto (ex.: "100 lm") — só o
número é extraído, pra bater com o fluxoLuminosoLm dos presets do catálogo
no site (ver PRESETS_EQUIPAMENTO em normas/MA/iluminacao.js). "Lampada" é
copiado como texto livre.

Granularidade até pavimento (sem ambiente, como o dimensionamento no site)
— o quantitativo já sai agregado por pavimento + tipo base + fluxo +
lâmpada, somando todas as instâncias equivalentes do modelo (ver
agrupar_por_pavimento).
"""

import re

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInCategory, ElementId, StorageType,
)

from sync import gravar_e_enviar, config_sync

CATEGORIA_ILUMINACAO = BuiltInCategory.OST_LightingFixtures

# Nomes de parâmetro tentados nessa ordem — cobre a variante sem acento
# usada nas famílias atuais (ver prints do usuário) e a acentuada, caso
# outra família do escritório use o nome "correto".
PARAM_TIPO_LUMINARIA = [u"Tipo de Luminaria", u"Tipo de Luminária"]
PARAM_FLUXO          = [u"Fluxo Luminoso"]
PARAM_LAMPADA         = [u"Lampada", u"Lâmpada"]

# "Tipo de Luminaria" -> tipoBase interno (ver EQUIPAMENTOS_ACLARAMENTO em
# normas/MA/iluminacao.js, site). Comparação sem acento/caixa (ver _norm).
MAPA_TIPO_LUMINARIA = {
    u"slim":      u"luminaria_30leds",
    u"2 farois":  u"bloco_emergencia",
    u"2 faróis":  u"bloco_emergencia",
}


def _get_id_value(eid):
    """ElementId.IntegerValue foi removido no Revit 2024+ (agora .Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _norm(texto):
    return (texto or u"").strip().lower()


def _lookup_tipo(elem, nomes_param):
    """Os três parâmetros são de TIPO — procura primeiro no Symbol (Tipo) da
    instância; cai pra instância só por robustez (mesmo padrão de
    sinalizacao/calc.py._lookup_tipo), embora não deva haver override de
    instância num parâmetro de tipo. Tenta cada nome candidato em ordem
    (ver PARAM_TIPO_LUMINARIA/PARAM_FLUXO/PARAM_LAMPADA)."""
    simbolo = getattr(elem, "Symbol", None)
    for nome in nomes_param:
        if simbolo:
            param = simbolo.LookupParameter(nome)
            if param and param.HasValue:
                return param
        param = elem.LookupParameter(nome)
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


def _get_texto(elem, nomes_param):
    param = _lookup_tipo(elem, nomes_param)
    if not param:
        return u""
    return _texto_exibido(param)


def _fluxo_numero(texto):
    """Extrai só o número de um texto como "100 lm"/"2200 lm" — descarta a
    unidade. Formata sem casas decimais quando o valor é inteiro (caso
    comum em fluxo luminoso), pra bater exatamente com o texto usado nos
    presets do catálogo no site (ex.: "100", não "100.0")."""
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", texto or u"")
    if not m:
        return u""
    valor = float(m.group().replace(u",", u"."))
    if valor == int(valor):
        return unicode(int(valor))
    return unicode(valor)


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
    categoria = doc.Settings.Categories.get_Item(CATEGORIA_ILUMINACAO)
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

        tipo_base = MAPA_TIPO_LUMINARIA.get(_norm(_get_texto(elem, PARAM_TIPO_LUMINARIA)))
        if not tipo_base:
            continue

        itens.append({
            u"pavimento":       _get_pavimento(doc, elem),
            u"tipoBase":        tipo_base,
            u"fluxoLuminosoLm": _fluxo_numero(_get_texto(elem, PARAM_FLUXO)),
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
