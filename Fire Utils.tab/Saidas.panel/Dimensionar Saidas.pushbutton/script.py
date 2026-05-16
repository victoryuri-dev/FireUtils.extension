# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Saídas de Emergência
Coleta ambientes, calcula AD / ER / PT por pavimento e exibe conferência rápida.
"""
__title__ = "Dimensionar\nSaídas"

import math
import datetime
from pyrevit import revit, DB, forms, script
from saidas.calc import calcular_saidas, salvar_cache_saidas

doc    = revit.doc
output = script.get_output()

# ===========================================================================
# PASSO 1 — Identificar o pavimento térreo
# ===========================================================================

niveis = DB.FilteredElementCollector(doc)\
           .OfClass(DB.Level)\
           .ToElements()
niveis_ordenados = sorted(niveis, key=lambda l: l.Elevation)
nomes_niveis     = [n.Name for n in niveis_ordenados]

nome_terreo = forms.SelectFromList.show(
    nomes_niveis,
    title=u"Fire Utils — Saídas de Emergência",
    prompt=u"Selecione o Pavimento Térreo:",
    multiselect=False
)
if not nome_terreo:
    script.exit()

# ===========================================================================
# PASSO 2 — Coletar ambientes com ocupação identificada
# ===========================================================================

rooms_revit = DB.FilteredElementCollector(doc)\
               .OfCategory(DB.BuiltInCategory.OST_Rooms)\
               .WhereElementIsNotElementType()\
               .ToElements()

rooms_data   = []
sem_ocupacao = []

for room in rooms_revit:
    try:
        if room.Area == 0:
            continue

        p_grupo = room.LookupParameter(u"Grupo")
        p_pop   = room.LookupParameter(u"População")
        p_nome  = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME)
        p_area  = room.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
        nivel   = room.Level.Name if room.Level else u"(sem nível)"

        grupo = p_grupo.AsString() if (p_grupo and p_grupo.HasValue) else None
        pop   = int(p_pop.AsInteger()) if (p_pop and p_pop.HasValue) else 0
        nome  = p_nome.AsString() if (p_nome and p_nome.HasValue) else u"(sem nome)"
        area  = math.ceil(p_area.AsDouble() * 0.092903) if p_area else 0.0

        if not grupo:
            sem_ocupacao.append(nome)
            continue

        rooms_data.append({
            u"nivel": nivel,
            u"nome":  nome,
            u"grupo": grupo,
            u"area":  float(area),
            u"pop":   pop,
        })
    except Exception:
        continue

if not rooms_data:
    forms.alert(
        u"Nenhum ambiente com ocupação identificada.\n"
        u"Execute 'Identificar Ambiente' primeiro.",
        title=u"Fire Utils", warn_icon=True
    )
    script.exit()

# ===========================================================================
# PASSO 3 — Calcular
# ===========================================================================

res = calcular_saidas(rooms_data, nome_terreo=nome_terreo)

# ===========================================================================
# PASSO 4 — Output rápido de conferência
# ===========================================================================

timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")

output.print_md(u"# Fire Utils — Dimensionamento de Saídas de Emergência")
output.print_md(u"*Calculado em {}  ·  Térreo: {}*".format(timestamp, nome_terreo))
output.print_md(u"---")

# Aviso de ambientes sem ocupação
if sem_ocupacao:
    output.print_md(
        u"> ⚠ **{} ambiente(s) sem ocupação ignorado(s):** {}".format(
            len(sem_ocupacao),
            u", ".join(sem_ocupacao[:8]) + (u"..." if len(sem_ocupacao) > 8 else u"")
        )
    )
    output.print_md(u"")

# ---- ACESSOS E DESCARGAS --------------------------------------------------
output.print_md(u"### 1. Acessos e Descargas (AD)")
output.print_md(u"| Pavimento | Pop. | Cap./UP | N | L calc. | L mín. | **L adotada** |")
output.print_md(u"|---|---|---|---|---|---|---|")
for nd in res[u"ad"]:
    cap  = nd[u"cap"]  or u"—"
    n    = nd[u"n_up"] if nd[u"n_up"] is not None else u"—"
    lc   = u"{:.2f} m".format(nd[u"largura_calc"])   if nd[u"largura_calc"]   else u"—"
    lm   = u"{:.2f} m".format(nd[u"largura_min"])    if nd[u"largura_min"]    else u"—"
    la   = u"**{:.2f} m**".format(nd[u"largura_adotada"]) if nd[u"largura_adotada"] else u"—"
    output.print_md(u"| {} | {} | {} pess./UP | {} UP | {} | {} | {} |".format(
        nd[u"nivel"], nd[u"pop"], cap, n, lc, lm, la
    ))

output.print_md(u"")

# ---- ESCADAS E RAMPAS ------------------------------------------------------
output.print_md(u"### 2. Escadas e Rampas (ER)")
er = res[u"er"]
output.print_md(u"*{}*".format(er[u"motivo"]))
output.print_md(u"")
output.print_md(u"| Pavimento | Pop. | Cap./UP | N | L calc. | L mín. | **L adotada** |")
output.print_md(u"|---|---|---|---|---|---|---|")
cap  = er[u"cap"]  or u"—"
n    = er[u"n_up"] if er[u"n_up"] is not None else u"—"
lc   = u"{:.2f} m".format(er[u"largura_calc"])   if er[u"largura_calc"]   else u"—"
lm   = u"{:.2f} m".format(er[u"largura_min"])    if er[u"largura_min"]    else u"—"
la   = u"**{:.2f} m**".format(er[u"largura_adotada"]) if er[u"largura_adotada"] else u"—"
output.print_md(u"| {} | {} | {} pess./UP | {} UP | {} | {} | {} |".format(
    er[u"nivel"], er[u"pop"], cap, n, lc, lm, la
))

output.print_md(u"")

# ---- PORTAS ---------------------------------------------------------------
output.print_md(u"### 3. Portas (PT)")
output.print_md(u"| Pavimento | Pop. | Cap./UP | N | L calc. | L mín. | Tipo | **L adotada** |")
output.print_md(u"|---|---|---|---|---|---|---|---|")
for nd in res[u"pt"]:
    cap  = nd[u"cap"]  or u"—"
    n    = nd[u"n_up"] if nd[u"n_up"] is not None else u"—"
    lc   = u"{:.2f} m".format(nd[u"largura_calc"])   if nd[u"largura_calc"]   else u"—"
    lm   = u"{:.2f} m".format(nd[u"largura_min"])    if nd[u"largura_min"]    else u"—"
    la   = u"**{:.2f} m**".format(nd[u"largura_adotada"]) if nd[u"largura_adotada"] else u"—"
    tipo = nd[u"tipo_porta"] or u"—"
    output.print_md(u"| {} | {} | {} pess./UP | {} UP | {} | {} | {} | {} |".format(
        nd[u"nivel"], nd[u"pop"], cap, n, lc, lm, tipo, la
    ))

output.print_md(u"")

# ---- RESUMO GERAL ----------------------------------------------------------
output.print_md(u"### Resumo Geral")
output.print_md(u"| Tipo | Pavimento | **Largura adotada** |")
output.print_md(u"|---|---|---|")

for nd in res[u"ad"]:
    output.print_md(u"| Acesso/Descarga | {} | **{:.2f} m** |".format(
        nd[u"nivel"], nd[u"largura_adotada"]
    ))

if res[u"tem_multiplos_pavimentos"]:
    output.print_md(u"| Escada/Rampa | {} *(maior pop.)* | **{:.2f} m** |".format(
        er[u"nivel"], er[u"largura_adotada"]
    ))
else:
    output.print_md(u"| Escada/Rampa | {} | **{:.2f} m** |".format(
        er[u"nivel"], er[u"largura_adotada"]
    ))

for nd in res[u"pt"]:
    tipo = u" ({})".format(nd[u"tipo_porta"]) if nd[u"tipo_porta"] else u""
    output.print_md(u"| Porta | {} | **{:.2f} m**{} |".format(
        nd[u"nivel"], nd[u"largura_adotada"], tipo
    ))

output.print_md(u"")
output.print_md(u"---")
output.print_md(u"*Cache salvo. Use o botão **Gerar Memorial** para o relatório completo.*")

# ===========================================================================
# PASSO 5 — Salvar cache
# ===========================================================================

payload_saidas = {
    u"resultados":              res,
    u"rooms_data":              rooms_data,
    u"nome_terreo":             nome_terreo,
    u"timestamp":               timestamp,
}
salvar_cache_saidas(payload_saidas)

# ===========================================================================
# PASSO 6 — Enviar ao servidor local (se ativo)
# ===========================================================================

try:
    from server.client import servidor_ativo, enviar_saidas
    if servidor_ativo():
        enviado = enviar_saidas(payload_saidas)
        if enviado:
            output.print_md(u"✅ *Dados enviados ao servidor local — memorial atualizado.*")
except Exception:
    pass  # servidor inativo ou não instalado — silencioso
