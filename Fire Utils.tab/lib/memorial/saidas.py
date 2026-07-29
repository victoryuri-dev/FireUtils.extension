# -*- coding: utf-8 -*-
"""
memorial/saidas.py — Fire Utils
Funções de geração do corpo HTML do memorial de saídas de emergência.

API pública:
    build_corpo_saidas() — retorna HTML do corpo (sem wrapper <html>)
"""

import datetime

from memorial.hidrantes import CSS


# ===========================================================================
# HELPERS
# ===========================================================================

def _badge_ok(texto):
    return u'<span class="badge badge-ok">{}</span>'.format(texto)

def _badge_warn(texto):
    return u'<span class="badge badge-warn">{}</span>'.format(texto)

def _secao(numero, titulo, conteudo, colapsavel=False):
    if colapsavel:
        return u"""
    <section class="secao">
        <details>
            <summary class="secao-header secao-header-details">
                <span class="secao-num">{num}</span>
                <h2 class="secao-titulo">{titulo}</h2>
                <span class="secao-chevron">&#9660;</span>
            </summary>
            <div class="secao-corpo">
                {conteudo}
            </div>
        </details>
    </section>""".format(num=numero, titulo=titulo, conteudo=conteudo)
    return u"""
    <section class="secao">
        <div class="secao-header">
            <span class="secao-num">{num}</span>
            <h2 class="secao-titulo">{titulo}</h2>
        </div>
        <div class="secao-corpo">
            {conteudo}
        </div>
    </section>""".format(num=numero, titulo=titulo, conteudo=conteudo)


def _tabela(cabecalho, linhas, classes=u""):
    ths = u"".join(u"<th>{}</th>".format(h) for h in cabecalho)
    trs = u"".join(
        u"<tr>{}</tr>".format(u"".join(u"<td>{}</td>".format(c) for c in linha))
        for linha in linhas
    )
    return u"""
    <table class="tabela {cls}">
        <thead><tr>{ths}</tr></thead>
        <tbody>{trs}</tbody>
    </table>""".format(cls=classes, ths=ths, trs=trs)


def _formula(texto):
    return u'<div class="formula">{}</div>'.format(texto)


def _nota(texto):
    return u'<p class="nota">{}</p>'.format(texto)


# ===========================================================================
# SEÇÃO 1 — Dados normativos
# ===========================================================================

def _html_normativos(estado=None):
    if estado:
        norma    = u"{} — {}".format(estado.get(u"norma_saidas", u"NT local"), estado.get(u"corpo", u""))
        lm       = estado.get(u"larguras_minimas", {})
        larg_ad  = u"<mono>{:.2f} m</mono>".format(lm.get(u"AD", 1.20))
        larg_er  = u"<mono>{:.2f} m</mono>".format(lm.get(u"ER", 1.20))
        pt_vals  = lm.get(u"PT", [])
        if pt_vals:
            pt_str = u" / ".join(
                u"{:.2f} m".format(e[u"largura"]) for e in sorted(pt_vals, key=lambda e: e[u"n_up"])
            )
            larg_pt = u"Conforme N° de UPs ({})".format(pt_str)
        else:
            larg_pt = u"Conforme N° de UPs"
    else:
        norma   = u"IT 11 CBMSP — Saídas de Emergência"
        larg_ad = u"<mono>1,20 m</mono>"
        larg_er = u"<mono>1,20 m</mono>"
        larg_pt = u"Conforme N° de UPs (0,80 / 1,00 / 1,50 / 2,00 m)"

    linhas = [
        [u"Norma de referência",       norma],
        [u"Unidade de Passagem (UP)",  u"<mono>1 UP = 0,55 m</mono>"],
        [u"Largura mín. — AD",         larg_ad],
        [u"Largura mín. — ER",         larg_er],
        [u"Largura mín. — PT",         larg_pt],
        [u"Capacidade por UP",         u"Menor valor entre as ocupações do pavimento"],
        [u"ER — critério de projeto",  u"Pavimento de maior população, excluindo o térreo"],
    ]
    return _tabela([u"Parâmetro", u"Valor / Referência"], linhas)


# ===========================================================================
# SEÇÃO 2 — Ambientes identificados
# ===========================================================================

def _html_ambientes(rooms_data):
    linhas = sorted(
        rooms_data,
        key=lambda r: (r.get(u"nivel", u""), r.get(u"nome", u""))
    )
    rows = []
    for r in linhas:
        rows.append([
            r.get(u"nivel", u"—"),
            u"<strong>{}</strong>".format(r.get(u"nome", u"—")),
            u"<mono>{}</mono>".format(r.get(u"grupo", u"—")),
            u"<mono>{:.0f} m²</mono>".format(r.get(u"area", 0.0)),
            u"<mono><strong>{}</strong></mono>".format(r.get(u"pop", 0)),
        ])
    return _tabela(
        [u"Nível", u"Ambiente", u"Ocupação", u"Área", u"Pop."],
        rows
    )


# ===========================================================================
# SEÇÃO 3 — Acessos e Descargas
# ===========================================================================

def _html_ad(ad_list):
    linhas = []
    for nd in ad_list:
        cap = u"<mono>{}</mono>".format(nd[u"cap"]) if nd[u"cap"] else u"—"
        n   = u"<mono>{} UP</mono>".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—"
        lc  = u"<mono>{:.2f} m</mono>".format(nd[u"largura_calc"]) if nd[u"largura_calc"] else u"—"
        lm  = u"<mono>{:.2f} m</mono>".format(nd[u"largura_min"])  if nd[u"largura_min"]  else u"—"
        la  = _badge_ok(u"{:.2f} m".format(nd[u"largura_adotada"])) if nd[u"largura_adotada"] else u"—"
        linhas.append([
            u"<strong>{}</strong>".format(nd[u"nivel"]),
            u"<mono>{}</mono>".format(nd[u"pop"]),
            cap, n, lc, lm, la,
        ])

    tab = _tabela(
        [u"Pavimento", u"Pop.", u"Cap./UP", u"N° UPs",
         u"L calculada", u"L mínima", u"L adotada"],
        linhas
    )
    form = _formula(u"N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L = N × 0,55  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(L, L<sub>mín</sub>)")
    return form + tab


# ===========================================================================
# SEÇÃO 4 — Escadas e Rampas
# ===========================================================================

def _html_er(er, tem_multiplos):
    nota_criterio = (
        u"Critério: pavimento de maior população excluindo o térreo (IT 11)."
        if tem_multiplos
        else u"Edifício com pavimento único."
    )
    cap = u"<mono>{}</mono>".format(er[u"cap"]) if er[u"cap"] else u"—"
    n   = u"<mono>{} UP</mono>".format(er[u"n_up"]) if er[u"n_up"] is not None else u"—"
    lc  = u"<mono>{:.2f} m</mono>".format(er[u"largura_calc"]) if er[u"largura_calc"] else u"—"
    lm  = u"<mono>{:.2f} m</mono>".format(er[u"largura_min"])  if er[u"largura_min"]  else u"—"
    la  = _badge_ok(u"{:.2f} m".format(er[u"largura_adotada"])) if er[u"largura_adotada"] else u"—"

    tab = _tabela(
        [u"Pavimento governante", u"Pop.", u"Cap./UP", u"N° UPs",
         u"L calculada", u"L mínima", u"L adotada"],
        [[
            u"<strong>{}</strong>".format(er[u"nivel"]),
            u"<mono>{}</mono>".format(er[u"pop"]),
            cap, n, lc, lm, la,
        ]]
    )
    lm_er = er.get(u"largura_min", 1.20) or 1.20
    form = _formula(
        u"N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L = N × 0,55  &nbsp;·&nbsp;  "
        u"L<sub>adotada</sub> = max(L, {:.2f} m)".format(lm_er)
    )
    return _nota(nota_criterio) + form + tab


# ===========================================================================
# SEÇÃO 5 — Portas
# ===========================================================================

def _html_pt(pt_list):
    linhas = []
    for nd in pt_list:
        cap  = u"<mono>{}</mono>".format(nd[u"cap"]) if nd[u"cap"] else u"—"
        n    = u"<mono>{} UP</mono>".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—"
        lc   = u"<mono>{:.2f} m</mono>".format(nd[u"largura_calc"]) if nd[u"largura_calc"] else u"—"
        lm   = u"<mono>{:.2f} m</mono>".format(nd[u"largura_min"])  if nd[u"largura_min"]  else u"—"
        tipo = nd.get(u"tipo_porta", u"—") or u"—"
        la   = _badge_ok(u"{:.2f} m".format(nd[u"largura_adotada"])) if nd[u"largura_adotada"] else u"—"
        linhas.append([
            u"<strong>{}</strong>".format(nd[u"nivel"]),
            u"<mono>{}</mono>".format(nd[u"pop"]),
            cap, n, lc, lm, tipo, la,
        ])

    tab = _tabela(
        [u"Pavimento", u"Pop.", u"Cap./UP", u"N° UPs",
         u"L calculada", u"L mínima", u"Tipo", u"L adotada"],
        linhas
    )
    form = _formula(u"N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(N × 0,55, L<sub>mín por UPs</sub>)")
    return form + tab


# ===========================================================================
# SEÇÃO 6 — Distâncias máximas a percorrer
# ===========================================================================

def _html_distancias(rooms_data, estado, config_distancias=None):
    """
    Gera a seção de distâncias máximas a percorrer.

    config_distancias : dict { ocupacao_principal, saida_unica, chuveiro, deteccao }
                        coletado pelo formulário de dimensionamento.
                        Se fornecido, exibe card de resumo com as distâncias
                        aplicáveis à edificação em destaque.

    Retorna None se o estado não tiver distancias_maximas.
    """
    if not estado:
        return None

    dist_cfg = estado.get(u"distancias_maximas")
    if not dist_cfg:
        return None

    mapa   = dist_cfg.get(u"mapa_ocupacao", {})
    grupos = dist_cfg.get(u"grupos", {})

    if not mapa or not grupos:
        return None

    html = u""

    # ------------------------------------------------------------------
    # Card de resumo: distâncias aplicáveis à edificação
    # ------------------------------------------------------------------
    if config_distancias:
        ocup_p  = config_distancias.get(u"ocupacao_principal", u"")
        s_unica = config_distancias.get(u"saida_unica",  False)
        chu     = config_distancias.get(u"chuveiro",     False)
        det     = config_distancias.get(u"deteccao",     False)

        saida_k = u"saida_unica"  if s_unica else u"mais_saidas"
        chu_k   = u"com_chuveiro" if chu     else u"sem_chuveiro"
        det_k   = u"com_deteccao" if det     else u"sem_deteccao"

        nome_grupo_p = mapa.get(ocup_p)

        def _lookup_dist(tipo_pav):
            if not nome_grupo_p:
                return None
            cfg = grupos.get(nome_grupo_p, {})
            try:
                return cfg[tipo_pav][chu_k][saida_k][det_k]
            except (KeyError, TypeError):
                return None

        dist_terreo = _lookup_dist(u"terreo")
        dist_demais = _lookup_dist(u"demais")

        tag_saida = u"Saída única"    if s_unica else u"2 ou mais saídas"
        tag_chu   = u"Com chuveiro"   if chu     else u"Sem chuveiro"
        tag_det   = u"Com detecção"   if det     else u"Sem detecção"

        def _dist_val(v):
            return u"<span class='dist-val'>{} m</span>".format(v) if v is not None \
                   else u"<span class='dist-val dist-na'>N/A</span>"

        html += u"""
        <div class="dist-resumo-card">
            <div class="dist-resumo-header">
                <span class="tag">{ocup}</span>
                <span class="dist-resumo-tags">
                    <span class="dist-tag">{saida}</span>
                    <span class="dist-tag">{chu}</span>
                    <span class="dist-tag">{det}</span>
                </span>
            </div>
            <div class="dist-resumo-valores">
                <div class="dist-resumo-col">
                    <div class="dist-resumo-label">Piso de descarga</div>
                    {vt}
                </div>
                <div class="dist-resumo-col">
                    <div class="dist-resumo-label">Demais pavimentos</div>
                    {vd}
                </div>
            </div>
        </div>""".format(
            ocup  = ocup_p,
            saida = tag_saida,
            chu   = tag_chu,
            det   = tag_det,
            vt    = _dist_val(dist_terreo),
            vd    = _dist_val(dist_demais),
        )

    # ------------------------------------------------------------------
    # Tabela de referência — apenas do grupo da ocupação principal
    # ------------------------------------------------------------------

    # Quando config_distancias existe → só mostra o grupo da ocup. principal
    # Quando não existe (cache antigo) → mostra todos os grupos do modelo
    if config_distancias:
        ocup_principal = config_distancias.get(u"ocupacao_principal", u"")
        nome_grupo_ref = mapa.get(ocup_principal)
        grupos_exibir  = [nome_grupo_ref] if (nome_grupo_ref and nome_grupo_ref in grupos) else []
    else:
        codigos_presentes = set(r.get(u"grupo", u"") for r in rooms_data)
        codigos_presentes.discard(u"")
        grupos_exibir = []
        for codigo in sorted(codigos_presentes):
            ng = mapa.get(codigo)
            if ng and ng in grupos and ng not in grupos_exibir:
                grupos_exibir.append(ng)

    # Parâmetros para realçe da célula aplicável
    _hl_saida = None
    _hl_chu   = None
    _hl_det   = None
    if config_distancias:
        _hl_saida = u"saida_unica"  if config_distancias.get(u"saida_unica") else u"mais_saidas"
        _hl_chu   = u"com_chuveiro" if config_distancias.get(u"chuveiro")    else u"sem_chuveiro"
        _hl_det   = u"com_deteccao" if config_distancias.get(u"deteccao")    else u"sem_deteccao"

    cols_cfg = [
        (u"sem_chuveiro", u"sem_deteccao"),
        (u"sem_chuveiro", u"com_deteccao"),
        (u"com_chuveiro", u"sem_deteccao"),
        (u"com_chuveiro", u"com_deteccao"),
    ]
    cab = [
        u"Pavimento", u"N° saídas",
        u"Sem chuveiro<br><small>Sem detecção</small>",
        u"Sem chuveiro<br><small>Com detecção</small>",
        u"Com chuveiro<br><small>Sem detecção</small>",
        u"Com chuveiro<br><small>Com detecção</small>",
    ]

    if grupos_exibir:
        html += u'<p class="resumo-tipo-label" style="margin-top:18px">Tabela de referência</p>'

    for nome_grupo in grupos_exibir:
        cfg_grupo = grupos[nome_grupo]
        descricao = cfg_grupo.get(u"descricao", nome_grupo)

        html += u"""
        <div class="dist-grupo">
            <div class="dist-grupo-header">
                <span class="tag">{nome}</span>
                <span class="dist-grupo-desc">{desc}</span>
            </div>
        """.format(nome=nome_grupo, desc=descricao)

        linhas_tab = []
        for tipo_pav in (u"terreo", u"demais"):
            label_pav = u"Térreo" if tipo_pav == u"terreo" else u"Demais"
            pav_data  = cfg_grupo.get(tipo_pav, {})

            for tipo_saida, label_saida in (
                (u"saida_unica", u"Saída única"),
                (u"mais_saidas", u"2 ou mais"),
            ):
                linha_hl = (_hl_saida is not None) and (tipo_saida == _hl_saida)
                cells = [
                    u"<strong>{}</strong>".format(label_pav),
                    u"<em>{}</em>".format(label_saida) if linha_hl else label_saida,
                ]
                for chu_k, det_k in cols_cfg:
                    col_hl = linha_hl and (chu_k == _hl_chu) and (det_k == _hl_det)
                    try:
                        v   = pav_data[chu_k][tipo_saida][det_k]
                        txt = u"{} m".format(v) if v is not None else u"—"
                    except (KeyError, TypeError):
                        txt = u"—"
                    if col_hl:
                        cells.append(u"<span class='dist-hl'>{}</span>".format(txt))
                    else:
                        cells.append(u"<mono>{}</mono>".format(txt))
                linhas_tab.append(cells)

        html += _tabela(cab, linhas_tab, classes=u"dist-tabela")
        html += u"</div>"

    return html


# ===========================================================================
# RESUMO EXECUTIVO — tabelas compactas
# ===========================================================================

def _html_ocupacoes_presentes(rooms_data, estado=None):
    """Tabela compacta: ocupações identificadas + população total por código."""
    dados = {}   # { codigo: { n_amb, pop } }
    for r in rooms_data:
        g = r.get(u"grupo", u"") or u""
        if not g:
            continue
        if g not in dados:
            dados[g] = {u"n_amb": 0, u"pop": 0}
        dados[g][u"n_amb"] += 1
        dados[g][u"pop"]   += r.get(u"pop", 0)

    if not dados:
        return u""

    ocups_dict = estado.get(u"ocupacoes", {}) if estado else {}
    total_pop  = sum(d[u"pop"] for d in dados.values())

    linhas = []
    for g in sorted(dados.keys()):
        d    = dados[g]
        desc = ocups_dict.get(g, {}).get(u"descricao", u"—") or u"—"
        linhas.append([
            u"<mono><strong>{}</strong></mono>".format(g),
            desc,
            u"<mono>{}</mono>".format(d[u"n_amb"]),
            u"<mono>{}</mono>".format(d[u"pop"]),
        ])

    linhas.append([
        u"<strong>Total</strong>",
        u"",
        u"",
        u"<mono><strong>{}</strong></mono>".format(total_pop),
    ])

    return (
        u'<p class="resumo-tipo-label">Ocupações Presentes</p>' +
        _tabela(
            [u"Código", u"Descrição", u"Ambientes", u"Pop. total"],
            linhas, classes=u"resumo-tab resumo-tab-ocup"
        )
    )


def _html_resumo_distancias(estado, config_distancias):
    """
    Mini-card de distâncias máximas para o resumo executivo.
    Reutiliza as classes CSS dist-resumo-* já existentes.
    Retorna string vazia se não houver dados.
    """
    if not estado or not config_distancias:
        return u""

    dist_cfg = estado.get(u"distancias_maximas")
    if not dist_cfg:
        return u""

    mapa   = dist_cfg.get(u"mapa_ocupacao", {})
    grupos = dist_cfg.get(u"grupos", {})

    ocup_p  = config_distancias.get(u"ocupacao_principal", u"")
    s_unica = config_distancias.get(u"saida_unica",  False)
    chu     = config_distancias.get(u"chuveiro",     False)
    det     = config_distancias.get(u"deteccao",     False)

    saida_k = u"saida_unica"  if s_unica else u"mais_saidas"
    chu_k   = u"com_chuveiro" if chu     else u"sem_chuveiro"
    det_k   = u"com_deteccao" if det     else u"sem_deteccao"

    nome_grupo = mapa.get(ocup_p)
    if not nome_grupo or nome_grupo not in grupos:
        return u""

    cfg = grupos[nome_grupo]

    def _dv(tipo_pav):
        try:
            v = cfg[tipo_pav][chu_k][saida_k][det_k]
            return u"{} m".format(v) if v is not None else u"N/A"
        except (KeyError, TypeError):
            return u"N/A"

    tag_saida = u"Saída única"  if s_unica else u"2 ou mais saídas"
    tag_chu   = u"Com chuveiro" if chu     else u"Sem chuveiro"
    tag_det   = u"Com detecção" if det     else u"Sem detecção"

    vt = _dv(u"terreo")
    vd = _dv(u"demais")

    cls_vt = u"dist-val" if vt != u"N/A" else u"dist-val dist-na"
    cls_vd = u"dist-val" if vd != u"N/A" else u"dist-val dist-na"

    return u"""
    <p class="resumo-tipo-label">Distâncias Máximas a Percorrer</p>
    <div class="dist-resumo-card">
        <div class="dist-resumo-header">
            <span class="tag">{ocup}</span>
            <span class="dist-resumo-tags">
                <span class="dist-tag">{saida}</span>
                <span class="dist-tag">{chu}</span>
                <span class="dist-tag">{det}</span>
            </span>
        </div>
        <div class="dist-resumo-valores">
            <div class="dist-resumo-col">
                <div class="dist-resumo-label">Piso de descarga</div>
                <span class="{cls_vt}">{vt}</span>
            </div>
            <div class="dist-resumo-col">
                <div class="dist-resumo-label">Demais pavimentos</div>
                <span class="{cls_vd}">{vd}</span>
            </div>
        </div>
    </div>""".format(
        ocup=ocup_p, saida=tag_saida, chu=tag_chu, det=tag_det,
        vt=vt, vd=vd, cls_vt=cls_vt, cls_vd=cls_vd,
    )


def _html_resumo(res, rooms_data=None, estado=None, config_distancias=None):
    """Resumo executivo compacto.

    Ordem:
      1. Ocupações Presentes (com pop. total por código)
      2. AD — Acessos e Descargas
      3. ER — Escadas e Rampas
      4. PT — Portas
      5. Distâncias Máximas a Percorrer
    """
    cab = [u"Pavimento", u"População", u"N° UPs", u"Largura adotada"]

    # --- AD ---
    linhas_ad = []
    for nd in res[u"ad"]:
        n_up = u"{} UP".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—"
        la   = _badge_ok(u"{:.2f} m".format(nd[u"largura_adotada"])) if nd[u"largura_adotada"] else u"—"
        linhas_ad.append([
            u"<strong>{}</strong>".format(nd[u"nivel"]),
            u"<mono>{} pess.</mono>".format(nd[u"pop"]),
            u"<mono>{}</mono>".format(n_up),
            la,
        ])

    # --- ER ---
    er = res[u"er"]
    n_up_er = u"{} UP".format(er[u"n_up"]) if er[u"n_up"] is not None else u"—"
    linhas_er = [[
        u"<strong>{}</strong>".format(er[u"nivel"]),
        u"<mono>{} pess.</mono>".format(er[u"pop"]),
        u"<mono>{}</mono>".format(n_up_er),
        _badge_ok(u"{:.2f} m".format(er[u"largura_adotada"])) if er[u"largura_adotada"] else u"—",
    ]]

    # --- PT ---
    linhas_pt = []
    for nd in res[u"pt"]:
        n_up = u"{} UP".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—"
        tipo = u" ({})".format(nd[u"tipo_porta"]) if nd.get(u"tipo_porta") else u""
        la   = _badge_ok(u"{:.2f} m{}".format(nd[u"largura_adotada"], tipo)) if nd[u"largura_adotada"] else u"—"
        linhas_pt.append([
            u"<strong>{}</strong>".format(nd[u"nivel"]),
            u"<mono>{} pess.</mono>".format(nd[u"pop"]),
            u"<mono>{}</mono>".format(n_up),
            la,
        ])

    html = u""

    # 1 — Ocupações presentes (com população)
    if rooms_data:
        html += _html_ocupacoes_presentes(rooms_data, estado=estado)

    # 2 / 3 / 4 — Dimensionamento
    html += u'<p class="resumo-tipo-label">AD — Acessos e Descargas</p>'
    html += _tabela(cab, linhas_ad, classes=u"resumo-tab")

    html += u'<p class="resumo-tipo-label">ER — Escadas e Rampas</p>'
    html += _tabela(cab, linhas_er, classes=u"resumo-tab")

    html += u'<p class="resumo-tipo-label">PT — Portas</p>'
    html += _tabela(cab, linhas_pt, classes=u"resumo-tab")

    # 5 — Distâncias máximas
    html += _html_resumo_distancias(estado, config_distancias)

    return html


# ===========================================================================
# ENTRADA PRINCIPAL
# ===========================================================================

def build_corpo_saidas(res, rooms_data, nome_terreo, timestamp=None,
                       estado=None, config_distancias=None):
    """Retorna o HTML do corpo do memorial de saídas (sem wrapper <html> nem rodapé).

    estado             : dict do estado (estados.get_estado)
    config_distancias  : dict { ocupacao_principal, saida_unica, chuveiro, deteccao }
                         coletado pelo formulário de dimensionamento; opcional.
    """
    if not timestamp:
        timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")

    tem_multiplos = res.get(u"tem_multiplos_pavimentos", False)

    s1 = _html_normativos(estado=estado)
    s2 = _html_ambientes(rooms_data)
    s3 = _html_ad(res[u"ad"])
    s4 = _html_er(res[u"er"], tem_multiplos)
    s5 = _html_pt(res[u"pt"])
    s6 = _html_distancias(rooms_data, estado, config_distancias=config_distancias)
    sr = _html_resumo(res, rooms_data=rooms_data, estado=estado,
                      config_distancias=config_distancias)

    norma_ref = u"IT 11"
    corpo_str = u""
    if estado:
        norma_ref = estado.get(u"norma_saidas", u"NT local")
        corpo_str = u" — {}".format(estado.get(u"corpo", u""))

    # Seção 6 só aparece se o estado tiver tabela de distâncias
    bloco_s6 = u""
    if s6:
        bloco_s6 = _secao(u"6", u"Distâncias Máximas a Percorrer", s6)

    return u"""
    <div class="cabecalho">
        <div class="cab-sub">
            <div class="cab-meta">
                <span class="cab-meta-label">Norma</span>
                <span>{norma}{corpo}</span>
            </div>
            <div class="cab-meta">
                <span class="cab-meta-label">Pavimentos</span>
                <span>{n_niveis}</span>
            </div>
        </div>
    </div>

    {res_exec}
    {s1}
    {s2}
    {s3}
    {s4}
    {s5}
    {s6}
    """.format(
        norma    = norma_ref,
        corpo    = corpo_str,
        terreo   = nome_terreo,
        n_niveis = len(res[u"ad"]),
        data     = timestamp,
        res_exec = _secao(u"↗", u"Resumo Executivo", sr),
        s1       = _secao(u"1", u"Dados Normativos e Critérios", s1),
        s2       = _secao(u"2", u"Ambientes Identificados", s2, colapsavel=True),
        s3       = _secao(u"3", u"Acessos e Descargas (AD)", s3),
        s4       = _secao(u"4", u"Escadas e Rampas (ER)", s4),
        s5       = _secao(u"5", u"Portas (PT)", s5),
        s6       = bloco_s6,
    )


