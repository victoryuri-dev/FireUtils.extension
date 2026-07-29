# -*- coding: utf-8 -*-
"""
estados/MA.py — Fire Utils
Dados normativos do Maranhão — CBM-MA.

Normas de referência:
  - Ocupações / taxa populacional : NT-01/2021 CBM-MA  (+ IT 11 CBMSP adaptada)
  - Saídas de emergência          : IT 11 CBMSP (adotada pelo MA)
"""

from fractions import Fraction

# =============================================================================
# HELPERS locais
# =============================================================================

def _dist(sd_su, sd_ms, cd_su, cd_ms):
    """Monta dict de distâncias para um tipo de pavimento."""
    return {
        u"sem_chuveiro": {
            u"saida_unica":  {u"sem_deteccao": sd_su[0], u"com_deteccao": sd_su[1]},
            u"mais_saidas":  {u"sem_deteccao": sd_ms[0], u"com_deteccao": sd_ms[1]},
        },
        u"com_chuveiro": {
            u"saida_unica":  {u"sem_deteccao": cd_su[0] if cd_su else None,
                              u"com_deteccao": cd_su[1] if cd_su else None},
            u"mais_saidas":  {u"sem_deteccao": cd_ms[0] if cd_ms else None,
                              u"com_deteccao": cd_ms[1] if cd_ms else None},
        },
    }


# =============================================================================
# ESTADO
# =============================================================================

ESTADO = {

    # -------------------------------------------------------------------------
    # Metadados
    # -------------------------------------------------------------------------
    u"sigla":            u"MA",
    u"nome":             u"Maranhão",
    u"corpo":            u"CBM-MA",
    u"norma_ocupacoes":  u"NT-01/2021 CBM-MA",
    u"norma_saidas":     u"IT 11 CBMSP (adotada pelo MA)",

    # -------------------------------------------------------------------------
    # Tabela 1 — Classificação das ocupações
    # Chaves devem coincidir com as chaves de "tabela" abaixo.
    # -------------------------------------------------------------------------
    u"ocupacoes": {

        # Grupo A — Residencial
        u"A-1": {u"grupo": u"A", u"uso": u"Residencial",
                 u"descricao": u"Habitação unifamiliar"},
        u"A-2": {u"grupo": u"A", u"uso": u"Residencial",
                 u"descricao": u"Habitação multifamiliar"},
        u"A-3": {u"grupo": u"A", u"uso": u"Residencial",
                 u"descricao": u"Habitação coletiva"},

        # Grupo B — Hospedagem
        u"B-1": {u"grupo": u"B", u"uso": u"Serviço de Hospedagem",
                 u"descricao": u"Hotel e assemelhado"},
        u"B-2": {u"grupo": u"B", u"uso": u"Serviço de Hospedagem",
                 u"descricao": u"Hotel residencial"},

        # Grupo C — Comercial
        u"C-1": {u"grupo": u"C", u"uso": u"Comercial",
                 u"descricao": u"Comércio com baixa carga de incêndio"},
        u"C-2": {u"grupo": u"C", u"uso": u"Comercial",
                 u"descricao": u"Comércio com média e alta carga de incêndio"},
        u"C-3": {u"grupo": u"C", u"uso": u"Comercial",
                 u"descricao": u"Shopping centers"},

        # Grupo D — Serviço Profissional
        u"D-1": {u"grupo": u"D", u"uso": u"Serviço Profissional",
                 u"descricao": u"Local para prestação de serviço profissional"},
        u"D-2": {u"grupo": u"D", u"uso": u"Serviço Profissional",
                 u"descricao": u"Agência bancária"},
        u"D-3": {u"grupo": u"D", u"uso": u"Serviço Profissional",
                 u"descricao": u"Serviço de reparação"},
        u"D-4": {u"grupo": u"D", u"uso": u"Serviço Profissional",
                 u"descricao": u"Laboratório"},

        # Grupo E — Educacional e Cultura Física
        u"E-1": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Escola em geral"},
        u"E-2": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Escola especial"},
        u"E-3": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Espaço para cultura física"},
        u"E-4": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Centro de treinamento profissional"},
        u"E-5": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Pré-escola"},
        u"E-6": {u"grupo": u"E", u"uso": u"Educacional e Cultura Física",
                 u"descricao": u"Escola para portadores de deficiências"},

        # Grupo F — Reunião de Público
        u"F-1":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Local com objeto de valor inestimável"},
        u"F-2":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Local religioso e velório"},
        u"F-3":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Centro esportivo e de exibição"},
        u"F-4":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Estação e terminal de passageiros"},
        u"F-5":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Arte cênica e auditório"},
        u"F-6":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Clubes sociais e salão de festas"},
        u"F-7":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Eventos temporários"},
        u"F-8":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Local para refeição"},
        u"F-9":  {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Recreação pública"},
        u"F-10": {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Exposição de objetos ou animais"},
        u"F-11": {u"grupo": u"F", u"uso": u"Local de Reunião de Público",
                  u"descricao": u"Boates"},

        # Grupo G — Serviço Automotivo
        u"G-1": {u"grupo": u"G", u"uso": u"Serviço Automotivo",
                 u"descricao": u"Garagem sem acesso ao público e sem abastecimento"},
        u"G-2": {u"grupo": u"G", u"uso": u"Serviço Automotivo",
                 u"descricao": u"Garagem com acesso ao público e sem abastecimento"},
        u"G-3": {u"grupo": u"G", u"uso": u"Serviço Automotivo",
                 u"descricao": u"Local dotado de abastecimento de combustível"},
        u"G-4": {u"grupo": u"G", u"uso": u"Serviço Automotivo",
                 u"descricao": u"Serviço de conservação, manutenção e reparos"},
        u"G-5": {u"grupo": u"G", u"uso": u"Serviço Automotivo",
                 u"descricao": u"Hangares"},

        # Grupo H — Saúde e Institucional
        u"H-1": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Hospital veterinário"},
        u"H-2": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Local para cuidados especiais"},
        u"H-3": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Hospital e assemelhado"},
        u"H-4": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Edificações das forças armadas e policiais"},
        u"H-5": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Local onde a liberdade das pessoas sofre restrições"},
        u"H-6": {u"grupo": u"H", u"uso": u"Saúde e Institucional",
                 u"descricao": u"Clínica e consultório médico e odontológico"},

        # Grupo I — Indústria
        u"I-1": {u"grupo": u"I", u"uso": u"Indústria",
                 u"descricao": u"Indústria com carga de incêndio até 300 MJ/m²"},
        u"I-2": {u"grupo": u"I", u"uso": u"Indústria",
                 u"descricao": u"Indústria com carga de incêndio de 300 a 1.200 MJ/m²"},
        u"I-3": {u"grupo": u"I", u"uso": u"Indústria",
                 u"descricao": u"Indústria com carga de incêndio superior a 1.200 MJ/m²"},

        # Grupo J — Depósito
        u"J-1": {u"grupo": u"J", u"uso": u"Depósito",
                 u"descricao": u"Depósito de material incombustível"},
        u"J-2": {u"grupo": u"J", u"uso": u"Depósito",
                 u"descricao": u"Depósito com carga de incêndio até 300 MJ/m²"},
        u"J-3": {u"grupo": u"J", u"uso": u"Depósito",
                 u"descricao": u"Depósito com carga de incêndio de 300 a 1.200 MJ/m²"},
        u"J-4": {u"grupo": u"J", u"uso": u"Depósito",
                 u"descricao": u"Depósito com carga de incêndio superior a 1.200 MJ/m²"},

        # Grupo K — Energia
        u"K-1": {u"grupo": u"K", u"uso": u"Energia",
                 u"descricao": u"Central de transmissão e distribuição de energia"},

        # Grupo L — Explosivo
        u"L-1": {u"grupo": u"L", u"uso": u"Explosivo", u"descricao": u"Comércio de explosivos"},
        u"L-2": {u"grupo": u"L", u"uso": u"Explosivo", u"descricao": u"Indústria de material explosivo"},
        u"L-3": {u"grupo": u"L", u"uso": u"Explosivo", u"descricao": u"Depósito de material explosivo"},

        # Grupo M — Especial
        u"M-1": {u"grupo": u"M", u"uso": u"Especial", u"descricao": u"Túnel"},
        u"M-3": {u"grupo": u"M", u"uso": u"Especial", u"descricao": u"Central de comunicação"},
        u"M-4": {u"grupo": u"M", u"uso": u"Especial", u"descricao": u"Canteiro de obras"},
        u"M-5": {u"grupo": u"M", u"uso": u"Especial", u"descricao": u"Silos"},
    },

    # -------------------------------------------------------------------------
    # Tabela 2 — Taxa populacional + capacidades de saída por UP
    # A  : m²/pessoa  (None = cálculo especial, ex: por dormitório ou leito)
    # AD : pessoas/UP — Acessos e Descargas
    # ER : pessoas/UP — Escadas e Rampas
    # PT : pessoas/UP — Portas
    # -------------------------------------------------------------------------
    u"tabela": {

        u"A-1": {u"A": None, u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"2 pessoas por dormitório", u"notas": [u"C"]},
        u"A-2": {u"A": None, u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"2 pessoas por dormitório", u"notas": [u"C"]},
        u"A-3": {u"A": 4,    u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"2 por dormitório + 1 por 4m²", u"notas": [u"C", u"D"]},

        u"B-1": {u"A": 15,   u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 15m²", u"notas": [u"E", u"G"]},
        u"B-2": {u"A": 15,   u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 15m²", u"notas": [u"E", u"G"]},

        u"C-1": {u"A": 3,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 3m²", u"notas": [u"E", u"J", u"M"]},
        u"C-2": {u"A": 3,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 3m²", u"notas": [u"E", u"J", u"M"]},
        u"C-3": {u"A": 3,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 3m²", u"notas": [u"E", u"J", u"M"]},

        u"D-1": {u"A": 7,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"L", u"N"]},
        u"D-2": {u"A": 7,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"L", u"N"]},
        u"D-3": {u"A": 7,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"L", u"N"]},
        u"D-4": {u"A": 7,    u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"L", u"N"]},

        u"E-1": {u"A": Fraction(3, 2), u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},
        u"E-2": {u"A": Fraction(3, 2), u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},
        u"E-3": {u"A": Fraction(3, 2), u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},
        u"E-4": {u"A": Fraction(3, 2), u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},
        u"E-5": {u"A": Fraction(3, 2), u"AD": 30,  u"ER": 22, u"PT": 30,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},
        u"E-6": {u"A": Fraction(3, 2), u"AD": 30,  u"ER": 22, u"PT": 30,
                 u"obs": u"1 pessoa por 1,50m² de sala de aula", u"notas": [u"F", u"N"]},

        u"F-1":  {u"A": 3,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por 3m²",   u"notas": [u"N"]},
        u"F-2":  {u"A": 1,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por m²",    u"notas": [u"E", u"G", u"N", u"P", u"Q"]},
        u"F-3":  {u"A": Fraction(1, 2),  u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"2 pessoas por m²",   u"notas": [u"G", u"N", u"P", u"Q"]},
        u"F-4":  {u"A": 3,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por 3m²",   u"notas": [u"E", u"F", u"J", u"N"]},
        u"F-5":  {u"A": 1,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por m²",    u"notas": [u"E", u"G", u"N", u"P", u"Q"]},
        u"F-6":  {u"A": Fraction(1, 2),  u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"2 pessoas por m²",   u"notas": [u"G", u"N", u"P", u"Q"]},
        u"F-7":  {u"A": Fraction(1, 2),  u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"2 pessoas por m²",   u"notas": [u"G", u"N", u"P", u"Q"]},
        u"F-8":  {u"A": 1,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por m²",    u"notas": [u"E", u"G", u"N", u"P", u"Q"]},
        u"F-9":  {u"A": Fraction(1, 2),  u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"2 pessoas por m²",   u"notas": [u"G", u"N", u"P", u"Q"]},
        u"F-10": {u"A": 3,               u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"1 pessoa por 3m²",   u"notas": [u"N"]},
        u"F-11": {u"A": Fraction(1, 3),  u"AD": 100, u"ER": 75, u"PT": 100, u"obs": u"3 pessoas por m²",   u"notas": [u"E"]},

        u"G-1": {u"A": None, u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 40 vagas", u"notas": []},
        u"G-2": {u"A": None, u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 40 vagas", u"notas": []},
        u"G-3": {u"A": None, u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 40 vagas", u"notas": []},
        u"G-4": {u"A": 20,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 20m²", u"notas": [u"E"]},
        u"G-5": {u"A": 20,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 20m²", u"notas": [u"E"]},

        u"H-1": {u"A": 7,    u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"E"]},
        u"H-2": {u"A": 4,    u"AD": 30,  u"ER": 22, u"PT": 30,
                 u"obs": u"2 por dormitório + 1 por 4m² de alojamento", u"notas": [u"C", u"E"]},
        u"H-3": {u"A": None, u"AD": 30,  u"ER": 22, u"PT": 30,
                 u"obs": u"1,5 por leito + 1 por 7m² de ambulatório", u"notas": [u"H"]},
        u"H-4": {u"A": 7,    u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"F"]},
        u"H-5": {u"A": 7,    u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"F"]},
        u"H-6": {u"A": 7,    u"AD": 60,  u"ER": 45, u"PT": 100,
                 u"obs": u"1 pessoa por 7m²", u"notas": [u"E"]},

        u"I-1": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 10m²", u"notas": []},
        u"I-2": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 10m²", u"notas": []},
        u"I-3": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 10m²", u"notas": []},

        u"J-1": {u"A": 30,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 30m²", u"notas": [u"J"]},
        u"J-2": {u"A": 30,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 30m²", u"notas": [u"J"]},
        u"J-3": {u"A": 30,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 30m²", u"notas": [u"J"]},
        u"J-4": {u"A": 30,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 30m²", u"notas": [u"J"]},

        u"K-1": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100,
                 u"obs": u"1 pessoa por 10m²", u"notas": []},

        u"L-1": {u"A": 3,    u"AD": 100, u"ER": 60, u"PT": 100, u"obs": u"1 pessoa por 3m²",  u"notas": []},
        u"L-2": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100, u"obs": u"1 pessoa por 10m²", u"notas": []},
        u"L-3": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100, u"obs": u"1 pessoa por 10m²", u"notas": []},

        u"M-1": {u"A": None, u"AD": 100, u"ER": 75, u"PT": 100,
                 u"obs": u"Consultar NT específica", u"notas": [u"I"]},
        u"M-3": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100, u"obs": u"1 pessoa por 10m²", u"notas": []},
        u"M-4": {u"A": 4,    u"AD": 60,  u"ER": 45, u"PT": 100, u"obs": u"1 pessoa por 4m²",  u"notas": []},
        u"M-5": {u"A": 10,   u"AD": 100, u"ER": 60, u"PT": 100, u"obs": u"1 pessoa por 10m²", u"notas": []},
    },

    # -------------------------------------------------------------------------
    # Notas normativas
    # -------------------------------------------------------------------------
    u"notas": {
        u"C": u"(C) Em apartamentos de até 2 dormitórios, a sala deve ser considerada como dormitório.",
        u"D": u"(D) Alojamento = dormitório coletivo, com mais de 10m².",
        u"E": u"(E) Por Área entende-se a área do pavimento que abriga a população em foco.",
        u"F": u"(F) Auditórios e assemelhados em escolas são considerados nos grupos F-5, F-6 e outros.",
        u"G": u"(G) As cozinhas nas ocupações B, F-6 e F-8 têm ocupação admitida como grupo D (1 pes/7m²).",
        u"H": u"(H) Em hospitais com ambulatório, acresce-se 1 pessoa por 7m² de área de ambulatório.",
        u"I": u"(I) Necessidade de consultar normas e regulamentos específicos.",
        u"J": u"(J) A parte de atendimento ao público de comércio atacadista deve ser considerada grupo C.",
        u"L": u"(L) Para ocupações tipo Call-center, calcular 1 pessoa por 1,5m² de área.",
        u"M": u"(M) Para área de lojas, adotar 1 pessoa por 7m² de área.",
        u"N": u"(N) Para o cálculo da população, será admitido o leiaute dos assentos permanentes.",
        u"P": u"(P) Para restaurante dançante com pista de dança: 1 pessoa por 0,67m² de área.",
        u"Q": u"(Q) Para locais com banco (assento comprido): 1 pessoa por 0,50m linear.",
    },

    # -------------------------------------------------------------------------
    # Larguras mínimas
    # -------------------------------------------------------------------------
    u"larguras_minimas": {
        u"AD": 1.20,
        u"ER": 1.20,
        u"PT": [
            {u"n_up": 1, u"largura": 0.80, u"tipo": u"1 folha"},
            {u"n_up": 2, u"largura": 1.00, u"tipo": u"1 folha"},
            {u"n_up": 3, u"largura": 1.50, u"tipo": u"2 folhas"},
            {u"n_up": 4, u"largura": 2.00, u"tipo": u"2 folhas"},
        ],
    },

    # -------------------------------------------------------------------------
    # Distâncias máximas a percorrer (metros)
    # Fonte: Tabela NT CBM-MA
    # -------------------------------------------------------------------------
    u"distancias_maximas": {

        u"mapa_ocupacao": {
            u"A-1": u"AB",  u"A-2": u"AB",  u"A-3": u"AB",
            u"B-1": u"AB",  u"B-2": u"AB",
            u"C-1": u"CDFG", u"C-2": u"CDFG", u"C-3": u"CDFG",
            u"D-1": u"CDFG", u"D-2": u"CDFG", u"D-3": u"CDFG", u"D-4": u"CDFG",
            u"E-1": u"CDFG", u"E-2": u"CDFG", u"E-3": u"CDFG",
            u"E-4": u"CDFG", u"E-5": u"CDFG", u"E-6": u"CDFG",
            u"F-1":  u"CDFG", u"F-2":  u"CDFG", u"F-3":  u"CDFG",
            u"F-4":  u"CDFG", u"F-5":  u"CDFG", u"F-6":  u"CDFG",
            u"F-7":  u"CDFG", u"F-8":  u"CDFG", u"F-9":  u"CDFG",
            u"F-10": u"CDFG", u"F-11": u"CDFG",
            u"G-1": u"G1G2J2", u"G-2": u"G1G2J2",
            u"G-3": u"CDFG",   u"G-4": u"CDFG",   u"G-5": u"CDFG",
            u"H-1": u"CDFG",   u"H-2": u"CDFG",   u"H-3": u"CDFG",
            u"H-4": u"CDFG",   u"H-5": u"CDFG",   u"H-6": u"CDFG",
            u"I-1": u"I1J1",
            u"I-2": u"I2I3J3J4", u"I-3": u"I2I3J3J4",
            u"J-1": u"G1G2J2",
            u"J-2": u"G1G2J2",
            u"J-3": u"I2I3J3J4", u"J-4": u"I2I3J3J4",
            u"K-1": u"CDFG",
            u"L-1": u"CDFG", u"L-2": u"CDFG", u"L-3": u"CDFG",
            u"M-1": u"CDFG", u"M-3": u"CDFG", u"M-4": u"CDFG", u"M-5": u"CDFG",
        },

        u"grupos": {

            u"AB": {
                u"descricao": u"A e B",
                u"terreo": _dist((45,55), (55,65), (60,70), (80,95)),
                u"demais": _dist((40,45), (50,60), (55,65), (75,90)),
            },

            u"CDFG": {
                u"descricao": u"C, D, E, F, G-3, G-4, G-5, H, K, L e M",
                u"terreo": _dist((40,45), (50,60), (55,65), (75,90)),
                u"demais": _dist((30,35), (40,45), (45,55), (65,75)),
            },

            u"I1J1": {
                u"descricao": u"I-1 e J-1",
                u"terreo": _dist((80,95), (120,140), None, None),
                u"demais": _dist((70,80), (110,130), None, None),
            },

            u"G1G2J2": {
                u"descricao": u"G-1, G-2 e J-2",
                u"terreo": _dist((50,60), (60,70), (80,95), (120,140)),
                u"demais": _dist((45,55), (55,65), (70,80), (110,130)),
            },

            u"I2I3J3J4": {
                u"descricao": u"I-2, I-3, J-3 e J-4",
                u"terreo": _dist((40,45), (50,60), (60,70), (100,120)),
                u"demais": _dist((30,35), (40,45), (50,65), (80,95)),
            },
        },
    },
}
