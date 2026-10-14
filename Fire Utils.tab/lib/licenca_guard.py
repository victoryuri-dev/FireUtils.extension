# -*- coding: utf-8 -*-
"""
licenca_guard.py — trava de licença dos botões da faixa de opções.

Uso, logo depois do __title__ do script:

    from licenca_guard import exigir
    exigir(u"hidrantes")

Sem licença, mostra o motivo e encerra o script — o código abaixo da
chamada não roda.

A consulta em si não vai à rede: licenca.tem_acesso() lê o resultado que a
sessão já resolveu quando o Revit abriu. Só a primeira chamada de uma
sessão ainda não verificada é que espera o servidor (ver
licenca.garantir_verificado).
"""

import sys

from pyrevit import forms

import licenca

# Nome de cada módulo como aparece na página de preços, para a mensagem
# falar a mesma língua do site onde a pessoa vai contratar.
_NOME_DO_MODULO = {
    u"hidrantes": u"Hidrantes",
    u"saidas": u"Saídas",
    u"memorial": u"Memorial",
    u"pro": u"FireUtils PRO",
}

_URL_PLANOS = u"https://fireutils.com.br/planos"


def _nome(modulo):
    return _NOME_DO_MODULO.get(modulo, modulo)


def exigir(modulo):
    """
    Interrompe o script se a conta não puder usar este módulo.

    Duas situações pedem respostas diferentes: quem nunca entrou precisa
    fazer login, e quem entrou mas não contratou precisa contratar. Uma
    mensagem genérica de "sem acesso" deixaria o primeiro caso parecendo
    cobrança indevida.
    """
    if licenca.tem_acesso(modulo):
        return

    if not licenca.esta_autenticado():
        forms.alert(
            u"Entre na sua conta para usar esta ferramenta.\n\n"
            u"Abra o Carregador de Famílias (aba Fire Utils → Biblioteca) "
            u"e faça login. O acesso é liberado na hora, sem reiniciar o Revit.",
            title=u"Fire Utils",
            warn_icon=True,
        )
        sys.exit()

    # PRO é plano, não módulo: "licença do módulo FireUtils PRO" soaria
    # errado para quem acabou de ler a página de preços, onde ele aparece
    # como o plano que inclui os demais.
    if modulo == licenca.MODULO_PRO:
        motivo = u"Esta ferramenta é exclusiva do FireUtils PRO."
    else:
        motivo = u"Esta conta não tem licença do módulo {}.".format(_nome(modulo))

    forms.alert(
        u"{}\n\n"
        u"Contrate em:\n{}\n\n"
        u"Se você acabou de contratar, faça login novamente no Carregador "
        u"de Famílias para atualizar o acesso.".format(motivo, _URL_PLANOS),
        title=u"Fire Utils",
        warn_icon=True,
    )
    sys.exit()
