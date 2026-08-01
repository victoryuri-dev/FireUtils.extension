# -*- coding: utf-8 -*-
"""
normas/MA/__init__.py — Fire Utils
Agrega as fontes normativas do Maranhão em um único ESTADO.

ESTADO mantém as chaves planas de saídas (sigla, nome, ocupacoes, tabela,
larguras_minimas, distancias_maximas...) exatamente como antes da migração
para lib/normas/ — nada que já consome estado["tabela"], estado["ocupacoes"]
etc. precisa mudar. A chave nova "hidrantes" concentra os dados de
dimensionamento de hidrantes (antes em lib/hidrantes/norm_profiles.py).
"""

from .saidas import DADOS_SAIDAS
from .hidrantes import DADOS_HIDRANTES

ESTADO = dict(DADOS_SAIDAS)
ESTADO[u"hidrantes"] = DADOS_HIDRANTES
