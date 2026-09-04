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

IMPORTANTE sobre o NOME do arquivo temporário: o Revit usa o nome do
ARQUIVO (sem a extensão) no momento do Document.LoadFamily() como o nome
da Family dentro do projeto — não existe metadado interno separado que
preserve um "nome bonito" independente disso. Por isso o arquivo baixado
precisa se chamar como a família do catálogo (ex.: "Extintor Portátil -
ABC.rfa"), nunca um nome gerado (como um uuid4) — do contrário toda
família carregada por aqui ganhava um nome gigante e ilegível no projeto,
e a checagem de "já existe" em family_loader.carregar_familias (que
compara pelo nome do catálogo) nunca batia, gerando uma família NOVA a
cada clique em vez de reaproveitar a já carregada.

IMPORTANTE sobre a PASTA temporária: usa System.IO.Path.GetTempPath()
(.NET) em vez de tempfile.gettempdir() (Python) de propósito.
tempfile.gettempdir() sob o IronPython do pyRevit devolve um `str` (bytes)
em vez de um `unicode`, decodificado pela codepage ANSI do Windows — em
máquinas com o nome do usuário acentuado (comum em Windows em
português, ex. "C:\\Users\\Usuário\\AppData\\Local\\Temp"), juntar esse
`str` com qualquer `unicode` (via os.path.join) força uma decodificação
implícita que o IronPython não sabe fazer ("'unknown' codec can't decode
byte 0xe1..."), derrubando a ação inteira sem nenhuma pista melhor que
essa mensagem genérica. Path.GetTempPath() já devolve uma
System.String — sempre Unicode de verdade, sem essa ambiguidade.
"""

import os
import re
import uuid

import clr
clr.AddReference(u"System")
from System import Uri
from System.IO import Path
from System.Net import WebClient

_CARACTERES_INVALIDOS_EM_ARQUIVO = re.compile(u'[<>:"/\\\\|?*]')


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


def _nome_arquivo_seguro(nome):
    """Remove caracteres inválidos em nome de arquivo do Windows — o nome
    da família no catálogo é definido por quem gerencia o acervo, mas
    sanear aqui evita que um caractere inesperado quebre o download."""
    nome = _CARACTERES_INVALIDOS_EM_ARQUIVO.sub(u"_", nome).strip(u" .")
    return nome or u"familia"


def baixar_temporario(storage_key, signed_url, nome_familia, sha256_esperado=None):
    """
    Baixa `signed_url` para um arquivo temporário e retorna o caminho.
    Levanta exceção se o download falhar ou (quando `sha256_esperado` for
    informado) se o checksum não bater — quem chama decide como reportar
    (ver family_webview_bridge.py).

    O arquivo é nomeado como `nome_familia` (o nome do catálogo — ver nota
    no topo do módulo sobre por que isso importa pro Revit), dentro de uma
    subpasta com nome único (uuid4) só pra garantir que dois downloads não
    colidam no mesmo arquivo; a unicidade não entra no nome do arquivo em
    si.

    Quem chamar é responsável por apagar o arquivo depois de usar — ver
    remover_temporario.
    """
    extensao = os.path.splitext(storage_key)[1] or u".rfa"
    pasta_unica = os.path.join(Path.GetTempPath(), u"FireUtils_{}".format(uuid.uuid4().hex))
    os.makedirs(pasta_unica)
    caminho_temp = os.path.join(pasta_unica, _nome_arquivo_seguro(nome_familia) + extensao)

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
    """Apaga o arquivo temporário baixado por baixar_temporario (e a
    subpasta única que o continha). Best-effort — se falhar (arquivo em
    uso, já removido etc.), não interrompe o fluxo; o SO limpa a pasta
    temp eventualmente de qualquer forma."""
    if not caminho:
        return
    pasta = os.path.dirname(caminho)
    try:
        if os.path.isfile(caminho):
            os.remove(caminho)
    except OSError:
        pass
    try:
        os.rmdir(pasta)
    except OSError:
        pass
