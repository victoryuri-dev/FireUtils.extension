# -*- coding: utf-8 -*-
"""
ocupacoes_fallback.py — Fire Utils · lib/

Grupos (A, B, C...) e divisões (A-1, C-1...) com descrição, por estado — usados
só pra rotular o diálogo "Identificar por ambiente" quando a norma de saídas
baixada da base central não traz o bloco "ocupacoes" (caso da PB). Cópia de
src/data/normas/<UF>/ocupacoes.js do site; formato { grupo: (descricao, { divisao: descricao }) }.
"""

OCUPACOES = {
    u"PB": {
        u"A": (u"Residencial", {u"A-1": u"Habita\u00e7\u00e3o unifamiliar", u"A-2": u"Habita\u00e7\u00e3o multifamiliar", u"A-3": u"Habita\u00e7\u00e3o coletiva"}),
        u"B": (u"Servi\u00e7o de Hospedagem", {u"B-1": u"Hotel e assemelhado", u"B-2": u"Hotel residencial"}),
        u"C": (u"Comercial", {u"C-1": u"Com\u00e9rcio com carga de inc\u00eandio N\u00edvel I", u"C-2": u"Com\u00e9rcio com carga de inc\u00eandio N\u00edvel II e N\u00edvel III", u"C-3": u"Centro de Compras"}),
        u"D": (u"Servi\u00e7o Profissional", {u"D-1": u"Local para presta\u00e7\u00e3o de servi\u00e7o profissional ou condu\u00e7\u00e3o de neg\u00f3cios", u"D-2": u"Ag\u00eancia banc\u00e1ria", u"D-3": u"Servi\u00e7o de repara\u00e7\u00e3o (exceto os classificados em G-4)", u"D-4": u"Laborat\u00f3rio"}),
        u"E": (u"Escolar e Cultura F\u00edsica", {u"E-1": u"Escola em geral", u"E-2": u"Escola especial", u"E-3": u"Espa\u00e7o para cultura f\u00edsica", u"E-4": u"Centro de treinamento profissional", u"E-5": u"Pr\u00e9-escola", u"E-6": u"Escola para portadores de defici\u00eancias"}),
        u"F": (u"Local de Reuni\u00e3o de P\u00fablico", {u"F-1": u"Local onde h\u00e1 objeto de valor inestim\u00e1vel", u"F-2": u"Local religioso e vel\u00f3rio", u"F-3": u"Centro esportivo e de exibi\u00e7\u00e3o", u"F-4": u"Esta\u00e7\u00e3o e terminal de passageiros", u"F-5": u"Arte c\u00eanica e audit\u00f3rio", u"F-6": u"Clube Social e Sal\u00e3o de Festas", u"F-7": u"Instala\u00e7\u00e3o tempor\u00e1ria", u"F-8": u"Local para refei\u00e7\u00e3o", u"F-9": u"Recrea\u00e7\u00e3o p\u00fablica", u"F-10": u"Exposi\u00e7\u00e3o de objetos e animais", u"F-11": u"Boate"}),
        u"G": (u"Servi\u00e7os Automotivos e Assemelhados", {u"G-1": u"Garagem sem acesso de p\u00fablico e sem abastecimento", u"G-2": u"Garagem com acesso de p\u00fablico e sem abastecimento", u"G-3": u"Local dotado de abastecimento de combust\u00edvel", u"G-4": u"Servi\u00e7os de conserva\u00e7\u00e3o, manuten\u00e7\u00e3o e reparos", u"G-5": u"Hangar"}),
        u"H": (u"Servi\u00e7o de Sa\u00fade e Institucional", {u"H-1": u"Hospital veterin\u00e1rio e assemelhados", u"H-2": u"Local onde pessoas requerem cuidados especiais por limita\u00e7\u00f5es f\u00edsicas ou mentais", u"H-3": u"Hospitais e assemelhado", u"H-4": u"Reparti\u00e7\u00e3o p\u00fablica, edifica\u00e7\u00f5es das for\u00e7as armadas e policiais", u"H-5": u"Local onde a liberdade das pessoas sofre restri\u00e7\u00f5es", u"H-6": u"Cl\u00ednicas e consut\u00f3rio m\u00e9dico e odontol\u00f3gico"}),
        u"I": (u"Ind\u00fastria", {u"I-1": u"Ind\u00fastria com carga de inc\u00eandio N\u00edvel I", u"I-2": u"Ind\u00fastria com carga de inc\u00eandio N\u00edvel II", u"I-3": u"Ind\u00fastria com carga de inc\u00eandio N\u00edvel III"}),
        u"J": (u"Dep\u00f3sito", {u"J-1": u"Dep\u00f3sitos de material incombust\u00edvel", u"J-2": u"Dep\u00f3sitos com carga de inc\u00eandio N\u00edvel I", u"J-3": u"Dep\u00f3sitos com carga de inc\u00eandio N\u00edvel II", u"J-4": u"Dep\u00f3sitos com carga de inc\u00eandio N\u00edvel III"}),
        u"K": (u"Energia", {u"K-1": u"Central de transmiss\u00e3o e distribui\u00e7\u00e3o de energia"}),
        u"L": (u"Explosivo", {u"L-1": u"Com\u00e9rcio", u"L-2": u"Ind\u00fastria", u"L-3": u"Dep\u00f3sito", u"L-4": u"Show Pirot\u00e9cnico"}),
        u"M": (u"Especial", {u"M-1": u"T\u00fanel", u"M-2": u"Tanques ou Parques de Tanques", u"M-3": u"Central de comunica\u00e7\u00e3o", u"M-4": u"Canteiro de obras", u"M-5": u"Silos", u"M-6": u"Floresta nativa ou cultivada", u"M-7": u"P\u00e1tio de Cont\u00eaineres"}),
    },
    u"MA": {
        u"A": (u"Residencial", {u"A-1": u"Habitacao unifamiliar", u"A-2": u"Habitacao multifamiliar", u"A-3": u"Habitacao coletiva"}),
        u"B": (u"Servico de Hospedagem", {u"B-1": u"Hotel e assemelhado", u"B-2": u"Hotel residencial"}),
        u"C": (u"Comercial", {u"C-1": u"Comercio com baixa carga de incendio", u"C-2": u"Comercio com media e alta carga de incendio", u"C-3": u"Shopping centers"}),
        u"D": (u"Servico profissional", {u"D-1": u"Local para prestacao de servico profissional ou conducao de negocios e administracao publica em geral", u"D-2": u"Agencia bancaria", u"D-3": u"Servico de reparacao (exceto os classificados em G-4)", u"D-4": u"Laboratorio"}),
        u"E": (u"Educacional e cultura fisica", {u"E-1": u"Escola em geral", u"E-2": u"Escola especial", u"E-3": u"Espaco para cultura fisica", u"E-4": u"Centro de treinamento profissional", u"E-5": u"Pre-escola", u"E-6": u"Escola para portadores de deficiencias"}),
        u"F": (u"Local de Reuniao de Publico", {u"F-1": u"Local onde ha objeto de valor inestimavel", u"F-2": u"Local religioso e velorio", u"F-3": u"Centro esportivo e de exibicao", u"F-4": u"Estacao e terminal de passageiro", u"F-5": u"Arte cenica e auditorio", u"F-6": u"Clubes sociais e Salao de Festas", u"F-7": u"Eventos temporarios", u"F-8": u"Local para refeicao", u"F-9": u"Recreacao publica", u"F-10": u"Exposicao de objetos ou animais", u"F-11": u"Boates"}),
        u"G": (u"Servico automotivo e assemelhados", {u"G-1": u"Garagem sem acesso de publico e sem abastecimento", u"G-2": u"Garagem com acesso de publico e sem abastecimento", u"G-3": u"Local dotado de abastecimento de combustivel", u"G-4": u"Servico de conservacao, manutencao e reparos", u"G-5": u"Hangares", u"G-6": u"Marinas, portos e garagens nauticas"}),
        u"H": (u"Servico de saude e institucional", {u"H-1": u"Hospital veterinario e assemelhados", u"H-2": u"Local onde pessoas requerem cuidados especiais por limitacoes fisicas ou mentais", u"H-3": u"Hospital e assemelhado", u"H-4": u"Edificacoes das forcas armadas e policiais", u"H-5": u"Local onde a liberdade das pessoas sofre restricoes", u"H-6": u"Clinica e consultorio medico e odontologico"}),
        u"I": (u"Industria", {u"I-1": u"Industria com carga de incendio ate 300 MJ/m\u00b2", u"I-2": u"Industria com carga de incendio acima de 300 MJ/m\u00b2 ate 1.200 MJ/m\u00b2", u"I-3": u"Industria com carga de incendio superior a 1.200 MJ/m\u00b2"}),
        u"J": (u"Deposito", {u"J-1": u"Deposito de material incombustivel", u"J-2": u"Deposito com carga de incendio ate 300 MJ/m\u00b2", u"J-3": u"Deposito com carga de incendio acima de 300 MJ/m\u00b2 ate 1.200 MJ/m\u00b2", u"J-4": u"Deposito com carga de incendio superior a 1.200 MJ/m\u00b2"}),
        u"K": (u"Energia", {u"K-1": u"Central de transmissao e distribuicao de energia"}),
        u"L": (u"Explosivo", {u"L-1": u"Comercio", u"L-2": u"Industria", u"L-3": u"Deposito"}),
        u"M": (u"Especial", {u"M-1": u"Tunel", u"M-2": u"Liquido ou gas inflamavel ou combustivel", u"M-3": u"Central de comunicacao", u"M-4": u"Canteiro de obras", u"M-5": u"Silos", u"M-6": u"Floresta nativa ou cultivada", u"M-7": u"Patio de conteineres", u"M-8": u"Torres de telefonia movel"}),
    },
}
