# -*- coding: utf-8 -*-
"""
alarm_insert_core.py — Fire Utils · lib/
Lógica central de posicionamento do conjunto de alarme de incêndio
(acionador + avisador sonoro/visual) ao lado dos abrigos de hidrante.

Função pública
--------------
inserir_alarmes(doc, uidoc, output)
    Localiza todos os abrigos no projeto e insere um conjunto de alarme
    57 cm à direita de cada um (HandOrientation do abrigo), na mesma
    face e direção, onde ainda não houver componente.
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
from Autodesk.Revit.DB.Structure import StructuralType
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

from alarm_family import (garantir_acionador, garantir_alarme_sonoro,
                           NOME_FAMILIA_ACIONADOR, NOME_FAMILIA_ALARME)
from shelter_family import NOME_FAMILIA_ABRIGO

TOL              = 1e-4
DIST_ALARME_M    = 0.57   # eixo a eixo: abrigo → conjunto de alarme
DESLOC_FRENTE_M  = 0.38   # valor do parâmetro "Desloc. Frente" do acionador
ALTURA_ACION_M   = 1.35   # elevação do acionador em relação ao NÍVEL DO ABRIGO
ALTURA_ALARME_M  = 2.20   # elevação do avisador sonoro/visual em relação ao NÍVEL DO ABRIGO
TOL_DUPLICATA_M  = 0.30   # raio (m) para considerar componente já existente

# Candidatos de parâmetro de instância pra forçar o "Nível de
# referência" (ver _forcar_nivel_referencia) — via getattr porque nem
# todo BuiltInParameter existe em toda versão da API do Revit.
_BIPS_NIVEL_REFERENCIA = [
    b for b in (getattr(BuiltInParameter, nome, None)
                for nome in (u"FAMILY_LEVEL_PARAM", u"SCHEDULE_LEVEL_PARAM"))
    if b is not None
]
_NOMES_NIVEL_REFERENCIA = (u"Nível de referência", u"Reference Level", u"Nível", u"Level")


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================

def _forcar_nivel_referencia(inst, nivel):
    """
    Garante que a instância recém-criada fica de fato associada ao nível
    `nivel` (o do ABRIGO) — passar `nivel` pro construtor de
    NewFamilyInstance nem sempre é suficiente: pra famílias não
    hospedadas (Work Plane-Based/genéricas, caso comum de Acionador/
    Avisador), o parâmetro de instância "Nível de referência" pode ficar
    associado a outro nível (tipicamente o nível base do projeto) em vez
    do nível passado no construtor.

    Sem essa correção, a "Elevação do nível" (offset) passa a ser
    calculada em relação ao nível errado — somando a cota do PAVIMENTO à
    elevação combinada em vez de ficar só com a elevação: um pavimento a
    3m do nível 0 + 2,20m de elevação vira 5,20m (relativos ao nível 0)
    em vez de 2,20m (relativos ao nível do abrigo, o valor combinado).
    Best-effort — se nenhum parâmetro candidato existir/for editável
    pra essa família, a instância continua na posição absoluta correta
    (calculada por quem chama), só o "Nível de referência" que pode
    ficar desatualizado.
    """
    for bip in _BIPS_NIVEL_REFERENCIA:
        try:
            p = inst.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(nivel.Id)
                return
        except Exception:
            pass
    for nome in _NOMES_NIVEL_REFERENCIA:
        try:
            p = inst.LookupParameter(nome)
            if p and not p.IsReadOnly:
                p.Set(nivel.Id)
                return
        except Exception:
            pass


def _zerar_offset_nivel(inst):
    """Zera o parâmetro de elevação de nível da instância."""
    for bip in [BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM,
                BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
                BuiltInParameter.SCHEDULE_BASE_LEVEL_OFFSET_PARAM]:
        try:
            p = inst.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(0.0)
                return
        except Exception:
            pass
    for nome in [u"Elevação do nível", u"Offset from Level", u"Level Offset"]:
        try:
            p = inst.LookupParameter(nome)
            if p and not p.IsReadOnly:
                p.Set(0.0)
                return
        except Exception:
            pass


def _set_param_metros(inst, nome_param, valor_m):
    """Seta um parâmetro de comprimento (em metros) por nome."""
    try:
        p = inst.LookupParameter(nome_param)
        if p and not p.IsReadOnly:
            p.Set(_to_ft(valor_m))
    except Exception:
        pass


def _inserir_componente(doc, simbolo, pt_xy, dir_face, nivel, altura_m):
    """
    Insere um FamilyInstance na posição (pt_xy.X, pt_xy.Y, nivel.Elevation + altura_m)
    e o rotaciona para alinhar sua FacingOrientation com dir_face.
    A altura é preservada como offset do nível — não é zerada.
    `nivel` (o do ABRIGO) é reforçado como Nível de referência da
    instância após a criação — ver _forcar_nivel_referencia.
    Retorna a instância criada.
    """
    pt = XYZ(pt_xy.X, pt_xy.Y, nivel.Elevation + _to_ft(altura_m))
    inst = doc.Create.NewFamilyInstance(
        pt, simbolo, nivel, StructuralType.NonStructural
    )
    _forcar_nivel_referencia(inst, nivel)

    # Lê a orientação atual do componente recém-inserido e ajusta para dir_face
    doc.Regenerate()
    try:
        dir_atual = inst.FacingOrientation
        angulo = (math.atan2(dir_face.Y, dir_face.X)
                  - math.atan2(dir_atual.Y, dir_atual.X)
                  + math.pi)
        if abs(angulo) > TOL:
            eixo = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + 1.0))
            ElementTransformUtils.RotateElement(doc, inst.Id, eixo, angulo)
    except Exception:
        pass

    return inst


# ===========================================================================
# API PÚBLICA
# ===========================================================================

def inserir_alarmes(doc, uidoc, output):
    """
    Localiza todos os abrigos de hidrante no projeto e insere um conjunto
    de alarme (acionador + avisador sonoro/visual) 57 cm à direita de cada
    um onde ainda não houver componente (tolerância 30 cm).

    Cada abrigo tem sua própria transação — falhas individuais não
    cancelam as demais.
    """
    # ── Garantir famílias ────────────────────────────────────────────────
    sim_acion, erro = garantir_acionador(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    sim_alarme, erro = garantir_alarme_sonoro(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # ── Coletar abrigos ──────────────────────────────────────────────────
    todas_inst = FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements()

    abrigos = [e for e in todas_inst
               if e.Symbol.Family.Name == NOME_FAMILIA_ABRIGO]

    if not abrigos:
        forms.alert(
            u"Nenhum abrigo de hidrante ('{}') encontrado no projeto.".format(
                NOME_FAMILIA_ABRIGO),
            title=u"Fire Utils", warn_icon=True
        )
        pyscript.exit()

    # ── Posições de componentes já existentes (evitar duplicatas) ────────
    pts_acion = []
    pts_alarm  = []
    for e in todas_inst:
        try:
            nome_fam = e.Symbol.Family.Name
            pt       = e.Location.Point
            if nome_fam == NOME_FAMILIA_ACIONADOR:
                pts_acion.append(pt)
            elif nome_fam == NOME_FAMILIA_ALARME:
                pts_alarm.append(pt)
        except Exception:
            pass

    tol_ft  = _to_ft(TOL_DUPLICATA_M)
    dist_ft = _to_ft(DIST_ALARME_M)

    inseridos = 0
    pulados   = 0
    erros     = 0

    for abrigo in abrigos:
        aid = abrigo.Id.Value

        try:
            pt_abrigo = abrigo.Location.Point
        except Exception:
            output.print_md(u"| {} | **posição inválida** |".format(aid))
            erros += 1
            continue

        nivel = doc.GetElement(abrigo.LevelId)
        if nivel is None:
            output.print_md(u"| {} | **nível não encontrado** |".format(aid))
            erros += 1
            continue

        # HandOrientation = direção "direita" da família no Revit
        try:
            hand = abrigo.HandOrientation
            dir_hand = XYZ(hand.X, hand.Y, 0.0)
        except Exception:
            dir_hand = XYZ(1.0, 0.0, 0.0)

        # FacingOrientation = direção da face (para replicar nos componentes)
        try:
            face = abrigo.FacingOrientation
            dir_face = XYZ(face.X, face.Y, 0.0)
        except Exception:
            dir_face = XYZ(0.0, 1.0, 0.0)

        # Ponto XY do conjunto de alarme (57 cm no lado OPOSTO ao HandOrientation)
        pt_conj = XYZ(
            pt_abrigo.X - dir_hand.X * dist_ft,
            pt_abrigo.Y - dir_hand.Y * dist_ft,
            pt_abrigo.Z
        )

        # Verificar duplicatas por componente
        ja_tem_acion = any(pt_conj.DistanceTo(p) < tol_ft for p in pts_acion)
        ja_tem_alarm  = any(pt_conj.DistanceTo(p) < tol_ft for p in pts_alarm)

        if ja_tem_acion and ja_tem_alarm:
            pulados += 1
            continue

        with Transaction(doc, u"FireUtils - Alarme {}".format(aid)) as t:
            t.Start()
            try:
                if not ja_tem_acion:
                    acion = _inserir_componente(
                        doc, sim_acion, pt_conj, dir_face, nivel, ALTURA_ACION_M)
                    _set_param_metros(acion, u"Desloc. Frente", DESLOC_FRENTE_M)
                    pts_acion.append(pt_conj)

                if not ja_tem_alarm:
                    _inserir_componente(
                        doc, sim_alarme, pt_conj, dir_face, nivel, ALTURA_ALARME_M)
                    pts_alarm.append(pt_conj)

                t.Commit()
                inseridos += 1

            except Exception as e:
                t.RollBack()
                output.print_md(u"| {} | **falhou** — `{}` |".format(aid, str(e)))
                erros += 1

    output.print_md(
        u"**Conjuntos inseridos:** {} | **Pulados (já existem):** {} | **Erros:** {}".format(
            inseridos, pulados, erros)
    )
