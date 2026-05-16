# -*- coding: utf-8 -*-
# it11.py — Tabela IT 11 CBMSP
# Banco de dados de ocupacoes para calculo de populacao

from fractions import Fraction

IT = {

    # -------------------------------------------------------------------------
    # GRUPO A - Residencial
    # -------------------------------------------------------------------------
    "A-1": {
        "grupo": "A",
        "A": None,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "2 pessoas por dormitorio",
        "notas": ["C"],
    },
    "A-2": {
        "grupo": "A",
        "A": None,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "2 pessoas por dormitorio",
        "notas": ["C"],
    },
    "A-3": {
        "grupo": "A",
        "A": 4,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "2 por dormitorio + 1 por 4m2",
        "notas": ["C", "D"],
    },

    # -------------------------------------------------------------------------
    # GRUPO B - Hospedagem
    # -------------------------------------------------------------------------
    "B": {
        "grupo": "B",
        "A": 15,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 15m2",
        "notas": ["E", "G"],
    },

    # -------------------------------------------------------------------------
    # GRUPO C - Comercial
    # -------------------------------------------------------------------------
    "C": {
        "grupo": "C",
        "A": 5,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 5m2",
        "notas": ["E", "J", "M"],
    },

    # -------------------------------------------------------------------------
    # GRUPO D - Servicos profissionais
    # -------------------------------------------------------------------------
    "D": {
        "grupo": "D",
        "A": 7,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 7m2",
        "notas": ["L", "N"],
    },

    # -------------------------------------------------------------------------
    # GRUPO E - Educacional e Cultura Fisica
    # -------------------------------------------------------------------------
    "E-1": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },
    "E-2": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },
    "E-3": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },
    "E-4": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },
    "E-5": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 30,
        "ER": 22,
        "PT": 30,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },
    "E-6": {
        "grupo": "E",
        "A": Fraction(3, 2),
        "AD": 30,
        "ER": 22,
        "PT": 30,
        "obs": "1 pessoa por 1,50m2 de area de sala de aula",
        "notas": ["F", "N"],
    },

    # -------------------------------------------------------------------------
    # GRUPO F - Reuniao de publico
    # -------------------------------------------------------------------------
    "F-1": {
        "grupo": "F",
        "A": 3,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 3m2",
        "notas": ["N"],
    },
    "F-2": {
        "grupo": "F",
        "A": 1,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por m2",
        "notas": ["E", "G", "N", "P", "Q"],
    },
    "F-3": {
        "grupo": "F",
        "A": Fraction(1, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "2 pessoas por m2",
        "notas": ["G", "N", "P", "Q"],
    },
    "F-4": {
        "grupo": "F",
        "A": 3,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 3m2",
        "notas": ["E", "F", "J", "N"],
    },
    "F-5": {
        "grupo": "F",
        "A": 1,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por m2",
        "notas": ["E", "G", "N", "P", "Q"],
    },
    "F-6": {
        "grupo": "F",
        "A": Fraction(1, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "2 pessoas por m2",
        "notas": ["G", "N", "P", "Q"],
    },
    "F-7": {
        "grupo": "F",
        "A": Fraction(1, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "2 pessoas por m2",
        "notas": ["G", "N", "P", "Q"],
    },
    "F-8": {
        "grupo": "F",
        "A": 1,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por m2",
        "notas": ["E", "G", "N", "P", "Q"],
    },
    "F-9": {
        "grupo": "F",
        "A": Fraction(1, 2),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "2 pessoas por m2",
        "notas": ["G", "N", "P", "Q"],
    },
    "F-10": {
        "grupo": "F",
        "A": 3,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "1 pessoa por 3m2",
        "notas": ["N"],
    },
    "F-11": {
        "grupo": "F",
        "A": Fraction(1, 3),
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "3 pessoas por m2",
        "notas": ["E"],
    },

    # -------------------------------------------------------------------------
    # GRUPO G - Garagens
    # -------------------------------------------------------------------------
    "G-1": {
        "grupo": "G",
        "A": None,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 40 vagas de veiculo",
        "notas": [],
    },
    "G-2": {
        "grupo": "G",
        "A": None,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 40 vagas de veiculo",
        "notas": [],
    },
    "G-3": {
        "grupo": "G",
        "A": None,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 40 vagas de veiculo",
        "notas": [],
    },
    "G-4": {
        "grupo": "G",
        "A": 20,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 20m2",
        "notas": ["E"],
    },
    "G-5": {
        "grupo": "G",
        "A": 20,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 20m2",
        "notas": ["E"],
    },

    # -------------------------------------------------------------------------
    # GRUPO H - Saude e Institucional
    # -------------------------------------------------------------------------
    "H-1": {
        "grupo": "H",
        "A": 7,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "1 pessoa por 7m2",
        "notas": ["E"],
    },
    "H-2": {
        "grupo": "H",
        "A": 4,
        "AD": 30,
        "ER": 22,
        "PT": 30,
        "obs": "2 pessoas por dormitorio + 1 pessoa por 4m2 de alojamento",
        "notas": ["C", "E"],
    },
    "H-3": {
        "grupo": "H",
        "A": None,
        "AD": 30,
        "ER": 22,
        "PT": 30,
        "obs": "1,5 por leito + 1 pessoa por 7m2 de ambulatorio",
        "notas": ["H"],
    },
    "H-4": {
        "grupo": "H",
        "A": 7,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "1 pessoa por 7m2",
        "notas": ["F"],
    },
    "H-5": {
        "grupo": "H",
        "A": 7,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "1 pessoa por 7m2",
        "notas": ["F"],
    },
    "H-6": {
        "grupo": "H",
        "A": 7,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "1 pessoa por 7m2",
        "notas": ["E"],
    },

    # -------------------------------------------------------------------------
    # GRUPO I - Industrial
    # -------------------------------------------------------------------------
    "I": {
        "grupo": "I",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },

    # -------------------------------------------------------------------------
    # GRUPO J - Depositos
    # -------------------------------------------------------------------------
    "J": {
        "grupo": "J",
        "A": 30,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 30m2",
        "notas": ["J"],
    },

    # -------------------------------------------------------------------------
    # GRUPO K - Especiais
    # -------------------------------------------------------------------------
    "K": {
        "grupo": "K",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },

    # -------------------------------------------------------------------------
    # GRUPO L - Explosivos
    # -------------------------------------------------------------------------
    "L-1": {
        "grupo": "L",
        "A": 3,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 3m2",
        "notas": [],
    },
    "L-2": {
        "grupo": "L",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },
    "L-3": {
        "grupo": "L",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },

    # -------------------------------------------------------------------------
    # GRUPO M - Especiais
    # -------------------------------------------------------------------------
    "M-1": {
        "grupo": "M",
        "A": None,
        "AD": 100,
        "ER": 75,
        "PT": 100,
        "obs": "Consultar NT especifica",
        "notas": ["I"],
    },
    "M-3": {
        "grupo": "M",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },
    "M-4": {
        "grupo": "M",
        "A": 4,
        "AD": 60,
        "ER": 45,
        "PT": 100,
        "obs": "1 pessoa por 4m2",
        "notas": [],
    },
    "M-5": {
        "grupo": "M",
        "A": 10,
        "AD": 100,
        "ER": 60,
        "PT": 100,
        "obs": "1 pessoa por 10m2",
        "notas": [],
    },
}


# =============================================================================
# DICIONARIO DE DESCRICAO DAS NOTAS
# =============================================================================
NOTAS_ESPECIFICAS = {
    "A": "(A) os parametros dados nesta tabela sao os minimos aceitaveis para o calculo da populacao (ver 5.3);",
    "B": "(B) as capacidades das unidades de passagem (1 UP = 0,55 m) em escadas e rampas estendem-se para lancos retos e saida descendente;",
    "C": "(C) em apartamentos de ate 2 dormitorios, a sala deve ser considerada como dormitorio: em apartamentos maiores (3 e mais dormitorios), as salas, gabinetes e outras dependencias que possam ser usadas como dormitorios (inclusive para empregadas) sao considerados como dormitorios. Em apartamentos minimos, sem divisoes em planta, considera-se uma pessoa para cada 6m2 de area de pavimento;",
    "D": "(D) alojamento = dormitorio coletivo, com mais de 10m2;",
    "E": "(E) por Area entende-se a Area do pavimento que abriga a populacao em foco. Quando discriminado o tipo de area (por ex.: area do alojamento), e a area util interna da dependencia em questao;",
    "F": "(F) auditorios e assemelhados, em escolas, bem como saloes de festas e centros de convencoes em hoteis sao considerados nos grupos de ocupacao F-5, F-6 e outros, conforme o caso;",
    "G": "(G) as cozinhas e suas areas de apoio, nas ocupacoes B, F-6, e F-8, tem sua ocupacao admitida como no grupo D, isto e, uma pessoa por 7m2 de area;",
    "H": "(H) em hospitais e clinicas com internamento (H-3), que tenham pacientes ambulatoriais, acresce-se a area calculada por leito, a area de pavimento correspondente ao ambulatorio, na base de uma pessoa por 7m2;",
    "I": "(I) o simbolo + indica necessidade de consultar normas e regulamentos especificos (nao cobertos por esta NT);",
    "J": "(J) a parte de atendimento ao publico de comercio atacadista deve ser considerada como do grupo C;",
    "K": "(K) esta tabela se aplica a todas as edificacoes, exceto para os locais destinados as divisoes F-3, F-7, com populacao total superior a 2.500 pessoas, onde deve ser consultada a norma tecnica especifica de Centros esportivos e de exibicao;",
    "L": "(L) para ocupacoes do tipo Call-center, o calculo da populacao e de uma pessoa por 1,5m2 de area;",
    "M": "(M) para a area de Lojas adota-se no calculo uma pessoa por 7m2 de area;",
    "N": "(N) para o calculo da populacao, sera admitido o leiaute dos assentos permanentes apresentado em planta;",
    "O": "(O) para a classificacao das ocupacoes (grupos e divisoes), consultar a tabela 1 da norma tecnica especifica;",
    "P": "(P) para a ocupacao restaurante dancante e salao de festas onde ha mesas e cadeiras para refeicao e pista de danca, o parametro para calculo de populacao e de 1 pessoa por 0,67m2 de area;",
    "Q": "(Q) para os locais que possuam assento do tipo banco (assento comprido, para varias pessoas, com ou sem encosto) o parametro para calculo de populacao e de 1 pessoa por 0,50m linear, mediante apresentacao de leiaute.",
}