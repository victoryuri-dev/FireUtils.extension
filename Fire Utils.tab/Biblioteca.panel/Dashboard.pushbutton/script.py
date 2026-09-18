# -*- coding: utf-8 -*-
__title__ = "Vincular\nProjeto"
__doc__ = (
    "Abre a dockpane direto na aba Dashboard, de onde o projeto Revit "
    "ativo e vinculado a um projeto/estrutura do site (ETOS.FireUtils). "
    "Mesmo painel do Carregador de Familias - so muda a aba inicial, pra "
    "quem quer vincular o projeto sem passar pela Biblioteca de Familias."
)

from family_loader_webview_forms import abrir_dashboard

abrir_dashboard(__revit__)
