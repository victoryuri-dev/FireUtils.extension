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
clr.AddReference("System.Drawing")
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector
from System.Drawing import Size
from System.Drawing.Imaging import ImageFormat

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
FAMILY_LIBRARY_DIR = os.path.join(_LIB_DIR, u"family_library")

# Cache de previews (miniaturas .png) — espelha a estrutura de pastas da
# biblioteca, trocando .rfa por .png (ex.: family_library/Hidrantes/X.rfa ->
# family_library/.previews/Hidrantes/X.png). Gerado sob demanda pelo botão
# "Gerar previews" do painel (abre cada .rfa como documento de família
# temporário, extrai o preview nativo do Revit e fecha sem salvar) — nunca
# automaticamente, pra manter a abertura do painel sempre instantânea.
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


def gerar_preview(app, entrada, tamanho_pixels=160):
    """
    Gera (ou regenera) o .png de preview de uma família a partir do .rfa,
    sem tocar no projeto ativo: abre o arquivo como um documento de família
    temporário (Application.OpenDocumentFile), extrai o preview nativo do
    Revit (Family.GetPreviewImage — o mesmo que a caixa "Carregar Família"
    do Revit mostra) e fecha o documento temporário sem salvar.

    Precisa rodar num contexto de API válido (ex.: dentro da fila de
    ExternalEvent do painel) — abrir/fechar documento é operação da API do
    Revit, não pode ser chamada direto de um clique da UI modeless.

    Retorna True se o .png foi gerado/atualizado com sucesso.
    """
    if not os.path.exists(entrada.path):
        return False

    caminho_png = caminho_preview(entrada)
    pasta_destino = os.path.dirname(caminho_png)
    if not os.path.isdir(pasta_destino):
        try:
            os.makedirs(pasta_destino)
        except OSError:
            pass

    familia_doc = None
    try:
        familia_doc = app.OpenDocumentFile(entrada.path)
        if familia_doc is None or not familia_doc.IsFamilyDocument:
            return False

        familia = familia_doc.OwnerFamily
        if familia is None:
            return False

        bitmap_nativo = familia.GetPreviewImage(Size(tamanho_pixels, tamanho_pixels))
        if bitmap_nativo is None:
            return False

        try:
            bitmap_nativo.Save(caminho_png, ImageFormat.Png)
        finally:
            bitmap_nativo.Dispose()

        return True
    except Exception as ex:
        print(u"[AVISO] Falha ao gerar preview de '{}': {}".format(entrada.name, ex))
        return False
    finally:
        if familia_doc is not None:
            try:
                familia_doc.Close(False)
            except Exception:
                pass


def gerar_previews_pendentes(app, entradas, tamanho_pixels=160, callback_progresso=None):
    """
    Gera o preview de todas as entradas que ainda não têm cache válido.
    callback_progresso(indice, total, entrada), se informado, é chamado
    antes de processar cada família (indice começa em 1) — usado pra
    alimentar uma pyrevit.forms.ProgressBar.

    Retorna (gerados, ja_em_cache, erros) — erros é uma lista de nomes.
    """
    pendentes = [e for e in entradas if preview_valido(e) is None]

    gerados = 0
    erros = []
    total = len(pendentes)
    for indice, entrada in enumerate(pendentes, start=1):
        if callback_progresso is not None:
            callback_progresso(indice, total, entrada)
        if gerar_preview(app, entrada, tamanho_pixels=tamanho_pixels):
            gerados += 1
        else:
            erros.append(entrada.name)

    ja_em_cache = len(entradas) - total
    return gerados, ja_em_cache, erros


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
