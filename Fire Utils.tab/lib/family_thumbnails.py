# -*- coding: utf-8 -*-
"""
family_thumbnails.py — Fire Utils · lib/
Gera (e mantém em cache no disco) uma miniatura PNG com a geometria real de
uma família (.rfa), abrindo o arquivo como documento de família e capturando
o Autodesk.Revit.UI.PreviewControl — o mesmo mecanismo que o próprio Revit
usa para pré-visualizar famílias antes de carregá-las.

A primeira geração de cada família custa alguns segundos (é preciso abrir o
documento da família); chamadas seguintes usam o PNG já salvo em
lib/family_library/.thumb_cache/ e são instantâneas.

Qualquer falha aqui é sinalizada com retorno None — quem chama deve manter
um retrato alternativo (ex.: monograma) como fallback.
"""

import io
import os
import hashlib
import datetime
import traceback

import clr
clr.AddReference(u"RevitAPI")
clr.AddReference(u"RevitAPIUI")
clr.AddReference(u"System.Windows.Forms")
clr.AddReference(u"System.Drawing")

from Autodesk.Revit.DB import FilteredElementCollector, View3D
from Autodesk.Revit.UI import PreviewControl

import System.Windows.Forms as WinForms
import System.Drawing as Drawing
import System.Drawing.Imaging as DrawingImaging

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_LIB_DIR, u"family_library", u".thumb_cache")
_LOG_PATH = os.path.join(_CACHE_DIR, u"erro.log")

TAMANHO = 160  # px — lado do quadrado gerado


def _garantir_cache_dir():
    if not os.path.isdir(_CACHE_DIR):
        try:
            os.makedirs(_CACHE_DIR)
        except OSError:
            pass


def _registrar(mensagem):
    """
    Grava uma linha de diagnóstico em lib/family_library/.thumb_cache/erro.log.
    Nunca lança exceção — geração de thumbnail não pode travar por causa do
    próprio log de erro.
    """
    print(u"[Fire Utils] Carregador de Famílias — {}".format(mensagem))
    try:
        _garantir_cache_dir()
        with io.open(_LOG_PATH, u"a", encoding=u"utf-8") as arquivo:
            carimbo = datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S")
            arquivo.write(u"[{}] {}\r\n".format(carimbo, mensagem))
    except Exception:
        pass


def _caminho_cache(caminho_rfa):
    try:
        assinatura = u"{}|{}".format(caminho_rfa, os.path.getmtime(caminho_rfa))
    except OSError:
        assinatura = caminho_rfa
    chave = hashlib.md5(assinatura.encode(u"utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, chave + u".png")


def obter_thumb_cacheada(caminho_rfa):
    """Retorna o caminho do PNG já em cache, ou None se ainda não foi gerado."""
    destino = _caminho_cache(caminho_rfa)
    return destino if os.path.exists(destino) else None


def _view_para_preview(familia_doc):
    for view in FilteredElementCollector(familia_doc).OfClass(View3D):
        if not view.IsTemplate:
            return view
    return None


def _bitmap_parece_vazio(bitmap):
    """
    Heurística: se uma amostra de pixels do bitmap é toda da mesma cor,
    provavelmente o DrawToBitmap não capturou geometria nenhuma (sintoma
    comum quando o controle renderiza via DirectX e não responde a WM_PRINT).
    """
    try:
        passo = max(1, TAMANHO // 8)
        cor_ref = bitmap.GetPixel(0, 0)
        ref = (cor_ref.R, cor_ref.G, cor_ref.B)
        for x in range(0, TAMANHO, passo):
            for y in range(0, TAMANHO, passo):
                px = bitmap.GetPixel(x, y)
                if (px.R, px.G, px.B) != ref:
                    return False
        return True
    except Exception:
        return False


def gerar_thumb(app, caminho_rfa):
    """
    Abre a família em segundo plano, captura uma imagem da geometria real e
    salva em cache. Retorna o caminho do PNG gerado, ou None em caso de falha.
    Qualquer falha (ou suspeita de imagem em branco) é registrada em
    lib/family_library/.thumb_cache/erro.log.

    Deve ser chamado a partir do contexto de API do Revit (mesma thread
    principal usada pelo comando que abriu o Carregador de Famílias).
    """
    nome_arquivo = os.path.basename(caminho_rfa)
    destino = _caminho_cache(caminho_rfa)
    if os.path.exists(destino):
        return destino

    if not os.path.exists(caminho_rfa):
        _registrar(u"{}: arquivo .rfa não encontrado em disco ({})".format(
            nome_arquivo, caminho_rfa))
        return None

    _garantir_cache_dir()

    familia_doc = None
    form = None
    try:
        try:
            familia_doc = app.OpenDocumentFile(caminho_rfa)
        except Exception as ex:
            _registrar(u"{}: falha ao abrir o arquivo como documento — {}".format(
                nome_arquivo, ex))
            return None

        view = _view_para_preview(familia_doc)
        if view is None:
            _registrar(
                u"{}: nenhuma vista 3D (não-template) encontrada no arquivo "
                u"de família — sem vista não há como gerar preview.".format(
                    nome_arquivo)
            )
            return None

        try:
            preview = PreviewControl(familia_doc, view.Id)
            preview.Size = Drawing.Size(TAMANHO, TAMANHO)

            form = WinForms.Form()
            form.ShowInTaskbar = False
            # "None" é palavra reservada em Python; acessa o membro do enum via getattr.
            form.FormBorderStyle = getattr(WinForms.FormBorderStyle, u"None")
            form.StartPosition = WinForms.FormStartPosition.Manual
            form.Location = Drawing.Point(-32000, -32000)
            form.Size = Drawing.Size(TAMANHO, TAMANHO)
            form.Controls.Add(preview)
            form.Show()
            WinForms.Application.DoEvents()

            bitmap = Drawing.Bitmap(TAMANHO, TAMANHO)
            preview.DrawToBitmap(bitmap, Drawing.Rectangle(0, 0, TAMANHO, TAMANHO))
        except Exception as ex:
            _registrar(
                u"{}: falha ao capturar o PreviewControl — {}".format(
                    nome_arquivo, ex)
            )
            return None

        if _bitmap_parece_vazio(bitmap):
            bitmap.Dispose()
            _registrar(
                u"{}: imagem capturada parece em branco/uniforme — o "
                u"PreviewControl pode não suportar DrawToBitmap neste "
                u"ambiente (renderização via DirectX). Mantendo monograma.".format(
                    nome_arquivo)
            )
            return None

        bitmap.Save(destino, DrawingImaging.ImageFormat.Png)
        bitmap.Dispose()

        return destino
    except Exception as ex:
        _registrar(u"{}: falha inesperada — {}\n{}".format(
            nome_arquivo, ex, traceback.format_exc()))
        return None
    finally:
        if form is not None:
            try:
                form.Close()
                form.Dispose()
            except Exception:
                pass
        if familia_doc is not None:
            try:
                familia_doc.Close(False)
            except Exception:
                pass
