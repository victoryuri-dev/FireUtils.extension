# -*- coding: utf-8 -*-
"""
comprimento_linha_config.py — Fire Utils · lib/
Configuração compartilhada entre os botões do stack "Comprimento de
Linhas":

  - estilo de linha padrão — usado por "Inserir Linha com Limite" pra
    não precisar escolher o estilo toda vez que o botão é executado;
  - estilo de texto (TextNoteType) padrão — usado por "Medir e Inserir
    Texto" e pelo painel "Limite Atingido" de "Inserir Linha com Limite"
    ao criar o TextNote do comprimento;
  - prefixo de texto — inserido antes do valor do comprimento (hoje
    fixo em "L = ", editável aqui; vazio ("") é um valor válido — só
    "nunca configurado" cai no padrão "L = ", ver carregar()).

Persistida no mesmo firedata.json da pasta do projeto que o resto da
extensão já usa (ver projeto.py) — não no pyRevit nem no repositório.
Por quê não pyRevit (script.get_config): estilo de linha e tipo de texto
são elementos que só existem DENTRO de um documento — salvar por projeto
é o que faz sentido (e combina com o fallback de "Inserir Linha com
Limite"/resolver_tipo_texto, que ignora a configuração salva se ela não
existir mais nesse documento).
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


def listar_tipos_de_texto(doc):
    """{nome: ElementId} de cada TextNoteType do projeto."""
    from Autodesk.Revit.DB import FilteredElementCollector, TextNoteType
    tipos = {}
    for tipo in FilteredElementCollector(doc).OfClass(TextNoteType):
        try:
            nome = tipo.Name
        except Exception:
            continue
        if nome:
            tipos[nome] = tipo.Id
    return tipos


def resolver_tipo_texto(doc, tipo_texto_nome):
    """ElementId do TextNoteType configurado — ou o primeiro disponível
    (ordem alfabética) se nada foi configurado ainda, ou se o tipo salvo
    não existe mais nesse documento. None só se o projeto não tiver
    NENHUM TextNoteType."""
    tipos = listar_tipos_de_texto(doc)
    if not tipos:
        return None
    if tipo_texto_nome and tipo_texto_nome in tipos:
        return tipos[tipo_texto_nome]
    return tipos[sorted(tipos.keys())[0]]


def carregar(doc):
    """-> (nome_estilo_linha ou None, prefixo_texto, nome_tipo_texto ou
    None). prefixo_texto pode vir vazio ("") se foi assim que o usuário
    salvou em "Configurar" — só cai no padrão "L = " quando NUNCA foi
    salvo (chave ausente), não quando foi salvo vazio de propósito."""
    projeto_dir = _projeto_dir(doc)
    if not projeto_dir:
        return None, _PREFIXO_PADRAO, None
    dados = carregar_cache(projeto_dir).get(_CHAVE) or {}
    estilo = dados.get(u"estilo_linha")
    prefixo = dados.get(u"prefixo_texto")
    if prefixo is None:
        prefixo = _PREFIXO_PADRAO
    tipo_texto = dados.get(u"tipo_texto")
    return estilo, prefixo, tipo_texto


def salvar(doc, estilo_nome, prefixo, tipo_texto_nome):
    projeto_dir = _projeto_dir(doc)
    if not projeto_dir:
        return False
    path = cache_path(projeto_dir)
    arquivo = carregar_cache(projeto_dir)
    arquivo[_CHAVE] = {
        u"estilo_linha": estilo_nome,
        u"prefixo_texto": prefixo,  # salva como veio, inclusive vazio ("")
        u"tipo_texto": tipo_texto_nome,
    }
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)
    return True


# ===========================================================================
# Janela — escolhe o estilo padrão + o prefixo, num painel só
# ===========================================================================

from System.Windows.Controls import ComboBoxItem  # noqa: E402  (precisa do clr/WPF já carregado por forms)


def _preencher_combo(combo, nomes, nome_atual):
    """Popula um ComboBox com ComboBoxItem a partir de `nomes` (lista já
    ordenada), selecionando `nome_atual` se bater com algum — senão o
    primeiro. Usado tanto pro estilo de linha quanto pro estilo de
    texto, mesma mecânica pros dois."""
    indice_selecionado = 0
    for i, nome in enumerate(nomes):
        item = ComboBoxItem()
        item.Content = nome
        combo.Items.Add(item)
        if nome == nome_atual:
            indice_selecionado = i
    if combo.Items.Count:
        combo.SelectedIndex = indice_selecionado


class _JanelaConfiguracao(forms.WPFWindow):

    def __init__(self, estilos, estilo_atual, prefixo_atual, tipos_texto, tipo_texto_atual):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.resultado = None  # (nome_estilo, prefixo, nome_tipo_texto) se "Salvar", senão None

        _preencher_combo(self.CmbEstilo, sorted(estilos.keys()), estilo_atual)
        _preencher_combo(self.CmbTipoTexto, sorted(tipos_texto.keys()), tipo_texto_atual)

        self.TxtPrefixo.Text = prefixo_atual

    def on_cancelar(self, sender, args):
        self.Close()

    def on_salvar(self, sender, args):
        item_estilo = self.CmbEstilo.SelectedItem
        if item_estilo is None:
            self.TxtErro.Text = u"Escolha um estilo de linha."
            return
        item_tipo_texto = self.CmbTipoTexto.SelectedItem
        if item_tipo_texto is None:
            self.TxtErro.Text = u"Escolha um estilo de texto."
            return
        self.resultado = (
            u"{}".format(item_estilo.Content),
            u"{}".format(self.TxtPrefixo.Text),  # pode vir vazio — é um valor válido
            u"{}".format(item_tipo_texto.Content),
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

    tipos_texto = listar_tipos_de_texto(doc)
    if not tipos_texto:
        forms.alert(u"Nenhum estilo de texto (TextNoteType) encontrado no projeto.", exitscript=True)
        return

    estilo_atual, prefixo_atual, tipo_texto_atual = carregar(doc)
    janela = _JanelaConfiguracao(estilos, estilo_atual, prefixo_atual, tipos_texto, tipo_texto_atual)
    janela.ShowDialog()

    if janela.resultado is not None:
        salvar(doc, *janela.resultado)
        forms.alert(u"Configuração salva.", title=u"Fire Utils — Comprimento de Linhas")
