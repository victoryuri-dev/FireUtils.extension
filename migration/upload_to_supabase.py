#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_to_supabase.py — Fire Utils · migration/

Fase 1 do plano de migração: lê o catalog.json e o upload_manifest.json
gerados por generate_catalog.py (migration/output/) e envia tudo pro
Supabase — ícones, thumbnails e catalog.json pro Bucket Público
(plugin-assets), arquivos .rfa pro Bucket Privado (revit-families).

Não faz nada de destrutivo sem confirmação explícita: por padrão roda em
modo --dry-run (só mostra o que seria enviado). Passe --execute pra
realmente subir os arquivos.

Credenciais NUNCA ficam no código nem no git — vêm de variáveis de
ambiente (ou de um migration/.env local, que está no .gitignore):

    SUPABASE_URL               ex.: https://xxxxxxxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY  chave service_role do projeto (Settings > API)
                                — tem permissão de bypass de RLS, use só
                                aqui no script local, nunca no frontend.

Uso:
    python3 migration/upload_to_supabase.py                 # dry-run
    python3 migration/upload_to_supabase.py --execute        # upload de verdade
    python3 migration/upload_to_supabase.py --execute --only-changed
"""

import argparse
import json
import os
import sys

_MIGRATION_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_MIGRATION_DIR)
_OUTPUT_DIR = os.path.join(_MIGRATION_DIR, u"output")
_ENV_FILE = os.path.join(_MIGRATION_DIR, u".env")


def _carregar_dotenv(caminho):
    """Carregador mínimo de .env (KEY=VALUE por linha) — evita depender do
    pacote python-dotenv só pra isso. Nunca sobrescreve uma env var que já
    esteja definida no ambiente (ambiente real tem prioridade)."""
    if not os.path.isfile(caminho):
        return
    with open(caminho, u"r", encoding=u"utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith(u"#") or u"=" not in linha:
                continue
            chave, _, valor = linha.partition(u"=")
            chave = chave.strip()
            valor = valor.strip().strip(u'"').strip(u"'")
            os.environ.setdefault(chave, valor)


def _credenciais():
    _carregar_dotenv(_ENV_FILE)
    url = os.environ.get(u"SUPABASE_URL", u"").rstrip(u"/")
    chave = os.environ.get(u"SUPABASE_SERVICE_ROLE_KEY", u"")
    if not url or not chave:
        sys.exit(
            u"Faltam credenciais. Defina SUPABASE_URL e "
            u"SUPABASE_SERVICE_ROLE_KEY como variáveis de ambiente, ou crie "
            u"migration/.env a partir de migration/.env.example."
        )
    return url, chave


def _upload(session, supabase_url, bucket, key, local_path, content_type):
    """Sobe um arquivo pro Supabase Storage via REST, sobrescrevendo se já
    existir (x-upsert). Retorna (ok, mensagem)."""
    endpoint = u"{}/storage/v1/object/{}/{}".format(supabase_url, bucket, key)
    with open(local_path, u"rb") as f:
        dados = f.read()
    resposta = session.post(
        endpoint,
        data=dados,
        headers={
            u"Content-Type": content_type,
            u"x-upsert": u"true",
        },
        timeout=120,
    )
    if resposta.status_code in (200, 201):
        return True, u"OK"
    return False, u"{} — {}".format(resposta.status_code, resposta.text[:300])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(u"--output-dir", default=_OUTPUT_DIR,
                         help=u"Pasta com catalog.json/upload_manifest.json (padrão: %(default)s)")
    parser.add_argument(u"--execute", action=u"store_true",
                         help=u"Sem esta flag, roda em modo dry-run (não envia nada).")
    args = parser.parse_args()

    caminho_catalogo = os.path.join(args.output_dir, u"catalog.json")
    caminho_manifest = os.path.join(args.output_dir, u"upload_manifest.json")

    if not os.path.isfile(caminho_catalogo) or not os.path.isfile(caminho_manifest):
        sys.exit(
            u"catalog.json/upload_manifest.json não encontrados em {}.\n"
            u"Rode primeiro: python3 migration/generate_catalog.py".format(args.output_dir)
        )

    with open(caminho_manifest, u"r", encoding=u"utf-8") as f:
        manifest = json.load(f)

    print(u"{} arquivo(s) no manifesto (ícones + thumbnails + .rfa) + catalog.json.".format(len(manifest)))

    if not args.execute:
        print(u"\n[DRY RUN] Nada será enviado. Prévia dos primeiros itens:\n")
        for item in manifest[:15]:
            print(u"  {} -> {}/{}".format(item[u"local_path"], item[u"bucket"], item[u"key"]))
        if len(manifest) > 15:
            print(u"  ... e mais {} arquivo(s).".format(len(manifest) - 15))
        print(u"\nRode de novo com --execute para enviar de verdade ao Supabase.")
        return

    try:
        import requests
    except ImportError:
        sys.exit(u"Falta o pacote 'requests'. Instale com: pip install requests")

    supabase_url, service_role_key = _credenciais()
    session = requests.Session()
    session.headers.update({
        u"Authorization": u"Bearer {}".format(service_role_key),
        u"apikey": service_role_key,
    })

    # catalog.json também sobe pro bucket público, na raiz — é o arquivo que
    # o React lê direto na inicialização da galeria.
    itens_para_subir = list(manifest) + [{
        u"local_path": os.path.relpath(caminho_catalogo, _REPO_ROOT).replace(os.sep, u"/"),
        u"bucket": u"plugin-assets",
        u"key": u"catalog.json",
        u"content_type": u"application/json",
    }]

    ok_count = 0
    falhas = []
    for i, item in enumerate(itens_para_subir, 1):
        local_path = os.path.join(_REPO_ROOT, item[u"local_path"])
        print(u"[{}/{}] {}/{} ...".format(i, len(itens_para_subir), item[u"bucket"], item[u"key"]), end=u" ")
        sys.stdout.flush()
        ok, msg = _upload(session, supabase_url, item[u"bucket"], item[u"key"], local_path, item[u"content_type"])
        print(u"OK" if ok else u"FALHOU: {}".format(msg))
        if ok:
            ok_count += 1
        else:
            falhas.append((item, msg))

    print(u"\n{}/{} enviados com sucesso.".format(ok_count, len(itens_para_subir)))
    if falhas:
        print(u"\nFalhas:")
        for item, msg in falhas:
            print(u"  {}/{}: {}".format(item[u"bucket"], item[u"key"], msg))
        sys.exit(1)


if __name__ == u"__main__":
    main()
