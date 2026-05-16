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

def _secao(numero, titulo, conteudo):
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

def _html_normativos():
    linhas = [
        [u"Norma de referência",       u"IT 11 — Saídas de Emergência"],
        [u"Unidade de Passagem (UP)",  u"<mono>1 UP = 0,55 m</mono>"],
        [u"Largura mín. — AD",         u"<mono>1,20 m</mono>"],
        [u"Largura mín. — ER",         u"<mono>1,20 m</mono>"],
        [u"Largura mín. — PT",         u"Conforme N° de UPs (0,80 / 1,00 / 1,50 / 2,00 m)"],
        [u"Capacidade por UP",         u"Menor valor entre as ocupações do pavimento (ver IT 11, Tabela 3)"],
        [u"ER — critério de projeto",  u"Pavimento de maior população, excluindo o térreo (IT 11)"],
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
    form = _formula(u"N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L = N × 0,55  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(L, 1,20 m)")
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
# RESUMO EXECUTIVO — cards
# ===========================================================================

def _html_resumo(res):
    def _row(label, valor, unidade=u""):
        return u"""<div class="resumo-row">
            <span class="resumo-row-label">{label}</span>
            <span class="resumo-row-valor">{valor}<span class="unidade"> {unidade}</span></span>
        </div>""".format(label=label, valor=valor, unidade=unidade)

    def _card(tag, titulo, corpo):
        return u"""<div class="resumo-card">
            <div class="resumo-card-header">
                <span class="tag">{tag}</span>{titulo}
            </div>
            <div class="resumo-card-body">{corpo}</div>
        </div>""".format(tag=tag, titulo=titulo, corpo=corpo)

    def _linha(rotulo, cards_html):
        return u"""
        <div class="resumo-linha">
            <div class="resumo-linha-label">{rotulo}</div>
            <div class="resumo-grid">{cards}</div>
        </div>""".format(rotulo=rotulo, cards=cards_html)

    # --- Linha AD ---
    cards_ad = u""
    for nd in res[u"ad"]:
        corpo = (
            _row(u"População", u"{}".format(nd[u"pop"]), u"pessoas") +
            _row(u"N° UPs", u"{}".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—") +
            u'<hr class="resumo-divider">' +
            _row(u"Largura adotada",
                 u"{:.2f}".format(nd[u"largura_adotada"]) if nd[u"largura_adotada"] else u"—",
                 u"m")
        )
        cards_ad += _card(nd[u"nivel"], u"", corpo)

    # --- Linha PT ---
    cards_pt = u""
    for nd in res[u"pt"]:
        tipo = u" ({})".format(nd[u"tipo_porta"]) if nd.get(u"tipo_porta") else u""
        corpo = (
            _row(u"População", u"{}".format(nd[u"pop"]), u"pessoas") +
            _row(u"N° UPs", u"{}".format(nd[u"n_up"]) if nd[u"n_up"] is not None else u"—") +
            u'<hr class="resumo-divider">' +
            _row(u"Largura adotada",
                 u"{:.2f}".format(nd[u"largura_adotada"]) if nd[u"largura_adotada"] else u"—",
                 u"m{}".format(tipo))
        )
        cards_pt += _card(nd[u"nivel"], u"", corpo)

    # --- Linha ER ---
    er = res[u"er"]
    corpo_er = (
        _row(u"Pavimento", er[u"nivel"]) +
        _row(u"População", u"{}".format(er[u"pop"]), u"pessoas") +
        _row(u"N° UPs", u"{}".format(er[u"n_up"]) if er[u"n_up"] is not None else u"—") +
        u'<hr class="resumo-divider">' +
        _row(u"Largura adotada",
             u"{:.2f}".format(er[u"largura_adotada"]) if er[u"largura_adotada"] else u"—",
             u"m")
    )
    cards_er = _card(er[u"nivel"], u"", corpo_er)

    return (
        _linha(u"AD — Acessos e Descargas", cards_ad) +
        _linha(u"PT — Portas",              cards_pt) +
        _linha(u"ER — Escadas e Rampas",    cards_er)
    )


# ===========================================================================
# ENTRADA PRINCIPAL
# ===========================================================================

def build_corpo_saidas(res, rooms_data, nome_terreo, timestamp=None):
    """Retorna o HTML do corpo do memorial de saídas (sem wrapper <html> nem rodapé)."""
    if not timestamp:
        timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")

    tem_multiplos = res.get(u"tem_multiplos_pavimentos", False)

    s1 = _html_normativos()
    s2 = _html_ambientes(rooms_data)
    s3 = _html_ad(res[u"ad"])
    s4 = _html_er(res[u"er"], tem_multiplos)
    s5 = _html_pt(res[u"pt"])
    sr = _html_resumo(res)

    return u"""
    <div class="cabecalho">
        <div class="cab-sub">
            <div class="cab-meta">
                <span class="cab-meta-label">Norma</span>
                <span>IT 11</span>
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
    """.format(
        terreo   = nome_terreo,
        n_niveis = len(res[u"ad"]),
        data     = timestamp,
        res_exec = _secao(u"↗", u"Resumo Executivo", sr),
        s1       = _secao(u"1", u"Dados Normativos e Critérios", s1),
        s2       = _secao(u"2", u"Ambientes Identificados", s2),
        s3       = _secao(u"3", u"Acessos e Descargas (AD)", s3),
        s4       = _secao(u"4", u"Escadas e Rampas (ER)", s4),
        s5       = _secao(u"5", u"Portas (PT)", s5),
    )


