# -*- coding: utf-8 -*-
"""
quantitativos_core.py — Fire Utils · lib/
Lógica central de "Gravar Quantitativos": para cada medida de quantitativo
disponível (Extintores, Sinalização de Emergência, Iluminação de
Emergência), coleta as instâncias do modelo, grava no firedata.json e
envia o resultado pro site (Supabase).

Antes um botão de faixa de opções com uma janela de seleção (o usuário
escolhia quais medidas gravar); agora é disparado por um clique na
dockpane (ver quantitativos_bridge.py) e roda SEMPRE as medidas todas —
sem janela nenhuma, sem abrir o output window do pyRevit. Cada medida
roda isolada: se uma falhar (ex.: erro ao criar parâmetro), a falha é
reportada só nela, as demais continuam.

Separado em duas etapas, pra quem chama (quantitativos_bridge.py) poder
rodar cada uma no contexto certo:
  - coletar_todos(doc): só leitura do modelo Revit — precisa de contexto
    de API válido (ExternalEvent), mas é local/rápido (sem rede).
  - salvar_todos(resultados_coleta, projeto_dir): grava o firedata.json e
    envia pro site (rede, até ~5s de timeout por medida) — não toca a API
    do Revit, então pode (e deve) rodar fora da UI thread.

Pra adicionar uma nova medida:
  1. no módulo <medida>/calc.py, exponha coletar_itens(doc) (+ agrupar, se
     a medida precisar agregar por algo antes de enviar — ver
     sinalizacao/calc.py) e salvar_cache(itens, projeto_dir);
  2. registre uma entrada em MEDIDAS aqui embaixo.

Funções públicas
----------------
coletar_todos(doc) -> [ {chave, rotulo, itens, erro}, ... ]
salvar_todos(resultados_coleta, projeto_dir) -> [ {chave, rotulo, quantidade, enviado, motivo, erro}, ... ]
"""

import extintores.calc as extintores_calc
import extintores.params as extintores_params
import sinalizacao.calc as sinalizacao_calc
import iluminacao.calc as iluminacao_calc

from family_error_utils import texto_erro


# ===========================================================================
# REGISTRO DE MEDIDAS
# ===========================================================================
class _Medida(object):
    def __init__(self, chave, rotulo, coletar, salvar, preparar=None, agrupar=None):
        self.chave    = chave
        self.rotulo   = rotulo
        self.preparar = preparar  # doc -> None, opcional (cria parâmetros)
        self.coletar  = coletar   # doc -> [item, ...]
        self.agrupar  = agrupar   # [item, ...] -> [item, ...], opcional
        self.salvar   = salvar    # (itens, projeto_dir) -> (path, ok, motivo)


MEDIDAS = [
    _Medida(
        chave=u"extintores",
        rotulo=u"Extintores",
        preparar=lambda doc: extintores_params.create_extinguisher_params(doc),
        coletar=extintores_calc.coletar_itens,
        salvar=extintores_calc.salvar_cache,
    ),
    _Medida(
        chave=u"sinalizacao",
        rotulo=u"Sinalização de Emergência",
        coletar=sinalizacao_calc.coletar_itens,
        agrupar=sinalizacao_calc.agrupar_por_placa,
        salvar=sinalizacao_calc.salvar_cache,
    ),
    _Medida(
        chave=u"iluminacao",
        rotulo=u"Iluminação de Emergência",
        coletar=iluminacao_calc.coletar_itens,
        agrupar=iluminacao_calc.agrupar_por_pavimento,
        salvar=iluminacao_calc.salvar_cache,
    ),
]


# ===========================================================================
# ETAPA 1 — coleta (precisa de contexto de API do Revit)
# ===========================================================================
def coletar_todos(doc):
    """Roda preparar+coletar+agrupar de cada medida contra o modelo ativo.
    Só leitura (e, pra extintores, criação dos parâmetros compartilhados
    que ainda faltarem) — sem rede. Chamar de dentro de um ExternalEvent
    (contexto de API válido)."""
    resultados = []
    for medida in MEDIDAS:
        if medida.preparar:
            try:
                medida.preparar(doc)
            except Exception as e:
                resultados.append({
                    u"chave": medida.chave, u"rotulo": medida.rotulo,
                    u"itens": [], u"erro": u"Falha ao preparar parâmetros: {}".format(texto_erro(e)),
                })
                continue

        try:
            itens_brutos = medida.coletar(doc)
            itens = medida.agrupar(itens_brutos) if medida.agrupar else itens_brutos
        except Exception as e:
            resultados.append({
                u"chave": medida.chave, u"rotulo": medida.rotulo,
                u"itens": [], u"erro": u"Falha ao coletar: {}".format(texto_erro(e)),
            })
            continue

        resultados.append({u"chave": medida.chave, u"rotulo": medida.rotulo, u"itens": itens, u"erro": None})
    return resultados


# ===========================================================================
# ETAPA 2 — gravação local + envio pro site (sem tocar a API do Revit)
# ===========================================================================
def salvar_todos(resultados_coleta, projeto_dir):
    """Grava/envia cada medida coletada (ver coletar_todos) — pode rodar
    fora da UI thread, já que só mexe com arquivo local e rede (cada envio
    tem até ~5s de timeout, 3 medidas em série não podem travar a UI do
    Revit — ver quantitativos_bridge.py)."""
    medidas_por_chave = dict((m.chave, m) for m in MEDIDAS)
    resumo = []
    for resultado in resultados_coleta:
        chave, rotulo, itens, erro = resultado[u"chave"], resultado[u"rotulo"], resultado[u"itens"], resultado[u"erro"]

        if erro:
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"quantidade": 0, u"enviado": None, u"motivo": None, u"erro": erro})
            continue

        if not itens:
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"quantidade": 0, u"enviado": None, u"motivo": None, u"erro": None})
            continue

        medida = medidas_por_chave[chave]
        try:
            _path, ok, motivo = medida.salvar(itens, projeto_dir)
        except Exception as e:
            resumo.append({
                u"chave": chave, u"rotulo": rotulo, u"quantidade": len(itens), u"enviado": None, u"motivo": None,
                u"erro": u"Falha ao gravar/enviar: {}".format(texto_erro(e)),
            })
            continue

        resumo.append({u"chave": chave, u"rotulo": rotulo, u"quantidade": len(itens), u"enviado": ok, u"motivo": (None if ok else motivo), u"erro": None})

    return resumo
