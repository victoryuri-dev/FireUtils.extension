# -*- coding: utf-8 -*-
"""
material_conexao.py — Fire Utils · lib/hidrantes/

Material da tubulação, escolhido na dockpane POR TRECHO — mais
especificamente por (etapa, tipo de tubo detectado no Revit): uma mesma
etapa (RTI-Bomba, Bomba-Ponto A, ...) pode ter mais de um PipeType
diferente ao longo do seu comprimento (troca de material no meio do
trecho), e cada um precisa da própria escolha. Guardado no Project
Information do projeto (JSON no parâmetro "FireUtils - Material e
Conexao" — nome mantido por compatibilidade com projetos já gravados),
no mesmo molde de succao.py.

O material decide o coeficiente C de Hazen-Williams do trecho. Não dá
para inferi-lo da família do Revit: a correspondência de cada PipeType
com a lista de materiais da norma é escolha do usuário.

O antigo "sistema de conexão" (BSP roscado x Grooved ranhurado) foi
removido: o motor usa uma única tabela de Leq para cotovelo/tê. Projetos
com escolha antiga gravada continuam válidos — a chave "sistema" é
ignorada ao ler.

Formato salvo:
    {"t1": {"<pipe_type_id>": {"material": "galvanizado"|None}, ...},
     "t2": {...}, "t3": {...}, "t4": {...}}
"<pipe_type_id>" é o ElementId (int, como string) do PipeType do Revit —
"none" pro grupo sem PipeType resolvível (fitting na ponta do trecho sem
nenhum Pipe vizinho no mesmo trecho; raro, e cai no padrão: material
None usa o C padrão do perfil).
"""

from __future__ import absolute_import

import json

PARAM = u"FireUtils - Material e Conexao"

ETAPAS_VALIDAS = (u"t1", u"t2", u"t3", u"t4")

# Mesmas chaves curtas que hazen_c usa no perfil normativo (ver
# ALIAS_MATERIAL_TUBULACAO em perfil.ts, ETOS.FireUtils) — evita qualquer
# tradução de chave entre o plugin e o motor.
MATERIAIS_VALIDOS = (
    u"ff_sem_revest", u"aco_preto_seco", u"aco_preto_molhado", u"galvanizado",
    u"plastico", u"ff_revest_cimento", u"cobre",
)

CHAVE_SEM_PIPE_TYPE = u"none"


def default_dados():
    return dict((etapa, {}) for etapa in ETAPAS_VALIDAS)


def chave_pipe_type(pipe_type_id):
    """Chave de string estável pro dict salvo — mesma função usada ao
    salvar (dockpane) e ao ler (get_material), pra nunca divergir."""
    if pipe_type_id is None:
        return CHAVE_SEM_PIPE_TYPE
    try:
        return u"{}".format(int(pipe_type_id))
    except (TypeError, ValueError):
        return CHAVE_SEM_PIPE_TYPE


def normalizar_dados(dados):
    """Converte um dict cru (JSON salvo, ou vindo da dockpane) pro formato
    canônico. Entradas inválidas (etapa desconhecida, material fora da
    lista) são descartadas silenciosamente — nunca gravam um
    valor que o motor não reconheceria."""
    out = default_dados()
    if not isinstance(dados, dict):
        return out
    for etapa, por_pipe_type in dados.items():
        if etapa not in ETAPAS_VALIDAS or not isinstance(por_pipe_type, dict):
            continue
        for chave, escolha in por_pipe_type.items():
            if not isinstance(escolha, dict):
                continue
            material = escolha.get(u"material")
            if material is not None and material not in MATERIAIS_VALIDOS:
                continue
            out[etapa][u"{}".format(chave)] = {u"material": material}
    return out


def get_material(dados, etapa, pipe_type_id):
    """Material configurado pra esse (etapa, pipe_type), ou None (usa o C
    padrão do perfil normativo) quando não há escolha salva pra essa
    combinação — um trecho nunca configurado não muda resultado nenhum."""
    por_pipe_type = (dados or {}).get(etapa) or {}
    escolha = por_pipe_type.get(chave_pipe_type(pipe_type_id))
    if not escolha:
        return None
    return escolha.get(u"material")


def load_dados(doc):
    param = doc.ProjectInformation.LookupParameter(PARAM)
    if not param:
        return default_dados()

    raw = param.AsString()
    if not raw or not raw.strip():
        return default_dados()

    try:
        dados = json.loads(raw)
    except Exception:
        return default_dados()

    return normalizar_dados(dados)


def save_dados(doc, dados):
    """
    Grava o material por (etapa, pipe_type) no projeto (JSON no
    Project Information). Abre e fecha a própria Transaction.
    """
    from Autodesk.Revit.DB import Transaction

    param = doc.ProjectInformation.LookupParameter(PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parâmetro '{}' não encontrado no projeto.".format(PARAM)

    normalizados = normalizar_dados(dados)
    with Transaction(doc, u"FireUtils - Material da tubulação por trecho") as t:
        t.Start()
        param.Set(json.dumps(normalizados, ensure_ascii=True, sort_keys=True))
        t.Commit()
    return True, u"Material salvo no projeto."
