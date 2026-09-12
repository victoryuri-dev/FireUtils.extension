# -*- coding: utf-8 -*-
__title__ = "Puxar Nomes\ndo Site"
__doc__ = (
    u"Busca no site o nome atual de cada ambiente da estrutura vinculada e "
    u"reaplica no parâmetro Nome do Room correspondente aqui no Revit "
    u"(casado por Room.UniqueId) — caminho inverso do que 'Recalcular "
    u"População' já faz (Revit → Site).\n\n"
    u"Use depois de renomear um ambiente no site/dockpane, pra trazer esse "
    u"nome de volta pro modelo."
)

from pyrevit import revit, script, forms
from projeto import exigir_projeto_e_estado
from saidas.populacao import puxar_nomes_do_site

doc = revit.doc

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

atualizados, nao_encontrados, erro = puxar_nomes_do_site(doc, projeto_dir)
if erro:
    forms.alert(erro, title=u"Puxar Nomes do Site")
    script.exit()

mensagem = u"{} ambiente(s) renomeado(s) a partir do site.".format(atualizados)
if nao_encontrados:
    mensagem += (
        u"\n{} ambiente(s) do site não encontrados neste modelo "
        u"(o Room pode ter sido apagado ou está em outro arquivo)."
        .format(nao_encontrados)
    )
forms.alert(mensagem, title=u"Puxar Nomes do Site")
