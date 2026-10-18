# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes

O dimensionamento hidráulico (método da marcha, Fator K, equilíbrio no Ponto
A, sucção/NPSH e verificações normativas) roda no servidor — ver
motor_nuvem.py e hidrantes_dimensionar_bridge.py — e é disparado pela
dockpane, que tem a sessão da conta, quem autentica o pedido. Este botão
ficou só como atalho: abre a dockpane.
"""
__title__ = "Dimensionar\nHidrantes"
__doc__ = (
    "Abre o painel Fire Utils. O dimensionamento de hidrantes é feito na aba "
    "'Sistema de Hidrantes', pelo botão Dimensionar."
)

# Trava de licenca: encerra o script se a conta nao tiver o modulo.
from licenca_guard import exigir
exigir(u"hidrantes")

from pyrevit import forms

from family_loader_webview_forms import mostrar_painel

if mostrar_painel(__revit__):
    forms.alert(
        u"O dimensionamento de hidrantes agora é feito no painel Fire Utils.\n\n"
        u"Abra a aba \"Sistema de Hidrantes\" e clique em Dimensionar. "
        u"Ele precisa de internet: o cálculo roda no servidor.",
        title=u"Fire Utils",
    )
