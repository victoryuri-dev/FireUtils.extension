# -*- coding: utf-8 -*-
"""
startup.py — Fire Utils.extension (raiz da extensão)

Executado pelo pyRevit uma vez ao carregar a extensão (e a cada reload),
antes de qualquer botão da faixa de opções ficar disponível.

É o único lugar onde dá pra registrar Dockable Panes (painéis de encaixe)
junto da API do Revit — Application.RegisterDockablePane só pode ser
chamado durante o startup do add-in, nunca a partir de um clique de botão.
Por isso o Carregador de Famílias é registrado aqui, e o script do botão
(Fire Utils.tab/Biblioteca.panel/Carregador de Familias.pushbutton) só
mostra/esconde a instância já registrada.

pyRevit roda este script isolado, num engine e output window próprios: um
erro aqui não derruba o carregamento do resto da extensão, só faz o painel
ficar indisponível (o botão cai para o formulário padrão do pyRevit nesse
caso — ver family_loader_forms.alternar_painel).
"""

import os
import sys

from pyrevit import forms
from pyrevit.coreutils.logger import get_logger

_mlogger = get_logger(__name__)

# O módulo do painel mora em "Fire Utils.tab/lib", não em "lib" na raiz da
# extensão (que é o único diretório que o pyRevit adiciona sozinho ao
# sys.path de um startup.py) — por isso precisa ser incluído manualmente.
_EXT_ROOT = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_EXT_ROOT, u"Fire Utils.tab", u"lib")
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

try:
    from family_loader_forms import PainelCarregadorFamilias

    if not forms.is_registered_dockable_panel(PainelCarregadorFamilias):
        forms.register_dockable_panel(PainelCarregadorFamilias, default_visible=False)
except Exception:
    _mlogger.exception(
        u"Falha ao registrar o Dockable Pane do Carregador de Famílias"
    )
