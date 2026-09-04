# Fire Utils — Carregador de Famílias (Frontend Web)

Fase 2 do `PLANO_DE_MIGRACAO_FAMILY_LIBRARY`: aplicação React (Vite) que
substitui o catálogo WPF/XAML do plugin. Roda como app web comum durante o
desenvolvimento (`npm run dev`) e, na Fase 3, passa a rodar embutida num
`Microsoft.Web.WebView2.Wpf` hospedado pelo pyRevit.

## Setup

Este projeto foi montado manualmente (sem `npm create vite`, por bloqueio de
rede do ambiente onde foi escrito) — a estrutura já está pronta, só falta
instalar as dependências:

```bash
cd webapp
npm install
```

## Rodando em desenvolvimento (sem o Revit aberto)

```bash
npm run dev
```

Abre em `http://localhost:5173`. Funciona mesmo **sem** o Supabase
configurado ainda: sem `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY`, a tela
de login mostra um aviso de configuração pendente em vez de quebrar, e o
catálogo (quando logado) cai automaticamente no exemplo local em
`src/mock/catalog.mock.json` — gerado a partir da `family_library/` real
pelo `migration/generate_catalog.py`, então reflete o acervo atual.

## Conectando ao Supabase de verdade

Depois que o projeto e os buckets (`plugin-assets` público, `revit-families`
privado) estiverem criados (ver `../migration/README.md`) e o `catalog.json`
já tiver sido enviado:

```bash
cp .env.example .env.local
# edite .env.local com a URL e a anon key do seu projeto (Settings > API)
npm run dev
```

**Nunca** coloque a `service_role` key aqui — só a `anon` (pública); o
controle de acesso de verdade é a política de RLS do bucket privado no
Supabase.

## Build de produção (o que a Fase 3 consome)

```bash
npm run build
```

Gera `dist/` — um `index.html` + assets estáticos, sem servidor Node
nenhum por trás. É essa pasta que o pyRevit aponta o WebView2 pra carregar
(Fase 3), via
[`SetVirtualHostNameToFolderMapping`](https://learn.microsoft.com/microsoft-edge/webview2/how-to/hostnametofoldermapping)
em vez de abrir o `index.html` direto com `file://` (evita restrições de
CORS/módulos ES do Chromium com `file://`).

**`dist/` é commitado no git** (não está no `.gitignore`), de propósito:
este plugin é distribuído via `git clone`/`git pull` direto pra cada
computador, sem CI/CD nem instalador — se `dist/` não fosse versionado,
cada máquina nova precisaria de Node/npm instalados só pra rodar o
Carregador de Famílias, o que não faz sentido pro usuário final do plugin.
Sempre que mudar algo em `src/`, rode `npm run build` de novo e **comite o
`dist/` atualizado junto** — sem isso, o plugin instalado continua rodando
a versão antiga da interface.

## Contrato da ponte JS ↔ Python (Fase 3/4)

Em `src/lib/bridge.js`. JS → Python chega via `WebMessageReceived`; Python →
JS chega via `PostWebMessageAsJson`, escutado com `escutarMensagensDoHost`.

**JS → Python**

```json
{
  "type": "LOAD_FAMILIES",
  "payload": {
    "familias": [
      { "name": "Extintor Portátil - ABC", "categoryId": "extintor-de-incendio", "storageKey": "extintor-de-incendio/extintor-portatil-abc.rfa", "sha256": "...", "signedUrl": "https://..." }
    ]
  }
}
```

O React já gera a Signed URL (via `supabase.storage.from('revit-families').createSignedUrl(...)`,
válida por 60s) antes de mandar a mensagem — o lado Python só precisa
baixar cada `signedUrl` e chamar `Document.LoadFamily`. Não há
posicionamento automático (sem `PromptForFamilyInstancePlacement`) — o
único botão do app carrega a família no projeto, sem posicionar.

```json
{ "type": "REQUEST_LOADED_FAMILIES", "payload": {} }
```

Pede ao host a lista de famílias do catálogo já carregadas no documento
ativo — usado pra popular o indicador "carregada" nos cards e o contador
correspondente. Disparado sempre que o catálogo termina de carregar.

**Python → JS**

```json
{ "type": "LOADED_FAMILIES", "payload": { "names": ["Extintor Portátil - ABC"] } }
```

Mandado em resposta a `REQUEST_LOADED_FAMILIES` e de novo, já atualizado,
logo depois de qualquer `LOAD_FAMILIES` processado — o frontend não
precisa pedir de novo pra saber que a família recém-carregada já conta.

```json
{
  "type": "LOAD_RESULT",
  "payload": {
    "carregadas": ["Extintor Portátil - ABC"],
    "jaExistentes": ["Extintor Portátil - BC"],
    "erros": [{ "name": "Extintor Portátil - K", "mensagem": "Checksum do arquivo baixado não confere com o catálogo (storage_key=...)." }]
  }
}
```

Resultado de um `LOAD_FAMILIES`: o que foi carregado de verdade, o que já
existia no documento ativo (`family_loader.carregar_familias` verifica por
nome antes de chamar `LoadFamily` — se já existe, pula em vez de recarregar
e duplicar) e o que falhou, com o motivo (download, checksum ou
`LoadFamily`). O React usa isso pra gerar as notificações (toasts) no
canto superior direito (`components/ToastStack.jsx`); nunca é usado pra
popular o indicador "carregada" — isso é sempre papel do `LOADED_FAMILIES`
que vem logo em seguida.

Download (`family_cache.py`): sem cache persistente, de propósito — o
`.rfa` é baixado pra um arquivo temporário via `System.Net.WebClient`,
carregado com `Document.LoadFamily`, e apagado logo em seguida (o Revit já
embute a família no `.rvt` a partir do `LoadFamily`, então o arquivo
original não faz falta depois disso). Cada carregamento sempre busca a
versão mais recente do Supabase — sem isso, um cache local poderia ficar
preso numa versão desatualizada da família, ou virar lixo acumulado no
disco do usuário para famílias que saíram do catálogo. O campo `sha256` do
catálogo ainda é usado pra validar a integridade do download.

No WebView2, essa mensagem chega no evento `CoreWebView2.WebMessageReceived`
como `args.WebMessageAsJson` (string JSON — precisa de `json.loads` do lado
Python).

## Estrutura

```
src/
├── lib/
│   ├── supabaseClient.js   cliente Supabase + helpers de URL pública/assinada
│   ├── catalog.js          busca catalog.json (com fallback pro mock local)
│   ├── bridge.js           postMessage <-> host WebView2 (JS <-> Python)
│   └── toasts.js           hook useToasts() — fila de notificações
├── components/
│   ├── LoginScreen.jsx
│   ├── Sidebar.jsx         navegação lateral (só Biblioteca de Famílias ativa)
│   ├── CategoryPills.jsx
│   ├── FamilyCard.jsx
│   ├── ToastStack.jsx      notificações (canto superior direito)
│   └── Icon.jsx            SVG local inline (permite cor via CSS)
├── assets/icons/           SVGs exportados do Figma (fill/stroke="currentColor")
├── mock/catalog.mock.json  exemplo pra dev sem depender do Supabase
├── App.jsx                 tela principal (busca, categorias, grade, ações)
└── main.jsx
```
