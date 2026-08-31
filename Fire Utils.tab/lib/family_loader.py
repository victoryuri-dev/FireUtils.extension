# -*- coding: utf-8 -*-
"""
family_loader.py — Fire Utils · lib/
Varre a biblioteca única de famílias de combate a incêndio
(lib/family_library/) e carrega as famílias selecionadas no documento ativo.

Cada subpasta imediata de family_library/ vira uma categoria (ex.:
family_library/Hidrantes/ → categoria "Hidrantes"); arquivos .rfa soltos
diretamente em family_library/ caem na categoria genérica "Geral".

Para adicionar novas famílias, basta copiar o .rfa para dentro de uma
subpasta (existente ou nova) de lib/family_library/ — nenhuma alteração de
código é necessária, o carregador varre a pasta automaticamente toda vez que
é aberto (ou quando o botão "Atualizar pasta" é clicado).
"""

import os
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
FAMILY_LIBRARY_DIR = os.path.join(_LIB_DIR, u"family_library")

# Cache de previews (miniaturas .png) — espelha a estrutura de pastas da
# biblioteca, trocando .rfa por .png (ex.: family_library/Hidrantes/X.rfa ->
# family_library/.previews/Hidrantes/X.png). Adicionado manualmente (não há
# geração automática): o gestor da biblioteca exporta/coloca o .png de cada
# família nesse caminho espelhado e o catálogo passa a mostrá-lo no lugar do
# monograma de duas letras.
_PREVIEWS_DIRNAME = u".previews"
PREVIEWS_DIR = os.path.join(FAMILY_LIBRARY_DIR, _PREVIEWS_DIRNAME)


class FamilyEntry(object):
    """Representa uma família (.rfa) encontrada na biblioteca."""

    def __init__(self, name, category, path):
        self.name = name
        self.category = category
        self.path = path

    def __repr__(self):
        return u"<FamilyEntry {} [{}]>".format(self.name, self.category)


def _arquivos_rfa(pasta):
    try:
        return [f for f in os.listdir(pasta) if f.lower().endswith(u".rfa")]
    except OSError:
        return []


def _scan_pasta(pasta, categoria_fixa):
    entradas = []
    if not os.path.isdir(pasta):
        return entradas

    if categoria_fixa is not None:
        for nome_arquivo in _arquivos_rfa(pasta):
            entradas.append(FamilyEntry(
                name=os.path.splitext(nome_arquivo)[0],
                category=categoria_fixa,
                path=os.path.join(pasta, nome_arquivo),
            ))
        return entradas

    # Sem categoria fixa: cada subpasta vira uma categoria própria.
    for item in os.listdir(pasta):
        if item == _PREVIEWS_DIRNAME:
            continue  # pasta de cache de previews, não é uma categoria
        caminho_item = os.path.join(pasta, item)
        if os.path.isdir(caminho_item):
            for nome_arquivo in _arquivos_rfa(caminho_item):
                entradas.append(FamilyEntry(
                    name=os.path.splitext(nome_arquivo)[0],
                    category=item,
                    path=os.path.join(caminho_item, nome_arquivo),
                ))
        elif item.lower().endswith(u".rfa"):
            entradas.append(FamilyEntry(
                name=os.path.splitext(item)[0],
                category=u"Geral",
                path=caminho_item,
            ))
    return entradas


def listar_familias():
    """
    Varre lib/family_library/ e retorna a lista de FamilyEntry encontrada,
    ordenada por categoria e nome. Nomes duplicados (mesmo nome de família em
    mais de uma subpasta) mantêm apenas a primeira ocorrência encontrada.
    """
    vistos = set()
    resultado = []
    for entrada in _scan_pasta(FAMILY_LIBRARY_DIR, None):
        chave = entrada.name.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(entrada)

    resultado.sort(key=lambda e: (e.category, e.name))
    return resultado


def listar_categorias(entradas):
    """Retorna a lista de categorias distintas presentes em `entradas`, ordenada."""
    categorias = set(entrada.category for entrada in entradas)
    return sorted(categorias)


# ---------------------------------------------------------------------------
# Preview (miniatura) das famílias — cache em .png, gerado sob demanda
# ---------------------------------------------------------------------------
def caminho_preview(entrada):
    """Caminho do .png de preview em cache para uma FamilyEntry — espelha a
    posição do .rfa dentro de family_library/, trocado para dentro de
    family_library/.previews/ com extensão .png."""
    relativo = os.path.relpath(entrada.path, FAMILY_LIBRARY_DIR)
    relativo_png = os.path.splitext(relativo)[0] + u".png"
    return os.path.join(PREVIEWS_DIR, relativo_png)


def preview_valido(entrada):
    """Retorna o caminho do .png em cache se ele existir e for mais recente
    que o .rfa de origem; None se precisa ser (re)gerado."""
    caminho_png = caminho_preview(entrada)
    if not os.path.isfile(caminho_png):
        return None
    try:
        if os.path.getmtime(caminho_png) < os.path.getmtime(entrada.path):
            return None  # .rfa foi modificado depois do cache — está desatualizado
    except OSError:
        return None
    return caminho_png


def carregar_familias(doc, entradas):
    """
    Carrega a lista de FamilyEntry no documento ativo.

    Retorno: (carregadas, ja_existentes, erros)
      carregadas    : lista de nomes carregados com sucesso
      ja_existentes : lista de nomes que já estavam no projeto (não recarregados)
      erros         : lista de tuplas (nome, mensagem_de_erro)
    """
    existentes = set(
        f.Name for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
    )

    carregadas = []
    ja_existentes = []
    erros = []

    with Transaction(doc, u"FireUtils - Carregar Familias") as t:
        t.Start()
        try:
            for entrada in entradas:
                if entrada.name in existentes:
                    ja_existentes.append(entrada.name)
                    continue
                if not os.path.exists(entrada.path):
                    erros.append((entrada.name, u"Arquivo não encontrado em disco."))
                    continue
                try:
                    ref_familia = clr.Reference[Family]()
                    if doc.LoadFamily(entrada.path, ref_familia):
                        carregadas.append(entrada.name)
                    else:
                        erros.append((entrada.name, u"LoadFamily retornou False."))
                except Exception as e:
                    erros.append((entrada.name, str(e)))
            t.Commit()
        except Exception as e:
            t.RollBack()
            erros.append((u"(transação)", str(e)))

    return carregadas, ja_existentes, erros


def obter_symbol_para_posicionar(doc, nome_familia):
    """
    Retorna o primeiro FamilySymbol (tipo) da família `nome_familia`, já
    carregada em `doc`, garantindo que esteja ativo — pronto para uso em
    uidoc.PromptForFamilyInstancePlacement(). Retorna None se a família ou
    algum tipo não for encontrado.
    """
    familia = next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if f.Name == nome_familia),
        None
    )
    if familia is None:
        return None

    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None

    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar tipo") as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo
