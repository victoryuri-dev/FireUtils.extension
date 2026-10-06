# -*- coding: utf-8 -*-
"""
niveis_bridge.py — Fire Utils · lib/
Processa as mensagens da bridge web relacionadas à correlação Nível do
Revit <-> Pavimento do FireUtils: GET_REVIT_LEVELS, SET_NIVEIS_CORRELACAO —
contrato documentado em webapp/README.md.

Nem sempre o nome do nível no Revit bate com o pavimento cadastrado no site
(ex.: "Nível 1" em vez de "Térreo") — em vez de tentar adivinhar por nome,
o usuário alinha as duas listas manualmente (ver
components/dashboard/CorrelacaoNiveisModal.jsx no React), arrastando a
ordem dos níveis do Revit até bater com a ordem (já fixa, vem do site) dos
pavimentos. O resultado (uniqueId do nível -> id do pavimento) é salvo no
firedata.json do documento Revit ativo, por estrutura — mesmo motivo de
`sync` (project_link_bridge.py/sync.py) ficar lá e não no Supabase: um
Level é um elemento deste documento Revit, não faz sentido compartilhar
entre documentos/projetos diferentes que apontem pra mesma estrutura.

Usa `Level.UniqueId` (não o ElementId inteiro) como chave persistida —
mesmo critério que saidas/rooms.py já usa pra Room (UniqueId sobrevive a
um rename do elemento; ElementId não é garantidamente estável entre
sessões/arquivos).

Todas as funções aqui esperam rodar dentro de uma ação enfileirada via
family_loader_events.criar_fila_acoes() (mesmo padrão do carregamento de
família) — precisam de `uiapp` com contexto de API válido pra ler
doc.PathName e os elementos do documento.
"""

import os
import io
import json

from Autodesk.Revit.DB import FilteredElementCollector, Level

from projeto import cache_path, carregar_cache
from family_error_utils import texto_erro


def _projeto_dir(uiapp):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        return None
    doc = uidoc.Document
    if not doc.PathName:
        return None
    return os.path.dirname(doc.PathName)


def _niveis_do_documento(doc):
    niveis = sorted(
        FilteredElementCollector(doc).OfClass(Level).ToElements(),
        key=lambda nivel: nivel.Elevation,
    )
    return [
        {u"uniqueId": nivel.UniqueId, u"nome": nivel.Name, u"elevacao": nivel.Elevation}
        for nivel in niveis
    ]


def _correlacao_salva(projeto_dir, estrutura_id):
    if not projeto_dir or not estrutura_id:
        return []
    arquivo = carregar_cache(projeto_dir)
    mapa = arquivo.get(u"niveis_pavimentos") or {}
    return mapa.get(estrutura_id) or []


def tratar_get_revit_levels(uiapp, payload, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        postar_mensagem(u"REVIT_LEVELS", {
            u"levels": [], u"correlacao": [],
            u"erro": u"Nenhum documento Revit ativo.",
        })
        return

    try:
        levels = _niveis_do_documento(uidoc.Document)
    except Exception as ex:
        postar_mensagem(u"REVIT_LEVELS", {
            u"levels": [], u"correlacao": [],
            u"erro": texto_erro(ex),
        })
        return

    correlacao = _correlacao_salva(_projeto_dir(uiapp), payload.get(u"estruturaId"))
    postar_mensagem(u"REVIT_LEVELS", {u"levels": levels, u"correlacao": correlacao})


def tratar_set_niveis_correlacao(uiapp, payload, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is None:
        postar_mensagem(u"NIVEIS_CORRELACAO_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de correlacionar os níveis.",
        })
        return

    estrutura_id = payload.get(u"estruturaId")
    if not estrutura_id:
        postar_mensagem(u"NIVEIS_CORRELACAO_SAVED", {u"ok": False, u"erro": u"Estrutura não identificada."})
        return

    try:
        path = cache_path(projeto_dir)
        arquivo = carregar_cache(projeto_dir)
        mapa = arquivo.get(u"niveis_pavimentos") or {}
        mapa[estrutura_id] = payload.get(u"correlacao") or []
        arquivo[u"niveis_pavimentos"] = mapa
        with io.open(path, u"w", encoding=u"utf-8") as f:
            json.dump(arquivo, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        postar_mensagem(u"NIVEIS_CORRELACAO_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    postar_mensagem(u"NIVEIS_CORRELACAO_SAVED", {u"ok": True})
