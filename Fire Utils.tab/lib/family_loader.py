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

from family_error_utils import texto_erro

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
    """Representa uma família (.rfa) encontrada na biblioteca.

    `nome_revit` é o nome que o Revit vai atribuir à família ao carregar
    o arquivo em `path` (normalmente o nome do arquivo sem extensão) —
    usado internamente pra achar a família de novo no documento (checagem
    de "já existe" e o rename cosmético depois do load). Pra quem chama
    de fora do bridge (ex.: o scan local legado abaixo), o nome do
    arquivo já É o nome de exibição, então por padrão `nome_revit` cai
    pra `name`.
    """

    def __init__(self, name, category, path, nome_revit=None):
        self.name = name
        self.category = category
        self.path = path
        self.nome_revit = nome_revit if nome_revit is not None else name

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


def _familias_por_nome_no_documento(doc):
    """
    Devolve {Family.Name: Family} de cada família já presente em `doc`.

    Uma família cujo .Name não puder ser lido é simplesmente pulada (em
    vez de derrubar a chamada inteira) — em projetos reais e antigos, às
    vezes uma família específica tem o nome salvo internamente de um jeito
    que o Revit/.NET não consegue traduzir de volta pra texto num
    ambiente IronPython (mesma classe de erro de codificação documentada
    em family_error_utils.py); isso não deveria impedir de listar as
    outras centenas de famílias normais do projeto.
    """
    resultado = {}
    for familia in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            resultado[familia.Name] = familia
        except Exception:
            continue
    return resultado


def carregar_familias(doc, entradas):
    """
    Carrega a lista de FamilyEntry no documento ativo.

    Retorno: (carregadas, ja_existentes, erros, familias_por_nome)
      carregadas         : lista de FamilyEntry.name carregados com sucesso
      ja_existentes      : lista de FamilyEntry.name que já estavam no
                           projeto (não recarregados)
      erros              : lista de tuplas (nome, mensagem_de_erro)
      familias_por_nome  : dict {FamilyEntry.name: Family} com o objeto
                           Family de verdade carregado (ou já existente).

    O LoadFamily em si usa sempre FamilyEntry.nome_revit (o nome que o
    arquivo dá à família — um slug ASCII, ver family_cache.py), nunca
    FamilyEntry.name (o nome de exibição, que pode ter acento) — só
    depois do Commit desta função é que uma tentativa (best-effort, numa
    transação própria) troca Family.Name pro nome de exibição de
    verdade, via _tentar_renomear_para_exibicao. Motivo: um Family.Name
    acentuado, na prática, ainda conseguia disparar a mesma classe de
    erro de codificação do IronPython durante o Commit em algumas
    máquinas — ao manter o load principal inteiramente livre de texto
    acentuado e isolar o rename cosmético depois, uma falha no rename
    nunca mais atrasa nem quebra o aviso de "carregamento concluído" que
    o frontend já está esperando.

    A checagem de "já existe" testa os dois nomes possíveis
    (nome_revit — o slug, se um carregamento anterior não chegou a
    renomear — e name — o nome de exibição, se já renomeou com sucesso),
    porque depois de uma renomeação bem-sucedida o slug fica livre de
    novo, e sem essa checagem dupla um carregamento seguinte recriaria a
    família como duplicata em vez de reconhecer a já existente.
    """
    existentes_por_nome = _familias_por_nome_no_documento(doc)

    carregadas = []
    ja_existentes = []
    erros = []
    familias_por_nome = {}
    para_renomear = []  # [(Family, nome_de_exibicao)]

    with Transaction(doc, u"FireUtils - Carregar Familias") as t:
        t.Start()
        try:
            for entrada in entradas:
                familia_existente = existentes_por_nome.get(entrada.nome_revit) or existentes_por_nome.get(entrada.name)
                if familia_existente is not None:
                    ja_existentes.append(entrada.name)
                    familias_por_nome[entrada.name] = familia_existente
                    continue
                if not os.path.exists(entrada.path):
                    erros.append((entrada.name, u"Arquivo não encontrado em disco."))
                    continue
                try:
                    ref_familia = clr.Reference[Family]()
                    if doc.LoadFamily(entrada.path, ref_familia):
                        familia_carregada = ref_familia.Value
                        carregadas.append(entrada.name)
                        familias_por_nome[entrada.name] = familia_carregada
                        if familia_carregada.Name != entrada.name:
                            para_renomear.append((familia_carregada, entrada.name))
                    else:
                        erros.append((entrada.name, u"LoadFamily retornou False."))
                except Exception as e:
                    erros.append((entrada.name, texto_erro(e)))
            t.Commit()
        except Exception as e:
            t.RollBack()
            erros.append((u"(transação)", texto_erro(e)))

    if para_renomear:
        _tentar_renomear_para_exibicao(doc, para_renomear)

    return carregadas, ja_existentes, erros, familias_por_nome


def _tentar_renomear_para_exibicao(doc, pares):
    """
    Troca Family.Name pro nome de exibição de verdade do catálogo (pode
    ter acento), numa transação separada, DEPOIS que o carregamento
    principal já commitou com sucesso. Só cosmético — a família já está
    carregada e funcional mesmo se isso falhar ou nem rodar — por isso
    fica isolado aqui, com uma rede de segurança em volta da transação
    inteira: se travar (a mesma classe de erro de codificação pode
    aparecer aqui, dependendo da máquina), fica só sem o nome bonito,
    sem afetar o resultado que o usuário já viu.
    """
    try:
        with Transaction(doc, u"FireUtils - Renomear Familias") as t:
            t.Start()
            for familia, nome_exibicao in pares:
                try:
                    familia.Name = nome_exibicao
                except Exception:
                    pass
            t.Commit()
    except Exception:
        pass
