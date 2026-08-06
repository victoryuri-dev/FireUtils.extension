# -*- coding: utf-8 -*-
"""
hydrant_params.py
Cria e vincula os parâmetros necessários para o dimensionamento de hidrantes:

Project Information:
  - FireUtils - Tipo de Sistema de Hidrante  (texto)
  - FireUtils - Sistema Personalizado        (texto/JSON com valores custom)

Shared Parameters (categorias alvo definidas abaixo):
  Tubulações:
    - FireUtils - Coeficiente C               (número)

  Acessórios de tubulação (família de esguicho/hidrante):
    - FireUtils - ID Hidrante                 (texto)
    - FireUtils - Pressao                     (número)   [mca]
    - FireUtils - Vazao                       (número)   [m³/min]
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

# Compatibilidade Revit 2022+
# BuiltInParameterGroup foi removido no Revit 2022 — substituído por GroupTypeId
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

GROUP_NAME  = "Fire Utils – Hidrantes"

# Parâmetros e suas configurações
#   (nome, tipo_spec_novo, tipo_param_legado, categoria_builtin_list)
PARAMS_CONFIG = [
    # Tubulações
    {
        "nome":       u"FireUtils - Coeficiente C",
        "tipo_novo":  "Number",
        "tipo_legado": "Number",
        "categorias": [BuiltInCategory.OST_PipeCurves],
        "instancia":  False,
        "grupo_ui":   "PG_DATA",
    },
    {
        "nome":       u"FireUtils - Pressao",
        "tipo_novo":  "Number",
        "tipo_legado": "Number",
        "categorias": [BuiltInCategory.OST_PipeAccessory],
        "instancia":  True,
        "grupo_ui":   "PG_DATA",
    },
    {
        "nome":       u"FireUtils - Vazao",
        "tipo_novo":  "Number",
        "tipo_legado": "Number",
        "categorias": [BuiltInCategory.OST_PipeAccessory],
        "instancia":  True,
        "grupo_ui":   "PG_DATA",
    },
    # Parâmetros de mapeamento de trechos
    # Aplicados a tubos, acessórios e conexões de tubo
    {
        "nome":       u"FireUtils - Trecho",
        "tipo_novo":  "Text",
        "tipo_legado": "Text",
        "categorias": [
            BuiltInCategory.OST_PipeCurves,
            BuiltInCategory.OST_PipeFitting,
            BuiltInCategory.OST_PipeAccessory,
        ],
        "instancia":  True,
        "grupo_ui":   "PG_DATA",
    },
    {
        "nome":       u"FireUtils - Identificador",
        "tipo_novo":  "Text",
        "tipo_legado": "Text",
        "categorias": [
            BuiltInCategory.OST_PipeCurves,
            BuiltInCategory.OST_PipeFitting,
            BuiltInCategory.OST_PipeAccessory,
        ],
        "instancia":  True,
        "grupo_ui":   "PG_DATA",
    },
]

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"

# Guarda, em JSON, os valores personalizados do sistema (quando o usuário opta
# por valores fora da Tabela 2). Fica no próprio projeto para permitir
# reclassificar quantas vezes for preciso sem redigitar.
PROJECT_INFO_CUSTOM_PARAM = u"FireUtils - Sistema Personalizado"

PROJECT_INFO_PARAMS = [PROJECT_INFO_PARAM, PROJECT_INFO_CUSTOM_PARAM]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_or_create_shared_param_file(app, sp_path):
    """Garante que o arquivo de shared parameters está configurado."""
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
    """Retorna definição existente ou cria uma nova."""
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
    """
    Vincula a definição ao documento.
    Se já existir mas com binding incorreto (ex: tipo errado), recria.
    """
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

    # Verifica se já existe
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name == definition.Name:
            # Já existe — usa ReInsert para atualizar o binding
            doc.ParameterBindings.ReInsert(definition, binding, grupo)
            return False, "atualizado"

    doc.ParameterBindings.Insert(definition, binding, grupo)
    return True, "criado"


def _create_project_info_definition(group, nome=None):
    """Garante que a definição do parâmetro de ProjectInfo existe no arquivo."""
    return _get_or_create_definition(group, nome or PROJECT_INFO_PARAM, "Text", "Text")


def _bind_project_info_param(doc, defn):
    """Vincula um parâmetro de texto à categoria ProjectInformation."""
    # Já vinculado?
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name == defn.Name:
            return False, "já existe"

    cat_set = CategorySet()
    pi_cat  = doc.Settings.Categories.get_Item(
        BuiltInCategory.OST_ProjectInformation
    )
    if pi_cat:
        cat_set.Insert(pi_cat)

    if USE_NEW_API:
        grupo = GroupTypeId.Data
    else:
        grupo = BuiltInParameterGroup.PG_DATA

    binding = doc.Application.Create.NewInstanceBinding(cat_set)
    doc.ParameterBindings.Insert(defn, binding, grupo)
    return True, "criado"


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def create_hydrant_params(doc, sp_folder=None):
    app = doc.Application

    # Resolve caminho do arquivo de shared parameters
    if sp_folder is None:
        doc_path = doc.PathName
        if doc_path:
            sp_folder = os.path.dirname(doc_path)
        else:
            import tempfile
            sp_folder = tempfile.gettempdir()

    # --- Etapa 1: operações de arquivo (sem transação) ---
    sp_path  = os.path.join(sp_folder, SHARED_PARAM_FILENAME)
    def_file = _get_or_create_shared_param_file(app, sp_path)
    group    = _get_or_create_group(def_file, GROUP_NAME)

    # Garante que todas as definições existem no arquivo
    definicoes = []
    for cfg in PARAMS_CONFIG:
        defn = _get_or_create_definition(
            group, cfg["nome"], cfg["tipo_novo"], cfg["tipo_legado"]
        )
        definicoes.append((cfg, defn))

    pi_defns = [
        (nome, _create_project_info_definition(group, nome))
        for nome in PROJECT_INFO_PARAMS
    ]

    # --- Etapa 2: vinculação ao documento (dentro de transação) ---
    log = []

    with Transaction(doc, "FireUtils - Criar Parametros de Hidrante") as t:
        t.Start()

        for cfg, defn in definicoes:
            ok, status = _bind_param(
                doc, defn, cfg["categorias"], cfg["instancia"], cfg["grupo_ui"]
            )
            log.append((cfg["nome"], status))

        for nome, pi_defn in pi_defns:
            ok, status = _bind_project_info_param(doc, pi_defn)
            log.append((nome, status))

        t.Commit()

    return log