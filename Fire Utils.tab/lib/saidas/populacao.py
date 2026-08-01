# -*- coding: utf-8 -*-
# saidas/populacao.py — Fire Utils
# Utilitários de população: parâmetros compartilhados Revit + gravação de ocupação.

import os
import math
from pyrevit import revit, DB, forms, script

doc   = revit.doc
uidoc = revit.uidoc
app   = doc.Application


def population_calc(area, rate):
    return area / rate


# ============================================================
# PARÂMETROS COMPARTILHADOS
# ============================================================

SHARED_PARAM_FILE = os.path.join(
    os.path.dirname(__file__),
    u"FireUtils_SharedParams.txt"
)

GRUPO_PARAM = u"Fire Utils"

PARAMETROS = [
    {
        u"nome":      u"Setor",
        u"tipo":      u"texto",
        u"descricao": u"Setorização de rotas de fuga",
    },
    {
        u"nome":      u"Grupo",
        u"tipo":      u"texto",
        u"descricao": u"Código de ocupação conforme norma estadual vigente",
    },
    {
        u"nome":      u"Taxa Populacional",
        u"tipo":      u"texto",
        u"descricao": u"Taxa populacional conforme norma estadual vigente",
    },
    {
        u"nome":      u"População",
        u"tipo":      u"inteiro",
        u"descricao": u"População calculada conforme norma estadual vigente",
    },
]


def garantir_parametros():
    """Garante que os parâmetros Fire Utils existem no projeto Revit. Retorna bool."""
    _garantir_arquivo_shared_params()

    app.SharedParametersFilename = SHARED_PARAM_FILE
    arquivo = app.OpenSharedParameterFile()

    if not arquivo:
        print(u"Erro: não foi possível abrir o arquivo de parâmetros.")
        return False

    grupo = _get_ou_criar_grupo(arquivo, GRUPO_PARAM)

    for param in PARAMETROS:
        nome      = param[u"nome"]
        tipo      = _get_tipo_parametro(param[u"tipo"])
        definicao = _get_ou_criar_definicao(grupo, nome, tipo)

        if not definicao:
            print(u"  [ERRO] Não foi possível criar '{}'.".format(nome))
            return False

        ok = _vincular_parametro_ao_projeto(definicao)
        if not ok:
            print(u"  [ERRO] Não foi possível vincular '{}'.".format(nome))
            return False

    return True


# ============================================================
# FUNÇÃO PRINCIPAL — grava ocupação, taxa e população
# ============================================================

def set_occupancy(rooms, occupancy_value, estado):
    """
    Grava ocupação, taxa populacional e população nos ambientes informados.

    estado : dict retornado por normas.get_estado(). Se fornecido, os dados
             são lidos de estado["tabela"] e estado["ocupacoes"].
             Se None, usa o banco fixo IT 11 CBMSP (fallback).
    """
    # ------------------------------------------------------------------
    # Resolver taxa, grupo e uso a partir do estado
    # ------------------------------------------------------------------
    if not estado or u"tabela" not in estado:
        print(u"set_occupancy: estado com 'tabela' é obrigatório.")
        return False

    entry = estado[u"tabela"].get(occupancy_value)
    if not entry:
        print(u"Ocupação '{}' não encontrada na tabela do estado.".format(occupancy_value))
        return False

    taxa_a     = entry.get(u"A")
    taxa_obs   = entry.get(u"obs", u"")
    ocup_entry = estado.get(u"ocupacoes", {}).get(occupancy_value, {})
    ocupacao   = ocup_entry.get(u"uso", u"")

    # ------------------------------------------------------------------
    # Gravar parâmetros nos ambientes
    # ------------------------------------------------------------------
    with revit.Transaction(u"Definir Ocupação"):
        for room in rooms:
            area = math.ceil(
                room.get_Parameter(DB.BuiltInParameter.ROOM_AREA).AsDouble() * 0.092903
            )
            nome_room = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or u""

            # Nome do ambiente → uso da ocupação
            if ocupacao:
                param_nome = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME)
                if param_nome:
                    param_nome.Set(ocupacao)

            # Código de ocupação
            param_ocup = room.LookupParameter(u"Grupo")
            if param_ocup:
                param_ocup.Set(occupancy_value)

            # Taxa populacional (texto descritivo)
            param_taxa = room.LookupParameter(u"Taxa Populacional")
            if param_taxa and taxa_obs:
                param_taxa.Set(taxa_obs)

            # População calculada
            param_pop = room.LookupParameter(u"População")
            if param_pop:
                if taxa_a and taxa_a > 0:
                    param_pop.Set(int(population_calc(area, float(taxa_a))))
                else:
                    # A = None: cálculo não é por área (vagas, leitos, etc.)
                    param_pop.Set(0)
                    formula = taxa_obs if taxa_obs else u"ver norma"
                    print(u"  [POP MANUAL] '{}': {} — informe o valor no parâmetro 'População'.".format(
                        nome_room, formula
                    ))

    return True


# ============================================================
# FUNÇÕES AUXILIARES — parâmetros compartilhados
# ============================================================

def _parametro_existe_no_projeto(nome):
    iterator = doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        if iterator.Key.Name == nome:
            return True
    return False


def _garantir_arquivo_shared_params():
    if not os.path.exists(SHARED_PARAM_FILE):
        with open(SHARED_PARAM_FILE, u"w") as f:
            f.write(u"# Arquivo de parâmetros compartilhados — Fire Utils\n")
            f.write(u"# Não edite este arquivo manualmente.\n")
        print(u"Arquivo de parâmetros criado em: {}".format(SHARED_PARAM_FILE))


def _get_tipo_parametro(tipo_str):
    if tipo_str == u"texto":
        try:
            return DB.SpecTypeId.String.Text
        except AttributeError:
            return DB.ParameterType.Text

    if tipo_str == u"numero":
        try:
            return DB.SpecTypeId.Number
        except AttributeError:
            return DB.ParameterType.Number

    if tipo_str == u"inteiro":
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
        print(u"  Grupo '{}' criado no arquivo.".format(nome_grupo))
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
        cat_rooms  = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Rooms)
        categorias.Insert(cat_rooms)

        binding = app.Create.NewInstanceBinding(categorias)

        try:
            grupo_revit = DB.GroupTypeId.Data
        except AttributeError:
            grupo_revit = DB.BuiltInParameterGroup.PG_DATA

        with revit.Transaction(u"Criar Parâmetro Fire Utils"):
            doc.ParameterBindings.Insert(definicao, binding, grupo_revit)

        return True

    except Exception as e:
        print(u"  Erro ao vincular: {}".format(str(e)))
        return False
