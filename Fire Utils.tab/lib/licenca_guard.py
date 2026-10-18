# -*- coding: utf-8 -*-
"""
licenca_guard.py — trava de licença dos botões da faixa de opções.

Uso, logo depois do __title__ do script:

    from licenca_guard import exigir
    exigir(u"hidrantes")

Sem licença, mostra o motivo e encerra o script — o código abaixo da
chamada não roda.

A consulta não vai à rede: licenca.tem_acesso() confere a assinatura do
token de licença guardado neste computador. Por isso as ferramentas de
produtividade funcionam offline — o token é renovado pela dockpane, sempre
que ela abre com internet.
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

    Quatro situações pedem respostas diferentes — uma mensagem genérica de
    "sem acesso" deixaria quem só precisa ativar parecendo cobrança indevida:
    sem licença guardada (nunca ativou neste computador), licença vencida
    (ficou muito tempo sem abrir o painel com internet), licença inválida e
    conta que simplesmente não contratou o módulo.
    """
    if licenca.tem_acesso(modulo):
        return

    situacao, _payload, motivo = licenca.situacao()

    if situacao == licenca.SIT_AUSENTE:
        forms.alert(
            u"Ative a licença neste computador para usar esta ferramenta.\n\n"
            u"Abra o painel Fire Utils (aba Fire Utils → Biblioteca), com "
            u"internet, e entre na sua conta. O acesso é liberado na hora, "
            u"sem reiniciar o Revit.",
            title=u"Fire Utils",
            warn_icon=True,
        )
        sys.exit()

    if situacao == licenca.SIT_EXPIRADO:
        forms.alert(
            u"A licença guardada neste computador venceu.\n\n"
            u"Ela se renova sozinha sempre que o painel Fire Utils abre com "
            u"internet. Abra o painel (aba Fire Utils → Biblioteca) conectado "
            u"e tente de novo.",
            title=u"Fire Utils",
            warn_icon=True,
        )
        sys.exit()

    if situacao == licenca.SIT_INVALIDO:
        forms.alert(
            u"Não foi possível validar a licença deste computador "
            u"({}).\n\n"
            u"Abra o painel Fire Utils (aba Fire Utils → Biblioteca), com "
            u"internet, e entre na sua conta para renová-la.".format(motivo),
            title=u"Fire Utils",
            warn_icon=True,
        )
        sys.exit()

    # PRO é plano, não módulo: "licença do módulo FireUtils PRO" soaria
    # errado para quem acabou de ler a página de preços, onde ele aparece
    # como o plano que inclui os demais.
    if modulo == licenca.MODULO_PRO:
        motivo_sem_acesso = u"Esta ferramenta é exclusiva do FireUtils PRO."
    else:
        motivo_sem_acesso = u"Esta conta não tem licença do módulo {}.".format(_nome(modulo))

    forms.alert(
        u"{}\n\n"
        u"Contrate em:\n{}\n\n"
        u"Se você acabou de contratar, abra o painel Fire Utils com internet "
        u"para atualizar o acesso.".format(motivo_sem_acesso, _URL_PLANOS),
        title=u"Fire Utils",
        warn_icon=True,
    )
    sys.exit()
