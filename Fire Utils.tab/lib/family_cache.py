# -*- coding: utf-8 -*-
"""
family_cache.py — Fire Utils · lib/
Fase 4 do plano de migração: cache local dos .rfa baixados do Supabase
(bucket privado revit-families, via Signed URL) — evita rebaixar o mesmo
arquivo em toda sessão do Revit.

Fica em %AppData%/FireUtils/FamilyCache/<category_id>/<family_id>.rfa,
espelhando a chave de storage usada no bucket (ver migration/generate_catalog.py).

Download via System.Net.WebClient (.NET) em vez de urllib/requests: dentro
do IronPython do pyRevit, é a forma mais confiável de baixar HTTPS sem
depender de pacotes extra nem lidar com bugs conhecidos do urllib2 do
IronPython com TLS.
"""

import os

import clr
clr.AddReference(u"System")
from System import Environment, Uri
from System.Net import WebClient

_APPDATA_DIR = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData)
CACHE_DIR = os.path.join(_APPDATA_DIR, u"FireUtils", u"FamilyCache")


def _caminho_cache(storage_key):
    """'extintor-de-incendio/extintor-portatil-abc.rfa' -> caminho local
    dentro de CACHE_DIR, preservando a mesma subpasta por categoria."""
    relativo = storage_key.replace(u"/", os.sep)
    return os.path.join(CACHE_DIR, relativo)


def _sha256_arquivo(caminho):
    import hashlib
    h = hashlib.sha256()
    with open(caminho, u"rb") as f:
        while True:
            bloco = f.read(1 << 20)
            if not bloco:
                break
            h.update(bloco)
    return h.hexdigest()


def obter_ou_baixar(storage_key, signed_url, sha256_esperado=None):
    """
    Retorna o caminho local do .rfa referente a `storage_key`, baixando de
    `signed_url` se ainda não estiver em cache (ou se `sha256_esperado` não
    bater com o que já está em disco — arquivo trocado no Supabase).

    Levanta exceção se o download falhar; quem chama decide como reportar
    (ver family_webview_bridge.py).
    """
    caminho = _caminho_cache(storage_key)

    if os.path.isfile(caminho):
        if sha256_esperado is None:
            return caminho  # sem hash pra conferir, confia na presença do arquivo
        try:
            if _sha256_arquivo(caminho) == sha256_esperado:
                return caminho
        except OSError:
            pass  # arquivo ilegível por algum motivo — trata como cache-miss e rebaixa

    pasta = os.path.dirname(caminho)
    if not os.path.isdir(pasta):
        os.makedirs(pasta)

    caminho_temporario = caminho + u".part"
    cliente = WebClient()
    try:
        cliente.DownloadFile(Uri(signed_url), caminho_temporario)
    finally:
        cliente.Dispose()

    if sha256_esperado is not None and _sha256_arquivo(caminho_temporario) != sha256_esperado:
        os.remove(caminho_temporario)
        raise ValueError(
            u"Checksum do arquivo baixado não confere com o catálogo "
            u"(storage_key={}).".format(storage_key)
        )

    if os.path.isfile(caminho):
        os.remove(caminho)
    os.rename(caminho_temporario, caminho)
    return caminho


def limpar_cache():
    """Apaga todo o cache local — útil pra depuração/forçar re-download geral."""
    import shutil
    if os.path.isdir(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
