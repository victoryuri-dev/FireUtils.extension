# -*- coding: utf-8 -*-
"""
material_conexao.py — Fire Utils · lib/hidrantes/

Material da tubulação e sistema de conexão (BSP roscado x Grooved
ranhurado), escolhidos na dockpane POR TRECHO — mais especificamente por
(etapa, tipo de tubo detectado no Revit): uma mesma etapa (RTI-Bomba,
Bomba-Ponto A, ...) pode ter mais de um PipeType diferente ao longo do
seu comprimento (troca de material no meio do trecho), e cada um precisa
da própria escolha. Guardado no Project Information do projeto (JSON no
parâmetro "FireUtils - Material e Conexao"), no mesmo molde de
succao.py. Substitui sistema_conexao.py: o sistema de conexão passou a
ser escolhido JUNTO do material, por (etapa, tipo de tubo), não mais só
por diâmetro isolado.

Por que isso existe:
- O material decide o coeficiente C de Hazen-Williams do trecho. Antes
  desta funcionalidade, o motor de cálculo sempre assumia "galvanizado"
  pra rede inteira, não importava o material real (ver dimensionar.ts,
  repositório ETOS.FireUtils) — o seletor de material que já existia no
  site nunca chegava no cálculo.
- Cotovelo/tê roscado e ranhurado têm Leq bem diferente pro mesmo
  diâmetro, e nenhum dos dois (material, sistema de conexão) dá pra
  inferir sozinho da família do Revit: só a FORMA da conexão (PartType)
  e a TROCA de tipo de tubo (PipeType) são nativas; a correspondência de
  cada uma com a lista de materiais/sistemas da norma é escolha do
  usuário.

Formato salvo:
    {"t1": {"<pipe_type_id>": {"material": "galvanizado"|None, "sistema": "bsp"|"grooved"}, ...},
     "t2": {...}, "t3": {...}, "t4": {...}}
"<pipe_type_id>" é o ElementId (int, como string) do PipeType do Revit —
"none" pro grupo sem PipeType resolvível (fitting na ponta do trecho sem
nenhum Pipe vizinho no mesmo trecho; raro, e cai no padrão sem precisar
de configuração: material None usa o C padrão do perfil, sistema "bsp"
é o mesmo default de antes desta funcionalidade).
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

SISTEMAS_VALIDOS = (u"bsp", u"grooved")
SISTEMA_PADRAO = u"bsp"
CHAVE_SEM_PIPE_TYPE = u"none"


def default_dados():
    return dict((etapa, {}) for etapa in ETAPAS_VALIDAS)


def chave_pipe_type(pipe_type_id):
    """Chave de string estável pro dict salvo — mesma função usada ao
    salvar (dockpane) e ao ler (get_escolha), pra nunca divergir."""
    if pipe_type_id is None:
        return CHAVE_SEM_PIPE_TYPE
    try:
        return u"{}".format(int(pipe_type_id))
    except (TypeError, ValueError):
        return CHAVE_SEM_PIPE_TYPE


def normalizar_dados(dados):
    """Converte um dict cru (JSON salvo, ou vindo da dockpane) pro formato
    canônico. Entradas inválidas (etapa desconhecida, material/sistema
    fora da lista) são descartadas silenciosamente — nunca gravam um
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
            sistema = escolha.get(u"sistema") or SISTEMA_PADRAO
            if sistema not in SISTEMAS_VALIDOS:
                continue
            out[etapa][u"{}".format(chave)] = {u"material": material, u"sistema": sistema}
    return out


def get_escolha(dados, etapa, pipe_type_id):
    """(material, sistema) configurados pra esse (etapa, pipe_type).

    material é None (usa o C padrão do perfil normativo) e sistema é
    SISTEMA_PADRAO ("bsp") quando não há escolha salva pra essa
    combinação — mesmo comportamento de antes desta funcionalidade
    existir, então um trecho nunca configurado não muda resultado
    nenhum."""
    por_pipe_type = (dados or {}).get(etapa) or {}
    escolha = por_pipe_type.get(chave_pipe_type(pipe_type_id))
    if not escolha:
        return None, SISTEMA_PADRAO
    return escolha.get(u"material"), (escolha.get(u"sistema") or SISTEMA_PADRAO)


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
    Grava material/sistema por (etapa, pipe_type) no projeto (JSON no
    Project Information). Abre e fecha a própria Transaction.
    """
    from Autodesk.Revit.DB import Transaction

    param = doc.ProjectInformation.LookupParameter(PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parâmetro '{}' não encontrado no projeto.".format(PARAM)

    normalizados = normalizar_dados(dados)
    with Transaction(doc, u"FireUtils - Material e sistema de conexão por trecho") as t:
        t.Start()
        param.Set(json.dumps(normalizados, ensure_ascii=True, sort_keys=True))
        t.Commit()
    return True, u"Material e sistema de conexão salvos no projeto."
