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

IMPORTANTE sobre o NOME do arquivo temporário: ele é montado a partir do
próprio `storage_key` (ex.: "extintor-de-incendio/extintor-portatil-a.rfa"
vira "extintor-portatil-a.rfa") — um slug sempre ASCII, gerado por quem
administra o catálogo — NUNCA a partir do nome de exibição da família
(que pode ter acento, ex. "Extintor Portátil - A").

Isso importa por dois motivos:

  1. O Revit usa o nome do ARQUIVO (sem extensão) como o nome inicial da
     Family dentro do projeto no momento do Document.LoadFamily() — um
     nome gerado (como um uuid4 puro) faria toda família carregada ganhar
     um nome gigante e ilegível no projeto. O slug do storage_key já é
     curto e legível, então nem precisa de correção posterior nesse
     ponto.
  2. Qualquer operação de arquivo (baixar, abrir pra somar o hash,
     carregar no Revit, apagar depois) que toque um caminho com caractere
     acentuado pode disparar a classe de erro de codificação do
     IronPython documentada em family_error_utils.py — mesmo com o
     caminho sendo Unicode de verdade (ver nota mais abaixo sobre
     Path.GetTempPath()), o problema reaparece porque essas chamadas
     acabam repassando o caminho pra APIs nativas do Windows por baixo, e
     alguma etapa nesse repasse ainda depende da codepage do sistema.
     Nunca usar um caractere acentuado no CAMINHO DE ARQUIVO evita a
     causa inteira, em vez de tentar prever every operação que poderia
     tropeçar nela.

O nome de exibição de verdade da família (com acento e tudo) é aplicado
depois, via Family.Name na API do Revit (ver
family_loader.carregar_familias) — uma troca só em memória, que nunca
passa perto de um caminho de disco.

IMPORTANTE sobre a PASTA temporária: usa System.IO.Path.GetTempPath()
(.NET) em vez de tempfile.gettempdir() (Python) de propósito.
tempfile.gettempdir() sob o IronPython do pyRevit devolve um `str` (bytes)
em vez de um `unicode`, decodificado pela codepage ANSI do Windows — em
máquinas com o nome do usuário acentuado (comum em Windows em
português, ex. "C:\\Users\\Usuário\\AppData\\Local\\Temp"), juntar esse
`str` com qualquer `unicode` (via os.path.join) força uma decodificação
implícita que o IronPython não sabe fazer ("'unknown' codec can't decode
byte 0xe1..."). Path.GetTempPath() já devolve uma System.String — sempre
Unicode de verdade, sem essa ambiguidade (mas isso sozinho não bastava
enquanto o NOME DO ARQUIVO em si ainda tinha acento — daí a mudança
acima).
"""

import os
import uuid

import clr
clr.AddReference(u"System")
from System import Uri
from System.IO import Path
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
    Baixa `signed_url` para um arquivo temporário e retorna o caminho.
    Levanta exceção se o download falhar ou (quando `sha256_esperado` for
    informado) se o checksum não bater — quem chama decide como reportar
    (ver family_webview_bridge.py).

    O arquivo é nomeado a partir do próprio `storage_key` — ver nota no
    topo do módulo sobre por que isso importa — dentro de uma subpasta
    com nome único (uuid4) só pra garantir que dois downloads não colidam
    no mesmo arquivo.

    Quem chamar é responsável por apagar o arquivo depois de usar — ver
    remover_temporario.
    """
    nome_arquivo = os.path.basename(storage_key) or u"familia.rfa"
    pasta_unica = os.path.join(Path.GetTempPath(), u"FireUtils_{}".format(uuid.uuid4().hex))
    os.makedirs(pasta_unica)
    caminho_temp = os.path.join(pasta_unica, nome_arquivo)

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
    temp eventualmente de qualquer forma. Captura `Exception` largo, não
    só `OSError`, pela mesma razão documentada no topo do módulo."""
    if not caminho:
        return
    pasta = os.path.dirname(caminho)
    try:
        if os.path.isfile(caminho):
            os.remove(caminho)
    except Exception:
        pass
    try:
        os.rmdir(pasta)
    except Exception:
        pass
