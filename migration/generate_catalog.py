#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_catalog.py — Fire Utils · migration/

Fase 1 do plano de migração (PLANO_DE_MIGRACAO_FAMILY_LIBRARY): varre a
biblioteca de famílias atual do plugin (Fire Utils.tab/lib/family_library/)
e gera dois arquivos em migration/output/:

  catalog.json          Metadados de categorias e famílias — é o arquivo que
                         vai pro Bucket Público (plugin-assets) e que o React
                         consome direto na inicialização da galeria.

  upload_manifest.json  Lista de (arquivo local -> bucket/chave de destino)
                         para todo ícone, thumbnail e .rfa encontrado. É o
                         input do upload_to_supabase.py (Fase 1, próximo
                         passo) — mantém a geração do catálogo (offline, sem
                         credenciais) separada do upload de fato.

Roda fora do plugin, com Python 3 puro (sem dependência do clr/Revit API que
family_loader.py usa) — não precisa estar instalado no Revit/pyRevit, só na
máquina de quem administra a biblioteca.

Uso:
    python3 migration/generate_catalog.py
    python3 migration/generate_catalog.py --library-dir "outra/pasta"
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Convenções compartilhadas com o plugin (Fire Utils.tab/lib/family_loader.py)
# — mantidas em sincronia manualmente, já que este script roda fora do
# plugin e não pode importar aquele módulo (ele exige clr/RevitAPI).
# ---------------------------------------------------------------------------
_PREVIEWS_DIRNAME = u".previews"
_CATEGORIA_GERAL = u"Geral"
_CATEGORIA_TODAS = u"Todas"
_ICONE_EXTENSOES = [u".png", u".jpg", u".jpeg"]  # .svg não é usado: não renderiza no WebView2/WPF nem precisa aqui, o React lida com raster direto

_MIGRATION_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_MIGRATION_DIR)
_DEFAULT_LIBRARY_DIR = os.path.join(
    _REPO_ROOT, u"Fire Utils.tab", u"lib", u"family_library"
)
_OUTPUT_DIR = os.path.join(_MIGRATION_DIR, u"output")

# Convenção de bucket/chave — usada tanto no catalog.json (campos *_key)
# quanto no upload_manifest.json. Mantida em um único lugar pra Fase 1
# (upload) e o frontend React (Fase 2) lerem exatamente a mesma coisa.
BUCKET_PUBLICO = u"plugin-assets"
BUCKET_PRIVADO = u"revit-families"


def slugify(texto):
    """'Extintor Portátil - ABC' -> 'extintor-portatil-abc' — vira nome de
    arquivo/chave de bucket, então precisa ser url-safe e sem acentos."""
    sem_acento = unicodedata.normalize(u"NFKD", texto)
    sem_acento = sem_acento.encode(u"ascii", u"ignore").decode(u"ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", u"-", sem_acento).strip(u"-").lower()
    return slug or u"item"


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, u"rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos_rfa(pasta):
    try:
        return sorted(f for f in os.listdir(pasta) if f.lower().endswith(u".rfa"))
    except OSError:
        return []


def _localizar_icone(pasta):
    for extensao in _ICONE_EXTENSOES:
        caminho = os.path.join(pasta, u"icon" + extensao)
        if os.path.isfile(caminho):
            return caminho
    return None


def _localizar_preview(library_dir, categoria, nome_arquivo_sem_ext):
    caminho = os.path.join(
        library_dir, _PREVIEWS_DIRNAME, categoria, nome_arquivo_sem_ext + u".png"
    )
    return caminho if os.path.isfile(caminho) else None


class ColetaCatalogo(object):
    """Acumula categorias/famílias e o manifesto de upload conforme varre a
    biblioteca — mesma lógica de duas passadas usada por
    family_loader.listar_familias()/listar_categorias(), reimplementada aqui
    em Python 3 puro."""

    def __init__(self, library_dir):
        self.library_dir = library_dir
        self.categorias = {}     # category_id -> dict
        self.familias = []
        self.manifest = []       # [{local_path, bucket, key, content_type}]
        self.nomes_vistos = set()  # dedup por nome (case-insensitive), igual ao plugin

    def _registrar_upload(self, local_path, bucket, key, content_type):
        self.manifest.append({
            u"local_path": os.path.relpath(local_path, _REPO_ROOT).replace(os.sep, u"/"),
            u"bucket": bucket,
            u"key": key,
            u"content_type": content_type,
        })

    def _registrar_categoria(self, nome_categoria, pasta_categoria, category_id):
        if category_id in self.categorias:
            return
        icon_key = None
        caminho_icone = _localizar_icone(pasta_categoria)
        if caminho_icone:
            icon_key = u"icons/{}{}".format(category_id, os.path.splitext(caminho_icone)[1].lower())
            self._registrar_upload(caminho_icone, BUCKET_PUBLICO, icon_key, _content_type(caminho_icone))
        self.categorias[category_id] = {
            u"id": category_id,
            u"name": nome_categoria,
            u"icon_key": icon_key,
        }

    def _registrar_familia(self, nome_categoria, category_id, caminho_rfa):
        nome = os.path.splitext(os.path.basename(caminho_rfa))[0]
        chave_dedup = nome.lower()
        if chave_dedup in self.nomes_vistos:
            print(u"[AVISO] Família duplicada ignorada: '{}' ({})".format(nome, caminho_rfa))
            return
        self.nomes_vistos.add(chave_dedup)

        family_id = u"{}__{}".format(category_id, slugify(nome))
        storage_key = u"{}/{}.rfa".format(category_id, slugify(nome))
        self._registrar_upload(caminho_rfa, BUCKET_PRIVADO, storage_key, u"application/octet-stream")

        thumbnail_key = None
        caminho_preview = _localizar_preview(self.library_dir, nome_categoria, nome)
        if caminho_preview:
            thumbnail_key = u"thumbnails/{}/{}.png".format(category_id, slugify(nome))
            self._registrar_upload(caminho_preview, BUCKET_PUBLICO, thumbnail_key, u"image/png")

        self.familias.append({
            u"id": family_id,
            u"name": nome,
            u"category_id": category_id,
            u"category": nome_categoria,
            u"thumbnail_key": thumbnail_key,
            u"storage_key": storage_key,
            u"size_bytes": os.path.getsize(caminho_rfa),
            u"sha256": sha256_arquivo(caminho_rfa),
        })

    def coletar(self):
        if not os.path.isdir(self.library_dir):
            raise SystemExit(u"Pasta da biblioteca não encontrada: {}".format(self.library_dir))

        # Ícone da categoria agregada "Todas" (fica solto na raiz da lib).
        self._registrar_categoria(_CATEGORIA_TODAS, self.library_dir, slugify(_CATEGORIA_TODAS))

        for item in sorted(os.listdir(self.library_dir)):
            if item == _PREVIEWS_DIRNAME:
                continue
            caminho_item = os.path.join(self.library_dir, item)

            if os.path.isdir(caminho_item):
                category_id = slugify(item)
                self._registrar_categoria(item, caminho_item, category_id)
                for nome_arquivo in _arquivos_rfa(caminho_item):
                    self._registrar_familia(item, category_id, os.path.join(caminho_item, nome_arquivo))
            elif item.lower().endswith(u".rfa"):
                category_id = slugify(_CATEGORIA_GERAL)
                self._registrar_categoria(_CATEGORIA_GERAL, self.library_dir, category_id)
                self._registrar_familia(_CATEGORIA_GERAL, category_id, caminho_item)

        # "Todas" não é uma pasta de família de verdade — não deve aparecer
        # na lista de categorias filtráveis do catálogo, só fornece o ícone
        # agregador que o React usa pro tile "Todas" da galeria.
        icone_todas = self.categorias.pop(slugify(_CATEGORIA_TODAS))[u"icon_key"]

        categorias_ordenadas = sorted(self.categorias.values(), key=lambda c: c[u"name"])
        familias_ordenadas = sorted(self.familias, key=lambda f: (f[u"category"], f[u"name"]))

        catalogo = {
            u"generated_at": datetime.now(timezone.utc).strftime(u"%Y-%m-%dT%H:%M:%SZ"),
            u"todas_icon_key": icone_todas,
            u"categories": categorias_ordenadas,
            u"families": familias_ordenadas,
        }
        return catalogo, self.manifest


def _content_type(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    return {
        u".png": u"image/png",
        u".jpg": u"image/jpeg",
        u".jpeg": u"image/jpeg",
    }.get(ext, u"application/octet-stream")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        u"--library-dir", default=_DEFAULT_LIBRARY_DIR,
        help=u"Caminho da pasta family_library (padrão: %(default)s)",
    )
    parser.add_argument(
        u"--output-dir", default=_OUTPUT_DIR,
        help=u"Pasta onde salvar catalog.json e upload_manifest.json (padrão: %(default)s)",
    )
    args = parser.parse_args()

    coleta = ColetaCatalogo(args.library_dir)
    catalogo, manifest = coleta.coletar()

    os.makedirs(args.output_dir, exist_ok=True)
    caminho_catalogo = os.path.join(args.output_dir, u"catalog.json")
    caminho_manifest = os.path.join(args.output_dir, u"upload_manifest.json")

    with open(caminho_catalogo, u"w", encoding=u"utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    with open(caminho_manifest, u"w", encoding=u"utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total_rfa_sem_icone = sum(1 for c in catalogo[u"categories"] if not c[u"icon_key"])
    total_sem_thumbnail = sum(1 for fam in catalogo[u"families"] if not fam[u"thumbnail_key"])

    print(u"Catálogo gerado: {}".format(caminho_catalogo))
    print(u"Manifesto de upload gerado: {}".format(caminho_manifest))
    print(u"")
    print(u"  Categorias: {}".format(len(catalogo[u"categories"])))
    print(u"  Famílias:   {}".format(len(catalogo[u"families"])))
    print(u"  Arquivos a enviar: {}".format(len(manifest)))
    if total_rfa_sem_icone:
        print(u"  [AVISO] {} categoria(s) sem icon.png/.jpg.".format(total_rfa_sem_icone))
    if total_sem_thumbnail:
        print(u"  [AVISO] {} família(s) sem preview em .previews/.".format(total_sem_thumbnail))
    if not catalogo[u"todas_icon_key"]:
        print(u"  [AVISO] Sem icon.png/.jpg na raiz de family_library/ para a categoria 'Todas'.")


if __name__ == u"__main__":
    main()
