# -*- coding: utf-8 -*-
"""
hidrantes_dimensionar_bridge.py — Fire Utils · lib/
Processa DIMENSIONAR_HIDRANTES: lê o modelo do Revit (trechos por diâmetro,
cotas, classificação do sistema) e manda para o motor de cálculo na nuvem
(Edge Function motor-hidrantes, repositório ETOS.FireUtils). Aqui não há
fórmula nenhuma — o método da marcha, a norma e as verificações normativas
(equilíbrio hidráulico, velocidade, pressão/vazão no hidrante, sucção e
NPSH) rodam no servidor; este módulo só extrai, envia e grava o que volta.

Três etapas, cada uma no contexto certo (mesmo desenho de
quantitativos_bridge.py):
  1. Leitura do modelo — toca a API do Revit, roda aqui mesmo (estamos na
     thread de API, chamados via fila_acoes pelo dispatcher).
  2. Chamada ao motor — rede, de centenas de ms a vários segundos conforme a
     internet. Numa thread de fundo: na thread de API, uma conexão ruim
     congelaria o Revit inteiro.
  3. Resposta à dockpane — reenfileirada na thread de API, porque
     postar_mensagem só é seguro a partir dela (ver
     family_loader_webview_forms.py:_postar_mensagem).

Autenticação: a dockpane manda o access token da sessão junto do pedido
(payload["accessToken"]) — ver motor_nuvem.py para o porquê de não usar o
refresh token guardado.

Em caso de sucesso, grava o mesmo cache (firedata.json, chave "hidrantes")
que sempre foi gravado — a dockpane manda GET_HIDRANTES_DIMENSIONAMENTO de
novo depois (ver hidrantes_dimensionamento_bridge.py) pra mostrar o
resultado completo (HidrantesDimensionamento.jsx), sem duplicar nenhum
formato de dado aqui.

Quando alguma verificação normativa não atende, o motor devolve o texto e a
dockpane o mostra; quem precisar localizar o elemento problemático usa
"Mostrar no Projeto" na própria dockpane (SELECIONAR_TRECHO_HIDRANTE).
"""

import os
import datetime
import threading

from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, FlowDirectionType
from Autodesk.Revit.DB.Plumbing import Pipe

from projeto import carregar_dados_projeto
from hidrantes.calc import extrair_trecho, salvar_cache, carregar_cache
from hidrantes.rede import (
    get_id, to_element_id, get_diametro_no_trecho, get_comprimento, get_leq,
    get_nome, get_z, get_cota_conector, get_cota_rti, diagnostico_conectores,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
from hidrantes import succao as succao_calc
import motor_nuvem
from family_error_utils import texto_erro

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_IDENTIFICADOR    = u"FireUtils - Identificador"
_TIPO_RESPOSTA      = u"HIDRANTES_DIMENSIONAR_RESULTADO"


def _erro(postar_mensagem, mensagem, categoria=u"requisito"):
    """`categoria` decide o título do aviso na dockpane — ver motor_nuvem.py.
    Aqui a padrão é "requisito": falta um passo antes de dimensionar."""
    postar_mensagem(_TIPO_RESPOSTA, {u"ok": False, u"erro": mensagem, u"categoria": categoria})


def _get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        if not p or not p.HasValue:
            return None
        valor = p.AsString()
        return valor.strip() if valor else None
    except Exception:
        return None


def tratar_dimensionar_hidrantes(uiapp, payload, fila_acoes, postar_mensagem):
    # Sem esse try/except, qualquer exceção não prevista (ex.: algo que o
    # pushbutton nunca tropeçou porque sempre rodou com o Revit em primeiro
    # plano) subia até o ExternalEvent, que só loga no console do pyRevit —
    # e a dockpane ficava com o botão em "Dimensionando..." pra sempre, sem
    # nenhuma mensagem de volta (mesmo motivo documentado em
    # project_link_bridge.py:tratar_get_project_link).
    try:
        _processar(uiapp, payload, fila_acoes, postar_mensagem)
    except Exception as ex:
        _erro(postar_mensagem, u"Falha inesperada ao dimensionar: {}".format(texto_erro(ex)), u"servidor")


def _processar(uiapp, payload, fila_acoes, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        _erro(postar_mensagem, u"Salve o projeto Revit (.rvt) antes de dimensionar.")
        return
    doc = uidoc.Document
    projeto_dir = os.path.dirname(doc.PathName)

    dados_projeto = carregar_dados_projeto(projeto_dir) or {}
    sigla_estado = dados_projeto.get(u"uf") or u"MA"

    # Etapa 1: tipo de sistema (classificação já aplicada no Project
    # Information — ver hidrantes_classificacao_bridge.py). Quem interpreta
    # "Tipo N Var. X" e busca os parâmetros dele na norma é o motor.
    param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
    if not param_sistema or not param_sistema.AsString():
        _erro(postar_mensagem, u"Sistema de hidrantes ainda não classificado. Classifique na seção acima primeiro.")
        return
    valor_sistema = param_sistema.AsString()

    # Etapa 1b: método de cálculo (gravado junto da classificação). Valor
    # desconhecido o motor recusa; ausente, ele assume "Válvula do Hidrante".
    param_metodo = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
    metodo_calculo = param_metodo.AsString() if param_metodo else None

    # Etapa 2: elementos da rota — cache salvo por "Mapear Trechos".
    payload_rotas, erro_rotas = carregar_cache(projeto_dir, chave=u"rotas")
    if erro_rotas:
        _erro(postar_mensagem, erro_rotas)
        return

    def _resolve_elems(eids):
        return [doc.GetElement(to_element_id(eid)) for eid in eids]

    trechos_elems = {
        u"RTI - Bomba":      _resolve_elems(payload_rotas[u"t1"]),
        u"Bomba - Ponto A":  _resolve_elems(payload_rotas[u"t2"]),
        u"Ponto A - Hid 01": _resolve_elems(payload_rotas[u"t3"]),
        u"Ponto A - Hid 02": _resolve_elems(payload_rotas[u"t4"]),
    }
    ponto_a_elem = doc.GetElement(to_element_id(payload_rotas[u"ponto_a_id"]))

    todos_elems_rota = [e for lst in trechos_elems.values() for e in lst] + [ponto_a_elem]
    if any(e is None for e in todos_elems_rota):
        _erro(postar_mensagem, u"Um ou mais elementos do mapeamento não existem mais no projeto "
                                u"(modelo alterado desde o último mapeamento). Execute 'Mapear Trechos' novamente.")
        return

    hid_map = {
        u"HID-01": trechos_elems[u"Ponto A - Hid 01"][-1],
        u"HID-02": trechos_elems[u"Ponto A - Hid 02"][-1],
    }

    ident_map = {u"Ponto A": ponto_a_elem}
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        ident = _get_identificador(elem)
        if ident and isinstance(elem, (Pipe, FamilyInstance)):
            ident_map[ident] = elem

    faltando = [nome for nome in (u"RTI", u"Bomba") if nome not in ident_map]
    if faltando:
        _erro(postar_mensagem, u"Elementos não encontrados: {}. Execute 'Mapear Trechos' primeiro.".format(
            u", ".join(faltando)))
        return

    # Etapa 3: cotas altimétricas de todos os pontos da marcha.
    cotas = {
        u"z_rti":      get_cota_rti(ident_map[u"RTI"]),
        u"z_succao":   get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.In,)),
        u"z_recalque": get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.Out,)),
        u"z_ponto_a":  get_z(ident_map[u"Ponto A"]),
        u"z_hd01":     get_cota_conector(hid_map[u"HID-01"]),
        u"z_hd02":     get_cota_conector(hid_map[u"HID-02"]),
    }
    nomes_cotas = {
        u"z_rti": u"RTI", u"z_succao": u"Sucção", u"z_recalque": u"Recalque",
        u"z_ponto_a": u"Ponto A", u"z_hd01": u"HID-01", u"z_hd02": u"HID-02",
    }
    elem_cotas = {
        u"z_rti": ident_map.get(u"RTI"), u"z_succao": ident_map.get(u"Bomba"),
        u"z_recalque": ident_map.get(u"Bomba"),
        u"z_hd01": hid_map.get(u"HID-01"), u"z_hd02": hid_map.get(u"HID-02"),
    }
    chaves_erro = [k for k, z in cotas.items() if z is None]
    if chaves_erro:
        detalhes = [u"Não foi possível ler a elevação de:"]
        for k in chaves_erro:
            elem = elem_cotas.get(k)
            if elem is None:
                detalhes.append(u"- {}".format(nomes_cotas[k]))
                continue
            detalhes.append(u"- {} (elemento ID {}):".format(nomes_cotas[k], elem.Id))
            detalhes.extend(diagnostico_conectores(elem))
        _erro(postar_mensagem, u"\n".join(detalhes))
        return

    dados_succao = succao_calc.load_dados(doc) or succao_calc.default_dados()

    # Etapa 4: extrair dados dos trechos (por diâmetro). O motor recalcula
    # Ltotal e os totais de cada trecho — vai só o que o modelo informa.
    def _diametro_fn(chave_trecho):
        ids_no_trecho = set(get_id(e) for e in trechos_elems[chave_trecho])
        return lambda e, _ids=ids_no_trecho: get_diametro_no_trecho(e, _ids)

    try:
        trechos_data = {
            u"t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, _diametro_fn(u"RTI - Bomba"),      get_leq, get_nome, get_id),
            u"t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, _diametro_fn(u"Bomba - Ponto A"),  get_leq, get_nome, get_id),
            u"t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, _diametro_fn(u"Ponto A - Hid 01"), get_leq, get_nome, get_id),
            u"t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, _diametro_fn(u"Ponto A - Hid 02"), get_leq, get_nome, get_id),
        }
    except ValueError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return

    entrada = {
        u"uf":            sigla_estado,
        u"valor_sistema": valor_sistema,
        u"metodo":        metodo_calculo,
        u"trechos":       {k: v[u"segmentos"] for k, v in trechos_data.items()},
        u"cotas":         cotas,
        u"dados_succao":  dados_succao,
    }

    # O que só existe deste lado e entra no cache junto do resultado.
    complemento_local = {
        u"_nome_projeto":     doc.Title,
        u"ranking_hidrantes": payload_rotas.get(u"ranking"),
    }

    access_token = (payload or {}).get(u"accessToken")

    threading.Thread(
        target=_calcular_em_background,
        args=(entrada, access_token, complemento_local, projeto_dir, fila_acoes, postar_mensagem),
    ).start()


def _calcular_em_background(entrada, access_token, complemento_local, projeto_dir,
                            fila_acoes, postar_mensagem):
    """
    Etapas 2 e 3: chama o motor, grava o cache e responde à dockpane. Qualquer
    exceção vira uma resposta de erro — sem isso a dockpane ficaria em
    "Dimensionando..." para sempre (thread de fundo não tem quem a capture).
    """
    try:
        resposta = motor_nuvem.dimensionar_hidrantes(entrada, access_token)

        if resposta.get(u"ok"):
            # Mesmo formato que o pushbutton sempre gravou (e que a dockpane
            # e o site leem) — o motor devolve o resultado no formato dele, e
            # aqui entra só o que é local.
            payload_hid = dict(resposta[u"resultado"])
            payload_hid[u"timestamp"] = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
            payload_hid.update(complemento_local)
            salvar_cache(payload_hid, projeto_dir)
            mensagem = {u"ok": True}
        else:
            mensagem = {
                u"ok": False,
                u"erro": resposta.get(u"erro"),
                u"categoria": resposta.get(u"categoria") or u"norma",
            }
    except Exception as ex:
        mensagem = {
            u"ok": False,
            u"erro": u"Falha inesperada ao dimensionar: {}".format(texto_erro(ex)),
            u"categoria": u"servidor",
        }

    fila_acoes.enfileirar(lambda uiapp: postar_mensagem(_TIPO_RESPOSTA, mensagem))
