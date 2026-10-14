# -*- coding: utf-8 -*-
"""
licenca.py — quais módulos esta conta pode usar.

A verificação acontece uma vez por sessão do Revit, não a cada clique: o
startup.py chama `verificar()` ao carregar a extensão, e o resultado vale
enquanto o Revit estiver aberto. Cada ferramenta consulta `tem_acesso()`,
que só lê o que já foi decidido.

Quem autentica é a dockpane (React/Supabase). Ao fazer login ela manda a
sessão para cá pela bridge (SET_SESSAO), e o refresh token fica guardado no
disco — é o que permite verificar a licença no startup seguinte, antes de o
painel ser aberto.

Módulos vêm de `public.licencas` no Supabase, os mesmos da página de preços:
'hidrantes', 'saidas', 'memorial' e 'pro' (que inclui os três).

Por que cache em arquivo e não em memória: o pyRevit roda o startup.py e o
script.py de cada botão em engines IronPython separados, que reimportam este
módulo do zero. Uma variável de módulo não sobreviveria de um clique para o
outro. O arquivo guarda o PID do Revit junto, então o cache vale para esta
sessão e não para a próxima.
"""

import io
import os
import json
import datetime

from family_error_utils import texto_erro

_SUPABASE_URL = u"https://lngvagifcukglgdjildw.supabase.co"
_ANON_KEY = (
    u"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    u"eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxuZ3ZhZ2lmY3VrZ2xnZGppbGR3Iiwicm9sZSI6ImFub24i"
    u"LCJpYXQiOjE3ODY3NDUwNzksImV4cCI6MjEwMjMyMTA3OX0."
    u"hApUcA5wunyv21JdL8XAVVD1TnGU9oRvyew1uCIlZRw"
)

# Mesmos módulos do constraint em public.licencas e da página de preços.
MODULO_PRO = u"pro"
MODULOS = (u"hidrantes", u"saidas", u"memorial", MODULO_PRO)

# Sem conseguir falar com o servidor, vale o último resultado conhecido por
# este tanto de dias. Sem isso, uma queda de internet (ou o avião) tiraria a
# ferramenta de quem pagou; com um prazo muito longo, desligar a rede viraria
# a forma de usar sem licença.
_DIAS_DE_GRACA = 7

# Rede no startup atrasa a abertura do Revit — melhor desistir rápido e
# cair na graça do cache do que segurar a tela de carregamento.
_TIMEOUT_MS = 8000


def _dir_dados():
    """%LOCALAPPDATA%\\FireUtils — criado sob demanda."""
    from System import Environment as DotNetEnvironment
    caminho = os.path.join(
        DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.LocalApplicationData),
        u"FireUtils",
    )
    if not os.path.isdir(caminho):
        os.makedirs(caminho)
    return caminho


def _arquivo_sessao():
    return os.path.join(_dir_dados(), u"sessao.dat")


def _arquivo_licencas():
    return os.path.join(_dir_dados(), u"licencas.json")


def _pid_do_revit():
    from System.Diagnostics import Process
    return Process.GetCurrentProcess().Id


# ---------------------------------------------------------------------------
# Sessão — o refresh token, protegido pelo DPAPI do Windows
# ---------------------------------------------------------------------------

def _escopo_dpapi():
    from System.Security.Cryptography import DataProtectionScope
    return DataProtectionScope.CurrentUser


def salvar_sessao(refresh_token):
    """
    Guarda o refresh token para as próximas sessões do Revit.

    É credencial de longa duração: quem a tiver entra na conta. Por isso vai
    cifrada pelo DPAPI, amarrada ao usuário do Windows — copiar o arquivo
    para outra máquina (ou outra conta) não serve de nada.
    """
    if not refresh_token:
        print(u"[AVISO] Sessão recebida sem refresh token — login não registrado.")
        return False

    try:
        from System.Security.Cryptography import ProtectedData
        from System.Text import Encoding
        from System.IO import File

        protegido = ProtectedData.Protect(
            Encoding.UTF8.GetBytes(refresh_token), None, _escopo_dpapi()
        )
        File.WriteAllBytes(_arquivo_sessao(), protegido)
        return True
    except Exception as ex:
        # Falhar em silêncio aqui deixaria o usuário logado na dockpane e
        # barrado nas ferramentas, sem nenhuma pista do motivo.
        print(u"[ERRO] Falha ao guardar a sessão: {}".format(texto_erro(ex)))
        return False


def _refresh_token_guardado():
    caminho = _arquivo_sessao()
    if not os.path.isfile(caminho):
        return None

    try:
        from System.Security.Cryptography import ProtectedData
        from System.Text import Encoding
        from System.IO import File

        aberto = ProtectedData.Unprotect(
            File.ReadAllBytes(caminho), None, _escopo_dpapi()
        )
        return Encoding.UTF8.GetString(aberto)
    except Exception:
        # Arquivo de outra máquina, de outro usuário do Windows, ou
        # corrompido: tratar como "não há sessão".
        return None


def esquecer_sessao():
    """Logout: apaga sessão e licenças em cache."""
    for caminho in (_arquivo_sessao(), _arquivo_licencas()):
        try:
            if os.path.isfile(caminho):
                os.remove(caminho)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _requisitar(url, metodo, cabecalhos, corpo=None):
    """
    Requisição HTTP com o WebRequest do .NET — mesma abordagem de sync.py,
    para não trazer dependência nova para o IronPython.

    Devolve (texto_da_resposta, erro). Erro é None em caso de sucesso.
    """
    from System.Net import WebRequest, WebException, ServicePointManager, SecurityProtocolType
    from System.IO import StreamReader
    from System.Text import Encoding

    try:
        # Servidores modernos recusam TLS antigo, e o padrão do .NET em
        # algumas instalações do Windows ainda é 1.0.
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    except Exception:
        pass

    try:
        req = WebRequest.Create(url)
        req.Method = metodo
        req.Timeout = _TIMEOUT_MS

        for chave, valor in cabecalhos.items():
            if chave.lower() == u"content-type":
                req.ContentType = valor
            else:
                req.Headers.Add(chave, valor)

        if corpo is not None:
            dados = Encoding.UTF8.GetBytes(corpo)
            req.ContentLength = dados.Length
            fluxo = req.GetRequestStream()
            try:
                fluxo.Write(dados, 0, dados.Length)
            finally:
                fluxo.Close()

        resposta = req.GetResponse()
        try:
            leitor = StreamReader(resposta.GetResponseStream(), Encoding.UTF8)
            try:
                return leitor.ReadToEnd(), None
            finally:
                leitor.Close()
        finally:
            resposta.Close()

    except WebException as ex:
        return None, texto_erro(ex)
    except Exception as ex:
        return None, texto_erro(ex)


def _renovar_acesso(refresh_token):
    """
    Troca o refresh token por um access token novo.

    O Supabase rotaciona o refresh token a cada uso, então o novo precisa ser
    guardado — senão a próxima sessão tenta usar um token já gasto.

    Devolve (access_token, erro).
    """
    url = u"{}/auth/v1/token?grant_type=refresh_token".format(_SUPABASE_URL)
    corpo = json.dumps({u"refresh_token": refresh_token})

    texto, erro = _requisitar(
        url,
        u"POST",
        {
            u"apikey": _ANON_KEY,
            u"Content-Type": u"application/json",
        },
        corpo,
    )
    if erro:
        return None, erro

    try:
        dados = json.loads(texto)
    except Exception as ex:
        return None, texto_erro(ex)

    acesso = dados.get(u"access_token")
    if not acesso:
        return None, u"resposta sem access_token"

    novo_refresh = dados.get(u"refresh_token")
    if novo_refresh:
        salvar_sessao(novo_refresh)

    return acesso, None


def _buscar_licencas(access_token):
    """
    Lê as licenças da conta. A política licencas_select_proprio do Supabase
    já limita o resultado ao próprio usuário — não há o que filtrar aqui.

    Devolve (lista_de_linhas, erro).
    """
    url = u"{}/rest/v1/licencas?select=modulo,plano,situacao,inicio_em,expira_em".format(
        _SUPABASE_URL
    )

    texto, erro = _requisitar(
        url,
        u"GET",
        {
            u"apikey": _ANON_KEY,
            u"Authorization": u"Bearer " + access_token,
        },
    )
    if erro:
        return None, erro

    try:
        return json.loads(texto), None
    except Exception as ex:
        return None, texto_erro(ex)


# ---------------------------------------------------------------------------
# Decisão de acesso
# ---------------------------------------------------------------------------

def _hoje():
    """
    Data de hoje no fuso de Brasília — o mesmo critério de tem_licenca() no
    Supabase. Sem isso, uma licença venceria três horas antes da meia-noite
    local para quem está no Brasil.
    """
    return (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).date()


def _licenca_vale(linha):
    if linha.get(u"situacao") not in (u"ativa", u"teste"):
        return False

    expira = linha.get(u"expira_em")
    if not expira:
        return True  # sem data de término

    try:
        ano, mes, dia = [int(p) for p in expira.split(u"-")[:3]]
        return datetime.date(ano, mes, dia) >= _hoje()
    except Exception:
        # Data ilegível: não dá para afirmar que está válida.
        return False


def _modulos_validos(linhas):
    liberados = set()
    for linha in linhas or []:
        if _licenca_vale(linha):
            modulo = linha.get(u"modulo")
            if modulo:
                liberados.add(modulo)
    return liberados


def _gravar_cache(modulos, email=None):
    dados = {
        u"pid": _pid_do_revit(),
        u"verificado_em": datetime.datetime.utcnow().isoformat(),
        u"modulos": sorted(modulos),
        u"email": email,
    }
    try:
        with io.open(_arquivo_licencas(), u"w", encoding=u"utf-8") as arquivo:
            arquivo.write(json.dumps(dados, ensure_ascii=False))
    except Exception:
        pass


def _ler_cache():
    caminho = _arquivo_licencas()
    if not os.path.isfile(caminho):
        return None
    try:
        with io.open(caminho, u"r", encoding=u"utf-8") as arquivo:
            return json.loads(arquivo.read())
    except Exception:
        return None


def _dias_desde(iso):
    try:
        quando = datetime.datetime.strptime(iso[:19], u"%Y-%m-%dT%H:%M:%S")
        return (datetime.datetime.utcnow() - quando).days
    except Exception:
        return None


def verificar():
    """
    Consulta o servidor e atualiza o cache da sessão.

    Chamado pelo startup.py quando o Revit abre, e de novo quando a dockpane
    faz login (daí o acesso valer na hora, sem reiniciar o Revit).

    Devolve (modulos_liberados, erro). Com erro, `modulos_liberados` é o que
    valia antes, dentro do prazo de graça.
    """
    refresh = _refresh_token_guardado()
    if not refresh:
        _gravar_cache(set())
        return set(), u"nenhuma sessão: faça login no Carregador de Famílias"

    acesso, erro = _renovar_acesso(refresh)
    if erro:
        return _acesso_em_graca(erro)

    linhas, erro = _buscar_licencas(acesso)
    if erro:
        return _acesso_em_graca(erro)

    modulos = _modulos_validos(linhas)
    _gravar_cache(modulos)
    return modulos, None


def _acesso_em_graca(erro):
    """
    Sem resposta do servidor, vale o último resultado — por um tempo.
    Passado o prazo, o acesso cai: do contrário bastaria ficar offline.
    """
    cache = _ler_cache()
    if not cache:
        return set(), erro

    dias = _dias_desde(cache.get(u"verificado_em", u""))
    if dias is None or dias > _DIAS_DE_GRACA:
        return set(), u"{} (última verificação há muito tempo)".format(erro)

    modulos = set(cache.get(u"modulos") or [])
    _gravar_cache(modulos, cache.get(u"email"))
    return modulos, None


def _cache_desta_sessao():
    """
    Cache gravado pelo Revit que está rodando agora, ou None.

    O PID é o que separa uma sessão da outra: cada abertura do Revit
    revalida, que é o combinado de verificar uma vez por sessão em vez de a
    cada clique.
    """
    cache = _ler_cache()
    if not cache or cache.get(u"pid") != _pid_do_revit():
        return None
    return cache


def modulos_liberados():
    """
    O que esta sessão pode usar, sem ir à rede. Vazio se a sessão ainda não
    foi verificada — use garantir_verificado() se precisar da resposta certa.
    """
    cache = _cache_desta_sessao()
    return set(cache.get(u"modulos") or []) if cache else set()


def garantir_verificado():
    """
    Os módulos desta sessão, verificando agora se ainda não foi.

    O startup.py dispara verificar() numa thread para não atrasar a abertura
    do Revit. Quem clica numa ferramenta antes de essa thread terminar cairia
    num cache vazio e seria barrado sem motivo — aqui a verificação acontece
    na hora, de forma síncrona, e esse clique passa a esperar em vez de
    receber um "sem licença" falso.
    """
    cache = _cache_desta_sessao()
    if cache is not None:
        return set(cache.get(u"modulos") or [])

    modulos, _erro = verificar()
    return modulos


def tem_acesso(modulo):
    """
    A conta pode usar este módulo nesta sessão? A licença PRO libera todos.
    """
    liberados = garantir_verificado()
    return modulo in liberados or MODULO_PRO in liberados


def esta_autenticado():
    return _refresh_token_guardado() is not None
