# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Lógica de "Inserir linha com limite": desenha uma sequência de Detail
Lines (clique a clique) no estilo de linha escolhido pelo usuário,
até um comprimento total máximo — ao ultrapassar o limite num segmento,
esse segmento é ENCURTADO (não descartado) pra fechar exatamente no
valor máximo, em vez de simplesmente recusar o clique.

Detail Line (não Model Line): não depende de SketchPlane,
funciona direto na vista ativa.

Ao atingir o limite, um painel (linha_limite_atingido.xaml) oferece
"Fechar" ou "Inserir Comprimento" — essa última insere um TextNote (mesmo
formato/prefixo configurável de "Medir e Inserir Texto", ver
comprimento_linha_config.py) 0,25 m ACIMA, na tela, do ponto onde a linha
parou (sempre vista de planta — é o único jeito de desenhar essas linhas
— ver _direcao_acima_na_view). Tudo roda dentro do mesmo script.py
síncrono (loop de PickPoint), nunca modeless, então o painel pode ser um
ShowDialog() comum — sem precisar de ExternalEvent pra tocar o documento
depois.
"""

import os

from Autodesk.Revit.DB import (
    Line, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType,
    FilteredElementCollector, TextNoteType, TextNote, TextNoteOptions,
    HorizontalTextAlignment,
)
from pyrevit import forms

_XAML_LIMITE_ATINGIDO = os.path.join(os.path.dirname(__file__), u"linha_limite_atingido.xaml")

try:
    from Autodesk.Revit.DB import UnitTypeId

    def _metros_para_interno(valor):
        return UnitUtils.ConvertToInternalUnits(valor, UnitTypeId.Meters)

    def _interno_para_metros(valor):
        return UnitUtils.ConvertFromInternalUnits(valor, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType

    def _metros_para_interno(valor):
        return UnitUtils.ConvertToInternalUnits(valor, DisplayUnitType.DUT_METERS)

    def _interno_para_metros(valor):
        return UnitUtils.ConvertFromInternalUnits(valor, DisplayUnitType.DUT_METERS)


def listar_estilos_de_linha(doc):
    """{nome: GraphicsStyle} de cada Estilo de Linha do projeto."""
    categoria_linhas = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    estilos = {}
    for subcategoria in categoria_linhas.SubCategories:
        estilo = subcategoria.GetGraphicsStyle(GraphicsStyleType.Projection)
        if estilo is not None:
            estilos[subcategoria.Name] = estilo
    return estilos


class _JanelaLimiteAtingido(forms.WPFWindow):

    def __init__(self, mensagem):
        forms.WPFWindow.__init__(self, _XAML_LIMITE_ATINGIDO)
        self.TxtMensagem.Text = mensagem
        self.inserir_comprimento = False

    def on_fechar(self, sender, args):
        self.Close()

    def on_inserir_comprimento(self, sender, args):
        self.inserir_comprimento = True
        self.Close()


def _mostrar_painel_limite_atingido(comprimento_max_m, total_m):
    mensagem = u"Limite de {:.2f} m atingido.\nComprimento total inserido: {:.2f} m".format(
        comprimento_max_m, total_m)
    janela = _JanelaLimiteAtingido(mensagem)
    janela.ShowDialog()
    return janela.inserir_comprimento


def _direcao_acima_na_view(view):
    """"Pra cima" na tela (não o eixo Z do mundo — em planta, Z aponta pra
    fora da tela, não pra cima nela). view.UpDirection não se mostrou
    confiável em planta (testado: deslocamento saiu pra DIREITA, não pra
    cima) — em vez disso, calcula a partir da base da própria view
    (RightDirection × ViewDirection), que dá "pra cima na tela" mesmo com
    a planta rotacionada (norte do projeto x norte verdadeiro)."""
    return view.RightDirection.CrossProduct(view.ViewDirection)


def _inserir_texto_comprimento(doc, view, ponto_final, comprimento_m):
    """TextNote com o mesmo prefixo configurável de "Medir e Inserir
    Texto" (comprimento_linha_config.py), 0,25 m ACIMA de ponto_final —
    sempre vista de planta aqui (único jeito de desenhar as linhas), ver
    _direcao_acima_na_view."""
    tipos = list(FilteredElementCollector(doc).OfClass(TextNoteType))
    if not tipos:
        forms.alert(u"Nenhum tipo de TextNote encontrado.",
                    title=u"Inserir Linha com Limite", warn_icon=True)
        return

    from comprimento_linha_config import carregar as carregar_config
    _, prefixo = carregar_config(doc)
    texto = u"{}{:.2f} m".format(prefixo, comprimento_m)

    deslocamento = _direcao_acima_na_view(view).Multiply(_metros_para_interno(0.25))
    ponto_texto = ponto_final + deslocamento

    with Transaction(doc, u"Inserir Comprimento de Linha") as t:
        t.Start()
        opcoes = TextNoteOptions(tipos[0].Id)
        opcoes.HorizontalAlignment = HorizontalTextAlignment.Left
        TextNote.Create(doc, view.Id, ponto_texto, texto, opcoes)
        t.Commit()


def _criar_detail_line(doc, view, linha, graphics_style):
    detail_curve = doc.Create.NewDetailCurve(view, linha)
    try:
        detail_curve.LineStyle = graphics_style
    except Exception:
        pass
    return detail_curve


def inserir_linha_com_limite(doc, uidoc, view, graphics_style, comprimento_max_m):
    """
    Loop de picking: cada clique fecha um segmento (Detail Line) a partir
    do ponto anterior, no estilo escolhido. ESC a qualquer momento termina.

    Ao ultrapassar comprimento_max_m, o segmento ATUAL é encurtado
    (endpoint recalculado na mesma direção, à distância restante)
    pra fechar exatamente no limite, e o desenho para sozinho.

    Cada segmento é criado em transação PRÓPRIA para visibilidade imediata.
    """
    limite_interno = _metros_para_interno(comprimento_max_m)

    try:
        ponto_atual = uidoc.Selection.PickPoint(u"Clique o ponto inicial")
    except Exception:
        return

    total_interno = 0.0
    parou_no_limite = False

    while True:
        restante_m = _interno_para_metros(limite_interno - total_interno)

        try:
            proximo_ponto = uidoc.Selection.PickPoint(
                u"Próximo ponto — faltam {:.2f} m (ESC para terminar)".format(restante_m)
            )
        except Exception:
            break

        vetor = proximo_ponto - ponto_atual
        comprimento_segmento = vetor.GetLength()
        if comprimento_segmento < 1e-9:
            continue

        restante_interno = limite_interno - total_interno
        excedeu = comprimento_segmento >= restante_interno
        if excedeu:
            direcao = vetor.Normalize()
            ponto_final = ponto_atual + direcao.Multiply(restante_interno)
        else:
            ponto_final = proximo_ponto

        linha = Line.CreateBound(ponto_atual, ponto_final)
        with Transaction(doc, u"Inserir Linha com Limite") as t:
            t.Start()
            _criar_detail_line(doc, view, linha, graphics_style)
            t.Commit()

        if excedeu:
            total_interno = limite_interno
            parou_no_limite = True
            break

        total_interno += comprimento_segmento
        ponto_atual = proximo_ponto

    if parou_no_limite:
        total_m = _interno_para_metros(total_interno)
        if _mostrar_painel_limite_atingido(comprimento_max_m, total_m):
            _inserir_texto_comprimento(doc, view, ponto_final, total_m)
