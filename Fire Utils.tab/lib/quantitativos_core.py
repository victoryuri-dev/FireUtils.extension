# -*- coding: utf-8 -*-
"""
quantitativos_core.py — Fire Utils · lib/
Lógica central do botão "Gravar Quantitativos": mostra uma janela com um
checkbox por medida de quantitativo disponível (Extintores, Sinalização de
Emergência, ...) e, pra cada uma marcada, roda a coleta no modelo, grava no
firedata.json e envia pro site (Supabase) — mesmo fluxo que antes vivia em
botões separados (Gravar Dados de Extintores / Gravar Dados de
Sinalização), agora unificado numa única janela.

Diferente dos botões antigos (que paravam tudo num forms.alert + script.exit
ao primeiro erro), aqui cada medida selecionada roda isolada: se uma falhar
(ex.: erro ao criar parâmetro), a falha é reportada e as demais continuam.

Pra adicionar uma nova medida a essa janela:
  1. no módulo <medida>/calc.py, exponha coletar_itens(doc) (+ agrupar, se a
     medida precisar agregar por algo antes de enviar — ver
     sinalizacao/calc.py) e salvar_cache(itens, projeto_dir);
  2. registre uma entrada em MEDIDAS aqui embaixo;
  3. acrescente o CheckBox x:Name="Chk_<chave>" correspondente em
     quantitativos_opcoes.xaml.

Função pública
--------------
gravar_quantitativos(doc, output)
"""

import os

from pyrevit import forms

import extintores.calc as extintores_calc
import extintores.params as extintores_params
import sinalizacao.calc as sinalizacao_calc
import iluminacao.calc as iluminacao_calc

_XAML_OPCOES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), u"quantitativos_opcoes.xaml")


# ===========================================================================
# REGISTRO DE MEDIDAS
# ===========================================================================
class _Medida(object):
    def __init__(self, chave, rotulo, coletar, salvar, rotulo_item,
                 preparar=None, agrupar=None, mensagem_vazia=None):
        self.chave          = chave
        self.rotulo         = rotulo
        self.preparar       = preparar    # doc -> log [(nome, status), ...], opcional
        self.coletar        = coletar     # doc -> [item, ...]
        self.agrupar        = agrupar     # [item, ...] -> [item, ...], opcional
        self.salvar         = salvar      # (itens, projeto_dir) -> path
        self.rotulo_item    = rotulo_item # item -> texto markdown de uma linha
        self.mensagem_vazia = mensagem_vazia or u"Nenhum item encontrado."


def _rotulo_extintor(it):
    return u"**{}** | {} | {} | {} {}".format(
        it[u"pavimento"] or u"(sem pavimento)",
        it[u"ambiente"] or u"(sem ambiente)",
        it[u"tipo"] or u"(sem tipo)",
        it[u"capacidade"],
        u"({} kg)".format(it[u"carga"]) if it.get(u"carga") is not None else u"",
    )


def _rotulo_placa(it):
    return u"**{}** — {}".format(it[u"tipoPlaca"], it[u"quantidade"])


def _rotulo_iluminacao(it):
    return u"**{}** | {} | {} {} — {}".format(
        it[u"pavimento"] or u"(sem pavimento)",
        it[u"tipoBase"],
        it[u"tipoLampada"] or u"(sem tipo de lâmpada)",
        u"({} lm)".format(it[u"fluxoLuminosoLm"]) if it.get(u"fluxoLuminosoLm") else u"",
        it[u"quantidade"],
    )


MEDIDAS = [
    _Medida(
        chave=u"extintores",
        rotulo=u"Extintores",
        preparar=lambda doc: extintores_params.create_extinguisher_params(doc),
        coletar=extintores_calc.coletar_itens,
        salvar=extintores_calc.salvar_cache,
        rotulo_item=_rotulo_extintor,
        mensagem_vazia=(
            u"Nenhum extintor encontrado — verifique se as instâncias "
            u"estão na categoria 'Proteção contra Incêndio' e se o "
            u"parâmetro 'Capacidade Extintora' (instância ou tipo) está "
            u"preenchido."
        ),
    ),
    _Medida(
        chave=u"sinalizacao",
        rotulo=u"Sinalização de Emergência",
        coletar=sinalizacao_calc.coletar_itens,
        agrupar=sinalizacao_calc.agrupar_por_placa,
        salvar=sinalizacao_calc.salvar_cache,
        rotulo_item=_rotulo_placa,
        mensagem_vazia=(
            u"Nenhuma placa de sinalização de emergência encontrada — "
            u"verifique se as instâncias estão na categoria 'Dispositivos "
            u"de Segurança' e se o parâmetro de tipo 'Código da Placa' "
            u"está preenchido."
        ),
    ),
    _Medida(
        chave=u"iluminacao",
        rotulo=u"Iluminação de Emergência",
        coletar=iluminacao_calc.coletar_itens,
        agrupar=iluminacao_calc.agrupar_por_pavimento,
        salvar=iluminacao_calc.salvar_cache,
        rotulo_item=_rotulo_iluminacao,
        mensagem_vazia=(
            u"Nenhum equipamento de aclaramento encontrado — verifique se "
            u"as instâncias estão na categoria 'Luminárias' e se o "
            u"parâmetro de tipo 'Tipo de Luminaria' está preenchido com "
            u"'SLIM' ou '2 FAROIS'."
        ),
    ),
]


# ===========================================================================
# JANELA — seleção das medidas a gravar/enviar
# ===========================================================================
class _JanelaQuantitativos(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, _XAML_OPCOES_PATH)
        self.confirmado = False
        self._checkboxes = dict(
            (m.chave, getattr(self, u"Chk_" + m.chave)) for m in MEDIDAS
        )

    def medidas_selecionadas(self):
        return [m for m in MEDIDAS if self._checkboxes[m.chave].IsChecked]

    def on_cancel(self, sender, args):
        self.Close()

    def on_ok(self, sender, args):
        if not self.medidas_selecionadas():
            self.TxtStatus.Text = u"Selecione ao menos uma medida."
            return
        self.confirmado = True
        self.Close()


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================
def _processar_medida(medida, doc, projeto_dir):
    """Processa uma medida e retorna a lista de linhas do relatório —
    ver gravar_quantitativos. Nada é impresso no console aqui: sucesso e
    falha (ex.: erro ao preparar parâmetros/gravar) são sempre parte do
    mesmo relatório, mostrado no final numa janela com OK."""
    linhas = []
    if medida.preparar:
        try:
            log = medida.preparar(doc)
            for nome, status in (log or []):
                icone = u"✔" if status == u"criado" else u"–"
                linhas.append(u"  {} {} -> {}".format(icone, nome, status))
        except Exception as e:
            linhas.append(u"Falhou ao preparar parâmetros: {}".format(e))
            return linhas

    itens_brutos = medida.coletar(doc)
    if not itens_brutos:
        linhas.append(medida.mensagem_vazia)
        return linhas

    itens = medida.agrupar(itens_brutos) if medida.agrupar else itens_brutos

    if medida.agrupar:
        linhas.append(u"✔ {} instância(s) encontrada(s) — {} item(ns) após agregação.".format(
            len(itens_brutos), len(itens)))
    else:
        linhas.append(u"✔ {} item(ns) encontrado(s).".format(len(itens)))

    try:
        path, ok, motivo = medida.salvar(itens, projeto_dir)
    except Exception as e:
        linhas.append(u"Falhou ao gravar/enviar: {}".format(e))
        return linhas

    linhas.append(u"✔ Dados gravados em {}".format(path))
    if ok:
        linhas.append(u"✔ Enviado pro site.")
    else:
        # Nunca é exceção (ver sync.enviar) — o caso mais comum é o
        # arquivo Revit ainda não estar vinculado a um projeto/estrutura
        # no Dashboard (dockpane). Reporta aqui porque antes disso era
        # silencioso: o firedata.json gravava certinho e ninguém percebia
        # que nada tinha chegado no site.
        linhas.append(u"⚠ Não enviado pro site: {}".format(motivo))

    return linhas


# ===========================================================================
# API PÚBLICA
# ===========================================================================
def gravar_quantitativos(doc, output):
    if not doc.PathName:
        forms.alert(
            u"O projeto Revit não está salvo.\n\n"
            u"Salve o arquivo (.rvt) antes de prosseguir — os dados de\n"
            u"quantitativos são gravados na pasta do projeto.",
            title=u"Fire Utils — Salve o projeto",
            warn_icon=True,
        )
        return

    projeto_dir = os.path.dirname(doc.PathName)

    janela = _JanelaQuantitativos()
    janela.ShowDialog()
    if not janela.confirmado:
        return

    # Relatório inteiro (sucesso, vazio ou falha pontual por medida) vai
    # pra uma janela com OK no final, em vez de linha a linha no console —
    # cada medida já roda isolada (ver docstring do módulo), então mesmo
    # uma falha pontual aqui é só mais uma linha do mesmo relatório.
    blocos = []
    for medida in janela.medidas_selecionadas():
        linhas = _processar_medida(medida, doc, projeto_dir)
        blocos.append(u"{}\n{}".format(medida.rotulo, u"\n".join(linhas)))

    forms.alert(u"\n\n".join(blocos), title=u"Fire Utils — Gravar Quantitativos")
