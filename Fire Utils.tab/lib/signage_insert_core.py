# -*- coding: utf-8 -*-
"""
signage_insert_core.py — Fire Utils · lib/
Lógica central do botão "Sinalizar Equipamentos": mostra um painel de
checkbox (signage_opcoes.xaml) com os tipos de placa disponíveis (ver
signage_family.py) e, pra cada tipo marcado, confirma que a família da
placa JÁ ESTÁ carregada no projeto (não baixa nada — se faltar, orienta
o usuário a carregá-la pela dockpane) e insere uma instância na mesma
posição (X, Y) e orientação de cada equipamento já presente no projeto
que ainda não tiver uma placa daquele tipo por perto — usando o nível
de referência de cada tipo (TipoSinalizacao.nivel_referencia — o do
próprio equipamento, ou o do abrigo mais próximo pra Sirene/Botoeira,
ver signage_family.py), na elevação definida por tipo
(TipoSinalizacao.elevacao_m), nunca a elevação real do equipamento.

Função pública
--------------
sinalizar_equipamentos(doc, uidoc, output)
"""

import os
import math

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, Family,
    FilteredElementCollector, FamilyInstance,
    ElementTransformUtils, UnitUtils,
)
from Autodesk.Revit.DB.Structure import StructuralType
from pyrevit import forms

from signage_family import TIPOS_SINALIZACAO, slugify
from family_error_utils import texto_erro

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

TOL              = 1e-4
TOL_DUPLICATA_M  = 0.30   # raio (m) para considerar já sinalizado

_XAML_OPCOES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"signage_opcoes.xaml")


# ===========================================================================
# FORM — seleção dos tipos de sinalização a inserir
# ===========================================================================

class _JanelaSinalizacao(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, _XAML_OPCOES_PATH)
        self.confirmado = False
        self._checkboxes = dict(
            (tipo.chave, getattr(self, u"Chk_" + tipo.chave))
            for tipo in TIPOS_SINALIZACAO
        )

    def tipos_selecionados(self):
        return [t for t in TIPOS_SINALIZACAO if self._checkboxes[t.chave].IsChecked]

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self.tipos_selecionados():
            self.TxtStatus.Text = u"Selecione ao menos um tipo de sinalização."
            return
        self.confirmado = True
        self.Close()


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================

def _familia_placa_carregada(doc, arquivo_slug):
    """Procura, entre as famílias já carregadas em `doc`, uma cujo Name —
    passado pelo mesmo slugify() usado pra gerar o nome de arquivo da
    placa no catálogo (ver signage_family.py) — bata com `arquivo_slug`
    (ex.: uma família 'Placa de Sinalização E8 - 8m' vira
    'placa-de-sinalizacao-e8-8m'). Não baixa nada: retorna None se a
    família ainda não estiver no projeto."""
    return next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if slugify(f.Name) == arquivo_slug),
        None
    )


def _ativar_simbolo_placa(doc, familia):
    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None
    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Símbolo {}".format(familia.Name)) as t:
            t.Start()
            simbolo.Activate()
            t.Commit()
    return simbolo


def _pontos_placas_existentes(doc, nome_familia_placa):
    pontos = []
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .WhereElementIsNotElementType().ToElements():
        if e.Symbol is None or e.Symbol.Family is None:
            continue
        if e.Symbol.Family.Name != nome_familia_placa:
            continue
        try:
            pontos.append(e.Location.Point)
        except Exception:
            pass
    return pontos


def _ponto_insercao(equipamento, nivel, elevacao_m):
    """X/Y do equipamento, Z = elevação do NÍVEL do equipamento + a
    elevação própria do tipo de placa (0 pra Hidrante/Extintor — a
    família já embute a altura certa; ALTURA_ALARME_M/ALTURA_ACION_M
    pra Sirene/Botoeira, que não têm altura própria embutida) — nunca a
    elevação real (Z) do equipamento em si."""
    pt_equip = equipamento.Location.Point
    return XYZ(pt_equip.X, pt_equip.Y, nivel.Elevation + _to_ft(elevacao_m))


def _inserir_placa(doc, simbolo, equipamento, nivel, pt):
    """Insere a placa em `pt` (ver _ponto_insercao), virada pra mesma
    orientação (FacingOrientation) do equipamento."""
    inst = doc.Create.NewFamilyInstance(pt, simbolo, nivel, StructuralType.NonStructural)

    doc.Regenerate()
    try:
        dir_alvo  = equipamento.FacingOrientation
        dir_atual = inst.FacingOrientation
        angulo = (math.atan2(dir_alvo.Y, dir_alvo.X)
                  - math.atan2(dir_atual.Y, dir_atual.X))
        if abs(angulo) > TOL:
            eixo = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
            ElementTransformUtils.RotateElement(doc, inst.Id, eixo, angulo)
    except Exception:
        pass

    return inst


def _sinalizar_tipo(doc, tipo, output):
    familia = _familia_placa_carregada(doc, tipo.arquivo_slug)
    if familia is None:
        output.print_md(
            u"**{}** — a família da placa ainda não está no projeto. Abra "
            u"a Biblioteca de Famílias (dockpane) e carregue-a antes de "
            u"sinalizar este tipo.".format(tipo.rotulo))
        return

    simbolo = _ativar_simbolo_placa(doc, familia)
    if simbolo is None:
        output.print_md(u"**{}** — família carregada, mas nenhum tipo encontrado.".format(tipo.rotulo))
        return

    nome_placa = familia.Name

    equipamentos = tipo.localizar(doc)
    if not equipamentos:
        output.print_md(u"**{}** — nenhum equipamento encontrado no projeto.".format(tipo.rotulo))
        return

    pontos_existentes = _pontos_placas_existentes(doc, nome_placa)
    tol_ft = _to_ft(TOL_DUPLICATA_M)

    inseridas = 0
    puladas   = 0
    erros     = 0

    with Transaction(doc, u"FireUtils - Sinalizar {}".format(tipo.rotulo)) as t:
        t.Start()
        try:
            for equipamento in equipamentos:
                nivel = tipo.nivel_referencia(doc, equipamento)
                if nivel is None:
                    erros += 1
                    continue

                try:
                    pt = _ponto_insercao(equipamento, nivel, tipo.elevacao_m)
                except Exception:
                    erros += 1
                    continue

                if any(pt.DistanceTo(p) < tol_ft for p in pontos_existentes):
                    puladas += 1
                    continue

                try:
                    _inserir_placa(doc, simbolo, equipamento, nivel, pt)
                    pontos_existentes.append(pt)
                    inseridas += 1
                except Exception:
                    erros += 1
            t.Commit()
        except Exception as ex:
            t.RollBack()
            output.print_md(u"**{}** — falhou: `{}`".format(tipo.rotulo, texto_erro(ex)))
            return

    output.print_md(
        u"**{}** — inseridas: {} | já sinalizadas: {} | erros: {}".format(
            tipo.rotulo, inseridas, puladas, erros))


# ===========================================================================
# API PÚBLICA
# ===========================================================================

def sinalizar_equipamentos(doc, uidoc, output):
    janela = _JanelaSinalizacao()
    janela.ShowDialog()
    if not janela.confirmado:
        return

    for tipo in janela.tipos_selecionados():
        _sinalizar_tipo(doc, tipo, output)
