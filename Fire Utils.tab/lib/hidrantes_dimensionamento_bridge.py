# -*- coding: utf-8 -*-
"""
hidrantes_dimensionamento_bridge.py — Fire Utils · lib/
Processa GET_HIDRANTES_DIMENSIONAMENTO: a página "Sistema de Hidrantes" da
dockpane (webapp) precisa de três coisas que não vêm do Supabase, só do
documento Revit ativo:

  1. O sistema classificado que está de fato APLICADO no projeto — Tipo,
     esguicho, mangueira, expedições, vazão/pressão mínima, método de
     cálculo e coeficiente C —, lido do Project Information e resolvido
     pelo perfil normativo do estado (mesma lógica de hidrantes/sistema.py,
     usada por "Dimensionar Hidrantes"). Pode divergir do que está
     pendente no site se "Aplicar classificação no Revit" ainda não foi
     clicado depois de uma mudança. Método/coeficiente C vêm sempre
     (Project Information + perfil, independente de "Dimensionar
     Hidrantes" já ter rodado) — é o card único de classificação da
     dockpane que precisa deles completos mesmo sem dimensionamento ainda.
     RTI NÃO vem daqui — o motor de cálculo nunca lê RTI do Project
     Information (dimensiona o reservatório, não a rede hidráulica), então
     a dockpane lê direto do Supabase (dadosHidrantes(projeto).rti) — ver
     SistemaHidrantesPage.jsx.
  2. O cache COMPLETO do último "Dimensionar Hidrantes" (firedata.json,
     hidrantes/calc.py:carregar_cache) — mesmo payload que o plugin
     sincroniza com o Supabase (state.hidrantes.dimensionamento no site) —
     repassado como está, sem reduzir, pra "Dimensionamento do Sistema" da
     dockpane renderizar as mesmas seções que o site (Verificação do
     Hidrante Mais Desfavorável, Resultado Hidráulico, Verificação de
     Velocidade, Perdas de Carga por Trecho — ver HidrantesPage.jsx lá) a
     partir do mesmo formato de dado, sem duplicar a lógica de leitura.
  3. Os limites normativos de velocidade (v_max_tubulacao/v_max_succao_*) e
     o nome da norma ativa, pra "Verificação de Velocidade" e o cabeçalho
     não precisarem de uma segunda fonte de dado normativo só pra isso.

A eficiência da bomba e a potência adotada NÃO passam por aqui: são lidas
e gravadas direto no Supabase pelo próprio React (dados.hidrantes.
bombaEficiencia/bombaPotenciaAdotada — ver webapp/src/components/dashboard/
SistemaHidrantesPage.jsx), o mesmo campo que o site edita na Etapa 3
("Dimensionamento da Bomba de Incêndio"). A potência é sempre calculada do
lado do React (JS), a partir de Qt/Ht daqui + a eficiência vinda do
Supabase — não há cálculo de potência no Python (ver
src/data/hidrantes_calc.js do site pra fórmula equivalente, e
webapp/src/lib/hidrantesCalc.js aqui).
"""

import os

from hidrantes.norm_profiles import get_profile, req, opt, NormProfileError
from hidrantes.sistema import resolver_dados_sistema_puro
from hidrantes.calc import METODO_VALVULA, METODOS_CALCULO
from hidrantes.params import PROJECT_INFO_METODO_PARAM
import hidrantes.calc as hidrantes_calc
from projeto import carregar_dados_projeto
from family_error_utils import texto_erro


def _doc_ou_erro(uiapp, tipo_resposta, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        postar_mensagem(tipo_resposta, {
            u"ok": False,
            u"erro": u"Salve o projeto Revit (.rvt) antes de abrir esta página.",
        })
        return None
    return uidoc.Document


def tratar_get_hidrantes_dimensionamento(uiapp, postar_mensagem):
    doc = _doc_ou_erro(uiapp, u"HIDRANTES_DIMENSIONAMENTO", postar_mensagem)
    if doc is None:
        return
    projeto_dir = os.path.dirname(doc.PathName)

    dados_projeto = carregar_dados_projeto(projeto_dir) or {}
    sigla_estado = dados_projeto.get(u"uf") or u"MA"
    try:
        perfil = get_profile(sigla_estado, projeto_dir)
    except NormProfileError as ex:
        postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {u"ok": False, u"erro": texto_erro(ex)})
        return

    erro, valor_sistema, dados_sistema = resolver_dados_sistema_puro(doc, perfil)
    if erro:
        postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {u"ok": False, u"erro": erro})
        return

    classificacao = dict(dados_sistema)
    classificacao[u"valorSistema"] = valor_sistema

    # Método e coeficiente C lidos aqui direto (Project Information + perfil),
    # independente do cache de "Dimensionar Hidrantes" — assim o card único
    # de classificação na dockpane (Tipo/RTI/Esguicho/Mangueira/Expedições/
    # Vazão/Pressão/Método/Coef. C) fica completo mesmo que o dimensionamento
    # hidráulico ainda não tenha rodado nesta sessão. Mesma leitura/fallback
    # que "Dimensionar Hidrantes"/script.py faz pro parâmetro de método.
    _param_metodo = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
    metodo = _param_metodo.AsString() if _param_metodo else None
    if metodo not in METODOS_CALCULO:
        metodo = METODO_VALVULA
    classificacao[u"metodo"] = metodo
    classificacao[u"chw"] = opt(perfil, u"hazen_c", {}).get(u"galvanizado")

    # Cache cru de "Dimensionar Hidrantes" (res, dados_sistema, valor_sistema,
    # metodo, C_HW, succao, ranking_hidrantes, cotas... — ver payload_hid em
    # "Dimensionar Hidrantes"/script.py) — mesmo formato que o site lê de
    # state.hidrantes.dimensionamento, repassado sem reduzir.
    cache, erro_cache = hidrantes_calc.carregar_cache(projeto_dir)

    try:
        limites = {
            u"vMaxTubulacao":      req(perfil, u"v_max_tubulacao"),
            u"vMaxSuccaoPositiva": req(perfil, u"v_max_succao_positiva"),
            u"vMaxSuccaoNegativa": req(perfil, u"v_max_succao_negativa"),
        }
    except NormProfileError as ex:
        postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {u"ok": False, u"erro": texto_erro(ex)})
        return

    postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {
        u"ok": True,
        u"classificacao": classificacao,
        u"norma": perfil.get(u"norma"),
        u"limites": limites,
        u"dimensionamento": cache,
        u"erroDimensionamento": None if cache else erro_cache,
    })


def tratar_selecionar_trecho_hidrante(uiapp, payload):
    """
    Processa SELECIONAR_TRECHO_HIDRANTE: botão "Localizar" da tabela
    "Verificação do Hidrante Mais Desfavorável" na dockpane (ver
    HidrantesDimensionamento.jsx) — seleciona e enquadra, na view ativa do
    Revit, todo o trecho (Bomba -> válvula) daquele hidrante.
    `payload["rota"]` é a lista de ElementId (int) de um item de
    `ranking_hidrantes` (gravada por "Mapear Trechos"/script.py, repassada
    sem reduzir pelo cache de "Dimensionar Hidrantes" — ver
    tratar_get_hidrantes_dimensionamento acima). Fire-and-forget: não manda
    nada de volta pro React — sucesso já é visível no Revit, e
    mostrar_no_revit mostra seu próprio alerta nativo em caso de falha
    (mesmo padrão dos botões "Localizar"/"Mostrar no Projeto" das janelas
    WPF do pushbutton "Mapear Trechos" — ver hidrantes/resultado_ui.py).
    """
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        return
    ids = payload.get(u"rota") or []
    if not ids:
        return
    from hidrantes.rede import mostrar_no_revit
    mostrar_no_revit(uidoc, ids)
