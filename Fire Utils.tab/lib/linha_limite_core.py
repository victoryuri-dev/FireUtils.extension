# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Inserir linha com limite: desenha sequência de linhas com preview
em tempo real acompanhando o mouse (via threading).
Valida comprimento máximo conforme os segmentos são criados.
Último segmento é encurtado ao atingir limite.
"""

from Autodesk.Revit.DB import (
    Line, DetailCurve, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType, XYZ
)
from pyrevit import forms
from System.Windows.Forms import Cursor
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
    """{nome: GraphicsStyle} de cada Estilo de Linha do projeto."""
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


def inserir_linha_com_limite(doc, uidoc, view, graphics_style, comprimento_max_m):
    """
    Desenha linhas com preview em tempo real conforme mouse se move:
    - Clica ponto inicial
    - Linha acompanha mouse (preview via threading)
    - Clica para confirmar ponto final
    - Segmento criado, próximo preview começa
    - Repete até ESC ou atingir limite máximo

    Ao atingir limite, último segmento é encurtado automaticamente.
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
        preview_id = [None]  # usamos lista para poder modificar em thread
        cursor_state = {'stop': False}
        thread_obj = [None]

        def monitor_preview():
            """Thread que monitora mouse e desenha preview."""
            try:
                last_cursor_pos = None
                cursor_pos_original = None

                while not cursor_state['stop']:
                    try:
                        cursor_pos = Cursor.Position

                        if cursor_pos_original is None:
                            cursor_pos_original = cursor_pos

                        if cursor_pos != last_cursor_pos:
                            last_cursor_pos = cursor_pos

                            # Estima ponto 3D baseado em movimento do mouse
                            # Calibração: 100 pixels = 1 metro aproximadamente
                            px_per_meter = 100.0

                            delta_x = (cursor_pos.X - cursor_pos_original.X) / px_per_meter
                            delta_y = (cursor_pos.Y - cursor_pos_original.Y) / px_per_meter

                            ponto_fim_aprox = XYZ(
                                ponto_atual.X + delta_x,
                                ponto_atual.Y - delta_y,
                                ponto_atual.Z
                            )

                            distancia = ponto_atual.DistanceTo(ponto_fim_aprox)

                            if distancia > 1e-9:
                                try:
                                    if preview_id[0] is not None:
                                        try:
                                            doc.Delete(preview_id[0])
                                        except:
                                            pass
                                        preview_id[0] = None

                                    restante_interno = limite_interno - total_interno

                                    if distancia > restante_interno:
                                        vetor = ponto_fim_aprox - ponto_atual
                                        direcao = vetor.Normalize()
                                        ponto_fim = ponto_atual + direcao.Multiply(restante_interno)
                                    else:
                                        ponto_fim = ponto_fim_aprox

                                    linha = Line.CreateBound(ponto_atual, ponto_fim)
                                    with Transaction(doc, u"Preview") as t:
                                        t.Start()
                                        preview_curve = doc.Create.NewDetailCurve(view, linha)
                                        try:
                                            preview_curve.LineStyle = graphics_style
                                        except:
                                            pass
                                        preview_id[0] = preview_curve.Id
                                        t.Commit()
                                except:
                                    pass

                        time.sleep(0.05)
                    except:
                        time.sleep(0.05)
            except:
                pass

        try:
            msg = u"Mova o mouse para ver preview — {:.2f}m restantes (ESC para terminar)".format(restante_m)

            # Inicia thread de monitoramento
            thread_obj[0] = threading.Thread(target=monitor_preview)
            thread_obj[0].daemon = True
            thread_obj[0].start()

            # Faz picking (bloqueante)
            proximo_ponto = uidoc.Selection.PickPoint(msg)

            # Para thread
            cursor_state['stop'] = True
            thread_obj[0].join(timeout=0.5)

        except Exception:
            cursor_state['stop'] = True
            if thread_obj[0] is not None:
                thread_obj[0].join(timeout=0.5)
            if preview_id[0] is not None:
                try:
                    doc.Delete(preview_id[0])
                except:
                    pass
            break

        # Remove preview
        if preview_id[0] is not None:
            try:
                doc.Delete(preview_id[0])
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
