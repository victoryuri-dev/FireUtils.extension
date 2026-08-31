# -*- coding: utf-8 -*-
"""
memorial.py — Fire Utils · lib/hidrantes/
Montagem do memorial de cálculo (passo a passo, método da marcha) em HTML —
mesma lógica de formatação usada tanto no console do pyRevit quanto no
arquivo .html salvo na pasta do projeto.

Módulo puro: recebe os resultados já calculados (por calcular_rede() e
companhia, em calc.py) e o objeto `output` do pyRevit do chamador — não
importa nada do Revit. Usado pelo botão "Memorial de Cálculo", que relê o
cache salvo por "Dimensionar Hidrantes" (firedata.json) e reimprime o
memorial completo sem recalcular nada.

"Dimensionar Hidrantes" não chama este módulo — ao final ele mostra só um
resumo de verificações e resultados finais, e para o dimensionamento no
primeiro ponto que não atender a norma.
"""

import os
import io as _io
import re as _re

from hidrantes.calc import MCA_POR_BAR, F_DARCY, K_VALVULA, COEF_JM, G
from hidrantes.norm_profiles import req, ref
from hidrantes import succao as succao_calc

# Simbolos de saida no output window do pyRevit (janela de output do pyRevit
# roda em unicode e normalmente exibe ✓/✗/≤ sem problema). Se algum ambiente
# nao renderizar esses caracteres, mude _ASCII_FALLBACK para True aqui -
# unico lugar do arquivo que define esses simbolos.
_ASCII_FALLBACK = False
if _ASCII_FALLBACK:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"OK", u"X", u"<=", u">="
else:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"✓", u"✗", u"≤", u"≥"

# Definido por print_memorial_calculo() antes de montar o memorial (trocado
# temporariamente por um buffer _Memorial, depois restaurado ao console real
# do chamador) - ver a funcao mais abaixo.
output = None

def _fmt_dh(dh):
    """ΔH com sinal explícito para as equações da marcha (J ± ΔH)."""
    return (u"+ {:.4f}" if dh >= 0 else u"− {:.4f}").format(abs(dh))

# IronPython 2.7 (engine do pyRevit) tem 'unicode'; CPython 3 não.
try:
    _txt = unicode
except NameError:
    _txt = str


def _esc(valor):
    """Escapa o texto para HTML."""
    return (_txt(valor).replace(u"&", u"&amp;")
                       .replace(u"<", u"&lt;")
                       .replace(u">", u"&gt;"))


# Expoentes em notação "X^1,85" / "X^−4,87" → sobrescrito real, em qualquer
# texto do memorial (fórmulas soltas no meio de frases incluídas).
_SUP_RE = _re.compile(u"\\^([\u2212-]?[0-9]+(?:,[0-9]+)?)")

def _sup(texto):
    return _SUP_RE.sub(lambda m: u"<sup>{}</sup>".format(m.group(1)), texto)


# Notação "X_abc" (P_hd01, Q_hd02, P_PA, P_valv, P_anterior...) → subscrito
# real, como em qualquer notação de engenharia (P com "hd01" pequeno embaixo).
# Só letras/dígitos ASCII depois do "_": rótulos com palavra acentuada
# (ex.: cabeçalho de tabela) não usam essa notação — ver comentário onde são
# definidos.
_SUB_RE = _re.compile(u"\\b([A-Za-zΔ∆]+)_([A-Za-z0-9]+)\\b")

def _sub(texto):
    return _SUB_RE.sub(lambda m: u"{}<sub>{}</sub>".format(m.group(1), m.group(2)), texto)


# Variáveis sem underscore que também devem usar subscrito: Jun, Ltotal, Leq, Pmin
# Padrão: J + un, L + total, L + eq, P + min (mantém a primeira letra normal)
_COMPOUND_VARS_RE = _re.compile(
    u"\\b(J(?=un\\b)|L(?=total\\b|eq\\b)|P(?=min\\b))"
    u"(un|total|eq|min)\\b")

def _format_compound_vars(texto):
    """Formata variáveis compostas sem underscore como subscrito: Jun→J_un, etc."""
    return _COMPOUND_VARS_RE.sub(
        lambda m: u"{}<sub>{}</sub>".format(m.group(1), m.group(2)), texto)


def _inline(valor):
    """Escapa HTML e converte **negrito** / *itálico* / ^expoente / _subscrito."""
    t = _format_compound_vars(_sub(_sup(_esc(valor))))
    partes = t.split(u"**")
    if len(partes) % 2 == 1:          # só converte se estiver balanceado
        t = u"".join(p if i % 2 == 0 else u"<b>" + p + u"</b>"
                     for i, p in enumerate(partes))
    partes = t.split(u"*")
    if len(partes) % 2 == 1:
        t = u"".join(p if i % 2 == 0 else u"<i>" + p + u"</i>"
                     for i, p in enumerate(partes))
    return t


def _frac(num, den):
    """Fração renderizada como numerador sobre denominador (com linha),
    em vez de 'num / den' em uma linha só."""
    return (u"<span class='fu-frac'><span class='fu-num'>{}</span>"
            u"<span class='fu-den'>{}</span></span>").format(
                _inline(num), _inline(den))


def _formula(expr, definicoes=None):
    """
    Emite uma equação em destaque (fórmula literal, sem números), no formato:

        Ltotal = L + Leq

        Onde:
        L: Comprimento real
        Leq: Comprimento equivalente das conexões e acessórios.

    definicoes: lista de (símbolo, descrição); quando omitida, só a equação.
    """
    html = [u"<div class='fu-eq'>{}</div>".format(_inline(expr))]
    _formula_onde(html, definicoes)
    output.print_html(u"".join(html))


def _formula_onde(html, definicoes):
    """Acrescenta o bloco 'Onde: símbolo: descrição' à lista de HTML de uma
    fórmula — usado tanto por _formula() quanto por _formula_frac()."""
    if not definicoes:
        return
    html.append(u"<div class='fu-eq-onde'><p class='fu-eq-onde-lbl'>Onde:</p>")
    for simb, desc in definicoes:
        html.append(u"<p class='fu-eq-def'><b>{}</b>: {}</p>".format(
            _inline(simb), _inline(desc)))
    html.append(u"</div>")


def _formula_frac(lhs, num, den, depois=u"", sufixo=u"", definicoes=None):
    """
    Como _formula(), mas para uma equação cujo lado direito é uma fração —
    renderiza numerador sobre denominador (com linha), em vez de
    'numerador / denominador' em uma linha só.

    depois: texto colado logo após a fração (ex.: '· Q²', quando a fração é
            multiplicada por algo). sufixo: unidade entre colchetes, ex. '[mca]'.
    """
    corpo = u"{} = {}".format(_inline(lhs), _frac(num, den))
    if depois:
        corpo += u" {}".format(_inline(depois))
    if sufixo:
        corpo += u"   {}".format(_inline(sufixo))
    html = [u"<div class='fu-eq'>{}</div>".format(corpo)]
    _formula_onde(html, definicoes)
    output.print_html(u"".join(html))


def _md_para_html(texto):
    """Converte uma linha do markdown usado no memorial para HTML."""
    t = (texto or u"").strip()
    if not t:
        return u""
    if t == u"---":            return u"<hr>"
    if t.startswith(u"### "):  return u"<h3>{}</h3>".format(_inline(t[4:]))
    if t.startswith(u"## "):   return u"<h2>{}</h2>".format(_inline(t[3:]))
    if t.startswith(u"# "):    return u"<h1>{}</h1>".format(_inline(t[2:]))
    if t.startswith(u"> "):    return u"<blockquote>{}</blockquote>".format(_inline(t[2:]))
    if t.startswith(u"- "):    return u"<li>{}</li>".format(_inline(t[2:]))
    return u"<p>{}</p>".format(_inline(t))


class _Memorial(object):
    """
    Acumula o memorial como HTML em vez de despejá-lo direto no console.

    As funções que montam o memorial chamam output.print_md()/print_html();
    trocando o 'output' global por uma instância desta classe, o mesmo código
    monta um documento único — que depois é exibido no console com CSS
    próprio e salvo como arquivo .html, formatado, fora do Revit.
    """

    def __init__(self):
        self._partes = []

    def print_md(self, texto):
        html = _md_para_html(texto)
        if html:
            self._partes.append(html)

    def print_html(self, html):
        self._partes.append(html)

    def corpo(self):
        """HTML do memorial, com os itens de lista agrupados em <ul>."""
        saida, lista = [], []
        for parte in self._partes:
            if parte.startswith(u"<li>"):
                lista.append(parte)
                continue
            if lista:
                saida.append(u"<ul>{}</ul>".format(u"".join(lista)))
                lista = []
            saida.append(parte)
        if lista:
            saida.append(u"<ul>{}</ul>".format(u"".join(lista)))
        return u"".join(saida)


def _css(cor_texto, cor_borda, cor_fundo, cor_suave, cor_acento):
    """
    Folha de estilo do memorial, com escopo em .fu-memorial.

    Os !important são necessários no console do pyRevit: o tema dele traz
    regras próprias para <table>/<th> (fundo escuro no cabeçalho, largura
    de 100%) que sobrescreveriam o estilo daqui.
    """
    return u"""
.fu-memorial {{ color:{txt}; line-height:1.7; }}
.fu-memorial h1 {{ font-size:1.45em; margin:0 0 8px 0; }}
.fu-memorial h2 {{ font-size:1.18em; margin:42px 0 16px 0; padding-top:18px;
                   border-top:1px solid {suave}; }}
.fu-memorial h3 {{ font-size:1.05em; margin:34px 0 14px 0; }}
.fu-memorial p  {{ margin:12px 0; }}
.fu-memorial ul {{ margin:12px 0 18px 0; padding-left:24px; }}
.fu-memorial li {{ margin:5px 0; }}
.fu-memorial hr {{ border:0; border-top:1px solid {suave}; margin:22px 0; }}
.fu-memorial blockquote {{ margin:16px 0; padding:10px 16px;
                           border-left:3px solid {borda}; }}
.fu-memorial table {{ border-collapse:collapse !important; width:auto !important;
                      background:transparent !important; margin:18px 0 26px 0 !important;
                      font-size:inherit !important; }}
.fu-memorial th, .fu-memorial td {{ border:1px solid {borda} !important;
                                    background:{fundo} !important;
                                    color:{txt} !important;
                                    padding:7px 15px !important; }}
.fu-memorial th {{ font-weight:bold !important; }}
.fu-memorial caption {{ caption-side:top; text-align:left; font-weight:bold;
                        padding:0 0 8px 0; }}
.fu-memorial .fu-eq {{ margin:18px 0 4px 0; padding:14px 18px;
                       border-left:3px solid {acento};
                       font-family:'Cambria Math','Cambria',Georgia,serif;
                       font-size:1.15em; letter-spacing:.2px; }}
.fu-memorial sup {{ font-size:.72em; }}
.fu-memorial sub {{ font-size:.72em; }}
.fu-memorial .fu-frac {{ display:inline-flex; flex-direction:column;
                         align-items:center; vertical-align:middle;
                         margin:0 5px; line-height:1.3; text-align:center; }}
.fu-memorial .fu-frac .fu-num {{ padding:0 4px 3px 4px;
                                 border-bottom:1.3px solid currentColor; }}
.fu-memorial .fu-frac .fu-den {{ padding:3px 4px 0 4px; }}
.fu-memorial .fu-eq-onde {{ margin:2px 0 22px 21px; }}
.fu-memorial .fu-eq-onde-lbl {{ margin:8px 0 4px 0 !important; font-weight:bold; }}
.fu-memorial .fu-eq-def {{ margin:3px 0 !important; }}
.fu-memorial .fu-bloco {{ margin:0 0 30px 0; }}
""".format(txt=cor_texto, borda=cor_borda, fundo=cor_fundo, suave=cor_suave,
           acento=cor_acento)


# Console do pyRevit: herda a cor do tema (claro ou escuro), sem fundo.
_CSS_CONSOLE = _css(u"inherit", u"rgba(128,128,128,0.6)", u"transparent",
                    u"rgba(128,128,128,0.35)", u"rgba(120,150,180,0.85)")
# Arquivo .html: documento próprio, pensado para leitura e impressão.
_CSS_ARQUIVO = _css(u"#1a1a1a", u"#9aa3ad", u"transparent", u"#d8dde2", u"#4c6f8c")


def _tabela(colunas, linhas, alinhas=None, titulo=None):
    """
    Acrescenta uma tabela ao memorial.

    Bordas, espaçamento e fundo vêm da folha de estilo (_css); aqui só vai
    o alinhamento de cada coluna, que é específico da tabela.

    colunas: lista de cabeçalhos.
    linhas:  lista de listas (uma por linha), já formatadas como texto.
    alinhas: alinhamento por coluna ("left"/"right"/"center"); por padrão a
             primeira coluna fica à esquerda e as demais à direita (números).
    """
    if alinhas is None:
        alinhas = [u"left"] + [u"right"] * (len(colunas) - 1)

    html = [u"<table>"]
    if titulo:
        html.append(u"<caption>{}</caption>".format(_inline(titulo)))
    html.append(u"<tr>")
    for col, ali in zip(colunas, alinhas):
        html.append(u"<th style='text-align:{}'>{}</th>".format(ali, _inline(col)))
    html.append(u"</tr>")
    for linha in linhas:
        html.append(u"<tr>")
        for val, ali in zip(linha, alinhas):
            html.append(u"<td style='text-align:{}'>{}</td>".format(ali, _inline(val)))
        html.append(u"</tr>")
    html.append(u"</table>")
    output.print_html(u"".join(html))


def _contador_letras():
    """Gerador de letras a), b), c)... para numerar passos — usado tanto no
    Roteiro quanto em cada trecho, onde a presença de certos passos (ex.: o
    trecho esguicho/mangueira/válvula) depende do método de cálculo."""
    it = iter(u"abcdefghijklmnopqrstuvwxyz")
    return lambda: next(it)


def _passo_ltotal(jt, letra):
    """Comprimento total por diâmetro: Ltotal = L + Leq (com as conexões)."""
    output.print_md(u"**{}) Comprimento total da tubulação**".format(letra))
    _formula(u"Ltotal = L + Leq")

    linhas_aces = [
        [a["nome"], u"{:.1f}".format(s["d_mm"]), u"{}".format(a["qtd"]),
         u"{:.4f}".format(a["leq_unit"]), u"{:.4f}".format(a["leq_tot"])]
        for s in jt["segmentos"] for a in s["acessorios"]
    ]
    if linhas_aces:
        _tabela([u"Conexão / acessório", u"DN (mm)", u"Qtd",
                 u"Leq unitário (m)", u"Leq total (m)"],
                linhas_aces,
                titulo=u"Conexões e acessórios por diâmetro")
    else:
        output.print_md(u"*Nenhuma conexão com comprimento equivalente "
                        u"cadastrado neste trecho.*")
        output.print_md(u"")

    _tabela([u"DN (mm)", u"L (m)", u"Leq (m)", u"Ltotal (m)"],
            [[u"{:.1f}".format(s["d_mm"]),
              u"{:.4f}".format(s["L"]), u"{:.4f}".format(s["Leq"]),
              u"**{:.4f}**".format(s["Ltotal"])]
             for s in jt["segmentos"]],
            titulo=u"Comprimento total por diâmetro")
    output.print_md(u"")


def _passo_perda(jt, c_hw, letra):
    """Perda de carga do trecho por Hazen-Williams, por diâmetro."""
    output.print_md(u"**{}) Perda de carga (Hazen-Williams)**".format(letra))
    _formula(u"Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87   [m/m]")
    _formula(u"J = Ltotal · Jun   [mca]")
    output.print_md(u"Com Q = {:.2f} L/min e C = {}.".format(jt["Q_lmin"], c_hw))
    output.print_md(u"")
    _tabela([u"DN (mm)", u"Ltotal (m)", u"Jun (m/m)", u"J (mca)"],
            [[u"{:.1f}".format(s["d_mm"]), u"{:.4f}".format(s["Ltotal"]),
              u"{:.6f}".format(s["Jun"]), u"**{:.4f}**".format(s["J"])]
             for s in jt["segmentos"]])
    output.print_md(u"**J do trecho (soma dos diâmetros) = {:.4f} mca**".format(jt["J"]))
    output.print_md(u"")


def _passo_velocidade(jt, v_limite, letra):
    """Velocidade de escoamento do trecho, por diâmetro, com verificação."""
    output.print_md(u"**{}) Velocidade de escoamento**".format(letra))
    _formula_frac(u"V", u"21,22 · Q", u"D²", sufixo=u"[m/s]")
    output.print_md(u"")
    linhas = []
    for s in jt["segmentos"]:
        ok = s["V"] <= v_limite
        linhas.append([u"{:.1f}".format(s["d_mm"]),
                       u"{:.2f}".format(jt["Q_lmin"]),
                       u"**{:.3f}**".format(s["V"]),
                       u"{:.1f}".format(v_limite),
                       u"{} atende".format(SIM_OK) if ok
                       else u"{} NÃO atende".format(SIM_X)])
    _tabela([u"DN (mm)", u"Q (L/min)", u"V (m/s)", u"Limite (m/s)", u"Verificação"],
            linhas,
            alinhas=[u"right", u"right", u"right", u"right", u"left"])
    output.print_md(u"")

def _secao_condicao_succao(v, perfil):
    """
    Condição de sucção pelo método direto e conservador: compara a cota da
    RTI com a cota de sucção da bomba, ambas já mostradas em "Cotas
    Altimétricas". Sem nível mínimo de água, dimensão de tomada ou tipo de
    captação.
    """
    output.print_md(
        u"A condição de sucção é dada pela comparação direta entre a cota da "
        u"RTI e a cota de sucção da bomba, já apresentadas em \"Cotas "
        u"Altimétricas\":")
    _formula(u"∆H_succao = cota_RTI − cota_succao",
             [(u"cota_RTI", u"Cota da RTI (reservatório)"),
              (u"cota_succao", u"Cota de sucção da bomba")])
    output.print_md(u"∆H_succao = {:.4f} − {:.4f} = **{:.4f} m**".format(
        v[u"cota_rti"], v[u"cota_succao_bomba"], v[u"dH"]))
    output.print_md(u"")

    output.print_md(u"**Verificação:**")
    output.print_md(v[u"justificativa"])
    output.print_md(u"")

    marca = SIM_X if v[u"condicao"] == succao_calc.COND_NEGATIVA else SIM_OK
    output.print_md(u"{} **Condição de sucção adotada: {}**".format(
        marca, v[u"condicao"]))
    output.print_md(u"")


def _secao_npshd(n, erro, v, j_succao, perfil, C_HW):
    """
    NPSH disponível na sucção. Só entra no memorial quando a condição de
    sucção resultou negativa — com sucção positiva a verificação não é
    exigida e a seção inteira é omitida.
    """
    fator = v[u"fator_vazao_npsh"]
    output.print_md(
        u"A sucção resultou **negativa**, o que exige verificar o NPSH "
        u"disponível{} — a energia que a instalação realmente oferece à bomba "
        u"na sucção.".format(ref(perfil, u"npshd_ref")))

    _formula(u"NPSHd = Ha − Hvp + Hs − Hf_s",
             [(u"NPSHd", u"NPSH disponível na tubulação de sucção"),
              (u"Ha", u"Pressão atmosférica local, em altura de coluna d'água"),
              (u"Hvp", u"Pressão de vapor da água na temperatura de operação"),
              (u"Hs", u"Altura estática de sucção — positiva com a bomba afogada, "
                      u"negativa quando a sucção da bomba está acima da RTI"),
              (u"Hf_s", u"Perda de carga na tubulação de sucção, com a vazão majorada")])

    output.print_md(u"Com a sucção da bomba acima da cota da RTI, Hs é negativo "
                    u"e a fórmula operacional fica:")
    _formula(u"NPSHd = Ha − Hvp − |Hs| − Hf_s")

    if erro:
        output.print_md(u"{} **Não foi possível calcular o NPSHd:** {}".format(
            SIM_X, erro))
        output.print_md(u"")
        return

    # |Hs| é a mesma elevação que a verificação da condição de sucção já
    # obteve, direto das cotas da RTI e da sucção da bomba.
    output.print_md(u"|Hs| = cota de sucção da bomba − cota da RTI = "
                    u"{:.4f} − {:.4f} = **{:.4f} m**".format(
                        v[u"cota_succao_bomba"], v[u"cota_rti"], n[u"Hs_abs"]))
    output.print_md(u"")

    # A majoração da vazão vale só para esta verificação — o resto do memorial
    # segue com Qt.
    output.print_md(u"**Perda de carga na sucção (Hf_s)** — mesmo Hazen-Williams "
                    u"do resto do memorial, mas com a vazão majorada em "
                    u"**{:g}×**, majoração exclusiva desta verificação:".format(fator))
    _formula(u"Q_npsh = {:g} · Qt = {:g} · {:.2f} = {:.2f} L/min".format(
        fator, fator, v[u"vazao_npsh_lmin"] / fator, v[u"vazao_npsh_lmin"]))
    _tabela([u"DN (mm)", u"Ltotal (m)", u"Jun (m/m)", u"J (mca)"],
            [[u"{:.1f}".format(seg["d_mm"]), u"{:.4f}".format(seg["Ltotal"]),
              u"{:.6f}".format(seg["Jun"]), u"**{:.4f}**".format(seg["J"])]
             for seg in j_succao["segmentos"]],
            alinhas=[u"right", u"right", u"right", u"right"])
    output.print_md(u"Hf_s = **{:.4f} mca** (C = {:g})".format(j_succao["J"], C_HW))
    output.print_md(u"")

    output.print_md(u"**Resultado:**")
    _tabela([u"Termo", u"Valor"],
            [[u"Ha — altitude {:g} m".format(n[u"altitude_m"]),
              u"{:.3f} mca".format(n[u"Ha"])],
             [u"Hvp — água a {:g} °C".format(n[u"temperatura_c"]),
              u"{:.3f} mca".format(n[u"Hvp"])],
             [u"|Hs| — sucção da bomba acima da RTI",
              u"{:.3f} mca".format(n[u"Hs_abs"])],
             [u"Hf_s — perda na sucção com a vazão majorada",
              u"{:.3f} mca".format(n[u"Hf_s"])],
             [u"**NPSHd**", u"**{:.3f} mca**".format(n[u"NPSHd"])]])

    output.print_md(u"NPSHd = {:.3f} − {:.3f} − {:.3f} − {:.3f} = "
                    u"**{:.3f} mca**".format(n[u"Ha"], n[u"Hvp"], n[u"Hs_abs"],
                                             n[u"Hf_s"], n[u"NPSHd"]))
    output.print_md(u"")


def _montar_memorial(res, dados_sistema, valor_sistema,
                     cotas, succao, verif_succao,
                     verif_npshd, erro_npshd, j_succao_npsh,
                     Qs_lmin, Pmin, C_HW,
                     eta, pot_cv, pot_kw, timestamp, perfil):
    norma           = req(perfil, u"norma")
    hidr_simult     = req(perfil, u"hidrantes_simultaneos")
    v_max_tubo      = req(perfil, u"v_max_tubulacao")
    v_max_suc_pos   = req(perfil, u"v_max_succao_positiva")
    v_max_suc_neg   = req(perfil, u"v_max_succao_negativa")

    v_max_succao = v_max_suc_pos if succao == u"positiva" else v_max_suc_neg

    K        = res["K"]
    dH       = res["dH"]
    j        = res["j"]
    metodo   = res["metodo"]
    esguicho = res["esguicho"]
    esg      = res["esg"]

    # Ponto de aplicação do par normativo (Q, Pmin), conforme o método
    ponto_ref = u"ponta do esguicho" if esguicho else u"válvula do hidrante"

    # Numeração dinâmica de seções: o método do esguicho acrescenta as
    # seções de perda na mangueira e na válvula antes do Fator K.
    _sec = {"n": 0}
    def sec(titulo):
        _sec["n"] += 1
        output.print_md(u"## {}. {}".format(_sec["n"], titulo))
        return _sec["n"]

    # ── Cabeçalho ─────────────────────────────────────────────────────────
    output.print_md(u"# Memorial de Cálculo — Dimensionamento Hidráulico de Hidrantes")
    output.print_md(u"**Sistema:** {} | **Método:** {} | **Norma:** {} | *{}*".format(
        valor_sistema, metodo, norma, timestamp))
    output.print_md(u"---")

    if perfil.get(u"_uf_efetiva") != perfil.get(u"_uf_solicitada"):
        output.print_md(
            u"> **Aviso:** o Estado do projeto ('{}') ainda não possui perfil "
            u"normativo próprio nesta extensão. Usando o perfil default "
            u"'{}' ({}).".format(
                perfil.get(u"_uf_solicitada"), perfil.get(u"_uf_efetiva"), norma))
        output.print_md(u"")

    # ── Vazão e pressão de projeto ────────────────────────────────────────
    sec(u"Definição da Vazão e da Pressão de Projeto")
    _tabela(
        [u"Parâmetro", u"Valor"],
        [
            [u"Norma aplicada", u"**{}**".format(norma)],
            [u"Classificação do sistema", u"**{}**".format(valor_sistema)],
            [u"Método de cálculo", u"**{}**".format(metodo)],
            [u"Ponto de aplicação de Q e Pmin", u"**{}**".format(ponto_ref)],
            [u"Vazão por hidrante (Q)", u"**{:g} L/min**".format(Qs_lmin)],
            [u"Hidrantes simultâneos (n)", u"**{}**".format(hidr_simult)],
            [u"Pressão residual mínima (Pmin)",
             u"**{:g} mca = {:.4f} bar**".format(Pmin, float(Pmin) / MCA_POR_BAR)],
            [u"Coef. Hazen-Williams (C)",
             u"**{}** — aço/ferro galvanizado".format(C_HW)],
            [u"Esguicho — DN", u"{:g} mm".format(dados_sistema["esguicho_dn"])],
            [u"Mangueira — DN / comprimento",
             u"{:g} mm / {:.1f} m".format(dados_sistema["mang_dn"],
                                          dados_sistema["mang_comp"])],
            [u"Velocidade máx. — recalque/descarga",
             u"{:.1f} m/s".format(v_max_tubo)],
            [u"Velocidade máx. — sucção ({})".format(succao),
             u"{:.1f} m/s".format(v_max_succao)],
        ],
        alinhas=[u"left", u"left"])

    # ── 2. Hidrantes mais desfavoráveis ───────────────────────────────────
    sec(u"Identificação dos Hidrantes Mais Desfavoráveis em "
        u"Funcionamento Simultâneo")
    output.print_md(u"O cenário de cálculo representa a condição mais crítica de operação "
                    u"do sistema: os **{} hidrantes mais desfavoráveis em funcionamento "
                    u"simultâneo**, ou seja, aquela que resulta na maior demanda de vazão "
                    u"total associada às maiores perdas de carga e ao maior desnível "
                    u"geométrico.".format(hidr_simult))
    output.print_md(u"")

    # ── 3. Identificação dos trechos ──────────────────────────────────────
    sec(u"Identificação dos Trechos")
    output.print_md(u"Para fins de organização e como facilitador de cálculo, a tubulação "
                    u"é dividida em trechos. O **Ponto A** é o ponto de distribuição onde "
                    u"há a separação das vazões que vão rumo aos hidrantes desfavoráveis "
                    u"considerados.")
    output.print_md(u"")
    output.print_md(u"- RTI → Bomba")
    output.print_md(u"- Bomba → Ponto A")
    output.print_md(u"- Ponto A → HD01")
    output.print_md(u"- Ponto A → HD02")
    output.print_md(u"")

    # ── Cotas altimétricas ────────────────────────────────────────────────
    sec(u"Cotas Altimétricas")
    _tabela([u"Ponto", u"Cota H (m)"],
            [[u"RTI (reservatório)", u"**{:.4f}**".format(cotas["z_rti"])],
             [u"Sucção (entrada da bomba)", u"**{:.4f}**".format(cotas["z_succao"])],
             [u"Descarga da bomba", u"**{:.4f}**".format(cotas["z_recalque"])],
             [u"Ponto A (distribuição)", u"**{:.4f}**".format(cotas["z_ponto_a"])],
             [u"HD01 (mais desfavorável)", u"**{:.4f}**".format(cotas["z_hd01"])],
             [u"HD02 (2º mais desfavorável)", u"**{:.4f}**".format(cotas["z_hd02"])]])
    output.print_md(u"**∆H = Hi − Hf** (posição dos pontos inicial e final de cada trecho, "
                    u"na direção da marcha de cálculo):")
    _tabela([u"Trecho", u"Hi (m)", u"Hf (m)", u"∆H (m)"],
            [[u"HD01 ao Ponto A", u"{:.4f}".format(cotas["z_hd01"]),
              u"{:.4f}".format(cotas["z_ponto_a"]), u"**{:.4f}**".format(dH["t3"])],
             [u"HD02 ao Ponto A", u"{:.4f}".format(cotas["z_hd02"]),
              u"{:.4f}".format(cotas["z_ponto_a"]), u"**{:.4f}**".format(dH["t4"])],
             [u"Ponto A à descarga da bomba", u"{:.4f}".format(cotas["z_ponto_a"]),
              u"{:.4f}".format(cotas["z_recalque"]), u"**{:.4f}**".format(dH["t2"])],
             [u"Sucção (Bomba à RTI)", u"{:.4f}".format(cotas["z_succao"]),
              u"{:.4f}".format(cotas["z_rti"]), u"**{:.4f}**".format(dH["t1"])]])
    output.print_md(u"")

    # ── Condição de sucção (diferença direta de cotas) ────────────────────
    sec(u"Verificação da Condição de Sucção")
    _secao_condicao_succao(verif_succao, perfil)

    # A verificação de NPSH só é exigida na sucção negativa — com sucção
    # positiva a seção inteira sai do memorial.
    if verif_succao[u"exige_npsh"]:
        sec(u"NPSH Disponível na Sucção")
        _secao_npshd(verif_npshd, erro_npshd, verif_succao, j_succao_npsh,
                     perfil, C_HW)

    # ── Roteiro de cálculo ────────────────────────────────────────────────
    sec(u"Roteiro de Cálculo")
    output.print_md(u"Cada trecho listado adiante é calculado na seguinte sequência:")
    output.print_md(u"")

    _p_ref_desc = (u"pressão na válvula do hidrante (P_valv), quando o "
                   u"método referencia Q e Pmin no esguicho"
                   if esguicho else
                   u"pressão mínima exigida em projeto (Pmin), já que o "
                   u"método referencia Q e Pmin diretamente na válvula")

    prox = _contador_letras()

    output.print_md(u"A marcha de cada ramal segue o sentido do escoamento, do ponto mais "
                    u"desfavorável (esguicho) até o Ponto A: esguicho → mangueira → "
                    u"válvula → canalização → Ponto A.")
    output.print_md(u"")

    if esguicho:
        output.print_md(u"Como o par normativo (Q, Pmin) está referido à ponta do "
                        u"esguicho, a marcha começa por ele: a perda de carga no esguicho "
                        u"é a própria **pressão mínima exigida em projeto (Pmin)**, e a "
                        u"pressão sobe até a válvula somando as perdas da mangueira e da "
                        u"válvula angular.")
        output.print_md(u"")

        output.print_md(u"**{}) Perda de carga na mangueira**:".format(prox()))
        _formula_frac(u"Jm", u"{:g}·f·Lm".format(COEF_JM), u"g·π²·Dm⁵",
                     depois=u"· Q²", sufixo=u"[mca]",
                     definicoes=[(u"Jm", u"Perda de carga na mangueira (Darcy-Weisbach)"),
                                (u"f", u"Fator de atrito = {:g}".format(F_DARCY)),
                                (u"Lm", u"Comprimento da mangueira, em m"),
                                (u"g", u"Aceleração da gravidade = {:g} m/s²".format(G)),
                                (u"Dm", u"Diâmetro da mangueira, em m"),
                                (u"Q", u"Vazão INDIVIDUAL do hidrante — nunca Qt nem "
                                      u"Qt/2, já que cada mangueira tem sua própria "
                                      u"vazão")])

        output.print_md(u"**{}) Velocidade do fluido na mangueira**:".format(prox()))
        _formula_frac(u"V", u"21,22 · Q", u"Dm²", sufixo=u"[m/s]",
                     definicoes=[(u"V", u"Velocidade do fluido na mangueira")])

        output.print_md(u"**{}) Perda de carga na válvula angular do hidrante**:".format(prox()))
        _formula_frac(u"Jvalv", u"K · V²", u"2g", sufixo=u"[mca]",
                     definicoes=[(u"Jvalv", u"Perda de carga na válvula angular do hidrante"),
                                (u"K", u"Fator K da válvula, adotado = {:g}".format(K_VALVULA))])

        output.print_md(u"**{}) Pressão na válvula do hidrante**:".format(prox()))
        _formula(u"P_valv = Pmin + Jm + Jvalv",
                 [(u"P_valv", u"Pressão na válvula do hidrante, soma das perdas "
                              u"entre o esguicho e a válvula")])

    output.print_md(u"**{}) Comprimento total da tubulação**, somado por diâmetro:".format(prox()))
    _formula(u"Ltotal = L + Leq",
             [(u"L", u"Comprimento real da tubulação"),
              (u"Leq", u"Comprimento equivalente das conexões e acessórios do trecho")])

    output.print_md(u"**{}) Perda de carga**, por Hazen-Williams, também por diâmetro:".format(prox()))
    _formula(u"Jun = 605·10⁴ · Q^1,85 · C^−1,85 · D^−4,87   [m/m]",
             [(u"Jun", u"Perda de carga unitária"),
              (u"Q", u"Vazão no trecho, em L/min"),
              (u"C", u"Coeficiente de rugosidade, adimensional — {} para "
                     u"aço/ferro galvanizado".format(C_HW)),
              (u"D", u"Diâmetro nominal (DN) da tubulação, em mm")])
    _formula(u"J = Ltotal · Jun   [mca]",
             [(u"J", u"Perda de carga do trecho — soma dos diâmetros")])

    output.print_md(u"**{}) Velocidade de escoamento**, verificada contra o limite do "
                    u"trecho:".format(prox()))
    _formula_frac(u"V", u"21,22 · Q", u"D²", sufixo=u"[m/s]",
                 definicoes=[(u"V", u"Velocidade de escoamento"),
                            (u"Limite", u"{:.1f} m/s no recalque/descarga; {:.1f} m/s "
                                       u"na sucção {}".format(
                                           v_max_tubo, v_max_succao, succao))])

    output.print_md(u"**{}) Fator K**, calculado **somente no 1º hidrante mais "
                    u"desfavorável**, a partir do par normativo:".format(prox()))
    _formula_frac(u"K", u"Q", u"√P",
                 definicoes=[(u"K", u"Fator de vazão (coeficiente de escoamento) do hidrante"),
                            (u"Q", u"Vazão normativa do hidrante mais desfavorável, em L/min"),
                            (u"P", u"{}, em bar (1 bar = {} mca)".format(
                                _p_ref_desc, MCA_POR_BAR))])
    output.print_md(u"Esse K, uma vez calculado, é reaproveitado para achar a vazão dos "
                    u"demais hidrantes: **Q = K·√P**.")
    output.print_md(u"")

    output.print_md(u"**{}) Pressão no Ponto A**, por ramal:".format(prox()))
    _formula(u"P_PA = P_ref + J ± ∆H",
             [(u"P_PA", u"Pressão necessária no Ponto A pelo ramal"),
              (u"P_ref", u"Pressão de referência do hidrante — Pmin ou P_valv, "
                        u"conforme o método"),
              (u"J", u"Perda de carga do ramal (hidrante → Ponto A)"),
              (u"∆H", u"Desnível geométrico do trecho (Hi − Hf)")])
    output.print_md(u"A pressão adotada no Ponto A é a **maior** entre os ramais "
                    u"calculados — o ramal dessa pressão é o **ramal governante**.")
    output.print_md(u"")

    output.print_md(u"**{}) Pressão e vazão final em cada hidrante**:".format(prox()))
    _formula(u"P_hd = P_PA − J ∓ ∆H",
             [(u"P_hd", u"Pressão resultante em cada hidrante — marcha inversa, "
                       u"partindo do Ponto A (o ramal governante retorna "
                       u"exatamente à pressão de referência)")])
    _formula(u"Q = K · √P",
             [(u"Q", u"Vazão final de cada hidrante, a partir do Fator K e de P_hd"),
              (u"Qt", u"Vazão total = soma das vazões dos hidrantes (Qt = ΣQ)")])

    output.print_md(u"**{}) Marcha de pressões** até a bomba e a RTI, agora com a "
                    u"vazão total Qt:".format(prox()))
    _formula(u"P = P_anterior + J ± ∆H",
             [(u"P", u"Pressão no ponto seguinte — aplicada do Ponto A até a saída "
                    u"da bomba, e da saída da bomba até a RTI (passando pela sucção)")])

    # ── Cálculo por trecho (marcha) ───────────────────────────────────────
    n7 = sec(u"Cálculo Trecho a Trecho")
    output.print_md(u"")

    P_ref      = res["P_valv_ref"]
    _P_ref_lbl = u"P_valv" if esguicho else u"Pmin"

    # --- Trecho HD01 (1º mais desfavorável) -------------------------------
    output.print_md(u"### {}.1 Trecho HD01 ao Ponto A".format(n7))
    output.print_md(u"Ramal do **1º hidrante mais desfavorável**, calculado com a vazão "
                    u"normativa Q = {:g} L/min. A marcha segue o sentido do escoamento: "
                    u"esguicho → mangueira → válvula → canalização → Ponto A.".format(Qs_lmin))
    output.print_md(u"")
    prox = _contador_letras()

    if esguicho:
        _ref   = esg["ref"]
        _dm_mm = esg["mang_dn_mm"]
        _lm    = esg["mang_comp_m"]
        output.print_md(u"A perda de carga no esguicho é a própria **pressão mínima "
                        u"exigida em projeto (Pmin = {:g} mca)**, aplicada na ponta do "
                        u"esguicho. Da ponta até a válvula somam-se a perda na mangueira "
                        u"e a perda na válvula angular.".format(Pmin))
        output.print_md(u"")

        output.print_md(u"**{}) Perda de carga na mangueira**".format(prox()))
        _formula_frac(u"Jm", u"{:g}·f·Lm".format(COEF_JM), u"g·π²·Dm⁵",
                     depois=u"· Q²", sufixo=u"[mca]")
        output.print_md(u"")
        _tabela([u"Lm (m)", u"Dm (mm)", u"Q (L/min)", u"Jm (mca)"],
                [[u"{:g}".format(_lm), u"{:g}".format(_dm_mm),
                  u"{:.2f}".format(Qs_lmin), u"**{:.4f}**".format(_ref["Jm"])]])
        output.print_md(u"")

        output.print_md(u"**{}) Velocidade do fluido na mangueira**".format(prox()))
        _formula_frac(u"V", u"21,22 · Q", u"Dm²", sufixo=u"[m/s]")
        output.print_md(u"")
        _tabela([u"Dm (mm)", u"Q (L/min)", u"V (m/s)"],
                [[u"{:g}".format(_dm_mm), u"{:.2f}".format(Qs_lmin),
                  u"**{:.4f}**".format(_ref["V"])]])
        output.print_md(u"")

        output.print_md(u"**{}) Perda de carga na válvula angular do hidrante**".format(prox()))
        _formula_frac(u"Jvalv", u"K · V²", u"2g", sufixo=u"[mca]")
        output.print_md(u"")
        _tabela([u"K", u"V (m/s)", u"Jvalv (mca)"],
                [[u"{:g}".format(K_VALVULA), u"{:.4f}".format(_ref["V"]),
                  u"**{:.4f}**".format(_ref["Jvalv"])]])
        output.print_md(u"")

        output.print_md(u"**{}) Pressão na válvula do hidrante**".format(prox()))
        _formula(u"P_valv = Pmin + Jm + Jvalv")
        output.print_md(u"P_valv = {:g} + {:.4f} + {:.4f} = "
                        u"**{:.4f} mca**".format(
                            Pmin, _ref["Jm"], _ref["Jvalv"], P_ref))
        output.print_md(u"")

    _passo_ltotal(j["t3"], prox())
    _passo_perda(j["t3"], C_HW, prox())
    _passo_velocidade(j["t3"], v_max_tubo, prox())

    output.print_md(u"**{}) Fator K** — calculado aqui, no 1º hidrante mais "
                    u"desfavorável, e reaproveitado nos demais trechos.".format(prox()))
    _formula_frac(u"K", u"Q", u"√P")
    output.print_md(u"K = {:g} / √({:.4f} / {}) = {:g} / √{:.4f} = "
                    u"**{:.4f} L/min/bar^0,5**".format(
                        Qs_lmin, P_ref, MCA_POR_BAR, Qs_lmin,
                        P_ref / MCA_POR_BAR, K))
    output.print_md(u"")

    output.print_md(u"**{}) Pressão necessária no Ponto A** pelo ramal do HD01:".format(prox()))
    _formula(u"P_PA = {} + J ± ∆H".format(_P_ref_lbl))
    _tabela([_P_ref_lbl + u" (mca)", u"J (mca)", u"∆H (m)", u"P_PA (mca)"],
            [[u"{:.4f}".format(P_ref), u"{:.4f}".format(j["t3"]["J"]),
              _fmt_dh(dH["t3"]), u"**{:.4f}**".format(res["P_PA1"])]])
    output.print_md(u"")

    # --- Trecho HD02 -------------------------------------------------------
    output.print_md(u"### {}.2 Trecho HD02 ao Ponto A".format(n7))
    output.print_md(u"Ramal do 2º hidrante mais desfavorável, calculado com a mesma "
                    u"vazão normativa Q = {:g} L/min.".format(Qs_lmin))
    output.print_md(u"")
    prox = _contador_letras()
    _passo_ltotal(j["t4"], prox())
    _passo_perda(j["t4"], C_HW, prox())
    _passo_velocidade(j["t4"], v_max_tubo, prox())
    output.print_md(u"**{}) Pressão necessária no Ponto A** pelo ramal do HD02:".format(prox()))
    _formula(u"P_PA = {} + J ± ∆H".format(_P_ref_lbl))
    _tabela([_P_ref_lbl + u" (mca)", u"J (mca)", u"∆H (m)", u"P_PA (mca)"],
            [[u"{:.4f}".format(P_ref), u"{:.4f}".format(j["t4"]["J"]),
              _fmt_dh(dH["t4"]), u"**{:.4f}**".format(res["P_PA2"])]])
    output.print_md(u"")

    # Ponto A e vazões finais pelo Fator K (sem ciclo)
    output.print_md(u"### {}.3 Pressão no Ponto A e Vazões Finais (Fator K)".format(n7))
    output.print_md(u"Pressão adotada no Ponto A = maior pressão calculada entre os "
                    u"dois trechos:")
    _formula(u"P_PA = max(P_PA1; P_PA2)")
    _tabela([u"Ramal", u"P_PA (mca)", u"Governante"],
            [[u"HD01", u"{:.4f}".format(res["P_PA1"]),
              SIM_OK if res["hid_governa"] == u"HD01" else u""],
             [u"HD02", u"{:.4f}".format(res["P_PA2"]),
              SIM_OK if res["hid_governa"] == u"HD02" else u""]],
            alinhas=[u"left", u"right", u"left"])
    output.print_md(u"P_PA adotado = **{:.4f} mca** (ramal governante: **{}**)".format(
        res["P_PA"], res["hid_governa"]))
    output.print_md(u"")
    output.print_md(u"Com o Ponto A nessa pressão, a pressão na válvula de cada hidrante "
                    u"vem da marcha inversa (o ramal governante retorna, por construção, "
                    u"exatamente à pressão de referência):")
    _formula(u"P_hd = P_PA − J ∓ ∆H")
    _tabela([u"Hidrante", u"P_PA (mca)", u"J (mca)", u"∆H (m)", u"P_hd (mca)"],
            [[u"HD01", u"{:.4f}".format(res["P_PA"]), u"{:.4f}".format(j["t3"]["J"]),
              _fmt_dh(-dH["t3"]), u"**{:.4f}**".format(res["P_hd01"])],
             [u"HD02", u"{:.4f}".format(res["P_PA"]), u"{:.4f}".format(j["t4"]["J"]),
              _fmt_dh(-dH["t4"]), u"**{:.4f}**".format(res["P_hd02"])]])
    output.print_md(u"")
    _formula(u"Q = K · √P")
    _tabela([u"Hidrante", u"K", u"P (bar)", u"Q (L/min)"],
            [[u"HD01", u"{:.4f}".format(K), u"{:.4f}".format(res["P_hd01"] / MCA_POR_BAR),
              u"**{:.2f}**".format(res["Q_hd01"])],
             [u"HD02", u"{:.4f}".format(K), u"{:.4f}".format(res["P_hd02"] / MCA_POR_BAR),
              u"**{:.2f}**".format(res["Q_hd02"])]])
    output.print_md(u"")
    output.print_md(u"**Qt = Q_hd01 + Q_hd02 = {:.2f} + {:.2f} = {:.2f} L/min**".format(
        res["Q_hd01"], res["Q_hd02"], res["Qt"]))
    output.print_md(u"")

    if esguicho:
        output.print_md(u"Com a vazão final de cada hidrante, recalculam-se a velocidade "
                        u"na mangueira e a perda na válvula angular — valores que aumentam "
                        u"conforme o traçado hidráulico caminha em direção aos pontos mais "
                        u"favoráveis. A pressão no esguicho sai de:")
        _formula(u"P_esg = P_hd − Jm − Jvalv")
        _tabela([u"Hidrante", u"Q (L/min)", u"V mangueira (m/s)", u"Jm (mca)",
                 u"Jvalv (mca)", u"P válvula (mca)", u"P esguicho (mca)"],
                [[lbl, u"{:.2f}".format(e["Q_lmin"]), u"{:.4f}".format(e["V"]),
                  u"{:.4f}".format(e["Jm"]), u"{:.4f}".format(e["Jvalv"]),
                  u"{:.4f}".format(e["P_valv"]), u"**{:.4f}**".format(e["P_esg"])]
                 for lbl, e in [(u"HD01", esg["hd01"]), (u"HD02", esg["hd02"])]])

    _col_p = u"P esguicho (mca)" if esguicho else u"P válvula (mca)"
    if esguicho:
        _linhas = [(u"HD01", esg["hd01"]["P_esg"], res["Q_hd01"]),
                   (u"HD02", esg["hd02"]["P_esg"], res["Q_hd02"])]
    else:
        _linhas = [(u"HD01", res["P_hd01"], res["Q_hd01"]),
                   (u"HD02", res["P_hd02"], res["Q_hd02"])]
    _rows = []
    for lbl, p, q in _linhas:
        _ok = (p >= float(Pmin) - 0.01 and q >= float(Qs_lmin) - 0.01)
        ver = (u"{} atende".format(SIM_OK) if _ok
               else u"{} NÃO atende".format(SIM_X))
        _rows.append([lbl, u"{:.4f}".format(p), u"{:.2f}".format(q), ver])
    _tabela([u"Hidrante", _col_p, u"Q (L/min)",
             u"Verificação (P {} {:g} mca e Q {} {:g} L/min)".format(
                 SIM_GE, Pmin, SIM_GE, Qs_lmin)],
            _rows,
            alinhas=[u"left", u"right", u"right", u"left"],
            titulo=u"Pressões e vazões resultantes nos hidrantes")

    # Ponto A à descarga da bomba
    output.print_md(u"### {}.4 Trecho do Ponto A à Descarga da Bomba".format(n7))
    output.print_md(u"Nesse trecho a vazão a ser considerada é a soma das vazões dos dois "
                    u"hidrantes em funcionamento, e a pressão inicial é a maior pressão "
                    u"calculada entre os dois trechos anteriores:")
    output.print_md(u"**Qt = Q_hd01 + Q_hd02 = {:.2f} + {:.2f} = {:.2f} L/min**".format(
        res["Q_hd01"], res["Q_hd02"], res["Qt"]))
    output.print_md(u"")
    prox = _contador_letras()
    _passo_ltotal(j["t2"], prox())
    _passo_perda(j["t2"], C_HW, prox())
    _passo_velocidade(j["t2"], v_max_tubo, prox())
    output.print_md(u"**{}) Pressão na saída da bomba**".format(prox()))
    _formula(u"P_SB = P_PA + J ± ∆H")
    _tabela([u"P_PA (mca)", u"J (mca)", u"∆H (m)", u"P_SB (mca)"],
            [[u"{:.4f}".format(res["P_PA"]), u"{:.4f}".format(j["t2"]["J"]),
              _fmt_dh(dH["t2"]), u"**{:.4f}**".format(res["P_SB"])]])
    output.print_md(u"")

    # Sucção
    output.print_md(u"### {}.5 Trecho de Sucção (RTI à Bomba)".format(n7))
    output.print_md(u"A pressão a ser utilizada agora é a encontrada no trecho anterior "
                    u"(Ponto A à descarga da bomba). Aqui utiliza-se para o cálculo de "
                    u"Jun também a vazão total Qt = {:.2f} L/min.".format(res["Qt"]))
    output.print_md(u"")
    prox = _contador_letras()
    _passo_ltotal(j["t1"], prox())
    _passo_perda(j["t1"], C_HW, prox())
    _passo_velocidade(j["t1"], v_max_succao, prox())
    output.print_md(u"**{}) Pressão de demanda referida à RTI**".format(prox()))
    _formula(u"P_RTI = P_SB + J ± ∆H")
    _tabela([u"P_SB (mca)", u"J (mca)", u"∆H (m)", u"P_RTI (mca)"],
            [[u"{:.4f}".format(res["P_SB"]), u"{:.4f}".format(j["t1"]["J"]),
              _fmt_dh(dH["t1"]), u"**{:.4f}**".format(res["P_RTI"])]])
    output.print_md(u"")

    # ── Demanda do sistema ────────────────────────────────────────────────
    sec(u"Demanda do Sistema")
    output.print_md(u"Concluídos os cálculos e verificações, o sistema possui a demanda de:")
    output.print_md(u"")
    output.print_md(u"Vazão total do sistema (Qt): **{:.2f} L/min - {:.4f} m³/h**".format(
        res["Qt"], res["Qt"] * 60.0 / 1000.0))
    output.print_md(u"")
    output.print_md(u"Altura manométrica total (HMT): **{:.4f} mca**".format(res["P_RTI"]))
    output.print_md(u"")

    # ── Bomba ─────────────────────────────────────────────────────────────
    sec(u"Dimensionamento da Bomba de Recalque")
    Qt_m3s  = res["Qt"] / 60000.0
    eta_dec = eta / 100.0
    _formula_frac(u"P_cv", u"1000 × Qt × Ht", u"75 × η",
                 definicoes=[(u"Qt", u"Vazão total de projeto, em m³/s"),
                            (u"Ht", u"Altura manométrica total, em mca (Ht = HMT = P_RTI)"),
                            (u"η", u"Eficiência global da bomba")])
    _tabela([u"Parâmetro", u"Símbolo", u"Valor"],
            [[u"Vazão total de projeto", u"Qt",
              u"**{:.2f} L/min = {:.6f} m³/s = {:.4f} m³/h**".format(
                  res["Qt"], Qt_m3s, res["Qt"] * 60.0 / 1000.0)],
             [u"Altura manométrica (demanda)", u"Ht = HMT",
              u"**{:.4f} mca**".format(res["P_RTI"])],
             [u"Eficiência global", u"η",
              u"**{:.0f}% = {:.2f}**".format(eta, eta_dec)]],
            alinhas=[u"left", u"left", u"left"])
    output.print_md(u"P_cv = (1000 × {:.6f} × {:.4f}) / (75 × {:.2f}) = {:.4f} / {:.4f}".format(
        Qt_m3s, res["P_RTI"], eta_dec,
        1000.0 * Qt_m3s * res["P_RTI"], 75.0 * eta_dec))
    output.print_md(u"**P_cv = {:.2f} cv  →  {:.2f} kW**".format(pot_cv, pot_kw))
    output.print_md(u"")


def _salvar_memorial(corpo, projeto_dir, nome_projeto):
    """
    Grava o memorial como .html na pasta do projeto e abre no visualizador
    padrão do sistema (janela fora do console do Revit). Retorna o caminho,
    ou None se não foi possível gravar.
    """
    nome = _re.sub(u"[^A-Za-z0-9_. -]", u"_", _txt(nome_projeto or u"projeto"))
    caminho = os.path.join(projeto_dir,
                           u"Memorial de Calculo - Hidrantes - {}.html".format(nome))
    documento = (
        u"<!DOCTYPE html><html lang='pt-br'><head><meta charset='utf-8'>"
        u"<title>Memorial de Cálculo — Hidrantes — {nome}</title><style>"
        u"body{{background:#ffffff;margin:0;padding:38px 46px;"
        u"font-family:'Segoe UI',Calibri,Arial,sans-serif;font-size:13.5px;}}"
        u"@media print{{body{{padding:0;}} .fu-memorial h2{{page-break-after:avoid;}}"
        u".fu-memorial table{{page-break-inside:avoid;}}}}"
        u"{css}</style></head><body><div class='fu-memorial'>{corpo}</div>"
        u"</body></html>"
    ).format(nome=_esc(nome), css=_CSS_ARQUIVO, corpo=corpo)

    try:
        with _io.open(caminho, "w", encoding="utf-8") as f:
            f.write(documento)
    except Exception:
        return None

    try:
        from System.Diagnostics import Process
        Process.Start(caminho)
    except Exception:
        try:
            os.startfile(caminho)
        except Exception:
            pass      # arquivo gravado; só não abriu sozinho
    return caminho


def print_memorial_calculo(console, res, dados_sistema, valor_sistema,
                           cotas, succao, verif_succao,
                           verif_npshd, erro_npshd, j_succao_npsh,
                           Qs_lmin, Pmin, C_HW,
                           eta, pot_cv, pot_kw, timestamp, perfil,
                           projeto_dir=None, nome_projeto=None):
    """
    Monta o memorial uma única vez e o entrega em dois lugares: no console
    do pyRevit (objeto `console`, de script.get_output() no chamador; usa
    folha de estilo própria, já que o tema do console sobrescreveria as
    tabelas) e como arquivo .html na pasta do projeto, aberto em janela
    separada.
    """
    global output
    doc_mem = _Memorial()
    output = doc_mem                      # as funções de montagem escrevem no buffer
    try:
        _montar_memorial(res, dados_sistema, valor_sistema,
                         cotas, succao, verif_succao,
                         verif_npshd, erro_npshd, j_succao_npsh,
                         Qs_lmin, Pmin, C_HW,
                         eta, pot_cv, pot_kw, timestamp, perfil)
    finally:
        output = console

    corpo = doc_mem.corpo()
    console.print_html(u"<style>{}</style><div class='fu-memorial'>{}</div>".format(
        _CSS_CONSOLE, corpo))

    caminho = _salvar_memorial(corpo, projeto_dir, nome_projeto) if projeto_dir else None
    if caminho:
        console.print_md(u"---")
        console.print_md(u"*Memorial salvo em* `{}` *— aberto em janela separada.*".format(
            caminho))

