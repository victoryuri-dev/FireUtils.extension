# -*- coding: utf-8 -*-
"""
connect_shelter_core_preview.py — Fire Utils · lib/

Conecta um abrigo de hidrante existente à rede de tubulação: cria uma
válvula + stub saindo do abrigo e roteia até o tubo de referência — com
PRÉVIA AO VIVO no modelo, no mesmo padrão de connect_pipe.py.

Fluxo de cliques
----------------
  1. Selecionar o abrigo de referência
  2. Clicar no tubo de referência — corpo → Tê  |  ponta → joelhos em L
  3. Janela WPF (connect_shelter_opcoes.xaml, classe _JanelaOpcoesAbrigo)
     pergunta:
       • lado do ramal (esquerda/direita da face do abrigo)
       • onde conectar em pipe_ref (corpo/ponta)
       • ordem dos até 3 trechos retos da rota (Vertical/Z, Paralelo e
         Perpendicular ao eixo de pipe_ref) — livre, só com os eixos que
         realmente precisam de ajuste (ver connect_pipe._eixos_disponiveis)
     A cada troca de opção, válvula + stub + roteamento são reconstruídos
     no modelo — cada troca roda sua própria transação, aberta e já
     comitada no mesmo ciclo (ver docstring de _JanelaOpcoesAbrigo).
     Cancelar ou fechar a janela desfaz TUDO (inclusive a válvula e o
     stub, que antes desta versão ficavam aplicados no projeto mesmo se o
     usuário desistisse da conexão — só desfazendo manualmente).
     Se essa janela falhar por qualquer motivo, cai para forms.SelectFromList
     + fluxo direto sem prévia (_escolher_opcoes_abrigo_fallback).

Tipo e sistema de tubulação do stub — e por herança, de qualquer segmento
criado pelo roteamento — são SEMPRE os do tubo de referência (pipe_ref),
lido antes de criar qualquer coisa (_pipe_params, de connect_pipe.py).
Diâmetro do stub continua fixo em DIAM_RAMAL_M (regra própria do ramal de
hidrante, independente do diâmetro de pipe_ref).

Todo o roteamento entre o stub e o tubo de referência é delegado a
connect_pipe._construir_conexao, para que melhorias futuras no algoritmo
de roteamento beneficiem este botão automaticamente.

Nível obtido diretamente do abrigo — sem prompt ao usuário.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import os
import math

import System.Windows as SW

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, UnitUtils,
    ElementTransformUtils, FamilyInstance,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

from hydrant_family      import garantir_valvula
from shelter_family      import NOME_FAMILIA_ABRIGO
from hydrant_insert_core import (
    ALTURA_VALVULA_M, COMP_HORIZ_M, DIAM_RAMAL_M, TOL,
    _angulo_entre, _conector_mais_proximo, _setar_diametro_ft,
)
from connect_pipe import (
    _construir_conexao, _ConexaoError, _FiltroPipe, _pipe_params, TOL_SEG,
    _eixos_necessarios, _preparar_alvo_nominal, _NOME_EIXO, _snapshot_ids,
)
from family_loader_events import criar_fila_acoes

_XAML_OPCOES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"connect_shelter_opcoes.xaml")


# ===========================================================================
# FILTRO — abrigo de hidrante
# ===========================================================================

class _FiltroAbrigo(ISelectionFilter):
    def AllowElement(self, e):
        if isinstance(e, FamilyInstance):
            try:
                return e.Symbol.Family.Name == NOME_FAMILIA_ABRIGO
            except Exception:
                pass
        return False
    def AllowReference(self, r, p): return True


# ===========================================================================
# HELPER — direção esquerda/direita a partir da face do abrigo
# ===========================================================================

def _direcao_lado(dir_face, lado):
    """dir_face: XYZ (normal da face do abrigo, plano horizontal).
    lado: "esquerda" ou "direita". Retorna XYZ unitário perpendicular a
    dir_face, no sentido escolhido."""
    if lado == u"esquerda":
        return XYZ(dir_face.Y, -dir_face.X, 0.0)   # 90° CW da face
    return XYZ(-dir_face.Y, dir_face.X, 0.0)        # 90° CCW da face (direita)


def _pt_stub_end(pt_abrigo, nivel, dir_face, lado):
    """Ponta livre do stub, calculada geometricamente (sem criar nada) —
    mesma fórmula usada dentro de _construir_valvula_stub_e_rota. Usada
    pra saber quais eixos precisam de ajuste antes mesmo de o tubo/válvula
    existirem de verdade (ver _eixos_disponiveis_abrigo)."""
    dir_pipe = _direcao_lado(dir_face, lado)
    z_val    = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)
    comp_ft  = _to_ft(COMP_HORIZ_M)
    pt_valvula = XYZ(
        pt_abrigo.X + _to_ft(0.18) * dir_pipe.X - _to_ft(0.085) * dir_face.X,
        pt_abrigo.Y + _to_ft(0.18) * dir_pipe.Y - _to_ft(0.085) * dir_face.Y,
        z_val,
    )
    return XYZ(
        pt_valvula.X + dir_pipe.X * comp_ft,
        pt_valvula.Y + dir_pipe.Y * comp_ft,
        z_val,
    )


def _eixos_disponiveis_abrigo(pipe_ref, pt_click_ref, pt_abrigo, nivel, dir_face,
                               lado, modo_conexao_ref):
    """
    Quais dos eixos (z/par/perp) precisam de ajuste pra ir do stub (ainda
    nem criado — só calculado geometricamente) até o alvo em pipe_ref.
    Espelha connect_pipe._eixos_disponiveis, mas sem precisar de um
    elemento Pipe real pro lado do stub. Nunca levanta exceção — se não
    conseguir decidir, libera os 3 eixos; o erro de verdade aparece
    depois, quando a rota for construída pra valer.
    """
    P_start = _pt_stub_end(pt_abrigo, nivel, dir_face, lado)
    try:
        P_final, d_ref = _preparar_alvo_nominal(pipe_ref, pt_click_ref, modo_conexao_ref)
    except _ConexaoError:
        return [u"z", u"par", u"perp"]
    return _eixos_necessarios(P_start, P_final, d_ref)


# ===========================================================================
# LÓGICA DE CONSTRUÇÃO — válvula + stub + roteamento
# ===========================================================================

def _construir_valvula_stub_e_rota(doc, pipe_ref, pt_click_ref, simbolo,
                                    pt_abrigo, nivel, dir_face,
                                    pipe_type_id, sys_type_id, output,
                                    lado=u"direita",
                                    ordem_eixos=(u"z", u"par", u"perp"),
                                    modo_conexao_ref=u"corpo"):
    """
    Cria a válvula + stub no lado escolhido e roteia até pipe_ref. NÃO abre
    nem fecha transação — quem chama decide (janela de prévia ou o fluxo
    direto de fallback). Propaga _ConexaoError nas validações conhecidas de
    connect_pipe._construir_conexao; erros inesperados propagam como
    Exception normal.
    """
    dir_pipe = _direcao_lado(dir_face, lado)

    z_val   = nivel.Elevation + _to_ft(ALTURA_VALVULA_M)
    comp_ft = _to_ft(COMP_HORIZ_M)
    diam_ft = _to_ft(DIAM_RAMAL_M)

    # Posição da válvula: inverso do offset de _calcular_pt_abrigo.
    # No fluxo original: pt_abrigo = pt_valvula + 0.18·dir_saida − 0.085·dir_face
    # Aqui dir_pipe = −dir_saida (aponta de válvula→rede), logo:
    #   pt_valvula = pt_abrigo + 0.18·dir_pipe + 0.085·dir_face
    pt_valvula = XYZ(
        pt_abrigo.X + _to_ft(0.18) * dir_pipe.X - _to_ft(0.085) * dir_face.X,
        pt_abrigo.Y + _to_ft(0.18) * dir_pipe.Y - _to_ft(0.085) * dir_face.Y,
        z_val,
    )
    pt_stub_end = XYZ(
        pt_valvula.X + dir_pipe.X * comp_ft,
        pt_valvula.Y + dir_pipe.Y * comp_ft,
        z_val,
    )

    tubo_stub = Pipe.Create(doc, sys_type_id, pipe_type_id, nivel.Id, pt_valvula, pt_stub_end)
    _setar_diametro_ft(tubo_stub, diam_ft)

    valvula = doc.Create.NewFamilyInstance(
        pt_valvula, simbolo, nivel, StructuralType.NonStructural
    )

    # Rotação: + π porque dir_pipe aponta para a rede;
    # a face da válvula fica voltada para o lado do abrigo
    angulo = _angulo_entre(XYZ(1.0, 0.0, 0.0), dir_pipe) + math.pi
    if abs(angulo) > TOL:
        eixo = Line.CreateBound(
            pt_valvula, XYZ(pt_valvula.X, pt_valvula.Y, pt_valvula.Z + 1.0)
        )
        ElementTransformUtils.RotateElement(doc, valvula.Id, eixo, angulo)

    doc.Regenerate()

    # Conectar válvula ao conector próximo do stub em pt_valvula
    best_d, conn_stub_val = float('inf'), None
    for c in tubo_stub.ConnectorManager.Connectors:
        d = c.Origin.DistanceTo(pt_valvula)
        if d < best_d:
            best_d, conn_stub_val = d, c

    if conn_stub_val:
        conn_val = _conector_mais_proximo(valvula, pt_valvula)
        if conn_val:
            desl = conn_stub_val.Origin - conn_val.Origin
            if desl.GetLength() > TOL:
                ElementTransformUtils.MoveElement(doc, valvula.Id, desl)
            try:
                conn_stub_val.ConnectTo(conn_val)
            except Exception:
                pass

    doc.Regenerate()

    # ── Roteamento delegado a connect_pipe ───────────────────────────────
    # pt_stub_end identifica a ponta livre do stub; modo_conexao_ref
    # decide corpo (Tê) vs ponta (joelho) de pipe_ref — escolha explícita
    # do usuário no diálogo, não mais adivinhada pela distância do clique.
    _construir_conexao(doc, tubo_stub, pipe_ref, pt_stub_end, pt_click_ref,
                        output, ordem_eixos=ordem_eixos,
                        modo_conexao_ref=modo_conexao_ref)


# ===========================================================================
# FORM — preferências de conexão (lado do ramal + altura), com prévia
# ===========================================================================

class _JanelaOpcoesAbrigo(forms.WPFWindow):
    """Janela WPF MODELESS (connect_shelter_opcoes.xaml) com PRÉVIA AO VIVO:
    a cada troca de opção (lado do ramal / onde conectar / ordem dos
    eixos), válvula + stub + roteamento são reconstruídos no modelo para o
    usuário ver o resultado antes de confirmar.

    Cada troca roda um ciclo completo (_ciclo_preview) que abre E FECHA
    (Commit) sua PRÓPRIA transação — o Revit não permite deixar uma
    transação "pendurada" entre uma troca de opção e a próxima (reclama de
    "transação aberta mas não fechada" assim que o comando externo que a
    abriu retorna), diferente de uma janela modal onde a mesma transação
    podia ficar aberta do início ao fim. Por isso não existe mais
    RollBack/Commit de uma transação única: cada ciclo primeiro DESFAZ
    manualmente o que o ciclo anterior criou (válvula + stub + roteamento
    — tudo criado do zero a cada ciclo, nunca pré-existente) e restaura a
    curva original de pipe_ref (guardada no __init__, já que o Tê do modo
    "corpo" quebra a curva em dois). "Cancelar" ou fechar sem confirmar
    roda esse mesmo desfazer uma última vez; "OK" não precisa fazer nada
    no documento — o que já está comitado da última prévia bem sucedida
    já É o resultado final.

    Por ser modeless (Show(), não ShowDialog() — ver conectar_abrigo_preview),
    o Revit continua respondendo normalmente: dá pra orbitar, aproximar/
    afastar e girar a câmera no modelo com a janela aberta. Em
    compensação, qualquer clique nela acontece FORA do contexto de API
    válido do Revit — toda ação que toca o documento (self.fila_acoes, de
    family_loader_events.criar_fila_acoes) é enfileirada e executada assim
    que o Revit libera o contexto via ExternalEvent, nunca chamada direto
    do evento de clique.

    Ordem dos eixos: mesmo mecanismo de connect_pipe._JanelaOpcoesRota —
    até 3 trechos retos (z/par/perp), só os necessários aparecem como
    opção, ordem livre escolhida pelo usuário."""

    _BOTOES_ORDEM1 = {u"z": u"RbO1Z", u"par": u"RbO1Par", u"perp": u"RbO1Perp"}
    _BOTOES_ORDEM2 = {u"z": u"RbO2Z", u"par": u"RbO2Par", u"perp": u"RbO2Perp"}

    def __init__(self, doc, uidoc, pipe_ref, pt_click_ref, simbolo,
                 pt_abrigo, nivel, dir_face, pipe_type_id, sys_type_id, output,
                 clicou_ponta_exata=False):
        forms.WPFWindow.__init__(self, _XAML_OPCOES_PATH)
        self.doc           = doc
        self.uidoc         = uidoc
        self.pipe_ref      = pipe_ref
        self.pt_click_ref  = pt_click_ref
        self.simbolo       = simbolo
        self.pt_abrigo     = pt_abrigo
        self.nivel         = nivel
        self.dir_face      = dir_face
        self.pipe_type_id  = pipe_type_id
        self.sys_type_id   = sys_type_id
        self.output        = output

        self.confirmado        = False
        self._preview_ok       = False
        self._finalizado       = False
        self._sincronizando    = False
        self._ordem_pref       = [u"z", u"par", u"perp"]
        self._elementos_criados = set()
        self.fila_acoes        = criar_fila_acoes()

        # Estado original de pipe_ref (antes de qualquer prévia) — cada
        # ciclo restaura isso antes de construir a prévia nova, já que o
        # modo "corpo" quebra essa curva num Tê.
        loc_ref = pipe_ref.Location.Curve
        self._p0_ref_orig = loc_ref.GetEndPoint(0)
        self._p1_ref_orig = loc_ref.GetEndPoint(1)

        # Se o clique já caiu exatamente na ponta de pipe_ref, a resposta
        # já é óbvia (ponta) — esconde a pergunta e força a opção, em vez
        # de fazer o usuário confirmar algo que ele já decidiu com o clique.
        if clicou_ponta_exata:
            self.SecaoRef.Visibility = SW.Visibility.Collapsed

        # Marcado com _sincronizando=True: IsChecked dispara o evento
        # Checked já aqui, de forma síncrona (mesmo com a janela ainda não
        # exibida), e on_opcao_changed enfileiraria uma rodada extra de
        # _ciclo_preview via ExternalEvent — redundante (a prévia real já
        # roda logo abaixo, direto) e é a causa do aviso "ExternalEvent ...
        # retornou 'Pending'" (um 2º/3º Raise() emendado no 1º antes do
        # Revit sequer ter devolvido o contexto de API pro fim do
        # __init__).
        self._sincronizando = True
        try:
            if clicou_ponta_exata:
                self.RbRefPonta.IsChecked = True
            else:
                self.RbRefCorpo.IsChecked = True
            self.RbLadoDireita.IsChecked = True
        finally:
            self._sincronizando = False

        try:
            self._ciclo_preview()
        except Exception:
            # _ciclo_preview já trata os erros esperados internamente (e
            # sempre fecha a própria transação, mesmo em erro); isto é só
            # uma rede de segurança pra desfazer qualquer coisa que tenha
            # escapado antes de propagar, o que travaria o fallback (uma
            # transação por vez no documento).
            self._finalizar(False)
            raise

    def _desfazer_elementos_criados(self):
        for eid in self._elementos_criados:
            try:
                self.doc.Delete(eid)
            except Exception:
                pass
        self._elementos_criados = set()

    def _restaurar_curva_original(self):
        try:
            self.pipe_ref.Location.Curve = Line.CreateBound(self._p0_ref_orig, self._p1_ref_orig)
        except Exception:
            pass

    def _finalizar(self, confirmado):
        """Fecha a prévia de vez: se confirmado, não mexe em nada — o que
        já está comitado no documento (da última prévia bem sucedida) já É
        o resultado final. Senão, desfaz tudo numa transação própria,
        aberta e fechada aqui mesmo. Chamado tanto de dentro da fila de
        ações (fechar a janela modeless) quanto direto, já num contexto de
        API válido (ex.: __init__/conectar_abrigo_preview(), se algo falhar
        antes da janela aparecer de verdade)."""
        if confirmado:
            return
        t = Transaction(self.doc, u"FireUtils - Conectar Abrigo (descartar prévia)")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self._restaurar_curva_original()
        finally:
            # Sempre fecha a transação antes de sair daqui — nunca pode
            # ficar aberta, nem em erro inesperado (ver _snapshot_ids).
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass

    def _lado_atual(self):
        return u"esquerda" if self.RbLadoEsquerda.IsChecked else u"direita"

    def _modo_conexao_ref_atual(self):
        return u"ponta" if self.RbRefPonta.IsChecked else u"corpo"

    def _ordem1_atual(self):
        for eixo, nome_btn in self._BOTOES_ORDEM1.items():
            if getattr(self, nome_btn).IsChecked:
                return eixo
        return None

    def _ordem2_atual(self):
        for eixo, nome_btn in self._BOTOES_ORDEM2.items():
            if getattr(self, nome_btn).IsChecked:
                return eixo
        return None

    def _sincronizar_ordem(self):
        """Recalcula quais eixos ainda precisam de ajuste (dado o lado e o
        modo de conexão atuais) e mostra só os botões cabíveis em "1º
        eixo"/"2º eixo" — o resto (0 ou 1 eixo necessário) não precisa de
        escolha nenhuma, então a seção some. Preserva ao máximo a
        preferência já escolhida pelo usuário (self._ordem_pref)."""
        necessarios = _eixos_disponiveis_abrigo(
            self.pipe_ref, self.pt_click_ref, self.pt_abrigo, self.nivel,
            self.dir_face, self._lado_atual(), self._modo_conexao_ref_atual())

        ordem = [e for e in self._ordem_pref if e in necessarios]
        for e in necessarios:
            if e not in ordem:
                ordem.append(e)
        self._ordem_pref = ordem

        n = len(ordem)
        self._sincronizando = True
        try:
            self.SecaoOrdem.Visibility = (SW.Visibility.Visible if n >= 1
                                           else SW.Visibility.Collapsed)

            mostrar1 = SW.Visibility.Visible if n >= 2 else SW.Visibility.Collapsed
            self.LinhaOrdem1.Visibility = mostrar1
            self.LblOrdem1.Visibility   = mostrar1
            if n >= 2:
                for eixo, nome_btn in self._BOTOES_ORDEM1.items():
                    getattr(self, nome_btn).Visibility = (
                        SW.Visibility.Visible if eixo in ordem else SW.Visibility.Collapsed)
                getattr(self, self._BOTOES_ORDEM1[ordem[0]]).IsChecked = True

            mostrar2 = SW.Visibility.Visible if n >= 3 else SW.Visibility.Collapsed
            self.LinhaOrdem2.Visibility = mostrar2
            self.LblOrdem2.Visibility   = mostrar2
            if n >= 3:
                restantes = ordem[1:]
                for eixo, nome_btn in self._BOTOES_ORDEM2.items():
                    getattr(self, nome_btn).Visibility = (
                        SW.Visibility.Visible if eixo in restantes else SW.Visibility.Collapsed)
                getattr(self, self._BOTOES_ORDEM2[ordem[1]]).IsChecked = True

            if n == 0:
                self.TxtOrdemInfo.Text = u""
            elif n == 1:
                self.TxtOrdemInfo.Text = u"Único ajuste necessário: {}".format(_NOME_EIXO[ordem[0]])
            else:
                self.TxtOrdemInfo.Text = u"Por último: {}".format(_NOME_EIXO[ordem[-1]])
        finally:
            self._sincronizando = False

    def _ciclo_preview(self):
        """Um ciclo completo de prévia, numa transação própria aberta E
        fechada aqui mesmo (nunca deixada pendurada — ver docstring da
        classe): desfaz o que o ciclo anterior criou/mudou, sincroniza as
        opções de ordem disponíveis e reconstrói válvula + stub + rota com
        as opções atuais. Em erro de validação/inesperado, desfaz de novo
        (deixa o modelo em branco, sem a prévia) e mostra o aviso em
        TxtStatus."""
        t = Transaction(self.doc, u"FireUtils - Conectar Abrigo")
        t.Start()
        try:
            self._desfazer_elementos_criados()
            self._restaurar_curva_original()
            self.doc.Regenerate()
            self._sincronizar_ordem()

            ids_antes = _snapshot_ids(self.doc)
            erro = None
            try:
                _construir_valvula_stub_e_rota(
                    self.doc, self.pipe_ref, self.pt_click_ref, self.simbolo,
                    self.pt_abrigo, self.nivel, self.dir_face,
                    self.pipe_type_id, self.sys_type_id, self.output,
                    lado=self._lado_atual(), ordem_eixos=self._ordem_pref,
                    modo_conexao_ref=self._modo_conexao_ref_atual(),
                )
                self.doc.Regenerate()
            except _ConexaoError as ex:
                erro = u"{}".format(ex)
            except Exception as ex:
                erro = u"Erro na prévia: {}".format(ex)
            self._elementos_criados = _snapshot_ids(self.doc) - ids_antes

            if erro is not None:
                self._desfazer_elementos_criados()
                self._restaurar_curva_original()
                self.doc.Regenerate()
                self._preview_ok = False
                self.TxtStatus.Text       = erro
                self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
            else:
                self._preview_ok = True
                self.TxtStatus.Text       = u""
                self.TxtStatus.Foreground = self.Resources[u"BrushOk"]
        finally:
            # Sempre fecha a transação antes de sair daqui — nunca pode
            # ficar aberta, nem em erro inesperado (ver _snapshot_ids).
            try:
                t.Commit()
            except Exception:
                try:
                    t.RollBack()
                except Exception:
                    pass
        try:
            self.uidoc.RefreshActiveView()
        except Exception:
            pass

    def _agendar_atualizacao(self):
        """Pede pro Revit rodar _ciclo_preview assim que liberar o contexto
        de API — toca o documento (transação), então não pode rodar direto
        do evento de clique numa janela modeless."""
        def _acao(uiapp):
            self._ciclo_preview()
        self.fila_acoes.enfileirar(_acao)

    def on_opcao_changed(self, sender, args):
        if self._sincronizando:
            return
        self._agendar_atualizacao()

    def on_ordem1_changed(self, sender, args):
        if self._sincronizando:
            return
        novo = self._ordem1_atual()
        if novo is not None:
            self._ordem_pref = [novo] + [e for e in self._ordem_pref if e != novo]
        self._agendar_atualizacao()

    def on_ordem2_changed(self, sender, args):
        if self._sincronizando:
            return
        novo2 = self._ordem2_atual()
        if novo2 is not None and self._ordem_pref:
            primeiro = self._ordem_pref[0]
            self._ordem_pref = ([primeiro, novo2] +
                                 [e for e in self._ordem_pref if e not in (primeiro, novo2)])
        self._agendar_atualizacao()

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self._preview_ok:
            forms.alert(
                u"Não é possível confirmar com as opções atuais:\n{}".format(self.TxtStatus.Text),
                title=u"Fire Utils", warn_icon=True)
            return
        self.confirmado = True
        self.Close()

    def on_closing(self, sender, args):
        """Sempre finaliza a prévia ao fechar — mantém o resultado comitado
        só se o usuário clicou OK; qualquer outro fechamento desfaz tudo,
        válvula e stub incluídos. Fechar a janela em si (Close/Hide) é só
        WPF, não precisa de contexto de API — mas desfazer toca o
        documento, então vai pra fila de ações em vez de rodar direto aqui."""
        if self._finalizado:
            return
        self._finalizado = True
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        confirmado = self.confirmado

        def _acao(uiapp):
            self._finalizar(confirmado)
        self.fila_acoes.enfileirar(_acao)


def _escolher_opcoes_abrigo_fallback(pipe_ref, pt_click_ref, pt_abrigo, nivel, dir_face,
                                      clicou_ponta_exata=False):
    if clicou_ponta_exata:
        # Clique já caiu exatamente na ponta de pipe_ref — resposta óbvia,
        # pula a pergunta em vez de fazer o usuário confirmar o óbvio.
        modo_conexao_ref = u"ponta"
    else:
        escolha_ref = forms.SelectFromList.show(
            [u"Ponto clicado", u"Ponta livre"],
            title=u"Fire Utils — Conectar Abrigo",
            prompt=u"Onde conectar no tubo de referência?",
            multiselect=False
        )
        if not escolha_ref:
            return None
        modo_conexao_ref = u"ponta" if escolha_ref.startswith(u"Ponta") else u"corpo"

    escolha_lado = forms.SelectFromList.show(
        [u"Esquerda", u"Direita"],
        title=u"Fire Utils — Conectar Abrigo",
        prompt=u"Lado do ramal (a partir da face do abrigo):",
        multiselect=False
    )
    if not escolha_lado:
        return None
    lado = u"esquerda" if escolha_lado == u"Esquerda" else u"direita"

    # Só pergunta a ordem dos eixos que realmente vão existir na rota —
    # um trecho já alinhado num eixo não aparece como escolha.
    necessarios = _eixos_disponiveis_abrigo(pipe_ref, pt_click_ref, pt_abrigo, nivel,
                                             dir_face, lado, modo_conexao_ref)
    ordem_eixos = [u"z", u"par", u"perp"]

    if len(necessarios) >= 2:
        escolha1 = forms.SelectFromList.show(
            [_NOME_EIXO[e] for e in necessarios],
            title=u"Fire Utils — Conectar Abrigo",
            prompt=u"Qual eixo alinhar primeiro?",
            multiselect=False
        )
        if not escolha1:
            return None
        primeiro  = [e for e in necessarios if _NOME_EIXO[e] == escolha1][0]
        restantes = [e for e in necessarios if e != primeiro]

        if len(restantes) >= 2:
            escolha2 = forms.SelectFromList.show(
                [_NOME_EIXO[e] for e in restantes],
                title=u"Fire Utils — Conectar Abrigo",
                prompt=u"E depois?",
                multiselect=False
            )
            if not escolha2:
                return None
            segundo  = [e for e in restantes if _NOME_EIXO[e] == escolha2][0]
            terceiro = [e for e in restantes if e != segundo][0]
            ordem_eixos = [primeiro, segundo, terceiro]
        else:
            ordem_eixos = [primeiro] + restantes

    return lado, ordem_eixos, modo_conexao_ref


# ===========================================================================
# PONTO DE ENTRADA
# ===========================================================================

_CHAVE_JANELA_ATIVA = u"FireUtils_ConectarAbrigo_JanelaAtiva"


def conectar_abrigo_preview(doc, uidoc, output):
    # Janela de prévia é modeless (Show, não ShowDialog) — nada impede o
    # usuário de chamar o comando de novo com a anterior ainda aberta; como
    # o Revit só permite uma transação aberta por documento, uma segunda
    # instância pisaria na transação da primeira. Só traz a existente pra
    # frente em vez de abrir outra.
    janela_ativa = pyscript.get_envvar(_CHAVE_JANELA_ATIVA)
    if janela_ativa is not None:
        try:
            janela_ativa.Activate()
            return
        except Exception:
            pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)

    # ── Família da válvula ───────────────────────────────────────────────
    simbolo, erro = garantir_valvula(doc)
    if erro:
        forms.alert(erro, title=u"Fire Utils – Erro", warn_icon=True)
        pyscript.exit()

    # ── Clique 1: abrigo ────────────────────────────────────────────────
    try:
        ref    = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroAbrigo(),
            u"[1/2] Selecione o abrigo de hidrante"
        )
        abrigo = doc.GetElement(ref.ElementId)
    except Exception:
        pyscript.exit()

    try:
        pt_abrigo = abrigo.Location.Point
    except Exception:
        forms.alert(u"Não foi possível obter a posição do abrigo.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    # Nível lido do próprio abrigo — sem prompt ao usuário
    nivel = doc.GetElement(abrigo.LevelId)
    if nivel is None:
        forms.alert(u"Não foi possível determinar o nível do abrigo.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    try:
        face     = abrigo.FacingOrientation
        dir_face = XYZ(face.X, face.Y, 0.0)
    except Exception:
        dir_face = XYZ(0.0, 1.0, 0.0)

    # ── Clique 2: tubo de referência ─────────────────────────────────────
    try:
        ref_p        = uidoc.Selection.PickObject(
            ObjectType.PointOnElement, _FiltroPipe(doc),
            u"[2/2] Clique no tubo de referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref_p.ElementId)
        pt_click_ref = ref_p.GlobalPoint
    except Exception:
        pyscript.exit()

    # Tipo e sistema de tubulação SEMPRE herdados do tubo de referência
    pipe_type_id, sys_type_id, _, _ = _pipe_params(doc, pipe_ref)

    # Clique caiu exatamente numa ponta de pipe_ref? Se sim, a resposta pra
    # "onde conectar no tubo de referência?" já é óbvia — pula a pergunta.
    clicou_ponta_exata = False
    if pt_click_ref is not None:
        loc_ref_click = pipe_ref.Location.Curve
        pt_a_click = loc_ref_click.GetEndPoint(0)
        pt_b_click = loc_ref_click.GetEndPoint(1)
        clicou_ponta_exata = (pt_click_ref.DistanceTo(pt_a_click) < TOL_SEG or
                               pt_click_ref.DistanceTo(pt_b_click) < TOL_SEG)

    # ── Preferências (lado + altura), com prévia ao vivo no modelo ─────────
    # Show() (modeless), não ShowDialog() — deixa o Revit responder
    # normalmente (orbitar/zoom/pan) com a janela aberta. Ver docstring de
    # _JanelaOpcoesAbrigo sobre como isso afeta o toque no documento.
    janela = None
    try:
        janela = _JanelaOpcoesAbrigo(doc, uidoc, pipe_ref, pt_click_ref, simbolo,
                                      pt_abrigo, nivel, dir_face,
                                      pipe_type_id, sys_type_id, output,
                                      clicou_ponta_exata=clicou_ponta_exata)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, janela)
        janela.Show()
        return
    except Exception as ex:
        # Se falhar depois da janela já ter aberto, garante que a
        # transação da prévia não fique presa — senão o fallback abaixo
        # não conseguiria abrir a dele (só uma transação por vez).
        if janela is not None:
            janela._finalizar(False)
        pyscript.set_envvar(_CHAVE_JANELA_ATIVA, None)
        print(u"[AVISO] Formulário WPF de Conectar Abrigo falhou ({}), "
              u"usando formulário padrão do pyRevit (sem prévia).".format(ex))

    # ── Fallback sem prévia ──────────────────────────────────────────────
    opcoes = _escolher_opcoes_abrigo_fallback(pipe_ref, pt_click_ref, pt_abrigo, nivel,
                                               dir_face, clicou_ponta_exata=clicou_ponta_exata)
    if opcoes is None:
        pyscript.exit()
    lado, ordem_eixos, modo_conexao_ref = opcoes

    with Transaction(doc, u"FireUtils - Conectar Abrigo") as t:
        t.Start()
        try:
            _construir_valvula_stub_e_rota(
                doc, pipe_ref, pt_click_ref, simbolo,
                pt_abrigo, nivel, dir_face,
                pipe_type_id, sys_type_id, output,
                lado=lado, ordem_eixos=ordem_eixos,
                modo_conexao_ref=modo_conexao_ref,
            )
            t.Commit()
        except _ConexaoError as ex:
            t.RollBack()
            forms.alert(u"{}".format(ex), title=u"Fire Utils", warn_icon=True)
        except Exception as ex:
            t.RollBack()
            forms.alert(
                u"Erro ao criar válvula, stub e conexão:\n{}".format(str(ex)),
                title=u"Fire Utils – Erro", warn_icon=True
            )
