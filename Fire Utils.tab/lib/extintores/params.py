# -*- coding: utf-8 -*-
"""
extintores/params.py
Cria e vincula os Shared Parameters de instância que ainda faltam nas
famílias de extintor (Estrutura, Ambiente — usados para localizar a peça).

"Tipo", "Formato", "Capacidade Extintora" e "Carga" NÃO são criados aqui:
já existem nas famílias de extintor (parâmetros de Tipo, definidos dentro
da própria família). São apenas lidos em extintores/calc.py — na instância
e, se não houver lá, no Symbol (tipo) da família.

Categoria: Proteção contra Incêndio (OST_FireProtection), que é como as
famílias de extintor são classificadas neste escritório.

A presença + preenchimento de "Capacidade Extintora" (instância ou tipo)
em um elemento dessa categoria é o critério usado para identificá-lo como
extintor (ver extintores/calc.py).
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

GROUP_NAME = "Fire Utils – Extintores"

CATEGORIAS_EXTINTOR = [
    BuiltInCategory.OST_FireProtection,
]

# Parâmetro usado como critério de identificação (categoria + preenchido).
# Já existe nas famílias de extintor como parâmetro de Tipo — não é criado
# por este módulo, apenas lido (ver extintores/calc.py).
PARAM_CAPACIDADE = u"Capacidade Extintora"

# Nomes que uma versão anterior deste módulo chegou a criar como parâmetro
# de PROJETO (instância) por engano — precisam ser removidos se existirem,
# senão "sombreiam" (em branco/zero) o parâmetro de Tipo real da família,
# que tem o mesmo nome.
NOMES_OBSOLETOS = [u"Tipo", u"Formato", PARAM_CAPACIDADE, u"Carga"]

# Únicos parâmetros que este módulo cria/vincula — os demais campos pedidos
# pelo usuário (Tipo, Formato, Capacidade Extintora, Carga) já existem nas
# famílias de extintor deste escritório.
PARAMS_CONFIG = [
    {
        "nome":        u"Estrutura",
        "tipo_novo":   "Text",
        "tipo_legado": "Text",
        "categorias":  CATEGORIAS_EXTINTOR,
        "instancia":   True,
        "grupo_ui":    "PG_DATA",
    },
    {
        "nome":        u"Ambiente",
        "tipo_novo":   "Text",
        "tipo_legado": "Text",
        "categorias":  CATEGORIAS_EXTINTOR,
        "instancia":   True,
        "grupo_ui":    "PG_DATA",
    },
]


# ---------------------------------------------------------------------------
# Helpers (idênticos ao padrão de hidrantes/params.py)
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


def _remover_bindings_obsoletos(doc, nomes):
    """Remove vínculos de parâmetro de projeto com esses nomes, se existirem
    (ver NOMES_OBSOLETOS)."""
    removidos = []
    chaves_para_remover = []
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name in nomes:
            chaves_para_remover.append(it.Key)

    for chave in chaves_para_remover:
        doc.ParameterBindings.Remove(chave)
        removidos.append(chave.Name)

    return removidos


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def create_extinguisher_params(doc, sp_folder=None):
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
    with Transaction(doc, "FireUtils - Criar Parametros de Extintor") as t:
        t.Start()

        removidos = _remover_bindings_obsoletos(doc, NOMES_OBSOLETOS)
        for nome in removidos:
            log.append((nome, "removido (obsoleto)"))

        for cfg, defn in definicoes:
            ok, status = _bind_param(
                doc, defn, cfg["categorias"], cfg["instancia"], cfg["grupo_ui"]
            )
            log.append((cfg["nome"], status))
        t.Commit()

    return log
