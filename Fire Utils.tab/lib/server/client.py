# -*- coding: utf-8 -*-
"""
client.py — Fire Utils · Cliente HTTP para IronPython

Usa System.Net.WebClient para se comunicar com o servidor Flask local.

API pública:
    servidor_ativo()             -> bool
    enviar_hidrantes(payload)    -> bool
    enviar_saidas(payload)       -> bool
    url_memorial()               -> str    # URL da página /memorial
    url_servidor()               -> str    # URL base
"""

import json

import clr
clr.AddReference("System")
clr.AddReference("System.Net")
from System.Net import WebClient, WebException
from System.Text import Encoding

_BASE = u"http://127.0.0.1:5000"


# ==============================================================================
def url_servidor():
    return _BASE


def url_memorial():
    return u"{}/memorial".format(_BASE)


# ==============================================================================
def servidor_ativo():
    """Retorna True se o servidor responder em /api/status."""
    try:
        wc = WebClient()
        wc.DownloadString(u"{}/api/status".format(_BASE))
        return True
    except Exception:
        return False


# ==============================================================================
def _post_json(endpoint, payload):
    """
    Faz POST de `payload` (dict) como JSON para `endpoint`.
    Retorna True se o servidor responder com {"ok": true}.
    """
    try:
        body   = json.dumps(payload, ensure_ascii=False)
        bytes_ = Encoding.UTF8.GetBytes(body)

        wc = WebClient()
        wc.Headers.Add(u"Content-Type", u"application/json; charset=utf-8")
        resp_bytes = wc.UploadData(
            u"{}/{}".format(_BASE, endpoint.lstrip(u"/")),
            u"POST",
            bytes_,
        )
        resp = Encoding.UTF8.GetString(resp_bytes)
        data = json.loads(resp)
        return bool(data.get(u"ok"))
    except Exception:
        return False


# ==============================================================================
def enviar_hidrantes(payload):
    """
    Envia o cache de hidrantes ao servidor.
    `payload` deve ser o mesmo dict salvo por salvar_cache().
    Retorna True em caso de sucesso.
    """
    return _post_json(u"/api/hidrantes", payload)


def enviar_saidas(payload):
    """
    Envia o cache de saídas ao servidor.
    `payload` deve ser o mesmo dict salvo por salvar_cache_saidas().
    Retorna True em caso de sucesso.
    """
    return _post_json(u"/api/saidas", payload)
