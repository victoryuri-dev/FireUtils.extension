# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Saídas de Emergência
Coleta ambientes, calcula AD / ER / PT por pavimento e exibe conferência rápida.
"""
__title__ = "Dimensionar\nSaídas"

import math
import os
import datetime
from pyrevit import revit, DB, forms, script
from saidas.calc  import calcular_saidas, salvar_cache_se_import
from saidas.forms import form_config_distancias
from projeto      import exigir_projeto_e_estado, carregar_dados_projeto

doc    = revit.doc
output = script.get_output()

# ===========================================================================
# PASSO 1 — Verificar projeto e estado configurados
# ===========================================================================

projeto_dir, sigla_estado, estado = exigir_projeto_e_estado(doc, forms, script)

# ===========================================================================
# PASSO 2 — Parâmetros de distância máxima a percorrer
# ===========================================================================

# Ocupação principal vem dos Dados do Projeto (configurada uma vez por obra)
_dados_proj       = carregar_dados_projeto(projeto_dir)
_ocup_principal   = _dados_proj.get(u"ocupacao_principal") if _dados_proj else None

config_distancias = form_config_distancias(estado, ocupacao_principal=_ocup_principal)
# Retorna None se o estado não tiver tabela de distâncias ou ocupação não configurada

# ===========================================================================
# PASSO 3 — Identificar o pavimento térreo
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
# PASSO 4 — Coletar ambientes com ocupação identificada
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
# PASSO 5 — Calcular
# ===========================================================================

res = calcular_saidas(rooms_data, nome_terreo=nome_terreo, estado=estado)

# ===========================================================================
# PASSO 6 — Output rápido de conferência
# ===========================================================================

timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")

output.print_md(u"# Fire Utils — Dimensionamento de Saídas de Emergência")
output.print_md(u"*Calculado em {}  ·  Estado: {}  ·  Térreo: {}*".format(
    timestamp, estado.get(u"nome", sigla_estado), nome_terreo
))
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

# Exibir distâncias aplicáveis no output (se configuradas)
if config_distancias:
    dist_cfg_e = estado.get(u"distancias_maximas", {})
    mapa_d   = dist_cfg_e.get(u"mapa_ocupacao", {})
    grupos_d = dist_cfg_e.get(u"grupos", {})
    ocup_p   = config_distancias[u"ocupacao_principal"]
    saida_k  = u"saida_unica"   if config_distancias[u"saida_unica"] else u"mais_saidas"
    chu_k    = u"com_chuveiro"  if config_distancias[u"chuveiro"]    else u"sem_chuveiro"
    det_k    = u"com_deteccao"  if config_distancias[u"deteccao"]    else u"sem_deteccao"
    nome_grupo = mapa_d.get(ocup_p)
    if nome_grupo and nome_grupo in grupos_d:
        cfg_g = grupos_d[nome_grupo]
        def _dv(pav):
            try:
                return cfg_g[pav][chu_k][saida_k][det_k]
            except (KeyError, TypeError):
                return u"N/A"
        output.print_md(u"### Distâncias máximas a percorrer")
        output.print_md(
            u"Ocupação: **{}** · {} · {} · {}".format(
                ocup_p,
                u"Saída única"  if config_distancias[u"saida_unica"] else u"2+ saídas",
                u"Com chuveiro" if config_distancias[u"chuveiro"]    else u"Sem chuveiro",
                u"Com detecção" if config_distancias[u"deteccao"]    else u"Sem detecção",
            )
        )
        output.print_md(u"| Piso de descarga | Demais pavimentos |")
        output.print_md(u"|---|---|")
        output.print_md(u"| **{} m** | **{} m** |".format(_dv(u"terreo"), _dv(u"demais")))
        output.print_md(u"")

output.print_md(u"---")
output.print_md(u"*Cache salvo. Use o botão **Gerar Memorial** para o relatório completo.*")

# ===========================================================================
# PASSO 7 — Montar se_import e salvar
# ===========================================================================

def _build_se_import():
    """Constrói o payload compacto se_import a partir dos dados coletados."""
    tabela = estado.get(u"tabela", {})

    # Atribuir IDs de pavimento relativos ao térreo
    terreo_idx = next(
        (i for i, n in enumerate(niveis_ordenados) if n.Name == nome_terreo), None
    )
    floor_ids = {}
    if terreo_idx is not None:
        for i in range(terreo_idx):
            floor_ids[niveis_ordenados[i].Name] = u"sub-{}".format(terreo_idx - i)
        floor_ids[nome_terreo] = u"P1"
        for i in range(terreo_idx + 1, len(niveis_ordenados)):
            floor_ids[niveis_ordenados[i].Name] = u"P{}".format(i - terreo_idx + 1)

    # Agrupar ambientes por nível mantendo ordem de elevação
    by_nivel = {}
    for room in rooms_data:
        by_nivel.setdefault(room[u"nivel"], []).append(room)

    nivel_nomes = [n.Name for n in niveis_ordenados if n.Name in by_nivel]

    pavimentos = []
    for nome_nivel in nivel_nomes:
        ambientes = []
        for room in by_nivel[nome_nivel]:
            divisao = room[u"grupo"]
            taxa_a  = tabela.get(divisao, {}).get(u"A")
            if taxa_a is not None and float(taxa_a) > 0:
                ambientes.append({u"nome": room[u"nome"], u"divisao": divisao,
                                   u"area": room[u"area"], u"popTipo": u"area"})
            else:
                ambientes.append({u"nome": room[u"nome"], u"divisao": divisao,
                                   u"area": room[u"area"], u"popTipo": u"manual",
                                   u"popManual": room[u"pop"]})
        pavimentos.append({
            u"id":        floor_ids.get(nome_nivel, u"P1"),
            u"nome":      nome_nivel,
            u"tipo":      u"descarga" if nome_nivel == nome_terreo else u"normal",
            u"ambientes": ambientes,
        })

    cd = config_distancias or {}
    return {
        u"_timestamp":   timestamp,
        u"uf":           sigla_estado,
        u"saida_unica":  bool(cd.get(u"saida_unica",  False)),
        u"temChuveiros": bool(cd.get(u"chuveiro",     False)),
        u"temDeteccao":  bool(cd.get(u"deteccao",     False)),
        u"pavimentos":   pavimentos,
    }


se_import = _build_se_import()
salvar_cache_se_import(se_import, projeto_dir)

