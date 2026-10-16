# -*- coding: utf-8 -*-
"""
estrutura_param.py — Fire Utils · lib/
Parâmetro compartilhado "Estrutura" (texto, instância) — marca qual
estrutura (das vinculadas ao arquivo Revit ativo — ver
project_link_bridge.py) cada elemento pertence, pra projetos com mais de
uma estrutura modelada no mesmo documento.

Reaproveita o nome "Estrutura" (sem o prefixo "FireUtils -" dos demais
parâmetros deste plugin) porque extintores/calc.py já lê um campo com
esse nome exato há tempos (`_get_texto(elem, u"Estrutura")`, ao lado de
"Ambiente"), sinal de que já é convenção do escritório nas famílias —
criar um segundo parâmetro com outro nome faria duas fontes de verdade
coexistirem na mesma instância. Este módulo só garante que o parâmetro
também existe e está vinculado (instância) nas outras 3 categorias que
precisam dele.

Guarda o NOME da estrutura (não o id/uuid): é um parâmetro nativo do
Revit, visível e editável à mão na paleta Properties — um uuid não serve
pra isso. A resolução nome -> estruturaId acontece na hora de agrupar/
enviar (ver quantitativos_core.py e saidas/calc.py), contra a lista de
estruturas do projeto buscada ao vivo (sync.buscar("listar_estruturas")),
nunca por um cache local.

Categorias cobertas — as mesmas que os quantitativos e a Saída de
Emergência já coletam, mais Dispositivos de Alarme de Incêndio (acionador/
avisador do alarm_insert_core.py, que também precisam ser rastreados por
estrutura mesmo não sendo hoje um quantitativo próprio):
  - Extintores            -> OST_FireProtection      (extintores/params.py)
  - Sinalização            -> OST_SecurityDevices      (sinalizacao/calc.py)
  - Iluminação de emergência -> OST_LightingFixtures  (iluminacao/calc.py)
  - Ambientes (Saída de Emergência) -> OST_Rooms       (saidas/rooms.py)
  - Alarme de incêndio     -> OST_FireAlarmDevices   (alarm_insert_core.py)

Ambientes merecem uma ressalva: num clique de seleção em planta, é comum
acabar selecionando a TAG do ambiente (OST_RoomTags), não o Room em si —
visualmente parecem a mesma coisa, mas são elementos diferentes e só o
Room tem o parâmetro vinculado. atribuir_estrutura resolve isso sozinha
(RoomTag -> seu Room), então tag ou room selecionado dá no mesmo.

Mesmo padrão de criação/vínculo de shared parameter que hidrantes/params.py
já usa (arquivo .txt compartilhado, grupo de definição, CategorySet) — só
que num módulo à parte porque essas 4 categorias não têm relação nenhuma
com hidrantes.
"""

import clr
clr.AddReference("RevitAPI")

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

SHARED_PARAM_FILENAME = u"FireUtils_SharedParams.txt"
GROUP_NAME = u"Fire Utils"

P_ESTRUTURA = u"Estrutura"

CATEGORIAS_ESTRUTURA = [
    BuiltInCategory.OST_FireProtection,
    BuiltInCategory.OST_SecurityDevices,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_Rooms,
    BuiltInCategory.OST_FireAlarmDevices,
]

try:
    from Autodesk.Revit.DB.Architecture import RoomTag as _RoomTag
except ImportError:
    _RoomTag = None


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


def _get_or_create_definition(group, nome):
    for d in group.Definitions:
        if d.Name == nome:
            return d
    if USE_NEW_API:
        opts = ExternalDefinitionCreationOptions(nome, SpecTypeId.String.Text)
    else:
        from Autodesk.Revit.DB import ParameterType
        opts = ExternalDefinitionCreationOptions(nome, ParameterType.Text)
    return group.Definitions.Create(opts)


def _bind_param(doc, definition, categorias_bic):
    cat_set = CategorySet()
    for bic in categorias_bic:
        cat = doc.Settings.Categories.get_Item(bic)
        if cat:
            cat_set.Insert(cat)

    grupo = GroupTypeId.Data if USE_NEW_API else BuiltInParameterGroup.PG_DATA
    binding = doc.Application.Create.NewInstanceBinding(cat_set)

    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name == definition.Name:
            doc.ParameterBindings.ReInsert(definition, binding, grupo)
            return False, u"atualizado"

    doc.ParameterBindings.Insert(definition, binding, grupo)
    return True, u"criado"


def _sp_path(doc, sp_folder=None):
    if sp_folder is None:
        doc_path = doc.PathName
        sp_folder = os.path.dirname(doc_path) if doc_path else os.path.expanduser(u"~")
    return os.path.join(sp_folder, SHARED_PARAM_FILENAME)


def create_estrutura_param(doc, sp_folder=None):
    """Garante que o parâmetro "Estrutura" existe e está
    vinculado (instância) nas 4 categorias acima. Idempotente — chamada
    de novo em qualquer sessão só confirma o binding, não duplica nada.
    Precisa rodar dentro de uma Transaction (ver chamadores — mesmo padrão
    de extintores_params.create_extinguisher_params)."""
    app = doc.Application
    sp_path = _sp_path(doc, sp_folder)
    def_file = _get_or_create_shared_param_file(app, sp_path)
    group = _get_or_create_group(def_file, GROUP_NAME)
    definition = _get_or_create_definition(group, P_ESTRUTURA)

    t = Transaction(doc, u"Fire Utils - Criar parametro Estrutura")
    t.Start()
    try:
        _, status = _bind_param(doc, definition, CATEGORIAS_ESTRUTURA)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return status


def _resolver_room(elem):
    """Uma RoomTag (a etiqueta/texto do ambiente, clicável em planta) não
    é o Room — é outro elemento, da categoria OST_RoomTags, sem o
    parâmetro "Estrutura" vinculado. Clicar na tag pra "selecionar o
    ambiente" é o jeito mais comum de selecionar ambientes em planta, então
    resolve pro Room de verdade antes de ler/gravar o parâmetro, senão a
    seleção parece não ter efeito nenhum."""
    if _RoomTag is not None and isinstance(elem, _RoomTag):
        try:
            return elem.Room or elem
        except Exception:
            return elem
    return elem


def ler_estrutura(elem):
    """Valor bruto (texto, como digitado/atribuído) do parâmetro
    "Estrutura" numa instância — None se o parâmetro não
    existir nela ou estiver vazio. Nunca resolve contra a lista de
    estruturas aqui (ver docstring do módulo) — só lê o texto cru."""
    elem = _resolver_room(elem)
    try:
        p = elem.LookupParameter(P_ESTRUTURA)
    except Exception:
        return None
    if not p or not p.HasValue:
        return None
    valor = p.AsString()
    return valor.strip() if valor else None


def atribuir_estrutura(doc, elementos, nome_estrutura):
    """Escreve `nome_estrutura` no parâmetro "Estrutura" de
    cada elemento em `elementos` que tiver esse parâmetro (criando-o antes,
    se preciso; RoomTag é resolvida pro seu Room — ver _resolver_room) —
    elementos de categorias fora de CATEGORIAS_ESTRUTURA são ignorados
    silenciosamente (não têm o parâmetro, LookupParameter sempre None).
    Retorna (marcados, ignorados)."""
    create_estrutura_param(doc)

    t = Transaction(doc, u"Fire Utils - Atribuir estrutura")
    t.Start()
    marcados = 0
    ignorados = 0
    try:
        for elem in elementos:
            elem = _resolver_room(elem)
            try:
                p = elem.LookupParameter(P_ESTRUTURA)
            except Exception:
                p = None
            if not p or p.IsReadOnly:
                ignorados += 1
                continue
            p.Set(nome_estrutura)
            marcados += 1
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return marcados, ignorados
