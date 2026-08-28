# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes
Dimensionamento hidráulico pelo MÉTODO DA MARCHA (passo a passo):
HD01 → Ponto A → Descarga da Bomba → RTI, com ajuste da vazão do hidrante
mais favorável pelo Fator K. Imprime o memorial de cálculo no output do
pyRevit e salva cache para os demais botões.
(Nos elementos do Revit os identificadores gravados por 'Mapear Trechos'
continuam sendo "HID-01"/"HID-02"; no memorial a nomenclatura é HD01/HD02.)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import io as _io
import re as _re
import math as _math

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInParameter,
    LocationCurve, LocationPoint, UnitUtils,
)
from pyrevit import forms, script

try:
    from Autodesk.Revit.DB import UnitTypeId
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def to_m(val): return UnitUtils.ConvertFromInternalUnits(val, DisplayUnitType.DUT_METERS)

from projeto import exigir_projeto_e_estado
from hidrantes.calc import (
    calcular_rede, calc_potencia, extrair_trecho, salvar_cache,
    MCA_POR_BAR, METODO_VALVULA, METODOS_CALCULO,
    F_DARCY, K_VALVULA, COEF_JM, G,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
from hidrantes.norm_profiles import get_profile, req
from hidrantes import custom as custom_store
from hidrantes import succao as succao_calc

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_TRECHO           = u"FireUtils - Trecho"
P_IDENTIFICADOR    = u"FireUtils - Identificador"

# Simbolos de saida no output window do pyRevit (janela de output do pyRevit
# roda em unicode e normalmente exibe ✓/✗/≤ sem problema). Se algum ambiente
# nao renderizar esses caracteres, mude _ASCII_FALLBACK para True aqui -
# unico lugar do arquivo que define esses simbolos.
_ASCII_FALLBACK = False
if _ASCII_FALLBACK:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"OK", u"X", u"<=", u">="
else:
    SIM_OK, SIM_X, SIM_LE, SIM_GE = u"✓", u"✗", u"≤", u"≥"

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

# ===========================================================================
# HELPERS REVIT
# ===========================================================================

def get_trecho(elem):
    try:
        p = elem.LookupParameter(P_TRECHO)
        return p.AsString() if p else None
    except: return None

def get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        return p.AsString() if p else None
    except: return None

def get_comprimento(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        return to_m(p.AsDouble()) if p else 0.0
    except: return 0.0

def get_diametro(pipe):
    """
    Diâmetro NOMINAL (DN) do elemento — não o diâmetro interno real medido
    pelo schedule/material. Ex.: um tubo DN 65 pode ter diâmetro interno
    de 68,8 mm; o cálculo (Jun, J, V) usa o nominal, como no dimensionamento
    de referência. RBS_PIPE_DIAMETER_PARAM é o parâmetro "Diâmetro" do tubo
    (o tamanho nominal da lista de segmentos/tipos de tubo do Revit).
    """
    try:
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if p and p.AsDouble() > 0: return to_m(p.AsDouble())
        # Fallback: elemento sem "Diâmetro" nominal (ex.: acessório atípico)
        # usa o diâmetro interno, melhor que nada.
        p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_INNER_DIAM_PARAM)
        return to_m(p.AsDouble()) if p else 0.065
    except: return 0.065

def get_leq(elem):
    try:
        p = elem.LookupParameter(u"Perda de Carga")
        return p.AsDouble() if p else 0.0
    except: return 0.0

def get_nome(elem):
    try:    return elem.Symbol.Family.Name
    except: return u"(desconhecido)"

def get_z(elem, modo="mid"):
    loc = elem.Location
    if isinstance(loc, LocationCurve):
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        dz = abs(p1.Z - p0.Z)
        dh = ((p1.X - p0.X)**2 + (p1.Y - p0.Y)**2) ** 0.5
        if dz > dh and modo == "auto":
            try:
                conns = sorted(list(elem.ConnectorManager.Connectors), key=lambda c: c.Origin.Z)
                return to_m(conns[0].Origin.Z)
            except:
                return to_m(min(p0.Z, p1.Z))
        return (to_m(p0.Z) + to_m(p1.Z)) / 2.0
    if isinstance(loc, LocationPoint):
        return to_m(loc.Point.Z)
    bbox = elem.get_BoundingBox(None)
    if bbox:
        return (to_m(bbox.Min.Z) + to_m(bbox.Max.Z)) / 2.0
    return None


# ---------------------------------------------------------------------------
# Geometria da tomada de sucção (Anexo B da NT 22)
# ---------------------------------------------------------------------------
# O tipo de tomada (lateral / superior / inferior) muda a verificação do nível
# X — é ele que decide se o dispositivo antivórtice pode dispensar a dimensão
# A (B.3.5/B.3.6). Em vez de perguntar ao usuário, ele é lido da própria
# geometria do modelo: a inclinação do eixo do tubo da tomada e qual das suas
# pontas está aberta para a água do reservatório.
#
# Ângulos entre o eixo do tubo e o plano horizontal que separam as três faixas.
ANG_VERTICAL   = 60.0
ANG_HORIZONTAL = 30.0


def _ponto(elem):
    """Ponto representativo do elemento, em coordenadas internas do Revit."""
    loc = getattr(elem, "Location", None)
    if isinstance(loc, LocationPoint):
        return loc.Point
    if isinstance(loc, LocationCurve):
        return loc.Curve.Evaluate(0.5, True)
    bbox = elem.get_BoundingBox(None)
    if bbox:
        return bbox.Min.Add(bbox.Max).Divide(2.0)
    return None


def get_orientacao(elem):
    """
    Orientação do eixo do elemento: "vertical", "horizontal" ou "inclinado",
    com o ângulo em graus. (None, None) quando o elemento não tem eixo.
    """
    loc = getattr(elem, "Location", None)
    if not isinstance(loc, LocationCurve):
        return None, None

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dz = abs(p1.Z - p0.Z)
    dh = ((p1.X - p0.X) ** 2 + (p1.Y - p0.Y) ** 2) ** 0.5
    if dz < 1e-9 and dh < 1e-9:
        return None, None

    ang = _math.degrees(_math.atan2(dz, dh))
    if ang >= ANG_VERTICAL:
        return u"vertical", ang
    if ang <= ANG_HORIZONTAL:
        return u"horizontal", ang
    return u"inclinado", ang


def _extremidade_aberta(elem):
    """
    "topo" ou "fundo" conforme a ponta SEM conexão do tubo — é ela que fica
    aberta para a água do reservatório. None quando não dá para decidir
    (nenhuma ponta livre, as duas livres, ou tubo sem desnível).
    """
    try:
        conns = [c for c in elem.ConnectorManager.Connectors]
    except Exception:
        return None

    livres = [c for c in conns if not c.IsConnected]
    if len(conns) < 2 or len(livres) != 1:
        return None

    zs = [c.Origin.Z for c in conns]
    if abs(max(zs) - min(zs)) < 1e-6:
        return None

    z_livre = livres[0].Origin.Z
    return u"topo" if abs(z_livre - max(zs)) < abs(z_livre - min(zs)) else u"fundo"


def detectar_tipo_tomada(elem_rti, candidatos=None):
    """
    Classifica a tomada de sucção pela geometria do modelo.

    Tubo horizontal atravessa a parede do reservatório → tomada LATERAL
    (Figuras B.1/B.2). Tubo vertical pode ser das duas formas restantes, e
    quem separa é a ponta aberta: aberta em cima, o tubo desce a partir da
    boca e sai pelo fundo → tomada INFERIOR (Figura B.3); aberta embaixo, o
    tubo mergulha no reservatório vindo de cima → tomada SUPERIOR.

    Quando o elemento identificado como "RTI" não tem eixo próprio (uma
    conexão ou acessório, por exemplo), usa o tubo do trecho de sucção mais
    próximo dele.

    Retorna dict com o tipo, o elemento usado, a orientação, o ângulo e a
    confiança da leitura ("alta" quando a geometria decidiu sozinha).
    """
    elem_geo = elem_rti
    orientacao, ang = get_orientacao(elem_rti)

    if orientacao is None and candidatos:
        origem = _ponto(elem_rti)
        melhor, menor = None, None
        for cand in candidatos:
            o, _a = get_orientacao(cand)
            p = _ponto(cand)
            if o is None or p is None or origem is None:
                continue
            d = origem.DistanceTo(p)
            if menor is None or d < menor:
                melhor, menor = cand, d
        if melhor is not None:
            elem_geo = melhor
            orientacao, ang = get_orientacao(melhor)

    if orientacao is None:
        return {u"tipo": succao_calc.TOMADA_SUPERIOR, u"elem": None,
                u"orientacao": None, u"angulo": None, u"confianca": u"baixa",
                u"base": u"não foi possível ler o eixo do tubo da tomada; "
                         u"adotada tomada superior (a dimensão A sempre se "
                         u"aplica), conferir manualmente"}

    if orientacao == u"horizontal":
        return {u"tipo": succao_calc.TOMADA_LATERAL, u"elem": elem_geo,
                u"orientacao": orientacao, u"angulo": ang, u"confianca": u"alta",
                u"base": u"tubo da tomada na horizontal ({:.1f}° com o plano "
                         u"horizontal) — captação pela parede".format(ang)}

    if orientacao == u"inclinado":
        return {u"tipo": succao_calc.TOMADA_LATERAL, u"elem": elem_geo,
                u"orientacao": orientacao, u"angulo": ang, u"confianca": u"baixa",
                u"base": u"tubo da tomada inclinado ({:.1f}°), sem enquadrar "
                         u"nas figuras do Anexo B; adotada tomada lateral (a "
                         u"dimensão A sempre se aplica), conferir "
                         u"manualmente".format(ang)}

    aberta = _extremidade_aberta(elem_geo)
    if aberta == u"topo":
        return {u"tipo": succao_calc.TOMADA_INFERIOR, u"elem": elem_geo,
                u"orientacao": orientacao, u"angulo": ang, u"confianca": u"alta",
                u"base": u"tubo da tomada na vertical ({:.1f}°) com a boca "
                         u"aberta na extremidade superior — captação pelo "
                         u"fundo (Figura B.3)".format(ang)}
    if aberta == u"fundo":
        return {u"tipo": succao_calc.TOMADA_SUPERIOR, u"elem": elem_geo,
                u"orientacao": orientacao, u"angulo": ang, u"confianca": u"alta",
                u"base": u"tubo da tomada na vertical ({:.1f}°) com a boca "
                         u"aberta na extremidade inferior — captação por "
                         u"cima".format(ang)}

    return {u"tipo": succao_calc.TOMADA_SUPERIOR, u"elem": elem_geo,
            u"orientacao": orientacao, u"angulo": ang, u"confianca": u"baixa",
            u"base": u"tubo da tomada na vertical ({:.1f}°), mas as duas "
                     u"pontas estão conectadas — não dá para distinguir "
                     u"captação pelo fundo de captação por cima; adotada "
                     u"tomada superior (a dimensão A sempre se aplica), "
                     u"conferir manualmente".format(ang)}

# ===========================================================================
# MEMORIAL DE CÁLCULO — passo a passo (método da marcha)
# ===========================================================================

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

    _tabela([u"DN (mm)", u"Nº tubos", u"L (m)", u"Leq (m)", u"Ltotal (m)"],
            [[u"{:.1f}".format(s["d_mm"]), u"{}".format(s["n_tubos"]),
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

_TOMADA_DESC = {
    u"lateral":  u"lateral — captação pela parede do reservatório (Fig. B.1/B.2)",
    u"superior": u"superior — captação por cima, tubo mergulhado (Fig. B.1/B.2)",
    u"inferior": u"inferior — captação pelo fundo do reservatório (Fig. B.3)",
}


def _secao_condicao_succao(v, erro, succao, Hz_succao):
    """
    Verificação da condição de sucção pelo nível X — o nível mínimo de água
    antes da formação de vórtice (Anexo B.3 / item C.1.10 da NT 22).
    """
    if v is None:
        output.print_md(
            u"{} **Não foi possível verificar o nível X:** {}".format(SIM_X, erro))
        output.print_md(
            u"Na falta dessa verificação a condição de sucção caiu no critério "
            u"geométrico simples — **sucção {}**, pelo desnível entre a cota da "
            u"RTI e a da sucção da bomba (∆H = {:.4f} m). **Confira o Anexo B "
            u"manualmente.**".format(succao, Hz_succao))
        output.print_md(u"")
        return

    output.print_md(
        u"A condição de sucção não é dada pelo desnível direto entre a RTI e a "
        u"bomba, e sim pela posição do eixo do rotor em relação ao **nível X** — "
        u"o nível mínimo de água antes da formação de vórtice (B.3.4).")

    _tabela([u"Dado", u"Valor"],
            [[u"Cota do fundo do reservatório", u"{:.4f} m".format(v[u"cota_fundo"])],
             [u"Tipo de tomada de sucção",
              u"**{}**".format(_TOMADA_DESC.get(v[u"tipo_tomada"], v[u"tipo_tomada"]))],
             [u"Origem do tipo de tomada", v[u"origem_tomada"]],
             [u"Cota da tomada de sucção", u"**{:.4f} m**".format(v[u"cota_tomada"])],
             [u"Diâmetro do tubo de sucção", u"DN {:g} mm".format(v[u"dn_succao_mm"])],
             [u"Dimensão A (Tabela B.1)", u"**{:.3f} m**".format(v[u"dimensao_A"])],
             [u"Dimensão B (Tabela B.1)",
              u"{:.3f} m".format(v[u"dimensao_B_mm"] / 1000.0)],
             [u"Cota do eixo do rotor da bomba",
              u"**{:.4f} m**".format(v[u"cota_eixo_rotor"])]])

    output.print_md(u"_{}._".format(v[u"observacao_A"]))
    if v[u"possui_poco_succao"]:
        output.print_md(u"_Reservatório com poço de sucção._")
    if v.get(u"confianca_deteccao") == u"baixa":
        output.print_md(
            u"{} **A geometria do modelo não determinou o tipo de tomada com "
            u"segurança** — foi adotado o tipo que sempre exige a dimensão A, "
            u"o lado conservador. Confira contra o Anexo B e, se preciso, "
            u"informe o tipo em 'Classificar Sistema'.".format(SIM_X))
    output.print_md(u"")

    _formula(u"Nível X = cota da tomada de sucção + A",
             [(u"Nível X", u"Nível mínimo de água antes da formação de vórtice"),
              (u"A", u"Dimensão da Tabela B.1, em função do DN da sucção")])
    output.print_md(u"Nível X = {:.4f} + {:.3f} = **{:.4f} m**".format(
        v[u"cota_tomada"], v[u"dimensao_A"], v[u"nivel_X"]))
    output.print_md(u"")

    # Capacidade efetiva (B.3.3) — o volume abaixo do nível X não é utilizável,
    # e é a capacidade efetiva que se compara com a RTI mínima da Tabela 3.
    if v[u"capacidade_efetiva"] is not None:
        output.print_md(u"**Capacidade efetiva da RTI** (B.3.3) — o volume abaixo "
                        u"do nível X não é utilizável:")
        _tabela([u"Parcela", u"Valor"],
                [[u"Volume total do reservatório",
                  u"{:.3f} m³".format(v[u"volume_total"])],
                 [u"Área em planta", u"{:.3f} m²".format(v[u"area_planta"])],
                 [u"Altura não utilizável (fundo ao nível X)",
                  u"{:.4f} m".format(v[u"altura_nao_utilizavel"])],
                 [u"Volume não utilizável",
                  u"{:.3f} m³".format(v[u"volume_nao_utilizavel"])],
                 [u"**Capacidade efetiva**",
                  u"**{:.3f} m³**".format(v[u"capacidade_efetiva"])]])
        output.print_md(u"{} É a **capacidade efetiva** — não o volume total — que "
                        u"deve ser comparada com a RTI mínima exigida pela Tabela 3.".format(
                            SIM_OK))
        output.print_md(u"")

    output.print_md(u"**Verificação** (item C.1.10):")
    output.print_md(v[u"justificativa"])
    output.print_md(u"")

    marca = SIM_X if v[u"condicao"] == succao_calc.COND_NEGATIVA else SIM_OK
    output.print_md(u"{} **Condição de sucção adotada: {}**".format(
        marca, v[u"condicao"]))

    if v[u"exige_npsh"]:
        output.print_md(u"")
        alerta = (u"{} **Sucção negativa — exige cálculo do NPSH disponível** "
                  u"(item 5.8.16).".format(SIM_X))
        if v[u"vazao_npsh_lmin"] is not None:
            alerta += (u" A verificação usa **1,5 × a vazão nominal** do sistema: "
                       u"1,5 × {:.2f} = **{:.2f} L/min** — não a vazão de projeto "
                       u"normal.".format(v[u"vazao_npsh_lmin"] / succao_calc.FATOR_VAZAO_NPSH,
                                         v[u"vazao_npsh_lmin"]))
        output.print_md(alerta)
        output.print_md(u"O NPSH disponível não é calculado por este comando — "
                        u"deve ser verificado à parte contra o NPSH requerido da "
                        u"bomba escolhida.")
    output.print_md(u"")


def _montar_memorial(res, dados_sistema, valor_sistema,
                     cotas, succao, Hz_succao, verif_succao, erro_succao,
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

    # ── Condição de sucção pelo nível X ───────────────────────────────────
    sec(u"Verificação da Condição de Sucção")
    _secao_condicao_succao(verif_succao, erro_succao, succao, Hz_succao)

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

    if esguicho:
        output.print_md(u"**{}) Esguicho, mangueira e válvula do hidrante** — como o par "
                        u"normativo (Q, Pmin) está referido à ponta do esguicho, a "
                        u"pressão sobe até a válvula somando as perdas da mangueira e "
                        u"da válvula angular:".format(prox()))
        _formula_frac(u"Jm", u"{:g}·f·Lm".format(COEF_JM), u"g·π²·Dm⁵",
                     depois=u"· Q²", sufixo=u"[mca]",
                     definicoes=[(u"Jm", u"Perda de carga na mangueira (Darcy-Weisbach)"),
                                (u"f", u"Fator de atrito = {:g}".format(F_DARCY)),
                                (u"Lm", u"Comprimento da mangueira, em m"),
                                (u"g", u"Aceleração da gravidade = {:g} m/s²".format(G)),
                                (u"Dm", u"Diâmetro da mangueira, em m")])
        _formula_frac(u"V", u"21,22 · Q", u"Dm²", sufixo=u"[m/s]",
                     definicoes=[(u"V", u"Velocidade do fluido na mangueira")])
        _formula_frac(u"Jvalv", u"K · V²", u"2g", sufixo=u"[mca]",
                     definicoes=[(u"Jvalv", u"Perda de carga na válvula angular do hidrante"),
                                (u"K", u"Fator K da válvula, adotado = {:g}".format(K_VALVULA))])
        _formula(u"P_valv = Pmin + Jm + Jvalv",
                 [(u"P_valv", u"Pressão na válvula do hidrante, soma das perdas "
                              u"entre o esguicho e a válvula")])

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
                    u"normativa Q = {:g} L/min.".format(Qs_lmin))
    output.print_md(u"")
    prox = _contador_letras()
    _passo_ltotal(j["t3"], prox())
    _passo_perda(j["t3"], C_HW, prox())
    _passo_velocidade(j["t3"], v_max_tubo, prox())

    if esguicho:
        _ref   = esg["ref"]
        _dm_mm = esg["mang_dn_mm"]
        _lm    = esg["mang_comp_m"]
        output.print_md(u"**{}) Esguicho, mangueira e válvula do hidrante**".format(prox()))
        output.print_md(u"A perda de carga no esguicho é a própria **pressão mínima "
                        u"exigida em projeto (Pmin = {:g} mca)**, aplicada na ponta do "
                        u"esguicho. Da ponta até a válvula somam-se a perda na mangueira "
                        u"e a perda na válvula angular.".format(Pmin))
        output.print_md(u"")
        output.print_md(u"Mangueira: Lm = {:g} m, Dm = {:g} mm.".format(_lm, _dm_mm))
        _tabela([u"Grandeza", u"Valor"],
                [[u"Jm — perda na mangueira", u"**{:.4f} mca**".format(_ref["Jm"])],
                 [u"V — velocidade na mangueira", u"**{:.4f} m/s**".format(_ref["V"])],
                 [u"Jvalv — perda na válvula angular",
                  u"**{:.4f} mca**".format(_ref["Jvalv"])]])
        output.print_md(u"P_valv = Pmin + Jm + Jvalv = {:g} + {:.4f} + {:.4f} = "
                        u"**{:.4f} mca**".format(
                            Pmin, _ref["Jm"], _ref["Jvalv"], P_ref))
        output.print_md(u"")

    output.print_md(u"**{}) Fator K** — calculado aqui, no 1º hidrante mais "
                    u"desfavorável, e reaproveitado nos demais trechos.".format(prox()))
    _formula_frac(u"K", u"Q", u"√P")
    output.print_md(u"K = {:g} / √({:.4f} / {}) = {:g} / √{:.4f} = "
                    u"**{:.4f} L/min/bar^0,5**".format(
                        Qs_lmin, P_ref, MCA_POR_BAR, Qs_lmin,
                        P_ref / MCA_POR_BAR, K))
    output.print_md(u"")

    output.print_md(u"**{}) Pressão necessária no Ponto A** pelo ramal do HD01:".format(prox()))
    output.print_md(u"P_PA = {} + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        _P_ref_lbl, P_ref, j["t3"]["J"], _fmt_dh(dH["t3"]), res["P_PA1"]))
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
    output.print_md(u"P_PA = {} + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        _P_ref_lbl, P_ref, j["t4"]["J"], _fmt_dh(dH["t4"]), res["P_PA2"]))
    output.print_md(u"")

    # Ponto A e vazões finais pelo Fator K (sem ciclo)
    output.print_md(u"### {}.3 Pressão no Ponto A e Vazões Finais (Fator K)".format(n7))
    output.print_md(u"Pressão adotada no Ponto A = maior pressão calculada entre os "
                    u"dois trechos: P_PA = max({:.4f}; {:.4f}) = **{:.4f} mca** "
                    u"(ramal governante: **{}**)".format(
                        res["P_PA1"], res["P_PA2"], res["P_PA"], res["hid_governa"]))
    output.print_md(u"")
    output.print_md(u"Com o Ponto A nessa pressão, a pressão na válvula de cada hidrante "
                    u"vem da marcha inversa (o ramal governante retorna, por construção, "
                    u"exatamente à pressão de referência):")
    _formula(u"P_hd = P_PA − J ∓ ∆H")
    output.print_md(u"P_hd01 = {:.4f} {} {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], u"−", j["t3"]["J"], _fmt_dh(-dH["t3"]), res["P_hd01"]))
    output.print_md(u"P_hd02 = {:.4f} {} {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], u"−", j["t4"]["J"], _fmt_dh(-dH["t4"]), res["P_hd02"]))
    output.print_md(u"")
    _formula(u"Q = K · √P")
    output.print_md(u"Q_hd01 = {:.4f} · √({:.4f} / {}) = **{:.2f} L/min**".format(
        K, res["P_hd01"], MCA_POR_BAR, res["Q_hd01"]))
    output.print_md(u"Q_hd02 = {:.4f} · √({:.4f} / {}) = **{:.2f} L/min**".format(
        K, res["P_hd02"], MCA_POR_BAR, res["Q_hd02"]))
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
    output.print_md(u"P_SB = P_PA + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_PA"], j["t2"]["J"], _fmt_dh(dH["t2"]), res["P_SB"]))
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
    output.print_md(u"P_RTI = P_SB + J ± ∆H = {:.4f} + {:.4f} {} = **{:.4f} mca**".format(
        res["P_SB"], j["t1"]["J"], _fmt_dh(dH["t1"]), res["P_RTI"]))
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


def print_memorial_calculo(res, dados_sistema, valor_sistema,
                           cotas, succao, Hz_succao, verif_succao, erro_succao,
                           Qs_lmin, Pmin, C_HW,
                           eta, pot_cv, pot_kw, timestamp, perfil,
                           projeto_dir=None, nome_projeto=None):
    """
    Monta o memorial uma única vez e o entrega em dois lugares: no console
    do pyRevit (com folha de estilo própria, já que o tema do console
    sobrescreveria as tabelas) e como arquivo .html na pasta do projeto,
    aberto em janela separada.
    """
    global output
    console = output
    doc_mem = _Memorial()
    output = doc_mem                      # as funções de montagem escrevem no buffer
    try:
        _montar_memorial(res, dados_sistema, valor_sistema,
                         cotas, succao, Hz_succao, verif_succao, erro_succao,
                         Qs_lmin, Pmin, C_HW,
                         eta, pot_cv, pot_kw, timestamp, perfil)
    finally:
        output = console

    corpo = doc_mem.corpo()
    output.print_html(u"<style>{}</style><div class='fu-memorial'>{}</div>".format(
        _CSS_CONSOLE, corpo))

    caminho = _salvar_memorial(corpo, projeto_dir, nome_projeto) if projeto_dir else None
    output.print_md(u"---")
    if caminho:
        output.print_md(u"*Memorial salvo em* `{}` *— aberto em janela separada.*".format(
            caminho))
    output.print_md(u"*Cache salvo em firedata.json (chave 'hidrantes').*")


# ===========================================================================
# MAIN
# ===========================================================================

# --- Verificar projeto salvo e estado configurado ---
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)

# --- Perfil normativo ativo (UF do projeto, default "MA") ---
perfil = get_profile(sigla_estado)

# --- Etapa 1: tipo de sistema ---
param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
if not param_sistema or not param_sistema.AsString():
    forms.alert(u"Execute 'Classificar Sistema de Hidrante' primeiro.",
                title="Fire Utils", warn_icon=True)
    script.exit()

valor_sistema = param_sistema.AsString()

if custom_store.is_custom(valor_sistema):
    # Sistema classificado com valores personalizados (fora da Tabela 2).
    # Os valores vêm do JSON salvo no próprio projeto, não do perfil normativo.
    _custom = custom_store.load_custom(doc)
    if not _custom:
        forms.alert(
            u"O projeto está classificado como sistema personalizado, mas os "
            u"valores não foram encontrados.\n\nExecute "
            u"'Classificar Sistema de Hidrante' novamente.",
            title="Fire Utils", warn_icon=True)
        script.exit()
    dados_sistema = custom_store.para_dados_sistema(_custom)
else:
    try:    tipo_num = int(valor_sistema.split()[1])
    except:
        forms.alert(u"Não foi possível interpretar o tipo.", title="Fire Utils", warn_icon=True)
        script.exit()

    variante_idx = 0
    if u"Var." in valor_sistema:
        try:    variante_idx = ord(valor_sistema.split(u"Var.")[1].strip()[0]) - 65
        except: variante_idx = 0

    _tipo_perfil = req(perfil, u"tipos").get(tipo_num)
    if _tipo_perfil is None:
        forms.alert(
            u"O perfil normativo '{}' não define o Tipo {} de sistema de hidrante.".format(
                perfil.get(u"norma"), tipo_num),
            title="Fire Utils", warn_icon=True)
        script.exit()

    dados_sistema = dict(_tipo_perfil["variantes"][variante_idx])
    dados_sistema["esguicho_dn"] = _tipo_perfil["esguicho_dn"]

# A Tabela 2 (hidrantes/db.py) guarda esses valores como int. O IronPython
# 2.7 do Revit (diferente do CPython) lança ValueError em "{:.1f}".format(x)
# quando x é int — então normalizamos tudo para float aqui, no único ponto
# de entrada dos dois caminhos (Tabela 2 e personalizado; este último já
# vem normalizado de custom_store, mas o float() abaixo é inofensivo).
for _chave in (u"q_min", u"p_min", u"mang_dn", u"mang_comp", u"esguicho_dn"):
    dados_sistema[_chave] = float(dados_sistema[_chave])

Qs_lmin = dados_sistema["q_min"]
Pmin    = dados_sistema["p_min"]
C_HW    = req(perfil, u"hazen_c")[u"galvanizado"]

# --- Etapa 1b: método de cálculo (define ONDE Qs/Pmin se aplicam) ---
# Gravado por "Classificar Sistema". Projetos classificados antes desse
# parâmetro existir caem no método da válvula (comportamento anterior).
_param_metodo = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
metodo_calculo = _param_metodo.AsString() if _param_metodo else None
if metodo_calculo not in METODOS_CALCULO:
    if metodo_calculo:
        forms.alert(
            u"Método de cálculo desconhecido no projeto:\n'{}'\n\n"
            u"Execute 'Classificar Sistema de Hidrante' novamente.".format(
                metodo_calculo),
            title="Fire Utils", warn_icon=True)
        script.exit()
    metodo_calculo = METODO_VALVULA

# --- Etapa 2: captura de elementos ---
TRECHOS = [u"RTI - Bomba", u"Bomba - Ponto A", u"Ponto A - Hid 01", u"Ponto A - Hid 02"]
trechos_elems = {t: [] for t in TRECHOS}
ident_map = {}; hid_map = {}

for elem in FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType().ToElements():
    t = get_trecho(elem)
    if t in trechos_elems: trechos_elems[t].append(elem)
    i = get_identificador(elem)
    if i: ident_map[i] = elem
    if isinstance(elem, FamilyInstance):
        try:
            p = elem.LookupParameter(u"FireUtils - Identificador")
            if p and p.AsString() in (u"HID-01", u"HID-02"):
                hid_map[p.AsString()] = elem
        except: pass

erros = []
for t in TRECHOS:
    if not trechos_elems[t]: erros.append(u"Trecho '{}' vazio".format(t))
for i in [u"RTI", u"Succao", u"Recalque", u"Ponto A"]:
    if i not in ident_map: erros.append(u"Identificador '{}' não encontrado".format(i))
for h in [u"HID-01", u"HID-02"]:
    if h not in hid_map: erros.append(u"'{}' não encontrado".format(h))
if erros:
    forms.alert(u"Elementos não encontrados:\n{}\n\nExecute 'Mapear Trechos' primeiro.".format(
        u"\n".join(erros)), title="Fire Utils", warn_icon=True)
    script.exit()

# --- Etapa 3: cotas altimétricas de todos os pontos da marcha ---
cotas = {
    "z_rti":      get_z(ident_map[u"RTI"],      modo="auto"),
    "z_succao":   get_z(ident_map[u"Succao"],   modo="auto"),
    "z_recalque": get_z(ident_map[u"Recalque"], modo="auto"),
    "z_ponto_a":  get_z(ident_map[u"Ponto A"]),
    "z_hd01":     get_z(hid_map[u"HID-01"]),
    "z_hd02":     get_z(hid_map[u"HID-02"]),
}

_nomes_cotas = {
    "z_rti": u"RTI", "z_succao": u"Sucção", "z_recalque": u"Recalque",
    "z_ponto_a": u"Ponto A", "z_hd01": u"HID-01", "z_hd02": u"HID-02",
}
erros_z = [_nomes_cotas[k] for k, z in cotas.items() if z is None]
if erros_z:
    forms.alert(u"Não foi possível ler a elevação de:\n{}".format(u"\n".join(erros_z)),
                title="Fire Utils", warn_icon=True)
    script.exit()

# Desnível geométrico entre a tomada de água e a sucção da bomba. Continua
# sendo usado no memorial e no cache, mas já NÃO decide sozinho a condição de
# sucção — quem decide é a verificação pelo nível X, logo abaixo.
Hz_succao = cotas["z_rti"] - cotas["z_succao"]

# --- Etapa 3b: condição de sucção pelo NÍVEL X (Anexo B.3 / C.1.10) ---
# O tipo de tomada sai da geometria do modelo (orientação do tubo da tomada e
# qual das suas pontas está aberta para a água); os dados que não existem no
# modelo — fundo, volume e área do reservatório, antivórtice, poço de sucção —
# vêm do que ficou salvo no projeto por "Classificar Sistema".
dados_succao = succao_calc.load_dados(doc) or succao_calc.default_dados()

deteccao_tomada = detectar_tipo_tomada(ident_map[u"RTI"],
                                       trechos_elems[u"RTI - Bomba"])

# Uma escolha manual salva no projeto tem precedência sobre a leitura da
# geometria — o desenho nem sempre representa a tomada real.
if dados_succao.get(u"tipo_tomada"):
    tipo_tomada = dados_succao[u"tipo_tomada"]
    origem_tomada = u"informado manualmente no projeto"
else:
    tipo_tomada = deteccao_tomada[u"tipo"]
    origem_tomada = u"detectado da geometria: {}".format(deteccao_tomada[u"base"])

# DN da sucção: o do próprio tubo da tomada quando a geometria o identificou;
# senão o maior DN do trecho de sucção.
dn_succao_mm = None
if deteccao_tomada[u"elem"] is not None:
    _d = get_diametro(deteccao_tomada[u"elem"])
    if _d:
        dn_succao_mm = _d * 1000.0

# --- Etapa 4: extrair dados dos trechos (por diâmetro) e resolver a marcha ---
trechos_data = {
    "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome),
}

if dn_succao_mm is None and trechos_data["t1"]:
    dn_succao_mm = max(s["d_mm"] for s in trechos_data["t1"])

res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas,
                    metodo=metodo_calculo,
                    mang_dn_mm=dados_sistema["mang_dn"],
                    mang_comp_m=dados_sistema["mang_comp"])

# Verificação pelo nível X — precisa da vazão total (Qt) resolvida acima, que
# é a vazão nominal de referência do gatilho de NPSH (1,5·Qt, item 5.8.16).
# A cota da tomada é a da RTI e a do eixo do rotor é a da sucção da bomba;
# quando o DN da sucção cai fora da faixa da Tabela B.1 a verificação não pode
# ser feita e o memorial registra a pendência em vez de inventar um nível X.
erro_succao = None
try:
    verif_succao = succao_calc.verificar_condicao_succao(
        cota_tomada_succao      = cotas["z_rti"],
        cota_eixo_rotor_bomba   = cotas["z_succao"],
        dn_succao_mm            = dn_succao_mm,
        tipo_tomada             = tipo_tomada,
        cota_fundo_reservatorio = dados_succao[u"cota_fundo_reservatorio"],
        possui_dispositivo_antivortice = dados_succao[u"possui_antivortice"],
        possui_poco_succao      = dados_succao[u"possui_poco_succao"],
        volume_total_m3         = dados_succao[u"volume_total_m3"],
        area_planta_m2          = dados_succao[u"area_planta_m2"],
        q_nominal_lmin          = res["Qt"],
    )
    # Só o resumo textual da detecção entra no dict — o elemento do Revit em
    # deteccao_tomada["elem"] não é serializável no cache.
    verif_succao[u"origem_tomada"]     = origem_tomada
    verif_succao[u"orientacao_tubo"]   = deteccao_tomada[u"orientacao"]
    verif_succao[u"angulo_tubo"]       = deteccao_tomada[u"angulo"]
    verif_succao[u"confianca_deteccao"] = deteccao_tomada[u"confianca"]
    succao = verif_succao[u"succao_simples"]
except ValueError as _e:
    # DN fora da Tabela B.1: sem nível X, cai no critério geométrico simples
    # e o memorial pede a conferência manual.
    erro_succao  = _txt(_e)
    verif_succao = None
    succao = u"negativa" if Hz_succao < -0.001 else u"positiva"
    forms.alert(u"{}\n\nA condição de sucção foi classificada apenas pelo "
                u"desnível geométrico — confira o Anexo B manualmente.".format(erro_succao),
                title="Fire Utils", warn_icon=True)

# --- Etapa 5: eficiência e potência da bomba ---
eta_str = forms.ask_for_string(
    default="60",
    prompt=u"Eficiência global da bomba (%)\nEx: 60",
    title=u"Fire Utils — Eficiência"
)
if not eta_str:
    output.print_md(u"Cancelado."); script.exit()
try:
    eta = float(eta_str.replace(",", "."))
    if not (0 < eta <= 100): raise ValueError
except ValueError:
    forms.alert(u"Valor inválido.", title="Fire Utils", warn_icon=True)
    script.exit()

eta_dec = eta / 100.0
pot_cv  = calc_potencia(res["Qt"] / 60000.0, res["P_RTI"], eta_dec)
pot_kw  = pot_cv / 1.36

# --- Etapa 6: memorial de cálculo ---
import datetime
timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
print_memorial_calculo(
    res, dados_sistema, valor_sistema,
    cotas, succao, Hz_succao, verif_succao, erro_succao,
    Qs_lmin, Pmin, C_HW,
    eta, pot_cv, pot_kw, timestamp, perfil,
    projeto_dir=projeto_dir, nome_projeto=doc.Title,
)

# --- Etapa 7: salvar cache ---
payload_hid = {
    "res":           res,
    "dados_sistema": dados_sistema,
    "valor_sistema": valor_sistema,
    "metodo":        metodo_calculo,
    "cotas":         cotas,
    "Hz_succao":     Hz_succao,
    "succao":        succao,
    "verif_succao":  verif_succao,
    "dados_succao":  dados_succao,
    "C_HW":          C_HW,
    "uf":            perfil.get(u"_uf_efetiva"),
    "eta":           eta,
    "pot_cv":        pot_cv,
    "pot_kw":        pot_kw,
    "_nome_projeto": doc.Title,
}
salvar_cache(payload_hid, projeto_dir)
