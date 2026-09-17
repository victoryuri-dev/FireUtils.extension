# -*- coding: utf-8 -*-
"""
resultado_ui.py — Fire Utils · lib/hidrantes/
Janela WPF nativa (XAML, Resultado.xaml na mesma pasta) que mostra o
resultado de "Dimensionar Hidrantes" — o resumo final, quando todas as
verificações atendem a norma, ou o bloqueio, quando alguma não atende — em
vez de imprimir no console do pyRevit.

Módulo puro: recebe os resultados já calculados (por calcular_rede() e
companhia, em calc.py) — não importa nada do Revit. O passo a passo
completo (memorial de cálculo) migrou pro site (ETOS.FireUtils, ver
src/data/memorial/hidrantesCalculo.js — sempre a última folha do memorial),
a partir do mesmo cache sincronizado por "Dimensionar Hidrantes"; aqui é
só o resumo/bloqueio de "Dimensionar Hidrantes".
"""

import os

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import (
    Thickness, HorizontalAlignment, TextWrapping, FontWeights, CornerRadius,
    Visibility,
)
from System.Windows.Controls import (
    Grid, TextBlock, Border, Button, CheckBox, ColumnDefinition, RowDefinition,
)

from pyrevit import forms

_XAML_PATH = os.path.join(os.path.dirname(__file__), u"Resultado.xaml")

SIM_OK, SIM_X = u"✓", u"✗"

# Marcador de célula "pill" (box arredondada de verificação) dentro do texto
# passado a tabela() — mesma convenção do "**negrito**": embutido na string,
# decodificado em _celula(). \x00 nao aparece em texto normal, entao serve
# de separador seguro entre a flag (0/1) e o rotulo.
_PILL_MARK = u"\x00PILL\x00"


def _pill(ok, texto=None):
    """Marca um valor de tabela para renderizar como box arredondada verde
    (atende) ou vermelha (não atende) em vez de texto simples."""
    if texto is None:
        texto = u"{} Atende".format(SIM_OK) if ok else u"{} Não atende".format(SIM_X)
    return u"{}{}\x00{}".format(_PILL_MARK, u"1" if ok else u"0", texto)


# Marcador de célula "botão" (ex.: "Localizar" por linha, mostrar_inconsistencias_
# mapeamento) — mesma convenção do _PILL_MARK acima.
_BOTAO_MARK = u"\x00BOTAO\x00"


def _botao(eid, rotulo=u"Localizar"):
    """Marca um valor de tabela para renderizar como botão em vez de texto —
    clicar fecha a janela e sinaliza pro chamador mostrar só esse elemento
    (ElementId int) no Revit; ver _JanelaResultado._on_localizar."""
    return u"{}{}\x00{}".format(_BOTAO_MARK, eid, rotulo)


# Marcador de célula "checkbox" (coluna "Ignorar" de mostrar_inconsistencias_
# mapeamento, quando permitir_continuar=True) — mesma convenção acima.
_CHECKBOX_MARK = u"\x00CHECK\x00"


def _checkbox(eid):
    """Marca um valor de tabela para renderizar como checkbox "Ignorar" —
    o usuário marca os itens que não afetam o cálculo antes de clicar em
    "Confirmar e Continuar" (ver _JanelaResultado.on_confirmar)."""
    return u"{}{}".format(_CHECKBOX_MARK, eid)


def _mca(valor):
    """Pressão em mca, 2 casas decimais, separador decimal vírgula (ex.: 21,00 mca)."""
    return u"{:.2f}".format(valor).replace(u".", u",") + u" mca"


def _mca_fina(valor, casas_max=8):
    """
    Como _mca(), mas com precisão variável — usada só para a diferença de
    pressão entre os ramais, que pode ser bem menor que 0,01 mca (ex.:
    0,00041 ou 0,0000062) e ficaria escondida (viraria "0,00") no formato
    fixo de 2 casas. Arredonda em `casas_max` decimais e tira os zeros à
    direita, nunca notação científica; mantém no mínimo 2 casas.
    """
    inteiro, dec = u"{:.{}f}".format(valor, casas_max).split(u".")
    dec = dec.rstrip(u"0").ljust(2, u"0")
    return u"{},{} mca".format(inteiro, dec)


# ===========================================================================
# Janela — casco fixo (XAML) + conteúdo dinâmico (seções/tabelas montadas
# em código, mesmo padrão do Carregador de Famílias para o catálogo)
# ===========================================================================

class _JanelaResultado(forms.WPFWindow):

    def __init__(self, titulo, subtitulo, status, fila_acoes=None, ao_localizar=None,
                 ao_confirmar=None):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.TxtTitulo.Text    = titulo
        self.TxtSubtitulo.Text = subtitulo or u""
        self._primeira_secao   = True
        self.ids_problema      = None
        self.mostrar_no_revit  = False
        # fila_acoes/ao_localizar: só usados pelos botões "Localizar" por
        # linha (ver _botao/_on_localizar) - permitem chamar a API do Revit
        # SEM fechar a janela, ao contrário de habilitar_botao_mostrar.
        self._fila_acoes  = fila_acoes
        self._ao_localizar = ao_localizar
        # ao_confirmar/_checkboxes: botão "Confirmar e Continuar" (ver
        # habilitar_confirmacao/on_confirmar) - só libera o prosseguimento
        # se todo checkbox "Ignorar" da tabela estiver marcado.
        self._ao_confirmar = ao_confirmar
        self._checkboxes   = []
        self._aplicar_status(status)

    def _aplicar_status(self, status):
        ok = (status == u"ok")
        cor_fundo = self.Resources[u"BrushOkTint"] if ok else self.Resources[u"BrushAccentTint"]
        cor_borda = self.Resources[u"BrushOk"]      if ok else self.Resources[u"BrushAccent"]
        self.BannerStatus.Background  = cor_fundo
        self.BannerStatus.BorderBrush = cor_borda
        self.TxtBanner.Foreground     = cor_borda
        self.TxtBanner.Text = (
            u"{} Dimensionamento concluído — todas as verificações atendem a norma.".format(SIM_OK)
            if ok else
            u"{} Dimensionamento interrompido — verificação normativa não atendida.".format(SIM_X)
        )

    def on_fechar(self, sender, args):
        self.Close()

    def habilitar_confirmacao(self):
        """Mostra o botão "Confirmar e Continuar" no rodapé — usado pela
        janela de inconsistências de mapeamento quando o mapeamento pode
        prosseguir (permitir_continuar=True). Ver on_confirmar."""
        self.BtnConfirmar.Visibility = Visibility.Visible

    def on_confirmar(self, sender, args):
        """Clique em "Confirmar e Continuar" - só prossegue o mapeamento se
        TODOS os checkboxes "Ignorar" da tabela estiverem marcados (o
        usuário confirmando que nenhum daqueles pontos afeta o cálculo).
        Caso contrário, avisa e mantém a janela aberta pra revisão. Assim
        como o "Localizar", a decisão só é tomada aqui, no clique - a
        janela abre sem travar nada, então o usuário pode conferir os
        elementos primeiro (com "Localizar") antes de marcar e confirmar."""
        if not self._checkboxes or not all(bool(c.IsChecked) for c in self._checkboxes):
            forms.alert(
                u"Marque \"Ignorar\" em todos os itens da lista antes de continuar — "
                u"eles precisam ser confirmados como sem efeito no cálculo. Se algum "
                u"for um problema real, feche esta janela, corrija a tubulação e "
                u"execute \"Mapear Trechos\" novamente.",
                title=u"Fire Utils", warn_icon=True)
            return
        if self._fila_acoes is not None and self._ao_confirmar is not None:
            self._fila_acoes.enfileirar(self._ao_confirmar)
        self.Close()

    def habilitar_botao_mostrar(self, ids_problema):
        """Mostra o botão "Mostrar no Projeto" no rodapé — usado pelas
        janelas de bloqueio para sinalizar quais elementos selecionar/
        enquadrar na view do Revit quando a janela fechar.

        O clique NÃO chama a API do Revit diretamente: a API não é
        reentrante — chamá-la de dentro do Click de uma janela modal
        (ShowDialog) trava o Revit. O botão só fecha a janela marcando
        mostrar_no_revit=True; é o chamador (Dimensionar Hidrantes/
        script.py), já de volta ao fluxo normal do comando depois que
        ShowDialog() retorna, quem efetivamente seleciona os elementos —
        mesmo motivo pelo qual o Carregador de Famílias despacha ações
        de API por ExternalEvent em vez de por clique direto."""
        if not ids_problema:
            return
        self.ids_problema = ids_problema
        self.BtnMostrarProjeto.Visibility = Visibility.Visible

    def on_mostrar_projeto(self, sender, args):
        self.mostrar_no_revit = True
        self.Close()

    def _on_localizar(self, sender, args):
        """Clique no botão "Localizar" de uma linha da tabela (ver _botao/
        _celula) — ao contrário do botão único (on_mostrar_projeto), NÃO
        fecha a janela: o usuário precisa poder clicar em várias linhas
        seguidas, conferindo cada elemento, sem perder a lista. A API do
        Revit ainda não pode ser chamada direto daqui (não é reentrante
        dentro do Click de uma janela modal) — em vez disso, enfileira a
        ação num ExternalEvent (fila_acoes.py), que o Revit executa assim
        que possível, com a janela continuando aberta."""
        if self._fila_acoes is None or self._ao_localizar is None:
            return
        eid = sender.Tag
        self._fila_acoes.enfileirar(lambda uiapp: self._ao_localizar(uiapp, eid))

    # ------------------------------------------------------------------
    # Blocos de conteúdo
    # ------------------------------------------------------------------
    def secao(self, titulo):
        bloco = TextBlock()
        bloco.Text       = titulo
        bloco.FontSize   = 14
        bloco.FontWeight = FontWeights.SemiBold
        bloco.Foreground = self.Resources[u"BrushText"]
        bloco.Margin     = Thickness(0, 0 if self._primeira_secao else 22, 0, 10)
        self._primeira_secao = False
        self.ConteudoPanel.Children.Add(bloco)

    def paragrafo(self, texto, cor=None):
        bloco = TextBlock()
        bloco.Text         = texto
        bloco.FontSize     = 12
        bloco.Foreground   = cor or self.Resources[u"BrushText2"]
        bloco.TextWrapping = TextWrapping.Wrap
        bloco.Margin       = Thickness(0, 0, 0, 10)
        self.ConteudoPanel.Children.Add(bloco)

    def dica(self, texto):
        """Caixa de dica — fundo e borda azuis, para a sugestão de correção
        nas janelas de bloqueio (separada do texto que diz o que não atendeu)."""
        caixa = Border()
        caixa.BorderBrush     = self.Resources[u"BrushInfo"]
        caixa.Background      = self.Resources[u"BrushInfoTint"]
        caixa.BorderThickness = Thickness(1)
        caixa.CornerRadius    = CornerRadius(6)
        caixa.Padding         = Thickness(14, 10, 14, 10)
        caixa.Margin          = Thickness(0, 0, 0, 10)

        txt = TextBlock()
        txt.Text         = texto
        txt.FontSize     = 12
        txt.Foreground   = self.Resources[u"BrushInfo"]
        txt.TextWrapping = TextWrapping.Wrap
        caixa.Child = txt
        self.ConteudoPanel.Children.Add(caixa)

    def tabela(self, colunas, linhas, alinhas=None):
        """
        colunas: lista de cabeçalhos.
        linhas:  lista de listas (uma por linha), já formatadas como texto.
                 Um valor entre "**...**" é renderizado em negrito (mesma
                 convenção usada nas tabelas HTML do memorial completo).
        alinhas: "left"/"right"/"center" por coluna; por padrão a primeira
                 coluna fica à esquerda e as demais à direita (números).
        """
        if alinhas is None:
            alinhas = [u"left"] + [u"right"] * (len(colunas) - 1)

        moldura = Border()
        moldura.BorderBrush     = self.Resources[u"BrushBorder"]
        moldura.BorderThickness = Thickness(1)
        moldura.CornerRadius    = CornerRadius(4)
        moldura.Margin          = Thickness(0, 0, 0, 16)

        grid = Grid()
        for _ in colunas:
            grid.ColumnDefinitions.Add(ColumnDefinition())
        grid.RowDefinitions.Add(RowDefinition())
        for _ in linhas:
            grid.RowDefinitions.Add(RowDefinition())

        for col_idx, (cabecalho, alinh) in enumerate(zip(colunas, alinhas)):
            self._celula(grid, 0, col_idx, cabecalho, alinh,
                        cabecalho=True, ultima_linha=(not linhas))

        n_linhas = len(linhas)
        for lin_idx, linha in enumerate(linhas):
            for col_idx, (valor, alinh) in enumerate(zip(linha, alinhas)):
                self._celula(grid, lin_idx + 1, col_idx, valor, alinh,
                            cabecalho=False, ultima_linha=(lin_idx == n_linhas - 1))

        moldura.Child = grid
        self.ConteudoPanel.Children.Add(moldura)

    def _badge(self, texto, ok):
        """Box arredondada de verificação: borda na cor do texto, fundo na
        mesma cor bem mais fraco (mesma paleta do banner de status)."""
        cor  = self.Resources[u"BrushOk"]     if ok else self.Resources[u"BrushAccent"]
        tint = self.Resources[u"BrushOkTint"] if ok else self.Resources[u"BrushAccentTint"]

        pilula = Border()
        pilula.CornerRadius = CornerRadius(10)
        pilula.BorderBrush = cor
        pilula.BorderThickness = Thickness(1)
        pilula.Background = tint
        pilula.Padding = Thickness(10, 3, 10, 3)

        txt = TextBlock()
        txt.Text = texto
        txt.FontSize = 11
        txt.FontWeight = FontWeights.SemiBold
        txt.Foreground = cor
        pilula.Child = txt
        return pilula

    def _celula(self, grid, linha, coluna, texto, alinh, cabecalho, ultima_linha):
        texto = u"{}".format(texto)

        cel = Border()
        cel.Padding = Thickness(14, 8, 14, 8)
        cel.Background = self.Resources[u"BrushBg3"] if cabecalho else self.Resources[u"BrushBg2"]
        espessura_baixo = 0 if ultima_linha else 1
        espessura_direita = 0 if coluna == grid.ColumnDefinitions.Count - 1 else 1
        cel.BorderBrush = self.Resources[u"BrushBorder"]
        cel.BorderThickness = Thickness(0, 0, espessura_direita, espessura_baixo)
        Grid.SetRow(cel, linha)
        Grid.SetColumn(cel, coluna)

        _alinh_wpf = {
            u"left": HorizontalAlignment.Left,
            u"right": HorizontalAlignment.Right,
            u"center": HorizontalAlignment.Center,
        }.get(alinh, HorizontalAlignment.Left)

        if texto.startswith(_PILL_MARK):
            ok_flag, rotulo = texto[len(_PILL_MARK):].split(u"\x00", 1)
            badge = self._badge(rotulo, ok_flag == u"1")
            badge.HorizontalAlignment = _alinh_wpf
            cel.Child = badge
            grid.Children.Add(cel)
            return

        if texto.startswith(_CHECKBOX_MARK):
            chk = CheckBox()
            chk.IsChecked = False
            chk.HorizontalAlignment = HorizontalAlignment.Center
            self._checkboxes.append(chk)
            cel.Child = chk
            grid.Children.Add(cel)
            return

        if texto.startswith(_BOTAO_MARK):
            eid_txt, rotulo = texto[len(_BOTAO_MARK):].split(u"\x00", 1)
            btn = Button()
            btn.Content = rotulo
            btn.FontSize = 11
            btn.Padding = Thickness(10, 3, 10, 3)
            btn.Background = self.Resources[u"BrushBg3"]
            btn.Foreground = self.Resources[u"BrushText"]
            btn.BorderBrush = self.Resources[u"BrushBorder2"]
            btn.BorderThickness = Thickness(1)
            btn.HorizontalAlignment = HorizontalAlignment.Left
            btn.Tag = int(eid_txt)
            btn.Click += self._on_localizar
            cel.Child = btn
            grid.Children.Add(cel)
            return

        negrito = False
        if texto.startswith(u"**") and texto.endswith(u"**") and len(texto) >= 4:
            negrito = True
            texto = texto[2:-2]

        txt = TextBlock()
        txt.Text = texto
        txt.FontSize = 12
        txt.TextWrapping = TextWrapping.Wrap
        if texto == SIM_OK or texto.startswith(SIM_OK + u" "):
            txt.Foreground = self.Resources[u"BrushOk"]
        elif texto == SIM_X or texto.startswith(SIM_X + u" "):
            txt.Foreground = self.Resources[u"BrushAccent"]
        else:
            txt.Foreground = self.Resources[u"BrushText"]
        if cabecalho or negrito:
            txt.FontWeight = FontWeights.SemiBold
        txt.HorizontalAlignment = _alinh_wpf
        cel.Child = txt

        grid.Children.Add(cel)


# ===========================================================================
# Funções públicas — chamadas por "Dimensionar Hidrantes"
# ===========================================================================

def mostrar_resultado_ok(res, valor_sistema, metodo_calculo, norma,
                          v_max_tubo, v_max_succao, p_ref_desc,
                          p_hd01_ref, p_hd02_ref, Pmin, Qs_lmin,
                          comprimento_min_velocidade=None):
    """
    Resumo final mostrado ao término de "Dimensionar Hidrantes": só
    verificações e resultados finais (velocidade nos quatro trechos —
    sucção, recalque e os dois ramais até os hidrantes —,
    pressão/vazão nos hidrantes mais desfavoráveis e no Ponto A, diferença
    de pressão entre os ramais após o equilíbrio e demanda do sistema) —
    não o passo a passo completo, que é o botão "Memorial de Cálculo". Só
    é chamada depois que todas as verificações normativas passaram.
    Eficiência e potência da bomba não entram mais aqui — o site
    (ETOS.FireUtils) faz esse dimensionamento a partir de Qt/Ht.

    comprimento_min_velocidade (m), quando informado: sub-trechos de
    sucção/recalque mais curtos que isso (ex.: redução na entrada/saída
    da bomba) ficam de fora da tabela — não foram verificados, não é que
    passaram. Não vale para os ramais até os hidrantes.
    """
    janela = _JanelaResultado(
        titulo=u"Dimensionamento de Hidrantes",
        subtitulo=u"Sistema: {}  ·  Método: {}  ·  Norma: {}".format(
            valor_sistema, metodo_calculo, norma),
        status=u"ok",
    )

    janela.secao(u"1. Velocidade nos Trechos")
    linhas_v = []
    for nome, j, limite, comp_min in (
        (u"RTI → Bomba",      res["j"]["t1"], v_max_succao, comprimento_min_velocidade),
        (u"Bomba → Ponto A",  res["j"]["t2"], v_max_tubo,   comprimento_min_velocidade),
        (u"Ponto A → HD01",   res["j"]["t3"], v_max_tubo,   None),
        (u"Ponto A → HD02",   res["j"]["t4"], v_max_tubo,   None),
    ):
        for s in j["segmentos"]:
            if comp_min is not None and s["L"] < comp_min:
                continue   # sub-trecho curto (ex.: redução na bomba) — não verificado
            linhas_v.append([nome, u"{:.1f}".format(s["d_mm"]),
                              u"{:.2f}".format(j["Q_lmin"]),
                              u"{:.3f}".format(s["V"]),
                              u"{:.1f}".format(limite),
                              _pill(True)])
    janela.tabela([u"Trecho", u"DN (mm)", u"Q (L/min)", u"V (m/s)", u"Limite (m/s)", u"Verificação"],
                  linhas_v,
                  alinhas=[u"left", u"right", u"right", u"right", u"right", u"left"])

    janela.secao(u"2. Pressão e Vazão")
    _col_p = p_ref_desc[0].upper() + p_ref_desc[1:]
    janela.tabela([u"Ponto", u"{} (mca)".format(_col_p), u"Mínimo exigido", u"Verificação"],
                  [[u"HD01", _mca(p_hd01_ref), _mca(Pmin), _pill(True)],
                   [u"HD02", _mca(p_hd02_ref), _mca(Pmin), _pill(True)],
                   [u"Ponto A", _mca(res["P_PA"]), u"—", u"—"]],
                  alinhas=[u"left", u"right", u"right", u"left"])
    janela.tabela([u"Ponto", u"Vazão (L/min)", u"Mínimo exigido", u"Verificação"],
                  [[u"HD01", u"{:.2f}".format(res["Q_hd01"]), u"{:.2f}".format(Qs_lmin), _pill(True)],
                   [u"HD02", u"{:.2f}".format(res["Q_hd02"]), u"{:.2f}".format(Qs_lmin), _pill(True)],
                   [u"Ponto A (Qt)", u"{:.2f}".format(res["Qt"]), u"—", u"—"]],
                  alinhas=[u"left", u"right", u"right", u"left"])

    janela.secao(u"3. Diferença de Pressão entre os Ramais")
    equilibrio = res.get("equilibrio")
    if equilibrio is not None:
        janela.tabela(
            [u"Verificação", u"Valor"],
            [[u"Diferença entre os ramais (após equilíbrio)", _mca_fina(equilibrio[u"erro"])],
             [u"Limite normativo ({})".format(norma), _mca(equilibrio[u"tolerancia"])],
             [u"Resultado", _pill(True)]],
            alinhas=[u"left", u"left"])

    janela.secao(u"4. Demanda do Sistema")
    janela.tabela([u"Parâmetro", u"Valor"],
                  [[u"Vazão total (Qt)", u"**{:.2f} L/min = {:.2f} m³/h**".format(
                      res["Qt"], res["Qt"] * 60.0 / 1000.0)],
                   [u"Altura manométrica total (HMT = P_RTI)",
                    u"**{}**".format(_mca(res["P_RTI"]))]],
                  alinhas=[u"left", u"left"])

    janela.paragrafo(u"Eficiência e potência da bomba são dimensionadas no site, a "
                     u"partir de Qt/Ht acima.")
    janela.paragrafo(u"O memorial de cálculo completo (passo a passo) é gerado no "
                     u"site — ETOS.FireUtils, última folha do memorial descritivo "
                     u"— a partir deste mesmo dimensionamento.")

    janela.ShowDialog()


def mostrar_inconsistencias_mapeamento(itens, bloqueante, fila_acoes, ao_localizar,
                                        permitir_continuar=False, ao_confirmar=None):
    """
    Janela mostrando pontos onde a rede de tubulação está quebrada — chamada
    por "Mapear Trechos". Cada linha tem seu próprio botão "Localizar", que
    NÃO fecha a janela (ao contrário do botão único "Mostrar no Projeto",
    não usado aqui): o usuário confere um elemento, a janela continua
    aberta, e ele clica no próximo. Clicar chama Revit por um ExternalEvent
    (ver fila_acoes/_on_localizar).

    Diferente das outras janelas deste módulo, esta é MODELESS (Show(),
    não ShowDialog()): o Revit só processa a fila de ExternalEvent quando
    o script Python que a abriu termina de rodar — com ShowDialog() (que
    bloqueia o script até a janela fechar) o clique em "Localizar" ficava
    parado na fila até o usuário fechar a janela. Com Show(), o script
    termina (ou segue em frente) imediatamente após abrir a janela, o
    Revit fica livre pra processar a fila, e cada clique em "Localizar"
    seleciona/enquadra o elemento na hora, com a janela ainda aberta.

    itens: lista de dicts {"trecho", "elemento", "eid"} já formatados pelo
        chamador (Revit-dependente — este módulo não importa nada do Revit).
        "eid": ElementId (int) do elemento daquela linha.
    bloqueante: True se alguma válvula de hidrante ficou sem rota — só
        afeta o texto mostrado (a decisão de prosseguir ou não é sempre
        do usuário, via o botão "Confirmar e Continuar" quando
        permitir_continuar=True; ver abaixo).
    fila_acoes: fila de ExternalEvent (hidrantes/fila_acoes.py), criada
        pelo chamador num contexto de API válido.
    ao_localizar: callable(uiapp, eid) que efetivamente seleciona/enquadra
        o elemento no Revit — chamado pela fila, não direto pelo clique.
    permitir_continuar: True quando o mapeamento pode prosseguir mesmo com
        esses itens (ex.: rede de recalque — ainda sobraram rotas válidas
        suficientes até outras válvulas). Nesse caso a tabela ganha uma
        coluna "Ignorar" (checkbox por linha) e aparece o botão "Confirmar
        e Continuar": o mapeamento só é retomado quando TODOS os itens da
        lista estiverem marcados (ver on_confirmar) — o usuário decide
        isso com calma, depois de conferir cada ponto com "Localizar", não
        mais assim que a janela abre. False (ex.: sucção sem rota até a
        bomba) — não há como prosseguir de jeito nenhum, a janela é só
        informativa.
    ao_confirmar: callable(uiapp), chamado pela fila (como ao_localizar)
        quando o usuário confirma com todos os itens marcados — deve
        terminar o mapeamento (gravar parâmetros/cache). Obrigatório se
        permitir_continuar=True.

    Não retorna nada — tanto "Localizar" quanto "Confirmar e Continuar"
    agem ao vivo, via fila_acoes, enquanto a janela está aberta.
    """
    janela = _JanelaResultado(
        titulo=u"Inconsistências no Mapeamento",
        subtitulo=u"Tubulação sem conexão em {} ponto(s)".format(len(itens)),
        status=u"erro",
        fila_acoes=fila_acoes,
        ao_localizar=ao_localizar,
        ao_confirmar=ao_confirmar,
    )
    if permitir_continuar:
        linhas = [[item[u"trecho"], item[u"elemento"], _botao(item[u"eid"]),
                   _checkbox(item[u"eid"])] for item in itens]
        janela.tabela([u"Trecho", u"Elemento", u"", u"Ignorar"], linhas,
                      alinhas=[u"left", u"left", u"left", u"center"])
    else:
        linhas = [[item[u"trecho"], item[u"elemento"], _botao(item[u"eid"])] for item in itens]
        janela.tabela([u"Trecho", u"Elemento", u""], linhas,
                      alinhas=[u"left", u"left", u"left"])
    if bloqueante:
        janela.paragrafo(u"Pelo menos uma válvula de hidrante ficou sem rota até a bomba.")
    else:
        janela.paragrafo(u"Hidrantes suficientes já foram encontrados, mas os pontos "
                         u"acima não levam a nenhuma válvula e vale revisar.")
    if permitir_continuar:
        janela.dica(u"Marque \"Ignorar\" nos itens que não afetam o cálculo (ex.: dreno, "
                    u"ramal morto de verdade) e clique em \"Confirmar e Continuar\" para "
                    u"prosseguir o mapeamento com as rotas já encontradas. Se algum for "
                    u"um problema real, feche esta janela, corrija a tubulação e execute "
                    u"\"Mapear Trechos\" novamente.")
        janela.habilitar_confirmacao()
    else:
        janela.dica(u"Dica: reconecte a tubulação nos pontos acima e execute "
                    u"\"Mapear Trechos\" novamente.")
    janela.Show()


def mostrar_bloqueio_equilibrio(equilibrio, norma, ids_problema=None):
    """Janela mostrando que o equilíbrio hidráulico entre os ramais no
    Ponto A não convergiu dentro da variação de pressão máxima admitida
    pela norma — chamada por "Dimensionar Hidrantes" quando o
    dimensionamento é interrompido nessa verificação.

    Retorna a lista de ElementId a selecionar no Revit se o usuário
    clicou "Mostrar no Projeto", ou None — ver habilitar_botao_mostrar()."""
    janela = _JanelaResultado(
        titulo=u"Verificação não atendida",
        subtitulo=u"Diferença de pressão entre os ramais não atende a norma",
        status=u"erro",
    )
    janela.tabela(
        [u"Verificação", u"Valor"],
        [[u"Diferença entre os ramais (após {} iteração(ões))".format(
              len(equilibrio[u"historico"])), _mca_fina(equilibrio[u"erro"])],
         [u"Limite normativo ({})".format(norma), _mca(equilibrio[u"tolerancia"])],
         [u"Resultado", _pill(False)]],
        alinhas=[u"left", u"left"])
    janela.paragrafo(u"Não atende: a diferença de pressão entre os ramais no "
                     u"Ponto A passou do limite da norma.")
    janela.dica(u"Dica: revise o diâmetro dos trechos entre o Ponto A e os hidrantes.")
    janela.habilitar_botao_mostrar(ids_problema)
    janela.ShowDialog()
    return janela.ids_problema if janela.mostrar_no_revit else None


def mostrar_bloqueio_velocidade(nome_trecho, j, limite, falhas, ids_problema=None):
    """Janela mostrando quais diâmetros do trecho passaram do limite de
    velocidade — chamada por "Dimensionar Hidrantes" quando o
    dimensionamento é interrompido nessa verificação.

    Retorna a lista de ElementId a selecionar no Revit se o usuário
    clicou "Mostrar no Projeto", ou None — ver habilitar_botao_mostrar()."""
    janela = _JanelaResultado(
        titulo=u"Verificação não atendida",
        subtitulo=u"Velocidade acima do limite — {}".format(nome_trecho),
        status=u"erro",
    )
    janela.tabela([u"DN (mm)", u"V (m/s)", u"Limite (m/s)", u"Verificação"],
                  [[u"{:.1f}".format(s["d_mm"]), u"**{:.3f}**".format(s["V"]),
                    u"{:.1f}".format(limite), _pill(False)] for s in falhas])
    janela.paragrafo(u"Não atende: velocidade acima do limite normativo.")
    janela.dica(u"Dica: aumente o diâmetro do trecho. A vazão é um dado "
                u"normativo fixo do tipo de sistema e não pode ser reduzida.")
    janela.habilitar_botao_mostrar(ids_problema)
    janela.ShowDialog()
    return janela.ids_problema if janela.mostrar_no_revit else None


def mostrar_bloqueio_hidrante(label, p, q, p_ref_desc, trecho_desc, Pmin, Qs_lmin,
                              ids_problema=None):
    """Janela mostrando por que a pressão/vazão de um hidrante mais
    desfavorável não atendeu a norma — chamada por "Dimensionar Hidrantes"
    quando o dimensionamento é interrompido nessa verificação.

    Retorna a lista de ElementId a selecionar no Revit se o usuário
    clicou "Mostrar no Projeto", ou None — ver habilitar_botao_mostrar()."""
    janela = _JanelaResultado(
        titulo=u"Verificação não atendida",
        subtitulo=u"{} não atende a norma".format(label),
        status=u"erro",
    )
    janela.tabela([u"Grandeza", u"Obtido", u"Mínimo exigido", u"Verificação"],
                  [[p_ref_desc[0].upper() + p_ref_desc[1:], _mca(p), _mca(Pmin),
                    _pill(p >= Pmin - 0.01)],
                   [u"Vazão", u"{:.2f} L/min".format(q), u"{:.2f} L/min".format(Qs_lmin),
                    _pill(q >= Qs_lmin - 0.01)]],
                  alinhas=[u"left", u"right", u"right", u"left"])
    janela.paragrafo(u"Não atende: pressão ou vazão abaixo do mínimo exigido.")
    janela.dica(u"Dica: revise o diâmetro/traçado do trecho {}.".format(trecho_desc))
    janela.habilitar_botao_mostrar(ids_problema)
    janela.ShowDialog()
    return janela.ids_problema if janela.mostrar_no_revit else None
