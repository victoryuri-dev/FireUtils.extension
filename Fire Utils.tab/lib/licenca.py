# -*- coding: utf-8 -*-
"""
licenca.py — quais módulos esta conta pode usar, SEM internet.

A licença é um token assinado pelo servidor (Edge Function emitir-licenca,
repositório ETOS.FireUtils): "esta conta, estes módulos, até estas datas,
válido até tal dia". A dockpane o busca com a sessão do usuário e entrega ao
Python pela bridge (SET_LICENCA_TOKEN); aqui ele é conferido com a chave
pública embutida e guardado em %LOCALAPPDATA%\\FireUtils\\licenca.token.

Por que assim: até aqui o resultado da licença ficava num JSON comum, e
editar o arquivo liberava tudo. A chave que assina só existe no servidor —
este módulo só consegue CONFERIR uma assinatura, nunca produzir uma. Editar o
arquivo (ou trocar o módulo no payload) invalida a assinatura. Quem edita o
código para pular a conferência ainda consegue, por isso o que realmente vale
(o dimensionamento) exige licença no servidor a cada chamada — este token só
decide as ferramentas de produtividade, que funcionam offline.

Como não há rede aqui, cada ferramenta confere o token na hora (RSA, na casa
de milissegundos). Também não há mais refresh token guardado no disco: a
renovação do token é a dockpane, com a sessão dela, quem faz — sem girar o
refresh token que ela mesma usa.

Módulos vêm de `public.licencas`, os mesmos da página de preços: 'hidrantes',
'saidas', 'memorial' e 'pro' (que inclui os três).

Formato do token: base64url(payload JSON) "." base64url(assinatura), com
assinatura RSASSA-PKCS1-v1_5/SHA-256 sobre os bytes ASCII da primeira parte.
Payload: {v, sub, email, iat, exp, mod: {módulo: "AAAA-MM-DD" | null}}.
"""

import base64
import datetime
import io
import json
import os
import time

from family_error_utils import texto_erro
import plugin_versao

# Chave PÚBLICA que confere a assinatura do token (RSA 2048, em base64
# padrão: módulo e expoente). Gerada por scripts/gerar-chave-licenca.mjs no
# repositório ETOS.FireUtils — a parte privada fica só nos secrets do
# Supabase. Sem estes valores nenhum token confere e as ferramentas ficam
# bloqueadas; installer/build.ps1 recusa gerar o instalador assim.
_CHAVE_PUBLICA_MODULO = u""
_CHAVE_PUBLICA_EXPOENTE = u""

_VERSAO_TOKEN = 1

# Mesmos módulos do constraint em public.licencas e da página de preços.
MODULO_PRO = u"pro"
MODULOS = (u"hidrantes", u"saidas", u"memorial", MODULO_PRO)

# Situações do token guardado.
SIT_AUSENTE = u"ausente"      # nenhum token neste computador
SIT_INVALIDO = u"invalido"    # assinatura não confere, formato ruim ou relógio errado
SIT_EXPIRADO = u"expirado"    # assinatura ok, mas passou da validade offline
SIT_VALIDO = u"valido"

# Tolerância a um relógio do computador levemente atrasado em relação ao
# servidor, na hora de conferir quando o token foi emitido.
_TOLERANCIA_RELOGIO_S = 24 * 3600


def _dir_dados():
    """%LOCALAPPDATA%\\FireUtils — criado sob demanda."""
    from System import Environment as DotNetEnvironment
    caminho = os.path.join(
        DotNetEnvironment.GetFolderPath(DotNetEnvironment.SpecialFolder.LocalApplicationData),
        u"FireUtils",
    )
    if not os.path.isdir(caminho):
        os.makedirs(caminho)
    return caminho


def _arquivo_token():
    return os.path.join(_dir_dados(), u"licenca.token")


def _arquivo_log():
    return os.path.join(_dir_dados(), u"licenca.log")


def log(mensagem):
    """
    Registra em %LOCALAPPDATA%\\FireUtils\\licenca.log. Sem print: no startup,
    qualquer saída abre a janela do pyRevit a cada abertura do Revit, mesmo
    quando está tudo certo. O arquivo guarda o que for preciso investigar.
    """
    linha = u"{} {}".format(datetime.datetime.now().strftime(u"%H:%M:%S"), mensagem)
    try:
        with io.open(_arquivo_log(), u"a", encoding=u"utf-8") as arquivo:
            arquivo.write(linha + u"\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Conferência da assinatura
# ---------------------------------------------------------------------------

def _base64url_decodificar(texto):
    texto = str(texto)
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _conferir_assinatura_dotnet(corpo_ascii, assinatura):
    """
    RSA PKCS#1 v1.5 + SHA-256 pelo .NET (o mesmo do Revit; não precisa de
    pacote nenhum). `corpo_ascii` é a primeira parte do token, como texto;
    `assinatura`, os bytes já decodificados.
    """
    import clr
    clr.AddReference(u"mscorlib")
    from System import Array, Byte
    from System.Security.Cryptography import RSACryptoServiceProvider
    from System.Text import Encoding

    rsa = RSACryptoServiceProvider()
    try:
        rsa.FromXmlString(
            u"<RSAKeyValue><Modulus>{}</Modulus><Exponent>{}</Exponent></RSAKeyValue>".format(
                _CHAVE_PUBLICA_MODULO, _CHAVE_PUBLICA_EXPOENTE
            )
        )
        return bool(rsa.VerifyData(
            Encoding.ASCII.GetBytes(corpo_ascii),
            u"SHA256",
            Array[Byte](list(bytearray(assinatura))),
        ))
    finally:
        rsa.Clear()


# Indireção só para os testes poderem trocar a conferência por uma em Python
# puro (o .NET não existe fora do Revit).
_conferir_assinatura = _conferir_assinatura_dotnet


def _hoje():
    """
    Data de hoje no fuso de Brasília, 'AAAA-MM-DD' — o mesmo critério de
    tem_licenca() no Supabase. Sem isso, uma licença venceria três horas
    antes da meia-noite local para quem está no Brasil.
    """
    return (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).date().isoformat()


def _analisar(token, agora_s=None):
    """
    Confere um token. Devolve (situação, payload, motivo): `payload` só vem
    preenchido quando a assinatura confere (mesmo expirado, para a dockpane
    saber de quem é e quando venceu); `motivo` explica uma situação ruim.
    """
    if not token:
        return SIT_AUSENTE, None, u"nenhuma licença guardada neste computador"

    if not _CHAVE_PUBLICA_MODULO or not _CHAVE_PUBLICA_EXPOENTE:
        return SIT_INVALIDO, None, u"esta versão do plugin não tem a chave de licença configurada"

    try:
        corpo, assinatura_b64 = token.strip().split(u".")
        assinatura = _base64url_decodificar(assinatura_b64)
        if not _conferir_assinatura(corpo, assinatura):
            return SIT_INVALIDO, None, u"a assinatura da licença não confere"
        payload = json.loads(_base64url_decodificar(corpo).decode(u"utf-8"))
    except Exception as ex:
        return SIT_INVALIDO, None, u"licença ilegível: {}".format(texto_erro(ex))

    if not isinstance(payload, dict) or payload.get(u"v") != _VERSAO_TOKEN \
            or not isinstance(payload.get(u"mod"), dict):
        return SIT_INVALIDO, None, u"formato de licença desconhecido"

    agora = time.time() if agora_s is None else agora_s
    try:
        iat = float(payload[u"iat"])
        exp = float(payload[u"exp"])
    except Exception:
        return SIT_INVALIDO, None, u"licença sem datas válidas"

    if agora < iat - _TOLERANCIA_RELOGIO_S:
        return SIT_INVALIDO, None, u"o relógio deste computador está atrasado em relação à licença"
    if agora >= exp:
        return SIT_EXPIRADO, payload, u"a licença guardada neste computador venceu"

    return SIT_VALIDO, payload, None


def _ler_token():
    caminho = _arquivo_token()
    if not os.path.isfile(caminho):
        return None
    try:
        with io.open(caminho, u"r", encoding=u"utf-8") as arquivo:
            return arquivo.read().strip()
    except Exception as ex:
        log(u"não foi possível ler o token: {}".format(texto_erro(ex)))
        return None


def situacao():
    """(situação, payload, motivo) do token guardado — ver _analisar."""
    return _analisar(_ler_token())


# ---------------------------------------------------------------------------
# Guardar / esquecer
# ---------------------------------------------------------------------------

def salvar_token(token):
    """
    Confere e guarda o token que a dockpane recebeu do servidor. Só o que a
    assinatura confirma é gravado — token adulterado nunca chega ao disco.
    Devolve (ok, motivo).
    """
    sit, payload, motivo = _analisar(token)
    if sit != SIT_VALIDO:
        log(u"token recusado ({}): {}".format(sit, motivo))
        return False, motivo

    try:
        with io.open(_arquivo_token(), u"w", encoding=u"utf-8") as arquivo:
            arquivo.write(token.strip())
    except Exception as ex:
        log(u"falha ao guardar o token: {}".format(texto_erro(ex)))
        return False, u"não foi possível guardar a licença neste computador"

    log(u"licença guardada para {}: {}".format(
        payload.get(u"email") or payload.get(u"sub"),
        u", ".join(sorted(payload[u"mod"])) if payload[u"mod"] else u"nenhum módulo",
    ))
    return True, None


def esquecer_sessao():
    """
    Logout: apaga a licença guardada — e os arquivos que versões anteriores
    deste plugin deixaram (sessão com refresh token e o JSON de licenças).
    """
    for nome in (u"licenca.token", u"sessao.dat", u"licencas.json"):
        try:
            caminho = os.path.join(_dir_dados(), nome)
            if os.path.isfile(caminho):
                os.remove(caminho)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Decisão de acesso
# ---------------------------------------------------------------------------

def modulos_liberados():
    """
    Módulos que o token guardado libera hoje: nele e dentro da data de
    validade de cada um. Vazio se não há token válido.
    """
    sit, payload, _motivo = situacao()
    if sit != SIT_VALIDO:
        return set()

    hoje = _hoje()
    return set(
        modulo for modulo, ate in payload[u"mod"].items()
        if ate is None or ate >= hoje
    )


def tem_acesso(modulo):
    """A conta pode usar este módulo? A licença PRO libera todos."""
    liberados = modulos_liberados()
    return modulo in liberados or MODULO_PRO in liberados


def esta_autenticado():
    """Há uma licença com assinatura válida neste computador (mesmo vencida)?"""
    sit, _payload, _motivo = situacao()
    return sit in (SIT_VALIDO, SIT_EXPIRADO)


def resumo_para_dockpane():
    """
    O que a dockpane precisa saber: os módulos e, para decidir se vale pedir
    um token novo ao servidor, se este computador já tem um válido e até
    quando. `suportaToken` avisa que este plugin entende SET_LICENCA_TOKEN —
    um plugin antigo não manda o campo, e a dockpane não envia o token.
    """
    sit, payload, motivo = situacao()
    return {
        u"modulos": sorted(modulos_liberados()),
        u"erro": None if sit in (SIT_VALIDO, SIT_AUSENTE, SIT_EXPIRADO) else motivo,
        u"suportaToken": True,
        u"tokenValido": sit == SIT_VALIDO,
        u"tokenExpiraEm": int(payload[u"exp"]) if payload else None,
        # Versão do plugin instalado (ver plugin_versao.py): vai junto porque
        # um plugin antigo simplesmente não manda o campo, e a dockpane o
        # trata como "anterior a qualquer versão publicada".
        u"versaoPlugin": plugin_versao.versao_instalada(),
    }
