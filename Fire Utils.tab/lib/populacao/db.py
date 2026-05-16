# -*- coding: utf-8 -*-
# ocupacoes.py — Tabela 1 NT 01/2021 CBM-MA
# Classificacao das edificacoes quanto a ocupacao/uso

OCUPACOES = {

    # ==========================================
    # GRUPO A — Residencial
    # ==========================================
    "A-1": {
        "grupo":    "A",
        "uso":      "Residencial",
        "divisao":  "A-1",
        "descricao":"Habitacao unifamiliar"
    },
    "A-2": {
        "grupo":    "A",
        "uso":      "Residencial",
        "divisao":  "A-2",
        "descricao":"Habitacao multifamiliar"
    },
    "A-3": {
        "grupo":    "A",
        "uso":      "Residencial",
        "divisao":  "A-3",
        "descricao":"Habitacao coletiva"
    },

    # ==========================================
    # GRUPO B — Servico de Hospedagem
    # ==========================================
    "B-1": {
        "grupo":    "B",
        "uso":      "Servico de Hospedagem",
        "divisao":  "B-1",
        "descricao":"Hotel e assemelhado"
    },
    "B-2": {
        "grupo":    "B",
        "uso":      "Servico de Hospedagem",
        "divisao":  "B-2",
        "descricao":"Hotel residencial"
    },

    # ==========================================
    # GRUPO C — Comercial
    # ==========================================
    "C-1": {
        "grupo":    "C",
        "uso":      "Comercial",
        "divisao":  "C-1",
        "descricao":"Comercio com baixa carga de incendio"
    },
    "C-2": {
        "grupo":    "C",
        "uso":      "Comercial",
        "divisao":  "C-2",
        "descricao":"Comercio com media e alta carga de incendio"
    },
    "C-3": {
        "grupo":    "C",
        "uso":      "Comercial",
        "divisao":  "C-3",
        "descricao":"Shopping centers"
    },

    # ==========================================
    # GRUPO D — Servico Profissional
    # ==========================================
    "D-1": {
        "grupo":    "D",
        "uso":      "Servico Profissional",
        "divisao":  "D-1",
        "descricao":"Local para prestacao de servico profissional ou conducao de negocios e administracao publica em geral"
    },
    "D-2": {
        "grupo":    "D",
        "uso":      "Servico Profissional",
        "divisao":  "D-2",
        "descricao":"Agencia bancaria"
    },
    "D-3": {
        "grupo":    "D",
        "uso":      "Servico Profissional",
        "divisao":  "D-3",
        "descricao":"Servico de reparacao (exceto os classificados em G-4)"
    },
    "D-4": {
        "grupo":    "D",
        "uso":      "Servico Profissional",
        "divisao":  "D-4",
        "descricao":"Laboratorio"
    },

    # ==========================================
    # GRUPO E — Educacional e Cultura Fisica
    # ==========================================
    "E-1": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-1",
        "descricao":"Escola em geral"
    },
    "E-2": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-2",
        "descricao":"Escola especial"
    },
    "E-3": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-3",
        "descricao":"Espaco para cultura fisica"
    },
    "E-4": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-4",
        "descricao":"Centro de treinamento profissional"
    },
    "E-5": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-5",
        "descricao":"Pre-escola"
    },
    "E-6": {
        "grupo":    "E",
        "uso":      "Educacional e Cultura Fisica",
        "divisao":  "E-6",
        "descricao":"Escola para portadores de deficiencias"
    },

    # ==========================================
    # GRUPO F — Local de Reuniao de Publico
    # ==========================================
    "F-1": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-1",
        "descricao":"Local onde ha objeto de valor inestimavel"
    },
    "F-2": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-2",
        "descricao":"Local religioso e velorio"
    },
    "F-3": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-3",
        "descricao":"Centro esportivo e de exibicao"
    },
    "F-4": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-4",
        "descricao":"Estacao e terminal de passageiro"
    },
    "F-5": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-5",
        "descricao":"Arte cenica e auditorio"
    },
    "F-6": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-6",
        "descricao":"Clubes sociais e Salao de Festas"
    },
    "F-7": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-7",
        "descricao":"Eventos temporarios"
    },
    "F-8": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-8",
        "descricao":"Local para refeicao"
    },
    "F-9": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-9",
        "descricao":"Recreacao publica"
    },
    "F-10": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-10",
        "descricao":"Exposicao de objetos ou animais"
    },
    "F-11": {
        "grupo":    "F",
        "uso":      "Local de Reuniao de Publico",
        "divisao":  "F-11",
        "descricao":"Boates"
    },

    # ==========================================
    # GRUPO G — Servico Automotivo e Assemelhados
    # ==========================================
    "G-1": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-1",
        "descricao":"Garagem sem acesso de publico e sem abastecimento"
    },
    "G-2": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-2",
        "descricao":"Garagem com acesso de publico e sem abastecimento"
    },
    "G-3": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-3",
        "descricao":"Local dotado de abastecimento de combustivel"
    },
    "G-4": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-4",
        "descricao":"Servico de conservacao, manutencao e reparos"
    },
    "G-5": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-5",
        "descricao":"Hangares"
    },
    "G-6": {
        "grupo":    "G",
        "uso":      "Servico Automotivo e Assemelhados",
        "divisao":  "G-6",
        "descricao":"Marinas, portos e garagens nauticas"
    },

    # ==========================================
    # GRUPO H — Servico de Saude e Institucional
    # ==========================================
    "H-1": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-1",
        "descricao":"Hospital veterinario e assemelhado"
    },
    "H-2": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-2",
        "descricao":"Local onde pessoas requerem cuidados especiais por limitacoes fisicas ou mentais"
    },
    "H-3": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-3",
        "descricao":"Hospital e assemelhado"
    },
    "H-4": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-4",
        "descricao":"Edificacoes das forcas armadas e policiais"
    },
    "H-5": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-5",
        "descricao":"Local onde a liberdade das pessoas sofre restricoes"
    },
    "H-6": {
        "grupo":    "H",
        "uso":      "Servico de Saude e Institucional",
        "divisao":  "H-6",
        "descricao":"Clinica e consultorio medico e odontologico"
    },

    # ==========================================
    # GRUPO I — Industria
    # ==========================================
    "I-1": {
        "grupo":    "I",
        "uso":      "Industria",
        "divisao":  "I-1",
        "descricao":"Industria com carga de incendio ate 300MJ/m2"
    },
    "I-2": {
        "grupo":    "I",
        "uso":      "Industria",
        "divisao":  "I-2",
        "descricao":"Industria com carga de incendio acima de 300MJ/m2 ate 1.200MJ/m2"
    },
    "I-3": {
        "grupo":    "I",
        "uso":      "Industria",
        "divisao":  "I-3",
        "descricao":"Industria com carga de incendio superior a 1.200MJ/m2"
    },

    # ==========================================
    # GRUPO J — Deposito
    # ==========================================
    "J-1": {
        "grupo":    "J",
        "uso":      "Deposito",
        "divisao":  "J-1",
        "descricao":"Deposito de material incombustivel"
    },
    "J-2": {
        "grupo":    "J",
        "uso":      "Deposito",
        "divisao":  "J-2",
        "descricao":"Deposito com carga de incendio ate 300MJ/m2"
    },
    "J-3": {
        "grupo":    "J",
        "uso":      "Deposito",
        "divisao":  "J-3",
        "descricao":"Deposito com carga de incendio acima de 300MJ/m2 ate 1.200MJ/m2"
    },
    "J-4": {
        "grupo":    "J",
        "uso":      "Deposito",
        "divisao":  "J-4",
        "descricao":"Deposito com carga de incendio superior a 1.200MJ/m2"
    },

    # ==========================================
    # GRUPO K — Energia
    # ==========================================
    "K-1": {
        "grupo":    "K",
        "uso":      "Energia",
        "divisao":  "K-1",
        "descricao":"Central de transmissao e distribuicao de energia"
    },

    # ==========================================
    # GRUPO L — Explosivo
    # ==========================================
    "L-1": {
        "grupo":    "L",
        "uso":      "Explosivo",
        "divisao":  "L-1",
        "descricao":"Comercio"
    },
    "L-2": {
        "grupo":    "L",
        "uso":      "Explosivo",
        "divisao":  "L-2",
        "descricao":"Industria de material explosivo"
    },
    "L-3": {
        "grupo":    "L",
        "uso":      "Explosivo",
        "divisao":  "L-3",
        "descricao":"Deposito de material explosivo"
    },

    # ==========================================
    # GRUPO M — Especial
    # ==========================================
    "M-1": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-1",
        "descricao":"Tunel"
    },
    "M-2": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-2",
        "descricao":"Liquido ou gas inflamavel ou combustivel"
    },
    "M-3": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-3",
        "descricao":"Central de comunicacao"
    },
    "M-4": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-4",
        "descricao":"Canteiro de obras"
    },
    "M-5": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-5",
        "descricao":"Silos"
    },
    "M-6": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-6",
        "descricao":"Floresta nativa ou cultivada"
    },
    "M-7": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-7",
        "descricao":"Patio de conteineres"
    },
    "M-8": {
        "grupo":    "M",
        "uso":      "Especial",
        "divisao":  "M-8",
        "descricao":"Torres de telefonia movel"
    },
}