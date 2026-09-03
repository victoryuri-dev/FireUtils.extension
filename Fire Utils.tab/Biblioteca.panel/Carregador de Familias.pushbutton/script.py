# -*- coding: utf-8 -*-
__title__ = "Carregador\nde Familias"
__doc__ = (
    "Pesquisa, filtra por categoria e carrega familias de combate a "
    "incendio a partir do acervo no Supabase diretamente no projeto "
    "ativo. O catalogo roda como app web (React) hospedado num WebView2 "
    "embutido. Clique para mostrar ou esconder o painel de encaixe "
    "(Dockable Pane)."
)

from family_loader_webview_forms import alternar_painel

alternar_painel(__revit__)
