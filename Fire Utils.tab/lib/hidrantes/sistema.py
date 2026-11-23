# -*- coding: utf-8 -*-
"""
sistema.py — Fire Utils · lib/hidrantes/
Resolve os dados do sistema classificado (Q mínima, pressão mínima,
DN/comprimento de mangueira, DN do esguicho, expedições) a partir do texto
gravado no Project Information. O site (ETOS.FireUtils) interpreta o Tipo
(Tabelas 2 e 3 da norma, ou um sistema personalizado) e manda os valores
prontos, gravados por hidrantes_classificacao_bridge.py — o plugin não tem
tabela de Tipos própria. Compartilhado por "Mapear Trechos"
(que precisa de Qs_lmin para pontuar as rotas) e "Dimensionar Hidrantes"
(que precisa do dict completo para a marcha de cálculo).
"""

import re

from hidrantes.params import PROJECT_INFO_PARAM


_NUM = u"(\\d+(?:[.,]\\d+)?)"


def _num(texto):
    return float(texto.replace(u",", u"."))


def interpretar_valor_sistema(valor_sistema):
    """
    Interpreta o texto gravado em 'FireUtils - Tipo de Sistema de Hidrante':

        <Tipo N [– Var. X] | Personalizado> – DN <mangueira> | <Q> L/min |
        <P> mca | Esg DN <esguicho> | <comprimento> m | <expedições>

    O SITE decide o Tipo (da norma ou personalizado) e manda os valores já
    resolvidos (ver hidrantes_classificacao_bridge.py): o plugin não tem
    tabela de Tipos — só lê o que foi gravado. Retorna (erro, dados_sistema).
    """
    texto = (valor_sistema or u"").strip()
    m_tipo = re.match(u"^(Personalizado|Tipo\\s+(\\d+))", texto)
    if not m_tipo:
        return u"Não foi possível interpretar o tipo.", None

    def pega(padrao):
        m = re.search(padrao, texto, re.IGNORECASE)
        return m.group(1) if m else None

    mang = pega(u"DN\\s*" + _NUM + u"\\s*\\|")
    q = pega(_NUM + u"\\s*L/min")
    p = pega(_NUM + u"\\s*mca")
    esg = pega(u"Esg\\s*DN\\s*" + _NUM)
    comp = pega(u"\\|\\s*" + _NUM + u"\\s*m\\s*\\|")
    exp = pega(u"\\|\\s*(simples|duplo)\\s*$")
    if None in (mang, q, p, esg, comp, exp):
        return (u"A classificação gravada neste projeto está incompleta (versão antiga). "
                u"Aplique a classificação do site no Revit novamente."), None

    variante_idx = 0
    m_var = re.search(u"Var\\.\\s*([A-Za-z])", texto)
    if m_var:
        variante_idx = ord(m_var.group(1).upper()) - 65

    # float(): o IronPython 2.7 do Revit lança ValueError em "{:.1f}".format(int).
    dados_sistema = {
        u"q_min": _num(q), u"p_min": _num(p),
        u"mang_dn": _num(mang), u"mang_comp": _num(comp), u"esguicho_dn": _num(esg),
        u"expedicoes": exp.lower(),
        u"tipo": int(m_tipo.group(2)) if m_tipo.group(2) else None,
        u"personalizado": m_tipo.group(1) == u"Personalizado",
        u"variante_idx": variante_idx,
        u"descricao": None,
    }
    if dados_sistema[u"q_min"] <= 0 or dados_sistema[u"p_min"] <= 0:
        return u"A classificação define vazão ou pressão mínima não positiva.", None
    return None, dados_sistema


def resolver_dados_sistema_puro(doc, perfil):
    """
    Lê 'FireUtils - Tipo de Sistema de Hidrante' do Project Information e
    interpreta o texto gravado (ver interpretar_valor_sistema) — sem tabela
    de Tipos: os valores vêm do site. `perfil` fica na assinatura só por
    compatibilidade com os chamadores (o perfil continua valendo para o
    resto do cálculo, ex.: coeficiente C).

    Retorna (erro, valor_sistema, dados_sistema): 'erro' é None em caso de
    sucesso, e nesse caso 'valor_sistema'/'dados_sistema' vêm preenchidos;
    caso contrário os dois vêm None e 'erro' é a mensagem pronta pra exibir.
    """
    param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
    if not param_sistema or not param_sistema.AsString():
        return (
            u"Sistema de hidrantes ainda não classificado. Aplique a "
            u"classificação do site (botão \"Aplicar classificação no "
            u"Revit\" na dockpane) primeiro.",
            None, None)

    valor_sistema = param_sistema.AsString()
    erro, dados_sistema = interpretar_valor_sistema(valor_sistema)
    if erro:
        return erro, None, None
    return None, valor_sistema, dados_sistema


def resolver_dados_sistema(doc, perfil, forms, script):
    """
    Wrapper de resolver_dados_sistema_puro pros pushbuttons: mostra o
    alerta apropriado e encerra o script se a classificação ainda não
    existir ou estiver inconsistente — mesmo comportamento em qualquer
    botão que chame esta função.

    Retorna (valor_sistema, dados_sistema).
    """
    erro, valor_sistema, dados_sistema = resolver_dados_sistema_puro(doc, perfil)
    if erro:
        forms.alert(erro, title="Fire Utils", warn_icon=True)
        script.exit()

    return valor_sistema, dados_sistema
