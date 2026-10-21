# -*- coding: utf-8 -*-
"""
saidas/calc.py — Fire Utils · lib/
Monta e sincroniza o payload de ambientes classificados (por pavimento) com
o site. Sem dependências de Revit — a coleta dos Room (parâmetros Grupo/
População/Área/Estrutura) fica em saidas/rooms.py; aqui só agrupa em dicts
puros e envia.

O dimensionamento de Acessos/Descargas/Portas (IT 11 CBMSP / NBR 9077) saiu
do plugin — é feito inteiramente no site/dockpane (SaidaEmergenciaPage +
AcessosDescargasView, webapp/src/components/dashboard/) a partir dos
ambientes que este módulo sincroniza. Nunca calcula largura de saída aqui.

Um projeto pode ter várias estruturas modeladas no mesmo arquivo Revit —
`sincronizar_ambientes` separa os ambientes coletados pelo parâmetro
"Estrutura" de cada Room (ver estrutura_param.py) antes de montar/enviar o
payload, um lote por estrutura — mesmo motivo e mesmo mecanismo de
quantitativos_core.py. Ambiente sem o parâmetro preenchido (ou preenchido
com um texto que não bate com nenhuma estrutura do projeto) não é
sincronizado — fica de fora, reportado à parte.
"""

import json
import os
import io
import datetime

from sync import enviar as enviar_sync, buscar
from family_error_utils import texto_erro

_CACHE_NOME = u"firedata.json"


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


# ===========================================================================
# PAYLOAD — ambientes classificados por pavimento, de UMA estrutura
# ===========================================================================

def montar_payload_ambientes(rooms_data, estado):
    """
    rooms_data : list de dicts {nivel, nome, grupo, area, pop, uid,
                 estruturaNome}, já de UMA estrutura (ver
                 sincronizar_ambientes, que separa por estrutura antes de
                 chamar isto) — ver saidas.rooms.get_rooms_classificados().
    estado     : não usado aqui (mantido só pra não mudar a assinatura nos
                 chamadores — ver saidas_ocupacao_bridge.py) — Revit não
                 decide mais população: só empurra Nome/Grupo/Área pro
                 site, que é quem calcula (área x taxa, ou o valor manual/
                 assento fixo cadastrado por lá) e manda de volta a
                 População/Taxa Populacional prontas (ver
                 populacao.puxar_populacao_do_site, caminho oposto).

    Retorna {"pavimentos": [{"nome": <nível>, "ambientes": [...]}, ...]} —
    mesmo formato que o site espera (SaidaEmergenciaPage.jsx →
    resolverImportacaoSaidas), casando cada pavimento pelo NOME do nível e
    cada ambiente pelo `revitId` (Room.UniqueId, estável mesmo se o nome
    mudar numa reclassificação ou a área for editada depois).
    """
    by_nivel = {}
    ordem    = []
    for r in rooms_data:
        nivel = r[u"nivel"]
        if nivel not in by_nivel:
            by_nivel[nivel] = []
            ordem.append(nivel)
        by_nivel[nivel].append(r)

    pavimentos = []
    for nivel in ordem:
        ambientes = []
        for r in by_nivel[nivel]:
            # `r["nome"]` já vem numerado do Revit (ver populacao.set_occupancy,
            # que grava "NN - <uso>" no parâmetro Nome do Room na hora de
            # classificar) — aqui só repassa, sem recalcular nada.
            ambientes.append({u"nome": r[u"nome"], u"divisao": r[u"grupo"],
                               u"area": r[u"area"], u"revitId": r.get(u"uid")})
        pavimentos.append({u"nome": nivel, u"ambientes": ambientes})

    return {u"pavimentos": pavimentos}


# ===========================================================================
# CACHE + SYNC
# ===========================================================================

def salvar_cache_se_import(se_import, projeto_dir, estruturaId):
    """Salva o payload de ambientes (de UMA estrutura) em firedata.json,
    aninhado por `estruturaId` (mesmo motivo/mecanismo de
    sync.gravar_e_enviar — várias estruturas no mesmo arquivo não podem
    se sobrescrever) e sincroniza best-effort com o site (Edge Function
    revit-sync)."""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        arquivo = {}

    por_estrutura = arquivo.get(u"saidas_emergencia") or {}
    if not isinstance(por_estrutura, dict) or u"porEstrutura" not in por_estrutura:
        por_estrutura = {u"porEstrutura": {}}
    por_estrutura[u"porEstrutura"][estruturaId] = se_import
    arquivo[u"saidas_emergencia"] = por_estrutura
    arquivo.pop(u"saidas", None)        # remove formato antigo
    arquivo.pop(u"se_import", None)     # remove chave legada
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)

    enviar_sync(u"saidas_emergencia", se_import, projeto_dir, estruturaId=estruturaId)


def carregar_cache_se_import(projeto_dir, estruturaId=None):
    """Sem `estruturaId`: True se HOUVER algum ambiente sincronizado, de
    qualquer estrutura (uso em project_link_bridge.py:
    GET_DIMENSIONAMENTOS_STATUS, que hoje só pergunta "já sincronizou
    alguma coisa?"). Com `estruturaId`: o payload daquela estrutura
    especificamente, ou None."""
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        return None

    bruto = arquivo.get(u"saidas_emergencia") or arquivo.get(u"se_import")
    if not bruto:
        return None
    if not isinstance(bruto, dict) or u"porEstrutura" not in bruto:
        # Formato antigo (achatado, de antes de várias estruturas por
        # arquivo) — devolve como está; só acontece pra arquivo nunca mais
        # sincronizado depois dessa mudança.
        return bruto if estruturaId is None else None
    if estruturaId is None:
        return bruto if bruto[u"porEstrutura"] else None
    return bruto[u"porEstrutura"].get(estruturaId)


def _mapa_estruturas(projeto_dir):
    """{nomeEstrutura: estruturaId} do projeto vinculado, buscado ao vivo —
    mesma função de quantitativos_core.py, duplicada aqui (dict simples,
    sem valer a pena um módulo só pra isso) pra não criar uma dependência
    cruzada entre saidas/ e o resto dos quantitativos."""
    estruturas, erro = buscar(u"listar_estruturas", projeto_dir)
    if erro:
        return None, erro
    mapa = {}
    for e in (estruturas or []):
        nome = (e.get(u"nome") or u"").strip()
        if nome:
            mapa[nome] = e.get(u"id")
    return mapa, None


def sincronizar_ambientes(rooms_data, estado, projeto_dir):
    """Separa `rooms_data` pela estrutura de cada ambiente (parâmetro
    "Estrutura", resolvido contra a lista ao vivo do projeto), monta o
    payload (montar_payload_ambientes) e grava+sincroniza
    (salvar_cache_se_import) um lote por estrutura — chamado ao final de
    qualquer fluxo de identificação de ambientes (identificar por ambiente /
    por nível / todos / sincronizar — saidas_ocupacao_bridge.py).

    Retorna {"porEstrutura": [{"estruturaNome", "quantidade"}, ...],
    "naoReconhecidos": [nome, ...], "erro": str|None} — pra quem chamou
    (os 4 pushbuttons) poder avisar o usuário do resultado, em vez de
    sincronizar silenciosamente."""
    mapa_nomes, erro_mapa = _mapa_estruturas(projeto_dir)
    if mapa_nomes is None:
        return {u"porEstrutura": [], u"naoReconhecidos": [],
                u"erro": u"Não foi possível confirmar as estruturas do projeto: {}".format(erro_mapa)}

    por_estrutura = {}
    nao_reconhecidos = set()
    sem_estrutura = 0
    for r in rooms_data:
        nome = (r.get(u"estruturaNome") or u"").strip()
        if not nome:
            sem_estrutura += 1
            continue
        estrutura_id = mapa_nomes.get(nome)
        if estrutura_id is None:
            nao_reconhecidos.add(nome)
            continue
        por_estrutura.setdefault(estrutura_id, []).append(r)

    mapa_id_para_nome = dict((v, k) for k, v in mapa_nomes.items())
    resumo = []
    for estrutura_id, rooms_da_estrutura in por_estrutura.items():
        payload = montar_payload_ambientes(rooms_da_estrutura, estado)
        payload[u"_timestamp"] = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
        try:
            salvar_cache_se_import(payload, projeto_dir, estrutura_id)
        except Exception as e:
            resumo.append({u"estruturaNome": mapa_id_para_nome.get(estrutura_id), u"quantidade": 0,
                            u"erro": texto_erro(e)})
            continue
        resumo.append({u"estruturaNome": mapa_id_para_nome.get(estrutura_id),
                        u"quantidade": len(rooms_da_estrutura), u"erro": None})

    return {u"porEstrutura": resumo, u"naoReconhecidos": sorted(nao_reconhecidos),
            u"semEstrutura": sem_estrutura, u"erro": None}


def resumo_texto(resultado):
    """Formata o retorno de sincronizar_ambientes numa linha por estrutura
    (+ aviso de não reconhecidos), pronto pra um forms.alert — usado pelos
    a dockpane (saidas_ocupacao_bridge.py)."""
    if resultado.get(u"erro"):
        return resultado[u"erro"]

    linhas = []
    for item in resultado.get(u"porEstrutura") or []:
        if item.get(u"erro"):
            linhas.append(u"{}: falha ao enviar ({})".format(item.get(u"estruturaNome") or u"?", item[u"erro"]))
        else:
            linhas.append(u"{}: {} ambiente(s) enviado(s)".format(item.get(u"estruturaNome") or u"?", item[u"quantidade"]))

    nao_reconhecidos = resultado.get(u"naoReconhecidos") or []
    if nao_reconhecidos:
        linhas.append(u"Texto de Estrutura não reconhecido em algum ambiente: {}".format(
            u", ".join(nao_reconhecidos)))

    sem_estrutura = resultado.get(u"semEstrutura") or 0
    if sem_estrutura:
        linhas.append(u"{} ambiente(s) sem o parâmetro Estrutura preenchido — não sincronizado(s).".format(sem_estrutura))

    if not linhas:
        linhas.append(u"Nenhum ambiente com Estrutura reconhecida pra sincronizar.")

    return u"\n".join(linhas)
