# -*- coding: utf-8 -*-
"""
plugin_pacote.py — Fire Utils · lib/
Atualização rápida do plugin por PACOTE: só o código Python (e seus XAML, YAML,
imagens), sem instalador. Mensagem INSTALAR_PACOTE, vinda da dockpane.

Quando serve: mudança em Python, em novos bridges e em arquivos de dados do
plugin. Quando NÃO serve (precisa do instalador): DLLs (webview2_runtime),
startup.py, dependências (pyRevit/WebView2) ou qualquer coisa fora de
`Fire Utils.tab`. O pacote declara a menor versão de instalador que o aceita
(`baseMinima`) e o plugin recusa se a base instalada for menor.

Como é confiável sem certificado do Windows: o pacote é um .zip assinado com uma
chave RSA SUA (installer/scripts/gerar-chave-pacote.ps1). A chave privada fica só
no seu computador; a pública está embutida aqui (_CHAVE_PACOTE_*), como a da
licença — mas é OUTRA chave: a da licença mora nos secrets do Supabase, e esta
não pode ficar em nenhum servidor. Sem assinatura que confira, nada é aplicado.
Conferências, nesta ordem:
  1. Origem: link assinado do bucket certo do projeto certo (plugin_atualizacao).
  2. Assinatura RSA/SHA-256 do .zip inteiro com a chave pública embutida.
  3. O manifesto `pacote.json` DE DENTRO do zip (já assinado) bate com o nome do
     arquivo e com a versão instalada (nunca volta versão; base compatível).
  4. Cada entrada do zip: caminho dentro de `Fire Utils.tab/`, sem `..`, sem
     caminho absoluto, só extensões de código/dados — nunca DLL, EXE nem
     script de instalação.

Aplicação (com o Revit aberto): extrai para uma pasta de preparo, copia os
arquivos por cima da extensão, remove os arquivos de código que saíram do
pacote e grava `VERSION` POR ÚLTIMO — se algo falhar no meio, `VERSION` continua
na versão antiga e a dockpane oferece o pacote de novo (a aplicação é
idempotente). NÃO se guarda a versão anterior: a correção de um pacote ruim é o
pacote seguinte.

O Python já carregado na memória não muda até o Revit reiniciar; por isso, no
fim, o pyRevit é recarregado (melhor esforço) e a dockpane avisa para reiniciar
o Revit.

Mensagens à dockpane: ATUALIZACAO_PROGRESSO / ATUALIZACAO_RESULTADO (as mesmas do
instalador; o resultado traz estado "aplicada").
"""

import io
import json
import os
import re
import shutil
import threading
import time

from family_error_utils import texto_erro
import plugin_atualizacao
import plugin_versao

# Chave PÚBLICA que confere a assinatura dos pacotes (RSA 2048, base64: módulo e
# expoente). Gerada por installer/scripts/gerar-chave-pacote.ps1. Vazio = a
# atualização por pacote está desligada (nada confere).
_CHAVE_PACOTE_MODULO = u""
_CHAVE_PACOTE_EXPOENTE = u""

# O prefixo do pacote no bucket: FireUtils-Pacote-<versão>-base-<instalador>.zip
# (e o .zip.sig ao lado). A base no nome deixa a dockpane decidir sem baixar.
_NOME_PACOTE = re.compile(
    r"^FireUtils-Pacote-(\d+(?:\.\d+){0,3})-base-(\d+(?:\.\d+){0,3})\.zip$")

_PASTA_CODIGO = u"Fire Utils.tab/"
_EXTENSOES = (u".py", u".xaml", u".yaml", u".json", u".png", u".svg", u".ico",
              u".txt", u".md", u".ps1")
# O que o pacote nunca toca (binários e o acervo de famílias).
_PROTEGIDOS = (u"fire utils.tab/lib/webview2_runtime/", u"fire utils.tab/lib/family_library/")

_LIMITE_ZIP = 100 * 1024 * 1024
_LIMITE_DESCOMPACTADO = 300 * 1024 * 1024
_RECARREGAR_PYREVIT = True

_em_andamento = False
_trava = threading.Lock()


class _Falha(Exception):
    """Falha com texto pronto para o usuário."""


# ---------------------------------------------------------------------------
# Regras puras (testáveis fora do Revit)
# ---------------------------------------------------------------------------

def analisar_nome(nome):
    """(versao, base) de um nome de pacote, ou None."""
    try:
        achou = _NOME_PACOTE.match(nome)
    except TypeError:
        return None
    return (achou.group(1), achou.group(2)) if achou else None


def entrada_permitida(caminho):
    """
    Pode esta entrada do zip ser extraída? Entram o manifesto (`pacote.json`) e
    arquivos de código/dados sob `Fire Utils.tab/`, fora das áreas protegidas.
    `VERSION` NÃO entra: quem o grava é a aplicação, por último.
    """
    if not isinstance(caminho, type(u"")) and not isinstance(caminho, str):
        return False
    if caminho == u"pacote.json":
        return True
    if not caminho.startswith(_PASTA_CODIGO) or caminho.endswith(u"/"):
        return False
    if u"\\" in caminho or u":" in caminho or caminho.startswith(u"/"):
        return False
    partes = caminho.split(u"/")
    if any(p in (u"", u".", u"..") for p in partes):
        return False
    minusculo = caminho.lower()
    if any(minusculo.startswith(p) for p in _PROTEGIDOS):
        return False
    return minusculo.endswith(_EXTENSOES)


def codigo_gerenciado(rel):
    """Um arquivo da extensão que o pacote pode APAGAR por ter saído da versão
    nova (mesmas regras de extensão e áreas protegidas das entradas)."""
    minusculo = rel.lower()
    if not minusculo.startswith(u"fire utils.tab/"):
        return False
    if any(minusculo.startswith(p) for p in _PROTEGIDOS):
        return False
    if u"/__pycache__/" in minusculo:
        return False
    return minusculo.endswith(_EXTENSOES)


def validar_manifesto(manifesto, nome, versao_instalada, base_instalada):
    """O manifesto assinado bate com o nome e com o que está instalado?
    Devolve texto de erro ou None."""
    nomeado = analisar_nome(nome)
    if nomeado is None:
        return u"Nome de pacote inválido."
    versao, base = nomeado
    if not isinstance(manifesto, dict) or manifesto.get(u"versao") != versao \
            or manifesto.get(u"baseMinima") != base:
        return u"O manifesto do pacote não bate com o nome do arquivo."
    if not re.match(r"^\d+(\.\d+){0,3}$", versao_instalada or u""):
        return (u"Esta instalação do plugin não tem versão (ambiente de "
                u"desenvolvimento): atualize pelo instalador.")
    if plugin_atualizacao.comparar_versoes(versao, versao_instalada) <= 0:
        return u"A versão instalada ({}) já é a mais recente.".format(versao_instalada)
    if not re.match(r"^\d+(\.\d+){0,3}$", base_instalada or u"") \
            or plugin_atualizacao.comparar_versoes(base, base_instalada) > 0:
        return (u"Este pacote exige o instalador {} ou mais novo (o seu é o {}). "
                u"Baixe o instalador.".format(base, base_instalada))
    return None


def validar_pedido(payload, versao_instalada, base_instalada):
    """Confere o pedido da dockpane (não confiável). (dados, erro)."""
    payload = payload or {}
    nome = payload.get(u"arquivo")
    nomeado = analisar_nome(nome)
    if nomeado is None:
        return None, u"Nome de pacote inválido."
    versao, base = nomeado
    if payload.get(u"versao") != versao:
        return None, u"A versão informada não bate com o pacote."
    if not plugin_atualizacao.url_permitida(payload.get(u"urlPacote"), nome) \
            or not plugin_atualizacao.url_permitida(payload.get(u"urlAssinatura"), nome + u".sig"):
        return None, u"Endereço de download não reconhecido."
    # Checagem antecipada (a definitiva usa o manifesto assinado).
    erro = validar_manifesto({u"versao": versao, u"baseMinima": base}, nome,
                             versao_instalada, base_instalada)
    if erro:
        return None, erro
    return {u"versao": versao, u"base": base, u"nome": nome,
            u"url_pacote": payload[u"urlPacote"], u"url_assinatura": payload[u"urlAssinatura"]}, None


def pacote_ligado():
    return bool(_CHAVE_PACOTE_MODULO and _CHAVE_PACOTE_EXPOENTE)


# ---------------------------------------------------------------------------
# .NET (só dentro do Revit)
# ---------------------------------------------------------------------------

def _assinatura_confere(caminho_zip, assinatura_b64):
    import clr
    clr.AddReference(u"mscorlib")
    from System import Convert
    from System.IO import File
    from System.Security.Cryptography import RSACryptoServiceProvider

    rsa = RSACryptoServiceProvider()
    try:
        rsa.FromXmlString(
            u"<RSAKeyValue><Modulus>{}</Modulus><Exponent>{}</Exponent></RSAKeyValue>".format(
                _CHAVE_PACOTE_MODULO, _CHAVE_PACOTE_EXPOENTE))
        return bool(rsa.VerifyData(
            File.ReadAllBytes(caminho_zip), u"SHA256",
            Convert.FromBase64String(assinatura_b64.strip())))
    except Exception:
        return False
    finally:
        rsa.Clear()


def _extrair(caminho_zip, preparo):
    """Extrai com as regras de entrada_permitida. Devolve o manifesto e a lista
    de caminhos (relativos à raiz da extensão, com '/')."""
    import clr
    clr.AddReference(u"System.IO.Compression")
    clr.AddReference(u"System.IO.Compression.FileSystem")
    from System.IO.Compression import ZipFile, ZipFileExtensions

    manifesto = None
    arquivos = []
    total = 0
    zip_ = ZipFile.OpenRead(caminho_zip)
    try:
        for entrada in zip_.Entries:
            caminho = entrada.FullName
            if caminho.endswith(u"/") and int(entrada.Length) == 0:
                continue  # pasta vazia
            if not entrada_permitida(caminho):
                raise _Falha(u"O pacote tem um arquivo não permitido ({}); nada foi aplicado.".format(caminho))
            total += int(entrada.Length)
            if total > _LIMITE_DESCOMPACTADO:
                raise _Falha(u"O pacote é maior do que o esperado; nada foi aplicado.")
            destino = os.path.join(preparo, *caminho.split(u"/"))
            pasta = os.path.dirname(destino)
            if not os.path.isdir(pasta):
                os.makedirs(pasta)
            ZipFileExtensions.ExtractToFile(entrada, destino, True)
            if caminho == u"pacote.json":
                with io.open(destino, u"r", encoding=u"utf-8-sig") as arquivo:
                    manifesto = json.loads(arquivo.read())
            else:
                arquivos.append(caminho)
    finally:
        zip_.Dispose()
    if manifesto is None:
        raise _Falha(u"O pacote não tem o manifesto (pacote.json).")
    if not arquivos:
        raise _Falha(u"O pacote está vazio.")
    return manifesto, arquivos


def _copiar_com_tentativas(origem, destino):
    ultimo = None
    for _ in range(5):
        try:
            shutil.copyfile(origem, destino)
            return
        except (IOError, OSError) as ex:
            ultimo = ex
            time.sleep(0.3)
    raise _Falha(u"Não foi possível atualizar {} ({}).".format(os.path.basename(destino), texto_erro(ultimo)))


def _aplicar(preparo, arquivos, raiz, versao):
    """Copia por cima, apaga o que saiu e grava VERSION por último."""
    novos = set(c.lower() for c in arquivos)

    for rel in arquivos:
        destino = os.path.join(raiz, *rel.split(u"/"))
        pasta = os.path.dirname(destino)
        if not os.path.isdir(pasta):
            os.makedirs(pasta)
        _copiar_com_tentativas(os.path.join(preparo, *rel.split(u"/")), destino)

    # Órfãos: código que existia e não faz parte desta versão.
    base_codigo = os.path.join(raiz, u"Fire Utils.tab")
    for pasta, _subpastas, nomes in os.walk(base_codigo):
        for nome in nomes:
            completo = os.path.join(pasta, nome)
            rel = os.path.relpath(completo, raiz).replace(u"\\", u"/")
            if codigo_gerenciado(rel) and rel.lower() not in novos:
                try:
                    os.remove(completo)
                except (IOError, OSError):
                    pass  # em uso: fica; some na próxima aplicação

    with io.open(os.path.join(raiz, u"VERSION"), u"w", encoding=u"utf-8") as arquivo:
        arquivo.write(versao)


def _recarregar_pyrevit():
    """Recarrega o pyRevit para o que dá para pegar sem reiniciar (a faixa e os
    scripts dos botões). Melhor esforço: o Python que a dockpane já carregou só
    muda quando o Revit reinicia, e é isso que a dockpane avisa."""
    if not _RECARREGAR_PYREVIT:
        return
    try:
        from pyrevit.loader import sessionmgr
        sessionmgr.load_session()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fluxo
# ---------------------------------------------------------------------------

def tratar_instalar_pacote(uiapp, payload, fila_acoes, postar_mensagem):
    global _em_andamento

    def responder(mensagem):
        fila_acoes.enfileirar(lambda _uiapp: postar_mensagem(u"ATUALIZACAO_RESULTADO", mensagem))

    if not pacote_ligado():
        postar_mensagem(u"ATUALIZACAO_RESULTADO", {
            u"ok": False,
            u"erro": u"Esta versão do plugin não tem a atualização por pacote configurada."})
        return

    versao_instalada = plugin_versao.versao_instalada()
    dados, erro = validar_pedido(payload, versao_instalada, plugin_versao.base_instalada())
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
        sucesso = False
        try:
            resposta = _executar(dados, fila_acoes, postar_mensagem)
            sucesso = True
            responder(resposta)
        except _Falha as ex:
            responder({u"ok": False, u"erro": u"{}".format(ex)})
        except plugin_atualizacao._Falha as ex:
            responder({u"ok": False, u"erro": u"{}".format(ex)})
        except Exception as ex:
            responder({u"ok": False,
                       u"erro": u"Falha inesperada na atualização: {}".format(texto_erro(ex))})
        finally:
            _em_andamento = False
        if sucesso:
            # Depois da resposta, na thread de API: o recarregamento do pyRevit
            # não pode competir com a mensagem que avisa o usuário.
            fila_acoes.enfileirar(lambda _uiapp: _recarregar_pyrevit())

    threading.Thread(target=trabalho).start()


def _executar(dados, fila_acoes, postar_mensagem):
    def progresso(etapa, percentual=None):
        mensagem = {u"etapa": etapa, u"percentual": percentual}
        fila_acoes.enfileirar(lambda _uiapp: postar_mensagem(u"ATUALIZACAO_PROGRESSO", mensagem))

    pasta = plugin_atualizacao._pasta_atualizacao()
    caminho_zip = os.path.join(pasta, dados[u"nome"])
    preparo = os.path.join(pasta, u"preparo")
    for caminho in (caminho_zip, caminho_zip + u".parcial"):
        if os.path.isfile(caminho):
            os.remove(caminho)
    if os.path.isdir(preparo):
        shutil.rmtree(preparo, True)

    try:
        progresso(u"baixando", 0)
        assinatura = plugin_atualizacao._baixar_texto(dados[u"url_assinatura"])

        ultimo = [-1]

        def ao_progresso(lidos, total):
            if total <= 0:
                return
            pct = int(lidos * 100 // total)
            if pct >= ultimo[0] + 10 or pct == 100:
                ultimo[0] = pct
                progresso(u"baixando", pct)

        plugin_atualizacao._baixar_arquivo(dados[u"url_pacote"], caminho_zip + u".parcial", ao_progresso)
        if os.path.getsize(caminho_zip + u".parcial") > _LIMITE_ZIP:
            raise _Falha(u"O pacote é maior do que o esperado; descartado.")
        os.rename(caminho_zip + u".parcial", caminho_zip)

        progresso(u"verificando")
        if not _assinatura_confere(caminho_zip, assinatura):
            raise _Falha(u"A assinatura do pacote não confere; ele foi descartado e nada foi aplicado.")

        os.makedirs(preparo)
        manifesto, arquivos = _extrair(caminho_zip, preparo)
        erro = validar_manifesto(manifesto, dados[u"nome"], plugin_versao.versao_instalada(),
                                 plugin_versao.base_instalada())
        if erro:
            raise _Falha(erro)

        progresso(u"aplicando")
        _aplicar(preparo, arquivos, plugin_versao.raiz_da_extensao(), dados[u"versao"])
    finally:
        # Pacote e preparo não ficam no disco: uma só versão, a instalada.
        if os.path.isfile(caminho_zip):
            os.remove(caminho_zip)
        for resto in (caminho_zip + u".parcial",):
            if os.path.isfile(resto):
                os.remove(resto)
        if os.path.isdir(preparo):
            shutil.rmtree(preparo, True)

    return {u"ok": True, u"estado": u"aplicada", u"versao": dados[u"versao"]}
