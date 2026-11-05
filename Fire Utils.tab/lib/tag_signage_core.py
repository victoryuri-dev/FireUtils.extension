# -*- coding: utf-8 -*-
"""
tag_signage_core.py — Fire Utils · lib/
Lógica do botão "Identificar Sinalizações": equivalente ao "Identificar
todos" nativo do Revit, mas com a chamada de detalhe (leader) saindo na
direção da face do elemento — em SENTIDO OPOSTO a FacingOrientation —
em vez de sempre pra cima.

Fluxo: janela (tag_signage_opcoes.xaml) com as categorias que têm
identificador carregado no projeto (e a família do identificador de cada
uma), a distância da chamada de detalhe (mm no papel, multiplicada pela
escala da vista, como o nativo) e o escopo (vista ativa ou todas as
plantas). Elementos que já têm identificador na vista são pulados.

Função pública
--------------
identificar_sinalizacoes(doc, uidoc, output)
"""

import os
import math

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")

import System
from System.Windows import Thickness
from System.Windows.Controls import CheckBox, ComboBox, Grid, ColumnDefinition
from System.Windows import GridLength, GridUnitType

from Autodesk.Revit.DB import (
    Transaction, XYZ, BuiltInCategory, BuiltInParameter, FamilySymbol,
    FilteredElementCollector, IndependentTag, ViewPlan, ViewType,
    Reference, TagMode, TagOrientation,
)
from pyrevit import forms

from family_error_utils import texto_erro

# Sentido da chamada de detalhe em relação a FacingOrientation do elemento.
# True = oposto à face (comportamento pedido). Mude pra False pra ir no
# mesmo sentido da face.
SENTIDO_OPOSTO = True

DISTANCIA_PADRAO_MM = 15.0
_MM_POR_FT = 304.8

_XAML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"tag_signage_opcoes.xaml")


# ===========================================================================
# HELPERS — categorias e tipos de identificador
# ===========================================================================

def _id_value(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _nome_simbolo(sym):
    """'Família : Tipo', lendo o nome do tipo pelo parâmetro (evita .Name,
    que falha em alguns tipos no IronPython)."""
    try:
        tipo = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    except Exception:
        tipo = u""
    try:
        fam = sym.FamilyName
    except Exception:
        fam = u""
    return u"{} : {}".format(fam, tipo)


def _bic_de_categoria(cat):
    try:
        return System.Enum.ToObject(BuiltInCategory, _id_value(cat.Id))
    except Exception:
        return None


def _categoria_modelo_do_identificador(doc, cat_tag):
    """Dado a categoria de identificador (ex.: OST_FireAlarmDeviceTags),
    devolve a categoria de modelo correspondente (OST_FireAlarmDevices)
    pelo nome do BuiltInCategory — o Revit não expõe esse vínculo direto.
    None se não houver correspondência (ex.: identificador multicategoria)."""
    bic = _bic_de_categoria(cat_tag)
    if bic is None:
        return None
    nome = System.Enum.GetName(BuiltInCategory, bic)
    if not nome or not nome.endswith(u"Tags") or nome == u"OST_MultiCategoryTags":
        return None
    base = nome[:-4]
    candidatos = [base + u"s", base, base + u"es"]
    if base.endswith(u"y"):
        candidatos.insert(0, base[:-1] + u"ies")
    for c in candidatos:
        try:
            bic_modelo = System.Enum.Parse(BuiltInCategory, c)
            cat = doc.Settings.Categories.get_Item(bic_modelo)
            if cat is not None:
                return cat
        except Exception:
            continue
    return None


def _catalogo_identificadores(doc):
    """[(categoria_modelo, [(rotulo, FamilySymbol), ...]), ...] ordenado
    por nome, só com categorias que têm identificador carregado."""
    por_cat = {}
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements():
        cat_tag = sym.Category
        if cat_tag is None:
            continue
        cat_modelo = _categoria_modelo_do_identificador(doc, cat_tag)
        if cat_modelo is None:
            continue
        chave = _id_value(cat_modelo.Id)
        entrada = por_cat.setdefault(chave, (cat_modelo, []))
        entrada[1].append((_nome_simbolo(sym), sym))
    resultado = []
    for cat_modelo, simbolos in por_cat.values():
        simbolos.sort(key=lambda x: x[0].lower())
        resultado.append((cat_modelo, simbolos))
    resultado.sort(key=lambda x: x[0].Name.lower())
    return resultado


# ===========================================================================
# FORM
# ===========================================================================

class _Janela(forms.WPFWindow):
    def __init__(self, catalogo):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.confirmado = False
        self.distancia_mm = DISTANCIA_PADRAO_MM
        self._linhas = []   # (CheckBox, ComboBox, cat_modelo, simbolos)

        for cat_modelo, simbolos in catalogo:
            grade = Grid()
            grade.Margin = Thickness(0, 0, 0, 6)
            c1 = ColumnDefinition(); c1.Width = GridLength(200)
            c2 = ColumnDefinition(); c2.Width = GridLength(1, GridUnitType.Star)
            grade.ColumnDefinitions.Add(c1)
            grade.ColumnDefinitions.Add(c2)

            chk = CheckBox()
            chk.Content = cat_modelo.Name
            chk.FontSize = 12
            chk.VerticalAlignment = System.Windows.VerticalAlignment.Center
            Grid.SetColumn(chk, 0)

            cmb = ComboBox()
            cmb.FontSize = 12
            cmb.Height = 26
            for rotulo, _ in simbolos:
                cmb.Items.Add(rotulo)
            cmb.SelectedIndex = 0
            Grid.SetColumn(cmb, 1)

            grade.Children.Add(chk)
            grade.Children.Add(cmb)
            self.PnlCategorias.Children.Add(grade)
            self._linhas.append((chk, cmb, cat_modelo, simbolos))

        if not catalogo:
            self.TxtStatus.Text = (
                u"Nenhuma família de identificador carregada no projeto.")

    def selecao(self):
        """[(categoria_modelo, FamilySymbol do identificador), ...]"""
        saida = []
        for chk, cmb, cat_modelo, simbolos in self._linhas:
            if chk.IsChecked and cmb.SelectedIndex >= 0:
                saida.append((cat_modelo, simbolos[cmb.SelectedIndex][1]))
        return saida

    def todo_projeto(self):
        return bool(self.RdoProjeto.IsChecked)

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self.selecao():
            self.TxtStatus.Text = u"Selecione ao menos uma categoria."
            return
        try:
            d = float(self.TxtDistancia.Text.strip().replace(u",", u"."))
            if d <= 0:
                raise ValueError()
        except Exception:
            self.TxtStatus.Text = u"Informe uma distância válida (maior que zero)."
            return
        self.distancia_mm = d
        self.confirmado = True
        self.Close()


# ===========================================================================
# CRIAÇÃO DOS IDENTIFICADORES
# ===========================================================================

def _ids_ja_identificados(doc, view):
    ids = set()
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag).ToElements():
        try:
            for eid in tag.GetTaggedLocalElementIds():      # Revit 2022+
                ids.add(_id_value(eid))
        except AttributeError:
            try:
                ids.add(_id_value(tag.TaggedLocalElementId))  # Revit <= 2021
            except Exception:
                pass
        except Exception:
            pass
    return ids


def _centro_xy(elem):
    try:
        bb = elem.get_BoundingBox(None)
        if bb is not None:
            return XYZ((bb.Min.X + bb.Max.X) / 2.0,
                       (bb.Min.Y + bb.Max.Y) / 2.0,
                       (bb.Min.Z + bb.Max.Z) / 2.0)
    except Exception:
        pass
    return elem.Location.Point


def _direcao_chamada(elem):
    """Vetor unitário (XY) pra onde a chamada de detalhe aponta:
    FacingOrientation do elemento, invertido se SENTIDO_OPOSTO. None se o
    elemento não tem orientação."""
    try:
        f = elem.FacingOrientation
    except Exception:
        return None
    n = math.sqrt(f.X * f.X + f.Y * f.Y)
    if n < 1e-9:
        return None
    sinal = -1.0 if SENTIDO_OPOSTO else 1.0
    return XYZ(sinal * f.X / n, sinal * f.Y / n, 0.0)


def _criar_tag(doc, view, elem, simbolo, ponto_cabeca):
    ref = Reference(elem)
    try:   # Revit 2023+
        tag = IndependentTag.Create(
            doc, simbolo.Id, view.Id, ref, True,
            TagOrientation.Horizontal, ponto_cabeca)
    except Exception:
        tag = IndependentTag.Create(
            doc, view.Id, ref, True, TagMode.TM_ADDBY_CATEGORY,
            TagOrientation.Horizontal, ponto_cabeca)
        if tag.GetTypeId() != simbolo.Id:
            tag.ChangeTypeId(simbolo.Id)
    tag.TagHeadPosition = ponto_cabeca
    return tag


def _identificar_na_vista(doc, view, selecao, distancia_mm, contadores):
    dist_ft = distancia_mm * view.Scale / _MM_POR_FT
    ja = _ids_ja_identificados(doc, view)

    for cat_modelo, simbolo in selecao:
        try:
            if view.GetCategoryHidden(simbolo.Category.Id):
                continue
        except Exception:
            pass
        elementos = FilteredElementCollector(doc, view.Id) \
            .OfCategoryId(cat_modelo.Id).WhereElementIsNotElementType().ToElements()
        for elem in elementos:
            if _id_value(elem.Id) in ja:
                contadores["puladas"] += 1
                continue
            direcao = _direcao_chamada(elem)
            if direcao is None:
                contadores["sem_orientacao"] += 1
                continue
            try:
                c = _centro_xy(elem)
                cabeca = XYZ(c.X + direcao.X * dist_ft,
                             c.Y + direcao.Y * dist_ft, c.Z)
                _criar_tag(doc, view, elem, simbolo, cabeca)
                contadores["criadas"] += 1
            except Exception:
                contadores["erros"] += 1


def _vistas_alvo(doc, uidoc, todo_projeto):
    def e_planta(v):
        return (isinstance(v, ViewPlan) and not v.IsTemplate
                and v.ViewType in (ViewType.FloorPlan, ViewType.EngineeringPlan))
    if not todo_projeto:
        v = uidoc.ActiveView
        return [v] if e_planta(v) else []
    return [v for v in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
            if e_planta(v)]


# ===========================================================================
# API PÚBLICA
# ===========================================================================

def identificar_sinalizacoes(doc, uidoc, output):
    janela = _Janela(_catalogo_identificadores(doc))
    janela.ShowDialog()
    if not janela.confirmado:
        return

    vistas = _vistas_alvo(doc, uidoc, janela.todo_projeto())
    if not vistas:
        forms.alert(
            u"A vista ativa não é uma planta. Abra uma planta ou escolha "
            u"\"todas as vistas de planta do projeto\".",
            title=u"Fire Utils — Identificar Sinalizações")
        return

    selecao = janela.selecao()
    contadores = {"criadas": 0, "puladas": 0, "sem_orientacao": 0, "erros": 0}

    with Transaction(doc, u"FireUtils - Identificar Sinalizações") as t:
        t.Start()
        try:
            for v in vistas:
                _identificar_na_vista(doc, v, selecao, janela.distancia_mm, contadores)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            output.print_md(u"**{}**".format(texto_erro(ex)))
            return

    forms.alert(
        u"Vistas processadas: {}\nIdentificadores criados: {}\n"
        u"Já identificados (pulados): {}\nSem orientação (pulados): {}\n"
        u"Erros: {}".format(
            len(vistas), contadores["criadas"], contadores["puladas"],
            contadores["sem_orientacao"], contadores["erros"]),
        title=u"Fire Utils — Identificar Sinalizações")
