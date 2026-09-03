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
ficar indisponível — ver family_loader_webview_forms.alternar_painel.
"""

import os
import sys
import traceback

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

def _registrar_dockable_pane(nome_amigavel, importar_classe_painel):
    """
    Registra um Dockable Pane, isolando falhas por painel — se um painel
    falhar, os outros (se houver mais de um no futuro) continuam
    registrados normalmente, cada um reportando seu próprio erro.
    `importar_classe_painel` é uma função (não a classe direto) pra que o
    próprio import do módulo também caia dentro do try/except.
    """
    try:
        classe_painel = importar_classe_painel()
        if not forms.is_registered_dockable_panel(classe_painel):
            forms.register_dockable_panel(classe_painel, default_visible=False)
            print(u"[OK] Dockable Pane '{}' registrado.".format(nome_amigavel))
        else:
            print(u"[OK] Dockable Pane '{}' já estava registrado.".format(nome_amigavel))
    except Exception:
        # _mlogger.exception manda só pro log em arquivo do pyRevit (fácil
        # de passar despercebido); o print força a abertura da output
        # window dedicada do startup script, com o traceback bem visível.
        _mlogger.exception(u"Falha ao registrar o Dockable Pane '{}'".format(nome_amigavel))
        print(u"[ERRO] Falha ao registrar o Dockable Pane '{}':".format(nome_amigavel))
        print(traceback.format_exc())


_registrar_dockable_pane(
    u"Carregador de Famílias",
    lambda: __import__(
        u"family_loader_webview_forms", fromlist=[u"PainelCarregadorFamiliasWeb"]
    ).PainelCarregadorFamiliasWeb,
)
