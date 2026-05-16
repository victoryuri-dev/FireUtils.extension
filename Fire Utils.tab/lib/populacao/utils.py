# -*- coding: utf-8 -*-
# room_utils.py — Funções utilitárias compartilhadas para ambientes

import os, math
from pyrevit import revit, DB, forms, script
from saidas.get import get_rate, get_ocupacao

doc = revit.doc
uidoc = revit.uidoc
app = doc.Application

def population_calc(area, rate):
    population = area / rate
    return population

# ============================================================
# PARÂMETROS
# ============================================================

SHARED_PARAM_FILE = os.path.join(
    os.path.dirname(__file__),
    "FireUtils_SharedParams.txt"
)

GRUPO_PARAM = "Fire Utils"

PARAMETROS = [
    {
        "nome":     "Setor",
        "tipo":     "texto",
        "descricao": "Setorização de rotas de fuga"
    },
    {
        "nome":     "Grupo",
        "tipo":     "texto",
        "descricao": "Codigo de ocupacao conforme norma estadual vigente"
    },
    {
        "nome":     "Taxa Populacional",
        "tipo":     "texto",
        "descricao": "Taxa populacional conforme norma estadual vigente"
    },
    {
        "nome":     "População",
        "tipo":     "inteiro",
        "descricao": "População calculada conforme norma estadual vigente"
    },
]

def garantir_parametros():

    _garantir_arquivo_shared_params()

    app.SharedParametersFilename = SHARED_PARAM_FILE
    arquivo = app.OpenSharedParameterFile()

    if not arquivo:
        print("Erro: nao foi possivel abrir o arquivo de parametros.")
        return False

    grupo = _get_ou_criar_grupo(arquivo, GRUPO_PARAM)

    for param in PARAMETROS:
        nome = param["nome"]

        tipo      = _get_tipo_parametro(param["tipo"])
        definicao = _get_ou_criar_definicao(grupo, nome, tipo)

        if not definicao:
            print("  [ERRO] Nao foi possivel criar '{}'.".format(nome))
            return False

        ok = _vincular_parametro_ao_projeto(definicao)

        if not ok:
            print("  [ERRO] Nao foi possivel vincular '{}'.".format(nome))
            return False

    return True

# ============================================================
# FUNCAO PRINCIPAL — grava ocupacao, taxa e populacao
# ============================================================

def set_occupancy(rooms, occupancy_value):

    from saidas.get import get_grupo
    from populacao.ocupacao import get_occupancy_use

    rate     = get_rate(occupancy_value)
    grupo    = get_grupo(occupancy_value)
    ocupacao = get_occupancy_use(occupancy_value)

    if not rate:
        print("Ocupacao '{}' nao encontrada na tabela.".format(occupancy_value))
        return False

    with revit.Transaction("Definir Ocupação"):
        for room in rooms:
            # Area
            area = math.ceil( (room.get_Parameter(DB.BuiltInParameter.ROOM_AREA).AsDouble() * 0.092903) )

            # Grava nome do ambiente = uso da ocupacao
            if ocupacao:
                param_nome = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME)
                if param_nome:
                    param_nome.Set(ocupacao)

            # Grava codigo de ocupacao
            param_ocup = room.LookupParameter("Grupo")
            if param_ocup:
                param_ocup.Set(occupancy_value)

            # Grava taxa populacional
            param_taxa = room.LookupParameter("Taxa Populacional")
            if param_taxa and rate:
                param_taxa.Set(rate[1])

            # Calcula e grava populacao
            param_pop = room.LookupParameter("População")
            if param_pop and rate:
                param_pop.Set(population_calc(area, rate[0]))

            elif param_pop and not rate:
                param_pop.Set(0)
                nome_room = room.get_Parameter(
                    DB.BuiltInParameter.ROOM_NAME
                ).AsString()
                print("  [AVISO] '{}': ocupacao {} requer calculo especial.".format(
                    nome_room, occupancy_value))

    return True

# ============================================================
# FUNCOES PARÂMETROS
# ============================================================

def _parametro_existe_no_projeto(nome):
    iterator = doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        if iterator.Key.Name == nome:
            return True
    return False


def _garantir_arquivo_shared_params():
    if not os.path.exists(SHARED_PARAM_FILE):
        with open(SHARED_PARAM_FILE, "w") as f:
            f.write("# Arquivo de parametros compartilhados — Fire Utils\n")
            f.write("# Nao edite este arquivo manualmente.\n")
        print("Arquivo de parametros criado em: {}".format(SHARED_PARAM_FILE))


def _get_tipo_parametro(tipo_str):
    if tipo_str == "texto":
        try:
            return DB.SpecTypeId.String.Text
        except AttributeError:
            return DB.ParameterType.Text

    if tipo_str == "numero":
        try:
            return DB.SpecTypeId.Number
        except AttributeError:
            return DB.ParameterType.Number

    if tipo_str == "inteiro":
        try:
            return DB.SpecTypeId.Int.Integer
        except AttributeError:
            return DB.ParameterType.Integer

    try:
        return DB.SpecTypeId.String.Text
    except AttributeError:
        return DB.ParameterType.Text


def _get_ou_criar_grupo(arquivo, nome_grupo):
    grupo = arquivo.Groups.get_Item(nome_grupo)
    if not grupo:
        grupo = arquivo.Groups.Create(nome_grupo)
        print("  Grupo '{}' criado no arquivo.".format(nome_grupo))
    return grupo


def _get_ou_criar_definicao(grupo, nome_param, tipo_param):
    definicao = grupo.Definitions.get_Item(nome_param)
    if not definicao:
        opcoes = DB.ExternalDefinitionCreationOptions(nome_param, tipo_param)
        opcoes.UserModifiable = True
        definicao = grupo.Definitions.Create(opcoes)
    return definicao


def _vincular_parametro_ao_projeto(definicao):
    try:
        categorias = app.Create.NewCategorySet()
        cat_rooms  = doc.Settings.Categories.get_Item(
            DB.BuiltInCategory.OST_Rooms
        )
        categorias.Insert(cat_rooms)

        binding = app.Create.NewInstanceBinding(categorias)

        try:
            grupo_revit = DB.GroupTypeId.Data
        except AttributeError:
            grupo_revit = DB.BuiltInParameterGroup.PG_DATA

        with revit.Transaction("Criar Parametro Fire Utils"):
            doc.ParameterBindings.Insert(definicao, binding, grupo_revit)

        return True

    except Exception as e:
        print("  Erro ao vincular: {}".format(str(e)))
        return False