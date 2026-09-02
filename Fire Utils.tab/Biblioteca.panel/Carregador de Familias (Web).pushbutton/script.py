# -*- coding: utf-8 -*-
__title__ = "Carregador\nde Familias (Web)"
__doc__ = (
    "Versao Fase 3 do plano de migracao: mesmo Carregador de Familias, "
    "agora com o catalogo rodando como app web (React) hospedado num "
    "WebView2 embutido, consumindo o acervo do Supabase em vez da pasta "
    "local family_library/. Convive com o botao 'Carregador de Familias' "
    "classico durante a migracao. Clique para mostrar ou esconder o "
    "painel de encaixe (Dockable Pane)."
)

from family_loader_webview_forms import alternar_painel

alternar_painel(__revit__)
