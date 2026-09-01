# -*- coding: utf-8 -*-
"""
resultado_ui.py — Fire Utils · lib/hidrantes/
Janela WPF nativa (XAML, Resultado.xaml na mesma pasta) que mostra o
resultado de "Dimensionar Hidrantes" — o resumo final, quando todas as
verificações atendem a norma, ou o bloqueio, quando alguma não atende — em
vez de imprimir no console do pyRevit.

Módulo puro: recebe os resultados já calculados (por calcular_rede() e
companhia, em calc.py) — não importa nada do Revit. O passo a passo
completo (memorial de cálculo) continua no botão separado "Memorial de
Cálculo" (hidrantes/memorial.py, console + arquivo .html) — aqui é só o
resumo/bloqueio de "Dimensionar Hidrantes".
"""

import os

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import (
    Thickness, HorizontalAlignment, TextWrapping, FontWeights, CornerRadius,
)
from System.Windows.Controls import Grid, TextBlock, Border, ColumnDefinition, RowDefinition

from pyrevit import forms

_XAML_PATH = os.path.join(os.path.dirname(__file__), u"Resultado.xaml")

SIM_OK, SIM_X = u"✓", u"✗"


# ===========================================================================
# Janela — casco fixo (XAML) + conteúdo dinâmico (seções/tabelas montadas
# em código, mesmo padrão do Carregador de Famílias para o catálogo)
# ===========================================================================

class _JanelaResultado(forms.WPFWindow):

    def __init__(self, titulo, subtitulo, status):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.TxtTitulo.Text    = titulo
        self.TxtSubtitulo.Text = subtitulo or u""
        self._primeira_secao   = True
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

    def _celula(self, grid, linha, coluna, texto, alinh, cabecalho, ultima_linha):
        texto = u"{}".format(texto)
        negrito = False
        if texto.startswith(u"**") and texto.endswith(u"**") and len(texto) >= 4:
            negrito = True
            texto = texto[2:-2]

        cel = Border()
        cel.Padding = Thickness(14, 8, 14, 8)
        cel.Background = self.Resources[u"BrushBg3"] if cabecalho else self.Resources[u"BrushBg2"]
        espessura_baixo = 0 if ultima_linha else 1
        espessura_direita = 0 if coluna == grid.ColumnDefinitions.Count - 1 else 1
        cel.BorderBrush = self.Resources[u"BrushBorder"]
        cel.BorderThickness = Thickness(0, 0, espessura_direita, espessura_baixo)
        Grid.SetRow(cel, linha)
        Grid.SetColumn(cel, coluna)

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
        txt.HorizontalAlignment = {
            u"left": HorizontalAlignment.Left,
            u"right": HorizontalAlignment.Right,
            u"center": HorizontalAlignment.Center,
        }.get(alinh, HorizontalAlignment.Left)
        cel.Child = txt

        grid.Children.Add(cel)


# ===========================================================================
# Funções públicas — chamadas por "Dimensionar Hidrantes"
# ===========================================================================

def mostrar_resultado_ok(res, valor_sistema, metodo_calculo, norma,
                          v_max_tubo, v_max_succao, p_ref_desc,
                          p_hd01_ref, p_hd02_ref, Pmin, Qs_lmin,
                          eta, pot_cv, pot_kw,
                          pot_escolhida_cv=None, pot_escolhida_kw=None):
    """
    Resumo final mostrado ao término de "Dimensionar Hidrantes": só
    verificações e resultados finais (velocidade por trecho, pressão/vazão
    nos hidrantes mais desfavoráveis e no Ponto A, diferença de pressão
    entre os ramais antes do equilíbrio, demanda do sistema e requisitos da
    bomba) — não o passo a passo completo, que é o botão "Memorial de
    Cálculo". Só é chamada depois que todas as verificações normativas
    passaram.
    """
    janela = _JanelaResultado(
        titulo=u"Dimensionamento de Hidrantes",
        subtitulo=u"Sistema: {}  ·  Método: {}  ·  Norma: {}".format(
            valor_sistema, metodo_calculo, norma),
        status=u"ok",
    )

    janela.secao(u"1. Velocidade nos Trechos")
    linhas_v = []
    for nome, j, limite in (
        (u"Sucção (RTI → Bomba)",       res["j"]["t1"], v_max_succao),
        (u"Recalque (Bomba → Ponto A)", res["j"]["t2"], v_max_tubo),
        (u"Ponto A → HD01",             res["j"]["t3"], v_max_tubo),
        (u"Ponto A → HD02",             res["j"]["t4"], v_max_tubo),
    ):
        for s in j["segmentos"]:
            linhas_v.append([nome, u"{:.1f}".format(s["d_mm"]),
                              u"{:.2f}".format(j["Q_lmin"]),
                              u"{:.3f}".format(s["V"]),
                              u"{:.1f}".format(limite),
                              u"{} atende".format(SIM_OK)])
    janela.tabela([u"Trecho", u"DN (mm)", u"Q (L/min)", u"V (m/s)", u"Limite (m/s)", u"Verificação"],
                  linhas_v,
                  alinhas=[u"left", u"right", u"right", u"right", u"right", u"left"])

    janela.secao(u"2. Pressão e Vazão Finais — Hidrantes e Ponto A")
    _col_p = p_ref_desc[0].upper() + p_ref_desc[1:]
    janela.tabela([u"Hidrante", u"{} (mca)".format(_col_p), u"Q (L/min)",
                  u"Mínimo exigido", u"Verificação"],
                  [[u"HD01", u"{:.4f}".format(p_hd01_ref), u"{:.2f}".format(res["Q_hd01"]),
                    u"{:.4f} mca / {:.2f} L/min".format(Pmin, Qs_lmin),
                    u"{} atende".format(SIM_OK)],
                   [u"HD02", u"{:.4f}".format(p_hd02_ref), u"{:.2f}".format(res["Q_hd02"]),
                    u"{:.4f} mca / {:.2f} L/min".format(Pmin, Qs_lmin),
                    u"{} atende".format(SIM_OK)]],
                  alinhas=[u"left", u"right", u"right", u"left", u"left"])
    janela.tabela([u"Ponto A", u"Valor"],
                  [[u"Pressão adotada (P_PA,alvo)", u"**{:.4f} mca**".format(res["P_PA"])],
                   [u"Vazão total (Qt = Q_hd01 + Q_hd02)",
                    u"**{:.2f} L/min**".format(res["Qt"])]],
                  alinhas=[u"left", u"left"])

    janela.secao(u"3. Verificação de Diferença de Pressão entre os Ramais")
    equilibrio = res.get("equilibrio")
    diferenca = abs(res["P_PA1"] - res["P_PA2"])
    janela.tabela([u"Ramal", u"P_A inicial (mca, ambos em Qs)", u"Governante"],
                  [[u"HD01", u"{:.4f}".format(res["P_PA1"]),
                    SIM_OK if res["hid_governa"] == u"HD01" else u""],
                   [u"HD02", u"{:.4f}".format(res["P_PA2"]),
                    SIM_OK if res["hid_governa"] == u"HD02" else u""]],
                  alinhas=[u"left", u"right", u"left"])
    janela.paragrafo(
        u"Diferença inicial entre os ramais (ambos calculados com a vazão mínima "
        u"Qs, antes do equilíbrio): {:.4f} mca. Essa diferença é esperada — vem de "
        u"variações de comprimento, comprimento equivalente (conexões/acessórios), "
        u"diâmetro e desnível entre os dois ramais — e não indica, por si só, "
        u"subdimensionamento da tubulação.".format(diferenca))
    if equilibrio is not None:
        if equilibrio[u"convergiu"]:
            janela.paragrafo(
                u"{} Equilíbrio hidráulico do ramal mais favorável (**{}**) convergiu em "
                u"{} iteração(ões) — erro final de {:.6f} mca (tolerância {:g} mca).".format(
                    SIM_OK, equilibrio[u"ramal_iterado"], len(equilibrio[u"historico"]),
                    equilibrio[u"erro"], equilibrio[u"tolerancia"]))
        else:
            janela.paragrafo(
                u"{} Equilíbrio hidráulico do ramal mais favorável (**{}**) NÃO convergiu "
                u"em {} iterações — erro final de {:.6f} mca (tolerância {:g} mca). "
                u"Resultado aproximado; revisar a geometria da rede.".format(
                    SIM_X, equilibrio[u"ramal_iterado"], len(equilibrio[u"historico"]),
                    equilibrio[u"erro"], equilibrio[u"tolerancia"]),
                cor=janela.Resources[u"BrushAccent"])
        _q_favoravel = (res["Q_hd02"] if equilibrio[u"ramal_iterado"] == u"HD02"
                        else res["Q_hd01"])
        _r_q = _q_favoravel / Qs_lmin if Qs_lmin else 0.0
        janela.paragrafo(
            u"Indicador de desequilíbrio — o quanto o equilíbrio elevou a vazão do "
            u"ramal mais favorável acima da vazão mínima: R_Q = Q_final/Q_mín = "
            u"{:.2f}/{:g} = {:.3f}. Não há percentual fixo como critério normativo; um "
            u"R_Q alto indica perda de carga desproporcional no ramal governante e "
            u"vale avaliar o diâmetro dele, desde que a diferença não seja "
            u"predominantemente por desnível geométrico (que o diâmetro não "
            u"corrige). Para o detalhamento completo da iteração, veja o \"Memorial "
            u"de Cálculo\".".format(_q_favoravel, Qs_lmin, _r_q))

    janela.secao(u"4. Demanda do Sistema")
    janela.tabela([u"Parâmetro", u"Valor"],
                  [[u"Vazão total (Qt)", u"**{:.2f} L/min = {:.4f} m³/h**".format(
                      res["Qt"], res["Qt"] * 60.0 / 1000.0)],
                   [u"Altura manométrica total (HMT = P_RTI)",
                    u"**{:.4f} mca**".format(res["P_RTI"])]],
                  alinhas=[u"left", u"left"])

    janela.secao(u"5. Requisitos da Bomba de Recalque")
    linhas_bomba = [
        [u"Vazão de projeto (Qt)", u"{:.2f} L/min = {:.4f} m³/h".format(
            res["Qt"], res["Qt"] * 60.0 / 1000.0)],
        [u"Altura manométrica (Ht)", u"{:.4f} mca".format(res["P_RTI"])],
        [u"Eficiência global (η)", u"{:.0f}%".format(eta)],
        [u"Potência mínima calculada", u"**{:.2f} cv = {:.2f} kW**".format(pot_cv, pot_kw)],
    ]
    if pot_escolhida_cv is not None:
        atende = pot_escolhida_cv >= pot_cv - 1e-6
        linhas_bomba.append(
            [u"Potência adotada",
             u"**{:.2f} cv = {:.2f} kW**  —  {} {}".format(
                 pot_escolhida_cv, pot_escolhida_kw,
                 SIM_OK if atende else SIM_X,
                 u"atende a mínima" if atende else u"ABAIXO da mínima calculada")])
    janela.tabela([u"Parâmetro", u"Valor"], linhas_bomba, alinhas=[u"left", u"left"])

    janela.paragrafo(u"Para o memorial de cálculo completo (passo a passo), "
                     u"execute \"Memorial de Cálculo\".")

    janela.ShowDialog()


def mostrar_bloqueio_velocidade(nome_trecho, j, limite, falhas):
    """Janela mostrando quais diâmetros do trecho passaram do limite de
    velocidade — chamada por "Dimensionar Hidrantes" quando o
    dimensionamento é interrompido nessa verificação."""
    janela = _JanelaResultado(
        titulo=u"Verificação não atendida",
        subtitulo=u"Velocidade acima do limite — {}".format(nome_trecho),
        status=u"erro",
    )
    janela.paragrafo(u"Vazão do trecho: {:.2f} L/min. Limite normativo: {:.1f} m/s.".format(
        j["Q_lmin"], limite))
    janela.tabela([u"DN (mm)", u"V (m/s)", u"Limite (m/s)"],
                  [[u"{:.1f}".format(s["d_mm"]), u"**{:.3f}**".format(s["V"]),
                    u"{:.1f}".format(limite)] for s in falhas])
    janela.paragrafo(
        u"Correção necessária: aumente o diâmetro nominal do(s) tubo(s) acima nesse "
        u"trecho (ou reduza a vazão, se possível) até a velocidade ficar dentro do "
        u"limite normativo. Ajuste o traçado no Revit e execute \"Dimensionar "
        u"Hidrantes\" novamente.")
    janela.ShowDialog()


def mostrar_bloqueio_hidrante(label, p, q, p_ref_desc, trecho_desc, Pmin, Qs_lmin):
    """Janela mostrando por que a pressão/vazão de um hidrante mais
    desfavorável não atendeu a norma — chamada por "Dimensionar Hidrantes"
    quando o dimensionamento é interrompido nessa verificação."""
    janela = _JanelaResultado(
        titulo=u"Verificação não atendida",
        subtitulo=u"{} não atende a norma".format(label),
        status=u"erro",
    )
    janela.tabela([u"Grandeza", u"Obtido", u"Mínimo exigido"],
                  [[p_ref_desc[0].upper() + p_ref_desc[1:],
                    u"**{:.4f} mca**".format(p), u"{:.4f} mca".format(Pmin)],
                   [u"Vazão", u"**{:.2f} L/min**".format(q), u"{:.2f} L/min".format(Qs_lmin)]],
                  alinhas=[u"left", u"right", u"right"])
    janela.paragrafo(
        u"Correção necessária: revise o diâmetro/traçado do trecho {} — perda de carga "
        u"ou desnível elevados estão reduzindo a pressão disponível abaixo do mínimo "
        u"exigido pela norma. Ajuste no Revit e execute \"Dimensionar Hidrantes\" "
        u"novamente.".format(trecho_desc))
    janela.ShowDialog()
