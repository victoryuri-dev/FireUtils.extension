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
       • lado do ramal (esquerda/direita da face do abrigo) — antes era
         escolhido por um clique de direção; agora é por botões, igual à
         pergunta de altura
       • onde a tubulação sobe/desce de altura — junto à válvula (padrão)
         ou junto ao tubo de referência
     A cada troca de opção, válvula + stub + roteamento são reconstruídos
     no modelo dentro de uma transação já aberta (revertida/refeita a cada
     mudança) — nada é gravado de fato até o usuário confirmar em OK.
     Cancelar ou fechar a janela reverte TUDO (inclusive a válvula e o
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
from connect_pipe import _construir_conexao, _ConexaoError, _FiltroPipe, _pipe_params

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


# ===========================================================================
# LÓGICA DE CONSTRUÇÃO — válvula + stub + roteamento
# ===========================================================================

def _construir_valvula_stub_e_rota(doc, pipe_ref, pt_click_ref, simbolo,
                                    pt_abrigo, nivel, dir_face,
                                    pipe_type_id, sys_type_id, output,
                                    lado=u"direita", modo_altura=u"origem",
                                    inverter_eixos=False):
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
    # pt_stub_end identifica a ponta livre do stub; pt_click_ref distingue
    # corpo (Tê) vs ponta (joelho) de pipe_ref.
    _construir_conexao(doc, tubo_stub, pipe_ref, pt_stub_end, pt_click_ref,
                        output, modo_altura=modo_altura,
                        inverter_eixos=inverter_eixos)


# ===========================================================================
# FORM — preferências de conexão (lado do ramal + altura), com prévia
# ===========================================================================

class _JanelaOpcoesAbrigo(forms.WPFWindow):
    """Janela WPF (connect_shelter_opcoes.xaml) com PRÉVIA AO VIVO: a cada
    troca de opção (lado do ramal / onde a rota sobe-desce de altura),
    válvula + stub + roteamento são reconstruídos no modelo dentro de uma
    transação já aberta — revertida e refeita a cada mudança. Só é gravado
    de fato (Commit) quando o usuário clica OK; Cancelar ou fechar a janela
    reverte (RollBack) tudo o que foi mostrado na prévia, válvula e stub
    incluídos."""

    def __init__(self, doc, uidoc, pipe_ref, pt_click_ref, simbolo,
                 pt_abrigo, nivel, dir_face, pipe_type_id, sys_type_id, output):
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
        self._transacao_ativa  = False

        # Dispara on_opcao_changed (via evento Checked), mas nesse momento
        # _transacao_ativa ainda é False, então _atualizar_preview só sai
        # sem fazer nada — a prévia real só começa abaixo, após abrir a
        # transação.
        self.RbLadoDireita.IsChecked  = True
        self.RbAlturaOrigem.IsChecked = True
        self.RbEixoPadrao.IsChecked   = True

        self._t = Transaction(doc, u"FireUtils - Conectar Abrigo")
        self._t.Start()
        self._transacao_ativa = True
        try:
            self._atualizar_preview()
        except Exception:
            # _atualizar_preview já trata os erros esperados internamente;
            # isto é só uma rede de segurança pra nunca deixar a transação
            # presa (sem RollBack) se algo inesperado escapar daqui, o que
            # travaria o fallback (uma transação por vez no documento).
            self._descartar()
            raise

    def _descartar(self):
        if self._transacao_ativa:
            try:
                self._t.RollBack()
            except Exception:
                pass
            self._transacao_ativa = False

    def _lado_atual(self):
        return u"esquerda" if self.RbLadoEsquerda.IsChecked else u"direita"

    def _modo_altura_atual(self):
        return u"destino" if self.RbAlturaDestino.IsChecked else u"origem"

    def _inverter_eixos_atual(self):
        return bool(self.RbEixoInvertido.IsChecked)

    def _atualizar_preview(self):
        """Descarta a prévia anterior e reconstrói válvula + stub + rota com
        as opções atuais, dentro da mesma transação (ainda não confirmada)."""
        if not self._transacao_ativa:
            return
        self._t.RollBack()
        self._t.Start()
        try:
            _construir_valvula_stub_e_rota(
                self.doc, self.pipe_ref, self.pt_click_ref, self.simbolo,
                self.pt_abrigo, self.nivel, self.dir_face,
                self.pipe_type_id, self.sys_type_id, self.output,
                lado=self._lado_atual(), modo_altura=self._modo_altura_atual(),
                inverter_eixos=self._inverter_eixos_atual(),
            )
            self.doc.Regenerate()
            self._preview_ok = True
            self.TxtStatus.Text       = u"Pré-visualização atualizada — confirme em OK."
            self.TxtStatus.Foreground = self.Resources[u"BrushOk"]
        except _ConexaoError as ex:
            self.doc.Regenerate()
            self._preview_ok = False
            self.TxtStatus.Text       = u"{}".format(ex)
            self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
        except Exception as ex:
            self.doc.Regenerate()
            self._preview_ok = False
            self.TxtStatus.Text       = u"Erro na prévia: {}".format(ex)
            self.TxtStatus.Foreground = self.Resources[u"BrushWarn"]
        try:
            self.uidoc.RefreshActiveView()
        except Exception:
            pass

    def on_opcao_changed(self, sender, args):
        self._atualizar_preview()

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
        """Sempre finaliza a transação da prévia ao fechar — confirma (Commit)
        só se o usuário clicou OK; qualquer outro fechamento reverte tudo,
        válvula e stub incluídos."""
        if not self._transacao_ativa:
            return
        if self.confirmado:
            try:
                self._t.Commit()
            except Exception:
                pass
            self._transacao_ativa = False
        else:
            self._descartar()


def _escolher_opcoes_abrigo_fallback():
    escolha_lado = forms.SelectFromList.show(
        [u"Esquerda", u"Direita"],
        title=u"Fire Utils — Conectar Abrigo",
        prompt=u"Lado do ramal (a partir da face do abrigo):",
        multiselect=False
    )
    if not escolha_lado:
        return None
    lado = u"esquerda" if escolha_lado == u"Esquerda" else u"direita"

    escolha_altura = forms.SelectFromList.show(
        [u"Junto à válvula", u"Junto ao tubo de referência"],
        title=u"Fire Utils — Conectar Abrigo",
        prompt=u"Onde a tubulação deve subir/descer de altura?",
        multiselect=False
    )
    if not escolha_altura:
        return None
    modo_altura = (u"destino" if escolha_altura == u"Junto ao tubo de referência"
                   else u"origem")

    escolha_eixo = forms.SelectFromList.show(
        [u"Padrão (ajusta primeiro o eixo do tubo referência)",
         u"Invertida (troca a ordem dos eixos X/Y)"],
        title=u"Fire Utils — Conectar Abrigo",
        prompt=u"Ordem dos eixos horizontais (X/Y) na rota:",
        multiselect=False
    )
    if not escolha_eixo:
        return None
    inverter_eixos = escolha_eixo.startswith(u"Invertida")

    return lado, modo_altura, inverter_eixos


# ===========================================================================
# PONTO DE ENTRADA
# ===========================================================================

def conectar_abrigo_preview(doc, uidoc, output):

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
            ObjectType.PointOnElement, _FiltroPipe(),
            u"[2/2] Clique no tubo de referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref_p.ElementId)
        pt_click_ref = ref_p.GlobalPoint
    except Exception:
        pyscript.exit()

    # Tipo e sistema de tubulação SEMPRE herdados do tubo de referência
    pipe_type_id, sys_type_id, _, _ = _pipe_params(doc, pipe_ref)

    # ── Preferências (lado + altura), com prévia ao vivo no modelo ─────────
    janela = None
    try:
        janela = _JanelaOpcoesAbrigo(doc, uidoc, pipe_ref, pt_click_ref, simbolo,
                                      pt_abrigo, nivel, dir_face,
                                      pipe_type_id, sys_type_id, output)
        janela.ShowDialog()
        return
    except Exception as ex:
        # Se falhar depois da janela já ter aberto, garante que a
        # transação da prévia não fique presa — senão o fallback abaixo
        # não conseguiria abrir a dele (só uma transação por vez).
        if janela is not None:
            janela._descartar()
        print(u"[AVISO] Formulário WPF de Conectar Abrigo falhou ({}), "
              u"usando formulário padrão do pyRevit (sem prévia).".format(ex))

    # ── Fallback sem prévia ──────────────────────────────────────────────
    opcoes = _escolher_opcoes_abrigo_fallback()
    if opcoes is None:
        pyscript.exit()
    lado, modo_altura, inverter_eixos = opcoes

    with Transaction(doc, u"FireUtils - Conectar Abrigo") as t:
        t.Start()
        try:
            _construir_valvula_stub_e_rota(
                doc, pipe_ref, pt_click_ref, simbolo,
                pt_abrigo, nivel, dir_face,
                pipe_type_id, sys_type_id, output,
                lado=lado, modo_altura=modo_altura,
                inverter_eixos=inverter_eixos,
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
