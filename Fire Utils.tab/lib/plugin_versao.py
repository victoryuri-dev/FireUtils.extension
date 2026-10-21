# -*- coding: utf-8 -*-
"""
plugin_versao.py — versão do plugin instalado.

O instalador (installer/build.ps1) grava a versão num arquivo VERSION na raiz
da extensão. A dockpane a compara com a última versão publicada para avisar
de atualização — e para saber se este plugin ainda atende à interface, que é
publicada na hora, sem passar por instalador.

Rodando direto do repositório (clone para desenvolvimento) não há VERSION, e
a resposta é "dev": a dockpane não avisa de nada nesse caso.
"""

import io
import os

VERSAO_DEV = u"dev"

# Fire Utils.tab/lib/ -> Fire Utils.tab/ -> raiz da extensão.
_RAIZ_DA_EXTENSAO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def raiz_da_extensao():
    return _RAIZ_DA_EXTENSAO


def _ler(nome, raiz=None):
    caminho = os.path.join(raiz or _RAIZ_DA_EXTENSAO, nome)
    try:
        # utf-8-sig: o Windows PowerShell costuma gravar com BOM.
        with io.open(caminho, u"r", encoding=u"utf-8-sig") as arquivo:
            return arquivo.read().strip()
    except Exception:
        return u""


def base_instalada(raiz=None):
    """Versão do INSTALADOR que pôs esta extensão aqui (arquivo BASE, gravado só
    pelo instalador). Pacotes mudam VERSION mas não BASE; é ela que diz se um
    pacote serve. Instalação anterior ao BASE: o instalador era a própria VERSION."""
    return _ler(u"BASE", raiz) or versao_instalada(raiz)


def versao_instalada(raiz=None):
    """Conteúdo de VERSION na raiz da extensão, ou "dev" se não houver."""
    caminho = os.path.join(raiz or _RAIZ_DA_EXTENSAO, u"VERSION")
    try:
        # utf-8-sig: o Windows PowerShell costuma gravar com BOM.
        with io.open(caminho, u"r", encoding=u"utf-8-sig") as arquivo:
            versao = arquivo.read().strip()
    except Exception:
        return VERSAO_DEV
    return versao or VERSAO_DEV
