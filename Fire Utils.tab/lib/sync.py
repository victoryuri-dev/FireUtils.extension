# -*- coding: utf-8 -*-
"""
sync.py — Fire Utils · lib/
Envio best-effort dos dados calculados para o Supabase (Edge Function
revit-sync), além da gravação local do firedata.json — não a substitui.

Uso em qualquer calc.py:
    from sync import enviar
    enviar(u"extintores", payload, projeto_dir)

Se o projeto não tiver um token de sincronização configurado (Projeto →
Dados do Projeto), a função não faz nada — sync é opt-in e nunca deve
bloquear, atrasar perceptivelmente ou quebrar o fluxo local do Revit.
"""

import io
import os
import json

_SYNC_URL     = u"https://lngvagifcukglgdjildw.supabase.co/functions/v1/revit-sync"
_ANON_KEY     = u"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxuZ3ZhZ2lmY3VrZ2xnZGppbGR3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDUwNzksImV4cCI6MjEwMjMyMTA3OX0.hApUcA5wunyv21JdL8XAVVD1TnGU9oRvyew1uCIlZRw"
_CACHE_NOME   = u"firedata.json"
_MEDIDAS_VALIDAS = (u"extintores", u"hidrantes", u"saidas_emergencia")


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def token_atual(projeto_dir):
    """Lê o token de sincronização salvo em firedata.json (chave 'sync').
    Retorna None se não houver projeto salvo ou token configurado."""
    try:
        with io.open(_cache_path(projeto_dir), u"r", encoding=u"utf-8") as f:
            dados = json.loads(f.read())
        token = (dados.get(u"sync") or {}).get(u"token")
        return token or None
    except Exception:
        return None


def enviar(medida, payload, projeto_dir):
    """Envia `payload` para a Edge Function revit-sync, best-effort.

    Nunca lança exceção — qualquer falha (sem token configurado, sem rede,
    timeout, erro do servidor) é silenciosamente ignorada, porque o
    firedata.json local já foi gravado antes desta chamada e continua
    sendo a fonte de verdade offline.
    """
    if medida not in _MEDIDAS_VALIDAS:
        return

    token = token_atual(projeto_dir)
    if not token:
        return

    try:
        import clr
        clr.AddReference(u"System.Net")
        from System.Net import WebRequest, ServicePointManager, SecurityProtocolType
        from System.Text import Encoding

        # IronPython/.NET Framework antigo não negocia TLS1.2 por padrão —
        # o Supabase exige TLS1.2+, então toda chamada falharia sem isto.
        ServicePointManager.SecurityProtocol = (
            ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
        )

        corpo = json.dumps({u"token": token, u"medida": medida, u"payload": payload}, ensure_ascii=False)
        dados_bytes = Encoding.UTF8.GetBytes(corpo)

        req = WebRequest.Create(_SYNC_URL)
        req.Method = u"POST"
        req.ContentType = u"application/json"
        req.Timeout = 5000
        req.Headers.Add(u"Authorization", u"Bearer " + _ANON_KEY)
        req.Headers.Add(u"apikey", _ANON_KEY)
        req.ContentLength = dados_bytes.Length

        stream = req.GetRequestStream()
        stream.Write(dados_bytes, 0, dados_bytes.Length)
        stream.Close()

        resp = req.GetResponse()
        resp.Close()
    except Exception:
        pass
