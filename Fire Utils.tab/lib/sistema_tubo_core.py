# -*- coding: utf-8 -*-
"""
sistema_tubo_core.py — Fire Utils · lib/
Carrega um "sistema de tubo" no projeto ativo a partir de um .rvt do catálogo.

Tubo não é família .rfa: é um Tipo de Tubulação (PipeType) com segmentos e
preferências de roteamento, que apontam para famílias de conexão. Em vez de
recriar isso por código, o catálogo guarda um .rvt por sistema (ex.: tubo
ranhurado, BSP) e este módulo faz o equivalente programático do "copiar e
colar entre projetos" do Revit (ElementTransformUtils.CopyElements, que não
usa a área de transferência do Windows):

  1. Abre o .rvt em segundo plano (sem janela, o projeto do usuário não é
     tocado).
  2. Confere por NOME quais PipeType do arquivo o projeto ainda não tem. Os
     que já existem não são copiados — carregar de novo não duplica nada.
  3. Copia os que faltam. Quando o arquivo traz um trecho de tubo daquele
     tipo, é o trecho que se copia (como no copiar/colar da interface, ele
     leva junto as preferências de roteamento e as conexões); sem trecho,
     copia-se o próprio tipo. O trecho colado é apagado em seguida: o tipo,
     o segmento e as conexões ficam no projeto.
  4. Nomes iguais de tipos que o projeto já tenha (conexões, segmentos, etc.)
     são reaproveitados (UseDestinationTypes), não viram "Tipo 1".
  5. Fecha o arquivo de origem sem salvar.

Tudo no projeto do usuário acontece numa transação só: se algo falhar, nada
é aplicado.

Precisa rodar dentro de um ExternalEvent (contexto de API válido), fora de
qualquer transação.
"""

import clr
clr.AddReference(u"RevitAPI")

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BuiltInParameter,
    CopyPasteOptions,
    DuplicateTypeAction,
    Element,
    ElementId,
    ElementTransformUtils,
    FilteredElementCollector,
    IDuplicateTypeNamesHandler,
    Transaction,
    Transform,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipeType

from family_error_utils import texto_erro

CARREGADO = u"carregado"
JA_EXISTENTE = u"ja_existente"


class _ReusarTiposDoDestino(IDuplicateTypeNamesHandler):
    """Tipo de mesmo nome já existente no projeto: usa o do projeto."""

    def OnDuplicateTypeNamesFound(self, args):
        return DuplicateTypeAction.UseDestinationTypes


def _nome(elemento):
    """
    Nome do elemento, sem depender de `elemento.Name`.

    No IronPython, `.Name` de um tipo (ElementType) é resolvido de forma
    ambígua entre ElementType.Name e Element.Name e pode falhar com um erro
    seco ("Name"). Tenta, em ordem: a propriedade da classe base
    (Element.Name), o acessor .NET direto (get_Name) e, por último, o
    parâmetro "Nome do tipo" (ALL_MODEL_TYPE_NAME). Só levanta se nenhum
    funcionar, dizendo qual elemento e o que cada tentativa respondeu.
    """
    falhas = []
    for descricao, ler in (
        (u"Element.Name", lambda: Element.Name.GetValue(elemento)),
        (u"get_Name", lambda: elemento.get_Name()),
        (u"ALL_MODEL_TYPE_NAME", lambda: elemento.get_Parameter(
            BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()),
    ):
        try:
            valor = ler()
            if valor:
                return valor
        except Exception as ex:
            falhas.append(u"{}: {}".format(descricao, texto_erro(ex)))
    raise ValueError(u"Não foi possível ler o nome do elemento {} ({}) — {}".format(
        elemento.Id.IntegerValue, type(elemento).__name__, u"; ".join(falhas)))


def _tipos_de_tubo(doc):
    """{nome: ElementId} dos PipeType do documento."""
    return dict((_nome(t), t.Id) for t in FilteredElementCollector(doc).OfClass(PipeType))


def carregar_sistema(uiapp, doc, caminho):
    """
    Copia para `doc` os tipos de tubo do .rvt em `caminho` que ele ainda não
    tem. Devolve (estado, nomes): estado é CARREGADO ou JA_EXISTENTE; `nomes`
    são os tipos de tubo copiados (ou, em JA_EXISTENTE, os que já havia).
    Levanta exceção com mensagem legível se algo falhar.
    """
    if doc.IsFamilyDocument:
        raise ValueError(u"Abra um projeto (não uma família) para carregar o sistema.")

    origem = uiapp.Application.OpenDocumentFile(caminho)
    try:
        tipos_origem = _tipos_de_tubo(origem)
        if not tipos_origem:
            raise ValueError(u"O arquivo do sistema não contém nenhum tipo de tubulação.")

        existentes = _tipos_de_tubo(doc)
        faltando = sorted(n for n in tipos_origem if n not in existentes)
        if not faltando:
            return JA_EXISTENTE, sorted(tipos_origem)

        # Um trecho de tubo por tipo, se o arquivo tiver: é ele que leva as
        # preferências de roteamento e as conexões, como no copiar/colar.
        trecho_por_tipo = {}
        for tubo in FilteredElementCollector(origem).OfClass(Pipe):
            nome_tipo = _nome(tubo.PipeType)
            if nome_tipo not in trecho_por_tipo:
                trecho_por_tipo[nome_tipo] = tubo.Id

        ids = List[ElementId]()
        for nome in faltando:
            ids.Add(trecho_por_tipo.get(nome) or tipos_origem[nome])

        opcoes = CopyPasteOptions()
        opcoes.SetDuplicateTypeNamesHandler(_ReusarTiposDoDestino())

        with Transaction(doc, u"FireUtils - Carregar sistema de tubo") as t:
            t.Start()
            try:
                copiados = ElementTransformUtils.CopyElements(
                    origem, ids, doc, Transform.Identity, opcoes)

                # O trecho colado só serviu para trazer o tipo e as conexões.
                colados = List[ElementId]()
                for eid in copiados:
                    if isinstance(doc.GetElement(eid), Pipe):
                        colados.Add(eid)
                if colados.Count:
                    doc.Delete(colados)
                t.Commit()
            except Exception:
                t.RollBack()
                raise

        depois = _tipos_de_tubo(doc)
        ausentes = [n for n in faltando if n not in depois]
        if ausentes:
            raise ValueError(
                u"A cópia terminou, mas estes tipos não entraram no projeto: {}.".format(
                    u", ".join(ausentes)))
        return CARREGADO, faltando
    finally:
        try:
            origem.Close(False)
        except Exception:
            pass
