# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Lógica de "Inserir linha com limite": desenha uma sequência de Detail
Lines interativamente, com preview em tempo real conforme move o mouse
(como a ferramenta nativa do Revit), até um comprimento máximo informado.
Ao ultrapassar o limite, o segmento final é ENCURTADO para fechar
exatamente no valor máximo, em vez de descartado.

Detail Line (não Model Line) de propósito: funciona direto na vista ativa.
"""

from Autodesk.Revit.DB import Line, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType
from Autodesk.Revit.UI.Selection import DynamicUpdateDelegate
from pyrevit import forms
import threading
import time

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
        pass
    return detail_curve


class PreviewUpdater(DynamicUpdateDelegate):
    """Delegate que atualiza preview enquanto picking acontece."""
    def __init__(self, state, ponto_inicio, view, doc, graphics_style):
        self.state = state
        self.ponto_inicio = ponto_inicio
        self.view = view
        self.doc = doc
        self.graphics_style = graphics_style
        self.preview_id = None

    def Update(self, elem_id):
        """Chamado pelo Revit conforme picking progride."""
        try:
            ponto_fim = self.state.get('cursor_point')
            if ponto_fim is None or ponto_fim == self.ponto_inicio:
                return True

            if self.preview_id is not None:
                try:
                    self.doc.Delete(self.preview_id)
                except:
                    pass
                self.preview_id = None

            distancia = self.ponto_inicio.DistanceTo(ponto_fim)
            if distancia < 1e-9:
                return True

            limite_restante = self.state.get('limite_restante', float('inf'))
            if distancia > limite_restante:
                vetor = ponto_fim - self.ponto_inicio
                direcao = vetor.Normalize()
                ponto_ajustado = self.ponto_inicio + direcao.Multiply(limite_restante)
            else:
                ponto_ajustado = ponto_fim

            linha = Line.CreateBound(self.ponto_inicio, ponto_ajustado)
            with Transaction(self.doc, u"Preview Linha com Limite") as t:
                t.Start()
                preview_curve = self.doc.Create.NewDetailCurve(self.view, linha)
                try:
                    preview_curve.LineStyle = self.graphics_style
                except:
                    pass
                self.preview_id = preview_curve.Id
                t.Commit()
        except:
            pass

        return True


def inserir_linha_com_limite(doc, uidoc, view, graphics_style, comprimento_max_m):
    """
    Desenha linhas interativamente com preview em tempo real:
    1. Clica no ponto inicial
    2. Uma linha acompanha o mouse (como ferramenta nativa do Revit)
    3. Clica para confirmar o ponto final
    4. O segmento é criado, inicia novo preview a partir desse ponto
    5. Repete até ESC ou atingir o limite de comprimento

    Ao atingir o limite, o último segmento é encurtado automaticamente
    para fechar no valor máximo informado.
    """
    limite_interno = _metros_para_interno(comprimento_max_m)

    try:
        ponto_atual = uidoc.Selection.PickPoint(u"Clique o ponto inicial")
    except Exception:
        return

    total_interno = 0.0
    parou_no_limite = False
    picking_active = False
    abort_flag = threading.Event()

    def monitor_mouse():
        """Thread que monitora posição do mouse durante picking."""
        state = {'cursor_point': None}
        while not abort_flag.is_set():
            try:
                restante_m = _interno_para_metros(limite_interno - total_interno)
                msg = u"Mova para preview — faltam {:.2f} m (ESC para terminar)".format(restante_m)

                updater = PreviewUpdater(state, ponto_atual, view, doc, graphics_style)

                try:
                    proximo = uidoc.Selection.PickPoint(updater, msg)
                    if updater.preview_id is not None:
                        try:
                            doc.Delete(updater.preview_id)
                        except:
                            pass
                    state['cursor_point'] = proximo
                    return proximo, state
                except Exception:
                    if updater.preview_id is not None:
                        try:
                            doc.Delete(updater.preview_id)
                        except:
                            pass
                    return None, state
            except:
                time.sleep(0.05)
        return None, state

    while True:
        restante_m = _interno_para_metros(limite_interno - total_interno)
        abort_flag.clear()

        state = {
            'cursor_point': None,
            'limite_restante': limite_interno - total_interno,
        }

        updater = PreviewUpdater(state, ponto_atual, view, doc, graphics_style)

        try:
            proximo_ponto = uidoc.Selection.PickPoint(
                updater,
                u"Mova para preview — faltam {:.2f} m (ESC para terminar)".format(restante_m)
            )
        except Exception:
            if updater.preview_id is not None:
                try:
                    doc.Delete(updater.preview_id)
                except:
                    pass
            break

        if updater.preview_id is not None:
            try:
                doc.Delete(updater.preview_id)
            except:
                pass

        if proximo_ponto is None:
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
        forms.alert(
            u"Limite de {:.2f} m atingido.\nComprimento total inserido: {:.2f} m".format(
                comprimento_max_m, total_m
            ),
            title=u"Inserir Linha com Limite",
        )
