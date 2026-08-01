# -*- coding: utf-8 -*-
"""
normas/PE/saidas.py — Fire Utils
Dados normativos de saídas de emergência de Pernambuco — CBMPE.

Normas de referência:
  - Classificação de ocupações : NT-018 CBMPE
  - Saídas de emergência       : NT-018 CBMPE

Classificação oficial (Art. da NT-018):
  I   - Tipo A  Residencial Privativa Unifamiliar
  II  - Tipo B  Residencial Privativa Multifamiliar
  III - Tipo C  Residencial Coletiva
  IV  - Tipo D  Residencial Transitória
  V   - Tipo E  Comercial
  VI  - Tipo F  Escritório
  VII - Tipo G  Mista
  VIII- Tipo H  Reunião de Público
  IX  - Tipo I  Hospitalar
  X   - Tipo J  Pública
  XI  - Tipo K  Escolar
  XII - Tipo L  Industrial
  XIII- Tipo M  Garagem
  XIV - Tipo N  Galpão ou Depósito
  XV  - Tipo O  Derivados de petróleo / álcool / produtos perigosos
  XVI - Tipo P  Templos Religiosos
  XVII- Tipo Q  Especiais
"""

from fractions import Fraction

# =============================================================================
# HELPERS locais
# =============================================================================

def _dist(sd_su, sd_ms, cd_su, cd_ms):
    """Monta dict de distâncias para um tipo de pavimento."""
    return {
        u"sem_chuveiro": {
            u"saida_unica": {u"sem_deteccao": sd_su[0], u"com_deteccao": sd_su[1]},
            u"mais_saidas": {u"sem_deteccao": sd_ms[0], u"com_deteccao": sd_ms[1]},
        },
        u"com_chuveiro": {
            u"saida_unica": {u"sem_deteccao": cd_su[0] if cd_su else None,
                             u"com_deteccao": cd_su[1] if cd_su else None},
            u"mais_saidas": {u"sem_deteccao": cd_ms[0] if cd_ms else None,
                             u"com_deteccao": cd_ms[1] if cd_ms else None},
        },
    }


# =============================================================================
# ESTADO
# =============================================================================

DADOS_SAIDAS = {

    # -------------------------------------------------------------------------
    # Metadados
    # -------------------------------------------------------------------------
    u"sigla":           u"PE",
    u"nome":            u"Pernambuco",
    u"corpo":           u"CBMPE",
    u"norma_ocupacoes": u"NT-018 CBMPE",
    u"norma_saidas":    u"NT-018 CBMPE",

    # -------------------------------------------------------------------------
    # Classificação das ocupações — exatamente conforme NT-018 CBMPE
    # Sub-tipos são chaves planas (sem dicts aninhados).
    # -------------------------------------------------------------------------
    u"ocupacoes": {

        # Tipo A — Residencial Privativa Unifamiliar
        u"A": {
            u"grupo":    u"A",
            u"uso":      u"Residencial Privativa Unifamiliar",
            u"descricao": u"Casa isolada, sobrado e assemelhados",
        },

        # Tipo B — Residencial Privativa Multifamiliar
        u"B": {
            u"grupo":    u"B",
            u"uso":      u"Residencial Privativa Multifamiliar",
            u"descricao": u"Apartamento, flat, kitnet e assemelhados",
        },

        # Tipo C — Residencial Coletiva
        u"C": {
            u"grupo":    u"C",
            u"uso":      u"Residencial Coletiva",
            u"descricao": u"Pensão, república, alojamento coletivo e assemelhados",
        },

        # Tipo D — Residencial Transitória
        u"D": {
            u"grupo":    u"D",
            u"uso":      u"Residencial Transitória",
            u"descricao": u"Hotel, pousada, motel, hostel e assemelhados",
        },

        # Tipo E — Comercial
        u"E": {
            u"grupo":    u"E",
            u"uso":      u"Comercial",
            u"descricao": u"Loja, mercado, shopping, supermercado e assemelhados",
        },

        # Tipo F — Escritório
        u"F": {
            u"grupo":    u"F",
            u"uso":      u"Escritório",
            u"descricao": u"Escritório, banco, consultório, co-working e assemelhados",
        },

        # Tipo G — Mista
        u"G": {
            u"grupo":    u"G",
            u"uso":      u"Mista",
            u"descricao": u"Edificação com duas ou mais ocupações distintas",
        },

        # Tipo H — Reunião de Público (sub-tipos por capacidade)
        u"H - Estadios": {
            u"grupo":    u"H",
            u"uso":      u"Reunião de Público",
            u"descricao": u"Estádio, arena, ginásio e locais de grande concentração",
        },
        u"H - Demais": {
            u"grupo":    u"H",
            u"uso":      u"Reunião de Público",
            u"descricao": u"Teatro, cinema, clube, restaurante, boate e assemelhados",
        },

        # Tipo I — Hospitalar
        u"I": {
            u"grupo":    u"I",
            u"uso":      u"Hospitalar",
            u"descricao": u"Hospital, maternidade, clínica com internação e assemelhados",
        },

        # Tipo J — Pública
        u"J": {
            u"grupo":    u"J",
            u"uso":      u"Pública",
            u"descricao": u"Repartição pública, tribunal, biblioteca pública e assemelhados",
        },

        # Tipo K — Escolar (sub-tipos por pavimento)
        u"K - Terreo": {
            u"grupo":    u"K",
            u"uso":      u"Escolar",
            u"descricao": u"Escola, faculdade, creche — pavimento térreo",
        },
        u"K - Demais": {
            u"grupo":    u"K",
            u"uso":      u"Escolar",
            u"descricao": u"Escola, faculdade, creche — demais pavimentos",
        },

        # Tipo L — Industrial
        u"L": {
            u"grupo":    u"L",
            u"uso":      u"Industrial",
            u"descricao": u"Indústria em geral",
        },

        # Tipo M — Garagem
        u"M": {
            u"grupo":    u"M",
            u"uso":      u"Garagem",
            u"descricao": u"Garagem, estacionamento coberto e pátio de veículos",
        },

        # Tipo N — Galpão ou Depósito
        u"N": {
            u"grupo":    u"N",
            u"uso":      u"Galpão ou Depósito",
            u"descricao": u"Galpão, depósito, armazém e assemelhados",
        },

        # Tipo O — Derivados de petróleo / álcool / produtos perigosos
        u"O": {
            u"grupo":    u"O",
            u"uso":      u"Produção / Armazenamento de Produtos Perigosos",
            u"descricao": (
                u"Produção, manipulação, armazenamento e distribuição de "
                u"derivados de petróleo e/ou álcool e/ou produtos perigosos"
            ),
        },

        # Tipo P — Templos Religiosos
        u"P": {
            u"grupo":    u"P",
            u"uso":      u"Templos Religiosos",
            u"descricao": u"Igreja, templo, mesquita, sinagoga e assemelhados",
        },

        # Tipo Q — Especiais
        u"Q": {
            u"grupo":    u"Q",
            u"uso":      u"Especiais",
            u"descricao": u"Ocupação especial — ver conformidade específica NT-018",
        },
    },

    # -------------------------------------------------------------------------
    # Tabela de taxa populacional + capacidades de saída por UP
    # A   : m²/pessoa  (None = cálculo por leito / dormitório / vaga)
    # AD  : pessoas/UP — Acessos e Descargas
    # ER  : pessoas/UP — Escadas e Rampas
    # PT  : pessoas/UP — Portas
    # -------------------------------------------------------------------------
    u"tabela": {

        # A — Residencial unifamiliar: isenta
        u"A": {
            u"A": None,
            u"AD": 60, u"ER": 45, u"PT": 100,
            u"obs": u"Isenta — 2 pessoas por dormitório (quando aplicável)",
            u"notas": [u"C"],
        },

        # B — Residencial multifamiliar: 2 pessoas por dormitório
        u"B": {
            u"A": None,
            u"AD": 60, u"ER": 45, u"PT": 100,
            u"obs": u"2 pessoas por dormitório",
            u"notas": [u"C"],
        },

        # C — Residencial coletiva: 2 pessoas por dormitório
        u"C": {
            u"A": None,
            u"AD": 60, u"ER": 45, u"PT": 100,
            u"obs": u"2 pessoas por dormitório",
            u"notas": [u"C"],
        },

        # D — Residencial transitória (hotel/pousada): 2 pessoas por dormitório
        u"D": {
            u"A": None,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"2 pessoas por dormitório",
            u"notas": [u"C"],
        },

        # E — Comercial: 1 pessoa por 3m²
        u"E": {
            u"A": 3,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por 3m²",
            u"notas": [u"E"],
        },

        # F — Escritório: 1 pessoa por 9m²
        u"F": {
            u"A": 9,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por 9m²",
            u"notas": [u"E"],
        },

        # G — Mista: usar a taxa da ocupação mais restritiva presente
        u"G": {
            u"A": None,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"Usar a taxa da ocupação de maior densidade presente na edificação",
            u"notas": [u"I"],
        },

        # H — Reunião de Público
        u"H - Estadios": {
            u"A": Fraction(1, 2),
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"2 pessoas por m² — estádios, arenas e ginásios",
            u"notas": [u"N"],
        },
        u"H - Demais": {
            u"A": 1,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por m² — teatro, cinema, clube, boate e assemelhados",
            u"notas": [u"N"],
        },

        # I — Hospitalar: 1,5 pessoa por leito
        u"I": {
            u"A": None,
            u"AD": 30, u"ER": 22, u"PT": 30,
            u"obs": u"1,5 pessoa por leito",
            u"notas": [u"H"],
        },

        # J — Pública: 1 pessoa por 9m²
        u"J": {
            u"A": 9,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por 9m²",
            u"notas": [u"E"],
        },

        # K — Escolar
        u"K - Terreo": {
            u"A": 3,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por 3m² — térreo",
            u"notas": [u"E", u"N"],
        },
        u"K - Demais": {
            u"A": 5,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por 5m² — demais pavimentos",
            u"notas": [u"E", u"N"],
        },

        # L — Industrial: 1 pessoa por 20m²
        u"L": {
            u"A": 20,
            u"AD": 100, u"ER": 60, u"PT": 100,
            u"obs": u"1 pessoa por 20m²",
            u"notas": [],
        },

        # M — Garagem: 1 pessoa por 20 vagas
        u"M": {
            u"A": None,
            u"AD": 100, u"ER": 60, u"PT": 100,
            u"obs": u"1 pessoa por 20 vagas de veículo",
            u"notas": [],
        },

        # N — Galpão ou Depósito: 1 pessoa por 30m²
        u"N": {
            u"A": 30,
            u"AD": 100, u"ER": 60, u"PT": 100,
            u"obs": u"1 pessoa por 30m²",
            u"notas": [],
        },

        # O — Derivados de petróleo / produtos perigosos: 1 pessoa por 20m²
        u"O": {
            u"A": 20,
            u"AD": 100, u"ER": 60, u"PT": 100,
            u"obs": u"1 pessoa por 20m²",
            u"notas": [u"I"],
        },

        # P — Templos Religiosos: 1 pessoa por m²
        u"P": {
            u"A": 1,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"1 pessoa por m²",
            u"notas": [u"N"],
        },

        # Q — Especiais: consultar conformidade específica
        u"Q": {
            u"A": None,
            u"AD": 100, u"ER": 75, u"PT": 100,
            u"obs": u"Consultar conformidade específica NT-018",
            u"notas": [u"I"],
        },
    },

    # -------------------------------------------------------------------------
    # Notas normativas
    # -------------------------------------------------------------------------
    u"notas": {
        u"C": (u"(C) Em habitações unifamiliares e multifamiliares de até 2 dormitórios, "
               u"a sala deve ser considerada como dormitório. Em unidades maiores, "
               u"todos os ambientes que possam funcionar como dormitório são contabilizados."),
        u"E": u"(E) Por Área entende-se a área do pavimento que abriga a população em foco.",
        u"H": (u"(H) Em edificações hospitalares, o cálculo é de 1,5 pessoa por leito. "
               u"Para área de ambulatório, acrescer 1 pessoa por 7m²."),
        u"I": u"(I) Ocupação especial ou mista: necessário consultar a NT-018 CBMPE e normas específicas.",
        u"N": u"(N) Para o cálculo da população, será admitido o leiaute dos assentos permanentes apresentado em planta.",
    },

    # -------------------------------------------------------------------------
    # Larguras mínimas (NT-018 CBMPE)
    # -------------------------------------------------------------------------
    u"larguras_minimas": {
        u"AD": 1.10,
        u"ER": 1.10,
        u"PT": [
            {u"n_up": 1, u"largura": 0.80, u"tipo": u"1 folha"},
            {u"n_up": 2, u"largura": 1.00, u"tipo": u"1 folha"},
            {u"n_up": 3, u"largura": 1.50, u"tipo": u"2 folhas"},
            {u"n_up": 4, u"largura": 2.00, u"tipo": u"2 folhas"},
        ],
    },

    # -------------------------------------------------------------------------
    # Distâncias máximas a percorrer (metros) — NT-018 CBMPE
    # Grupos de distância:
    #   ABCD  → Residencial (A, B, C, D)
    #   EFGHIJKP → Comercial, Escritório, Mista, Reunião, Hospitalar, Pública, Escolar, Templos
    #   M     → Garagem
    #   LNO   → Industrial, Depósito e Produtos Perigosos
    #   Q     → Especiais (conformidade específica → None)
    # -------------------------------------------------------------------------
    u"distancias_maximas": {

        u"mapa_ocupacao": {
            u"A":            u"ABCD",
            u"B":            u"ABCD",
            u"C":            u"ABCD",
            u"D":            u"ABCD",
            u"E":            u"EFGHIJKP",
            u"F":            u"EFGHIJKP",
            u"G":            u"EFGHIJKP",
            u"H - Estadios": u"EFGHIJKP",
            u"H - Demais":   u"EFGHIJKP",
            u"I":            u"EFGHIJKP",
            u"J":            u"EFGHIJKP",
            u"K - Terreo":   u"EFGHIJKP",
            u"K - Demais":   u"EFGHIJKP",
            u"L":            u"LNO",
            u"M":            u"M",
            u"N":            u"LNO",
            u"O":            u"LNO",
            u"P":            u"EFGHIJKP",
            u"Q":            None,   # conformidade específica
        },

        u"grupos": {

            u"ABCD": {
                u"descricao": u"Residencial (A, B, C e D)",
                u"terreo": _dist((45, 55), (55, 65), (60, 70), (80, 95)),
                u"demais": _dist((40, 45), (50, 60), (55, 65), (75, 90)),
            },

            u"EFGHIJKP": {
                u"descricao": (
                    u"Comercial, Escritório, Mista, Reunião de Público, "
                    u"Hospitalar, Pública, Escolar e Templos (E, F, G, H, I, J, K e P)"
                ),
                u"terreo": _dist((40, 45), (50, 60), (55, 65), (75, 90)),
                u"demais": _dist((30, 35), (40, 45), (45, 55), (65, 75)),
            },

            u"M": {
                u"descricao": u"Garagem (M)",
                u"terreo": _dist((50, 60), (60, 70), (60, 70), (90, 110)),
                u"demais": _dist((45, 55), (55, 65), (55, 65), (80, 95)),
            },

            u"LNO": {
                u"descricao": u"Industrial, Depósito e Produtos Perigosos (L, N e O)",
                u"terreo": _dist((40, 45), (50, 60), (55, 65), (75, 90)),
                u"demais": _dist((30, 35), (40, 45), (45, 55), (65, 75)),
            },
        },
    },
}
