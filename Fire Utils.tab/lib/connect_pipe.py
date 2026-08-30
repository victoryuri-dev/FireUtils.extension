# -*- coding: utf-8 -*-
"""
connect_pipe.py — Fire Utils · lib/
Conecta dois tubos com roteamento em ângulos retos.

Fluxo:
  Clique 1 — ponta do PIPE_DESC (tubo desconectado)
  Clique 2 — PIPE_REF (tubo referência): o CLIQUE só marca a posição no
             corpo (usada se o modo "corpo" for escolhido); corpo vs ponta
             não é mais adivinhado pela distância do clique — ver form abaixo.
  Form     — janela WPF (connect_pipe_opcoes.xaml, classe _JanelaOpcoesRota)
             reúne as preferências de rota E mostra PRÉVIA AO VIVO no
             modelo a cada mudança de opção (dentro de uma transação aberta,
             revertida/refeita a cada troca — só grava de fato no OK):
             • onde conectar em pipe_ref: ponto clicado no corpo (Tê,
               padrão) ou ponta livre — se houver (ver modo_conexao_ref em
               _construir_conexao)
             • onde a rota sobe/desce de altura: junto ao tubo desconectado
               (padrão) ou junto ao tubo de referência (ver modo_altura em
               _construir_conexao)
             • ordem dos eixos horizontais X/Y: padrão (primeiro paralelo ao
               eixo do tubo referência) ou invertida (ver inverter_eixos)
             Se essa janela falhar por qualquer motivo, cai para diálogos
             forms.SelectFromList em sequência + fluxo sem prévia
             (_escolher_opcoes_rota_fallback + _conectar).

Etapa 1 — Extensão direta:
  Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref
  E as retas forem REALMENTE colineares (não só paralelas), apenas estende
  e conecta (tê ou joelho conforme posição).

Etapa 2 — Roteamento em L:
  modo_altura="origem"  (padrão): sobe/desce logo na saída de pipe_desc
    pipe_desc horizontal  → tubo vertical P_start→P_knee + joelho em P_start
    pipe_desc vertical    → estende a curva do tubo até z_ref
    mesma cota            → conecta direto sem segmento vertical
  modo_altura="destino": roteia horizontal na cota de pipe_desc e só
    sobe/desce no último trecho, já junto ao ponto de conexão em pipe_ref

  inverter_eixos=False (padrão): seg1 fica paralelo ao eixo de pipe_ref e
    seg2 perpendicular (entra em pipe_ref em ângulo reto — comportamento
    histórico). inverter_eixos=True: troca a ordem — seg1 fica perpendicular
    ao eixo de pipe_ref (ajusta o outro eixo primeiro) e seg2 paralelo.

  seg1 "colinear com pipe_desc": antes de criar seg1 como tubo novo,
    _tenta_estender_colinear checa se pipe_desc já aponta reto (mesma
    direção, mesma reta) para P_mid — se sim, PROLONGA pipe_desc até lá
    (move só o endpoint solto) em vez de criar um tubo novo + joelho ali.
    Só se aplica quando pipe_desc ainda não sofreu nenhum ajuste de altura
    nesse trecho (ver pipe_desc_no_knee/modo_altura="destino").

Casos PIPE_REF (modo_conexao_ref):
  corpo  → tubo horizontal P_knee→P_target + Tê (BreakCurve)
  ponta  → rota em L (seg1/seg2 conforme inverter_eixos) + joelhos
"""

import os

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

import math

from Autodesk.Revit.DB import (
    Transaction, XYZ, Line, LocationCurve,
    BuiltInParameter, FilteredElementCollector,
    ElementId, UnitUtils,
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType, PlumbingUtils
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script as pyscript

_XAML_OPCOES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"connect_pipe_opcoes.xaml")

try:
    from Autodesk.Revit.DB import UnitTypeId
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Meters)
except ImportError:
    from Autodesk.Revit.DB import DisplayUnitType
    def _to_ft(v): return UnitUtils.ConvertToInternalUnits(v, DisplayUnitType.DUT_METERS)

# ── Tolerâncias ──────────────────────────────────────────────────────────────
TOL           = 1e-4          # geral (pés)
TOL_DZ        = _to_ft(0.01)  # 1 cm  — diferença de Z considerada "mesmo nível"
TOL_SEG       = _to_ft(0.05)  # 5 cm  — distância mínima para criar segmento
TOL_PONTA_REF = _to_ft(0.40)  # 40 cm — teto do raio do clique p/ detectar ponta do PIPE_REF
                               # (raio efetivo é limitado a 25% do comprimento de pipe_ref)
TOL_CONN      = _to_ft(0.50)  # 50 cm — raio de busca de conector próximo
TOL_COLINEAR  = _to_ft(0.02)  # 2 cm  — desvio perpendicular máx. p/ considerar 2 retas paralelas como a MESMA reta


# ============================================================================
# HELPERS GEOMÉTRICOS
# ============================================================================

def _pipe_is_vertical(pipe):
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dx = p1.X - p0.X; dy = p1.Y - p0.Y; dz = p1.Z - p0.Z
    L  = math.sqrt(dx*dx + dy*dy + dz*dz)
    return L > TOL and math.sqrt(dx*dx + dy*dy) / L < 0.1


def _projetar_segmento(pt, pt_a, pt_b):
    """Projeta pt no segmento pt_a→pt_b (clamped). Retorna XYZ."""
    ab = pt_b - pt_a
    L  = ab.GetLength()
    if L < TOL:
        return XYZ(pt_a.X, pt_a.Y, pt_a.Z)
    n  = ab.Normalize()
    t  = max(0.0, min(L, (pt - pt_a).DotProduct(n)))
    return XYZ(pt_a.X + n.X * t, pt_a.Y + n.Y * t, pt_a.Z + n.Z * t)


def _rota_ate_endpoint(P_knee, P_target, d_ref, inverter_eixos=False):
    """
    Calcula a rota em L de P_knee até P_target.
    inverter_eixos=False (padrão): usa d_ref (eixo de PIPE_REF) como direção
      primária — seg1: P_knee → P_mid (paralelo ao eixo de PIPE_REF),
      seg2: P_mid → P_target (perpendicular ao eixo de PIPE_REF).
    inverter_eixos=True: usa o eixo perpendicular (no plano horizontal) a
      d_ref como direção primária — inverte a ordem dos ajustes X/Y.
    Retorna (P_mid, needs_seg1, needs_seg2).
    """
    if inverter_eixos:
        d_horiz = XYZ(d_ref.X, d_ref.Y, 0.0)
        L_h     = d_horiz.GetLength()
        if L_h > TOL:
            d_horiz = XYZ(d_horiz.X / L_h, d_horiz.Y / L_h, 0.0)
        d_prim = XYZ(-d_horiz.Y, d_horiz.X, 0.0)
    else:
        d_prim = d_ref

    v = P_target - P_knee
    a = v.DotProduct(d_prim)
    P_mid = XYZ(P_knee.X + d_prim.X * a,
                P_knee.Y + d_prim.Y * a,
                P_knee.Z)
    needs_seg1 = abs(a) > TOL_SEG
    needs_seg2 = P_mid.DistanceTo(P_target) > TOL_SEG
    if not needs_seg2:
        # P_mid já está "perto o suficiente" de P_target (dentro de
        # TOL_SEG) — sem isso, quem chama usaria P_mid como ponto final
        # de verdade (já que seg2 é dispensado), deixando uma folga de
        # até TOL_SEG entre o tubo e o alvo. ConnectTo não reclama dessa
        # folga (ao contrário de NewElbowFitting), então ela passava
        # despercebida: sem erro, mas sem encostar de fato. Encaixa exato.
        P_mid = P_target
    return P_mid, needs_seg1, needs_seg2


def _intersecao_com_pipe(P_start, d_ext, pt_A, pt_B):
    """
    Verifica se o raio (P_start + t*d_ext, t>=0) intersecta o segmento pt_A→pt_B.
    Usa fórmula de menor distância entre duas retas 3-D.
    Retorna (P_int, t, em_ponta) ou None.
    """
    TOL_SKEW  = _to_ft(0.02)   # 2 cm
    TOL_PONTA = _to_ft(0.05)   # 5 cm
    d_ref = pt_B - pt_A
    L_ref = d_ref.GetLength()
    if L_ref < TOL:
        return None
    d_ref_n = XYZ(d_ref.X / L_ref, d_ref.Y / L_ref, d_ref.Z / L_ref)
    w   = P_start - pt_A
    b   = d_ext.DotProduct(d_ref_n)
    d_  = d_ext.DotProduct(w)
    e   = d_ref_n.DotProduct(w)
    den = 1.0 - b * b
    if abs(den) < 1e-9:
        return None  # paralelo
    t = (b * e - d_) / den
    s = (e - b * d_) / den
    if t < -TOL:
        return None  # interseção ficaria atrás de P_start
    t = max(0.0, t)
    P_t = XYZ(P_start.X + d_ext.X * t, P_start.Y + d_ext.Y * t, P_start.Z + d_ext.Z * t)
    P_s = XYZ(pt_A.X + d_ref_n.X * s,  pt_A.Y + d_ref_n.Y * s,  pt_A.Z + d_ref_n.Z * s)
    if P_t.DistanceTo(P_s) > TOL_SKEW:
        return None  # retas oblíquas
    if s < -TOL_PONTA or s > L_ref + TOL_PONTA:
        return None  # fora dos limites do pipe_ref
    s_cl     = max(0.0, min(L_ref, s))
    em_ponta = s_cl < TOL_PONTA or s_cl > L_ref - TOL_PONTA
    P_int    = XYZ(pt_A.X + d_ref_n.X * s_cl,
                   pt_A.Y + d_ref_n.Y * s_cl,
                   pt_A.Z + d_ref_n.Z * s_cl)
    return P_int, t, em_ponta


def _extremo_oposto(curve, pt):
    """Endpoint de curve mais distante de pt (o outro extremo)."""
    p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
    return p1 if p0.DistanceTo(pt) < p1.DistanceTo(pt) else p0


def _tenta_estender_colinear(doc, pipe, P_fixo, P_atual, P_alvo):
    """
    Se `pipe` (indo de P_fixo até P_atual) já aponta, em linha reta e no
    mesmo sentido, para P_alvo, PROLONGA pipe até P_alvo (move só o
    endpoint P_atual, mantém P_fixo) em vez de deixar quem chamou criar um
    tubo novo + joelho ali. Retorna True se estendeu, False se não é
    colinear (quem chamou deve criar o tubo novo normalmente).
    """
    if P_atual.DistanceTo(P_alvo) < TOL:
        return False

    d_pipe = P_atual - P_fixo
    L_pipe = d_pipe.GetLength()
    if L_pipe < TOL:
        return False
    d_pipe = XYZ(d_pipe.X / L_pipe, d_pipe.Y / L_pipe, d_pipe.Z / L_pipe)

    d_want = P_alvo - P_atual
    L_want = d_want.GetLength()
    d_want = XYZ(d_want.X / L_want, d_want.Y / L_want, d_want.Z / L_want)

    if d_pipe.DotProduct(d_want) < 0.999:
        return False  # não é o mesmo sentido/direção — precisa de joelho

    # Confere colinearidade de verdade (desvio perpendicular), não só
    # direções paralelas — mesma checagem usada na Etapa 1.
    w      = P_alvo - P_fixo
    w_proj = w.DotProduct(d_pipe)
    perp   = XYZ(w.X - d_pipe.X * w_proj,
                w.Y - d_pipe.Y * w_proj,
                w.Z - d_pipe.Z * w_proj)
    if perp.GetLength() > TOL_COLINEAR:
        return False

    pipe.Location.Curve = Line.CreateBound(P_fixo, P_alvo)
    doc.Regenerate()
    return True


# ============================================================================
# HELPERS REVIT
# ============================================================================

def _conn_near(element, pt, tol=None):
    """Conector de element mais próximo de pt."""
    tol = tol or TOL_CONN
    try:
        mgr = element.ConnectorManager
    except AttributeError:
        try:
            mgr = element.MEPModel.ConnectorManager
        except Exception:
            return None
    best, best_d = None, tol
    for c in mgr.Connectors:
        d = c.Origin.DistanceTo(pt)
        if d < best_d:
            best_d, best = d, c
    return best


def _conn_nearest(pipe, pt):
    """Conector de pipe mais próximo de pt (sem limite de distância)."""
    best, best_d = None, float('inf')
    for c in pipe.ConnectorManager.Connectors:
        d = c.Origin.DistanceTo(pt)
        if d < best_d:
            best_d, best = d, c
    return best


def _pipe_params(doc, pipe):
    """Retorna (pipe_type_id, sys_type_id, level_id, diam_ft) herdados de pipe."""
    pipe_type_id = pipe.GetTypeId()
    if pipe_type_id == ElementId.InvalidElementId:
        try:
            from Autodesk.Revit.DB.Plumbing import PipeType
            ts = FilteredElementCollector(doc).OfClass(PipeType).ToElements()
            if ts:
                pipe_type_id = ts[0].Id
        except Exception:
            pass

    sys_type_id = ElementId.InvalidElementId
    try:
        mep = pipe.MEPSystem
        if mep:
            sys_type_id = mep.GetTypeId()
    except Exception:
        pass
    if sys_type_id == ElementId.InvalidElementId:
        try:
            ts = FilteredElementCollector(doc).OfClass(PipingSystemType).ToElements()
            if ts:
                sys_type_id = ts[0].Id
        except Exception:
            pass

    try:
        level_id = pipe.ReferenceLevel.Id
    except Exception:
        level_id = ElementId.InvalidElementId

    diam_ft = _to_ft(0.065)
    for bip in [BuiltInParameter.RBS_PIPE_DIAMETER_PARAM,
                BuiltInParameter.RBS_PIPE_OUTER_DIAMETER]:
        try:
            p = pipe.get_Parameter(bip)
            if p and p.AsDouble() > 0:
                diam_ft = p.AsDouble()
                break
        except Exception:
            pass

    return pipe_type_id, sys_type_id, level_id, diam_ft


def _set_diam(pipe, diam_ft):
    for bip in [BuiltInParameter.RBS_PIPE_DIAMETER_PARAM,
                BuiltInParameter.RBS_PIPE_OUTER_DIAMETER]:
        try:
            p = pipe.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(diam_ft)
                return
        except Exception:
            pass


def _mk_pipe(doc, pa, pb, pt_id, sys_id, lvl_id, diam_ft):
    """Cria tubo de pa a pb e aplica diâmetro."""
    novo = Pipe.Create(doc, sys_id, pt_id, lvl_id, pa, pb)
    _set_diam(novo, diam_ft)
    return novo


def _elbow(doc, c1, c2):
    """Cria joelho entre c1 e c2. Falha silenciosa."""
    try:
        doc.Create.NewElbowFitting(c1, c2)
        return True
    except Exception:
        return False


def _conn_dir(c):
    try:
        return c.CoordinateSystem.BasisZ
    except Exception:
        return None


def _juntar(doc, c1, c2):
    """
    Junta dois conectores que já estão no mesmo ponto (ex.: fim da rota
    encostando bem na ponta de pipe_ref). Se apontam um pro outro em linha
    reta (colineares), NewElbowFitting falha — não é uma curva de verdade,
    é uma continuação reta — então conecta direto (ConnectTo). Caso
    contrário, cria joelho normalmente. Retorna True se conseguiu (por
    qualquer um dos dois métodos).
    """
    d1, d2 = _conn_dir(c1), _conn_dir(c2)
    if d1 is not None and d2 is not None and d1.DotProduct(d2) < -0.999:
        try:
            c1.ConnectTo(c2)
            return True
        except Exception:
            pass  # cai pro joelho abaixo como última tentativa
    return _elbow(doc, c1, c2)


def _tee(doc, pipe_ref, P_target, conn_branch):
    """
    Cria tê no corpo de pipe_ref em P_target, conectando conn_branch como ramal.
    """
    def _dir(c):
        try:
            return c.CoordinateSystem.BasisZ
        except Exception:
            return XYZ(0, 0, 1)

    new_id   = PlumbingUtils.BreakCurve(doc, pipe_ref.Id, P_target)
    pipe_sec = doc.GetElement(new_id)
    c_r1     = _conn_near(pipe_ref, P_target)
    c_r2     = _conn_near(pipe_sec,  P_target)
    if not (c_r1 and c_r2):
        return False
    conns = [c_r1, c_r2, conn_branch]
    melhor, par = -1.0, (0, 1)
    for i in range(3):
        for j in range(i + 1, 3):
            d = abs(_dir(conns[i]).DotProduct(_dir(conns[j])))
            if d > melhor:
                melhor, par = d, (i, j)
    run  = [conns[par[0]], conns[par[1]]]
    rest = [c for k, c in enumerate(conns) if k not in par]
    try:
        doc.Create.NewTeeFitting(run[0], run[1], rest[0])
        return True
    except Exception:
        return False


def _global_pt(ref):
    try:
        return ref.GlobalPoint
    except Exception:
        return None


class _FiltroPipe(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, Pipe)
    def AllowReference(self, r, p):
        return True


# ============================================================================
# FORM — preferências de roteamento (altura + ordem dos eixos X/Y)
# ============================================================================

class _JanelaOpcoesRota(forms.WPFWindow):
    """Janela WPF (connect_pipe_opcoes.xaml) com PRÉVIA AO VIVO: a cada troca
    de opção (altura / ordem dos eixos X-Y), o tubo é reconstruído no modelo
    dentro de uma transação já aberta — revertida e refeita a cada mudança —
    para o usuário ver o resultado antes de confirmar. Só é gravado de fato
    (Commit) quando o usuário clica OK; Cancelar ou fechar a janela reverte
    (RollBack) tudo o que foi mostrado na prévia."""

    def __init__(self, doc, uidoc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output):
        forms.WPFWindow.__init__(self, _XAML_OPCOES_PATH)
        self.doc           = doc
        self.uidoc         = uidoc
        self.pipe_desc     = pipe_desc
        self.pipe_ref      = pipe_ref
        self.pt_click_desc = pt_click_desc
        self.pt_click_ref  = pt_click_ref
        self.output        = output

        self.confirmado        = False
        self._preview_ok       = False
        self._transacao_ativa  = False

        # Dispara on_opcao_changed (via evento Checked), mas nesse momento
        # _transacao_ativa ainda é False, então _atualizar_preview só sai
        # sem fazer nada — a prévia real só começa abaixo, após abrir a
        # transação.
        self.RbRefCorpo.IsChecked     = True
        self.RbAlturaOrigem.IsChecked = True
        self.RbEixoPadrao.IsChecked   = True

        self._t = Transaction(doc, u"FireUtils - Conectar Tubo")
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

    def _modo_altura_atual(self):
        return u"destino" if self.RbAlturaDestino.IsChecked else u"origem"

    def _inverter_eixos_atual(self):
        return bool(self.RbEixoInvertido.IsChecked)

    def _modo_conexao_ref_atual(self):
        return u"ponta" if self.RbRefPonta.IsChecked else u"corpo"

    def _atualizar_preview(self):
        """Descarta a prévia anterior e reconstrói a conexão com as opções
        atuais, dentro da mesma transação (ainda não confirmada)."""
        if not self._transacao_ativa:
            return
        self._t.RollBack()
        self._t.Start()
        try:
            _construir_conexao(
                self.doc, self.pipe_desc, self.pipe_ref,
                self.pt_click_desc, self.pt_click_ref, self.output,
                modo_altura=self._modo_altura_atual(),
                inverter_eixos=self._inverter_eixos_atual(),
                modo_conexao_ref=self._modo_conexao_ref_atual(),
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
        só se o usuário clicou OK; qualquer outro fechamento reverte tudo."""
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


def _escolher_opcoes_rota_fallback():
    escolha_ref = forms.SelectFromList.show(
        [u"Ponto clicado no corpo (Tê)", u"Ponta livre (se houver)"],
        title=u"Fire Utils — Conectar Tubo",
        prompt=u"Onde conectar no tubo de referência?",
        multiselect=False
    )
    if not escolha_ref:
        return None
    modo_conexao_ref = u"ponta" if escolha_ref.startswith(u"Ponta") else u"corpo"

    escolha_altura = forms.SelectFromList.show(
        [u"Junto ao tubo desconectado", u"Junto ao tubo de referência"],
        title=u"Fire Utils — Conectar Tubo",
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
        title=u"Fire Utils — Conectar Tubo",
        prompt=u"Ordem dos eixos horizontais (X/Y) na rota:",
        multiselect=False
    )
    if not escolha_eixo:
        return None
    inverter_eixos = escolha_eixo.startswith(u"Invertida")

    return modo_altura, inverter_eixos, modo_conexao_ref


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

def run(doc, uidoc, output):
    # ── Clique 1: ponta do PIPE_DESC ────────────────────────────────────────
    try:
        ref1         = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroPipe(),
            u"[1/2] Clique em uma PONTA do tubo desconectado"
        )
        pipe_desc    = doc.GetElement(ref1.ElementId)
        pt_click_desc = _global_pt(ref1)
    except Exception:
        pyscript.exit()

    # ── Clique 2: PIPE_REF (corpo ou ponta) ─────────────────────────────────
    try:
        ref2         = uidoc.Selection.PickObject(
            ObjectType.Element, _FiltroPipe(),
            u"[2/2] Clique no tubo referência — corpo para Tê, ponta para joelho"
        )
        pipe_ref     = doc.GetElement(ref2.ElementId)
        pt_click_ref = _global_pt(ref2)
    except Exception:
        pyscript.exit()

    if pipe_ref.Id == pipe_desc.Id:
        forms.alert(u"Os dois tubos selecionados são o mesmo elemento.",
                    title=u"Fire Utils", warn_icon=True)
        pyscript.exit()

    # ── Preferências de roteamento, com prévia ao vivo no modelo ────────────
    janela = None
    try:
        janela = _JanelaOpcoesRota(doc, uidoc, pipe_desc, pipe_ref,
                                    pt_click_desc, pt_click_ref, output)
        janela.ShowDialog()
        return
    except Exception as ex:
        # Se falhar depois da janela já ter aberto (ex.: erro ao exibir),
        # garante que a transação da prévia não fique presa — senão o
        # fallback abaixo não conseguiria abrir a dele (só uma por vez).
        if janela is not None:
            janela._descartar()
        print(u"[AVISO] Formulário WPF com prévia de Conectar Tubo falhou ({}), "
              u"usando formulário padrão do pyRevit (sem prévia).".format(ex))

    opcoes = _escolher_opcoes_rota_fallback()
    if opcoes is None:
        pyscript.exit()
    modo_altura, inverter_eixos, modo_conexao_ref = opcoes

    _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
               modo_altura=modo_altura, inverter_eixos=inverter_eixos,
               modo_conexao_ref=modo_conexao_ref)


# ============================================================================
# LÓGICA DE CONEXÃO
# ============================================================================

class _ConexaoError(Exception):
    """Falha de validação/criação conhecida — mensagem já pronta para o
    usuário (alerta no fluxo sem prévia, texto de status no fluxo com
    prévia). Erros inesperados propagam como Exception normal."""
    pass


def _validar_ordem_eixos(inverter_eixos, needs_seg2):
    """
    Com inverter_eixos=True, o 1º trecho fecha TODO o desvio perpendicular
    de uma vez — o que faz esse trecho terminar exatamente SOBRE a reta de
    pipe_ref (matematicamente: o ponto final do 1º trecho sempre cai na
    reta, seja qual for o deslocamento perpendicular original). Se ainda
    sobra um 2º trecho depois disso (needs_seg2=True), esse 2º trecho anda
    PARALELO a pipe_ref a partir de um ponto que já está sobre a própria
    reta dele — ou seja, sobrepõe/duplica um pedaço de pipe_ref em vez de
    formar um Tê/joelho em ângulo reto. Isso só é detectável depois de
    calcular a rota (não dá pra saber antes se vai sobrar 2º trecho), por
    isso é chamado logo após cada _rota_ate_endpoint, antes de criar
    qualquer tubo. Com inverter_eixos=False isso nunca acontece (o trecho
    final é sempre perpendicular por construção).
    """
    if inverter_eixos and needs_seg2:
        raise _ConexaoError(
            u"Com a ordem de eixos invertida, o trecho final ficaria "
            u"paralelo ao tubo de referência (sobreposto à própria linha "
            u"dele) em vez de perpendicular — não forma um Tê/joelho "
            u"válido aqui. Use a ordem padrão para esta conexão.")


def _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref):
    """
    Escolhe a ponta LIVRE (sem conexão) de pipe_ref pra conectar via joelho.
    Se as duas pontas estiverem livres, usa a mais próxima do clique (ou de
    pt_A, se não houver clique). Levanta _ConexaoError se nenhuma ponta
    estiver livre. Retorna o XYZ da ponta escolhida.
    """
    c_a = _conn_near(pipe_ref, pt_A)
    c_b = _conn_near(pipe_ref, pt_B)
    livre_a = c_a is not None and not c_a.IsConnected
    livre_b = c_b is not None and not c_b.IsConnected

    if livre_a and livre_b:
        ref = pt_click_ref if pt_click_ref is not None else pt_A
        return pt_A if ref.DistanceTo(pt_A) < ref.DistanceTo(pt_B) else pt_B
    if livre_a:
        return pt_A
    if livre_b:
        return pt_B
    raise _ConexaoError(
        u"O tubo de referência não tem nenhuma ponta livre para conectar — "
        u"as duas pontas já estão conectadas a outros elementos.")


def _construir_conexao(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
                        modo_altura=u"origem", inverter_eixos=False,
                        modo_conexao_ref=u"auto"):
    """
    Lógica pura de conexão — NÃO abre/fecha transação (fica a cargo de
    quem chama: _conectar, no fluxo direto, ou a janela de prévia, que
    reconstrói isso a cada mudança de opção dentro da MESMA transação).

    modo_altura : "origem"  → sobe/desce logo na saída do tubo desconectado
                              (comportamento padrão/histórico).
                  "destino" → roteia horizontalmente na cota do tubo
                              desconectado e só sobe/desce por último,
                              já junto ao tubo de referência.
    inverter_eixos : False (padrão) → no trecho horizontal em L, ajusta
                              primeiro o eixo paralelo ao tubo de referência.
                     True  → inverte a ordem, ajustando primeiro o eixo
                              perpendicular (troca X/Y).
    modo_conexao_ref : escolhe ponta vs corpo em pipe_ref — decisão do
                              usuário, não mais adivinhada pela distância do
                              clique (raio de tolerância dava falso positivo
                              em pipe_ref curto).
                        "ponta" → força joelho na ponta LIVRE de pipe_ref
                              (a mais próxima do clique, se as duas
                              estiverem livres); _ConexaoError se nenhuma
                              ponta estiver livre.
                        "corpo" → força Tê no ponto clicado (projetado no
                              corpo de pipe_ref), mesmo perto de uma ponta.
                        "auto"  (compatibilidade, sem diálogo) → heurística
                              antiga por proximidade do clique.
    """

    # ── Endpoint de PIPE_DESC selecionado pelo clique ────────────────────────
    if pt_click_desc is not None:
        conn_desc = _conn_nearest(pipe_desc, pt_click_desc)
    else:
        loc_fb = pipe_ref.Location.Curve
        mid_fb = XYZ((loc_fb.GetEndPoint(0).X + loc_fb.GetEndPoint(1).X) / 2,
                     (loc_fb.GetEndPoint(0).Y + loc_fb.GetEndPoint(1).Y) / 2,
                     (loc_fb.GetEndPoint(0).Z + loc_fb.GetEndPoint(1).Z) / 2)
        conn_desc = _conn_nearest(pipe_desc, mid_fb)

    if conn_desc is None:
        raise _ConexaoError(u"Não foi possível encontrar conector no tubo desconectado.")

    if conn_desc.IsConnected:
        raise _ConexaoError(
            u"A ponta selecionada do tubo já está conectada a outro elemento.\n"
            u"Selecione uma ponta livre (sem conexão).")

    P_start = conn_desc.Origin

    # ── Geometria de PIPE_REF ────────────────────────────────────────────────
    loc_ref = pipe_ref.Location.Curve
    pt_A    = loc_ref.GetEndPoint(0)
    pt_B    = loc_ref.GetEndPoint(1)
    z_ref   = (pt_A.Z + pt_B.Z) / 2.0
    d_ref   = (pt_B - pt_A).Normalize()

    # ── Modo de conexão: ponta ou corpo? ────────────────────────────────────
    # Decisão explícita do usuário via diálogo, por padrão — não é mais
    # adivinhada por um raio de tolerância (dava falso positivo em pipe_ref
    # curto: corpo inteiro "parecia" ponta).
    if modo_conexao_ref == u"ponta":
        clicou_ponta = True
        pt_endpoint  = _escolher_ponta_livre(pipe_ref, pt_A, pt_B, pt_click_ref)
    elif modo_conexao_ref == u"corpo":
        clicou_ponta = False
        pt_endpoint  = None
    elif pt_click_ref is not None:
        # "auto" (compatibilidade, sem diálogo) — heurística antiga por
        # proximidade do clique, com raio proporcional ao comprimento de
        # pipe_ref (até o teto de TOL_PONTA_REF).
        L_ref          = pt_A.DistanceTo(pt_B)
        tol_ponta_ref  = min(TOL_PONTA_REF, L_ref * 0.25)
        da = pt_click_ref.DistanceTo(pt_A)
        db = pt_click_ref.DistanceTo(pt_B)
        clicou_ponta = da < tol_ponta_ref or db < tol_ponta_ref
        pt_endpoint  = pt_A if da < db else pt_B
    else:
        clicou_ponta = False
        pt_endpoint  = None

    # ── Etapa 1: extensão direta ─────────────────────────────────────────────
    # Se o eixo de pipe_desc, estendido a partir de P_start, intersectar pipe_ref,
    # apenas estende e conecta sem criar tubos extras. Só roda no modo "auto"
    # (compatibilidade, sem diálogo) — com ponta/corpo escolhidos
    # explicitamente pelo usuário, pular esse atalho evita que o resultado
    # saia "silenciosamente" diferente do que foi pedido no diálogo.
    loc_desc = pipe_desc.Location.Curve
    p_desc_0 = loc_desc.GetEndPoint(0)
    p_desc_1 = loc_desc.GetEndPoint(1)
    L_desc   = p_desc_0.DistanceTo(p_desc_1)
    if modo_conexao_ref == u"auto" and L_desc > TOL:
        P_other = (p_desc_1 if p_desc_0.DistanceTo(P_start) < p_desc_1.DistanceTo(P_start)
                   else p_desc_0)
        d_ext = XYZ(
            (P_start.X - P_other.X) / L_desc,
            (P_start.Y - P_other.Y) / L_desc,
            (P_start.Z - P_other.Z) / L_desc,
        )
        resultado = _intersecao_com_pipe(P_start, d_ext, pt_A, pt_B)
        if resultado is not None:
            P_int, t_ext, em_ponta_int = resultado
            if t_ext > TOL:
                pipe_desc.Location.Curve = Line.CreateBound(P_other, P_int)
                doc.Regenerate()
            conn_end = _conn_near(pipe_desc, P_int)
            if conn_end:
                if em_ponta_int:
                    at_end_a = P_int.DistanceTo(pt_A) < _to_ft(0.05)
                    pt_ponta = pt_A if at_end_a else pt_B
                    c_ponta  = _conn_near(pipe_ref, pt_ponta)
                    if c_ponta:
                        _juntar(doc, c_ponta, conn_end)
                else:
                    _tee(doc, pipe_ref, P_int, conn_end)
            return

        # Caso colinear: tubos alinhados ponta a ponta.
        # dot_par só confirma que as direções são PARALELAS — dois tubos
        # paralelos porém em retas diferentes (ex.: alturas/afastamentos
        # distintos) NÃO são colineares. Sem checar o desvio perpendicular,
        # o trecho abaixo ligaria P_other direto a pt_A/pt_B criando um
        # tubo diagonal (fora de esquadro) em vez de rotear em ângulo reto.
        dot_par = abs(d_ext.DotProduct(d_ref))
        if dot_par > 0.99:
            w      = pt_A - P_start
            w_proj = w.DotProduct(d_ext)
            perp   = XYZ(w.X - d_ext.X * w_proj,
                        w.Y - d_ext.Y * w_proj,
                        w.Z - d_ext.Z * w_proj)
            if perp.GetLength() > TOL_COLINEAR:
                dot_par = 0.0  # paralelo mas não colinear → cai para o roteamento em L
        if dot_par > 0.99:
            t_a = (pt_A - P_start).DotProduct(d_ext)
            t_b = (pt_B - P_start).DotProduct(d_ext)
            candidates = []
            if t_a >= -TOL:
                candidates.append((t_a, pt_A))
            if t_b >= -TOL:
                candidates.append((t_b, pt_B))
            if candidates:
                _, pt_join = min(candidates, key=lambda x: x[0])
                if P_start.DistanceTo(pt_join) > TOL:
                    pipe_desc.Location.Curve = Line.CreateBound(P_other, pt_join)
                    doc.Regenerate()
                conn_end = _conn_near(pipe_desc, pt_join)
                c_ep     = _conn_near(pipe_ref,  pt_join)
                if conn_end and c_ep:
                    conn_end.ConnectTo(c_ep)
                return

    # ── Etapa 2: roteamento em L ─────────────────────────────────────────────
    P_knee    = XYZ(P_start.X, P_start.Y, z_ref)
    dz        = abs(P_start.Z - z_ref)
    need_vert = dz > TOL_DZ
    desc_vert = _pipe_is_vertical(pipe_desc)

    if not clicou_ponta:
        # Usa a posição do CLIQUE do usuário (não P_knee) para determinar
        # ONDE no pipe_ref a conexão deve ser feita.
        # P_knee pode estar fora da extensão do pipe_ref e causaria projeção
        # clamped para um endpoint → gerava joelho em vez de tê.
        ref_proj = pt_click_ref if pt_click_ref is not None else P_knee
        P_target   = _projetar_segmento(ref_proj, pt_A, pt_B)
        dist_horiz = P_knee.DistanceTo(P_target)
        need_horiz = dist_horiz > TOL_SEG
        if not need_horiz:
            P_target = P_knee
    else:
        P_target   = None
        need_horiz = True

    if not need_vert and not need_horiz and not clicou_ponta:
        raise _ConexaoError(u"Os tubos já estão alinhados — nenhuma conexão necessária.")

    # Ponto final da rota — onde o último trecho encontra pipe_ref.
    P_final = pt_endpoint if clicou_ponta else P_target

    pt_id, sys_id, _,      diam_ft = _pipe_params(doc, pipe_desc)
    _,     _,      lvl_id, _       = _pipe_params(doc, pipe_ref)

    _elbows_pend = []

    if modo_altura == u"destino":
        # ── Muda de altura junto ao tubo de REFERÊNCIA ────────────────────
        # Roteia horizontalmente ainda na cota do tubo desconectado,
        # alinhando X/Y ao ponto final; sobe/desce só no último trecho.
        P_pre = XYZ(P_final.X, P_final.Y, P_start.Z)
        P_mid, needs_s1, needs_s2 = _rota_ate_endpoint(
            P_start, P_pre, d_ref, inverter_eixos=inverter_eixos)
        _validar_ordem_eixos(inverter_eixos, needs_s2)
        conn_cur = conn_desc

        if needs_s1:
            # Se pipe_desc já aponta reto para P_mid, prolonga o próprio
            # tubo em vez de criar um segmento novo + joelho desnecessário.
            P_other_desc = _extremo_oposto(pipe_desc.Location.Curve, P_start)
            if _tenta_estender_colinear(doc, pipe_desc, P_other_desc, P_start, P_mid):
                conn_cur = _conn_near(pipe_desc, P_mid)
            else:
                seg1   = _mk_pipe(doc, P_start, P_mid, pt_id, sys_id, lvl_id, diam_ft)
                c_s1_k = _conn_near(seg1, P_start)
                c_s1_m = _conn_near(seg1, P_mid)
                _elbows_pend.append((conn_cur, c_s1_k))
                conn_cur = c_s1_m

        if needs_s2:
            seg2   = _mk_pipe(doc, P_mid, P_pre, pt_id, sys_id, lvl_id, diam_ft)
            c_s2_m = _conn_near(seg2, P_mid)
            c_s2_e = _conn_near(seg2, P_pre)
            _elbows_pend.append((conn_cur, c_s2_m))
            conn_cur = c_s2_e

        if need_vert:
            pipe_vert = _mk_pipe(doc, P_pre, P_final, pt_id, sys_id, lvl_id, diam_ft)
            c_v_pre   = _conn_near(pipe_vert, P_pre)
            c_v_final = _conn_near(pipe_vert, P_final)
            _elbows_pend.append((conn_cur, c_v_pre))
            conn_cur = c_v_final

        conn_final = conn_cur

    else:
        # ── Muda de altura junto ao tubo DESCONECTADO (padrão) ────────────
        conn_knee = None
        # True só quando conn_knee ainda é o conector original de pipe_desc
        # (nenhum trecho vertical foi criado/aplicado) — só nesse caso faz
        # sentido tentar prolongar o próprio pipe_desc no passo seguinte.
        pipe_desc_no_knee = False

        if not need_vert:
            conn_knee = _conn_near(pipe_desc, P_start)
            pipe_desc_no_knee = True

        elif desc_vert:
            # pipe_desc vertical: estende a curva até z_ref
            c  = pipe_desc.Location.Curve
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            if p0.DistanceTo(P_start) < p1.DistanceTo(P_start):
                pipe_desc.Location.Curve = Line.CreateBound(
                    XYZ(p0.X, p0.Y, z_ref), p1)
            else:
                pipe_desc.Location.Curve = Line.CreateBound(
                    p0, XYZ(p1.X, p1.Y, z_ref))
            doc.Regenerate()
            conn_knee = _conn_near(pipe_desc, P_knee)

        else:
            # pipe_desc horizontal: cria tubo vertical P_start → P_knee
            pipe_vert = _mk_pipe(doc, P_start, P_knee, pt_id, sys_id, lvl_id, diam_ft)
            conn_knee = _conn_near(pipe_vert, P_knee)
            c_d       = _conn_near(pipe_desc,  P_start)
            c_v       = _conn_near(pipe_vert,  P_start)
            _elbows_pend.append((c_d, c_v))

        if conn_knee is None:
            raise _ConexaoError(u"Não foi possível localizar o conector em P_knee.")

        # Roteamento em L: seg1 paralelo ao eixo de pipe_ref,
        # seg2 perpendicular. Garante ângulos retos mesmo quando
        # P_knee está fora da extensão lateral de pipe_ref.
        P_mid, needs_s1, needs_s2 = _rota_ate_endpoint(
            P_knee, P_final, d_ref, inverter_eixos=inverter_eixos)
        _validar_ordem_eixos(inverter_eixos, needs_s2)
        conn_cur = conn_knee

        if needs_s1:
            estendeu = False
            if pipe_desc_no_knee:
                # P_knee == P_start aqui (não houve trecho vertical) — se
                # pipe_desc já aponta reto para P_mid, prolonga o próprio
                # tubo em vez de criar um segmento novo + joelho.
                P_other_desc = _extremo_oposto(pipe_desc.Location.Curve, P_knee)
                estendeu = _tenta_estender_colinear(doc, pipe_desc, P_other_desc, P_knee, P_mid)
                if estendeu:
                    conn_cur = _conn_near(pipe_desc, P_mid)

            if not estendeu:
                seg1   = _mk_pipe(doc, P_knee, P_mid, pt_id, sys_id, lvl_id, diam_ft)
                c_s1_k = _conn_near(seg1, P_knee)
                c_s1_m = _conn_near(seg1, P_mid)
                _elbows_pend.append((conn_cur, c_s1_k))
                conn_cur = c_s1_m

        if needs_s2:
            seg2   = _mk_pipe(doc, P_mid, P_final, pt_id, sys_id, lvl_id, diam_ft)
            c_s2_m = _conn_near(seg2, P_mid)
            c_s2_e = _conn_near(seg2, P_final)
            _elbows_pend.append((conn_cur, c_s2_m))
            conn_cur = c_s2_e

        conn_final = conn_cur

    # ── Conexão final a pipe_ref: Tê (modo corpo) ou joelho (modo ponta) ──────
    if not clicou_ponta:
        if conn_final:
            doc.Regenerate()
            _TOL_PONTA_GEO = _to_ft(0.05)
            at_end_a = P_final.DistanceTo(pt_A) < _TOL_PONTA_GEO
            at_end_b = P_final.DistanceTo(pt_B) < _TOL_PONTA_GEO
            if at_end_a or at_end_b:
                pt_ponta = pt_A if at_end_a else pt_B
                c_ponta  = _conn_near(pipe_ref, pt_ponta)
                if c_ponta:
                    # _juntar: se o último trecho chega colinear na ponta de
                    # pipe_ref (reta contínua), conecta direto em vez de
                    # forçar um joelho — que falharia por não ser uma curva
                    # de verdade nesse caso.
                    ok = _juntar(doc, c_ponta, conn_final)
                    if not ok:
                        output.print_md(u"| Conexão na ponta | **falhou** |")
            else:
                ok = _tee(doc, pipe_ref, P_final, conn_final)
                if not ok:
                    output.print_md(u"| Tê | **falhou** — verifique se há família de tê carregada |")

            doc.Regenerate()
            for c1, c2 in _elbows_pend:
                _juntar(doc, c1, c2)

    else:
        doc.Regenerate()
        c_ref_end = _conn_near(pipe_ref, P_final)
        if c_ref_end and conn_final:
            # Idem: pode ser uma continuação reta (ConnectTo), não
            # necessariamente um joelho — ver _juntar.
            ok = _juntar(doc, c_ref_end, conn_final)
            if not ok:
                output.print_md(
                    u"| Conexão na ponta | **falhou** — "
                    u"verifique se o endpoint de pipe_ref está livre |")

        doc.Regenerate()
        for c1, c2 in _elbows_pend:
            _juntar(doc, c1, c2)


def _conectar(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref, output,
              modo_altura=u"origem", inverter_eixos=False, modo_conexao_ref=u"auto"):
    """Fluxo direto (sem prévia) — abre/fecha a transação e mostra alerta em
    caso de falha. Usado como fallback quando a janela de prévia falha."""
    with Transaction(doc, u"FireUtils - Conectar Tubo") as t:
        t.Start()
        try:
            _construir_conexao(doc, pipe_desc, pipe_ref, pt_click_desc, pt_click_ref,
                                output, modo_altura=modo_altura, inverter_eixos=inverter_eixos,
                                modo_conexao_ref=modo_conexao_ref)
            t.Commit()
        except _ConexaoError as ex:
            t.RollBack()
            forms.alert(u"{}".format(ex), title=u"Fire Utils", warn_icon=True)
        except Exception as ex:
            t.RollBack()
            forms.alert(
                u"Erro ao criar a conexão:\n{}".format(str(ex)),
                title=u"Fire Utils – Erro",
                warn_icon=True)
