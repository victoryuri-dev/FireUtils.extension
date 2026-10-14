# -*- coding: utf-8 -*-
"""
hydrant_shared.py — Fire Utils · lib/
Constantes e helpers de hidrante usados por mais de um botão — extraídos
de hydrant_insert_core.py pra não forçar quem só precisa disto (ex.:
connect_shelter_core_preview.py, no "Conectar Abrigo") a importar o
arquivo inteiro (run_coluna_multilevel, _JanelaOpcoesColuna etc. — a
maior parte de hydrant_insert_core.py, sem relação com Conectar Abrigo).
Python executa o corpo de um módulo inteiro no import, não só os nomes
pedidos, então um módulo pequeno e focado custa menos nesse caminho.

hydrant_insert_core.py reimporta estes nomes daqui (em vez de duplicá-los)
pra manter uma única definição de cada um.
"""

import math

from Autodesk.Revit.DB import BuiltInParameter

ALTURA_VALVULA_M = 1.30
COMP_HORIZ_M     = 0.20
DIAM_RAMAL_M     = 0.065
TOL              = 1e-4


def _setar_diametro_ft(pipe, d_ft):
    for bip in [BuiltInParameter.RBS_PIPE_OUTER_DIAMETER,
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM]:
        try:
            p = pipe.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(d_ft)
                return True
        except Exception:
            pass
    return False


def _angulo_entre(v_de, v_para):
    return math.atan2(v_para.Y, v_para.X) - math.atan2(v_de.Y, v_de.X)


def _conector_mais_proximo(familia_inst, pt):
    """Retorna o conector MEP da família mais próximo de pt."""
    try:
        mgr = familia_inst.MEPModel.ConnectorManager
    except Exception:
        return None
    melhor, menor_dist = None, float('inf')
    for conn in mgr.Connectors:
        d = conn.Origin.DistanceTo(pt)
        if d < menor_dist:
            menor_dist = d
            melhor = conn
    return melhor
