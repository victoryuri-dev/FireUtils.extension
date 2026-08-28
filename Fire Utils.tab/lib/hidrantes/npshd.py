# -*- coding: utf-8 -*-
"""
npshd.py — Fire Utils · lib/hidrantes/

NPSH disponível na tubulação de sucção.

A verificação só é exigida quando a condição de sucção é NEGATIVA — quando a
cota de sucção da bomba fica acima da cota da RTI (comparação direta das
cotas altimétricas). Com sucção positiva/afogada a bomba não corre risco de
cavitação por essa via e a rotina não roda.

    NPSHd = Ha − Hvp + Hs − Hf,s

Na sucção negativa o nível de água está ABAIXO da sucção da bomba, então Hs é
negativo e a fórmula operacional vira:

    NPSHd = Ha − Hvp − |Hs| − Hf,s

|Hs| é a diferença entre a cota de sucção da bomba e a cota da RTI — o mesmo
|Hs| que a verificação da condição de sucção já calculou, reaproveitado aqui
para os dois módulos não divergirem.

Hf,s sai do mesmo Hazen-Williams do resto do memorial, aplicado ao trecho de
sucção, mas com a vazão majorada (Q_npsh = fator · Qt) — a majoração é
normativa e vale só para esta verificação, por isso o fator vem do perfil do
estado, não daqui.

Critério: NPSHd ≥ NPSHr. O NPSHr é dado de catálogo da bomba escolhida — não
se calcula a partir da instalação. Sem ele o módulo entrega o NPSHd e deixa a
comparação pendente, em vez de afirmar que atende.

Módulo puro: as tabelas de Ha e Hvp são propriedades físicas da água e da
atmosfera, praticamente iguais entre normas, e ficam aqui. Citações de
item/tabela e o fator de majoração da vazão vêm do perfil normativo.
"""

from __future__ import absolute_import


# ===========================================================================
# Tabelas de referência (propriedades físicas — não normativas)
# ===========================================================================

# Pressão atmosférica local em altura de coluna d'água, por altitude.
TABELA_HA = [
    (0,    10.33),
    (500,   9.72),
    (1000,  9.15),
    (1500,  8.61),
]

# Pressão de vapor da água, por temperatura de operação.
TABELA_HVP = [
    (10, 0.125),
    (15, 0.174),
    (20, 0.239),
    (25, 0.323),
    (30, 0.433),
    (35, 0.573),
    (40, 0.752),
]

# Padrões usuais: altitude baixa e água de reservatório em temperatura
# ambiente. Servem só como valor inicial do formulário — o usuário troca por
# seleção, entre as linhas das tabelas acima.
ALTITUDE_PADRAO    = 0
TEMPERATURA_PADRAO = 30

# Margem de segurança sobre o NPSHr. Não é exigência normativa — é boa
# prática de projeto, e por isso entra como sugestão, nunca como reprovação.
MARGEM_RECOMENDADA_M = 0.5


def _busca(tabela, chave):
    for k, v in tabela:
        if k == chave:
            return v
    return None


def ha_para_altitude(altitude_m):
    """Ha (mca) para uma altitude tabelada. None se a altitude não está na tabela."""
    return _busca(TABELA_HA, altitude_m)


def hvp_para_temperatura(temperatura_c):
    """Hvp (mca) para uma temperatura tabelada. None se não está na tabela."""
    return _busca(TABELA_HVP, temperatura_c)


def opcoes_altitude():
    """[(altitude_m, Ha_mca, rótulo)] para alimentar o combo do formulário."""
    return [(alt, ha, u"{:g} m — Ha = {:g} mca".format(alt, ha))
            for alt, ha in TABELA_HA]


def opcoes_temperatura():
    """[(temp_c, Hvp_mca, rótulo)] para alimentar o combo do formulário."""
    return [(t, hvp, u"{:g} °C — Hvp = {:g} mca".format(t, hvp))
            for t, hvp in TABELA_HVP]


# ===========================================================================
# Cálculo
# ===========================================================================

def calcular_npshd(altitude_m, temperatura_c, hs_abs_m, hf_s_mca,
                   npshr_m=None, margem_m=MARGEM_RECOMENDADA_M):
    """
    NPSH disponível na sucção.

    altitude_m/temperatura_c: linhas escolhidas nas tabelas de Ha e Hvp.
    hs_abs_m: |Hs|, distância vertical entre a cota de sucção da bomba e a
              cota da RTI.
    hf_s_mca: perda de carga no trecho de sucção, JÁ calculada com a vazão
              majorada.
    npshr_m:  NPSH requerido pela bomba (catálogo). None quando ainda não há
              bomba definida — a comparação fica pendente.

    Retorna dict pronto para o memorial.
    """
    ha  = ha_para_altitude(altitude_m)
    hvp = hvp_para_temperatura(temperatura_c)

    if ha is None:
        raise ValueError(
            u"Altitude {} m não está na tabela de pressão atmosférica.".format(
                altitude_m))
    if hvp is None:
        raise ValueError(
            u"Temperatura {} °C não está na tabela de pressão de vapor.".format(
                temperatura_c))

    hs_abs = abs(float(hs_abs_m))
    hf_s   = float(hf_s_mca)
    npshd  = ha - hvp - hs_abs - hf_s

    if npshr_m is None:
        atende = None
        folga  = None
        veredicto = (u"NPSHr não informado — a comparação não pode ser "
                     u"concluída. Informe o NPSH requerido da bomba escolhida "
                     u"(dado de catálogo do fabricante).")
    else:
        npshr = float(npshr_m)
        folga = npshd - npshr
        atende = folga >= 0.0
        if atende:
            veredicto = (u"NPSHd ({:.3f} mca) ≥ NPSHr ({:.3f} mca) — folga de "
                         u"{:.3f} mca.".format(npshd, npshr, folga))
            if margem_m and folga < float(margem_m):
                veredicto += (u" A folga é menor que a margem de segurança "
                              u"usualmente recomendada ({:g} mca); vale rever a "
                              u"bomba ou a geometria da sucção.".format(margem_m))
        else:
            veredicto = (u"NPSHd ({:.3f} mca) < NPSHr ({:.3f} mca) — falta "
                         u"{:.3f} mca. A bomba cavita nessa instalação: é "
                         u"preciso reduzir a perda ou a altura de sucção, ou "
                         u"escolher bomba com NPSHr menor.".format(
                             npshd, npshr, -folga))

    return {
        u"altitude_m":    altitude_m,
        u"temperatura_c": temperatura_c,
        u"Ha":            ha,
        u"Hvp":           hvp,
        u"Hs_abs":        hs_abs,
        u"Hf_s":          hf_s,
        u"NPSHd":         npshd,
        u"NPSHr":         (None if npshr_m is None else float(npshr_m)),
        u"folga":         folga,
        u"atende":        atende,
        u"margem":        margem_m,
        u"veredicto":     veredicto,
    }
