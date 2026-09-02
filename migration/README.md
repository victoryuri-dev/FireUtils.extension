# Migração da Family Library para o Supabase (Fase 1)

Scripts locais, fora do plugin, que preparam a migração descrita em
`PLANO_DE_MIGRACAO_FAMILY_LIBRARY`: hoje os `.rfa` moram dentro do próprio
pacote do plugin (`Fire Utils.tab/lib/family_library/`); a nova arquitetura
move o acervo para o Supabase e o plugin passa a baixar sob demanda.

Estes scripts **não alteram o plugin** — só preparam os dados que vão pro
Supabase. Rodam com Python 3 puro (sem pyRevit/Revit aberto).

## 1. Criar o projeto e os buckets no Supabase

Antes de rodar qualquer coisa aqui, crie manualmente no [supabase.com](https://supabase.com):

1. Um projeto novo.
2. Bucket **público** chamado `plugin-assets` — vai guardar `catalog.json`,
   os ícones de categoria e os thumbnails das famílias.
3. Bucket **privado** chamado `revit-families` — vai guardar os `.rfa`,
   protegido por Row Level Security (RLS); só usuário autenticado gera
   Signed URL pra baixar (isso é configurado na Fase 2, junto do frontend).

Pegue em **Settings → API** a `Project URL` e a `service_role` key (não a
`anon` key — essa aqui tem permissão de bypass de RLS, só usa local, nunca
no frontend React).

## 2. Gerar o catálogo (offline, sem credenciais)

```bash
python3 migration/generate_catalog.py
```

Varre `Fire Utils.tab/lib/family_library/` e gera em `migration/output/`:

- **`catalog.json`** — metadados de categorias e famílias (o arquivo que o
  React vai consumir direto do bucket público na Fase 2).
- **`upload_manifest.json`** — lista de todo arquivo local (ícone,
  thumbnail, `.rfa`) e pra onde ele vai (bucket + chave).

Revise o `catalog.json` gerado antes de subir — o script avisa no final se
alguma categoria está sem ícone ou família sem thumbnail (não é erro, só
cai no fallback visual de sempre).

## 3. Subir pro Supabase

```bash
cp migration/.env.example migration/.env
# edite migration/.env com sua SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY

pip install requests   # se ainda não tiver

python3 migration/upload_to_supabase.py              # dry-run — só mostra o que subiria
python3 migration/upload_to_supabase.py --execute    # sobe de verdade
```

Reenviar depois de adicionar/trocar famílias é seguro — o upload sobrescreve
(`x-upsert`) em vez de duplicar.

## Convenção de chaves nos buckets

```
plugin-assets/ (público)
├── catalog.json
├── icons/<category_id>.png
└── thumbnails/<category_id>/<family_id>.png

revit-families/ (privado, RLS)
└── <category_id>/<family_id>.rfa
```

`category_id`/`family_id` são slugs (sem acento, minúsculo, hífen) gerados a
partir do nome da categoria/família — ex.: "Extintor de Incêndio" →
`extintor-de-incendio`.

## Próximos passos (fora do escopo destes scripts)

- Fase 2: frontend React consumindo `catalog.json` do bucket público e
  gerando Signed URL do `.rfa` no clique (via `@supabase/supabase-js`).
- Fase 3: Dockable Pane hospedando o WebView2 e a ponte JS↔Python.
- Fase 4: cache local (`%AppData%`) + `LoadFamily` via `IExternalEventHandler`.
