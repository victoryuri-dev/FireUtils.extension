# -*- coding: utf-8 -*-
"""
iluminacao/params.py
Cria e vincula os Shared Parameters de TIPO que ainda faltam nas famílias
de equipamento de aclaramento (iluminação de emergência): "Tipo Base
Iluminação", "Fluxo Luminoso Nominal" e "Tipo de Lâmpada".

Categoria: Luminárias (OST_LightingFixtures) — como as famílias de
iluminação de emergência (luminária de LEDs, bloco autônomo) são
classificadas neste escritório, junto com toda luminária comum do projeto.

A presença + preenchimento de "Tipo Base Iluminação" (na instância ou no
Tipo) em um elemento dessa categoria é o critério usado para identificá-lo
como equipamento de aclaramento do Fire Utils — luminárias comuns do
projeto (iluminação normal, não de emergência) não têm esse parâmetro
preenchido e são ignoradas (ver iluminacao/calc.py).

Valores aceitos em "Tipo Base Iluminação" (texto livre; o site casa por
chave OU label, ignorando acento/caixa — ver resolverImportacaoIluminacao
em IluminacaoPage.jsx):
  - "Luminária de Emergência 30 LEDs" (ou "luminaria_30leds")
  - "Bloco de Iluminação de Emergência" (ou "bloco_emergencia")

São parâmetros de TIPO (não de instância): fluxo luminoso e tipo de
lâmpada são propriedades do modelo/catálogo do equipamento, não variam
entre instâncias da mesma família/tipo.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    Transaction,
    ExternalDefinitionCreationOptions,
    BuiltInCategory,
    CategorySet,
)

import os

try:
    from Autodesk.Revit.DB import SpecTypeId, GroupTypeId
    USE_NEW_API = True
except ImportError:
    from Autodesk.Revit.DB import BuiltInParameterGroup
    USE_NEW_API = False

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
SHARED_PARAM_FILENAME = "FireUtils_SharedParams.txt"

GROUP_NAME = "Fire Utils – Iluminação de Emergência"

CATEGORIAS_ILUMINACAO = [
    BuiltInCategory.OST_LightingFixtures,
]

# Parâmetro usado como critério de identificação (categoria + preenchido).
PARAM_TIPO_BASE = u"Tipo Base Iluminação"
PARAM_FLUXO     = u"Fluxo Luminoso Nominal"
PARAM_LAMPADA   = u"Tipo de Lâmpada"

PARAMS_CONFIG = [
    {
        "nome":        PARAM_TIPO_BASE,
        "tipo_novo":   "Text",
        "tipo_legado": "Text",
        "categorias":  CATEGORIAS_ILUMINACAO,
        "instancia":   False,
        "grupo_ui":    "PG_DATA",
    },
    {
        "nome":        PARAM_FLUXO,
        "tipo_novo":   "Number",
        "tipo_legado": "Number",
        "categorias":  CATEGORIAS_ILUMINACAO,
        "instancia":   False,
        "grupo_ui":    "PG_DATA",
    },
    {
        "nome":        PARAM_LAMPADA,
        "tipo_novo":   "Text",
        "tipo_legado": "Text",
        "categorias":  CATEGORIAS_ILUMINACAO,
        "instancia":   False,
        "grupo_ui":    "PG_DATA",
    },
]


# ---------------------------------------------------------------------------
# Helpers (idênticos ao padrão de extintores/params.py)
# ---------------------------------------------------------------------------
def _get_or_create_shared_param_file(app, sp_path):
    if not os.path.exists(sp_path):
        with open(sp_path, "w") as f:
            f.write("")
    app.SharedParametersFilename = sp_path
    return app.OpenSharedParameterFile()


def _get_or_create_group(def_file, group_name):
    for g in def_file.Groups:
        if g.Name == group_name:
            return g
    return def_file.Groups.Create(group_name)


def _get_or_create_definition(group, nome, tipo_novo, tipo_legado):
    for d in group.Definitions:
        if d.Name == nome:
            return d

    if USE_NEW_API:
        spec_map = {
            "Text":   SpecTypeId.String.Text,
            "Number": SpecTypeId.Number,
        }
        opts = ExternalDefinitionCreationOptions(nome, spec_map[tipo_novo])
    else:
        from Autodesk.Revit.DB import ParameterType
        pt_map = {
            "Text":   ParameterType.Text,
            "Number": ParameterType.Number,
        }
        opts = ExternalDefinitionCreationOptions(nome, pt_map[tipo_legado])

    return group.Definitions.Create(opts)


def _get_group_type(grupo_ui_str):
    if USE_NEW_API:
        return GroupTypeId.Data
    else:
        return BuiltInParameterGroup.PG_DATA


def _bind_param(doc, definition, categorias_bic, instancia, grupo_ui_str):
    cat_set = CategorySet()
    for bic in categorias_bic:
        cat = doc.Settings.Categories.get_Item(bic)
        if cat:
            cat_set.Insert(cat)

    grupo = _get_group_type(grupo_ui_str)

    if instancia:
        binding = doc.Application.Create.NewInstanceBinding(cat_set)
    else:
        binding = doc.Application.Create.NewTypeBinding(cat_set)

    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name == definition.Name:
            doc.ParameterBindings.ReInsert(definition, binding, grupo)
            return False, "atualizado"

    doc.ParameterBindings.Insert(definition, binding, grupo)
    return True, "criado"


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def create_iluminacao_params(doc, sp_folder=None):
    app = doc.Application

    if sp_folder is None:
        doc_path = doc.PathName
        if doc_path:
            sp_folder = os.path.dirname(doc_path)
        else:
            import tempfile
            sp_folder = tempfile.gettempdir()

    sp_path  = os.path.join(sp_folder, SHARED_PARAM_FILENAME)
    def_file = _get_or_create_shared_param_file(app, sp_path)
    group    = _get_or_create_group(def_file, GROUP_NAME)

    definicoes = []
    for cfg in PARAMS_CONFIG:
        defn = _get_or_create_definition(
            group, cfg["nome"], cfg["tipo_novo"], cfg["tipo_legado"]
        )
        definicoes.append((cfg, defn))

    log = []
    with Transaction(doc, "FireUtils - Criar Parametros de Iluminacao") as t:
        t.Start()
        for cfg, defn in definicoes:
            ok, status = _bind_param(
                doc, defn, cfg["categorias"], cfg["instancia"], cfg["grupo_ui"]
            )
            log.append((cfg["nome"], status))
        t.Commit()

    return log
