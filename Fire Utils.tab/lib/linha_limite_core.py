# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Lógica de "Inserir linha com limite": desenha uma sequência de Detail
Lines (clique a clique, como uma polilinha) no estilo de linha escolhido
pelo usuário, até um comprimento total máximo — ao ultrapassar o limite
num segmento, esse segmento é ENCURTADO (não descartado) pra fechar
exatamente no valor máximo, em vez de simplesmente recusar o clique.

Detail Line (não Model Line) de propósito: não depende de SketchPlane,
funciona direto na vista ativa — mesmo tipo de elemento associado a um
"estilo de linha" na interface nativa do Revit.
"""

from Autodesk.Revit.DB import Line, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType
from pyrevit import forms

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
    """{nome: GraphicsStyle} de cada Estilo de Linha do projeto — a mesma
    lista que aparece no seletor de estilo de linha nativo do Revit
    (categoria "Linhas" > subcategorias)."""
    categoria_linhas = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    estilos = {}
    for subcategoria in categoria_linhas.SubCategories:
        estilo = subcategoria.GetGraphicsStyle(GraphicsStyleType.Projection)
        if estilo is not None:
            estilos[subcategoria.Name] = estilo
    return estilos


def _criar_detail_line(doc, view, linha, graphics_style):
    detail_curve = doc.Create.NewDetailCurve(view, linha)
    try:
        detail_curve.LineStyle = graphics_style
    except Exception:
        pass  # estilo não aplicável a essa curva — segue só sem o estilo
    return detail_curve


def inserir_linha_com_limite(doc, uidoc, view, graphics_style, comprimento_max_m):
    """
    Loop de picking: cada clique fecha um segmento (Detail Line) a partir
    do ponto anterior, no estilo escolhido. ESC a qualquer momento termina
    o desenho normalmente (como qualquer ferramenta de linha do Revit).

    Ao ultrapassar `comprimento_max_m` na soma dos segmentos, o segmento
    ATUAL é encurtado (endpoint recalculado na mesma direção, à distância
    restante) pra fechar exatamente no limite, e o desenho para sozinho —
    mostra uma mensagem com o comprimento total inserido.

    Cada segmento é criado numa transação PRÓPRIA (Start+Commit logo após
    o clique que o fecha) — não uma transação só pro desenho inteiro. Sem
    isso, nenhum segmento aparecia na tela até o commit final (só depois
    de ESC ou do limite ser atingido): o Revit só redesenha uma vista com
    o que já foi de fato commitado, então uma transação única deixava o
    usuário "cego" durante todo o desenho.
    """
    limite_interno = _metros_para_interno(comprimento_max_m)

    try:
        ponto_atual = uidoc.Selection.PickPoint(u"Clique o ponto inicial da linha (ESC para cancelar)")
    except Exception:
        return  # cancelado antes de desenhar qualquer coisa — nada a fazer

    total_interno = 0.0
    parou_no_limite = False

    while True:
        restante_m = _interno_para_metros(limite_interno - total_interno)
        try:
            proximo_ponto = uidoc.Selection.PickPoint(
                u"Clique o próximo ponto (ESC para terminar) — faltam {:.2f} m".format(restante_m)
            )
        except Exception:
            break  # ESC — usuário decidiu terminar antes do limite

        vetor = proximo_ponto - ponto_atual
        comprimento_segmento = vetor.GetLength()
        if comprimento_segmento < 1e-9:
            continue  # clique em cima do ponto anterior — ignora, sem travar o loop

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
        forms.alert(
            u"Limite de {:.2f} m atingido.\nComprimento total inserido: {:.2f} m".format(
                comprimento_max_m, total_m
            ),
            title=u"Inserir Linha com Limite",
        )
