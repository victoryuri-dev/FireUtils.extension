# -*- coding: utf-8 -*-
"""
script.py — Fire Utils · Dimensionar Hidrantes
Dimensionamento hidráulico pelo MÉTODO DA MARCHA (passo a passo):
HD01 → Ponto A → Descarga da Bomba → RTI, com ajuste da vazão do hidrante
mais favorável pelo Fator K.

Ao final, mostra só as verificações e os resultados finais (velocidade nos
trechos, pressão/vazão nos hidrantes mais desfavoráveis, demanda do sistema
e requisitos da bomba) — não o memorial de cálculo completo, que agora é o
botão separado "Memorial de Cálculo". Se alguma verificação não atender a
norma, o dimensionamento para naquele ponto e mostra onde corrigir, em vez
de seguir adiante com um resultado que não atende.

Salva os resultados completos no cache (firedata.json) para o botão
"Memorial de Cálculo" reimprimir o passo a passo sem recalcular.
(Nos elementos do Revit os identificadores gravados por 'Mapear Trechos'
continuam sendo "HID-01"/"HID-02"; no memorial a nomenclatura é HD01/HD02.)
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import io as _io
import re as _re

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, BuiltInParameter,
    FlowDirectionType, ConnectorType, ElementId,
    LocationCurve, LocationPoint, UnitUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from System.Collections.Generic import List
from System import Int64
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
    METODO_VALVULA, METODOS_CALCULO, calc_j_trecho,
    COMPRIMENTO_MIN_VERIF_VELOCIDADE_M,
)
from hidrantes.resultado_ui import (
    mostrar_bloqueio_velocidade, mostrar_bloqueio_hidrante,
    mostrar_bloqueio_equilibrio, mostrar_resultado_ok,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
from hidrantes.norm_profiles import get_profile, req, opt
from hidrantes import custom as custom_store
from hidrantes import succao as succao_calc
from hidrantes import npshd as npshd_calc

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_TRECHO           = u"FireUtils - Trecho"
P_IDENTIFICADOR    = u"FireUtils - Identificador"

# IronPython 2.7 (engine do pyRevit) tem 'unicode'; CPython 3 não.
try:
    _txt = unicode
except NameError:
    _txt = str

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

# ===========================================================================
# HELPERS REVIT
# ===========================================================================

def get_id(elem):
    """ElementId como int nativo do Python — para gravar no cache (JSON,
    que não serializa o Int64/Int32 do .NET direto) e usar no botão
    "Mostrar no Projeto" das janelas de bloqueio."""
    try:    return int(elem.Id.Value)
    except: return int(elem.Id.IntegerValue)

def mostrar_no_revit(ids):
    """Seleciona e enquadra, na view ativa do Revit, os elementos cujo
    ElementId (int) está em `ids` — callback do botão "Mostrar no
    Projeto" das janelas de bloqueio (resultado_ui.py). Qualquer falha
    aparece num alert (nunca engolida em silêncio, senão o clique some
    sem dar pista nenhuma do que houve) e ao final o foco volta para a
    janela principal do Revit — depois que a janela de bloqueio (WPF)
    fecha, o foco costuma ficar com o console do pyRevit, não com o
    Revit, então a seleção acontece mas ninguém vê."""
    if not ids:
        return
    try:
        # ElementId(int) é ambíguo no IronPython nas versões do Revit que
        # também têm ElementId(BuiltInParameter)/ElementId(BuiltInCategory)
        # (2024+) — Int64(i) força o overload certo.
        eids = List[ElementId]([ElementId(Int64(i)) for i in ids])
        uidoc.Selection.SetElementIds(eids)
        uidoc.ShowElements(eids)
        uidoc.RefreshActiveView()
    except Exception as _e:
        forms.alert(u"Não foi possível selecionar os elementos no Revit:\n{}".format(_e),
                    title="Fire Utils", warn_icon=True)
        return
    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(__revit__.MainWindowHandle)
    except Exception:
        pass

def get_trecho(elem):
    try:
        p = elem.LookupParameter(P_TRECHO)
        return p.AsString() if p else None
    except: return None

def get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        if not p or not p.HasValue: return None
        valor = p.AsString()
        return valor.strip() if valor else None
    except: return None

def get_comprimento(pipe):
    try:
        p = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        return to_m(p.AsDouble()) if p else 0.0
    except: return 0.0

def get_diametro(elem):
    """
    Diâmetro NOMINAL (DN) do elemento — não o diâmetro interno real medido
    pelo schedule/material. Ex.: um tubo DN 65 pode ter diâmetro interno
    de 68,8 mm; o cálculo (Jun, J, V) usa o nominal, como no dimensionamento
    de referência. RBS_PIPE_DIAMETER_PARAM é o parâmetro "Diâmetro" do tubo
    (o tamanho nominal da lista de segmentos/tipos de tubo do Revit).

    Para um Pipe o diâmetro TEM que ser lido com sucesso: um fallback
    silencioso aqui faria dois tubos de tamanhos diferentes caírem no
    mesmo valor "adivinhado" e o dimensionamento perderia a diferença
    real de velocidade entre eles sem avisar. Por isso lança erro em vez
    de chutar — o chamador mostra qual elemento é. Só um acessório
    (FamilyInstance sem "Diâmetro" cadastrado, ex.: conexão atípica) usa
    o diâmetro interno e, na falta dele, um valor padrão.
    """
    try:
        p = elem.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if p and p.AsDouble() > 0:
            return to_m(p.AsDouble())
    except Exception: pass
    if isinstance(elem, Pipe):
        raise ValueError(
            u"Não foi possível ler o diâmetro nominal do tubo ID {} "
            u"(parâmetro 'Diâmetro' ausente ou zerado). Verifique o tipo "
            u"de tubo/segmento desse trecho no Revit.".format(elem.Id))
    try:
        p = elem.get_Parameter(BuiltInParameter.RBS_PIPE_INNER_DIAM_PARAM)
        return to_m(p.AsDouble()) if p and p.AsDouble() > 0 else 0.065
    except Exception: return 0.065

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

# ===========================================================================
# COTAS DE RTI/SUCCAO/RECALQUE/HIDRANTE — ao vivo, pelos conectores nativos
# ===========================================================================
# RTI e bomba sao marcadas pelo "Mapear Trechos" com FireUtils -
# Identificador = "RTI"/"Bomba", direto na propria familia - igual ja
# acontece com HID-01/HID-02 na valvula do hidrante. Com o elemento
# certo em maos (achado pela tag, sem percorrer a rede), a cota e so
# ler o conector nativo dele. Nada e gravado; recalculado a cada execucao.

def get_conectores(elem):
    try:
        if hasattr(elem, 'ConnectorManager'):
            return list(elem.ConnectorManager.Connectors)
        mep = elem.MEPModel
        if mep and mep.ConnectorManager:
            return list(mep.ConnectorManager.Connectors)
    except: pass
    return []

def get_cota_conector(elem, direcoes=None):
    """Cota (Z, em metros) de um conector nativo e conectado de `elem`.
    Se `direcoes` for informado (RTI/bomba), usa o primeiro conector com
    essa Direction; senao (valvula do hidrante), prioriza um conector
    conectado e cai no primeiro conector que existir. None se nao
    encontrar - sem nenhum fallback por geometria."""
    conns = get_conectores(elem)
    if direcoes is not None:
        for conn in conns:
            try:
                if conn.ConnectorType == ConnectorType.Logical: continue
                if conn.Direction not in direcoes: continue
                if not conn.IsConnected: continue
                return to_m(conn.Origin.Z)
            except: continue
        return None
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            if conn.IsConnected:
                return to_m(conn.Origin.Z)
        except: continue
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            return to_m(conn.Origin.Z)
        except: continue
    return None

def get_cota_rti(elem):
    """Cota da RTI: le a elevacao de um conector fisico de `elem` (o
    elemento marcado "RTI" pelo "Mapear Trechos" - familia da RTI ou, no
    fallback manual, o proprio tubo). Preferencia pela ponta solta (conector
    nao Logical e nao conectado a nada) - normalmente e ela que fica virada
    para dentro do reservatorio. Mas nem todo modelo tem uma ponta solta ali
    (o elemento pode estar plenamente conectado nos dois lados da rede, com
    a cota do RTI vindo so da posicao dele) - nesse caso cai para qualquer
    conector fisico, mesmo criterio de get_cota_conector() para os demais
    pontos (succao/recalque/hidrantes). None so se nao achar conector
    nenhum."""
    cm = None
    if hasattr(elem, "ConnectorManager") and elem.ConnectorManager:
        cm = elem.ConnectorManager
    elif hasattr(elem, "MEPModel") and elem.MEPModel and elem.MEPModel.ConnectorManager:
        cm = elem.MEPModel.ConnectorManager
    if not cm:
        return None
    conns = list(cm.Connectors)
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            if not conn.IsConnected:
                return to_m(conn.Origin.Z)
        except: continue
    for conn in conns:
        try:
            if conn.ConnectorType == ConnectorType.Logical: continue
            return to_m(conn.Origin.Z)
        except: continue
    return None

def diagnostico_conectores(elem):
    """Linhas com id/tipo/categoria de `elem` e Direction/IsConnected/Z de
    cada conector dele - usado so para montar o alerta quando uma cota
    nao e lida, pra mostrar exatamente por que (em vez de um "nao foi
    possivel" generico). Nao usa get_conectores (que engole excecoes) -
    aqui o erro real, se houver, aparece no alerta."""
    linhas = []
    try:    id_txt = u"{}".format(elem.Id)
    except: id_txt = u"?"
    try:    tipo = type(elem).__name__
    except: tipo = u"?"
    try:    eh_pipe = isinstance(elem, Pipe)
    except Exception as e: eh_pipe = u"erro ({})".format(e)
    try:    cat = elem.Category.Name if elem.Category else u"(sem categoria)"
    except: cat = u"?"
    try:    tem_cm = hasattr(elem, "ConnectorManager")
    except: tem_cm = u"?"
    linhas.append(u"    Id={} tipo={} isinstance(Pipe)={}".format(id_txt, tipo, eh_pipe))
    linhas.append(u"    categoria={} hasattr(ConnectorManager)={}".format(cat, tem_cm))

    conns = None
    erro = None
    try:
        cm = elem.ConnectorManager if hasattr(elem, "ConnectorManager") else None
        linhas.append(u"    elem.ConnectorManager = {}".format(cm))
        if cm is not None:
            conns = list(cm.Connectors)
        else:
            mep = elem.MEPModel
            if mep and mep.ConnectorManager:
                conns = list(mep.ConnectorManager.Connectors)
    except Exception as e:
        erro = e

    if erro is not None:
        linhas.append(u"    erro ao ler ConnectorManager: {}".format(erro))
        return linhas
    if not conns:
        linhas.append(u"    ConnectorManager nao encontrou nenhum conector")
        return linhas

    for i, conn in enumerate(conns):
        try:    direcao = conn.Direction
        except: direcao = u"?"
        try:    conectado = conn.IsConnected
        except: conectado = u"?"
        try:    z = u"{:.4f} m".format(to_m(conn.Origin.Z))
        except: z = u"?"
        linhas.append(u"    {}. Direction={} IsConnected={} Z={}".format(
            i + 1, direcao, conectado, z))
    return linhas

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

for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
    t = get_trecho(elem)
    if t in trechos_elems: trechos_elems[t].append(elem)
    i = get_identificador(elem)
    # So Pipe ou FamilyInstance sao alvos legitimos de "Mapear Trechos" -
    # ignora qualquer outro elemento que porventura carregue o mesmo
    # texto no parametro (ex.: elemento auxiliar de categoria "Linha de
    # centro"), pra nao pegar o elemento errado por engano.
    if i and isinstance(elem, (Pipe, FamilyInstance)):
        ident_map[i] = elem
    if isinstance(elem, FamilyInstance):
        try:
            p = elem.LookupParameter(u"FireUtils - Identificador")
            if p and p.AsString() in (u"HID-01", u"HID-02"):
                hid_map[p.AsString()] = elem
        except: pass

erros = []
for t in TRECHOS:
    if not trechos_elems[t]: erros.append(u"Trecho '{}' vazio".format(t))
for i in [u"RTI", u"Bomba", u"Ponto A"]:
    if i not in ident_map: erros.append(u"Identificador '{}' não encontrado".format(i))
for h in [u"HID-01", u"HID-02"]:
    if h not in hid_map: erros.append(u"'{}' não encontrado".format(h))
if erros:
    forms.alert(u"Elementos não encontrados:\n{}\n\nExecute 'Mapear Trechos' primeiro.".format(
        u"\n".join(erros)), title="Fire Utils", warn_icon=True)
    script.exit()

# --- Etapa 3: cotas altimétricas de todos os pontos da marcha ---
# RTI e Bomba vêm do próprio ident_map (marcados direto na família pelo
# "Mapear Trechos"): a cota é lida direto do conector nativo delas.
cotas = {
    "z_rti":      get_cota_rti(ident_map[u"RTI"]),
    "z_succao":   get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.In,)),
    "z_recalque": get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.Out,)),
    "z_ponto_a":  get_z(ident_map[u"Ponto A"]),
    "z_hd01":     get_cota_conector(hid_map[u"HID-01"]),
    "z_hd02":     get_cota_conector(hid_map[u"HID-02"]),
}

_nomes_cotas = {
    "z_rti": u"RTI", "z_succao": u"Sucção", "z_recalque": u"Recalque",
    "z_ponto_a": u"Ponto A", "z_hd01": u"HID-01", "z_hd02": u"HID-02",
}
# Elemento por tras de cada cota - so os lidos por conector (Ponto A usa
# geometria, get_z, e nao entra aqui).
_elem_cotas = {
    "z_rti": ident_map.get(u"RTI"), "z_succao": ident_map.get(u"Bomba"),
    "z_recalque": ident_map.get(u"Bomba"),
    "z_hd01": hid_map.get(u"HID-01"), "z_hd02": hid_map.get(u"HID-02"),
}
_chaves_erro = [k for k, z in cotas.items() if z is None]
if _chaves_erro:
    detalhes = [u"Não foi possível ler a elevação de:"]
    for k in _chaves_erro:
        elem = _elem_cotas.get(k)
        if elem is None:
            detalhes.append(u"- {}".format(_nomes_cotas[k]))
            continue
        detalhes.append(u"- {} (elemento ID {}):".format(_nomes_cotas[k], elem.Id))
        detalhes.extend(diagnostico_conectores(elem))
    forms.alert(u"\n".join(detalhes), title="Fire Utils", warn_icon=True)
    script.exit()

# --- Etapa 3b: dados do NPSH disponível ---
# Só o que o cálculo de NPSH precisa e não vem da geometria — a condição de
# sucção em si (positiva/negativa) é decidida abaixo, direto das cotas.
dados_succao = succao_calc.load_dados(doc) or succao_calc.default_dados()

# --- Etapa 4: extrair dados dos trechos (por diâmetro) e resolver a marcha ---
try:
    trechos_data = {
        "t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, get_diametro, get_leq, get_nome, get_id),
        "t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, get_diametro, get_leq, get_nome, get_id),
        "t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, get_diametro, get_leq, get_nome, get_id),
        "t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, get_diametro, get_leq, get_nome, get_id),
    }
except ValueError as _e:
    forms.alert(_txt(_e), title="Fire Utils", warn_icon=True)
    script.exit()

res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas,
                    req(perfil, u"tolerancia_equilibrio_mca"),
                    metodo=metodo_calculo,
                    mang_dn_mm=dados_sistema["mang_dn"],
                    mang_comp_m=dados_sistema["mang_comp"])

# --- Etapa 4a: verificação normativa do equilíbrio hidráulico entre HD01
# e HD02 no Ponto A — a variação de pressão entre os ramais, após o
# equilíbrio, precisa ficar dentro da máxima admitida pela norma. Verifica
# antes das demais (velocidade, pressão/vazão por hidrante), porque um
# equilíbrio que não converge invalida os resultados por trecho abaixo.
if not res["equilibrio"][u"convergiu"]:
    ids_ramais = [get_id(e) for e in trechos_elems[u"Ponto A - Hid 01"] + trechos_elems[u"Ponto A - Hid 02"]]
    ids_mostrar = mostrar_bloqueio_equilibrio(res["equilibrio"], req(perfil, u"norma"),
                                              ids_problema=ids_ramais)
    if ids_mostrar:
        mostrar_no_revit(ids_mostrar)
    script.exit()

# Condição de sucção pelo método direto e conservador: compara a cota da RTI
# com a cota de sucção da bomba, ambas já lidas em "Cotas Altimétricas". Não
# depende de nível mínimo de água, dimensão de tomada, nem tipo de captação.
# Precisa da vazão total (Qt) resolvida acima, que é a vazão nominal
# majorada do gatilho de NPSH.
verif_succao = succao_calc.verificar_condicao_succao(
    cota_rti            = cotas["z_rti"],
    cota_succao_bomba   = cotas["z_succao"],
    q_nominal_lmin      = res["Qt"],
    fator_vazao_npsh    = opt(perfil, u"npshd_fator_vazao",
                              succao_calc.FATOR_VAZAO_NPSH),
)
succao = verif_succao[u"succao_simples"]

# --- Etapa 4b: NPSH disponível (só quando a sucção é negativa) ---
# Reaproveita o |Hs| da verificação acima — a diferença entre a cota de
# sucção da bomba e a cota da RTI — para os dois módulos não divergirem. A
# perda na sucção é recalculada com a vazão majorada, que vale só para esta
# verificação.
verif_npshd = None
erro_npshd  = None
j_succao_npsh = None

if verif_succao is not None and verif_succao[u"exige_npsh"]:
    q_npsh = verif_succao[u"vazao_npsh_lmin"]
    j_succao_npsh = calc_j_trecho(trechos_data["t1"], q_npsh, C_HW,
                                  u"Sucção — vazão majorada (NPSH)")
    try:
        verif_npshd = npshd_calc.calcular_npshd(
            altitude_m    = (dados_succao[u"altitude_m"]
                             if dados_succao[u"altitude_m"] is not None
                             else npshd_calc.ALTITUDE_PADRAO),
            temperatura_c = (dados_succao[u"temperatura_c"]
                             if dados_succao[u"temperatura_c"] is not None
                             else npshd_calc.TEMPERATURA_PADRAO),
            hs_abs_m      = verif_succao[u"hs_abs"],
            hf_s_mca      = j_succao_npsh["J"],
        )
    except ValueError as _e:
        erro_npshd = _txt(_e)

# ===========================================================================
# Etapa 5 — Verificações normativas: para o dimensionamento no primeiro
# ponto que não atender, em vez de seguir adiante com um resultado que não
# atende a norma. Mostra exatamente onde o projetista deve corrigir.
# ===========================================================================
v_max_tubo    = req(perfil, u"v_max_tubulacao")
v_max_suc_pos = req(perfil, u"v_max_succao_positiva")
v_max_suc_neg = req(perfil, u"v_max_succao_negativa")
v_max_succao  = v_max_suc_pos if succao == u"positiva" else v_max_suc_neg

if res["esguicho"]:
    p_hd01_ref = res["esg"]["hd01"]["P_esg"]
    p_hd02_ref = res["esg"]["hd02"]["P_esg"]
    p_ref_desc = u"pressão no esguicho"
else:
    p_hd01_ref = res["P_hd01"]
    p_hd02_ref = res["P_hd02"]
    p_ref_desc = u"pressão na válvula"

def _para_por_velocidade(j, limite, nome_trecho, comprimento_min=None):
    """comprimento_min (m), quando informado: sub-trechos mais curtos que
    isso (ex.: redução na entrada/saída da bomba) ficam fora da
    verificação — ver COMPRIMENTO_MIN_VERIF_VELOCIDADE_M em calc.py."""
    segmentos = j["segmentos"]
    if comprimento_min is not None:
        segmentos = [s for s in segmentos if s["L"] >= comprimento_min]
    falhas = [s for s in segmentos if s["V"] > limite + 1e-9]
    if not falhas:
        return
    ids_falha = [eid for s in falhas for eid in s.get("ids", [])]
    ids_mostrar = mostrar_bloqueio_velocidade(nome_trecho, j, limite, falhas,
                                              ids_problema=ids_falha)
    if ids_mostrar:
        mostrar_no_revit(ids_mostrar)
    script.exit()

def _para_por_hidrante(label, p, q, p_ref_desc, trecho_desc, elems_trecho):
    if p >= float(Pmin) - 0.01 and q >= float(Qs_lmin) - 0.01:
        return
    ids_trecho = [get_id(e) for e in elems_trecho]
    ids_mostrar = mostrar_bloqueio_hidrante(label, p, q, p_ref_desc, trecho_desc, Pmin, Qs_lmin,
                                            ids_problema=ids_trecho)
    if ids_mostrar:
        mostrar_no_revit(ids_mostrar)
    script.exit()

_para_por_velocidade(res["j"]["t3"], v_max_tubo, u"Ponto A → HD01")
_para_por_hidrante(u"HD01", p_hd01_ref, res["Q_hd01"], p_ref_desc, u"Ponto A → HD01",
                   trechos_elems[u"Ponto A - Hid 01"])
_para_por_velocidade(res["j"]["t4"], v_max_tubo, u"Ponto A → HD02")
_para_por_hidrante(u"HD02", p_hd02_ref, res["Q_hd02"], p_ref_desc, u"Ponto A → HD02",
                   trechos_elems[u"Ponto A - Hid 02"])
_para_por_velocidade(res["j"]["t2"], v_max_tubo, u"Bomba → Ponto A (recalque)",
                     comprimento_min=COMPRIMENTO_MIN_VERIF_VELOCIDADE_M)
_para_por_velocidade(res["j"]["t1"], v_max_succao, u"Sucção (RTI → Bomba)",
                     comprimento_min=COMPRIMENTO_MIN_VERIF_VELOCIDADE_M)

# --- Etapa 6: eficiência e potência da bomba ---
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

# Potência adotada para a bomba do projeto — digitada pelo usuário (não é
# calculada): a mínima acima é só a referência mostrada no prompt. Cancelar
# ou deixar em branco segue o dimensionamento só com a potência mínima.
pot_escolhida_str = forms.ask_for_string(
    default=u"{:.2f}".format(pot_cv),
    prompt=u"Potência adotada (cv)\nPotência mínima calculada: {:.2f} cv".format(pot_cv),
    title=u"Fire Utils — Potência Adotada"
)
pot_escolhida_cv = None
pot_escolhida_kw = None
if pot_escolhida_str:
    try:
        pot_escolhida_cv = float(pot_escolhida_str.replace(",", "."))
        if pot_escolhida_cv <= 0: raise ValueError
        pot_escolhida_kw = pot_escolhida_cv / 1.36
    except ValueError:
        forms.alert(u"Potência adotada inválida — seguindo só com a potência "
                    u"mínima calculada.", title="Fire Utils", warn_icon=True)
        pot_escolhida_cv = None

# ===========================================================================
# Etapa 7 — Verificações e resultados finais (resumo; o passo a passo
# completo agora é o botão separado "Memorial de Cálculo")
# ===========================================================================
mostrar_resultado_ok(
    res, valor_sistema, metodo_calculo, req(perfil, u"norma"),
    v_max_tubo, v_max_succao, p_ref_desc, p_hd01_ref, p_hd02_ref,
    Pmin, Qs_lmin, eta, pot_cv, pot_kw,
    pot_escolhida_cv=pot_escolhida_cv, pot_escolhida_kw=pot_escolhida_kw,
    comprimento_min_velocidade=COMPRIMENTO_MIN_VERIF_VELOCIDADE_M,
)

# --- Etapa 8: salvar cache (para "Memorial de Cálculo" reimprimir sem recalcular) ---
import datetime
timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
payload_hid = {
    "res":           res,
    "dados_sistema": dados_sistema,
    "valor_sistema": valor_sistema,
    "metodo":        metodo_calculo,
    "cotas":         cotas,
    "succao":        succao,
    "verif_succao":  verif_succao,
    "dados_succao":  dados_succao,
    "verif_npshd":   verif_npshd,
    "erro_npshd":    erro_npshd,
    "j_succao_npsh": j_succao_npsh,
    "C_HW":          C_HW,
    "uf":            perfil.get(u"_uf_efetiva"),
    "eta":              eta,
    "pot_cv":           pot_cv,
    "pot_kw":           pot_kw,
    "pot_escolhida_cv": pot_escolhida_cv,
    "pot_escolhida_kw": pot_escolhida_kw,
    "timestamp":     timestamp,
    "_nome_projeto": doc.Title,
}
salvar_cache(payload_hid, projeto_dir)
