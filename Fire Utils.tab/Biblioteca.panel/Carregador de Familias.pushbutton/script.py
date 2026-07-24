# -*- coding: utf-8 -*-
__title__ = "Carregador\nde Familias"
__doc__ = (
    "Pesquisa, filtra por categoria e carrega familias de combate a "
    "incendio a partir da biblioteca da extensao (Fire Utils.tab/lib/"
    "family_library) diretamente no projeto ativo. A janela fica aberta "
    "(modeless) enquanto voce trabalha no Revit."
)

from family_loader_forms import obter_ou_criar_janela

obter_ou_criar_janela(__revit__)
