# Prompt para o chat que vai criar o repositório `FireUtils.admin`

> Copie tudo abaixo da linha e cole no novo chat.

---

Você vai criar do zero o painel de administração do **Fire Utils** num repositório novo, `victoryuri-dev/FireUtils.admin` (privado). Fale com o usuário em português do Brasil. Trabalhe só nesse repositório; mudanças em outros repositórios estão listadas em "Entregas fora deste repositório" e só se fazem com autorização explícita.

## 1. Contexto do ecossistema

O Fire Utils é um plugin de proteção contra incêndio para Autodesk Revit, com três repositórios e um projeto Supabase compartilhado:

| Repositório | O que é |
|---|---|
| `victoryuri-dev/ETOS.FireUtils` (hoje renomeado `FireUtils`) | O site (React + Vite + Tailwind, no Vercel) **e dono das migrações e Edge Functions do Supabase** (`supabase/migrations`, `supabase/functions`). |
| `victoryuri-dev/FireUtils.extension` | O plugin pyRevit (Python/IronPython) e o **webapp da dockpane** (`webapp/`, React + Vite, no Vercel), que roda dentro do Revit (WebView2). |
| `victoryuri-dev/FireUtils.admin` | **Este, novo.** Painel só para o administrador. |

- Projeto Supabase: `https://lngvagifcukglgdjildw.supabase.co`. O app usa **somente a anon key** no navegador (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`).
- Autenticação: Supabase Auth (e-mail e senha), a mesma conta que os clientes usam no site e na dockpane.
- Identidade visual: tema escuro `#101014`, vermelho da marca `#C0152A`, títulos em **Space Grotesk**, texto e números em **Inter**, logo em `https://github.com/victoryuri-dev/FireUtils.extension` (`webapp/src/assets/icons/fireutils-logo.svg`, símbolo em `currentColor`). Interface densa e sóbria, em português. Use o webapp da dockpane como referência de estilo (`webapp/src/App.css`, `index.css`).

## 2. O que construir

Um app **React + Vite** (JavaScript, mesmo estilo dos outros repositórios), publicado no Vercel, com:

1. **Login** (e-mail/senha). Só entra no painel quem for administrador; os demais veem "sem permissão" e são deslogados.
2. **Menu lateral (aside) fixo** para navegar entre telas dedicadas, nesta ordem:
   - **Usuários** (e licenças)
   - **Versões** (versionamento e patch notes)
   - **Biblioteca** (famílias do Revit)
3. Cada seção é uma tela própria (rota própria), com listagem, filtros, formulários e confirmações para ações destrutivas.

Faça em **fases**, uma por vez, e valide com o usuário ao fim de cada uma: **Fase 0** (base, login, guarda de admin), **Fase 1** Usuários e licenças, **Fase 2** Versões, **Fase 3** Biblioteca.

## 3. Segurança (inegociável)

- **Nunca** coloque a `service_role` do Supabase, a chave privada de licença nem a chave privada de assinatura de pacotes no navegador, no repositório, em `VITE_*` ou em logs.
- Quem é administrador vem de uma tabela `admins` + função `public.is_admin()` (`security definer`, `stable`), consultada nas **políticas RLS**. Nada de "admin" decidido só no front-end.
- Operações que exigem privilégio de serviço (listar/criar/banir usuários do Auth) vão em **Edge Functions** que: (a) recebem o JWT do chamador, (b) verificam `is_admin()` antes de qualquer coisa, (c) usam a service role só dentro da function, (d) validam todas as entradas, (e) gravam uma linha em `admin_auditoria` (quem, ação, alvo, antes/depois, quando).
- O administrador inicial é **`victoryuri.eng@gmail.com`** (inserido na tabela `admins` pela migração, por e-mail → `user_id`). Outros entram depois, pelo painel.
- Toda ação destrutiva (excluir usuário, despublicar versão, excluir família) pede confirmação digitando o nome do item.
- Sem dependências desnecessárias; fixe versões; nenhum script de CDN fora de `cdnjs`/`jsdelivr`/`unpkg` com versão exata.

## 4. Dados que já existem no Supabase

- `auth.users`, e `public.perfis` (`user_id`, `nome`, `telefone`, `responsavel_tecnico`, `atualizado_em`).
- `public.licencas`: `id`, `user_id`, `modulo` (`saidas` | `memorial` | `hidrantes` | `pro`), `plano` (texto livre, ex.: "Anual"), `situacao` (`ativa` | `teste` | `suspensa` | `cancelada`), `inicio_em` (date), `expira_em` (date, nulo = sem término), `atualizado_em`; unique `(user_id, modulo)`. "Expirada" **não** é um valor: é `expira_em` já passada. Existe trigger de validação do início (`20261014120000_validar_inicio_licenca.sql`; leia antes de escrever). `public.tem_licenca(p_modulo text default null)` diz se a conta logada tem licença válida (o PRO vale para todos os módulos).
- Buckets: `plugin-releases` (**privado**, instaladores/pacotes), `plugin-assets` (**público**: `catalog.json`, ícones, thumbnails), `revit-families` (**privado**: os `.rfa`).
- Edge Functions existentes: `motor-hidrantes`, `emitir-licenca` (emite o token de licença do plugin; validade em `LICENCA_TTL_DIAS`, hoje 7).

## 5. Fase 1: Usuários e licenças

- Lista paginada de usuários: e-mail, nome (perfis), criado em, último login, situação (ativo/banido), licenças (chips por módulo com situação e validade), busca por e-mail/nome, filtro por "sem licença", "vencendo em 15 dias", "expirada".
- Detalhe do usuário: dados do perfil (somente leitura), licenças com **criar/editar/revogar** (módulo, plano, situação, início, expiração) e atalhos "+30 dias", "+1 ano", "sem término". Respeite o trigger/constraints existentes e mostre o erro do banco de forma legível.
- Ações: convidar usuário por e-mail, gerar link de redefinição de senha, banir/desbanir, excluir (com confirmação). Tudo via Edge Function `admin-usuarios`.
- Visão geral: contagem de licenças ativas por módulo e as que vencem logo.
- Auditoria: tela somente leitura com `admin_auditoria`.

## 6. Fase 2: Versões (versionamento e patch notes)

O plugin se atualiza de dois jeitos, e o painel publica os dois:

- **Instalador:** `FireUtils-Setup-X.Y.Z.exe` + `FireUtils-Setup-X.Y.Z.exe.sha256` (hex minúsculo de 64 caracteres).
- **Pacote de atualização rápida (só código Python):** `FireUtils-Pacote-X.Y.Z-base-B.zip` + `FireUtils-Pacote-X.Y.Z-base-B.zip.sig`. `B` é a menor versão de **instalador** que aceita o pacote. O `.zip` é assinado **no computador do administrador** com uma chave RSA privada (script `installer/publicar-pacote.ps1` do repositório `FireUtils.extension`); **o painel nunca vê essa chave**: ele só recebe o `.zip` e o `.sig` já prontos. (Assinar no navegador é uma etapa futura, fora do escopo.)

Requisitos:

- Tela **Nova versão**: escolher tipo (instalador/pacote), arrastar o arquivo (e o `.sig` para pacote), informar `base_minima` (pacote), título e **notas** (lista de itens, cada um com tipo `novo` | `melhoria` | `correcao` e texto). O painel valida o nome do arquivo contra as regexes acima, calcula o **SHA-256 no navegador** (Web Crypto) e sobe o `.sha256` sozinho (instalador), impede versão repetida ou menor que a última do mesmo tipo e confere que a versão do nome bate com o formulário.
- **Rascunho/Publicar:** a versão só aparece para os clientes depois de **Publicar**; dá para **despublicar**. Upload com barra de progresso, direto para o bucket `plugin-releases` (com as políticas de admin abaixo).
- Lista de versões (tipo, versão, base, data, tamanho, publicada?) e editor de notas de versões já publicadas.
- A prévia das notas mostra como a dockpane vai exibir (etiquetas Novo / Melhoria / Correção).

Modelo de dados proposto (migração no repositório do site; ver seção 9):

```
plugin_releases(
  id uuid pk, versao text, tipo text check (tipo in ('instalador','pacote')),
  arquivo text, base_minima text null, sha256 text null, tamanho_bytes bigint,
  titulo text, notas jsonb /* [{tipo, texto}] */, publicada boolean default false,
  publicada_em timestamptz, criada_em timestamptz default now(), criada_por uuid,
  unique (tipo, versao))
```

Políticas: `select` para admin em tudo; `select` para `authenticated` **com `tem_licenca()`** só onde `publicada`; escrita só para admin. No bucket `plugin-releases`: admin pode `insert/update/delete`; um usuário licenciado só pode `select` objetos que pertençam a uma release **publicada** (`name in (arquivo, arquivo||'.sha256', arquivo||'.sig')`), para rascunhos não vazarem.

## 7. Fase 3: Biblioteca de famílias

Hoje o catálogo é gerado por scripts Python (`migration/generate_catalog.py`, `upload_to_supabase.py` no repositório `FireUtils.extension`). O painel substitui esses scripts. O contrato que a dockpane lê **não pode quebrar**: `plugin-assets/catalog.json` (público):

```
{ "todas_icon_key": "icons/<id>.png|null",
  "categories": [{ "id": "extintor-de-incendio", "name": "Extintor de Incêndio", "icon_key": "icons/extintor-de-incendio.png|null" }],
  "families":   [{ "id": "<category_id>__<slug>", "name": "...", "category_id": "...", "category": "...",
                   "thumbnail_key": "thumbnails/<category_id>/<slug>.png|null",
                   "storage_key": "<category_id>/<slug>.rfa", "size_bytes": 123, "sha256": "<hex>" }] }
```

`slug` = nome sem acento, minúsculo, hífens. `.rfa` vão para o bucket privado `revit-families` (chave `storage_key`); ícones e thumbnails para `plugin-assets`. Duplicata por nome (sem diferenciar maiúsculas) é rejeitada.

Requisitos: CRUD de categorias (nome, ícone) e famílias (nome, categoria, `.rfa`, thumbnail PNG), com SHA-256 e tamanho calculados no navegador; pré-visualização; reordenar; e um botão **Publicar catálogo** que gera e sobe o `catalog.json` (via Edge Function, com rascunho/publicado, para nunca publicar um catálogo inconsistente: valida que toda `storage_key`/`thumbnail_key` existe no bucket antes). Inclua uma **importação inicial** do `catalog.json` atual. Guarde o catálogo em tabelas (`catalogo_categorias`, `catalogo_familias`) e gere o JSON a partir delas.

## 8. Padrões do trabalho

- Estrutura sugerida: `src/pages/{Login,Usuarios,Versoes,Biblioteca}`, `src/components`, `src/lib` (cliente Supabase, helpers puros), `supabase/functions/admin-*` **somente se** o dono do Supabase aceitar mantê-las aqui; caso contrário, entregue-as no repositório do site (seção 9).
- Lógica pura (parse/validação de versões e nomes de arquivo, slug, geração do `catalog.json`, ordenação) em módulos separados **com testes** (`node --test`).
- `README.md` com: variáveis de ambiente, como rodar, como publicar no Vercel, modelo de segurança, e o procedimento de publicar uma versão (incluindo a assinatura local do pacote).
- Commits pequenos e descritivos; **não** abra Pull Request sem o usuário pedir; **não** faça deploy nem execute migrações em produção por conta própria.
- Antes de qualquer ação externa e difícil de desfazer (criar repositório, aplicar migração, publicar), **peça confirmação**.
- Não invente credenciais: use `.env.example` e peça os valores ao usuário.

## 9. Entregas fora deste repositório (peça autorização antes)

1. **No repositório do site (`ETOS.FireUtils`)**, uma migração com: `admins`, `is_admin()`, `admin_auditoria`, `plugin_releases` + políticas, políticas do bucket `plugin-releases`, tabelas do catálogo, e (se aplicável) as Edge Functions `admin-usuarios` e `admin-catalogo`. Nomeie as migrações com timestamp posterior a `20261019120000`.
2. **No repositório `FireUtils.extension`** (webapp da dockpane): trocar a descoberta de versões (hoje `webapp/src/lib/atualizacao.js` lista o nome dos arquivos do bucket) e as notas (`webapp/src/data/patchNotes.js`) por **leitura da tabela `plugin_releases`** (só publicadas), mantendo o formato dos nomes de arquivo e a lógica de `webapp/src/lib/versoes.js`. Enquanto isso não for feito, mantenha os nomes de arquivo no bucket exatamente como hoje, para a dockpane atual continuar funcionando.

Comece pela **Fase 0**: proponha a estrutura do projeto, o desenho do menu lateral e a migração de `admins`, e espere a aprovação do usuário antes de seguir.
