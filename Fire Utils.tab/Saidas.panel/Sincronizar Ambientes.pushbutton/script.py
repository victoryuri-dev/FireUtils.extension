# -*- coding: utf-8 -*-
__title__ = "Sincronizar\nAmbientes"
__doc__ = (
    u"Sincroniza os ambientes deste projeto com o site nos dois sentidos, "
    u"num único clique:\n\n"
    u"1. Puxa do site o nome atual de cada ambiente (casado por "
    u"Room.UniqueId) e reaplica no parâmetro Nome do Room aqui, se tiver "
    u"sido alterado por lá.\n"
    u"2. Reaplica a taxa normativa ATUAL na População/Taxa Populacional "
    u"de todos os ambientes já classificados (Grupo já preenchido).\n"
    u"3. Envia o resultado (nomes/área/população atualizados) de volta "
    u"pro site.\n\n"
    u"Use depois de renomear um ambiente no site, mudar a UF/norma do "
    u"projeto, editar a área de algum Room, ou sempre que quiser garantir "
    u"que Revit e site estão com os mesmos dados."
)

from pyrevit import revit, script, forms
from projeto import exigir_projeto_e_estado
from saidas.calc       import sincronizar_ambientes
from saidas.populacao  import garantir_parametros, recalcular_populacao, puxar_nomes_do_site
from saidas.rooms      import get_rooms_com_grupo, get_rooms_classificados

doc = revit.doc

if not garantir_parametros():
    forms.alert(u"Não foi possível verificar os parâmetros necessários.", title=u"Erro")
    script.exit()

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

# 1) Site -> Revit: nomes editados no site entram primeiro, pra já saírem
#    corretos no payload que o passo 3 envia de volta.
renomeados, nao_encontrados, erro_nomes = puxar_nomes_do_site(doc, projeto_dir)

# 2) Reaplica a taxa normativa atual nos ambientes já classificados.
rooms = get_rooms_com_grupo(doc)
if rooms:
    atualizados, sem_taxa = recalcular_populacao(rooms, estado)
else:
    atualizados, sem_taxa = 0, 0

# 3) Revit -> Site: envia nomes/área/população já atualizados.
sincronizar_ambientes(get_rooms_classificados(doc), estado, projeto_dir)

mensagem = u"{} ambiente(s) com população recalculada.".format(atualizados)
if renomeados:
    mensagem += u"\n{} nome(s) atualizado(s) a partir do site.".format(renomeados)
if sem_taxa:
    mensagem += (
        u"\n{} ambiente(s) com Grupo que não existe mais na norma atual "
        u"— não foram alterados.".format(sem_taxa)
    )
if nao_encontrados:
    mensagem += (
        u"\n{} ambiente(s) do site não encontrados neste modelo "
        u"(Room pode ter sido apagado ou está em outro arquivo)."
        .format(nao_encontrados)
    )
if erro_nomes:
    mensagem += u"\n[Nomes do site não sincronizados: {}]".format(erro_nomes)

forms.alert(mensagem, title=u"Sincronizar Ambientes")
