# -*- coding: utf-8 -*-
"""
normas/PE/__init__.py — Fire Utils
Agrega as fontes normativas de Pernambuco em um único ESTADO.

PE ainda não tem dados de hidrantes cadastrados nesta extensão — a chave
"hidrantes" simplesmente não existe no ESTADO até que sejam levantados
(get_profile() de lib/hidrantes/norm_profiles.py cai para o perfil "MA"
nesse caso, com aviso no memorial — nunca inventa valores para PE).
"""

from .saidas import DADOS_SAIDAS

ESTADO = dict(DADOS_SAIDAS)
