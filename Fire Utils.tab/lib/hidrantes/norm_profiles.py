# -*- coding: utf-8 -*-
"""
norm_profiles.py - Fire Utils - lib/hidrantes/
Adaptador fino sobre o centro normativo unificado (lib/normas/<UF>/hidrantes.py).

Os dados normativos de hidrantes agora vivem em lib/normas/<UF>/hidrantes.py,
ao lado dos dados de saidas de emergencia do mesmo estado (lib/normas/<UF>/saidas.py).
Este modulo existe apenas para nao quebrar o import ja usado em
"Dimensionar Hidrantes"/script.py (from hidrantes.norm_profiles import get_profile, req).

Uso:
    from hidrantes.norm_profiles import get_profile, req

    perfil = get_profile(sigla_estado)   # default "MA" se a UF nao tiver dominio hidrantes
    c_ref = req(perfil, u"hazen_c_ref")  # erro claro se a chave nao existir
"""

import copy

from normas import get_estado


class NormProfileError(Exception):
    """Erro de perfil normativo: chave obrigatoria ausente ou nenhum perfil disponivel."""
    pass


def get_profile(uf):
    """
    Retorna uma copia do perfil normativo de hidrantes ativo para a UF informada
    (lib/normas/<UF>/hidrantes.py).

    Se a UF nao tiver perfil proprio nem dominio "hidrantes" cadastrado ainda,
    cai para "MA" (default explicito) - isso e sinalizado nas chaves internas
    '_uf_solicitada' e '_uf_efetiva', para que o memorial possa avisar quando
    os dois divergirem, em vez de silenciar a substituicao.
    """
    sigla_solicitada = (uf or u"MA").upper()

    estado = get_estado(sigla_solicitada)
    dados = estado.get(u"hidrantes") if estado else None
    sigla_efetiva = sigla_solicitada

    if dados is None:
        sigla_efetiva = u"MA"
        estado_ma = get_estado(u"MA")
        dados = estado_ma.get(u"hidrantes") if estado_ma else None
        if dados is None:
            raise NormProfileError(
                u"Nenhum perfil normativo de hidrantes disponivel (nem 'MA'). "
                u"Verifique lib/normas/MA/hidrantes.py.")

    perfil = copy.deepcopy(dados)
    perfil[u"_uf_solicitada"] = sigla_solicitada
    perfil[u"_uf_efetiva"] = sigla_efetiva
    return perfil


def req(perfil, chave):
    """
    Acessa uma chave obrigatoria do perfil normativo ativo.

    Lanca NormProfileError com mensagem clara se a chave nao existir -
    nunca usa silenciosamente o valor de outro estado como fallback.
    """
    if chave not in perfil:
        raise NormProfileError(
            u"O perfil normativo '{}' ({}) nao define o parametro obrigatorio "
            u"'{}'. Adicione '{}' em lib/normas/{}/hidrantes.py.".format(
                perfil.get(u"_uf_efetiva", u"?"),
                perfil.get(u"norma", u"?"),
                chave, chave, perfil.get(u"_uf_efetiva", u"?")))
    return perfil[chave]


def lista_ufs_disponiveis():
    """Retorna a lista de siglas de UF com domínio 'hidrantes' cadastrado."""
    from normas import lista_estados
    ufs = []
    for sigla, _ in lista_estados():
        estado = get_estado(sigla)
        if estado and estado.get(u"hidrantes"):
            ufs.append(sigla)
    return ufs
