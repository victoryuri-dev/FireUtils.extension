# -*- coding: utf-8 -*-
__title__ = "Sincronizar\nAmbientes"
__doc__ = (
    u"Sincroniza os ambientes deste projeto com o site nos dois sentidos, "
    u"num único clique:\n\n"
    u"1. Envia pro site o Nome/Grupo/Área atuais de cada ambiente já "
    u"classificado (casado por Room.UniqueId) — Revit é quem manda nesses "
    u"campos.\n"
    u"2. Puxa de volta do site a População e a Taxa Populacional já "
    u"calculadas por lá (área x taxa normativa vigente, ou o valor "
    u"manual/assento fixo cadastrado na tela de Acessos e Descargas) e "
    u"grava nos parâmetros do Room correspondente — o site é quem manda "
    u"nesses campos.\n\n"
    u"Use depois de editar um ambiente aqui (nome, classificação, área) "
    u"ou lá no site (população manual, assentos fixos, taxa normativa), "
    u"ou sempre que quiser garantir que Revit e site estão com os mesmos "
    u"dados."
)

from pyrevit import revit, script, forms
from projeto import exigir_projeto_e_estado
from saidas.calc       import sincronizar_ambientes
from saidas.populacao  import garantir_parametros, puxar_populacao_do_site
from saidas.rooms      import get_rooms_classificados

doc = revit.doc

if not garantir_parametros():
    forms.alert(u"Não foi possível verificar os parâmetros necessários.", title=u"Erro")
    script.exit()

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

# 1) Revit -> Site: envia nome/grupo/área atuais.
sincronizar_ambientes(get_rooms_classificados(doc), estado, projeto_dir)

# 2) Site -> Revit: puxa população/taxa populacional já calculadas lá.
atualizados, nao_encontrados, erro_pop = puxar_populacao_do_site(doc, projeto_dir)

if erro_pop:
    mensagem = u"Ambientes enviados pro site.\n[População não sincronizada: {}]".format(erro_pop)
else:
    mensagem = u"{} ambiente(s) com população atualizada a partir do site.".format(atualizados)
    if nao_encontrados:
        mensagem += (
            u"\n{} ambiente(s) do site não encontrados neste modelo "
            u"(Room pode ter sido apagado ou está em outro arquivo)."
            .format(nao_encontrados)
        )

forms.alert(mensagem, title=u"Sincronizar Ambientes")
