# -*- coding: utf-8 -*-
"""
family_cache.py — Fire Utils · lib/
Download dos .rfa vindos do Supabase (bucket privado revit-families, via
Signed URL) para um arquivo TEMPORÁRIO — sem cache persistente.

Decisão deliberada de não manter cache em disco entre carregamentos:

  1. Depois que Document.LoadFamily() roda com sucesso, o Revit embute a
     família inteira dentro do próprio arquivo .rvt — o .rfa original não
     é mais necessário a partir daí, então não há motivo pra guardá-lo.
  2. Cache persistente só cresce, nunca some sozinho (família removida do
     catálogo vira lixo esquecido no disco do usuário para sempre).
  3. Sempre baixar de novo garante pegar a versão mais recente da família
     no Supabase — sem isso, o cache local poderia ficar "preso" numa
     versão desatualizada mesmo depois de o gestor da biblioteca subir
     uma família corrigida.

O arquivo temporário é responsabilidade de quem chama remover depois de
usar (ver remover_temporario) — normalmente logo após o LoadFamily, sem
esperar o posicionamento manual terminar.

Download via System.Net.WebClient (.NET) em vez de urllib/requests: dentro
do IronPython do pyRevit, é a forma mais confiável de baixar HTTPS sem
depender de pacotes extra nem lidar com bugs conhecidos do urllib2 do
IronPython com TLS.
"""

import os
import tempfile
import uuid

import clr
clr.AddReference(u"System")
from System import Uri
from System.Net import WebClient


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


def baixar_temporario(storage_key, signed_url, sha256_esperado=None):
    """
    Baixa `signed_url` para um arquivo temporário exclusivo desta chamada
    (nome único por uuid4, sem reaproveitar nada de execuções anteriores)
    e retorna o caminho. Levanta exceção se o download falhar ou (quando
    `sha256_esperado` for informado) se o checksum não bater — quem chama
    decide como reportar (ver family_webview_bridge.py).

    Quem chamar é responsável por apagar o arquivo depois de usar — ver
    remover_temporario.
    """
    extensao = os.path.splitext(storage_key)[1] or u".rfa"
    caminho_temp = os.path.join(
        tempfile.gettempdir(), u"FireUtils_{}{}".format(uuid.uuid4().hex, extensao)
    )

    cliente = WebClient()
    try:
        cliente.DownloadFile(Uri(signed_url), caminho_temp)
    finally:
        cliente.Dispose()

    if sha256_esperado is not None and _sha256_arquivo(caminho_temp) != sha256_esperado:
        os.remove(caminho_temp)
        raise ValueError(
            u"Checksum do arquivo baixado não confere com o catálogo "
            u"(storage_key={}).".format(storage_key)
        )

    return caminho_temp


def remover_temporario(caminho):
    """Apaga o arquivo temporário baixado por baixar_temporario. Best-effort
    — se falhar (arquivo em uso, já removido etc.), não interrompe o fluxo;
    o SO limpa a pasta temp eventualmente de qualquer forma."""
    try:
        if caminho and os.path.isfile(caminho):
            os.remove(caminho)
    except OSError:
        pass
