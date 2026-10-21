# -*- coding: utf-8 -*-
"""
plugin_atualizacao.py — Fire Utils · lib/
Baixa, confere e instala uma versão nova do plugin a pedido da dockpane
(mensagem INSTALAR_ATUALIZACAO).

Por que não é só "baixar e rodar": isto EXECUTA um programa que veio da
internet, com os direitos do usuário. Então nada é rodado sem passar por duas
conferências, e o próprio pedido da dockpane é tratado como não confiável:

  1. Origem. Só aceita links assinados do bucket `plugin-releases` do projeto
     Supabase deste plugin, para um arquivo `FireUtils-Setup-X.Y.Z.exe` cuja
     versão é MAIOR que a instalada (nunca volta versão).
  2. Integridade. O SHA-256 do arquivo precisa bater com o `.sha256` publicado
     ao lado dele (pega download truncado ou corrompido).
  3. Autenticidade. A assinatura Authenticode do .exe precisa ser válida e o
     nome do assinante (CN do certificado) precisa ser `_PUBLICADOR_ASSINATURA`,
     fixado neste arquivo como a chave pública de licenca.py. É isto que impede
     alguém que invada o bucket de trocar o instalador (e o .sha256 junto).

Enquanto `_PUBLICADOR_ASSINATURA` estiver vazio (instalador ainda não assinado)
a instalação automática fica DESLIGADA: o plugin baixa e confere o hash, mas
só abre a pasta com o instalador — quem decide executar é o usuário.

Instalação: o instalador não roda com o Revit aberto (as DLLs do WebView2 ficam
em uso). Um script (atualizar_plugin.ps1) é copiado para uma pasta temporária e
roda em segundo plano: espera todo Revit fechar, confere o arquivo DE NOVO e só
então executa o instalador em modo silencioso. O usuário só precisa fechar o
Revit; se o script morrer (logoff, por exemplo), a dockpane oferece a
atualização de novo na próxima vez.

Fluxo (a rede e o disco ficam numa thread de fundo; mensagens à dockpane voltam
pela thread de API, que é a única onde postar_mensagem é seguro):
    ATUALIZACAO_PROGRESSO  {etapa: "baixando"|"verificando", percentual?}
    ATUALIZACAO_RESULTADO  {ok, versao, estado: "agendada"|"manual", pasta?}
                         | {ok: False, erro}
"""

import io
import json
import os
import re
import shutil
import threading

from family_error_utils import texto_erro
import plugin_versao

# CN (nome do assinante) do certificado de assinatura de código do instalador.
# Vazio = instalador ainda não assinado = instalação automática desligada.
# Preencha com o nome EXATO que aparece no certificado, por exemplo
# u"Empresa Exemplo Ltda". installer/build.ps1 avisa quando está vazio.
_PUBLICADOR_ASSINATURA = u""

# O bucket privado do projeto Supabase deste plugin (mesmo host de sync.py).
_HOST_STORAGE = u"lngvagifcukglgdjildw.supabase.co"
_PREFIXO_STORAGE = u"/storage/v1/object/sign/plugin-releases/"

# Teto de tamanho: o instalador tem algumas dezenas de MB. Acima disto é
# arquivo errado (ou ataque), não atualização.
_LIMITE_BYTES = 400 * 1024 * 1024
_TIMEOUT_MS = 30000

_NOME_INSTALADOR = re.compile(r"^FireUtils-Setup-(\d+(?:\.\d+){0,3})\.exe$")
_SHA256 = re.compile(r"\b([0-9a-fA-F]{64})\b")

_em_andamento = False
_trava = threading.Lock()


class _Falha(Exception):
    """Falha com texto pronto para o usuário."""


# ---------------------------------------------------------------------------
# Regras puras (testáveis fora do Revit)
# ---------------------------------------------------------------------------

def comparar_versoes(a, b):
    """-1, 0 ou 1. Partes que faltam valem 0 ("2.1" = "2.1.0")."""
    pa = [int(x) for x in a.strip().split(u".")]
    pb = [int(x) for x in b.strip().split(u".")]
    for i in range(max(len(pa), len(pb))):
        x = pa[i] if i < len(pa) else 0
        y = pb[i] if i < len(pb) else 0
        if x != y:
            return -1 if x < y else 1
    return 0


def url_permitida(url, nome_arquivo):
    """
    O link é https, do bucket certo do projeto certo e aponta para
    `nome_arquivo` — nada de redirecionar o download para outro lugar.
    """
    try:
        from urlparse import urlparse
    except ImportError:  # pragma: no cover  (CPython 3, nos testes)
        from urllib.parse import urlparse
    try:
        partes = urlparse(url)
    except Exception:
        return False
    if partes.scheme != u"https" or (partes.hostname or u"").lower() != _HOST_STORAGE:
        return False
    if partes.port not in (None, 443) or partes.username or partes.password:
        return False
    return partes.path == _PREFIXO_STORAGE + nome_arquivo and u"token=" in (partes.query or u"")


def validar_pedido(payload, versao_instalada):
    """
    Confere o pedido da dockpane. Devolve (dados, erro): `dados` =
    {versao, nome, url_instalador, url_hash} ou None com `erro` em texto.
    """
    payload = payload or {}
    nome = payload.get(u"arquivo")
    try:
        achou = _NOME_INSTALADOR.match(nome)
    except TypeError:
        achou = None
    if not achou:
        return None, u"Nome de instalador inválido."
    versao = achou.group(1)
    if payload.get(u"versao") != versao:
        return None, u"A versão informada não bate com o instalador."

    if not re.match(r"^\d+(\.\d+){0,3}$", versao_instalada or u""):
        return None, (u"Esta instalação do plugin não tem versão (ambiente de "
                      u"desenvolvimento): atualize pelo instalador.")
    if comparar_versoes(versao, versao_instalada) <= 0:
        return None, u"A versão instalada ({}) já é a mais recente.".format(versao_instalada)

    url_instalador = payload.get(u"urlInstalador")
    url_hash = payload.get(u"urlHash")
    if not url_permitida(url_instalador, nome) or not url_permitida(url_hash, nome + u".sha256"):
        return None, u"Endereço de download não reconhecido."

    return {u"versao": versao, u"nome": nome,
            u"url_instalador": url_instalador, u"url_hash": url_hash}, None


def ler_sha256(texto):
    """O hash (hex minúsculo) de um arquivo `.sha256` — aceita "<hash>" e
    "<hash>  nome" (formato do sha256sum). None se não houver um."""
    achou = _SHA256.search(texto or u"")
    return achou.group(1).lower() if achou else None


def cn_do_assunto(assunto):
    """CN de um 'Subject' de certificado (CN=..., O=..., C=...), com ou sem
    aspas (nomes com vírgula vêm entre aspas). None se não houver."""
    achou = re.search(r'(?:^|,\s*)CN=(?:"((?:[^"]|"")*)"|([^,]*))', assunto or u"")
    if not achou:
        return None
    valor = achou.group(1)
    if valor is not None:
        return valor.replace(u'""', u'"').strip()
    return achou.group(2).strip()


def assinatura_confere(status, assunto, publicador):
    """A assinatura é válida e é do publicador esperado?"""
    return bool(publicador) and status == u"Valid" and cn_do_assunto(assunto) == publicador


def instalacao_automatica_ligada():
    return bool(_PUBLICADOR_ASSINATURA)


# ---------------------------------------------------------------------------
# Disco e rede (.NET, só dentro do Revit)
# ---------------------------------------------------------------------------

def _pasta_atualizacao():
    from System import Environment as DotNetEnvironment
    pasta = os.path.join(
        DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.LocalApplicationData),
        u"FireUtils", u"atualizacao")
    if not os.path.isdir(pasta):
        os.makedirs(pasta)
    return pasta


def _abrir(url):
    import clr
    clr.AddReference(u"System.Net")
    from System.Net import WebRequest, ServicePointManager, SecurityProtocolType
    try:
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12
    except Exception:
        pass
    req = WebRequest.Create(url)
    req.Method = u"GET"
    req.Timeout = _TIMEOUT_MS
    req.ReadWriteTimeout = _TIMEOUT_MS
    req.AllowAutoRedirect = False  # um link assinado não redireciona: se redirecionar, é desvio
    return req.GetResponse()


def _baixar_texto(url):
    from System.IO import StreamReader
    from System.Text import Encoding
    try:
        resposta = _abrir(url)
        try:
            leitor = StreamReader(resposta.GetResponseStream(), Encoding.UTF8)
            try:
                return leitor.ReadToEnd()
            finally:
                leitor.Close()
        finally:
            resposta.Close()
    except Exception as ex:
        raise _Falha(u"Não foi possível baixar o arquivo de conferência: {}".format(texto_erro(ex)))


def _baixar_arquivo(url, destino, ao_progresso):
    from System import Array, Byte
    from System.IO import FileStream, FileMode, FileAccess, FileShare
    try:
        resposta = _abrir(url)
        try:
            total = int(resposta.ContentLength)
            if total > _LIMITE_BYTES:
                raise _Falha(u"O instalador é maior do que o esperado; download cancelado.")
            origem = resposta.GetResponseStream()
            # `None` é palavra reservada em Python: o membro do .NET se pega por getattr.
            saida = FileStream(destino, FileMode.Create, FileAccess.Write, getattr(FileShare, u"None"))
            try:
                buffer = Array.CreateInstance(Byte, 65536)
                lidos = 0
                while True:
                    n = origem.Read(buffer, 0, buffer.Length)
                    if n <= 0:
                        break
                    lidos += n
                    if lidos > _LIMITE_BYTES:
                        raise _Falha(u"O instalador é maior do que o esperado; download cancelado.")
                    saida.Write(buffer, 0, n)
                    ao_progresso(lidos, total)
            finally:
                saida.Close()
        finally:
            resposta.Close()
    except _Falha:
        raise
    except Exception as ex:
        raise _Falha(u"O download falhou: {}".format(texto_erro(ex)))


def _sha256_do_arquivo(caminho):
    from System.IO import File
    from System.Security.Cryptography import SHA256Managed
    fluxo = File.OpenRead(caminho)
    try:
        algoritmo = SHA256Managed()
        hex_ = u"".join(u"{:02x}".format(int(b)) for b in algoritmo.ComputeHash(fluxo))
    finally:
        fluxo.Close()
    return hex_


def _assinatura_do_arquivo(caminho):
    """(status, assunto) da assinatura Authenticode, pelo PowerShell do Windows
    (verifica a cadeia até uma raiz confiável e a integridade do arquivo). O
    caminho vai por variável de ambiente, nunca montado dentro do comando."""
    from System.Diagnostics import Process, ProcessStartInfo
    comando = (u"$s = Get-AuthenticodeSignature -LiteralPath $env:FIREUTILS_ARQUIVO; "
               u"$c = if ($s.SignerCertificate) { $s.SignerCertificate.Subject } else { '' }; "
               u"[pscustomobject]@{ Status = [string]$s.Status; Subject = $c } | ConvertTo-Json -Compress")
    info = ProcessStartInfo(u"powershell.exe",
                            u"-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"{}\"".format(comando))
    info.UseShellExecute = False
    info.CreateNoWindow = True
    info.RedirectStandardOutput = True
    info.EnvironmentVariables[u"FIREUTILS_ARQUIVO"] = caminho
    processo = Process.Start(info)
    saida = processo.StandardOutput.ReadToEnd()
    processo.WaitForExit(60000)
    try:
        dados = json.loads(saida.strip())
    except Exception:
        return u"Unknown", u""
    return dados.get(u"Status"), dados.get(u"Subject")


# ---------------------------------------------------------------------------
# Fluxo
# ---------------------------------------------------------------------------

def tratar_instalar_atualizacao(uiapp, payload, fila_acoes, postar_mensagem):
    global _em_andamento

    def responder(mensagem):
        fila_acoes.enfileirar(lambda _uiapp: postar_mensagem(u"ATUALIZACAO_RESULTADO", mensagem))

    dados, erro = validar_pedido(payload, plugin_versao.versao_instalada())
    if erro:
        postar_mensagem(u"ATUALIZACAO_RESULTADO", {u"ok": False, u"erro": erro})
        return

    with _trava:
        if _em_andamento:
            postar_mensagem(u"ATUALIZACAO_RESULTADO", {
                u"ok": False, u"erro": u"Já há uma atualização em andamento."})
            return
        _em_andamento = True

    def trabalho():
        global _em_andamento
        try:
            responder(_executar(dados, fila_acoes, postar_mensagem))
        except _Falha as ex:
            responder({u"ok": False, u"erro": u"{}".format(ex)})
        except Exception as ex:
            responder({u"ok": False,
                       u"erro": u"Falha inesperada na atualização: {}".format(texto_erro(ex))})
        finally:
            _em_andamento = False

    threading.Thread(target=trabalho).start()


def _executar(dados, fila_acoes, postar_mensagem):
    def progresso(etapa, percentual=None):
        mensagem = {u"etapa": etapa, u"percentual": percentual}
        fila_acoes.enfileirar(lambda _uiapp: postar_mensagem(u"ATUALIZACAO_PROGRESSO", mensagem))

    pasta = _pasta_atualizacao()
    destino = os.path.join(pasta, dados[u"nome"])
    parcial = destino + u".parcial"
    for caminho in (destino, parcial):
        if os.path.isfile(caminho):
            os.remove(caminho)

    progresso(u"baixando", 0)
    esperado = ler_sha256(_baixar_texto(dados[u"url_hash"]))
    if not esperado:
        raise _Falha(u"O arquivo de conferência (.sha256) desta versão está ilegível.")

    ultimo = [-1]

    def ao_progresso(lidos, total):
        if total <= 0:
            return
        pct = int(lidos * 100 // total)
        if pct >= ultimo[0] + 5 or pct == 100:
            ultimo[0] = pct
            progresso(u"baixando", pct)

    _baixar_arquivo(dados[u"url_instalador"], parcial, ao_progresso)

    progresso(u"verificando")
    if _sha256_do_arquivo(parcial) != esperado:
        os.remove(parcial)
        raise _Falha(u"O arquivo baixado não confere com o hash publicado; ele foi descartado. "
                     u"Tente de novo.")

    if instalacao_automatica_ligada():
        status, assunto = _assinatura_do_arquivo(parcial)
        if not assinatura_confere(status, assunto, _PUBLICADOR_ASSINATURA):
            os.remove(parcial)
            raise _Falha(u"A assinatura digital do instalador não é a esperada; ele foi descartado "
                         u"e nada foi instalado.")

    os.rename(parcial, destino)

    if not instalacao_automatica_ligada():
        # Sem instalação automática quem executa é o usuário, então o arquivo
        # vai para onde ele procura: a pasta Downloads (já conferido).
        final = _mover_para_downloads(destino)
        _mostrar_na_pasta(final)
        return {u"ok": True, u"estado": u"manual", u"versao": dados[u"versao"],
                u"pasta": os.path.dirname(final)}

    _agendar_instalacao(pasta, destino, esperado)
    return {u"ok": True, u"estado": u"agendada", u"versao": dados[u"versao"]}


def _pasta_downloads():
    """A pasta Downloads do usuário (respeita redirecionamento, ex.: OneDrive
    ou outro disco); None se não for possível descobrir."""
    try:
        from Microsoft.Win32 import Registry
        # GUID da pasta conhecida "Downloads". O valor pode ser expansível
        # (%USERPROFILE%\Downloads); GetValue já o expande.
        caminho = Registry.GetValue(
            u"HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders",
            u"{374DE290-123F-4565-9164-39C4925E467B}", None)
        if caminho and os.path.isdir(caminho):
            return caminho
    except Exception:
        pass
    from System import Environment as DotNetEnvironment
    padrao = os.path.join(
        DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.UserProfile), u"Downloads")
    return padrao if os.path.isdir(padrao) else None


def _mover_para_downloads(arquivo):
    """Move o instalador conferido para Downloads. Se não achar a pasta ou
    falhar, deixa onde está (nunca perde o arquivo). Devolve o caminho final."""
    pasta = _pasta_downloads()
    if not pasta:
        return arquivo
    destino = os.path.join(pasta, os.path.basename(arquivo))
    try:
        shutil.copyfile(arquivo, destino)
        os.remove(arquivo)
        return destino
    except Exception:
        return arquivo


def _mostrar_na_pasta(arquivo):
    from System.Diagnostics import Process
    Process.Start(u"explorer.exe", u'/select,"{}"'.format(arquivo))


def _agendar_instalacao(pasta, instalador, sha256):
    """Copia o script para fora da extensão (o instalador apaga a pasta da
    extensão, e o script ainda estaria rodando) e o dispara em segundo plano."""
    from System.Diagnostics import Process, ProcessStartInfo

    origem = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"atualizar_plugin.ps1")
    script = os.path.join(pasta, u"atualizar_plugin.ps1")
    shutil.copyfile(origem, script)

    argumentos = (u'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{}" '
                  u'-Instalador "{}" -Sha256 {} -Publicador "{}" -Log "{}"').format(
        script, instalador, sha256, _PUBLICADOR_ASSINATURA,
        os.path.join(os.path.dirname(pasta), u"atualizacao.log"))
    info = ProcessStartInfo(u"powershell.exe", argumentos)
    info.UseShellExecute = False
    info.CreateNoWindow = True
    Process.Start(info)
