# -*- coding: utf-8 -*-
"""
script.py — Dados do Projeto
Code-behind da tela de configuração do projeto. O layout estático (cores,
grid, botões) vive em DadosDoProjeto.xaml e é carregado via
pyrevit.forms.WPFWindow — este arquivo só cuida da lógica: carregar/
salvar firedata.json, consultar o site (sync.buscar) e travar os campos
que já vierem sincronizados de lá.

Nome do projeto / Estado só travam quando o site manda `projeto: {nome,
uf}` na resposta de `ocupacao_area` (extensão do contrato ainda pendente
do lado do site) — até lá seguem editáveis normalmente. Área construída
sempre trava quando uma estrutura é vinculada, porque `estrutura.areaTotal`
já faz parte do contrato atual. Ocupação principal nunca trava: fica
restrita às divisões que existem de fato nos pavimentos da estrutura,
pré-selecionada na mais restritiva (menor distância máxima de saída),
mas o usuário pode escolher outra dentre as existentes.
"""

__title__ = "Dados do\nProjeto"

import io
import os
import json
import datetime

import clr
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")
import System.Windows.Controls as SWC

from pyrevit import forms, script

from sync import config_sync, salvar_config_sync, buscar

_CACHE_NOME = u"firedata.json"
_TEMP       = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
_LAST_PROJ  = os.path.join(_TEMP, u"fireutils_last_project.txt")
_XAML_PATH  = os.path.join(os.path.dirname(__file__), u"DadosDoProjeto.xaml")


# =============================================================================
# Persistência local (firedata.json)
# =============================================================================

def _salvar_ponteiro(projeto_dir):
    try:
        with io.open(_LAST_PROJ, "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def _carregar_projeto(projeto_dir):
    try:
        with io.open(_cache_path(projeto_dir), u"r", encoding=u"utf-8") as f:
            return json.loads(f.read()).get(u"dados_projeto")
    except Exception:
        return None


def _salvar_projeto(projeto_dir, identificador, estado_nome, uf, ocupacao_principal, area_construida):
    dados = {
        u"identificador":      identificador,
        u"estado":             estado_nome,
        u"uf":                 uf,
        u"ocupacao_principal": ocupacao_principal,
        u"area_construida":    area_construida,
        u"_timestamp":         datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"),
    }
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            arquivo = json.loads(f.read())
    except Exception:
        arquivo = {}
    arquivo[u"dados_projeto"] = dados
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(arquivo, f, ensure_ascii=False, indent=2)
    _salvar_ponteiro(projeto_dir)


def _carregar_estado(uf):
    """Carrega o dict normativo do estado a partir da sigla, ou None."""
    try:
        from normas import get_estado
        return get_estado(uf)
    except Exception:
        return None


def _parse_area(txt):
    """Converte texto para float, aceitando vírgula ou ponto. Retorna None se vazio."""
    s = (txt or u"").strip().replace(u",", u".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# =============================================================================
# Ocupação principal — tabela normativa completa (fallback sem estrutura
# vinculada) e recorte pelas divisões que existem na estrutura do site
# =============================================================================

def _opcoes_ocupacao_normativa(estado):
    if not estado:
        return []
    tabela = estado.get(u"tabela", {})
    ocups  = estado.get(u"ocupacoes", {})
    opcoes = []
    for codigo in sorted(tabela.keys()):
        desc = ocups.get(codigo, {}).get(u"descricao", u"")
        label = u"{}  —  {}".format(codigo, desc) if desc else codigo
        opcoes.append((codigo, label))
    return opcoes


def _distancia_minima(estado, codigo):
    """Menor distância máxima aplicável ao código de ocupação, no cenário
    mais exigente (saída única, sem chuveiro, sem detecção) — usado só
    pra decidir qual divisão é a mais restritiva entre as existentes na
    estrutura. Retorna None se o código não constar da tabela normativa."""
    dist_cfg = (estado or {}).get(u"distancias_maximas")
    if not dist_cfg:
        return None
    mapa   = dist_cfg.get(u"mapa_ocupacao", {})
    grupos = dist_cfg.get(u"grupos", {})
    nome_grupo = mapa.get(codigo)
    if not nome_grupo:
        return None
    cfg = grupos.get(nome_grupo, {})
    valores = []
    for tipo_pav in (u"terreo", u"demais"):
        try:
            v = cfg[tipo_pav][u"sem_chuveiro"][u"saida_unica"][u"sem_deteccao"]
            if v is not None:
                valores.append(v)
        except (KeyError, TypeError):
            pass
    return min(valores) if valores else None


def _opcoes_ocupacao_estrutura(estado, pavimentos):
    """Códigos de divisão que existem de fato nos pavimentos da estrutura
    vinculada, ordenados do mais restritivo (menor distância) pro menos —
    cada item (codigo, label, distancia_ou_None)."""
    codigos = []
    for p in pavimentos:
        cod = p.get(u"divisao")
        if cod and cod not in codigos:
            codigos.append(cod)

    ocups = (estado or {}).get(u"ocupacoes", {})

    def _label(codigo):
        desc = ocups.get(codigo, {}).get(u"descricao", u"")
        return u"{}  —  {}".format(codigo, desc) if desc else codigo

    itens = [(cod, _label(cod), _distancia_minima(estado, cod)) for cod in codigos]
    itens.sort(key=lambda t: (t[2] is None, t[2]))
    return itens


# =============================================================================
# Janela
# =============================================================================

class _JanelaDadosProjeto(forms.WPFWindow):

    def __init__(self, projeto_dir):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.projeto_dir = projeto_dir
        self._estado_travado = False

        existente = _carregar_projeto(projeto_dir) or {}
        existente.setdefault(u"identificador", existente.get(u"nome", u""))

        self.TxtNome.Text = existente.get(u"identificador", u"")
        area_salva = existente.get(u"area_construida")
        self.TxtAreaConstruida.Text = u"{}".format(area_salva) if area_salva is not None else u""

        uf_salva = existente.get(u"uf", u"")
        idx_uf = 0
        for i in range(self.CbEstado.Items.Count):
            if self.CbEstado.Items[i].Tag == uf_salva:
                idx_uf = i
                break
        self.CbEstado.SelectedIndex = idx_uf

        self._preencher_ocupacao_normativa(existente.get(u"ocupacao_principal"))

        config_salva = config_sync(projeto_dir)
        self.TxtToken.Text = config_salva.get(u"token", u"")
        self._estrutura_id_salva   = config_salva.get(u"estruturaId", u"")
        estrutura_nome_salva       = config_salva.get(u"estruturaNome", u"")

        # Placeholder com o vínculo já salvo — selecioná-lo dispara
        # on_estrutura_changed automaticamente (abaixo), que já busca a
        # ocupação/área no site e trava os campos aplicáveis de novo.
        if estrutura_nome_salva:
            item = SWC.ComboBoxItem()
            item.Content = estrutura_nome_salva
            item.Tag     = self._estrutura_id_salva
            self.CbEstrutura.Items.Add(item)
            self.CbEstrutura.SelectedIndex = 0

    # ------------------------------------------------------------------
    # Ocupação — popular o ComboBox
    # ------------------------------------------------------------------
    def _uf_selecionada(self):
        item = self.CbEstado.SelectedItem
        return item.Tag if item else u"MA"

    def _preencher_ocupacao_normativa(self, preselect_codigo):
        estado = _carregar_estado(self._uf_selecionada())
        opcoes = _opcoes_ocupacao_normativa(estado)
        self.CbOcupacao.Items.Clear()
        for codigo, label in opcoes:
            item = SWC.ComboBoxItem()
            item.Content = label
            item.Tag     = codigo
            self.CbOcupacao.Items.Add(item)
        idx = 0
        if preselect_codigo:
            for i, (codigo, _label) in enumerate(opcoes):
                if codigo == preselect_codigo:
                    idx = i
                    break
        if self.CbOcupacao.Items.Count > 0:
            self.CbOcupacao.SelectedIndex = idx

    def _preencher_ocupacao_estrutura(self, estado, pavimentos):
        itens = _opcoes_ocupacao_estrutura(estado, pavimentos)
        if not itens:
            return
        self.CbOcupacao.Items.Clear()
        for codigo, label, _dist in itens:
            item = SWC.ComboBoxItem()
            item.Content = label
            item.Tag     = codigo
            self.CbOcupacao.Items.Add(item)
        self.CbOcupacao.SelectedIndex = 0  # já vem ordenado — mais restritiva primeiro

    # ------------------------------------------------------------------
    # Handlers (nomes batem com Click/SelectionChanged do XAML)
    # ------------------------------------------------------------------
    def on_estado_changed(self, sender, args):
        if self._estado_travado:
            return
        self._preencher_ocupacao_normativa(None)

    def on_cancel(self, sender, args):
        self.Close()

    def on_buscar_estruturas(self, sender, args):
        token = self.TxtToken.Text.strip()
        if not token:
            forms.alert(u"Informe o token antes de buscar as estruturas.", title=u"Fire Utils")
            return

        try:
            salvar_config_sync(self.projeto_dir, token=token)
        except Exception as ex:
            forms.alert(u"Erro ao salvar o token: {}".format(ex), title=u"Fire Utils", warn_icon=True)
            return

        self.BtnBuscarEstruturas.Content   = u"Buscando…"
        self.BtnBuscarEstruturas.IsEnabled = False
        try:
            resultado, erro = buscar(u"listar_estruturas", self.projeto_dir)
        finally:
            self.BtnBuscarEstruturas.Content   = u"Buscar"
            self.BtnBuscarEstruturas.IsEnabled = True

        if erro:
            forms.alert(u"Não foi possível buscar as estruturas:\n{}".format(erro),
                        title=u"Fire Utils", warn_icon=True)
            return
        if not resultado:
            forms.alert(u"Nenhuma estrutura encontrada nesse projeto no site.", title=u"Fire Utils")
            return

        self.CbEstrutura.Items.Clear()
        idx_sel = -1
        for i, est in enumerate(resultado):
            item = SWC.ComboBoxItem()
            item.Content = est.get(u"nome", u"")
            item.Tag     = est.get(u"id", u"")
            self.CbEstrutura.Items.Add(item)
            if est.get(u"id") == self._estrutura_id_salva:
                idx_sel = i
        if self.CbEstrutura.Items.Count > 0:
            # Dispara on_estrutura_changed sozinho (SelectionChanged).
            self.CbEstrutura.SelectedIndex = idx_sel if idx_sel >= 0 else 0

    def on_estrutura_changed(self, sender, args):
        item = self.CbEstrutura.SelectedItem
        if not item or not item.Tag:
            return

        resultado, erro = buscar(u"ocupacao_area", self.projeto_dir, estruturaId=item.Tag)
        if erro:
            forms.alert(u"Não foi possível buscar os dados da estrutura:\n{}".format(erro),
                        title=u"Fire Utils", warn_icon=True)
            return

        estrutura  = (resultado or {}).get(u"estrutura") or {}
        pavimentos = (resultado or {}).get(u"pavimentos") or []
        projeto    = (resultado or {}).get(u"projeto") or {}

        # Área construída — sempre disponível na estrutura, sempre trava.
        area = estrutura.get(u"areaTotal")
        if area is not None:
            self.TxtAreaConstruida.Text       = u"{}".format(area)
            self.TxtAreaConstruida.IsEnabled  = False

        # Nome do projeto / Estado — só travam quando o site já mandar
        # `projeto` na resposta (extensão de contrato ainda pendente).
        if projeto.get(u"nome"):
            self.TxtNome.Text      = projeto.get(u"nome")
            self.TxtNome.IsEnabled = False

        if projeto.get(u"uf"):
            self._estado_travado = True
            for i in range(self.CbEstado.Items.Count):
                if self.CbEstado.Items[i].Tag == projeto.get(u"uf"):
                    self.CbEstado.SelectedIndex = i
                    break
            self.CbEstado.IsEnabled = False

        # Ocupação — recalcula com base nos pavimentos vindos do site,
        # restrita às divisões que existem de fato, mais restritiva primeiro.
        if pavimentos:
            estado = _carregar_estado(self._uf_selecionada())
            self._preencher_ocupacao_estrutura(estado, pavimentos)

        self.TxtStatusSync.Text = u"✓ Sincronizado com o site — {} pavimento(s).".format(len(pavimentos))

    def on_salvar(self, sender, args):
        nome           = self.TxtNome.Text.strip()
        item_estado    = self.CbEstado.SelectedItem
        item_ocup      = self.CbOcupacao.SelectedItem
        item_estrutura = self.CbEstrutura.SelectedItem

        if not nome:
            forms.alert(u"Informe o nome do projeto.", title=u"Fire Utils")
            return
        if not item_estado:
            forms.alert(u"Selecione o Estado.", title=u"Fire Utils")
            return
        if not item_ocup:
            forms.alert(u"Selecione a ocupação principal.", title=u"Fire Utils")
            return

        uf                 = item_estado.Tag
        estado_nome        = item_estado.Content
        ocupacao_principal = item_ocup.Tag
        area_construida    = _parse_area(self.TxtAreaConstruida.Text)
        token              = self.TxtToken.Text.strip()
        estrutura_id       = item_estrutura.Tag     if item_estrutura else u""
        estrutura_nome     = item_estrutura.Content if item_estrutura else u""

        try:
            _salvar_projeto(self.projeto_dir, nome, estado_nome, uf, ocupacao_principal, area_construida)
        except Exception as ex:
            forms.alert(u"Erro ao salvar dados: {}".format(ex), title=u"Fire Utils", warn_icon=True)
            return

        try:
            salvar_config_sync(self.projeto_dir, token=token, estruturaId=estrutura_id, estruturaNome=estrutura_nome)
        except Exception as ex:
            forms.alert(
                u"Dados do projeto salvos, mas houve um erro ao salvar a configuração de "
                u"sincronização:\n{}".format(ex),
                title=u"Fire Utils", warn_icon=True,
            )

        self.Close()


# =============================================================================
# ENTRY POINT
# =============================================================================

doc = __revit__.ActiveUIDocument.Document

if not doc.PathName:
    forms.alert(
        u"O projeto Revit não está salvo.\n\n"
        u"Salve o arquivo (.rvt) antes de configurar os Dados do Projeto.",
        title=u"Fire Utils — Salve o projeto",
        warn_icon=True,
    )
    script.exit()

projeto_dir = os.path.dirname(doc.PathName)

try:
    _JanelaDadosProjeto(projeto_dir).ShowDialog()
except Exception as ex:
    forms.alert(u"Erro ao abrir formulário: {}".format(ex), title=u"Fire Utils", warn_icon=True)
    script.exit()
