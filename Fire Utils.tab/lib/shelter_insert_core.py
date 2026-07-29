# -*- coding: utf-8 -*-
"""
shelter_insert_core.py — Fire Utils · lib/
Lógica central de posicionamento do abrigo de mangueira para hidrante.

Funções públicas
----------------
posicionar_abrigo(doc, valvula, dir_saida, nivel, output=None)
    Insere um abrigo ao lado de uma válvula já existente.

posicionar_todos_abrigos(doc, uidoc, output)
    Localiza todas as válvulas no projeto e insere abrigos onde ainda não existem.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line,
    FilteredElementCollector, FamilyInstance,
    ElementTransformUtils, UnitUtils,
    BuiltInParameter,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Structure import StructuralType
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

from shelter_family import garantir_abrigo, NOME_FAMILIA_ABRIGO
from hydrant_family import NOME_FAMILIA as NOME_FAMILIA_VALVULA

TOL = 1e-4
TOL_DUPLICATA_M = 0.50  # raio 3D (metros) para considerar abrigo já existente
OFFSET_FRENTE_M = 0.10  # deslocamento extra à frente (dir_abrigo) no posicionamento automático


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================

def _angulo_entre(v_de, v_para):
    return math.atan2(v_para.Y, v_para.X) - math.atan2(v_de.Y, v_de.X)


def _dist_xy(a, b):
    """Distância horizontal (XY) entre dois pontos — ignora Z."""
    return math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2)


def _dir_valvula(doc, valvula):
    """
    Retorna a direção horizontal do pipe conectado à válvula.
    Fallback: FacingOrientation da família, depois eixo X.
    """
    try:
        for conn in valvula.MEPModel.ConnectorManager.Connectors:
            for ref in conn.AllRefs:
                try:
                    elem = doc.GetElement(ref.Owner.Id)
                    if isinstance(elem, Pipe):
                        loc = elem.Location.Curve
                        p0, p1 = loc.GetEndPoint(0), loc.GetEndPoint(1)
                        dx, dy = p1.X - p0.X, p1.Y - p0.Y
                        length = math.sqrt(dx * dx + dy * dy)
                        if length > TOL:
                            return XYZ(dx / length, dy / length, 0.0)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        fo = valvula.FacingOrientation
        return XYZ(fo.X, fo.Y, 0.0)
    except Exception:
        pass
    return XYZ(1.0, 0.0, 0.0)


def _calcular_pt_abrigo(pt_valvula, dir_saida, nivel, dir_abrigo=None):
    """
    Calcula a posição de inserção do abrigo:
      +0.18 m ao longo do eixo da válvula (dir_saida)
      -0.085 m na direção da face do abrigo (dir_abrigo → "para trás")
      +OFFSET_FRENTE_M na direção da face do abrigo (dir_abrigo → "à frente")
      Z = nivel.Elevation (família tem altura predefinida, sem offset)
    """
    # Offset ao longo do eixo da válvula
    ox = dir_saida.X * _to_ft(0.18)
    oy = dir_saida.Y * _to_ft(0.18)
    # Offset "para trás" = oposto à face do abrigo, mais um deslocamento extra à frente
    if dir_abrigo is not None:
        ox -= dir_abrigo.X * _to_ft(0.18)
        oy -= dir_abrigo.Y * _to_ft(0.18)
        ox += dir_abrigo.X * _to_ft(OFFSET_FRENTE_M)
        oy += dir_abrigo.Y * _to_ft(OFFSET_FRENTE_M)
    return XYZ(pt_valvula.X + ox, pt_valvula.Y + oy, nivel.Elevation)


def _zerar_offset_nivel(abrigo):
    """Zera o parâmetro 'Elevação do nível' (offset from level) da instância."""
    for bip in [BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM,
                BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
                BuiltInParameter.SCHEDULE_BASE_LEVEL_OFFSET_PARAM]:
        try:
            p = abrigo.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(0.0)
                return
        except Exception:
            pass
    # Fallback: busca por nome (varia com idioma do Revit)
    for nome in [u"Elevação do nível", u"Offset from Level", u"Level Offset"]:
        try:
            p = abrigo.LookupParameter(nome)
            if p and not p.IsReadOnly:
                p.Set(0.0)
                return
        except Exception:
            pass


def _inserir_abrigo_transacao(doc, simbolo, pt, dir_abrigo, nivel):
    """Cria, rotaciona e zera o offset do abrigo dentro de uma transação já aberta.
    dir_abrigo define a face frontal do abrigo (direção escolhida pelo usuário).
    """
    abrigo = doc.Create.NewFamilyInstance(
        pt, simbolo, nivel, StructuralType.NonStructural
    )
    _zerar_offset_nivel(abrigo)
    angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_abrigo) + math.pi / 2.0
    if abs(angulo) > TOL:
        eixo = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
        ElementTransformUtils.RotateElement(doc, abrigo.Id, eixo, angulo)
    return abrigo


# ===========================================================================
# API PÚBLICA
# ===========================================================================

def posicionar_abrigo(doc, valvula, dir_saida, nivel, output=None, dir_abrigo=None):
    """
    Insere o abrigo de mangueira na posição da válvula.

    Parâmetros
    ----------
    doc        : Revit Document
    valvula    : FamilyInstance da válvula de hidrante já inserida
    dir_saida  : XYZ — direção do ramal horizontal (usada como fallback)
    nivel      : Level do Revit
    output     : pyRevit output (opcional)
    dir_abrigo : XYZ — direção da face do abrigo (clique 3).
                 Se None, usa dir_saida como fallback.

    Retorno
    -------
    FamilyInstance do abrigo, ou None em caso de erro.
    """
    if dir_abrigo is None:
        dir_abrigo = dir_saida
    simbolo, erro = garantir_abrigo(doc)
    if erro:
        if output:
            output.print_md(u"| Abrigo | **erro ao carregar família** — {} |".format(erro))
        return None

    try:
        pt_valvula = valvula.Location.Point
    except Exception as e:
        if output:
            output.print_md(u"| Abrigo | **posição da válvula inválida** — `{}` |".format(str(e)))
        return None

    pt = _calcular_pt_abrigo(pt_valvula, dir_saida, nivel, dir_abrigo)

    with Transaction(doc, u"FireUtils - Inserir Abrigo de Hidrante") as t:
        t.Start()
        try:
            abrigo = _inserir_abrigo_transacao(doc, simbolo, pt, dir_abrigo, nivel)
            t.Commit()
            return abrigo
        except Exception as e:
            t.RollBack()
            if output:
                output.print_md(u"| Abrigo | **falhou** — `{}` |".format(str(e)))
            return None


def posicionar_todos_abrigos(doc, uidoc, output):
    """
    Localiza todas as instâncias de 'Valvula para Hidrante' no projeto
    e insere um abrigo ao lado de cada uma onde ainda não houver um.
    Cada válvula recebe sua própria transação — falhas individuais não
    cancelam as demais.
    """
    simbolo, erro = garantir_abrigo(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # Coleta válvulas
    todas_inst = FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements()
    valvulas = [e for e in todas_inst
                if e.Symbol.Family.Name == NOME_FAMILIA_VALVULA]

    if not valvulas:
        forms.alert(
            u"Nenhuma instância de '{}' encontrada no projeto.".format(NOME_FAMILIA_VALVULA),
            title=u"Fire Utils", warn_icon=True
        )
        pyscript.exit()

    # Posições de abrigos já existentes (para evitar duplicatas)
    abrigos_existentes = [e for e in todas_inst
                          if e.Symbol.Family.Name == NOME_FAMILIA_ABRIGO]
    posicoes_abrigo = []
    for a in abrigos_existentes:
        try:
            posicoes_abrigo.append(a.Location.Point)
        except Exception:
            pass

    tol_dup_ft = _to_ft(TOL_DUPLICATA_M)

    inseridos = 0
    pulados   = 0
    erros     = 0

    for valvula in valvulas:
        vid = valvula.Id.Value
        try:
            pt_valvula = valvula.Location.Point
        except Exception:
            output.print_md(u"| {} | **posição inválida** |".format(vid))
            erros += 1
            continue

        dir_s  = _dir_valvula(doc, valvula)
        nivel  = doc.GetElement(valvula.LevelId)
        if nivel is None:
            output.print_md(u"| {} | **nível não encontrado** |".format(vid))
            erros += 1
            continue

        dir_abrigo_s = XYZ(dir_s.Y, -dir_s.X, 0.0)   # direita de dir_s (padrão batch)
        pt = _calcular_pt_abrigo(pt_valvula, dir_s, nivel, dir_abrigo_s)

        # Compara a posição calculada do abrigo contra abrigos existentes (3D, 50 cm).
        # Usa pt (posição do abrigo) vs posições de abrigos — mesmo Z, distância real.
        if any(pt.DistanceTo(pa) < tol_dup_ft for pa in posicoes_abrigo):
            pulados += 1
            continue

        with Transaction(doc, u"FireUtils - Abrigo {}".format(vid)) as t:
            t.Start()
            try:
                _inserir_abrigo_transacao(doc, simbolo, pt, dir_abrigo_s, nivel)
                t.Commit()
                posicoes_abrigo.append(pt)   # evita dupla inserção na mesma execução
                inseridos += 1
            except Exception as e:
                t.RollBack()
                erros += 1