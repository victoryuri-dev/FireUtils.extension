# -*- coding: utf-8 -*-
"""
normas/MA/hidrantes.py — Fire Utils
Dados normativos de dimensionamento de hidrantes do Maranhão — CBM-MA.

Norma de referência: NT 22/2021 - CBMMA

Todo parametro normativo usado pelo motor de calculo e pelas verificacoes do
memorial (Pmin, Qmin, limites de velocidade, ponto de referencia de Pmin,
coeficiente de Hazen-Williams, numero de hidrantes simultaneos, tolerancia de
equilibrio no no de derivacao etc.) vive aqui - nunca hardcoded no motor
(hidrantes/calc.py) ou no script de apresentacao (Dimensionar Hidrantes).
"""

# Import absoluto obrigatorio: este arquivo se chama "hidrantes.py" (mesmo
# nome do pacote de nivel superior lib/hidrantes/). Sem absolute_import, o
# Python 2 / IronPython resolve "from hidrantes.db import ..." como import
# relativo primeiro, conflita consigo mesmo e lanca
# "ImportError: No module named db".
from __future__ import absolute_import
from hidrantes.db import SISTEMAS_HIDRANTE


def _tipos_de_db():
    """
    Deriva a secao 'tipos' (Tabela 2) a partir de hidrantes/db.py, que continua
    sendo a fonte unica desses dados (usada tambem por Classificar Sistema e
    hidrantes/forms.py). Isso evita duplicar/hardcodar os mesmos valores em
    dois lugares - aqui apenas renomeamos as chaves para o vocabulario da
    Tabela 2 (q_min/p_min/mang_dn/mang_comp) usado pelas verificacoes.
    """
    tipos = {}
    for tipo_num, dados in SISTEMAS_HIDRANTE.items():
        tipos[tipo_num] = {
            u"descricao":   dados[u"descricao"],
            u"esguicho_dn": dados[u"esguicho_dn"],
            u"variantes": [
                {
                    u"mang_dn":   v[u"mangueira_dn"],
                    u"mang_comp": v[u"mangueira_comp"],
                    u"q_min":     v[u"vazao_min"],
                    u"p_min":     v[u"pressao_min"],
                }
                for v in dados[u"variantes"]
            ],
        }
    return tipos


DADOS_HIDRANTES = {
    u"norma": u"NT 22/2021 - CBMMA",

    u"hidrantes_simultaneos": 2,
    u"hidrantes_simultaneos_ref": u"NT 22 itens 5.8.3 / 5.8.8",

    # Tabela 2 - Tipos de sistema (derivada de hidrantes/db.py)
    u"tipos": _tipos_de_db(),
    u"tipos_ref": u"NT 22 Tabela 2",

    u"v_max_tubulacao": 5.0,
    u"v_max_tubulacao_ref": u"NT 22 item 5.8.13",

    u"v_max_succao_positiva": 3.0,
    u"v_max_succao_negativa": 2.0,
    u"v_max_succao_ref": u"NT 22 item 5.8.12",

    # -- Condicao de succao pelo nivel X --------------------------------
    # As tabelas de dimensoes (A/B) e a mecanica do nivel X vivem em
    # hidrantes/succao.py, por serem praticamente gerais entre normas; o que
    # muda de estado para estado - e portanto mora aqui - sao os valores
    # normativos e as citacoes exibidas no memorial.
    u"succao_tolerancia_max": 2.0,

    u"succao_ref":            u"NT 22 Anexo B.3",
    u"succao_condicao_ref":   u"NT 22 item C.1.10",
    u"succao_capacidade_ref": u"NT 22 item B.3.3",
    u"succao_antivortice_ref": u"NT 22 itens B.3.5/B.3.6",
    u"succao_dimensoes_ref":  u"NT 22 Tabela B.1",
    u"succao_rti_min_ref":    u"NT 22 Tabela 3",

    # -- NPSH disponivel (exigido quando a succao e negativa) ------------
    # Majoracao normativa da vazao usada SO nesta verificacao.
    u"npshd_fator_vazao": 1.5,
    u"npshd_ref":         u"NT 22 item 5.8.16",

    # Tabela 1 - Coeficiente de Hazen-Williams por material
    u"hazen_c": {
        u"galvanizado":       120,
        u"aco_preto_molhado": 120,
        u"ff_sem_revest":     100,
        u"ff_revest_cimento": 140,
        u"plastico":          150,
        u"cobre":             150,
    },
    u"hazen_c_ref": u"NT 22 Tabela 1",
}
