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

## Build de produção (o que a Fase 3 vai consumir)

```bash
npm run build
```

Gera `dist/` — um `index.html` + assets estáticos, sem servidor Node
nenhum por trás. É essa pasta que o pyRevit vai apontar o WebView2 pra
carregar (Fase 3), idealmente via
[`SetVirtualHostNameToFolderMapping`](https://learn.microsoft.com/microsoft-edge/webview2/how-to/hostnametofoldermapping)
em vez de abrir o `index.html` direto com `file://` (evita restrições de
CORS/módulos ES do Chromium com `file://`).

## Contrato da ponte JS → Python (Fase 3/4)

Só existe um tipo de mensagem por enquanto, em `src/lib/bridge.js`:

```json
{
  "type": "LOAD_FAMILIES",
  "payload": {
    "posicionar": false,
    "familias": [
      { "name": "Extintor Portátil - ABC", "categoryId": "extintor-de-incendio", "storageKey": "extintor-de-incendio/extintor-portatil-abc.rfa", "signedUrl": "https://..." }
    ]
  }
}
```

O React já gera a Signed URL (via `supabase.storage.from('revit-families').createSignedUrl(...)`,
válida por 60s) antes de mandar a mensagem — o lado Python só precisa
baixar cada `signedUrl` (com cache local por `storageKey`, Fase 4) e chamar
`Document.LoadFamily`; se `posicionar` for `true`, encadear um
`PromptForFamilyInstancePlacement` por família carregada, na mesma ordem da
lista.

No WebView2, essa mensagem chega no evento `CoreWebView2.WebMessageReceived`
como `args.WebMessageAsJson` (string JSON — precisa de `json.loads` do lado
Python).

## Estrutura

```
src/
├── lib/
│   ├── supabaseClient.js   cliente Supabase + helpers de URL pública/assinada
│   ├── catalog.js          busca catalog.json (com fallback pro mock local)
│   └── bridge.js           postMessage pro host WebView2
├── components/
│   ├── LoginScreen.jsx
│   ├── CategoryPills.jsx
│   └── FamilyCard.jsx
├── mock/catalog.mock.json  exemplo pra dev sem depender do Supabase
├── App.jsx                 tela principal (busca, categorias, grade, ações)
└── main.jsx
```
