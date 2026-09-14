# -*- coding: utf-8 -*-
"""
level_offset_utils.py — Fire Utils · lib/
Ajusta, de forma EXPLÍCITA, os dois parâmetros nativos do Revit que
juntos definem a posição vertical de uma instância — "Nível de
referência" (qual Level) e "Elevação do nível" (offset a partir dele) —
em vez de confiar que passar um Z absoluto pro NewFamilyInstance faz o
Revit derivar a "Elevação do nível" corretamente.

Por quê: pra várias categorias de família NÃO hospedadas (caso do
Acionador Manual/Avisador Sonoro e Visual e das placas de sinalização
deste plugin), a "Elevação do nível" é calculada pelo Revit em relação
a um nível fixo do projeto (tipicamente o nível base, não o "Nível de
referência" escolhido na instância) — então criar a instância num Z
absoluto de nivel.Elevation + altura_m faz a "Elevação do nível"
exibida somar a cota do próprio nível de referência à altura combinada
(ex.: um pavimento a 3m do nível 0 + 2,20m de altura combinada vira
"Elevação do nível" = 5,20m em vez de 2,20m). Setando os dois
parâmetros direto — cada um com o valor esperado — em vez de deixar o
Revit derivar um a partir do outro, os dois ficam corretos
independentemente de como essa derivação funciona internamente pra
cada família. Mesmo padrão já usado (só que hardcoded pra zero) em
shelter_insert_core._zerar_offset_nivel pro Abrigo de Mangueira.

Uso:
    inst = doc.Create.NewFamilyInstance(
        XYZ(x, y, nivel.Elevation), simbolo, nivel, StructuralType.NonStructural)
    forcar_nivel_referencia(inst, nivel)
    definir_elevacao_nivel(inst, altura_m)

Também expõe nivel_mais_proximo_abaixo(doc, elevacao_absoluta_ft), que
resolve "qual é o pavimento real de um ponto" a partir da cota Z real
(Location.Point.Z) em vez de confiar em Element.LevelId — mesma classe
de problema, útil pra reconhecer corretamente cada válvula/abrigo de
uma coluna de hidrantes com uma instância por pavimento.
"""

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import BuiltInParameter, UnitUtils, FilteredElementCollector, Level

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)


def _bips(nomes):
    """getattr em vez de acesso direto — nem todo BuiltInParameter existe
    em toda versão da API do Revit."""
    return [b for b in (getattr(BuiltInParameter, nome, None) for nome in nomes) if b is not None]


_BIPS_NIVEL_REFERENCIA = _bips((u"FAMILY_LEVEL_PARAM", u"SCHEDULE_LEVEL_PARAM"))
_NOMES_NIVEL_REFERENCIA = (u"Nível de referência", u"Reference Level", u"Nível", u"Level")

_BIPS_OFFSET_NIVEL = _bips((
    u"INSTANCE_FREE_HOST_OFFSET_PARAM",
    u"FAMILY_BASE_LEVEL_OFFSET_PARAM",
    u"SCHEDULE_BASE_LEVEL_OFFSET_PARAM",
))
_NOMES_OFFSET_NIVEL = (u"Elevação do nível", u"Offset from Level", u"Level Offset")


def _set_primeiro_disponivel(inst, bips, nomes, valor):
    for bip in bips:
        try:
            p = inst.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(valor)
                return True
        except Exception:
            pass
    for nome in nomes:
        try:
            p = inst.LookupParameter(nome)
            if p and not p.IsReadOnly:
                p.Set(valor)
                return True
        except Exception:
            pass
    return False


def forcar_nivel_referencia(inst, nivel):
    """
    Garante que `inst` fica de fato associada ao "Nível de referência"
    `nivel` — best-effort, nunca lança; se nenhum parâmetro candidato
    existir/for editável pra essa família, não faz nada.
    """
    _set_primeiro_disponivel(inst, _BIPS_NIVEL_REFERENCIA, _NOMES_NIVEL_REFERENCIA, nivel.Id)


def definir_elevacao_nivel(inst, valor_m):
    """
    Define o parâmetro "Elevação do nível" (offset a partir do Nível de
    referência) de `inst` diretamente para `valor_m` (metros) — em vez
    de derivá-lo de um Z absoluto. Best-effort, nunca lança.
    """
    _set_primeiro_disponivel(inst, _BIPS_OFFSET_NIVEL, _NOMES_OFFSET_NIVEL, _to_ft(valor_m))


_TOL_NIVEL_FT = _to_ft(0.01)  # 1cm — tolerância pra ponto "bem em cima" da elevação do nível


def nivel_mais_proximo_abaixo(doc, elevacao_absoluta_ft):
    """
    Retorna o Level do documento cuja Elevation é a maior dentre as que
    são <= `elevacao_absoluta_ft` (pés) — ou seja, o nível do pavimento
    que fisicamente contém essa cota. Se `elevacao_absoluta_ft` for
    menor que todos os níveis do projeto, retorna o de menor elevação.
    Retorna None se não houver nenhum Level no documento.

    Usado em vez de confiar em Element.LevelId: pra várias categorias de
    família não hospedadas (válvula de hidrante, abrigo, acionador,
    avisador, sirene/botoeira sinalizadas...) o LevelId pode não
    refletir o pavimento real da instância — ver
    forcar_nivel_referencia. Derivar o nível a partir da cota Z real do
    elemento (Location.Point.Z) é robusto independente dessa
    confiabilidade, e é o que permite diferenciar corretamente uma
    coluna de hidrantes com uma válvula por pavimento (cada uma na sua
    elevação real), mesmo quando o LevelId de cada válvula está errado.
    """
    niveis = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not niveis:
        return None
    abaixo_ou_igual = [n for n in niveis if n.Elevation <= elevacao_absoluta_ft + _TOL_NIVEL_FT]
    if abaixo_ou_igual:
        return max(abaixo_ou_igual, key=lambda n: n.Elevation)
    return min(niveis, key=lambda n: n.Elevation)
