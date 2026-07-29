# -*- coding: utf-8 -*-
__title__ = u"Parar\nServidor"

from pyrevit import forms, script
from server.launcher import servidor_ativo, parar_servidor, url_servidor

if not servidor_ativo():
    forms.alert(
        u"O servidor não está rodando.",
        title=u"Fire Utils — Servidor Local"
    )
    script.exit()

resposta = forms.alert(
    u"Servidor rodando em {}\n\nDeseja encerrar o servidor agora?".format(url_servidor()),
    title=u"Fire Utils — Parar Servidor",
    ok=True,
    cancel=True,
)
if not resposta:
    script.exit()

parar_servidor()

if servidor_ativo():
    forms.alert(
        u"Não foi possível encerrar o servidor automaticamente.\n"
        u"Encerre manualmente via Gerenciador de Tarefas (python.exe).",
        title=u"Fire Utils", warn_icon=True
    )
else:
    forms.alert(
        u"Servidor encerrado com sucesso.",
        title=u"Fire Utils — Servidor Local"
    )
