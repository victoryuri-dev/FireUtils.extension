# -*- coding: utf-8 -*-
"""
projeto.py — Fire Utils · lib/
Utilitário central para verificação de projeto e estado.

Uso em qualquer script:
    from projeto import exigir_projeto_e_estado
    projeto_dir, sigla, estado = exigir_projeto_e_estado(doc, forms, script)
"""

import os
import io
import json

_CACHE_NOME = u"firedata.json"
_TEMP       = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
_LAST_PROJ  = os.path.join(_TEMP, u"fireutils_last_project.txt")


# ── Ponteiro ──────────────────────────────────────────────────────────────────

def salvar_ponteiro(projeto_dir):
    """Grava %TEMP%/fireutils_last_project.txt para o servidor Flask encontrar o cache."""
    try:
        with io.open(_LAST_PROJ, "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


# ── Cache ─────────────────────────────────────────────────────────────────────

def cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def carregar_cache(projeto_dir):
    path = cache_path(projeto_dir)
    if not os.path.exists(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}


def carregar_dados_projeto(projeto_dir):
    """Retorna o dict dados_projeto salvo no firedata.json, ou None."""
    return carregar_cache(projeto_dir).get(u"dados_projeto")


# ── Verificação principal ─────────────────────────────────────────────────────

def exigir_projeto_e_estado(doc, forms, script):
    """
    Verifica dois pré-requisitos antes de qualquer dimensionamento:

      1. O projeto Revit está salvo em disco (.rvt).
      2. O campo 'Estado' foi preenchido em Projeto → Dados do Projeto.

    Se qualquer verificação falhar, exibe alerta e chama script.exit().

    Retorna:
        (projeto_dir, sigla_estado, estado_dict)
        ex.: ("C:/projetos/obra", "MA", {...})
    """
    # 1 — projeto salvo?
    if not doc.PathName:
        forms.alert(
            u"O projeto Revit não está salvo.\n\n"
            u"Salve o arquivo (.rvt) antes de prosseguir — os dados\n"
            u"de cálculo são gravados na pasta do projeto.",
            title=u"Fire Utils — Salve o projeto",
            warn_icon=True,
        )
        script.exit()

    projeto_dir = os.path.dirname(doc.PathName)
    salvar_ponteiro(projeto_dir)   # mantém ponteiro atualizado para o servidor Flask

    # 2 — estado configurado?
    dados = carregar_dados_projeto(projeto_dir)
    uf    = dados.get(u"uf") if dados else None
    if not uf:
        forms.alert(
            u"O Estado do projeto não foi configurado.\n\n"
            u"Acesse  Projeto → Dados do Projeto  e selecione o Estado\n"
            u"antes de prosseguir.",
            title=u"Fire Utils — Dados do Projeto",
            warn_icon=True,
        )
        script.exit()

    # 3 — carregar dados normativos
    from estados import get_estado
    estado = get_estado(uf)
    if not estado:
        forms.alert(
            u"Estado '{}' não encontrado na extensão.\n"
            u"Verifique os Dados do Projeto.".format(uf),
            title=u"Fire Utils",
            warn_icon=True,
        )
        script.exit()

    return projeto_dir, uf, estado
