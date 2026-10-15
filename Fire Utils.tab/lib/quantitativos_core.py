# -*- coding: utf-8 -*-
"""
quantitativos_core.py — Fire Utils · lib/
Lógica central de "Gravar Quantitativos": para cada medida de quantitativo
disponível (Extintores, Sinalização de Emergência, Iluminação de
Emergência), coleta as instâncias do modelo, agrupa por estrutura (ver
estrutura_param.py — parâmetro "Estrutura", texto, instância) e grava/envia
um lote por estrutura.

Disparado por um clique na dockpane (ver quantitativos_bridge.py) — roda
sempre as medidas todas, sem janela nenhuma, sem abrir o output window do
pyRevit. Cada medida roda isolada: se uma falhar (ex.: erro ao criar
parâmetro), a falha é reportada só nela, as demais continuam.

Um projeto pode ter várias estruturas modeladas no mesmo arquivo Revit —
não existe mais "a estrutura do documento": cada item vai pra onde o
parâmetro "Estrutura" dele apontar. Item sem o parâmetro preenchido, ou
preenchido com um texto que não bate com nenhuma estrutura do projeto, não
é enviado — fica reportado à parte (ver salvar_todos), nunca presumido.

Separado em duas etapas, pra quem chama (quantitativos_bridge.py) poder
rodar cada uma no contexto certo:
  - coletar_todos(doc): só leitura do modelo Revit — precisa de contexto
    de API válido (ExternalEvent), mas é local/rápido (sem rede). NÃO
    agrega ainda (ver salvar_todos pro porquê).
  - salvar_todos(resultados_coleta, projeto_dir): busca a lista de
    estruturas do projeto (rede, uma vez), agrupa os itens brutos de cada
    medida por estrutura resolvida, só ENTÃO agrega (medida.agrupar — teria
    que ser por estrutura, nunca antes, senão a contagem de uma mistura com
    a de outra) e grava/envia um lote por (medida, estrutura) — não toca a
    API do Revit, então pode (e deve) rodar fora da UI thread.

Pra adicionar uma nova medida:
  1. no módulo <medida>/calc.py, exponha coletar_itens(doc) — cada item com
     uma chave "estruturaNome" (ver estrutura_param.ler_estrutura) — (+
     agrupar, se a medida precisar agregar por algo antes de enviar — ver
     sinalizacao/calc.py) e salvar_cache(itens, projeto_dir, estruturaId);
  2. registre uma entrada em MEDIDAS aqui embaixo.

Funções públicas
----------------
coletar_todos(doc) -> [ {chave, rotulo, itens, erro}, ... ]
salvar_todos(resultados_coleta, projeto_dir) -> [ {chave, rotulo, estruturaNome, quantidade, enviado, motivo, erro}, ... ]
"""

import extintores.calc as extintores_calc
import extintores.params as extintores_params
import sinalizacao.calc as sinalizacao_calc
import iluminacao.calc as iluminacao_calc

from sync import buscar
from family_error_utils import texto_erro


# ===========================================================================
# REGISTRO DE MEDIDAS
# ===========================================================================
class _Medida(object):
    def __init__(self, chave, rotulo, coletar, salvar, preparar=None, agrupar=None):
        self.chave    = chave
        self.rotulo   = rotulo
        self.preparar = preparar  # doc -> None, opcional (cria parâmetros)
        self.coletar  = coletar   # doc -> [item, ...] (cada um com "estruturaNome")
        self.agrupar  = agrupar   # [item, ...] -> [item, ...], opcional — SEMPRE por estrutura já separada
        self.salvar   = salvar    # (itens, projeto_dir, estruturaId) -> (path, ok, motivo)


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
    """Roda preparar+coletar de cada medida contra o modelo ativo — itens
    BRUTOS, um por instância, cada um com "estruturaNome" (texto cru do
    parâmetro, ainda não resolvido). Só leitura (e, pra extintores, criação
    dos parâmetros compartilhados que ainda faltarem) — sem rede. Chamar de
    dentro de um ExternalEvent (contexto de API válido)."""
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
        except Exception as e:
            resultados.append({
                u"chave": medida.chave, u"rotulo": medida.rotulo,
                u"itens": [], u"erro": u"Falha ao coletar: {}".format(texto_erro(e)),
            })
            continue

        resultados.append({u"chave": medida.chave, u"rotulo": medida.rotulo, u"itens": itens_brutos, u"erro": None})
    return resultados


# ===========================================================================
# ETAPA 2 — resolução de estrutura + gravação local + envio pro site
# (sem tocar a API do Revit — pode rodar fora da UI thread)
# ===========================================================================
def _mapa_estruturas(projeto_dir):
    """{nomeEstrutura: estruturaId} do projeto vinculado, buscado ao vivo
    (sync.buscar, Edge Function site-sync) — nunca de um cache local (uma
    estrutura renomeada no site não pode deixar a resolução desatualizada
    silenciosamente). Retorna (mapa, erro) — mapa é None só quando a busca
    falhou de verdade (sem rede, projeto não vinculado); lista vazia (projeto
    sem estrutura nenhuma) já volta como {} sem erro."""
    estruturas, erro = buscar(u"listar_estruturas", projeto_dir)
    if erro:
        return None, erro
    mapa = {}
    for e in (estruturas or []):
        nome = (e.get(u"nome") or u"").strip()
        if nome:
            mapa[nome] = e.get(u"id")
    return mapa, None


def _agrupar_por_estrutura(itens, mapa_nomes):
    """Separa itens brutos em {estruturaId: [itens, ...]} + uma lista à
    parte de nomes não reconhecidos (sem parâmetro preenchido, ou
    preenchido com um texto que não bate com nenhuma estrutura do
    projeto) — nunca presume uma estrutura padrão (ver docstring do
    módulo)."""
    por_estrutura = {}
    nao_reconhecidos = set()
    for it in itens:
        nome = (it.get(u"estruturaNome") or u"").strip()
        estrutura_id = mapa_nomes.get(nome) if nome else None
        if estrutura_id is None:
            if nome:
                nao_reconhecidos.add(nome)
            continue
        por_estrutura.setdefault(estrutura_id, []).append(it)
    return por_estrutura, nao_reconhecidos


def salvar_todos(resultados_coleta, projeto_dir):
    """Resolve a estrutura de cada item coletado (ver coletar_todos) contra
    a lista ao vivo do projeto, agrega (medida.agrupar) e grava/envia um
    lote por (medida, estrutura) — pode rodar fora da UI thread, já que só
    mexe com arquivo local e rede (cada envio tem até ~5s de timeout — ver
    quantitativos_bridge.py)."""
    medidas_por_chave = dict((m.chave, m) for m in MEDIDAS)
    mapa_nomes, erro_mapa = _mapa_estruturas(projeto_dir)

    resumo = []
    for resultado in resultados_coleta:
        chave, rotulo, itens, erro = resultado[u"chave"], resultado[u"rotulo"], resultado[u"itens"], resultado[u"erro"]

        if erro:
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": None, u"quantidade": 0,
                            u"enviado": None, u"motivo": None, u"erro": erro, u"naoReconhecidos": []})
            continue

        if not itens:
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": None, u"quantidade": 0,
                            u"enviado": None, u"motivo": None, u"erro": None, u"naoReconhecidos": []})
            continue

        if mapa_nomes is None:
            # Sem conexão pra confirmar as estruturas — nenhum item desta
            # medida pode ser resolvido com segurança (ver docstring de
            # _mapa_estruturas). Reporta uma falha só pra medida inteira,
            # em vez de arriscar mandar pra estrutura errada.
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": None, u"quantidade": len(itens),
                            u"enviado": None, u"motivo": None,
                            u"erro": u"Não foi possível confirmar as estruturas do projeto: {}".format(erro_mapa),
                            u"naoReconhecidos": []})
            continue

        grupos, nao_reconhecidos = _agrupar_por_estrutura(itens, mapa_nomes)
        mapa_id_para_nome = dict((v, k) for k, v in mapa_nomes.items())
        medida = medidas_por_chave[chave]

        if nao_reconhecidos:
            resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": None, u"quantidade": 0,
                            u"enviado": None, u"motivo": None, u"erro": None,
                            u"naoReconhecidos": sorted(nao_reconhecidos)})

        if not grupos:
            continue

        for estrutura_id, itens_brutos in grupos.items():
            itens_finais = medida.agrupar(itens_brutos) if medida.agrupar else itens_brutos
            try:
                _path, ok, motivo = medida.salvar(itens_finais, projeto_dir, estrutura_id)
            except Exception as e:
                resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": mapa_id_para_nome.get(estrutura_id),
                                u"quantidade": len(itens_brutos), u"enviado": None, u"motivo": None,
                                u"erro": u"Falha ao gravar/enviar: {}".format(texto_erro(e)), u"naoReconhecidos": []})
                continue

            resumo.append({u"chave": chave, u"rotulo": rotulo, u"estruturaNome": mapa_id_para_nome.get(estrutura_id),
                            u"quantidade": len(itens_brutos), u"enviado": ok, u"motivo": (None if ok else motivo),
                            u"erro": None, u"naoReconhecidos": []})

    return resumo
