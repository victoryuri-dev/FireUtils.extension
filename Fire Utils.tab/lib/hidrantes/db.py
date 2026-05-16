# -*- coding: utf-8 -*-
"""
DB_HIDRANTES.py
Banco de dados da Tabela 2 da NT 22 CBMMA.
Tipos de sistemas de proteção por hidrante ou mangotinho.

Estrutura por tipo:
  - descricao        : descrição resumida do tipo
  - esguicho_dn      : DN do esguicho regulável (mm)
  - variantes        : lista de configurações possíveis dentro do tipo
      - mangueira_dn     : DN da mangueira de incêndio (mm)
      - mangueira_comp   : comprimento da mangueira (m)
      - num_expedicoes   : número de expedições ("Simples" / "Duplo")
      - vazao_min        : vazão mínima na válvula do hidrante mais desfavorável (L/min)
      - pressao_min      : pressão mínima na válvula do hidrante mais desfavorável (mca)
"""

SISTEMAS_HIDRANTE = {
    1: {
        "descricao": "Mangotinho",
        "esguicho_dn": 25,
        "variantes": [
            {
                "mangueira_dn": 25,
                "mangueira_comp": 30,
                "num_expedicoes": "Simples",
                "vazao_min": 100,
                "pressao_min": 80,
            }
        ],
    },
    2: {
        "descricao": "Hidrante Tipo 2",
        "esguicho_dn": 40,
        "variantes": [
            {
                "mangueira_dn": 40,
                "mangueira_comp": 30,
                "num_expedicoes": "Simples",
                "vazao_min": 150,
                "pressao_min": 30,
            }
        ],
    },
    3: {
        "descricao": "Hidrante Tipo 3",
        "esguicho_dn": 40,
        "variantes": [
            {
                "mangueira_dn": 40,
                "mangueira_comp": 30,
                "num_expedicoes": "Simples",
                "vazao_min": 200,
                "pressao_min": 40,
            }
        ],
    },
    4: {
        "descricao": "Hidrante Tipo 4",
        "esguicho_dn": 40,
        "variantes": [
            {
                # Variante 4A — mangueira DN 40
                "mangueira_dn": 40,
                "mangueira_comp": 30,
                "num_expedicoes": "Simples",
                "vazao_min": 300,
                "pressao_min": 65,
            },
            {
                # Variante 4B — mangueira DN 65
                "mangueira_dn": 65,
                "mangueira_comp": 30,
                "num_expedicoes": "Simples",
                "vazao_min": 300,
                "pressao_min": 30,
            },
        ],
    },
    5: {
        "descricao": "Hidrante Tipo 5",
        "esguicho_dn": 65,
        "variantes": [
            {
                "mangueira_dn": 65,
                "mangueira_comp": 30,
                "num_expedicoes": "Duplo",
                "vazao_min": 600,
                "pressao_min": 60,
            }
        ],
    },
}


def get_sistema(tipo):
    """Retorna o dicionário de um tipo de sistema. Retorna None se não existir."""
    return SISTEMAS_HIDRANTE.get(tipo, None)


def get_todos_tipos():
    """Retorna lista ordenada de todos os tipos disponíveis."""
    return sorted(SISTEMAS_HIDRANTE.keys())
