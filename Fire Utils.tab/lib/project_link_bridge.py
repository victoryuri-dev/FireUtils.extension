# -*- coding: utf-8 -*-
"""
project_link_bridge.py — Fire Utils · lib/
Processa as mensagens da bridge web (webapp/) relacionadas ao vínculo
projeto/estruturas do Dashboard: GET_PROJECT_LINK, SET_PROJECT_LINK,
DISCONNECT_PROJECT e GET_DIMENSIONAMENTOS_STATUS — contrato documentado em
webapp/README.md.

Um arquivo Revit pode conter várias estruturas modeladas juntas — o
vínculo deixou de ser "uma estrutura por documento" e virou "um CONJUNTO
de estruturas por documento" (`estruturas`, lista de {id, nome}, em vez de
um `estruturaId`/`estruturaNome` só). Esse conjunto não decide mais quem
pertence a quem: é só a lista de opções que a dockpane oferece na
ferramenta "Atribuir seleção à estrutura" (ver atribuir_estrutura_bridge.py)
— cada elemento/ambiente carrega a sua própria estrutura no parâmetro
"Estrutura" (ver estrutura_param.py), nunca herdada do vínculo. Hidrantes
é a exceção: sistema único, compartilhado entre todas as estruturas do
projeto, sem nenhuma mudança por essa migração.

Substitui o antigo pushbutton "Dados do Projeto" (WPF/XAML, Fire
Utils.tab/Projeto.panel — aposentado): a escolha do projeto/estruturas
agora acontece direto no Dashboard React, consultando o Supabase com a
sessão do usuário logado (RLS) — nada aqui fala com o Supabase. Este
módulo só persiste o vínculo escolhido no firedata.json do documento
aberto.

Todas as funções aqui esperam rodar dentro de uma ação enfileirada via
family_loader_events.criar_fila_acoes() (mesmo padrão do carregamento de
família) — precisam de `uiapp` com contexto de API válido pra ler
doc.PathName.
"""

import os

from sync import config_sync, salvar_config_sync, estruturas_vinculadas
from projeto import salvar_dados_projeto, limpar_vinculo_projeto, carregar_cache
from normas import get_estado
from family_error_utils import texto_erro
import hidrantes.calc as hidrantes_calc
import saidas.calc as saidas_calc


def _projeto_dir(uiapp):
    """Pasta do projeto Revit ativo, ou None se não houver documento aberto
    ou ele ainda não tiver sido salvo em disco — ao contrário do antigo
    pushbutton, a dockpane pode estar aberta nesses dois casos, então aqui
    isso vira um estado pro React tratar (`docSalvo: false`), nunca um
    alerta bloqueante."""
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        return None
    doc = uidoc.Document
    if not doc.PathName:
        return None
    return os.path.dirname(doc.PathName)


def _estado_vinculo(projeto_dir):
    if projeto_dir is None:
        return {
            u"docSalvo": False,
            u"projetoId": None,
            u"projetoNome": None,
            u"estruturas": [],
        }
    sync = config_sync(projeto_dir)
    return {
        u"docSalvo": True,
        u"projetoId": sync.get(u"projetoId"),
        u"projetoNome": sync.get(u"projetoNome"),
        u"estruturas": estruturas_vinculadas(projeto_dir),
    }


def tratar_get_project_link(uiapp, postar_mensagem):
    # Sem try/except aqui, um erro (ex.: exceção de rede ao consultar a
    # base normativa central — ver sync.buscar_norma) deixava essa
    # mensagem sem resposta nenhuma: a exceção subia até
    # family_loader_events.Execute, que só loga no console do pyRevit, e
    # o Dashboard ficava preso em "Carregando..." pra sempre, sem nenhum
    # aviso visível no React.
    try:
        estado = _estado_vinculo(_projeto_dir(uiapp))
    except Exception as ex:
        print(u"[AVISO] GET_PROJECT_LINK falhou: {}".format(texto_erro(ex)))
        estado = _estado_vinculo(None)
    postar_mensagem(u"PROJECT_LINK", estado)


def tratar_set_project_link(uiapp, payload, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is None:
        postar_mensagem(u"PROJECT_LINK_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de vincular um projeto.",
        })
        return

    estruturas = payload.get(u"estruturas") or []
    if not estruturas:
        postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": False, u"erro": u"Selecione ao menos uma estrutura."})
        return

    try:
        uf = payload.get(u"uf") or u""
        estado = get_estado(uf, projeto_dir) if uf else None
        estado_nome = (estado.get(u"nome") if estado else None) or uf
        salvar_dados_projeto(
            projeto_dir,
            identificador=payload.get(u"projetoNome") or u"",
            estado_nome=estado_nome,
            uf=uf,
            area_construida=payload.get(u"areaConstruida"),
        )
        salvar_config_sync(
            projeto_dir,
            projetoId=payload.get(u"projetoId"),
            projetoNome=payload.get(u"projetoNome"),
            estruturas=estruturas,
        )
    except Exception as ex:
        postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
        return

    postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": True})
    postar_mensagem(u"PROJECT_LINK", _estado_vinculo(projeto_dir))


def tratar_disconnect_project(uiapp, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is not None:
        try:
            limpar_vinculo_projeto(projeto_dir)
        except Exception as ex:
            postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": False, u"erro": texto_erro(ex)})
            return
    postar_mensagem(u"PROJECT_LINK", _estado_vinculo(projeto_dir))


def tratar_get_dimensionamentos_status(uiapp, payload, postar_mensagem):
    """`payload.estruturaId` é a estrutura sendo VISTA no momento no
    Dashboard (um dos cartões — Hidrantes é o único que ignora isso, por
    ser um sistema só pro projeto inteiro). Sem `estruturaId` (chamada
    antiga, ou nenhuma estrutura ainda carregada), saída/níveis caem pra
    "existe algo sincronizado, de qualquer estrutura?", só pra não quebrar
    quem ainda não manda o parâmetro nenhum."""
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is None:
        postar_mensagem(u"DIMENSIONAMENTOS_STATUS", {u"hidrantes": False, u"saidaEmergencia": False, u"niveis": False})
        return

    estrutura_id = (payload or {}).get(u"estruturaId")
    try:
        hidrantes_ok = hidrantes_calc.cache_existe(projeto_dir)
        saida_ok = saidas_calc.carregar_cache_se_import(projeto_dir, estrutura_id) is not None
        # "Correlacionado" quando já existe uma correlação Nível Revit <->
        # Pavimento salva pra estrutura sendo vista (ver niveis_bridge.py).
        niveis_pavimentos = carregar_cache(projeto_dir).get(u"niveis_pavimentos") or {}
        if estrutura_id:
            niveis_ok = bool(niveis_pavimentos.get(estrutura_id))
        else:
            niveis_ok = any(niveis_pavimentos.values())
    except Exception as ex:
        print(u"[AVISO] GET_DIMENSIONAMENTOS_STATUS falhou: {}".format(texto_erro(ex)))
        hidrantes_ok = False
        saida_ok = False
        niveis_ok = False
    postar_mensagem(u"DIMENSIONAMENTOS_STATUS", {
        u"hidrantes": hidrantes_ok,
        u"saidaEmergencia": saida_ok,
        u"niveis": niveis_ok,
    })
