# -*- coding: utf-8 -*-
"""
succao.py — Fire Utils · lib/hidrantes/

Verificação da CONDIÇÃO DE SUCÇÃO pelo NÍVEL X.

Substitui a verificação simplificada (comparação direta entre a cota da RTI
e a cota da sucção da bomba), que ignorava o nível mínimo de água antes da
formação de vórtice.

Passo a passo implementado:

  1. Dimensão A, em função do DN da sucção — interpolada linearmente para DN
     fora dos valores tabelados. Dispensada quando há dispositivo
     antivórtice, o que só vale para tomada INFERIOR: em captação horizontal
     (lateral/superior) o antivórtice não substitui a altura de água.

  2. Nível X = cota da tomada de sucção + dimensão A. A referência é sempre
     a TOMADA, não o fundo do reservatório — para tomada inferior a cota da
     tomada já coincide com o fundo, então a mesma fórmula vale para os três
     tipos.

  3. Condição de sucção, comparando o eixo do rotor com o nível X:
       eixo ≤ nível X                        → POSITIVA (bomba afogada)
       eixo acima, dentro da tolerância      → POSITIVA (dentro da tolerância)
       eixo acima, excedendo a tolerância    → NEGATIVA (exige NPSH)
     Tolerância = menor entre o teto normativo e 1/3 da altura da capacidade
     efetiva.

  4. Capacidade efetiva da RTI: o volume abaixo do nível X não é utilizável,
     e é a capacidade EFETIVA — não o volume total — que deve ser comparada
     com a reserva mínima exigida.

  5. Sucção negativa aciona o cálculo de NPSH disponível (hidrantes/npshd.py),
     com a vazão nominal do sistema majorada pelo fator normativo.

Módulo puro: sem dependência de Revit ou de output. A geometria (tipo de
tomada, DN da sucção, cotas) é lida do modelo pelo script chamador; os
valores e citações que mudam de estado para estado vêm do perfil normativo
ativo, nunca daqui.
"""

from __future__ import absolute_import

import json

# IronPython 2.7 (engine do pyRevit) tem 'unicode'; CPython 3 não.
try:
    _txt = unicode
except NameError:
    _txt = str


# ===========================================================================
# Constantes normativas
# ===========================================================================

# Dimensões mínimas em MILÍMETROS, por DN da tomada:
#   A = altura mínima de água acima da tomada, para evitar vórtice
#   B = afastamento mínimo lateral / de fundo da tomada
TABELA_B1 = {
    65:  {"A": 250, "B": 80},
    80:  {"A": 310, "B": 80},
    100: {"A": 370, "B": 100},
    150: {"A": 500, "B": 100},
    200: {"A": 620, "B": 150},
    250: {"A": 750, "B": 150},
}

DN_MIN_B1 = min(TABELA_B1)
DN_MAX_B1 = max(TABELA_B1)

# Tipos de tomada de sucção: lateral e superior (captação horizontal) e
# inferior (pelo fundo do reservatório).
TOMADA_LATERAL  = u"lateral"
TOMADA_SUPERIOR = u"superior"
TOMADA_INFERIOR = u"inferior"
TIPOS_TOMADA    = (TOMADA_LATERAL, TOMADA_SUPERIOR, TOMADA_INFERIOR)

# O dispositivo antivórtice só dispensa a dimensão A quando a captação NÃO é
# horizontal; ou seja, apenas na tomada inferior.
TOMADAS_SEM_ANTIVORTICE = (TOMADA_LATERAL, TOMADA_SUPERIOR)

# Tolerância máxima absoluta para o eixo do rotor acima do nível X, e fator de
# majoração da vazão na verificação de NPSH. Ambos são normativos: os valores
# abaixo são só o default geral, e o perfil do estado ativo
# (succao_tolerancia_max / npshd_fator_vazao) tem precedência.
TOLERANCIA_MAX_M = 2.0
FATOR_VAZAO_NPSH = 1.5

# Veredictos possíveis da verificação.
COND_POSITIVA           = u"POSITIVA"
COND_POSITIVA_TOLERANCIA = u"POSITIVA (dentro da tolerância)"
COND_NEGATIVA           = u"NEGATIVA"

# Folga de 1 mm nas comparações de cota, só para não virar o veredicto por
# ruído de arredondamento quando duas cotas são, na prática, iguais.
EPS_M = 0.001

# Parâmetro de Project Information que guarda (em JSON) os dados do
# reservatório que não dá para ler da geometria.
SUCCAO_PARAM = u"FireUtils - Dados de Succao"


# ===========================================================================
# Dimensões A e B por DN
# ===========================================================================

def dimensoes_b1(dn_mm):
    """
    Dimensões A e B (mm) para um DN de sucção.

    Interpola linearmente entre os DN tabelados. Fora da faixa 65–250
    levanta ValueError — a norma não cobre esses diâmetros e o caso exige
    conferência manual.

    Retorna (A_mm, B_mm, interpolado).
    """
    dn = float(dn_mm)
    if dn < DN_MIN_B1 - EPS_M or dn > DN_MAX_B1 + EPS_M:
        raise ValueError(
            u"DN {:g} mm fora da faixa tabelada para a dimensão A "
            u"({}–{} mm). O valor não pode ser obtido por interpolação — "
            u"conferir manualmente.".format(dn, DN_MIN_B1, DN_MAX_B1))

    tabelados = sorted(TABELA_B1)

    for k in tabelados:
        if abs(dn - k) < 1e-9:
            return float(TABELA_B1[k]["A"]), float(TABELA_B1[k]["B"]), False

    inferior = max(k for k in tabelados if k < dn)
    superior = min(k for k in tabelados if k > dn)
    f = (dn - inferior) / float(superior - inferior)

    a = TABELA_B1[inferior]["A"] + f * (TABELA_B1[superior]["A"] - TABELA_B1[inferior]["A"])
    b = TABELA_B1[inferior]["B"] + f * (TABELA_B1[superior]["B"] - TABELA_B1[inferior]["B"])
    return float(a), float(b), True


def dimensao_a_aplicavel(tipo_tomada, possui_dispositivo_antivortice):
    """
    O antivórtice dispensa a dimensão A, mas não vale quando a captação é
    horizontal (tomada lateral ou superior).
    """
    if not possui_dispositivo_antivortice:
        return True
    return tipo_tomada in TOMADAS_SEM_ANTIVORTICE


# ===========================================================================
# Verificação principal
# ===========================================================================

def verificar_condicao_succao(cota_tomada_succao, cota_eixo_rotor_bomba,
                              dn_succao_mm, tipo_tomada,
                              cota_fundo_reservatorio=0.0,
                              possui_dispositivo_antivortice=False,
                              possui_poco_succao=False,
                              volume_total_m3=None, area_planta_m2=None,
                              q_nominal_lmin=None,
                              tolerancia_max_m=TOLERANCIA_MAX_M,
                              fator_vazao_npsh=FATOR_VAZAO_NPSH):
    """
    Verificação completa da condição de sucção pelo nível X.

    Cotas em metros, DN em milímetros, volume em m³ e área em m².
    volume_total_m3/area_planta_m2 são opcionais: sem eles não dá para
    calcular a capacidade efetiva nem a parcela de 1/3 da tolerância — nesse
    caso a tolerância fica zerada (lado conservador: o veredicto cai para
    NEGATIVA em vez de conceder 2 m sem respaldo no volume do reservatório).

    Retorna um dict com todos os intermediários, pronto para o memorial.
    """
    if tipo_tomada not in TIPOS_TOMADA:
        raise ValueError(u"Tipo de tomada inválido: {}".format(tipo_tomada))

    cota_tomada = float(cota_tomada_succao)
    cota_eixo   = float(cota_eixo_rotor_bomba)
    cota_fundo  = float(cota_fundo_reservatorio)

    # --- Passo 1: dimensão A ---
    a_mm, b_mm, interpolado = dimensoes_b1(dn_succao_mm)
    aplica_a = dimensao_a_aplicavel(tipo_tomada, possui_dispositivo_antivortice)

    if aplica_a:
        dimensao_A = a_mm / 1000.0
        observacao_A = u"Dimensão A aplicada conforme a tabela de dimensões mínimas"
        if interpolado:
            observacao_A += u" (interpolada linearmente entre os DN tabelados)"
    else:
        dimensao_A = 0.0
        observacao_A = (u"Dimensão A dispensada por dispositivo antivórtice — "
                        u"admitido por ser tomada inferior")

    # --- Passo 2: nível X (medido a partir da TOMADA) ---
    nivel_X = cota_tomada + dimensao_A

    # --- Passo 4 (antecipado): capacidade efetiva ---
    # Vem antes do veredicto porque a tolerância do critério depende da
    # altura da capacidade efetiva.
    altura_nao_utilizavel = max(0.0, nivel_X - cota_fundo)
    volume_nao_utilizavel = None
    capacidade_efetiva    = None
    altura_efetiva        = None

    if area_planta_m2 is not None and float(area_planta_m2) > 0:
        area = float(area_planta_m2)
        volume_nao_utilizavel = area * altura_nao_utilizavel
        if volume_total_m3 is not None:
            capacidade_efetiva = float(volume_total_m3) - volume_nao_utilizavel
            altura_efetiva = capacidade_efetiva / area

    # --- Passo 3: condição de sucção ---
    if altura_efetiva is not None and altura_efetiva > 0:
        tolerancia = min(tolerancia_max_m, altura_efetiva / 3.0)
        base_tolerancia = (u"menor entre {:.2f} m e 1/3 da altura da capacidade "
                           u"efetiva ({:.2f} m)".format(tolerancia_max_m,
                                                        altura_efetiva / 3.0))
    else:
        # Sem volume/área do reservatório não há como sustentar a parcela de
        # 1/3; zerar a tolerância mantém a verificação do lado seguro.
        tolerancia = 0.0
        base_tolerancia = (u"zerada — capacidade efetiva do reservatório não "
                           u"informada, tolerância não pode ser sustentada")

    desnivel = cota_eixo - nivel_X   # > 0 = eixo acima do nível X

    if desnivel <= EPS_M:
        condicao = COND_POSITIVA
        justificativa = (
            u"Eixo do rotor (cota {:.3f} m) está abaixo do nível X "
            u"(cota {:.3f} m), com folga de {:.3f} m — bomba afogada mesmo no "
            u"nível mínimo antes de vórtice.".format(
                cota_eixo, nivel_X, -desnivel))
    elif desnivel <= tolerancia + EPS_M:
        condicao = COND_POSITIVA_TOLERANCIA
        justificativa = (
            u"Eixo acima do nível X em {:.3f} m, dentro da tolerância admitida "
            u"de {:.3f} m ({}).".format(desnivel, tolerancia, base_tolerancia))
    else:
        condicao = COND_NEGATIVA
        justificativa = (
            u"Eixo acima do nível X em {:.3f} m, excedendo a tolerância de "
            u"{:.3f} m ({}) — exige o cálculo do NPSH disponível, com a vazão "
            u"nominal do sistema majorada em {:g}×.".format(
                desnivel, tolerancia, base_tolerancia, fator_vazao_npsh))

    # --- Passo 5: gatilho do NPSH ---
    exige_npsh = (condicao == COND_NEGATIVA)
    vazao_npsh_lmin = None
    if exige_npsh and q_nominal_lmin is not None:
        vazao_npsh_lmin = float(fator_vazao_npsh) * float(q_nominal_lmin)

    return {
        u"tipo_tomada":            tipo_tomada,
        u"dn_succao_mm":           float(dn_succao_mm),
        u"dimensao_A_mm":          a_mm,
        u"dimensao_B_mm":          b_mm,
        u"dimensao_A_interpolada": interpolado,
        u"dimensao_A_aplicada":    aplica_a,
        u"dimensao_A":             dimensao_A,
        u"observacao_A":           observacao_A,

        u"cota_fundo":             cota_fundo,
        u"cota_tomada":            cota_tomada,
        u"cota_eixo_rotor":        cota_eixo,
        u"nivel_X":                nivel_X,
        u"desnivel":               desnivel,

        u"tolerancia":             tolerancia,
        u"base_tolerancia":        base_tolerancia,
        u"condicao":               condicao,
        u"justificativa":          justificativa,
        u"succao_simples":         succao_simples(condicao),

        u"altura_nao_utilizavel":  altura_nao_utilizavel,
        u"volume_nao_utilizavel":  volume_nao_utilizavel,
        u"capacidade_efetiva":     capacidade_efetiva,
        u"altura_efetiva":         altura_efetiva,
        u"volume_total":           (None if volume_total_m3 is None
                                    else float(volume_total_m3)),
        u"area_planta":            (None if area_planta_m2 is None
                                    else float(area_planta_m2)),

        u"possui_antivortice":     bool(possui_dispositivo_antivortice),
        u"possui_poco_succao":     bool(possui_poco_succao),
        u"exige_npsh":             exige_npsh,
        u"vazao_npsh_lmin":        vazao_npsh_lmin,
        u"fator_vazao_npsh":       float(fator_vazao_npsh),
    }


def succao_simples(condicao):
    """
    Reduz o veredicto a "positiva"/"negativa" — é essa forma que o resto do
    motor consome para escolher o limite de velocidade do trecho de sucção.
    """
    return u"negativa" if condicao == COND_NEGATIVA else u"positiva"


# ===========================================================================
# Dados do reservatório que não vêm da geometria
# ===========================================================================

DEFAULT_DADOS = {
    u"cota_fundo_reservatorio": 0.0,
    u"volume_total_m3":         None,
    u"area_planta_m2":          None,
    u"possui_antivortice":      False,
    u"possui_poco_succao":      False,
    u"tipo_tomada":             None,   # None = detectar pela geometria
    # Entradas do NPSH disponível. Altitude e temperatura são escolhidas
    # entre as linhas das tabelas de hidrantes/npshd.py — por isso já vêm
    # preenchidas com o valor usual. NPSHr é dado de catálogo da bomba: sem
    # bomba definida fica vazio, e a comparação sai como pendente.
    u"altitude_m":              None,
    u"temperatura_c":           None,
    u"npshr_m":                 None,
}


def default_dados():
    return dict(DEFAULT_DADOS)


def normalizar_dados(dados):
    """Converte um dict cru (formulário ou JSON salvo) para o formato canônico."""
    base = default_dados()
    out  = dict(base)

    for chave in (u"cota_fundo_reservatorio", u"volume_total_m3",
                  u"area_planta_m2", u"npshr_m"):
        valor = dados.get(chave, base[chave])
        if valor is None or valor == u"":
            out[chave] = base[chave]
            continue
        try:
            out[chave] = float(valor)
        except (TypeError, ValueError):
            out[chave] = base[chave]

    if out[u"cota_fundo_reservatorio"] is None:
        out[u"cota_fundo_reservatorio"] = 0.0

    # Altitude e temperatura são chaves das tabelas de Ha/Hvp: inteiros, e
    # só valem se existirem na tabela — quem valida é hidrantes/npshd.py.
    for chave in (u"altitude_m", u"temperatura_c"):
        valor = dados.get(chave, base[chave])
        if valor is None or valor == u"":
            out[chave] = base[chave]
            continue
        try:
            out[chave] = int(round(float(valor)))
        except (TypeError, ValueError):
            out[chave] = base[chave]

    out[u"possui_antivortice"] = bool(dados.get(u"possui_antivortice", False))
    out[u"possui_poco_succao"] = bool(dados.get(u"possui_poco_succao", False))

    tipo = dados.get(u"tipo_tomada")
    out[u"tipo_tomada"] = tipo if tipo in TIPOS_TOMADA else None

    return out


def load_dados(doc):
    """Lê os dados de sucção salvos no projeto; None se não houver."""
    param = doc.ProjectInformation.LookupParameter(SUCCAO_PARAM)
    if not param:
        return None

    raw = param.AsString()
    if not raw or not raw.strip():
        return None

    try:
        dados = json.loads(raw)
    except Exception:
        return None

    if not isinstance(dados, dict):
        return None

    return normalizar_dados(dados)


def save_dados(doc, dados):
    """
    Grava os dados de sucção no projeto (JSON no Project Information).
    Precisa ser chamado dentro de uma Transaction já aberta pelo chamador.
    """
    param = doc.ProjectInformation.LookupParameter(SUCCAO_PARAM)
    if not param or param.IsReadOnly:
        return False, u"Parâmetro '{}' não encontrado no projeto.".format(SUCCAO_PARAM)

    param.Set(json.dumps(normalizar_dados(dados), ensure_ascii=True, sort_keys=True))
    return True, u"Dados de sucção salvos no projeto."
