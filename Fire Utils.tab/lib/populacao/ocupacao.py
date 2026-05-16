# -*- coding: utf-8 -*-
# it11.py — Tabela IT 11 CBMSP
from populacao.db import OCUPACOES

# ============================================================
# FUNCOES AUXILIARES
# ============================================================

def get_occupancy_data(key):
    """Retorna os dados de uma ocupacao pelo codigo"""
    return OCUPACOES.get(key, None)

def get_occupancy_use(key):
    grupo = key[0]
    for codigo, dados in OCUPACOES.items():
        if dados["grupo"] == grupo:
            return dados["uso"]
        
    return None

def get_codigos():
    """Retorna lista ordenada de todos os codigos"""
    return sorted(OCUPACOES.keys())


def get_opcoes_exibidas():
    """
    Retorna lista formatada para exibir no menu.
    Formato: "D-1 -- Local para prestacao de servico..."
    """
    return [
        "{} -- {}".format(k, OCUPACOES[k]["descricao"])
        for k in get_codigos()
    ]

def get_por_grupo(grupo):
    """Retorna todas as ocupacoes de um grupo especifico"""
    return {
        k: v for k, v in OCUPACOES.items()
        if v["grupo"] == grupo.upper()
    }