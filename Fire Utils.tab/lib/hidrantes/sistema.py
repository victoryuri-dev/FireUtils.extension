# -*- coding: utf-8 -*-
"""
sistema.py — Fire Utils · lib/hidrantes/
Resolve os dados do sistema classificado (Q mínima, pressão mínima,
DN/comprimento de mangueira, DN do esguicho) a partir da Tabela 2 do
perfil normativo ativo. A classificação (Tipo + variante) vem do site
(ETOS.FireUtils, Tabela 3 da norma) e é gravada no Project Information
por hidrantes_classificacao_bridge.py. Compartilhado por "Mapear Trechos"
(que precisa de Qs_lmin para pontuar as rotas) e "Dimensionar Hidrantes"
(que precisa do dict completo para a marcha de cálculo).
"""

from hidrantes.params import PROJECT_INFO_PARAM
from hidrantes.norm_profiles import req


def resolver_dados_sistema(doc, perfil, forms, script):
    """
    Lê 'FireUtils - Tipo de Sistema de Hidrante' do Project Information e
    resolve o dict de dados do sistema (q_min, p_min, mang_dn, mang_comp,
    esguicho_dn, todos já normalizados para float).

    Se o projeto ainda não foi classificado (ou a classificação está
    inconsistente), mostra o alerta apropriado e encerra o script — mesmo
    comportamento em qualquer botão que chame esta função.

    Retorna (valor_sistema, dados_sistema).
    """
    param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
    if not param_sistema or not param_sistema.AsString():
        forms.alert(
            u"Sistema de hidrantes ainda não classificado. Aplique a "
            u"classificação do site (botão \"Aplicar classificação no "
            u"Revit\" na dockpane) primeiro.",
            title="Fire Utils", warn_icon=True)
        script.exit()

    valor_sistema = param_sistema.AsString()

    try:    tipo_num = int(valor_sistema.split()[1])
    except:
        forms.alert(u"Não foi possível interpretar o tipo.", title="Fire Utils", warn_icon=True)
        script.exit()

    variante_idx = 0
    if u"Var." in valor_sistema:
        try:    variante_idx = ord(valor_sistema.split(u"Var.")[1].strip()[0]) - 65
        except: variante_idx = 0

    _tipo_perfil = req(perfil, u"tipos").get(tipo_num)
    if _tipo_perfil is None:
        forms.alert(
            u"O perfil normativo '{}' não define o Tipo {} de sistema de hidrante.".format(
                perfil.get(u"norma"), tipo_num),
            title="Fire Utils", warn_icon=True)
        script.exit()

    dados_sistema = dict(_tipo_perfil["variantes"][variante_idx])
    dados_sistema["esguicho_dn"] = _tipo_perfil["esguicho_dn"]

    # A Tabela 2 (hidrantes/db.py) guarda esses valores como int. O IronPython
    # 2.7 do Revit (diferente do CPython) lança ValueError em "{:.1f}".format(x)
    # quando x é int — então normalizamos tudo para float aqui.
    for _chave in (u"q_min", u"p_min", u"mang_dn", u"mang_comp", u"esguicho_dn"):
        dados_sistema[_chave] = float(dados_sistema[_chave])

    return valor_sistema, dados_sistema
