# -*- coding: utf-8 -*-
"""
comprimento_linha_config.py — Fire Utils · lib/
Configuração compartilhada entre os botões do stack "Comprimento de
Linhas":

  - estilo de linha padrão — usado por "Inserir Linha com Limite" pra
    não precisar escolher o estilo toda vez que o botão é executado;
  - prefixo de texto — usado por "Medir e Inserir Texto" antes do valor
    do comprimento (hoje fixo em "L = ", editável aqui).

Persistida no mesmo firedata.json da pasta do projeto que o resto da
extensão já usa (ver projeto.py) — não no pyRevit nem no repositório.
Por quê não pyRevit (script.get_config): o estilo de linha é um
GraphicsStyle que só existe DENTRO de um documento — salvar por projeto
é o que faz sentido (e combina com o fallback de "Inserir Linha com
Limite", que ignora o estilo salvo se ele não existir mais nesse
documento).
"""

import io
import json
import os

from pyrevit import forms

from projeto import carregar_cache, cache_path

_CHAVE = u"comprimento_linha"
_PREFIXO_PADRAO = u"L = "

_XAML_PATH = os.path.join(os.path.dirname(__file__), u"comprimento_linha_opcoes.xaml")


def _projeto_dir(doc):
    if not doc.PathName:
        return None
    return os.path.dirname(doc.PathName)


def carregar(doc):
    """-> (nome_estilo ou None, prefixo_texto) — prefixo nunca vem vazio
    (cai no padrão "L = " se nada foi salvo ainda, ou se o projeto ainda
    não foi salvo em disco)."""
    projeto_dir = _projeto_dir(doc)
    if not projeto_dir:
        return None, _PREFIXO_PADRAO
    dados = carregar_cache(projeto_dir).get(_CHAVE) or {}
    estilo = dados.get(u"estilo_linha")
    prefixo = dados.get(u"prefixo_texto") or _PREFIXO_PADRAO
    return estilo, prefixo


def salvar(doc, estilo_nome, prefixo):
    projeto_dir = _projeto_dir(doc)
    if not projeto_dir:
        return False
    path = cache_path(projeto_dir)
    arquivo = carregar_cache(projeto_dir)
    arquivo[_CHAVE] = {
        u"estilo_linha": estilo_nome,
        u"prefixo_texto": prefixo if prefixo else _PREFIXO_PADRAO,
    }
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)
    return True


# ===========================================================================
# Janela — escolhe o estilo padrão + o prefixo, num painel só
# ===========================================================================

from System.Windows.Controls import ComboBoxItem  # noqa: E402  (precisa do clr/WPF já carregado por forms)


class _JanelaConfiguracao(forms.WPFWindow):

    def __init__(self, estilos, estilo_atual, prefixo_atual):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.resultado = None  # (nome_estilo, prefixo) se "Salvar", senão None

        nomes = sorted(estilos.keys())
        indice_selecionado = 0
        for i, nome in enumerate(nomes):
            item = ComboBoxItem()
            item.Content = nome
            self.CmbEstilo.Items.Add(item)
            if nome == estilo_atual:
                indice_selecionado = i
        if self.CmbEstilo.Items.Count:
            self.CmbEstilo.SelectedIndex = indice_selecionado

        self.TxtPrefixo.Text = prefixo_atual

    def on_cancelar(self, sender, args):
        self.Close()

    def on_salvar(self, sender, args):
        item_selecionado = self.CmbEstilo.SelectedItem
        if item_selecionado is None:
            self.TxtErro.Text = u"Escolha um estilo de linha."
            return
        self.resultado = (
            u"{}".format(item_selecionado.Content),
            u"{}".format(self.TxtPrefixo.Text),
        )
        self.Close()


def abrir_configuracao(doc):
    if not doc.PathName:
        forms.alert(
            u"O projeto Revit não está salvo.\n\n"
            u"Salve o arquivo (.rvt) antes de configurar — a configuração "
            u"é gravada na pasta do projeto.",
            title=u"Fire Utils — Salve o projeto",
            warn_icon=True,
        )
        return

    from linha_limite_core import listar_estilos_de_linha  # reaproveita a mesma listagem

    estilos = listar_estilos_de_linha(doc)
    if not estilos:
        forms.alert(u"Nenhum estilo de linha encontrado no projeto.", exitscript=True)
        return

    estilo_atual, prefixo_atual = carregar(doc)
    janela = _JanelaConfiguracao(estilos, estilo_atual, prefixo_atual)
    janela.ShowDialog()

    if janela.resultado is not None:
        salvar(doc, *janela.resultado)
        forms.alert(u"Configuração salva.", title=u"Fire Utils — Comprimento de Linhas")
