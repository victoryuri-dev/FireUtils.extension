# -*- coding: utf-8 -*-
"""
memorial/hidrantes.py — Fire Utils
Funções de geração do corpo HTML do memorial de hidrantes.

API pública:
    CSS                    — string CSS compartilhada com saidas.py e geral.py
    build_corpo_hidrantes() — retorna HTML do corpo (sem wrapper <html>)
"""

import datetime


def _status_badge(valor, minimo, maximo=None):
    if valor < minimo:
        return u'<span class="badge badge-err">ABAIXO DO MÍNIMO</span>'
    if maximo and valor > maximo:
        return u'<span class="badge badge-err">ACIMA DO MÁXIMO</span>'
    return u'<span class="badge badge-ok">ATENDE</span>'

def _vel_badge(v):
    if v <= 3.0:
        return u'<span class="badge badge-ok">✓ {:.3f} m/s</span>'.format(v)
    return u'<span class="badge badge-err">⚠ {:.3f} m/s</span>'.format(v)

def _cond_badge(hz):
    if hz < -0.05:
        return u'<span class="badge badge-warn">Hidrante acima da RTI</span>'
    if hz > 0.05:
        return u'<span class="badge badge-ok">Hidrante abaixo da RTI</span>'
    return u'<span class="badge badge-ok">Mesmo nível da RTI</span>'


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


def _tabela(cabecalho, linhas, classes=""):
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


def _card_metrica(label, valor, unidade=""):
    return u"""<div class="card-metrica">
        <div class="card-label">{label}</div>
        <div class="card-valor">{valor}<span class="card-unidade"> {unidade}</span></div>
    </div>""".format(label=label, valor=valor, unidade=unidade)


def _html_secao_dados(dados_sistema, valor_sistema, calculo_escolha,
                      Qs_lmin, Qs_m3s, Qt_lmin, Qt_m3s, Pmin, C):
    linhas = [
        [u"Classificação", u"<strong>{}</strong>".format(valor_sistema), u"NT 22 CBMMA"],
        [u"Método de cálculo", u"<strong>{}</strong>".format(calculo_escolha), u"—"],
        [u"Vazão mínima (Qmin)", u"<strong>{} L/min = {:.4f} m³/s</strong>".format(Qs_lmin, Qs_m3s), u"NT 22"],
        [u"Vazão total (Qt)", u"<strong>{} L/min = {:.4f} m³/s</strong>".format(Qt_lmin, Qt_m3s), u"2 hidrantes simultâneos"],
        [u"Pressão mínima (Pmin)", u"<strong>{} mca</strong>".format(Pmin), u"NT 22"],
        [u"Pressão máxima", u"<strong>100 mca</strong>", u"NT 22"],
        [u"Coef. Hazen-Williams (C)", u"<strong>{}</strong>".format(C), u"Aço / Ferro galvanizado"],
        [u"Velocidade máxima", u"<strong>3,0 m/s</strong>", u"NBR 13714"],
    ]
    return _tabela([u"Parâmetro", u"Valor", u"Referência"], linhas)


def _html_secao_elevacoes(Z_RTI, Z_HID01, Z_HID02, Hz_H1, Hz_H2):
    rows_cotas = [
        [u"RTI",    u"<mono>{:.4f} m</mono>".format(Z_RTI)],
        [u"HID-01", u"<mono>{:.4f} m</mono>".format(Z_HID01)],
        [u"HID-02", u"<mono>{:.4f} m</mono>".format(Z_HID02)],
    ]
    tab_cotas = _tabela([u"Ponto", u"Cota Z (m)"], rows_cotas)

    rows_desn = [
        [u"RTI → HID-01", u"<mono>{:.4f}</mono>".format(Hz_H1), _cond_badge(Hz_H1)],
        [u"RTI → HID-02", u"<mono>{:.4f}</mono>".format(Hz_H2), _cond_badge(Hz_H2)],
    ]
    tab_desn = _tabela([u"Percurso", u"ΔZ (m)", u"Condição"], rows_desn)

    nota = (u'<p class="nota">ΔZ = Z<sub>RTI</sub> − Z<sub>válvula</sub>. '
            u'Negativo indica hidrante <strong>acima</strong> da RTI — '
            u'a bomba precisa vencer essa altura.</p>')
    return tab_cotas + u"<br>" + tab_desn + nota


def _html_trecho(t, C, idx):
    v_badge = _vel_badge(t["V"])

    # Tabela de dados gerais
    tab_dados = _tabela(
        [u"Item", u"Valor"],
        [
            [u"Comprimento real (L)", u"<mono>{:.4f} m</mono>".format(t["L"])],
            [u"Diâmetro interno médio (D)", u"<mono>{:.1f} mm ({:.4f} m)</mono>".format(t["D"]*1000, t["D"])],
            [u"Vazão no trecho (Q)", u"<mono>{:.2f} L/min ({:.4f} m³/s)</mono>".format(t["Q_lmin"], t["Q_m3s"])],
            [u"Velocidade (V = Q/A)", v_badge],
        ]
    )

    # Tabela de acessórios
    if t["acessorios"]:
        linhas_aces = [
            [
                u"<mono><strong>{}</strong></mono>".format(ace["qtd"]),
                ace["nome"],
                u"<mono>{:.4f}</mono>".format(ace["leq_unit"]),
                u"<mono>{:.4f}</mono>".format(ace["leq_tot"]),
            ]
            for ace in t["acessorios"]
        ]
        linhas_aces.append([
            u"—", u"<strong>Total</strong>", u"—",
            u"<mono><strong>{:.4f} m</strong></mono>".format(t["Leq"])
        ])
        tab_aces = u'<p class="sub-titulo">Acessórios ({} tipo(s)):</p>'.format(t["n_aces"])
        tab_aces += _tabela(
            [u"Qtd", u"Descrição", u"Le unit. (m)", u"Σ Le (m)"],
            linhas_aces,
            classes="tabela-aces"
        )
    else:
        tab_aces = u'<p class="nota">Nenhum acessório registrado neste trecho.</p>'

    formula = _formula(
        u"hf = 10,643 × {Lt:.4f} × {Q:.4f}<sup>1,852</sup> / "
        u"({C}<sup>1,852</sup> × {D:.4f}<sup>4,871</sup>) = "
        u"<strong>{Hf:.4f} mca</strong>".format(
            Lt=t["Lt"], Q=t["Q_m3s"], C=C, D=t["D"], Hf=t["Hf"])
    )

    lt_eq = _formula(
        u"Lt = L + Σ Le = {:.4f} + {:.4f} = <strong>{:.4f} m</strong>".format(
            t["L"], t["Leq"], t["Lt"])
    )

    return u"""
    <div class="trecho-card">
        <div class="trecho-header">
            <span class="trecho-num">T{idx}</span>
            <span class="trecho-label">{label}</span>
        </div>
        {tab_dados}
        {tab_aces}
        {lt_eq}
        {formula}
    </div>""".format(
        idx=idx, label=t["label"],
        tab_dados=tab_dados, tab_aces=tab_aces,
        lt_eq=lt_eq, formula=formula
    )


def _html_secao_trechos(hf, C):
    cards = u"".join(
        _html_trecho(hf[key], C, idx)
        for idx, key in enumerate(["t1","t2","t3","t4"], 1)
    )

    # Tabela resumo
    linhas_res = []
    for key in ["t1","t2","t3","t4"]:
        t = hf[key]
        v_b = _vel_badge(t["V"])
        linhas_res.append([
            t["label"],
            u"<mono>{:.2f}</mono>".format(t["Q_lmin"]),
            u"<mono>{:.1f}</mono>".format(t["D"]*1000),
            u"<mono>{:.4f}</mono>".format(t["Lt"]),
            v_b,
            u"<mono><strong>{:.4f}</strong></mono>".format(t["Hf"]),
        ])
    tab_res = u'<h3 class="sub-secao">Resumo dos Trechos</h3>'
    tab_res += _tabela(
        [u"Trecho", u"Q (L/min)", u"D (mm)", u"Lt (m)", u"V (m/s)", u"hf (mca)"],
        linhas_res
    )

    return cards + tab_res


def _html_secao_hmt(res, Hm_mangueira, Hesg, Pmin):
    hz = res["Hz_governa"]
    if hz > 0.05:
        hz_desc = u"RTI acima do hidrante — favorável (reduz Ht)"
    elif hz < -0.05:
        hz_desc = u"RTI abaixo do hidrante — desfavorável (aumenta Ht)"
    else:
        hz_desc = u"Mesmo nível"

    linhas = [
        [u"Σhf (ramal governante)",
         u"<mono><strong>{:.4f} mca</strong></mono>".format(res["Hf_governa"]),
         u"Soma das perdas por atrito"],
        [u"ΔZ (com sinal)",
         u"<mono><strong>{:.4f} m</strong></mono>".format(hz),
         hz_desc],
    ]
    Hm_gov = res.get(u"Hm_governa", Hm_mangueira)
    if Hm_gov > 0:
        linhas.append([u"Hm (mangueira — ramal governante)",
                       u"<mono>{:.4f} mca</mono>".format(Hm_gov),
                       u"Darcy-Weisbach · Q real convergido"])
    if Hesg > 0:
        linhas.append([u"Hesg (esguicho)",
                       u"<mono>{:.4f} mca</mono>".format(Hesg), u"—"])
    linhas.append([u"Pmin",
                   u"<mono><strong>{} mca</strong></mono>".format(Pmin),
                   u"NT 22 CBMMA"])

    tab = _tabela([u"Parcela", u"Valor", u"Descrição"], linhas)

    if Hm_gov > 0:
        eq = u"Ht = Σhf − ΔZ + Hm + Hesg + Pmin = {:.4f} − ({:.4f}) + {:.4f} + {:.4f} + {} = <strong>{:.4f} mca</strong>".format(
            res["Hf_governa"], hz, Hm_gov, Hesg, Pmin, res["Ht"])
    else:
        eq = u"Ht = Σhf − ΔZ + Pmin = {:.4f} − ({:.4f}) + {} = <strong>{:.4f} mca</strong>".format(
            res["Hf_governa"], hz, Pmin, res["Ht"])

    nota = u'<p class="nota">Percurso crítico: <strong>{}</strong></p>'.format(res["hid_governa"])

    return nota + tab + _formula(eq)


def _html_secao_hidrantes(res, Hz_H1, Hz_H2, Pmin, ponto_pmin=u"válvula"):
    def bloco(label, Hz, Hf, P, Q, ordem):
        status = _status_badge(P, Pmin, 100.0)
        tab = _tabela(
            [u"Parâmetro", u"Desenvolvimento", u"Resultado"],
            [
                [u"Σhf do percurso",
                 u"T1 + T2 + trecho exclusivo",
                 u"<mono><strong>{:.4f} mca</strong></mono>".format(Hf)],
                [u"ΔZ",
                 u"Z<sub>RTI</sub> − Z<sub>{}</sub>".format(label),
                 u"<mono><strong>{:.4f} m</strong></mono>".format(Hz)],
                [u"Pressão na {} (P)".format(ponto_pmin),
                 u"<mono>{:.4f} + ({:.4f}) − {:.4f}</mono>".format(res["Ht"], Hz, Hf),
                 u"<mono><strong>{:.4f} mca</strong></mono>".format(P)],
                [u"Vazão real (Q)",
                 u"Equilíbrio hidráulico da rede",
                 u"<mono><strong>{:.2f} L/min</strong></mono>".format(Q)],
                [u"Verificação normativa",
                 u"Pmin = {} / Pmax = 100 mca".format(Pmin),
                 status],
            ]
        )
        return u"""
        <div class="hid-card">
            <div class="hid-header">
                <span class="hid-tag">{label}</span>
                <span class="hid-ordem">{ordem}</span>
            </div>
            {tab}
        </div>""".format(label=label, ordem=ordem, tab=tab)

    b1 = bloco(u"HID-01", Hz_H1, res["Hf_Hid01"], res["p_hid01"], res["Q_h01"], u"1º mais desfavorável")
    b2 = bloco(u"HID-02", Hz_H2, res["Hf_Hid02"], res["p_hid02"], res["Q_h02"], u"2º mais desfavorável")
    diff = abs(res["p_hid02"] - res["p_hid01"])
    nota = u'<p class="nota">Modelo de demanda fixa · Q_i = Qs_min · ΔP = <mono>{:.4f} mca</mono> · Pressões calculadas pelas equações hidráulicas</p>'.format(
        diff)
    formula = _formula(u"P = Ht + ΔZ − Σhf  &nbsp;|&nbsp;  E₁(Q₁) = E₂(Qt − Q₁)")

    return formula + nota + u'<div class="hid-grid">' + b1 + b2 + u'</div>'


def _html_secao_bomba(res, eta, eta_dec, pot_cv, pot_kw):
    tab = _tabela(
        [u"Parâmetro", u"Valor", u"Observação"],
        [
            [u"Vazão total de projeto (Qt)",
             u"<mono><strong>{:.2f} L/min = {:.4f} m³/s</strong></mono>".format(
                 res["Qt_final"], res["Qt_final"]/60000.0),
             u"Q<sub>HID-01</sub> + Q<sub>HID-02</sub>"],
            [u"Altura manométrica (Ht)",
             u"<mono><strong>{:.4f} mca</strong></mono>".format(res["Ht"]),
             u"Percurso crítico: {}".format(res["hid_governa"])],
            [u"Eficiência global (η)",
             u"<mono><strong>{}%</strong></mono>".format(eta),
             u"Informada pelo projetista"],
        ]
    )
    eq = _formula(
        u"Pcv = (1000 × {:.4f} × {:.4f}) / (75 × {:.2f}) = <strong>{:.2f} cv</strong>".format(
            res["Qt_final"]/60000.0, res["Ht"], eta_dec, pot_cv)
    )
    tab_op = _tabela(
        [u"Q (m³/h)", u"Hm (mca)", u"Potência mínima (cv)", u"Potência mínima (kW)"],
        [[
            u"<mono><strong>{:.2f}</strong></mono>".format(res["Qt_final"]/1000.0*60),
            u"<mono><strong>{:.2f}</strong></mono>".format(res["Ht"]),
            u"<mono><strong>{:.2f}</strong></mono>".format(pot_cv),
            u"<mono><strong>{:.2f}</strong></mono>".format(pot_kw),
        ]]
    )
    subtitulo = u'<h3 class="sub-secao">Ponto de operação para seleção</h3>'
    return tab + eq + subtitulo + tab_op


def _html_resumo(res, Pmin, pot_cv, pot_kw, ponto_pmin=u"válvula"):

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

    _label_p = u"Pressão na {}".format(ponto_pmin)
    st1 = _status_badge(res["p_hid01"], Pmin, 100.0)
    c1 = (
        _row(_label_p, u"{:.4f}".format(res["p_hid01"]), u"mca") +
        _row(u"Vazão real", u"{:.2f}".format(res["Q_h01"]), u"L/min") +
        _row(u"Σhf percurso", u"{:.4f}".format(res["Hf_Hid01"]), u"mca") +
        u'<hr class="resumo-divider">' +
        u'<div class="resumo-status">{}</div>'.format(st1)
    )

    st2 = _status_badge(res["p_hid02"], Pmin, 100.0)
    c2 = (
        _row(_label_p, u"{:.4f}".format(res["p_hid02"]), u"mca") +
        _row(u"Vazão real", u"{:.2f}".format(res["Q_h02"]), u"L/min") +
        _row(u"Σhf percurso", u"{:.4f}".format(res["Hf_Hid02"]), u"mca") +
        u'<hr class="resumo-divider">' +
        u'<div class="resumo-status">{}</div>'.format(st2)
    )

    c3 = (
        _row(u"Altura manométrica (Ht)", u"{:.4f}".format(res["Ht"]), u"mca") +
        _row(u"Vazão total (Qt)", u"{:.2f}".format(res["Qt_final"]), u"L/min") +
        _row(u"Qt em m³/h", u"{:.2f}".format(res["Qt_final"] / 1000.0 * 60), u"m³/h") +
        u'<hr class="resumo-divider">' +
        _row(u"Potência mínima", u"{:.2f}".format(pot_cv), u"cv") +
        _row(u"Potência mínima", u"{:.2f}".format(pot_kw), u"kW")
    )

    cards = (
        _card(u"HID-01", u"1º mais desfavorável", c1) +
        _card(u"HID-02", u"2º mais desfavorável", c2) +
        _card(u"BOMBA", u"Ponto de operação", c3)
    )

    return u'<div class="resumo-grid">{}</div>'.format(cards)


CSS = u"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #ffffff;
  --bg2:       #f7f8fa;
  --bg3:       #eef0f4;
  --border:    #d0d5de;
  --border2:   #b8bfcc;
  --accent:    #4a5568;
  --accent2:   #c94a24;
  --text:      #1a1d24;
  --text2:     #4a5060;
  --text3:     #8a909e;
  --ok:        #1a6e3c;
  --ok-bg:     #eaf5ee;
  --ok-text:   #1a6e3c;
  --warn-bg:   #fdf4e3;
  --warn-text: #8a5a00;
  --err-bg:    #fdecea;
  --err-text:  #b32020;
  --font:      'DM Sans', sans-serif;
  --mono:      'DM Mono', monospace;
  --radius:    4px;
}

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
}

.wrapper {
  max-width: 980px;
  margin: 0 auto;
  padding: 48px 40px 80px;
}

/* CABEÇALHO */
.cabecalho {
  padding-bottom: 28px;
}
.cab-eyebrow {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: 10px;
}
.cab-titulo {
  font-size: 26px;
  font-weight: 300;
  color: var(--text);
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}
.cab-titulo strong { font-weight: 600; color: var(--accent); }
.cab-sub {
  font-size: 12px;
  color: var(--text2);
  display: flex;
  gap: 28px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 14px;
}
.cab-meta { display: flex; align-items: center; gap: 6px; }
.cab-meta-label {
  color: var(--text3);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

/* SEÇÕES */
.secao { margin-bottom: 44px;}
.secao-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.secao-num {
  width: 22px; height: 22px;
  border: 1.5px solid var(--accent);
  color: var(--accent);
  font-size: 10px;
  font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  border-radius: 3px;
  flex-shrink: 0;
}
.secao-titulo {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
  letter-spacing: 0;
}
.sub-secao {
  font-size: 11px;
  font-weight: 500;
  color: var(--text3);
  margin: 20px 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* TABELAS */
.tabela {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 14px;
}
.tabela thead tr {
  background: var(--bg3);
  border-bottom: 1.5px solid var(--border2);
}
.tabela th {
  text-align: left;
  padding: 7px 11px;
  font-size: 10px;
  font-weight: 500;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.tabela td {
  padding: 7px 11px;
  color: var(--text);
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.tabela tbody tr:nth-child(even) td { background: var(--bg2); }
.tabela tbody tr:hover td { background: #eef3ff; }
.tabela-aces { margin-top: 10px; }

/* FÓRMULAS */
.formula {
  font-family: var(--mono);
  font-size: 12px;
  background: var(--bg2);
  border-left: 3px solid var(--accent);
  padding: 9px 14px;
  margin: 10px 0;
  border-radius: 0 var(--radius) var(--radius) 0;
  color: var(--text);
  line-height: 1.9;
  overflow-x: auto;
}

/* MONO inline */
mono {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--accent2);
}

/* BADGES */
.badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.badge-ok   { background: var(--ok-bg);   color: var(--ok-text);   border: 1px solid #b8ddc8; }
.badge-warn { background: var(--warn-bg); color: var(--warn-text); border: 1px solid #f0d8a0; }
.badge-err  { background: var(--err-bg);  color: var(--err-text);  border: 1px solid #f0c0bc; }

/* NOTAS */
.nota {
  font-size: 11px;
  color: var(--text2);
  margin: 8px 0;
  padding-left: 10px;
  border-left: 2px solid var(--border2);
}

/* TRECHOS */
.trecho-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 18px 22px;
  margin-bottom: 16px;
}
.trecho-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.trecho-num {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 500;
  background: var(--bg3);
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 2px 7px;
  border-radius: 3px;
}
.trecho-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}
.sub-titulo {
  font-size: 11px;
  font-weight: 500;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin: 12px 0 5px;
}

/* HIDRANTES */
.hid-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  margin-top: 14px;
}
.hid-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 18px 22px;
}
.hid-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.hid-tag {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
}
.hid-ordem { font-size: 11px; color: var(--text3); }

/* RESUMO EXECUTIVO — cards agrupados */
.resumo-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
}
.resumo-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.resumo-card-header {
  background: var(--bg3);
  border-bottom: 1px solid var(--border);
  padding: 8px 14px;
  font-size: 10px;
  font-weight: 500;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  display: flex;
  align-items: center;
  gap: 6px;
}
.resumo-card-header .tag {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--accent);
  background: var(--bg);
  border: 1px solid var(--accent);
  border-radius: 3px;
  padding: 1px 5px;
}
.resumo-card-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.resumo-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.resumo-row-label {
  font-size: 11px;
  color: var(--text3);
}
.resumo-row-valor {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
  text-align: right;
}
.resumo-row-valor .unidade {
  font-size: 11px;
  font-weight: 400;
  color: var(--text2);
}
.resumo-divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2px 0;
}
.resumo-status {
  display: flex;
  justify-content: flex-end;
  margin-top: 2px;
}

/* RESUMO — linhas por tipo de saída */
.resumo-linha {
  margin-bottom: 20px;
}
.resumo-linha-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--accent);
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}
.resumo-linha-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.resumo-linha-cards .resumo-card {
  flex: 1 1 180px;
  max-width: 260px;
}

/* RODAPÉ */
.rodape {
  margin-top: 56px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 10px;
  color: var(--text3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

/* IMPRESSÃO */
@media print {
  body { font-size: 11px; }
  .wrapper { padding: 0; max-width: 100%; }
  .cabecalho { margin-bottom: 24px; padding-bottom: 16px; }
  .secao { margin-bottom: 28px; page-break-inside: avoid; }
  .trecho-card, .hid-card { page-break-inside: avoid; }
  .hid-grid { grid-template-columns: 1fr; }
  .resumo-grid { grid-template-columns: 1fr 1fr 1fr; }
  .tabela tbody tr:hover td { background: transparent; }
}
"""


def build_corpo_hidrantes(res, dados_sistema, Z_RTI, Z_HID01, Z_HID02,
                          Hz_H1, Hz_H2, Hm_mangueira, Hesg, C_HW,
                          eta, pot_cv, pot_kw, calculo_escolha, valor_sistema,
                          data_str=None,
                          cache_hid_Dm=None):
    """Retorna o HTML do corpo do memorial de hidrantes (sem wrapper <html> nem rodapé)."""
    if data_str is None:
        data_str = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")

    Qs_lmin = dados_sistema["vazao_min"]
    Qs_m3s  = Qs_lmin / 60000.0
    Qt_lmin = Qs_lmin * 2
    Qt_m3s  = Qt_lmin / 60000.0
    Pmin    = dados_sistema["pressao_min"]
    eta_dec = eta / 100.0

    _Dm_m = cache_hid_Dm if cache_hid_Dm is not None else (
        dados_sistema["mangueira_dn"] / 1000.0 if Hm_mangueira > 0 else None
    )
    # Ponto onde P_i = Ht + ΔZ_i − Hf_i − Hm_i − Hesg é de fato calculada:
    # se não há mangueira/esguicho (Hm=0) ou Hesg>0 (Pmin referenciado na
    # válvula, perda do esguicho já explícita), o ponto é a válvula; caso
    # contrário (mangueira ativa e Hesg=0) a subtração de Hm desloca o ponto
    # calculado para a entrada do esguicho.
    ponto_pmin = u"válvula" if (_Dm_m is None or Hesg > 0) else u"entrada do esguicho"

    s1 = _html_secao_dados(dados_sistema, valor_sistema, calculo_escolha,
                           Qs_lmin, Qs_m3s, Qt_lmin, Qt_m3s, Pmin, C_HW)
    s2 = _html_secao_elevacoes(Z_RTI, Z_HID01, Z_HID02, Hz_H1, Hz_H2)
    s3 = _html_secao_trechos(res["hf"], C_HW)
    s4 = _html_secao_hmt(res, Hm_mangueira, Hesg, Pmin)
    s5 = _html_secao_hidrantes(res, Hz_H1, Hz_H2, Pmin, ponto_pmin)
    s6 = _html_secao_bomba(res, eta, eta_dec, pot_cv, pot_kw)
    sr = _html_resumo(res, Pmin, pot_cv, pot_kw, ponto_pmin)

    secao_mangueira = u""
    if _Dm_m is not None:
        import math as _math
        _f_val  = 0.022
        _g_val  = 9.81
        _Lm_val = 30.0
        pi2  = _math.pi ** 2
        Dm5  = _Dm_m ** 5

        # Parâmetros constantes da fórmula
        tab_params = _tabela(
            [u"Parâmetro", u"Símbolo", u"Valor"],
            [
                [u"Fator de atrito Darcy (mangueira lisa)", u"f",   u"<mono>0,022</mono>"],
                [u"Comprimento da mangueira",               u"Lm",  u"<mono>30,0 m</mono>"],
                [u"Aceleração da gravidade",                u"g",   u"<mono>9,81 m/s²</mono>"],
                [u"Diâmetro interno da mangueira",          u"Dm",  u"<mono>{:.4f} m ({} mm)</mono>".format(
                    _Dm_m, dados_sistema["mangueira_dn"])],
            ]
        )

        # Hm por hidrante — usa Q real convergido
        Hm1 = res.get(u"Hm_hid01", Hm_mangueira)
        Hm2 = res.get(u"Hm_hid02", Hm_mangueira)
        Q1  = res.get(u"Q_h01", Qs_lmin)
        Q2  = res.get(u"Q_h02", Qs_lmin)
        Q1_m3s = Q1 / 60000.0
        Q2_m3s = Q2 / 60000.0

        tab_hm = _tabela(
            [u"Hidrante", u"Q real (L/min)", u"Q real (m³/s)", u"Hm (mca)"],
            [
                [u"HID-01",
                 u"<mono>{:.2f}</mono>".format(Q1),
                 u"<mono>{:.6f}</mono>".format(Q1_m3s),
                 u"<mono><strong>{:.4f}</strong></mono>".format(Hm1)],
                [u"HID-02",
                 u"<mono>{:.2f}</mono>".format(Q2),
                 u"<mono>{:.6f}</mono>".format(Q2_m3s),
                 u"<mono><strong>{:.4f}</strong></mono>".format(Hm2)],
            ]
        )

        _nota_demanda = u""
        if Hesg <= 0:
            _nota_demanda = (
                u'<p class="nota">Modelo de demanda fixa: adota-se o par normativo '
                u"do esguicho regulável (Q = {qs} L/min a P = {pmin} mca na entrada "
                u"do esguicho), de modo que a pressão requerida do esguicho já está "
                u"incorporada em Pmin e Hesg = 0 na cadeia de energia. As vazões "
                u"reais de operação serão iguais ou superiores às normativas.</p>"
            ).format(qs=Qs_lmin, pmin=Pmin)

        hm_formula = (
            tab_params
            + _formula(
                u"Hm = (8 × f × Lm) / (g × π² × Dm⁵) × Q²<br>"
                u"Hm = (8 × {f} × {Lm}) / ({g} × {pi2:.6f} × {Dm5:.4e}) × Q²".format(
                    f=_f_val, Lm=_Lm_val, g=_g_val, pi2=pi2, Dm5=Dm5)
            )
            + u'<h3 class="sub-secao">Hm por hidrante (Q real convergido)</h3>'
            + tab_hm
            + _nota_demanda
        )
        secao_mangueira = _secao(u"3", u"Perda de Carga na Mangueira (Darcy-Weisbach)", hm_formula)
        s3_num = u"4"; s4_num = u"5"; s5_num = u"6"; s6_num = u"7"
    else:
        s3_num = u"3"; s4_num = u"4"; s5_num = u"5"; s6_num = u"6"

    return u"""
    <div class="cabecalho">
        <div class="cab-sub">
            <div class="cab-meta">
                <span class="cab-meta-label">Tipo de Sistema: </span>
                <span>{sistema}</span>
            </div>
            <div class="cab-meta">
                <span class="cab-meta-label">Método de Cálculo: </span>
                <span>{metodo}</span>
            </div>
        </div>
    </div>

    {res_executivo}

    {s1}
    {s2}
    {s_mangueira}
    {s3}
    {s4}
    {s5}
    {s6}
    """.format(
        sistema=valor_sistema,
        metodo=calculo_escolha,
        data=data_str,
        res_executivo=_secao(u"↗", u"Resumo Executivo", sr),
        s1=_secao(u"1", u"Dados Normativos do Sistema", s1),
        s2=_secao(u"2", u"Cotas Altimétricas e Desníveis", s2),
        s_mangueira=secao_mangueira,
        s3=_secao(s3_num, u"Perdas de Carga por Trecho (Hazen-Williams)", s3),
        s4=_secao(s4_num, u"Altura Manométrica Total (Ht)", s4),
        s5=_secao(s5_num, u"Pressão e Vazão nos Hidrantes", s5),
        s6=_secao(s6_num, u"Dimensionamento da Bomba de Recalque", s6),
    )


