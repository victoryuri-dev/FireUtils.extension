# -*- coding: utf-8 -*-
"""
memorial/geral.py — Fire Utils
Gera o Memorial Geral de PPCI unificando hidrantes e saídas de emergência.

API pública:
    build_html_geral(cache_hid, cache_saidas) -> str   # retorna HTML direto
"""

import os
import base64
import datetime

from memorial.hidrantes import CSS, build_corpo_hidrantes
from memorial.saidas import build_corpo_saidas

_LIB_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # lib/
_ASSETS_DIR = os.path.join(_LIB_DIR, u"assets")


def _logo_src():
    try:
        path = os.path.join(_ASSETS_DIR, u"etos-logo-hor.png")
        with open(path, "rb") as f:
            data = base64.b64encode(f.read())
        return u"data:image/png;base64,{}".format(data)
    except Exception:
        return u""


_CSS_EXTRA = u"""
/* CAPÍTULO — separador entre sistemas no memorial geral */
@media print {
    .page, .page-break { break-after: page; }
}

.capitulo-sep {
  margin: 0;
  padding: 18px 0 14px;
  border-top: 3px solid var(--accent);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.section-sep {
  margin-bottom: 100px;
}
.capitulo-sep-num {
  font-family: var(--mono);
  font-size: 16px;
  font-weight: 500;
  color: var(--accent);
  border: 1.5px solid var(--accent);
  border-radius: 3px;
  padding: 2px 8px;
  flex-shrink: 0;
}
.capitulo-sep-titulo {
  font-size: 22px;
  font-weight: 300;
  color: var(--text);
  letter-spacing: -0.01em;
}
.capitulo-sep-titulo strong { font-weight: 600; color: var(--accent); }

/* RESUMO-LINHA — usado no resumo executivo de saídas */
.resumo-linha { margin-bottom: 18px; }
.resumo-linha-label {
  font-size: 10px;
  font-weight: 500;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 8px;
}
.resumo-linha-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
"""


def build_html_geral(cache_hid=None, cache_saidas=None):
    """
    Gera e retorna o Memorial Geral de PPCI como string HTML.

    cache_hid    : dict retornado por carregar_cache() de hidrantes (ou None)
    cache_saidas : dict retornado por carregar_cache_saidas() (ou None)
    """
    agora    = datetime.datetime.now()
    data_str = agora.strftime(u"%d/%m/%Y %H:%M")

    partes = []

    if cache_hid:
        ts_hid = cache_hid.get(u"_timestamp", data_str)
        corpo_hid = build_corpo_hidrantes(
            res             = cache_hid["res"],
            dados_sistema   = cache_hid["dados_sistema"],
            Z_RTI           = cache_hid["Z_RTI"],
            Z_HID01         = cache_hid["Z_HID01"],
            Z_HID02         = cache_hid["Z_HID02"],
            Hz_H1           = cache_hid["Hz_H1"],
            Hz_H2           = cache_hid["Hz_H2"],
            Hm_mangueira    = cache_hid["Hm_mangueira"],
            Hesg            = cache_hid["Hesg"],
            C_HW            = cache_hid["C_HW"],
            eta             = cache_hid["eta"],
            pot_cv          = cache_hid["pot_cv"],
            pot_kw          = cache_hid["pot_kw"],
            calculo_escolha = cache_hid["calculo_escolha"],
            valor_sistema   = cache_hid["valor_sistema"],
            data_str        = ts_hid,
        )
        partes.append((u"I", u"Dimensionamento do Sistema de <strong>Hidrantes</strong>", corpo_hid))

    if cache_saidas:
        ts_saidas = cache_saidas.get(u"timestamp", data_str)
        corpo_saidas = build_corpo_saidas(
            res         = cache_saidas["resultados"],
            rooms_data  = cache_saidas["rooms_data"],
            nome_terreo = cache_saidas["nome_terreo"],
            timestamp   = ts_saidas,
        )
        partes.append((u"II", u"Dimensionamento das <strong>Saídas de Emergência</strong>", corpo_saidas))

    conteudo = u""
    for num, titulo, corpo in partes:
        conteudo += u"""<section class="section-sep">"""
        sep = u"""
        <div class="capitulo-sep">
            <h1 class="capitulo-sep-num">{num}</h1>
            <h1 class="capitulo-sep-titulo">{titulo}</h1>
        </div>""".format(num=num, titulo=titulo)
        conteudo += sep + corpo
        conteudo += u"</section>"
        conteudo += u"""<div class="page-break"></div>"""

    sistemas_str = u" | ".join(
        u"Hidrantes" if p[0] == u"I" else u"Saídas de Emergência"
        for p in partes
    )

    cabecalho = u"""
    <div class="cabecalho">
        <h1 class="cab-titulo"><strong>MEMORIAL DESCRITIVO</strong></h1>
        <div class="cab-sub">
            <div class="cab-meta">
                <span class="cab-meta-label">Sistemas</span>
                <span>{sistemas}</span>
            </div>
        </div>
    </div>""".format(sistemas=sistemas_str)

    logo = _logo_src()
    logo_tag = u'<img src="{}" style="height:50px;">'.format(logo) if logo else u""
    rodape = u"""
    <div class="rodape">
        {logo}
        <div style="display:flex; gap:28px;">
            <span>Fire Utils · pyRevit Extension</span>
            <span>Gerado em {data}</span>
        </div>
    </div>""".format(logo=logo_tag, data=data_str)

    return u"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memorial Geral · Fire Utils</title>
<style>{css}
{css_extra}
</style>
</head>
<body>
<div class="wrapper">
{cabecalho}
{conteudo}
{rodape}
</div>
</body>
</html>""".format(
        css=CSS, css_extra=_CSS_EXTRA,
        cabecalho=cabecalho, conteudo=conteudo, rodape=rodape,
    )
