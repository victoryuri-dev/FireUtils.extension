# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Lógica de "Inserir linha com limite": usa a ferramenta nativa de linha
do Revit (com preview em tempo real acompanhando o mouse), mas monitora
o comprimento total dos segmentos criados. Se ultrapassar o limite máximo
informado, deleta os segmentos extras e mantém apenas até o limite,
encurtando o último segmento se necessário.
"""

from Autodesk.Revit.DB import (
    Line, DetailCurve, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType, ElementId
)
from Autodesk.Revit.UI import PostableCommand
from pyrevit import revit, forms

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


def _aplicar_estilo_linhas(doc, view, ids_linhas, graphics_style):
    """Aplica o estilo de linha a uma lista de DetailCurves."""
    if not ids_linhas:
        return
    try:
        with Transaction(doc, u"Aplicar Estilo de Linha") as t:
            t.Start()
            for linha_id in ids_linhas:
                try:
                    elem = doc.GetElement(linha_id)
                    if isinstance(elem, DetailCurve):
                        elem.LineStyle = graphics_style
                except:
                    pass
            t.Commit()
    except:
        pass


def _obter_linhas_da_view(doc, view):
    """Retorna dict {ElementId: comprimento_interno} de todas as DetailLines na view."""
    linhas = {}
    try:
        for elem in view.GetAllElementsInView():
            if isinstance(elem, DetailCurve):
                geom = elem.GeometryCurve
                if geom is not None:
                    try:
                        comprimento = geom.Length
                        linhas[elem.Id] = comprimento
                    except:
                        pass
    except:
        pass
    return linhas


def _validar_e_ajustar_linhas(doc, view, linhas_antes, graphics_style, limite_interno, comprimento_max_m):
    """
    Valida as linhas criadas após ferramenta nativa.
    Se exceder limite, deleta segmentos extras e encurta o último.
    Retorna True se atingiu limite, False caso contrário.
    """
    linhas_depois = _obter_linhas_da_view(doc, view)

    # Identifica linhas novas (criadas durante a ferramenta)
    ids_novas = [lid for lid in linhas_depois.keys() if lid not in linhas_antes]

    if not ids_novas:
        return False

    # Ordena por criação (última criada é a mais recente)
    ids_novas_sorted = sorted(ids_novas, key=lambda x: x.IntegerValue)

    total_interno = 0.0
    parou_no_limite = False
    ids_para_deletar = []

    for idx, linha_id in enumerate(ids_novas_sorted):
        elem = doc.GetElement(linha_id)
        if not isinstance(elem, DetailCurve):
            continue

        comprimento_segmento = linhas_depois[linha_id]
        total_interno += comprimento_segmento

        if total_interno > limite_interno:
            # Excedeu o limite
            parou_no_limite = True

            # Calcula quanto falta do segmento atual
            excesso = total_interno - limite_interno
            comprimento_ajustado = comprimento_segmento - excesso

            if comprimento_ajustado > 1e-9:
                # Encurta o segmento atual
                try:
                    geom = elem.GeometryCurve
                    if isinstance(geom, Line):
                        ponto_inicio = geom.GetEndPoint(0)
                        ponto_fim_original = geom.GetEndPoint(1)
                        vetor = ponto_fim_original - ponto_inicio
                        direcao = vetor.Normalize()
                        ponto_fim_ajustado = ponto_inicio + direcao.Multiply(comprimento_ajustado)

                        with Transaction(doc, u"Ajustar Linha ao Limite") as t:
                            t.Start()
                            doc.Delete(linha_id)
                            nova_linha = Line.CreateBound(ponto_inicio, ponto_fim_ajustado)
                            elem_novo = doc.Create.NewDetailCurve(view, nova_linha)
                            try:
                                elem_novo.LineStyle = graphics_style
                            except:
                                pass
                            t.Commit()
                except:
                    ids_para_deletar.append(linha_id)
            else:
                ids_para_deletar.append(linha_id)

            # Marca segmentos posteriores para deletar
            for idx_post in range(idx + 1, len(ids_novas_sorted)):
                ids_para_deletar.append(ids_novas_sorted[idx_post])

            break

    # Deleta segmentos extras
    if ids_para_deletar:
        try:
            with Transaction(doc, u"Deletar Linhas Extras") as t:
                t.Start()
                for linha_id in ids_para_deletar:
                    try:
                        doc.Delete(linha_id)
                    except:
                        pass
                t.Commit()
        except:
            pass

    return parou_no_limite, total_interno


def inserir_linha_com_limite(doc, uidoc, view, graphics_style, comprimento_max_m):
    """
    Usa a ferramenta nativa de linha do Revit (com preview acompanhando mouse),
    mas monitora o comprimento total dos segmentos criados.

    Ao atingir o limite máximo informado:
    - O último segmento é encurtado para fechar no limite exato
    - Segmentos posteriores (se houver) são deletados
    - Mostra mensagem informando o comprimento total atingido
    """
    limite_interno = _metros_para_interno(comprimento_max_m)

    # Guarda linhas existentes antes da ferramenta nativa
    linhas_antes = _obter_linhas_da_view(doc, view)

    # Invoca a ferramenta nativa de desenho de linhas detalhadas
    try:
        uidoc.PostCommand(PostableCommand.DetailLineSegment)
    except Exception as e:
        forms.alert(u"Erro ao invocar ferramenta de linha nativa:\n{}".format(str(e)), exitscript=True)
        return

    # Valida e ajusta linhas criadas
    try:
        parou_no_limite, total_interno = _validar_e_ajustar_linhas(
            doc, view, linhas_antes, graphics_style, limite_interno, comprimento_max_m
        )

        if parou_no_limite:
            total_m = _interno_para_metros(total_interno)
            forms.alert(
                u"Limite de {:.2f} m atingido.\nComprimento total inserido: {:.2f} m".format(
                    comprimento_max_m, total_m
                ),
                title=u"Inserir Linha com Limite",
            )
    except Exception as e:
        forms.alert(u"Erro ao validar linhas:\n{}".format(str(e)))
