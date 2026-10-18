# -*- coding: utf-8 -*-
"""
motor_nuvem.py — Fire Utils · lib/
Cliente do motor de cálculo, que roda como Edge Function no Supabase
(repositório ETOS.FireUtils, supabase/functions/motor-*).

O plugin só lê o modelo do Revit e escreve o resultado de volta; as fórmulas,
a norma e as verificações normativas ficam no servidor. Por isso nada aqui
calcula coisa alguma — só monta o pedido, autentica e traduz a resposta.

Autenticação: o motor exige a sessão do usuário (access token do Supabase),
que a dockpane manda junto do pedido. A anon key, que é pública e está
embutida neste plugin, NÃO serve — a function a recusa. O refresh token
guardado por licenca.py não é usado aqui de propósito: renová-lo gira o token
que a dockpane também usa, e os dois acabariam se derrubando.

Quem chama costuma estar numa thread de fundo (a chamada leva de centenas de
milissegundos a vários segundos, conforme a internet): nunca chame isto de
dentro de um handler da fila do Revit sem uma thread — travaria a interface.

Toda chamada devolve um dict {ok, ...}; nunca lança. Em caso de falha vem
`erro` (texto pronto para o usuário) e `categoria`, para a dockpane escolher
o título do aviso:
    norma     o motor rodou e o sistema não atende (ou os dados não fecham)
    sessao    sem sessão, ou ela expirou
    licenca   a conta não tem o módulo
    conexao   sem internet, ou conexão lenta demais
    limite    pedidos demais em sequência
    servidor  falha do motor ou plugin incompatível com ele
"""

import json

from family_error_utils import texto_erro
from sync import _ANON_KEY

_FUNCOES_URL = u"https://lngvagifcukglgdjildw.supabase.co/functions/v1/"

# Cold start da function + rede ruim: melhor esperar um pouco mais do que
# falhar uma conta que ia dar certo. O usuário vê "Dimensionando..." enquanto isso.
_TIMEOUT_MS = 30000

# Contrato da resposta que este plugin entende (campo "versao" do motor).
# O motor sobe a versão quando muda o formato de um jeito que um plugin
# antigo não leria — melhor avisar para atualizar do que gravar lixo.
_VERSAO_SUPORTADA = {u"motor-hidrantes": 1}


def _falha(categoria, erro):
    return {u"ok": False, u"categoria": categoria, u"erro": erro}


def _enviar(url, corpo_json, access_token):
    """POST. Devolve (status, texto, erro_de_rede) — status None sem resposta."""
    import clr
    clr.AddReference(u"System.Net")
    from System.Net import WebRequest, WebException, ServicePointManager, SecurityProtocolType
    from System.Text import Encoding
    from System.IO import StreamReader

    try:
        # Servidores modernos recusam TLS antigo, e o padrão do .NET em
        # algumas instalações do Windows ainda é 1.0.
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    except Exception:
        pass

    dados = Encoding.UTF8.GetBytes(corpo_json)

    try:
        req = WebRequest.Create(url)
        req.Method = u"POST"
        req.ContentType = u"application/json; charset=utf-8"
        req.Timeout = _TIMEOUT_MS
        req.Headers.Add(u"Authorization", u"Bearer " + access_token)
        req.Headers.Add(u"apikey", _ANON_KEY)
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
                return int(resposta.StatusCode), leitor.ReadToEnd(), None
            finally:
                leitor.Close()
        finally:
            resposta.Close()

    except WebException as ex:
        resposta = ex.Response
        if resposta is None:
            return None, None, texto_erro(ex)
        try:
            leitor = StreamReader(resposta.GetResponseStream(), Encoding.UTF8)
            try:
                return int(resposta.StatusCode), leitor.ReadToEnd(), None
            finally:
                leitor.Close()
        finally:
            resposta.Close()
    except Exception as ex:
        return None, None, texto_erro(ex)


def _chamar(funcao, entrada, access_token):
    if not access_token:
        return _falha(
            u"sessao",
            u"Não encontrei a sua sessão. Entre na sua conta na dockpane "
            u"(Carregador de Famílias) e tente de novo.",
        )

    try:
        corpo = json.dumps(entrada, ensure_ascii=False)
    except Exception as ex:
        return _falha(u"servidor", u"Não foi possível montar o pedido: {}".format(texto_erro(ex)))

    status, texto, erro_rede = _enviar(_FUNCOES_URL + funcao, corpo, access_token)

    if status is None:
        return _falha(
            u"conexao",
            u"Não foi possível falar com o servidor de cálculo. O dimensionamento "
            u"precisa de internet — confira a conexão e tente de novo.",
        )

    try:
        dados = json.loads(texto)
    except Exception:
        dados = {}
    detalhe = dados.get(u"erro") if isinstance(dados, dict) else None

    if status == 200:
        if not isinstance(dados, dict):
            return _falha(u"servidor", u"Resposta inesperada do servidor de cálculo.")
        versao = dados.get(u"versao")
        if versao != _VERSAO_SUPORTADA.get(funcao):
            return _falha(
                u"servidor",
                u"O servidor de cálculo está numa versão diferente da deste plugin. "
                u"Atualize o Fire Utils para a versão mais recente.",
            )
        if dados.get(u"ok"):
            return dados
        return _falha(u"norma", detalhe or u"O dimensionamento não pôde ser concluído.")

    if status == 401:
        return _falha(u"sessao", u"Sua sessão expirou. Entre de novo na dockpane e tente outra vez.")
    if status == 403:
        return _falha(u"licenca", detalhe or u"Esta conta não tem licença para este módulo.")
    if status == 429:
        return _falha(u"limite", detalhe or u"Muitos pedidos em sequência. Aguarde um minuto e tente de novo.")
    if status in (400, 413):
        return _falha(
            u"servidor",
            u"O servidor de cálculo recusou os dados enviados ({}). Atualize o Fire Utils; "
            u"se continuar, reporte este erro.".format(detalhe or status),
        )

    return _falha(
        u"servidor",
        u"O servidor de cálculo não conseguiu processar o pedido (código {}). "
        u"Tente de novo em instantes.".format(status),
    )


def dimensionar_hidrantes(entrada, access_token):
    """
    Dimensionamento do Sistema de Hidrantes (método da marcha). `entrada` é o
    que o motor documenta em supabase/functions/motor-hidrantes/README.md
    (ETOS.FireUtils). Em sucesso devolve {ok: True, norma, resultado}.
    """
    return _chamar(u"motor-hidrantes", entrada, access_token)
