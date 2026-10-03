# -*- coding: utf-8 -*-
"""
hidrantes_dimensionar_bridge.py — Fire Utils · lib/
Processa DIMENSIONAR_HIDRANTES: roda o mesmo motor de cálculo do
pushbutton "Dimensionar Hidrantes" (Hidrantes.panel/Dimensionar
Hidrantes.pushbutton/script.py — método da marcha HD01 → Ponto A →
Descarga da Bomba → RTI), disparado por um clique na dockpane em vez do
botão do Revit — mesma fonte de verdade dos dois lados (hidrantes/calc.py,
hidrantes/rede.py), sem reimplementar a matemática nem a leitura de
conectores aqui.

Única diferença de verdade em relação ao pushbutton: quando alguma
verificação normativa não atende (equilíbrio hidráulico, velocidade,
pressão/vazão no hidrante), em vez de abrir uma janela WPF de bloqueio
com botão "Mostrar no Projeto" (resultado_ui.py — só faz sentido rodando
dentro do Revit, com a seleção de elementos ao vivo), devolve um erro em
texto pra dockpane mostrar. Quem precisar localizar o elemento problemático
ainda pode rodar o pushbutton no Revit, que continua com a janela
completa — este bridge não o substitui, só oferece um atalho pro caminho
feliz (classificação e mapeamento já ok, dimensionamento atende de
primeira) sem sair da dockpane.

Em caso de sucesso, grava exatamente o mesmo cache (firedata.json, chave
"hidrantes") que o pushbutton grava — a dockpane só manda
GET_HIDRANTES_DIMENSIONAMENTO de novo depois (ver
hidrantes_dimensionamento_bridge.py) pra mostrar o resultado completo
(HidrantesDimensionamento.jsx), sem duplicar nenhum formato de dado aqui.
"""

import os
import datetime

from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, FlowDirectionType
from Autodesk.Revit.DB.Plumbing import Pipe

from projeto import carregar_dados_projeto
from hidrantes.calc import (
    calcular_rede, extrair_trecho, salvar_cache, carregar_cache,
    METODO_VALVULA, METODOS_CALCULO, calc_j_trecho,
    COMPRIMENTO_MIN_VERIF_VELOCIDADE_M,
)
from hidrantes.rede import (
    get_id, to_element_id, get_diametro_no_trecho, get_comprimento, get_leq,
    get_nome, get_z, get_cota_conector, get_cota_rti, diagnostico_conectores,
)
from hidrantes.params import PROJECT_INFO_METODO_PARAM
from hidrantes.norm_profiles import get_profile, req, opt, NormProfileError
from hidrantes import succao as succao_calc
from hidrantes import npshd as npshd_calc
from family_error_utils import texto_erro

PROJECT_INFO_PARAM = u"FireUtils - Tipo de Sistema de Hidrante"
P_IDENTIFICADOR    = u"FireUtils - Identificador"
_TIPO_RESPOSTA      = u"HIDRANTES_DIMENSIONAR_RESULTADO"


def _erro(postar_mensagem, mensagem):
    postar_mensagem(_TIPO_RESPOSTA, {u"ok": False, u"erro": mensagem})


def _get_identificador(elem):
    try:
        p = elem.LookupParameter(P_IDENTIFICADOR)
        if not p or not p.HasValue:
            return None
        valor = p.AsString()
        return valor.strip() if valor else None
    except Exception:
        return None


def _resumo_falha_velocidade(nome_trecho, limite, falhas):
    partes = [u"Velocidade acima do limite normativo em \"{}\" (limite {:.3f} m/s):".format(nome_trecho, limite)]
    for s in falhas:
        partes.append(u"- DN{} : {:.3f} m/s".format(int(round(s[u"d_mm"])), s[u"V"]))
    return u"\n".join(partes)


def _resumo_falha_hidrante(label, p, q, p_ref_desc, trecho_desc, pmin, qmin):
    return (
        u"{} não atende a norma em \"{}\":\n"
        u"- {} obtida: {:.4f} mca (mínimo {:.2f} mca)\n"
        u"- Vazão obtida: {:.2f} L/min (mínimo {:.2f} L/min)"
    ).format(label, trecho_desc, p_ref_desc, p, pmin, q, qmin)


def tratar_dimensionar_hidrantes(uiapp, postar_mensagem):
    # Sem esse try/except, qualquer exceção não prevista (ex.: algo que o
    # pushbutton nunca tropeçou porque sempre rodou com o Revit em primeiro
    # plano) subia até o ExternalEvent, que só loga no console do pyRevit —
    # e a dockpane ficava com o botão em "Dimensionando..." pra sempre, sem
    # nenhuma mensagem de volta (mesmo motivo documentado em
    # project_link_bridge.py:tratar_get_project_link).
    try:
        _processar(uiapp, postar_mensagem)
    except Exception as ex:
        _erro(postar_mensagem, u"Falha inesperada ao dimensionar: {}".format(texto_erro(ex)))


def _processar(uiapp, postar_mensagem):
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or not uidoc.Document.PathName:
        _erro(postar_mensagem, u"Salve o projeto Revit (.rvt) antes de dimensionar.")
        return
    doc = uidoc.Document
    projeto_dir = os.path.dirname(doc.PathName)

    dados_projeto = carregar_dados_projeto(projeto_dir) or {}
    sigla_estado = dados_projeto.get(u"uf") or u"MA"
    try:
        perfil = get_profile(sigla_estado, projeto_dir)
    except NormProfileError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return

    # Etapa 1: tipo de sistema (classificação já aplicada no Project
    # Information — ver hidrantes_classificacao_bridge.py).
    param_sistema = doc.ProjectInformation.LookupParameter(PROJECT_INFO_PARAM)
    if not param_sistema or not param_sistema.AsString():
        _erro(postar_mensagem, u"Sistema de hidrantes ainda não classificado. Classifique na seção acima primeiro.")
        return
    valor_sistema = param_sistema.AsString()

    try:
        tipo_num = int(valor_sistema.split()[1])
    except Exception:
        _erro(postar_mensagem, u"Não foi possível interpretar o tipo classificado.")
        return

    variante_idx = 0
    if u"Var." in valor_sistema:
        try:
            variante_idx = ord(valor_sistema.split(u"Var.")[1].strip()[0]) - 65
        except Exception:
            variante_idx = 0

    try:
        tipo_perfil = req(perfil, u"tipos").get(tipo_num)
    except NormProfileError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return
    if tipo_perfil is None:
        _erro(postar_mensagem, u"O perfil normativo '{}' não define o Tipo {} de sistema de hidrante.".format(
            perfil.get(u"norma"), tipo_num))
        return

    dados_sistema = dict(tipo_perfil[u"variantes"][variante_idx])
    # A Tabela 2 pode vir da base central com esses valores como int — ver
    # mesmo ajuste em "Dimensionar Hidrantes"/script.py.
    for chave in (u"q_min", u"p_min", u"mang_dn", u"mang_comp", u"esguicho_dn"):
        dados_sistema[chave] = float(dados_sistema[chave])

    Qs_lmin = dados_sistema[u"q_min"]
    Pmin = dados_sistema[u"p_min"]
    try:
        C_HW = req(perfil, u"hazen_c")[u"galvanizado"]
    except NormProfileError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return

    # Etapa 1b: método de cálculo (gravado junto da classificação).
    param_metodo = doc.ProjectInformation.LookupParameter(PROJECT_INFO_METODO_PARAM)
    metodo_calculo = param_metodo.AsString() if param_metodo else None
    if metodo_calculo not in METODOS_CALCULO:
        if metodo_calculo:
            _erro(postar_mensagem, u"Método de cálculo desconhecido no projeto: '{}'. Classifique o sistema novamente.".format(metodo_calculo))
            return
        metodo_calculo = METODO_VALVULA

    # Etapa 2: elementos da rota — cache salvo por "Mapear Trechos".
    payload_rotas, erro_rotas = carregar_cache(projeto_dir, chave=u"rotas")
    if erro_rotas:
        _erro(postar_mensagem, erro_rotas)
        return

    def _resolve_elems(eids):
        return [doc.GetElement(to_element_id(eid)) for eid in eids]

    trechos_elems = {
        u"RTI - Bomba":      _resolve_elems(payload_rotas[u"t1"]),
        u"Bomba - Ponto A":  _resolve_elems(payload_rotas[u"t2"]),
        u"Ponto A - Hid 01": _resolve_elems(payload_rotas[u"t3"]),
        u"Ponto A - Hid 02": _resolve_elems(payload_rotas[u"t4"]),
    }
    ponto_a_elem = doc.GetElement(to_element_id(payload_rotas[u"ponto_a_id"]))

    todos_elems_rota = [e for lst in trechos_elems.values() for e in lst] + [ponto_a_elem]
    if any(e is None for e in todos_elems_rota):
        _erro(postar_mensagem, u"Um ou mais elementos do mapeamento não existem mais no projeto "
                                u"(modelo alterado desde o último mapeamento). Execute 'Mapear Trechos' novamente.")
        return

    hid_map = {
        u"HID-01": trechos_elems[u"Ponto A - Hid 01"][-1],
        u"HID-02": trechos_elems[u"Ponto A - Hid 02"][-1],
    }

    ident_map = {u"Ponto A": ponto_a_elem}
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        ident = _get_identificador(elem)
        if ident and isinstance(elem, (Pipe, FamilyInstance)):
            ident_map[ident] = elem

    faltando = [nome for nome in (u"RTI", u"Bomba") if nome not in ident_map]
    if faltando:
        _erro(postar_mensagem, u"Elementos não encontrados: {}. Execute 'Mapear Trechos' primeiro.".format(
            u", ".join(faltando)))
        return

    # Etapa 3: cotas altimétricas de todos os pontos da marcha.
    cotas = {
        u"z_rti":      get_cota_rti(ident_map[u"RTI"]),
        u"z_succao":   get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.In,)),
        u"z_recalque": get_cota_conector(ident_map[u"Bomba"], (FlowDirectionType.Out,)),
        u"z_ponto_a":  get_z(ident_map[u"Ponto A"]),
        u"z_hd01":     get_cota_conector(hid_map[u"HID-01"]),
        u"z_hd02":     get_cota_conector(hid_map[u"HID-02"]),
    }
    nomes_cotas = {
        u"z_rti": u"RTI", u"z_succao": u"Sucção", u"z_recalque": u"Recalque",
        u"z_ponto_a": u"Ponto A", u"z_hd01": u"HID-01", u"z_hd02": u"HID-02",
    }
    elem_cotas = {
        u"z_rti": ident_map.get(u"RTI"), u"z_succao": ident_map.get(u"Bomba"),
        u"z_recalque": ident_map.get(u"Bomba"),
        u"z_hd01": hid_map.get(u"HID-01"), u"z_hd02": hid_map.get(u"HID-02"),
    }
    chaves_erro = [k for k, z in cotas.items() if z is None]
    if chaves_erro:
        detalhes = [u"Não foi possível ler a elevação de:"]
        for k in chaves_erro:
            elem = elem_cotas.get(k)
            if elem is None:
                detalhes.append(u"- {}".format(nomes_cotas[k]))
                continue
            detalhes.append(u"- {} (elemento ID {}):".format(nomes_cotas[k], elem.Id))
            detalhes.extend(diagnostico_conectores(elem))
        _erro(postar_mensagem, u"\n".join(detalhes))
        return

    dados_succao = succao_calc.load_dados(doc) or succao_calc.default_dados()

    # Etapa 4: extrair dados dos trechos (por diâmetro) e resolver a marcha.
    def _diametro_fn(chave_trecho):
        ids_no_trecho = set(get_id(e) for e in trechos_elems[chave_trecho])
        return lambda e, _ids=ids_no_trecho: get_diametro_no_trecho(e, _ids)

    try:
        trechos_data = {
            u"t1": extrair_trecho(trechos_elems[u"RTI - Bomba"],      get_comprimento, _diametro_fn(u"RTI - Bomba"),      get_leq, get_nome, get_id),
            u"t2": extrair_trecho(trechos_elems[u"Bomba - Ponto A"],  get_comprimento, _diametro_fn(u"Bomba - Ponto A"),  get_leq, get_nome, get_id),
            u"t3": extrair_trecho(trechos_elems[u"Ponto A - Hid 01"], get_comprimento, _diametro_fn(u"Ponto A - Hid 01"), get_leq, get_nome, get_id),
            u"t4": extrair_trecho(trechos_elems[u"Ponto A - Hid 02"], get_comprimento, _diametro_fn(u"Ponto A - Hid 02"), get_leq, get_nome, get_id),
        }
    except ValueError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return

    try:
        tolerancia_equilibrio_mca = req(perfil, u"tolerancia_equilibrio_mca")
        v_max_tubo    = req(perfil, u"v_max_tubulacao")
        v_max_suc_pos = req(perfil, u"v_max_succao_positiva")
        v_max_suc_neg = req(perfil, u"v_max_succao_negativa")
        norma_nome    = req(perfil, u"norma")
    except NormProfileError as ex:
        _erro(postar_mensagem, texto_erro(ex))
        return

    res = calcular_rede(trechos_data, Qs_lmin, Pmin, C_HW, cotas,
                        tolerancia_equilibrio_mca,
                        metodo=metodo_calculo,
                        mang_dn_mm=dados_sistema[u"mang_dn"],
                        mang_comp_m=dados_sistema[u"mang_comp"])

    # Etapa 4a: equilíbrio hidráulico entre HD01/HD02 no Ponto A.
    if not res[u"equilibrio"][u"convergiu"]:
        eq = res[u"equilibrio"]
        _erro(postar_mensagem, (
            u"O equilíbrio hidráulico entre HD01 e HD02 não convergiu "
            u"(diferença de {:.4f} mca, limite {:.2f} mca — {}). Revise o "
            u"traçado/diâmetro da rede entre os dois ramais."
        ).format(eq.get(u"erro", 0.0), eq.get(u"tolerancia", tolerancia_equilibrio_mca), norma_nome))
        return

    # Condição de sucção + NPSH (quando negativa).
    verif_succao = succao_calc.verificar_condicao_succao(
        cota_rti=cotas[u"z_rti"],
        cota_succao_bomba=cotas[u"z_succao"],
        q_nominal_lmin=res[u"Qt"],
        fator_vazao_npsh=opt(perfil, u"npshd_fator_vazao", succao_calc.FATOR_VAZAO_NPSH),
    )
    succao = verif_succao[u"succao_simples"]

    verif_npshd = None
    erro_npshd = None
    j_succao_npsh = None
    if verif_succao is not None and verif_succao[u"exige_npsh"]:
        q_npsh = verif_succao[u"vazao_npsh_lmin"]
        j_succao_npsh = calc_j_trecho(trechos_data[u"t1"], q_npsh, C_HW, u"Sucção — vazão majorada (NPSH)")
        try:
            verif_npshd = npshd_calc.calcular_npshd(
                altitude_m=(dados_succao[u"altitude_m"] if dados_succao[u"altitude_m"] is not None else npshd_calc.ALTITUDE_PADRAO),
                temperatura_c=(dados_succao[u"temperatura_c"] if dados_succao[u"temperatura_c"] is not None else npshd_calc.TEMPERATURA_PADRAO),
                hs_abs_m=verif_succao[u"hs_abs"],
                hf_s_mca=j_succao_npsh[u"J"],
            )
        except ValueError as ex:
            erro_npshd = texto_erro(ex)

    v_max_succao = v_max_suc_pos if succao == u"positiva" else v_max_suc_neg

    if res[u"esguicho"]:
        p_hd01_ref = res[u"esg"][u"hd01"][u"P_esg"]
        p_hd02_ref = res[u"esg"][u"hd02"][u"P_esg"]
        p_ref_desc = u"pressão no esguicho"
    else:
        p_hd01_ref = res[u"P_hd01"]
        p_hd02_ref = res[u"P_hd02"]
        p_ref_desc = u"pressão na válvula"

    # Etapa 5 — verificações normativas: para no primeiro ponto que não
    # atender, igual ao pushbutton (ver docstring do módulo pro porquê de
    # não ter mais o "Mostrar no Projeto" aqui).
    def _falha_velocidade(j, limite, nome_trecho, comprimento_min=None):
        segmentos = j[u"segmentos"]
        if comprimento_min is not None:
            segmentos = [s for s in segmentos if s[u"L"] >= comprimento_min]
        falhas = [s for s in segmentos if s[u"V"] > limite + 1e-9]
        if not falhas:
            return None
        return _resumo_falha_velocidade(nome_trecho, limite, falhas)

    def _falha_hidrante(label, p, q, trecho_desc):
        if p >= float(Pmin) - 0.01 and q >= float(Qs_lmin) - 0.01:
            return None
        return _resumo_falha_hidrante(label, p, q, p_ref_desc, trecho_desc, Pmin, Qs_lmin)

    falhas_normativas = (
        _falha_velocidade(res[u"j"][u"t3"], v_max_tubo, u"Ponto A → HD01"),
        _falha_hidrante(u"HD01", p_hd01_ref, res[u"Q_hd01"], u"Ponto A → HD01"),
        _falha_velocidade(res[u"j"][u"t4"], v_max_tubo, u"Ponto A → HD02"),
        _falha_hidrante(u"HD02", p_hd02_ref, res[u"Q_hd02"], u"Ponto A → HD02"),
        _falha_velocidade(res[u"j"][u"t2"], v_max_tubo, u"Bomba → Ponto A (recalque)", COMPRIMENTO_MIN_VERIF_VELOCIDADE_M),
        _falha_velocidade(res[u"j"][u"t1"], v_max_succao, u"Sucção (RTI → Bomba)", COMPRIMENTO_MIN_VERIF_VELOCIDADE_M),
    )
    for falha in falhas_normativas:
        if falha:
            _erro(postar_mensagem, falha)
            return

    # Etapa 6 — salvar cache (sincroniza com o site e alimenta
    # HidrantesDimensionamento.jsx — mesmo formato que o pushbutton grava).
    timestamp = datetime.datetime.now().strftime(u"%d/%m/%Y %H:%M")
    payload_hid = {
        u"res":              res,
        u"dados_sistema":    dados_sistema,
        u"valor_sistema":    valor_sistema,
        u"metodo":           metodo_calculo,
        u"cotas":            cotas,
        u"succao":           succao,
        u"verif_succao":     verif_succao,
        u"dados_succao":     dados_succao,
        u"verif_npshd":      verif_npshd,
        u"erro_npshd":       erro_npshd,
        u"j_succao_npsh":    j_succao_npsh,
        u"C_HW":             C_HW,
        u"uf":               perfil.get(u"_uf_efetiva"),
        u"timestamp":        timestamp,
        u"_nome_projeto":    doc.Title,
        u"ranking_hidrantes": payload_rotas.get(u"ranking"),
    }
    salvar_cache(payload_hid, projeto_dir)

    postar_mensagem(_TIPO_RESPOSTA, {u"ok": True})
