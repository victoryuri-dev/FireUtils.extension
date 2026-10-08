# -*- coding: utf-8 -*-
"""
normas/__init__.py — Fire Utils
Centro normativo unificado. TODA a normativa (saídas de emergência e
hidrantes) vem exclusivamente da base normativa central (Supabase, tabela
`normas_dados`) — mesma base que o site (ETOS.FireUtils) lê, ver
src/lib/normasRemote.js lá. O plugin não guarda nenhuma cópia própria de
norma de estado nenhum: sem isso, um estado que muda de norma no Supabase
(ou corrige um valor) ficava com o plugin desatualizado até alguém lembrar
de editar um arquivo .py aqui também.

Uso:
    from normas import get_estado

    estado = get_estado("MA", projeto_dir)
    tabela     = estado["tabela"]           # domínio saídas
    larg_min   = estado["larguras_minimas"]
    distancias = estado["distancias_maximas"]
    hidrantes  = estado.get("hidrantes")    # domínio hidrantes (pode não existir)

Cache offline: a última resposta boa de cada (uf, sistema) fica gravada
dentro do próprio firedata.json do projeto (chave "normas_cache") — assim
o plugin continua funcionando sem rede depois da primeira consulta bem-
sucedida daquele projeto, sempre com o dado mais recente que já buscou
(nunca um snapshot desatualizado embutido no instalador). Por cima disso,
um cache em memória do processo evita repetir a consulta (rede ou disco) a
cada clique de botão na mesma sessão do Revit.

"tipos" (Tabela 2 de hidrantes — quais Tipos de sistema existem e seus
parâmetros de vazão/pressão/mangueira/esguicho) também vem da base central
agora, a partir da chave "tipos_sistema" do payload "hidrantes" (mesmo
formato que o site usa em src/data/normas/<UF>/hidrantes.js:TIPOS_SISTEMA)
— convertida aqui pro vocabulário que hidrantes/sistema.py já indexa
(q_min/p_min/mang_dn/mang_comp/esguicho_dn/expedicoes).
"""

import io
import json


# Chaves do domínio "saídas" que vêm do payload central (sistema=
# "saida_emergencia").
_CHAVES_SAIDAS = (
    u"sigla", u"nome", u"corpo", u"norma_ocupacoes", u"norma_saidas",
    u"ocupacoes", u"tabela", u"notas", u"larguras_minimas",
    u"distancias_maximas", u"_pendencias",
)

# Chaves do domínio "hidrantes" (dentro de estado["hidrantes"]) que vêm
# direto do payload central (sistema="hidrantes") sem conversão de forma —
# "hazen_c"/"norma"/"tipos" têm forma diferente da do payload e são
# tratadas à parte (_hazen_c_da_base_central / abaixo / _tipos_da_base_central).
_CHAVES_HIDRANTES = (
    u"v_max_tubulacao", u"v_max_tubulacao_ref",
    u"v_max_succao_positiva", u"v_max_succao_negativa", u"v_max_succao_ref",
    u"tolerancia_equilibrio_mca", u"tolerancia_equilibrio_mca_ref",
    u"npshd_fator_vazao", u"npshd_ref",
    u"hidrantes_simultaneos", u"hidrantes_simultaneos_ref",
)

# Chaves numéricas de _CHAVES_HIDRANTES (as "_ref" são citações, string) —
# um valor sem casa decimal (ex.: 5, não 5.0) chega do JSON do Supabase
# como int, e o IronPython 2.7 do Revit (diferente do CPython) lança
# ValueError em "{:.1f}".format(x) quando x é int — normalizadas pra
# float no merge abaixo, mesmo motivo/consertos já feitos pra Tabela 2 em
# hidrantes/sistema.py e "Dimensionar Hidrantes"/script.py.
_CHAVES_HIDRANTES_NUMERICAS = (
    u"v_max_tubulacao", u"v_max_succao_positiva", u"v_max_succao_negativa",
    u"tolerancia_equilibrio_mca", u"npshd_fator_vazao", u"hidrantes_simultaneos",
)

# hazen_c usa apelidos curtos (ff_sem_revest, ff_revest_cimento) que o
# payload central (materiais_tubulacao — mesmo array que o site consome,
# ver src/data/normas/MA/hidrantes.js:MATERIAIS_TUBULACAO) não usa
# (ferro_fundido_sem_revest, ferro_fundido_com_cimento). Convertido pro
# apelido aqui, sem mudar a chave que o motor de cálculo ("Dimensionar
# Hidrantes"/script.py) já indexa (hazen_c[u"galvanizado"]).
_ALIAS_MATERIAL_TUBULACAO = {
    u"ferro_fundido_sem_revest":  u"ff_sem_revest",
    u"ferro_fundido_com_cimento": u"ff_revest_cimento",
}


# ── Cache offline (dentro do firedata.json do projeto) ─────────────────────

def _ler_cache_normas(projeto_dir):
    """Lê a chave 'normas_cache' (uf -> sistema -> dados) do firedata.json
    do projeto — última resposta boa de uma consulta anterior."""
    from projeto import carregar_cache
    return carregar_cache(projeto_dir).get(u"normas_cache") or {}


def _gravar_cache_normas(projeto_dir, uf, sistema, dados):
    from projeto import cache_path, carregar_cache
    arquivo = carregar_cache(projeto_dir)
    cache = arquivo.get(u"normas_cache") or {}
    cache.setdefault(uf, {})[sistema] = dados
    arquivo[u"normas_cache"] = cache
    try:
        with io.open(cache_path(projeto_dir), u"w", encoding=u"utf-8") as f:
            json.dump(arquivo, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # cache é só otimização — falha ao gravar não deve travar nada


# Cache em memória do processo — enquanto o engine do pyRevit continuar
# carregado (normalmente o caso entre cliques de botão na mesma sessão do
# Revit), a rede/disco só são consultados UMA vez por uf. Valor None (chave
# ausente) = ainda não buscado nesta sessão; False = já tentou e não achou
# nem rede nem cache em disco (também não tenta de novo até a sessão do
# Revit reiniciar).
_SESSION_CACHE = {}
_SESSION_CACHE_HIDRANTES = {}  # separado de _SESSION_CACHE — sistema diferente, mesmo uf


def _buscar_saidas(uf, projeto_dir):
    if uf in _SESSION_CACHE:
        return _SESSION_CACHE[uf] or None

    from sync import buscar_norma

    dados, erro = buscar_norma(uf, u"saida_emergencia")
    if dados:
        _gravar_cache_normas(projeto_dir, uf, u"saida_emergencia", dados)
        _SESSION_CACHE[uf] = dados
        return dados

    dados = _ler_cache_normas(projeto_dir).get(uf, {}).get(u"saida_emergencia")
    _SESSION_CACHE[uf] = dados or False
    return dados


def _hazen_c_da_base_central(materiais_tubulacao):
    """Constrói o dict hazen_c (apelido local -> fator C) a partir do array
    materiais_tubulacao vindo da base central — ver
    _ALIAS_MATERIAL_TUBULACAO acima."""
    hazen_c = {}
    for item in materiais_tubulacao or []:
        chave = item.get(u"key")
        fator = item.get(u"fatorC")
        if not chave or fator is None:
            continue
        hazen_c[_ALIAS_MATERIAL_TUBULACAO.get(chave, chave)] = fator
    return hazen_c


def _tipos_da_base_central(tipos_sistema_remoto):
    """Constrói 'tipos' (Tabela 2 — quais Tipos de sistema existem e seus
    parâmetros) a partir do payload remoto 'tipos_sistema' (mesmo formato
    que TIPOS_SISTEMA no site: {"1": {label, vazaoMin, expedicoes,
    variantes:[{esguicho, pressaoMin, mangueiraDn, mangueiraComprimento}]}, ...})
    pro vocabulário que hidrantes/sistema.py já indexa. "esguicho_dn" fica
    dentro de cada variante (não um só valor por Tipo): o Tipo 4, por
    exemplo, tem uma variante com esguicho DN40 e outra com DN65."""
    tipos = {}
    for tipo_str, dados in (tipos_sistema_remoto or {}).items():
        try:
            tipo_num = int(tipo_str)
        except (TypeError, ValueError):
            continue
        tipos[tipo_num] = {
            u"descricao": dados.get(u"label"),
            u"variantes": [
                {
                    u"mang_dn":     v.get(u"mangueiraDn"),
                    u"mang_comp":   v.get(u"mangueiraComprimento"),
                    u"q_min":       dados.get(u"vazaoMin"),
                    u"p_min":       v.get(u"pressaoMin"),
                    u"expedicoes":  dados.get(u"expedicoes"),
                    u"esguicho_dn": v.get(u"esguicho"),
                }
                for v in (dados.get(u"variantes") or [])
            ],
        }
    return tipos


def _buscar_hidrantes(uf, projeto_dir):
    """Mesmo esquema de _buscar_saidas, pro sistema 'hidrantes' (mesma
    linha de normas_dados que src/data/normas/<UF>/hidrantes.js, no site,
    já lê)."""
    if uf in _SESSION_CACHE_HIDRANTES:
        return _SESSION_CACHE_HIDRANTES[uf] or None

    from sync import buscar_norma

    dados, erro = buscar_norma(uf, u"hidrantes")
    if dados:
        _gravar_cache_normas(projeto_dir, uf, u"hidrantes", dados)
        _SESSION_CACHE_HIDRANTES[uf] = dados
        return dados

    dados = _ler_cache_normas(projeto_dir).get(uf, {}).get(u"hidrantes")
    _SESSION_CACHE_HIDRANTES[uf] = dados or False
    return dados


def get_estado(sigla, projeto_dir):
    """Retorna o dict ESTADO pra sigla (uf) informada, buscado inteiramente
    na base normativa central (com cache em memória/no firedata.json do
    projeto por cima) — ou None se não houver nada cadastrado pra essa UF
    (nem saída de emergência nem hidrantes, nem uma consulta anterior
    guardada no cache do projeto)."""
    sigla = sigla.upper()
    estado = {}

    remoto = _buscar_saidas(sigla, projeto_dir)
    if remoto:
        for chave in _CHAVES_SAIDAS:
            if chave in remoto:
                estado[chave] = remoto[chave]

    remoto_hid = _buscar_hidrantes(sigla, projeto_dir)
    if remoto_hid:
        hidrantes = {}
        for chave in _CHAVES_HIDRANTES:
            if chave in remoto_hid:
                valor = remoto_hid[chave]
                if chave in _CHAVES_HIDRANTES_NUMERICAS and valor is not None:
                    valor = float(valor)
                hidrantes[chave] = valor

        hazen_c_remoto = _hazen_c_da_base_central(remoto_hid.get(u"materiais_tubulacao"))
        if hazen_c_remoto:
            hidrantes[u"hazen_c"] = hazen_c_remoto

        # "norma" no payload vem como objeto ({desc, nome, estado}) — o
        # resto do código (norm_profiles.py, os scripts de dimensionamento)
        # espera uma string simples nessa chave.
        norma_remota = remoto_hid.get(u"norma")
        if isinstance(norma_remota, dict) and norma_remota.get(u"nome"):
            hidrantes[u"norma"] = norma_remota[u"nome"]

        tipos_remotos = _tipos_da_base_central(remoto_hid.get(u"tipos_sistema"))
        if tipos_remotos:
            hidrantes[u"tipos"] = tipos_remotos

        if hidrantes:
            estado[u"hidrantes"] = hidrantes

    if not estado:
        return None

    estado.setdefault(u"sigla", sigla)
    return estado
