# -*- coding: utf-8 -*-
"""
linha_limite_core.py — Fire Utils · lib/
Lógica de "Inserir Linha com Limite" — painel WPF MODELESS (Show(), não
ShowDialog()) com duas etapas:

  1. Configuração: usuário escolhe o estilo de linha e o comprimento
     máximo do trecho (em metros).
  2. Acompanhamento: ao confirmar, a ferramenta nativa "Linha de Detalhe"
     do Revit já é ativada automaticamente (via PostCommand — ver
     _iniciar_ferramenta_linha), então o usuário só precisa clicar os
     pontos, sem ir até a faixa de opções. O painel fica aberto, SEM
     bloquear a view do Revit, acompanhando o comprimento total do
     trecho em tempo real, comparado ao limite configurado. Três botões:
     "Cancelar" (desfaz tudo o que foi desenhado desde o OK), "Finalizar"
     (só para de acompanhar, mantém o que foi desenhado) e "Finalizar e
     Limitar" (se o total passou do limite, encurta/remove o(s)
     último(s) trecho(s) até fechar exatamente no valor configurado).

Acompanhamento ao vivo via Application.DocumentChanged — o painel nunca
roda seu próprio loop de cliques (PickPoint): ele só OBSERVA o que o
Revit cria quando o usuário usa a ferramenta padrão, somando o
comprimento de cada novo elemento de linha (Detail Line ou Model Line)
cujo estilo bata com o escolhido na etapa 1. Ler propriedades dentro do
evento DocumentChanged é sempre permitido; é proibido abrir transação
nesse contexto — por isso a leitura/soma do comprimento acontece direto
no handler, e qualquer ação que precise ESCREVER no documento (Cancelar/
Finalizar e Limitar) é despachada por ExternalEvent (mesmo padrão de
hidrantes/fila_acoes.py e family_loader_events.py: cada feature cria sua
própria fila, pra não acoplar uma à outra).

Por ser MODELESS, qualquer clique nos botões do painel acontece FORA do
contexto de API válido do Revit — toda ação que toca o documento
(apagar/encurtar elementos) é enfileirada e só roda quando o Revit libera
o contexto via ExternalEvent, nunca chamada direto do evento de clique
(mesmo motivo documentado em connect_shelter_core_preview.py).
"""

import clr
clr.AddReference(u"RevitAPIUI")
clr.AddReference(u"PresentationFramework")
clr.AddReference(u"PresentationCore")
clr.AddReference(u"WindowsBase")

from System.Windows import Visibility
from System.Windows.Controls import ComboBoxItem

from Autodesk.Revit.DB import (
    Line, Transaction, UnitUtils, BuiltInCategory, GraphicsStyleType,
    CurveElement, ElementId,
)
from Autodesk.Revit.UI import (
    IExternalEventHandler, ExternalEvent, PostableCommand, RevitCommandId,
)

from pyrevit import forms, script as pyscript

import os

_XAML_PATH = os.path.join(os.path.dirname(__file__), u"linha_limite_painel.xaml")

try:
    from Autodesk.Revit.DB import UnitTypeId

    def _metros_para_interno(valor):
        return UnitUtils.ConvertToInternalUnits(valor, UnitTypeId.Meters)

    def _interno_para_metros(valor):
        return UnitUtils.ConvertFromInternalUnits(valor, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType

    def _metros_para_interno(valor):
        return UnitUtils.ConvertToInternalUnits(valor, DisplayUnitType.DUT_METERS)

    def _interno_para_metros(valor):
        return UnitUtils.ConvertFromInternalUnits(valor, DisplayUnitType.DUT_METERS)


def _fmt_m(valor_m):
    return u"{:.2f}".format(valor_m).replace(u".", u",") + u" m"


def listar_estilos_de_linha(doc):
    """{nome: GraphicsStyle} de cada Estilo de Linha do projeto."""
    categoria_linhas = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    estilos = {}
    for subcategoria in categoria_linhas.SubCategories:
        estilo = subcategoria.GetGraphicsStyle(GraphicsStyleType.Projection)
        if estilo is not None:
            estilos[subcategoria.Name] = estilo
    return estilos


# ===========================================================================
# ExternalEvent — fila de ações que precisam do contexto de API, despachadas
# a partir dos cliques (fora de contexto) do painel modeless. Cópia própria
# do mesmo padrão de hidrantes/fila_acoes.py — ver docstring do módulo.
# ===========================================================================

class _FilaAcoesHandler(IExternalEventHandler):

    def __init__(self):
        self._fila = []
        self.evento = None  # atribuído por criar_fila_acoes() logo após a criação

    def enfileirar(self, funcao):
        self._fila.append(funcao)
        if self.evento is not None:
            self.evento.Raise()

    def Execute(self, uiapp):
        """Chamado pelo Revit — nunca deve ser chamado diretamente."""
        if not self._fila:
            return
        funcao = self._fila.pop(0)
        try:
            funcao(uiapp)
        except Exception as ex:
            print(u"[AVISO] Ação da fila de Linha com Limite falhou: {}".format(ex))
        finally:
            if self._fila:
                self.evento.Raise()

    def GetName(self):
        return u"FireUtils_LinhaComLimite_ExternalEvent"


def criar_fila_acoes():
    handler = _FilaAcoesHandler()
    handler.evento = ExternalEvent.Create(handler)
    return handler


# ===========================================================================
# Janela — painel de configuração + acompanhamento ao vivo
# ===========================================================================

_CHAVE_JANELA_ATIVA = u"FireUtils_LinhaComLimite_JanelaAtiva"


class _JanelaLimite(forms.WPFWindow):

    def __init__(self, doc, uidoc, estilos):
        forms.WPFWindow.__init__(self, _XAML_PATH)
        self.doc = doc
        self.uidoc = uidoc
        self._estilos = estilos            # {nome: GraphicsStyle}
        self._estilo_atual = None
        self._limite_interno = 0.0
        self._app = None                   # Application, atribuído por _assinar_mudancas
        self._itens = []                   # [(ElementId.IntegerValue, comprimento_interno), ...] em ordem de criação
        self._processados = set()          # IntegerValue já somados, pra não contar o mesmo elemento 2x
        self._finalizado = False
        self.fila_acoes = criar_fila_acoes()

        for nome in sorted(estilos.keys()):
            item = ComboBoxItem()
            item.Content = nome
            self.CmbEstilo.Items.Add(item)
        if self.CmbEstilo.Items.Count:
            self.CmbEstilo.SelectedIndex = 0

    # ------------------------------------------------------------------
    # Etapa 1 — configuração
    # ------------------------------------------------------------------
    def on_cancelar_config(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        item_selecionado = self.CmbEstilo.SelectedItem
        if item_selecionado is None:
            self.TxtErroConfig.Text = u"Escolha um estilo de linha."
            return

        try:
            comprimento_m = float(u"{}".format(self.TxtComprimentoMax.Text).replace(u",", u"."))
        except ValueError:
            comprimento_m = -1
        if comprimento_m <= 0:
            self.TxtErroConfig.Text = u"Informe um comprimento máximo válido (maior que zero)."
            return

        self._estilo_atual = self._estilos[u"{}".format(item_selecionado.Content)]
        self._limite_interno = _metros_para_interno(comprimento_m)

        self.TxtLimiteValor.Text = _fmt_m(comprimento_m)
        self.TxtComprimentoAtual.Text = _fmt_m(0.0)
        self.PainelConfig.Visibility = Visibility.Collapsed
        self.PainelRastreio.Visibility = Visibility.Visible

        self.fila_acoes.enfileirar(self._assinar_mudancas)

    # ------------------------------------------------------------------
    # Etapa 2 — acompanhamento ao vivo (DocumentChanged só LÊ, nunca escreve)
    # ------------------------------------------------------------------
    def _assinar_mudancas(self, uiapp):
        self._app = uiapp.Application
        self._app.DocumentChanged += self._ao_documento_mudar
        self._iniciar_ferramenta_linha(uiapp)

    def _iniciar_ferramenta_linha(self, uiapp):
        """Ativa a ferramenta nativa "Linha de Detalhe" do Revit assim que
        o usuário confirma a configuração — ele não precisa ir até a faixa
        de opções manualmente, só clicar os pontos. PostCommand é o jeito
        correto de disparar um comando nativo a partir de um complemento
        (não dá pra chamar o comando direto); funciona bem de dentro do
        Execute() do ExternalEvent, mesmo padrão usado pras demais ações
        que tocam a UI/documento neste módulo."""
        try:
            cmd_id = RevitCommandId.LookupPostableCommandId(PostableCommand.DetailLine)
            if uiapp.CanPostCommand(cmd_id):
                uiapp.PostCommand(cmd_id)
        except Exception as ex:
            print(u"[AVISO] Não foi possível iniciar a ferramenta Linha de "
                  u"Detalhe automaticamente: {}".format(ex))

    def _ao_documento_mudar(self, sender, args):
        try:
            if not args.GetDocument().Equals(self.doc):
                return
        except Exception:
            pass

        mudou = False

        for eid in args.GetDeletedElementIds():
            chave = eid.IntegerValue
            if chave in self._processados:
                self._processados.discard(chave)
                self._itens = [item for item in self._itens if item[0] != chave]
                mudou = True

        for eid in args.GetAddedElementIds():
            chave = eid.IntegerValue
            if chave in self._processados:
                continue
            elemento = self.doc.GetElement(eid)
            if not isinstance(elemento, CurveElement):
                continue
            try:
                estilo = elemento.LineStyle
            except Exception:
                continue
            if estilo is None or self._estilo_atual is None:
                continue
            if estilo.Id.IntegerValue != self._estilo_atual.Id.IntegerValue:
                continue
            try:
                comprimento = elemento.Location.Curve.Length
            except Exception:
                continue
            self._processados.add(chave)
            self._itens.append((chave, comprimento))
            mudou = True

        if mudou:
            self._atualizar_total()

    def _atualizar_total(self):
        total_interno = sum(c for _, c in self._itens)
        self.TxtComprimentoAtual.Text = _fmt_m(_interno_para_metros(total_interno))
        if total_interno > self._limite_interno + 1e-6:
            self.TxtComprimentoAtual.Foreground = self.Resources[u"BrushWarn"]
        else:
            self.TxtComprimentoAtual.Foreground = self.Resources[u"BrushValor"]

    # ------------------------------------------------------------------
    # Botões finais — SEMPRE enfileirados (contexto de API inválido num
    # clique de janela modeless), nunca chamados direto daqui.
    # ------------------------------------------------------------------
    def on_cancelar_rastreio(self, sender, args):
        self._finalizado = True
        self.fila_acoes.enfileirar(self._acao_cancelar)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        self.Close()

    def on_finalizar(self, sender, args):
        self._finalizado = True
        self.fila_acoes.enfileirar(self._acao_finalizar)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        self.Close()

    def on_finalizar_limitar(self, sender, args):
        self._finalizado = True
        self.fila_acoes.enfileirar(self._acao_finalizar_limitar)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        self.Close()

    def on_closing(self, sender, args):
        """Fechou pelo X (ou outro caminho) sem passar por nenhum botão —
        mesmo comportamento de "Finalizar": só para de acompanhar, sem
        apagar nem encurtar nada."""
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        if self._finalizado:
            return
        self._finalizado = True
        self.fila_acoes.enfileirar(self._acao_finalizar)

    # ------------------------------------------------------------------
    # Ações no documento — rodam via ExternalEvent, dentro de contexto de
    # API válido.
    # ------------------------------------------------------------------
    def _desinscrever(self):
        if self._app is not None:
            try:
                self._app.DocumentChanged -= self._ao_documento_mudar
            except Exception:
                pass
            self._app = None

    def _acao_finalizar(self, uiapp):
        self._desinscrever()

    def _acao_cancelar(self, uiapp):
        self._desinscrever()
        if not self._itens:
            return
        with Transaction(self.doc, u"Fire Utils - Cancelar Linha com Limite") as t:
            t.Start()
            for chave, _ in self._itens:
                try:
                    self.doc.Delete(ElementId(chave))
                except Exception:
                    pass
            t.Commit()
        self._itens = []
        self._processados = set()

    def _acao_finalizar_limitar(self, uiapp):
        self._desinscrever()
        itens = list(self._itens)
        excedente = sum(c for _, c in itens) - self._limite_interno
        if excedente <= 1e-6 or not itens:
            return

        with Transaction(self.doc, u"Fire Utils - Finalizar e Limitar") as t:
            t.Start()
            while itens and excedente > 1e-6:
                chave, comprimento = itens.pop()
                if comprimento <= excedente + 1e-6:
                    # Trecho inteiro cabe dentro do excedente — remove
                    # por completo e segue encurtando/removendo os
                    # trechos anteriores até zerar o excedente.
                    try:
                        self.doc.Delete(ElementId(chave))
                    except Exception:
                        pass
                    excedente -= comprimento
                else:
                    # Encurta ESTE trecho (o último que ainda sobra)
                    # pra fechar exatamente no limite — ponto inicial
                    # fixo, ponto final recalculado na mesma direção.
                    elemento = self.doc.GetElement(ElementId(chave))
                    if elemento is None:
                        continue
                    curva = elemento.Location.Curve
                    p0 = curva.GetEndPoint(0)
                    p1 = curva.GetEndPoint(1)
                    direcao = (p1 - p0).Normalize()
                    novo_comprimento = comprimento - excedente
                    elemento.Location.Curve = Line.CreateBound(
                        p0, p0 + direcao.Multiply(novo_comprimento)
                    )
                    excedente = 0.0
            t.Commit()
        self._itens = []
        self._processados = set()


# ===========================================================================
# PONTO DE ENTRADA
# ===========================================================================

def abrir_painel_linha_com_limite(doc, uidoc):
    # Painel é modeless (Show, não ShowDialog) — nada impede o usuário de
    # chamar o comando de novo com o painel anterior ainda aberto; só traz
    # o existente pra frente em vez de abrir outro (evita duas filas de
    # ExternalEvent/dois rastreamentos disputando o mesmo documento).
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_ATIVA)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)

    estilos = listar_estilos_de_linha(doc)
    if not estilos:
        forms.alert(u"Nenhum estilo de linha encontrado no projeto.", exitscript=True)
        return

    janela = _JanelaLimite(doc, uidoc, estilos)
    pyscript.set_envvar(_CHAVE_JANELA_ATIVA, janela)
    janela.Show()
