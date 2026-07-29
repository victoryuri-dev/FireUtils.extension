# -*- coding: utf-8 -*-
__title__ = "Inserir Hidrante\ncom Abrigo"

import math
from Autodesk.Revit.DB import XYZ
from pyrevit import script, forms
from hydrant_insert_core import run
from shelter_insert_core import posicionar_abrigo

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

# Cliques 1 e 2 acontecem dentro de run() (origem + direção da válvula).
# A transação de criação da coluna também ocorre dentro de run().
resultado = run(doc, uidoc, output, forcar_nivel=False)
if not resultado:
    script.exit()

# ── Clique 3: direção da face do abrigo ──────────────────────────────────
try:
    pt_dir_abrigo = uidoc.Selection.PickPoint(
        u"Clique para indicar a direção do abrigo de hidrante"
    )
except Exception:
    script.exit()

# Vetor horizontal do clique 3 em relação à posição da válvula,
# com snapping a 90° em relação ao tubo principal.
try:
    pt_valvula = resultado[u"valvula"].Location.Point
except Exception:
    pt_valvula = None

dir_saida = resultado[u"dir_saida"]

if pt_valvula:
    dx   = pt_dir_abrigo.X - pt_valvula.X
    dy   = pt_dir_abrigo.Y - pt_valvula.Y
    dlen = math.sqrt(dx * dx + dy * dy)
    if dlen > 1e-3:
        _v = XYZ(dx / dlen, dy / dlen, 0.0)
        # Face do abrigo só pode ser perpendicular ao eixo da válvula:
        # esquerda ou direita de dir_saida.
        _direita   = XYZ( dir_saida.Y, -dir_saida.X, 0.0)
        _esquerda  = XYZ(-dir_saida.Y,  dir_saida.X, 0.0)
        dir_abrigo = max([_direita, _esquerda], key=lambda d: _v.DotProduct(d))
    else:
        dir_abrigo = XYZ(dir_saida.Y, -dir_saida.X, 0.0)  # direita por padrão
else:
    dir_abrigo = XYZ(dir_saida.Y, -dir_saida.X, 0.0)

posicionar_abrigo(
    doc,
    resultado[u"valvula"],
    dir_saida,
    resultado[u"nivel"],
    output,
    dir_abrigo=dir_abrigo,
)
