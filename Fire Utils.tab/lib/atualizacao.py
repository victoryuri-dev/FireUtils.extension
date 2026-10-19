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

Publicação (manual, pelo painel do Supabase):
    plugin-assets/atualizacao/versao.json
    plugin-assets/atualizacao/fireutils-<versao>.zip
"""

import io
import os
import json

from family_error_utils import texto_erro

import licenca  # reaproveita _requisitar, _log e a URL do Supabase

_URL_VERSAO = u"{}/storage/v1/object/public/plugin-assets/atualizacao/versao.json".format(
    licenca._SUPABASE_URL
)

# Fire Utils.tab/lib/ -> Fire Utils.tab/ -> raiz da extensão
_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARQUIVO_VERSAO_LOCAL = os.path.join(_EXT_ROOT, u"versao.json")


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
    resposta[u"temAtualizacao"] = e_mais_nova(disponivel, instalada)

    licenca.log(u"atualização: instalada={} publicada={} nova={}".format(
        instalada, disponivel, resposta[u"temAtualizacao"]
    ))

    return resposta
