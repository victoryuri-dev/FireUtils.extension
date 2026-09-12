# -*- coding: utf-8 -*-
__title__ = "Recalcular\nPopulação"
__doc__ = (
    u"Reaplica a taxa normativa ATUAL na População/Taxa Populacional de "
    u"todos os ambientes já classificados (Grupo já preenchido), sem "
    u"precisar reselecionar nada nem reclassificar ocupação.\n\n"
    u"Use depois de mudar a UF/norma do projeto ou quando a tabela "
    u"normativa for atualizada — sem isso, os ambientes classificados "
    u"antes continuam com o valor de população calculado com a taxa "
    u"antiga. Também sincroniza os ambientes com o site/dockpane em "
    u"seguida, então uma edição de área feita depois da classificação "
    u"também é levada pra lá nesse mesmo passo."
)

from pyrevit import revit, script, forms
from projeto import exigir_projeto_e_estado
from saidas.calc       import sincronizar_ambientes
from saidas.populacao  import garantir_parametros, recalcular_populacao
from saidas.rooms      import get_rooms_com_grupo, get_rooms_classificados

doc = revit.doc

if not garantir_parametros():
    forms.alert(u"Não foi possível verificar os parâmetros necessários.", title=u"Erro")
    script.exit()

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

rooms = get_rooms_com_grupo(doc)
if not rooms:
    forms.alert(u"Nenhum ambiente classificado encontrado no projeto.", title=u"Aviso")
    script.exit()

atualizados, sem_taxa = recalcular_populacao(rooms, estado)
sincronizar_ambientes(get_rooms_classificados(doc), estado, projeto_dir)

mensagem = u"{} ambiente(s) recalculado(s) com a taxa atual da norma.".format(atualizados)
if sem_taxa:
    mensagem += u"\n{} ambiente(s) com Grupo que não existe mais na norma atual — não foram alterados.".format(sem_taxa)
forms.alert(mensagem, title=u"Recalcular População")
