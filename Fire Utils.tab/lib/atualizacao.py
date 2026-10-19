# -*- coding: utf-8 -*-
"""
atualizacao.py — descobre se há versão nova do plugin publicada.

A dockpane pergunta ao abrir; havendo versão nova, mostra uma faixa com
"Atualizar" e o download só acontece quando o usuário confirma.

O que é atualizável: os scripts Python e os arquivos de configuração dos
painéis. As DLLs do WebView2 ficam de fora porque estão carregadas no
processo do Revit e o Windows não deixa sobrescrevê-las — essas continuam
vindo pelo instalador, e mudam só quando o SDK muda.

Não exige licença: correção de bug chega para todo mundo. A licença
controla o uso das ferramentas, não o direito de receber a versão corrigida.

Publicação: `installer\\publicar.ps1` monta os dois arquivos e você os sobe
pelo painel do Supabase (Storage > plugin-assets > atualizacao):

    versao.json              — {"versao", "sha256", "notas"}
    fireutils-<versao>.zip   — o mesmo payload do instalador

O sha256 do versao.json é o que autentica o pacote: o cliente baixa o zip
de um bucket público e só instala se o checksum bater.
"""

import io
import os
import json
import shutil
import uuid

from family_error_utils import texto_erro

import licenca  # reaproveita _requisitar, _log e a URL do Supabase

_BASE_ATUALIZACAO = u"{}/storage/v1/object/public/plugin-assets/atualizacao".format(
    licenca._SUPABASE_URL
)
_URL_VERSAO = u"{}/versao.json".format(_BASE_ATUALIZACAO)
_URL_PACOTE = u"{}/fireutils-{{}}.zip".format(_BASE_ATUALIZACAO)

# Fire Utils.tab/lib/ -> Fire Utils.tab/ -> raiz da extensão
_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARQUIVO_VERSAO_LOCAL = os.path.join(_EXT_ROOT, u"versao.json")

# Caminhos (relativos à raiz da extensão) que a atualização nunca toca.
#
# As DLLs do WebView2 estão carregadas no processo do Revit: o Windows
# mantém o arquivo aberto e sobrescrever falha com "em uso". Elas mudam só
# quando o SDK muda, então continuam vindo pelo instalador — e ficar de
# fora daqui é o que permite atualizar o resto com o Revit aberto.
_PRESERVADOS = (
    os.path.join(u"Fire Utils.tab", u"lib", u"webview2_runtime"),
)


def versao_instalada():
    """Versão desta cópia do plugin, ou None se o arquivo faltar."""
    if not os.path.isfile(_ARQUIVO_VERSAO_LOCAL):
        return None
    try:
        with io.open(_ARQUIVO_VERSAO_LOCAL, u"r", encoding=u"utf-8") as arquivo:
            return (json.loads(arquivo.read()) or {}).get(u"versao")
    except Exception as ex:
        licenca.log(u"versão local ilegível: {}".format(texto_erro(ex)))
        return None


def _partes(versao):
    """
    "2.10.1" -> (2, 10, 1), para comparar como número e não como texto.

    Comparar string diria que "2.9.0" é maior que "2.10.0", porque "9" > "1"
    — e aí a nona versão seguraria a décima para sempre.
    """
    partes = []
    for pedaco in (versao or u"").split(u"."):
        digitos = u"".join(c for c in pedaco if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def e_mais_nova(candidata, atual):
    """`candidata` é posterior a `atual`?"""
    if not candidata:
        return False
    if not atual:
        # Sem saber o que está instalado, propor a atualização é melhor do
        # que esconder uma correção — no pior caso reinstala o mesmo.
        return True
    return _partes(candidata) > _partes(atual)


def verificar():
    """
    Consulta a versão publicada.

    Devolve um dicionário pronto para a dockpane:
        {
          "instalada": "2.0.0",
          "disponivel": "2.1.0",   (None se não deu para consultar)
          "temAtualizacao": True,
          "notas": "...",
          "erro": None,
        }

    Rede fora do ar nunca vira erro na cara do usuário: sem resposta, a
    faixa simplesmente não aparece e ele segue trabalhando.
    """
    instalada = versao_instalada()
    resposta = {
        u"instalada": instalada,
        u"disponivel": None,
        u"temAtualizacao": False,
        u"notas": None,
        u"sha256": None,
        u"erro": None,
    }

    texto, erro = licenca.requisitar(
        _URL_VERSAO,
        u"GET",
        {u"apikey": licenca._ANON_KEY},
    )
    if erro:
        licenca.log(u"atualização: falha ao consultar ({})".format(erro))
        resposta[u"erro"] = erro
        return resposta

    try:
        dados = json.loads(texto) or {}
    except Exception as ex:
        licenca.log(u"atualização: versao.json inválido ({})".format(texto_erro(ex)))
        resposta[u"erro"] = texto_erro(ex)
        return resposta

    disponivel = dados.get(u"versao")
    resposta[u"disponivel"] = disponivel
    resposta[u"notas"] = dados.get(u"notas")
    resposta[u"sha256"] = dados.get(u"sha256")
    resposta[u"temAtualizacao"] = e_mais_nova(disponivel, instalada)

    licenca.log(u"atualização: instalada={} publicada={} nova={}".format(
        instalada, disponivel, resposta[u"temAtualizacao"]
    ))

    return resposta


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------

def _sha256(caminho):
    import hashlib
    h = hashlib.sha256()
    with open(caminho, u"rb") as arquivo:
        while True:
            bloco = arquivo.read(1 << 20)
            if not bloco:
                break
            h.update(bloco)
    return h.hexdigest()


def _baixar(url, destino):
    """WebClient do .NET, pelo mesmo motivo de family_cache.py: é o jeito
    confiável de baixar HTTPS dentro do IronPython do pyRevit."""
    import clr
    clr.AddReference(u"System")
    from System import Uri
    from System.Net import WebClient

    cliente = WebClient()
    try:
        cliente.DownloadFile(Uri(url), destino)
    finally:
        cliente.Dispose()


def _descompactar(caminho_zip, pasta_destino):
    """
    ZipFile do .NET em vez do zipfile do Python: além de estar sempre
    disponível, ele recusa entrada cujo caminho escape da pasta de destino
    — e um pacote baixado da rede é exatamente onde isso importa.
    """
    import clr
    clr.AddReference(u"System.IO.Compression.FileSystem")
    from System.IO.Compression import ZipFile

    ZipFile.ExtractToDirectory(caminho_zip, pasta_destino)


def _e_preservado(relativo):
    for preservado in _PRESERVADOS:
        if relativo == preservado or relativo.startswith(preservado + os.sep):
            return True
    return False


def _arquivos_relativos(raiz):
    """Todo arquivo sob `raiz`, como caminho relativo a ela."""
    encontrados = set()
    for pasta, _subpastas, arquivos in os.walk(raiz):
        relativo_pasta = os.path.relpath(pasta, raiz)
        for nome in arquivos:
            if relativo_pasta == u".":
                encontrados.add(nome)
            else:
                encontrados.add(os.path.join(relativo_pasta, nome))
    return encontrados


def _ignorar_preservados(raiz):
    """Callback de `shutil.copytree` que pula as pastas preservadas."""
    def ignorar(pasta, nomes):
        relativo_pasta = os.path.relpath(pasta, raiz)
        pulados = []
        for nome in nomes:
            relativo = nome if relativo_pasta == u"." else os.path.join(relativo_pasta, nome)
            if _e_preservado(relativo):
                pulados.append(nome)
        return pulados
    return ignorar


def _pasta_backup():
    return os.path.join(licenca.dir_dados(), u"backup")


def _fazer_backup():
    """
    Cópia do estado atual, para poder desfazer se a troca der errado no meio.

    Guarda só a última: o objetivo é reverter esta atualização, não manter
    histórico — e a extensão inteira é copiada a cada vez.
    """
    backup = _pasta_backup()
    if os.path.isdir(backup):
        shutil.rmtree(backup)
    shutil.copytree(_EXT_ROOT, backup, ignore=_ignorar_preservados(_EXT_ROOT))
    return backup


def _escrever_sobre(origem, destino):
    """
    Copia tudo de `origem` por cima de `destino`, criando o que falta.

    Os caminhos preservados ficam de fora mesmo se vierem no pacote: uma DLL
    carregada no processo do Revit não pode ser sobrescrita, e tentar
    derrubaria a atualização inteira por causa de um arquivo que não mudou.
    """
    for pasta, _subpastas, arquivos in os.walk(origem):
        relativo_pasta = os.path.relpath(pasta, origem)
        if relativo_pasta != u"." and _e_preservado(relativo_pasta):
            continue
        pasta_destino = destino if relativo_pasta == u"." else os.path.join(destino, relativo_pasta)
        if not os.path.isdir(pasta_destino):
            os.makedirs(pasta_destino)
        for nome in arquivos:
            relativo = nome if relativo_pasta == u"." else os.path.join(relativo_pasta, nome)
            if _e_preservado(relativo):
                continue
            shutil.copy2(os.path.join(pasta, nome), os.path.join(pasta_destino, nome))


def _remover_orfaos(origem, destino):
    """
    Apaga do destino o que a versão nova não tem mais.

    Sem isso, um módulo renomeado deixa a versão antiga no disco para
    sempre — e `import` acha o arquivo velho tão bem quanto o novo.
    """
    novos = _arquivos_relativos(origem)
    for relativo in _arquivos_relativos(destino):
        if relativo in novos or _e_preservado(relativo):
            continue
        try:
            os.remove(os.path.join(destino, relativo))
        except Exception as ex:
            licenca.log(u"atualização: sobrou {} ({})".format(relativo, texto_erro(ex)))

    # Pastas que ficaram vazias depois da limpeza. De baixo para cima, para
    # que uma pasta cujo único conteúdo era outra pasta vazia também saia.
    for pasta, _subpastas, _arquivos in sorted(os.walk(destino), reverse=True):
        if pasta == destino or _e_preservado(os.path.relpath(pasta, destino)):
            continue
        try:
            os.rmdir(pasta)
        except Exception:
            pass  # não estava vazia — é o caso normal


def _restaurar(backup):
    licenca.log(u"atualização: revertendo a partir do backup")
    _escrever_sobre(backup, _EXT_ROOT)
    _remover_orfaos(backup, _EXT_ROOT)


def aplicar():
    """
    Baixa e instala a versão publicada. Devolve `(ok, erro)`.

    Consulta a versão por conta própria em vez de receber qual instalar:
    assim o número e o checksum vêm os dois do mesmo versao.json, e nada
    que chegue da dockpane escolhe o que baixar.

    Exige confirmação do usuário antes de chegar aqui (ver o handler da
    bridge) — e o Revit precisa ser reiniciado depois, porque os módulos
    desta sessão já estão carregados na memória.
    """
    situacao = verificar()
    if situacao[u"erro"]:
        return False, situacao[u"erro"]
    if not situacao[u"temAtualizacao"]:
        return False, u"não há versão nova para instalar"

    versao = situacao[u"disponivel"]
    pasta_trabalho = os.path.join(
        licenca.dir_dados(), u"download-{}".format(uuid.uuid4().hex)
    )
    os.makedirs(pasta_trabalho)
    caminho_zip = os.path.join(pasta_trabalho, u"pacote.zip")
    pasta_extraida = os.path.join(pasta_trabalho, u"conteudo")

    backup = None
    try:
        licenca.log(u"atualização: baixando {}".format(versao))
        _baixar(_URL_PACOTE.format(versao), caminho_zip)

        esperado = situacao.get(u"sha256")
        if esperado:
            obtido = _sha256(caminho_zip)
            if obtido != esperado:
                licenca.log(u"atualização: checksum não confere ({})".format(obtido))
                return False, u"o pacote baixado não confere com o publicado"
        else:
            # Publicar sem checksum é um erro de publicação, não do cliente:
            # sem ele não há como saber se o arquivo chegou íntegro.
            licenca.log(u"atualização: versao.json não trouxe sha256")
            return False, u"pacote publicado sem checksum"

        _descompactar(caminho_zip, pasta_extraida)

        # Antes de tocar em qualquer coisa: o pacote é o que esperamos? Um
        # zip com outro formato por dentro apagaria a instalação inteira na
        # hora de remover os órfãos.
        if not os.path.isfile(os.path.join(pasta_extraida, u"versao.json")) or \
                not os.path.isdir(os.path.join(pasta_extraida, u"Fire Utils.tab", u"lib")):
            return False, u"o pacote baixado não tem a estrutura esperada"

        backup = _fazer_backup()
        _escrever_sobre(pasta_extraida, _EXT_ROOT)
        _remover_orfaos(pasta_extraida, _EXT_ROOT)

        licenca.log(u"atualização: {} instalada".format(versao))
        return True, None
    except Exception as ex:
        erro = texto_erro(ex)
        licenca.log(u"atualização: falhou ({})".format(erro))
        if backup is not None:
            try:
                _restaurar(backup)
            except Exception as ex_reverter:
                # Reverter falhou depois de a troca ter começado: a
                # instalação pode estar pela metade, e só o instalador
                # resolve. Dizer isso é melhor do que o usuário descobrir
                # sozinho na próxima abertura do Revit.
                licenca.log(u"atualização: reversão falhou ({})".format(
                    texto_erro(ex_reverter)))
                return False, (
                    u"a atualização falhou no meio da troca de arquivos e não "
                    u"foi possível desfazer. Reinstale o Fire Utils pelo "
                    u"instalador."
                )
        return False, erro
    finally:
        try:
            shutil.rmtree(pasta_trabalho)
        except Exception:
            pass
