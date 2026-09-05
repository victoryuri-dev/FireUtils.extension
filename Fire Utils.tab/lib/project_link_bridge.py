# -*- coding: utf-8 -*-
"""
project_link_bridge.py — Fire Utils · lib/
Processa as mensagens da bridge web (webapp/) relacionadas ao vínculo
projeto/estrutura do Dashboard: GET_PROJECT_LINK, SET_PROJECT_LINK,
DISCONNECT_PROJECT e GET_DIMENSIONAMENTOS_STATUS — contrato documentado em
webapp/README.md.

Substitui o antigo pushbutton "Dados do Projeto" (WPF/XAML, Fire
Utils.tab/Projeto.panel — aposentado): a escolha do projeto/estrutura agora
acontece direto no Dashboard React, consultando o Supabase com a sessão do
usuário logado (RLS) — nada aqui fala com o Supabase. Este módulo só
persiste o vínculo escolhido no firedata.json do documento aberto, no
mesmo formato que o pushbutton antigo gravava (dados_projeto + sync), pra
manter os módulos de dimensionamento (hidrantes/saidas/extintores)
funcionando sem nenhuma mudança neles.

Todas as funções aqui esperam rodar dentro de uma ação enfileirada via
family_loader_events.criar_fila_acoes() (mesmo padrão do carregamento de
família) — precisam de `uiapp` com contexto de API válido pra ler
doc.PathName.
"""

import os

from sync import config_sync, salvar_config_sync
from projeto import salvar_dados_projeto, limpar_vinculo_projeto
from normas import get_label, get_estado
import hidrantes.calc as hidrantes_calc
import saidas.calc as saidas_calc


def _distancia_minima(estado, codigo):
    """Menor distância máxima aplicável ao código de ocupação, no cenário
    mais exigente (saída única, sem chuveiro, sem detecção) — usado só pra
    decidir qual divisão é a mais restritiva entre as existentes na
    estrutura. Portado do antigo formulário "Dados do Projeto"
    (_distancia_minima), que fazia exatamente essa escolha antes de
    aposentado. Retorna None se o código não constar da tabela normativa."""
    dist_cfg = (estado or {}).get(u"distancias_maximas")
    if not dist_cfg:
        return None
    mapa   = dist_cfg.get(u"mapa_ocupacao", {})
    grupos = dist_cfg.get(u"grupos", {})
    nome_grupo = mapa.get(codigo)
    if not nome_grupo:
        return None
    cfg = grupos.get(nome_grupo, {})
    valores = []
    for tipo_pav in (u"terreo", u"demais"):
        try:
            v = cfg[tipo_pav][u"sem_chuveiro"][u"saida_unica"][u"sem_deteccao"]
            if v is not None:
                valores.append(v)
        except (KeyError, TypeError):
            pass
    return min(valores) if valores else None


def _divisao_mais_restritiva(uf, divisoes):
    """Entre os códigos de ocupação presentes nos pavimentos da estrutura
    (`divisoes`, vindo do React — ver lib/projetoDados.js), escolhe o mais
    restritivo (menor distância máxima) pra virar
    dados_projeto.ocupacao_principal. Os módulos de dimensionamento (ex.:
    Dimensionar Saídas, via saidas/forms.form_config_distancias) exigem um
    código válido e único da tabela normativa — "Mista" (o rótulo que a
    tela mostra pra estrutura com mais de uma divisão) não existe nela e
    quebraria esse lookup, por isso a escolha acontece aqui, não no React."""
    codigos = [c for c in (divisoes or []) if c]
    if not codigos:
        return None
    estado = get_estado(uf) if uf else None
    itens = [(cod, _distancia_minima(estado, cod)) for cod in codigos]
    itens.sort(key=lambda t: (t[1] is None, t[1]))
    return itens[0][0]


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
            u"estruturaId": None,
            u"estruturaNome": None,
        }
    sync = config_sync(projeto_dir)
    return {
        u"docSalvo": True,
        u"projetoId": sync.get(u"projetoId"),
        u"projetoNome": sync.get(u"projetoNome"),
        u"estruturaId": sync.get(u"estruturaId"),
        u"estruturaNome": sync.get(u"estruturaNome"),
    }


def tratar_get_project_link(uiapp, postar_mensagem):
    postar_mensagem(u"PROJECT_LINK", _estado_vinculo(_projeto_dir(uiapp)))


def tratar_set_project_link(uiapp, payload, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is None:
        postar_mensagem(u"PROJECT_LINK_SAVED", {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de vincular um projeto.",
        })
        return

    try:
        uf = payload.get(u"uf") or u""
        estado_nome = get_label(uf).split(u" — ")[0] if uf else u""
        ocupacao_principal = _divisao_mais_restritiva(uf, payload.get(u"divisoes"))
        salvar_dados_projeto(
            projeto_dir,
            identificador=payload.get(u"projetoNome") or u"",
            estado_nome=estado_nome,
            uf=uf,
            ocupacao_principal=ocupacao_principal,
            area_construida=payload.get(u"areaConstruida"),
        )
        salvar_config_sync(
            projeto_dir,
            projetoId=payload.get(u"projetoId"),
            projetoNome=payload.get(u"projetoNome"),
            estruturaId=payload.get(u"estruturaId"),
            estruturaNome=payload.get(u"estruturaNome"),
        )
    except Exception as ex:
        postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": False, u"erro": u"{}".format(ex)})
        return

    postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": True})
    postar_mensagem(u"PROJECT_LINK", _estado_vinculo(projeto_dir))


def tratar_disconnect_project(uiapp, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is not None:
        try:
            limpar_vinculo_projeto(projeto_dir)
        except Exception as ex:
            postar_mensagem(u"PROJECT_LINK_SAVED", {u"ok": False, u"erro": u"{}".format(ex)})
            return
    postar_mensagem(u"PROJECT_LINK", _estado_vinculo(projeto_dir))


def tratar_get_dimensionamentos_status(uiapp, postar_mensagem):
    projeto_dir = _projeto_dir(uiapp)
    if projeto_dir is None:
        postar_mensagem(u"DIMENSIONAMENTOS_STATUS", {u"hidrantes": False, u"saidaEmergencia": False})
        return

    hidrantes_ok = hidrantes_calc.cache_existe(projeto_dir)
    saida_ok = saidas_calc.carregar_cache_se_import(projeto_dir) is not None
    postar_mensagem(u"DIMENSIONAMENTOS_STATUS", {
        u"hidrantes": hidrantes_ok,
        u"saidaEmergencia": saida_ok,
    })
