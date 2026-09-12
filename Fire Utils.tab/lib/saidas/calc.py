# -*- coding: utf-8 -*-
"""
saidas/calc.py — Fire Utils · lib/
Monta e sincroniza o payload de ambientes classificados (por pavimento) com
o site. Sem dependências de Revit — a coleta dos Room (parâmetros Grupo/
População/Área) fica em saidas/rooms.py; aqui só agrupa em dicts puros e
envia.

O dimensionamento de Acessos/Descargas/Portas (IT 11 CBMSP / NBR 9077) saiu
do plugin — é feito inteiramente no site/dockpane (SaidaEmergenciaPage +
AcessosDescargasView, webapp/src/components/dashboard/) a partir dos
ambientes que este módulo sincroniza. Nunca calcula largura de saída aqui.
"""

import json
import os
import io
import datetime

from sync import enviar as enviar_sync, config_sync

_CACHE_NOME = u"firedata.json"


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


# ===========================================================================
# PAYLOAD — ambientes classificados por pavimento
# ===========================================================================

def montar_payload_ambientes(rooms_data, estado):
    """
    rooms_data : list de dicts {nivel, nome, grupo, area, pop, uid} — ver
                 saidas.rooms.get_rooms_classificados().
    estado     : dict de normas.get_estado(); usa estado["tabela"] pra
                 decidir se a população do ambiente é derivada da área
                 (taxa "A" da divisão) ou manual (parâmetro "População").

    Retorna {"pavimentos": [{"nome": <nível>, "ambientes": [...]}, ...]} —
    mesmo formato que o site espera (SaidaEmergenciaPage.jsx →
    resolverImportacaoSaidas), casando cada pavimento pelo NOME do nível e
    cada ambiente pelo `revitId` (Room.UniqueId, estável mesmo se o nome
    mudar numa reclassificação ou a área for editada depois).
    """
    tabela = (estado or {}).get(u"tabela", {})

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
            divisao = r[u"grupo"]
            taxa_a  = tabela.get(divisao, {}).get(u"A")
            if taxa_a is not None and float(taxa_a) > 0:
                ambientes.append({u"nome": r[u"nome"], u"divisao": divisao,
                                   u"area": r[u"area"], u"popTipo": u"area",
                                   u"revitId": r.get(u"uid")})
            else:
                ambientes.append({u"nome": r[u"nome"], u"divisao": divisao,
                                   u"area": r[u"area"], u"popTipo": u"manual",
                                   u"popManual": r[u"pop"], u"revitId": r.get(u"uid")})
        pavimentos.append({u"nome": nivel, u"ambientes": ambientes})

    return {u"pavimentos": pavimentos}


# ===========================================================================
# CACHE + SYNC
# ===========================================================================

def salvar_cache_se_import(se_import, projeto_dir=None):
    """Salva o payload de ambientes em firedata.json e sincroniza
    best-effort com o site (Edge Function revit-sync)."""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        arquivo = {}
    arquivo[u"saidas_emergencia"] = se_import
    arquivo.pop(u"saidas", None)        # remove formato antigo
    arquivo.pop(u"se_import", None)     # remove chave legada
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)

    estrutura_id = config_sync(projeto_dir).get(u"estruturaId")
    enviar_sync(u"saidas_emergencia", se_import, projeto_dir, estruturaId=estrutura_id)


def carregar_cache_se_import(projeto_dir=None):
    path = _cache_path(projeto_dir)
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
        return arquivo.get(u"saidas_emergencia") or arquivo.get(u"se_import")
    except Exception:
        return None


def sincronizar_ambientes(rooms_data, estado, projeto_dir):
    """Monta o payload (montar_payload_ambientes) e grava+sincroniza
    (salvar_cache_se_import) — chamado ao final de qualquer fluxo de
    identificação de ambientes (Identificar Ambiente / Por Nível / Todos)."""
    payload = montar_payload_ambientes(rooms_data, estado)
    payload[u"_timestamp"] = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
    salvar_cache_se_import(payload, projeto_dir)
