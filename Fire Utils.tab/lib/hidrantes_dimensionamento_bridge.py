# -*- coding: utf-8 -*-
"""
hidrantes_dimensionamento_bridge.py — Fire Utils · lib/
Processa GET_HIDRANTES_DIMENSIONAMENTO: a página "Sistema de Hidrantes" da
dockpane (webapp) precisa de duas coisas que não vêm do Supabase, só do
documento Revit ativo:

  1. O sistema classificado que está de fato APLICADO no projeto — Tipo,
     esguicho, mangueira, expedições, vazão/pressão mínima —, lido do
     Project Information e resolvido pelo perfil normativo do estado
     (mesma lógica de hidrantes/sistema.py, usada por "Dimensionar
     Hidrantes"). Pode divergir do que está pendente no site se "Aplicar
     classificação no Revit" ainda não foi clicado depois de uma mudança.
     RTI NÃO vem daqui — o motor de cálculo nunca lê RTI do Project
     Information (dimensiona o reservatório, não a rede hidráulica), então
     a dockpane lê direto do Supabase (dadosHidrantes(projeto).rti) — ver
     SistemaHidrantesPage.jsx.
  2. O ponto de operação do sistema (pressão/vazão nos hidrantes
     desfavoráveis, vazão e altura manométrica totais) do último
     "Dimensionar Hidrantes" — lido do cache local (firedata.json,
     hidrantes/calc.py:carregar_cache), sem precisar rodar nada de novo.

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

from hidrantes.norm_profiles import get_profile, NormProfileError
from hidrantes.sistema import resolver_dados_sistema_puro
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
        perfil = get_profile(sigla_estado)
    except NormProfileError as ex:
        postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {u"ok": False, u"erro": texto_erro(ex)})
        return

    erro, valor_sistema, dados_sistema = resolver_dados_sistema_puro(doc, perfil)
    if erro:
        postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {u"ok": False, u"erro": erro})
        return

    classificacao = dict(dados_sistema)
    classificacao[u"valorSistema"] = valor_sistema

    # 'res', dentro do cache, é o dict cru de hidrantes/calc.py:calcular_rede
    # (Qt, P_hd01/02, Q_hd01/02, P_RTI, hid_governa) — ver docstring do
    # módulo pra por que P_RTI é a "altura manométrica total" (Ht): é a
    # pressão que precisaria existir na RTI, atmosférica como referência,
    # pra alimentar o sistema por gravidade — ou seja, exatamente o que a
    # bomba precisa suprir a mais, já contando sucção e recalque.
    cache, erro_cache = hidrantes_calc.carregar_cache(projeto_dir)
    ponto_operacao = None
    if cache:
        res = cache.get(u"res") or {}
        ponto_operacao = {
            u"qt":         res.get(u"Qt"),
            u"ht":         res.get(u"P_RTI"),
            u"pHd01":      res.get(u"P_hd01"),
            u"pHd02":      res.get(u"P_hd02"),
            u"qHd01":      res.get(u"Q_hd01"),
            u"qHd02":      res.get(u"Q_hd02"),
            u"hidGoverna": res.get(u"hid_governa"),
            u"timestamp":  cache.get(u"timestamp"),
        }

    postar_mensagem(u"HIDRANTES_DIMENSIONAMENTO", {
        u"ok": True,
        u"classificacao": classificacao,
        u"pontoOperacao": ponto_operacao,
        u"erroDimensionamento": None if cache else erro_cache,
    })
