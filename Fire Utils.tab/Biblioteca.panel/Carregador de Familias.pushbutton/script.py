# -*- coding: utf-8 -*-
__title__ = "Carregador\nde Familias"
__doc__ = (
    "Pesquisa, filtra por categoria e carrega familias de combate a "
    "incendio a partir da biblioteca da extensao (Fire Utils.tab/lib/"
    "family_library) diretamente no projeto ativo. Clique para mostrar ou "
    "esconder o painel de encaixe (Dockable Pane) do carregador."
)

from family_loader_forms import alternar_painel

alternar_painel(__revit__)
