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

Os elementos de cada trecho não vêm mais de uma varredura por parâmetro:
"Mapear Trechos" salva a rota (listas de ElementId) no cache, chave
'rotas', e este script só resolve os elementos por Id. RTI e Bomba
continuam sendo achados pela tag "FireUtils - Identificador" na própria
família, como antes.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilyInstance, ElementId, FlowDirectionType,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from pyrevit import forms, script

from projeto import exigir_projeto_e_estado
from hidrantes.calc import (
    calcular_rede, calc_potencia, extrair_trecho, salvar_cache, carregar_cache,
    METODO_VALVULA, METODOS_CALCULO, calc_j_trecho,
)
from hidrantes.resultado_ui import (
    mostrar_bloqueio_velocidade, mostrar_bloqueio_hidrante,
    mostrar_resultado_ok,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
from hidrantes.norm_profiles import get_profile, req, opt
from hidrantes.sistema import resolver_dados_sistema
from hidrantes.rede import (
    get_cota_conector, get_cota_rti, get_z, diagnostico_conectores,
    get_comprimento, get_diametro, get_leq, get_nome,
)
from hidrantes import succao as succao_calc
from hidrantes import npshd as npshd_calc

P_IDENTIFICADOR = u"FireUtils - Identificador"

# IronPython 2.7 (engine do pyRevit) tem 'unicode'; CPython 3 não.
try:
    _txt = unicode
except NameError:
    _txt = str

doc    = __revit__.ActiveUIDocument.Document
output = script.get_output()

# ===========================================================================
# HELPERS REVIT
# ===========================================================================

def get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        if not p or not p.HasValue: return None
        valor = p.AsString()
        return valor.strip() if valor else None
    except: return None

# ===========================================================================
# MAIN
# ===========================================================================

# --- Verificar projeto salvo e estado configurado ---
projeto_dir, sigla_estado, _ = exigir_projeto_e_estado(doc, forms, script)

# --- Perfil normativo ativo (UF do projeto, default "MA") ---
perfil = get_profile(sigla_estado)

# --- Etapa 1: tipo de sistema ---
valor_sistema, dados_sistema = resolver_dados_sistema(doc, perfil, forms, script)

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
# A rota (RTI-Bomba / Bomba-Ponto A / Ponto A-H-01 / Ponto A-H-02) vem do
# cache salvo por "Mapear Trechos" (chave 'rotas'), como listas de
# ElementId - não mais de uma varredura pelo parametro "FireUtils -
# Trecho". RTI e Bomba continuam vindo da tag "FireUtils - Identificador"
# na propria familia, sem mudanca.
payload_rotas, erro_rotas = carregar_cache(projeto_dir, chave=u"rotas")
if erro_rotas:
    forms.alert(erro_rotas, title="Fire Utils", warn_icon=True)
    script.exit()

def _resolve_elems(eids):
    return [doc.GetElement(ElementId(eid)) for eid in eids]

elems_t1 = _resolve_elems(payload_rotas[u"t1"])   # RTI -> Bomba
elems_t2 = _resolve_elems(payload_rotas[u"t2"])   # Bomba -> Ponto A
elems_t3 = _resolve_elems(payload_rotas[u"t3"])   # Ponto A -> H-01
elems_t4 = _resolve_elems(payload_rotas[u"t4"])   # Ponto A -> H-02
ponto_a_elem = doc.GetElement(ElementId(payload_rotas[u"ponto_a_id"]))

if (any(e is None for e in elems_t1 + elems_t2 + elems_t3 + elems_t4)
        or ponto_a_elem is None):
    forms.alert(
        u"Um ou mais elementos do mapeamento não existem mais no projeto "
        u"(modelo alterado desde o último mapeamento).\n\n"
        u"Execute 'Mapear Trechos' novamente.",
        title="Fire Utils", warn_icon=True)
    script.exit()

hid01_elem = elems_t3[-1]
hid02_elem = elems_t4[-1]

ident_map = {}
for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
    i = get_identificador(elem)
    # So Pipe ou FamilyInstance sao alvos legitimos de "Mapear Trechos" -
    # ignora qualquer outro elemento que porventura carregue o mesmo
    # texto no parametro (ex.: elemento auxiliar de categoria "Linha de
    # centro"), pra nao pegar o elemento errado por engano.
    if i and isinstance(elem, (Pipe, FamilyInstance)):
        ident_map[i] = elem

erros = []
for i in [u"RTI", u"Bomba"]:
    if i not in ident_map: erros.append(u"Identificador '{}' não encontrado".format(i))
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
    "z_ponto_a":  get_z(ponto_a_elem),
    "z_hd01":     get_cota_conector(hid01_elem),
    "z_hd02":     get_cota_conector(hid02_elem),
}

_nomes_cotas = {
    "z_rti": u"RTI", "z_succao": u"Sucção", "z_recalque": u"Recalque",
    "z_ponto_a": u"Ponto A", "z_hd01": u"H-01", "z_hd02": u"H-02",
}
# Elemento por tras de cada cota - so os lidos por conector (Ponto A usa
# geometria, get_z, e nao entra aqui).
_elem_cotas = {
    "z_rti": ident_map.get(u"RTI"), "z_succao": ident_map.get(u"Bomba"),
    "z_recalque": ident_map.get(u"Bomba"),
    "z_hd01": hid01_elem, "z_hd02": hid02_elem,
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
trechos_data = {
    "t1": extrair_trecho(elems_t1, get_comprimento, get_diametro, get_leq, get_nome),
    "t2": extrair_trecho(elems_t2, get_comprimento, get_diametro, get_leq, get_nome),
    "t3": extrair_trecho(elems_t3, get_comprimento, get_diametro, get_leq, get_nome),
    "t4": extrair_trecho(elems_t4, get_comprimento, get_diametro, get_leq, get_nome),
}

res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas,
                    metodo=metodo_calculo,
                    mang_dn_mm=dados_sistema["mang_dn"],
                    mang_comp_m=dados_sistema["mang_comp"])

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

def _para_por_velocidade(j, limite, nome_trecho):
    falhas = [s for s in j["segmentos"] if s["V"] > limite + 1e-9]
    if not falhas:
        return
    mostrar_bloqueio_velocidade(nome_trecho, j, limite, falhas)
    script.exit()

def _para_por_hidrante(label, p, q, p_ref_desc, trecho_desc):
    if p >= float(Pmin) - 0.01 and q >= float(Qs_lmin) - 0.01:
        return
    mostrar_bloqueio_hidrante(label, p, q, p_ref_desc, trecho_desc, Pmin, Qs_lmin)
    script.exit()

_para_por_velocidade(res["j"]["t3"], v_max_tubo, u"Ponto A → HD01")
_para_por_hidrante(u"HD01", p_hd01_ref, res["Q_hd01"], p_ref_desc, u"Ponto A → HD01")
_para_por_velocidade(res["j"]["t4"], v_max_tubo, u"Ponto A → HD02")
_para_por_hidrante(u"HD02", p_hd02_ref, res["Q_hd02"], p_ref_desc, u"Ponto A → HD02")
_para_por_velocidade(res["j"]["t2"], v_max_tubo, u"Bomba → Ponto A (recalque)")
_para_por_velocidade(res["j"]["t1"], v_max_succao, u"Sucção (RTI → Bomba)")

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

# ===========================================================================
# Etapa 7 — Verificações e resultados finais (resumo; o passo a passo
# completo agora é o botão separado "Memorial de Cálculo")
# ===========================================================================
mostrar_resultado_ok(
    res, valor_sistema, metodo_calculo, req(perfil, u"norma"),
    v_max_tubo, v_max_succao, p_ref_desc, p_hd01_ref, p_hd02_ref,
    Pmin, Qs_lmin, eta, pot_cv, pot_kw,
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
    "eta":           eta,
    "pot_cv":        pot_cv,
    "pot_kw":        pot_kw,
    "timestamp":     timestamp,
    "_nome_projeto": doc.Title,
}
salvar_cache(payload_hid, projeto_dir)
output.print_md(u"*Cache salvo em firedata.json (chave 'hidrantes').*")
