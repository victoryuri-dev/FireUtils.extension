# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Iniciar Servidor Local
Inicia o servidor Flask (CPython) e abre o memorial no browser.
"""
__title__ = u"Memorial\nDescritivo"

import os
from pyrevit import forms, script
from server.launcher import iniciar_servidor, servidor_ativo, url_servidor
from server.client  import url_memorial

output = script.get_output()

# ---- Verificar se já está rodando -------------------------------------------
if servidor_ativo():
    resposta = forms.alert(
        u"O servidor já está rodando em {}\n\nDeseja abrir o memorial no navegador?".format(
            url_servidor()
        ),
        title=u"Fire Utils — Servidor Local",
        ok=True,
        cancel=True,
    )
    if resposta:
        os.startfile(url_memorial())
    script.exit()

# ---- Tentar iniciar ----------------------------------------------------------
output.print_md(u"# Fire Utils — Iniciando Servidor Local")
output.print_md(u"Aguarde enquanto o servidor é iniciado...")

ok = iniciar_servidor()

if ok:
    output.print_md(u"✅ **Servidor iniciado com sucesso!**")
    output.print_md(u"Endereço: `{}`".format(url_servidor()))
    output.print_md(u"Memorial:  `{}`".format(url_memorial()))
    output.print_md(u"")
    output.print_md(
        u"> Execute **Dimensionar Hidrantes** e/ou **Dimensionar Saídas** — "
        u"os dados serão enviados automaticamente ao servidor.  \n"
        u"> Depois acesse **{}** para ver o memorial atualizado.".format(url_memorial())
    )

    # Abre o memorial (pode estar vazio se ainda não calculou, mas já mostra a página)
    os.startfile(url_memorial())
else:
    # Diagnóstico
    from server.launcher import _encontrar_python, _APP_PY
    py = _encontrar_python()

    linhas = [u"Não foi possível iniciar o servidor.\n"]
    if py:
        linhas.append(u"Python encontrado: {}".format(py))
        linhas.append(u"Script: {}".format(_APP_PY))
        linhas.append(u"\nVerifique se Flask está instalado:")
        linhas.append(u"  pip install flask")
    else:
        linhas.append(u"Python (CPython) não encontrado na máquina.")
        linhas.append(u"\nInstale Python 3.x em https://www.python.org/downloads/")
        linhas.append(u"e execute:  pip install flask")
        linhas.append(u"\nOu defina a variável de ambiente FIREUTILS_PYTHON")
        linhas.append(u"apontando para o executável python.exe.")

    forms.alert(u"\n".join(linhas), title=u"Fire Utils — Servidor Local", warn_icon=True)
    script.exit()
