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

**Python → JS**

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
canto superior direito (`components/ToastStack.jsx`) e pra tirar da
seleção as famílias já resolvidas (carregadas ou já existentes), deixando
só as que falharam marcadas pra facilitar tentar de novo.

Não existe um indicador de "família já carregada no projeto" nos cards —
já foi tentado (`LOADED_FAMILIES`/`REQUEST_LOADED_FAMILIES`, removidos),
mas listar TODAS as famílias do documento ativo pra isso se mostrou frágil
demais: uma única família pré-existente com o nome salvo de um jeito que
o Revit/IronPython não conseguem traduzir de volta pra texto derrubava a
leitura inteira (ver `family_loader._familias_por_nome_no_documento`, que
ainda pula esse tipo de família individualmente, mas só é chamada durante
um carregamento de verdade — nunca mais pra listar o documento inteiro só
pra exibição).

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

## Dashboard — vínculo de projeto/estrutura

Migrado do antigo pushbutton "Dados do Projeto" (WPF/XAML, aposentado) pra
dentro da dockpane. Fluxo, depois de logado:

1. Aba **Dashboard** na sidebar → tela "Conectar um projeto" (busca +
   grade dos projetos do usuário).
2. Escolhido o projeto: se ele tiver mais de uma estrutura cadastrada,
   mostra "Selecione uma estrutura"; com só uma, pula direto pro dashboard.
3. Dashboard da estrutura: cards "Edificação"/"Classificação" +
   "Dimensionamentos" (status local de Hidrantes/Saída de Emergência) +
   dropdown pra trocar de estrutura (se houver mais de uma).
4. Botão "Desconectar projeto" na sidebar (acima do avatar) — some o
   vínculo do documento Revit ativo, volta pra tela de conexão.

**Busca de projetos/estruturas**: direto no Supabase via `supabase-js`
(`lib/projectData.js`), com a sessão do usuário logado decidindo via RLS
quais linhas aparecem — sem Edge Function, sem token, no mesmo espírito de
como `lib/catalog.js` já lê o catálogo de famílias direto do bucket
público. **Persistência do vínculo escolhido**: como só o lado Python sabe
qual é o documento Revit ativo (e sua pasta), o vínculo final (depois de
resolvido projeto + estrutura) é mandado pra lá via bridge
(`SET_PROJECT_LINK`) e gravado no `firedata.json` da pasta do projeto —
mesmo formato que o pushbutton antigo gravava (`dados_projeto` + `sync`),
pra não quebrar os módulos de dimensionamento (hidrantes/saidas/extintores,
que continuam lendo esses dados sem nenhuma mudança neles).

### Schema do Dashboard (Supabase — real)

Uma tabela só, sem `estruturas` separada — tudo (projeto e suas
estruturas) mora dentro da coluna `dados` (jsonb):

```sql
create table public.projetos (
  id          text primary key,       -- "ID do projeto" (não é uuid) — guardado
                                       -- localmente como sync.projetoId no firedata.json
  user_id     uuid not null references auth.users(id),  -- RLS: user_id = auth.uid()
  nome        text not null,
  dados       jsonb not null,
  sync_token  uuid not null default gen_random_uuid(),  -- em desuso, ver nota abaixo
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  version     integer not null default 1
);
```

`lib/projectData.js` só busca a linha crua (`id, nome, dados, updated_at`);
quem decodifica o formato de `dados` é `lib/projetoDados.js`. Campos de
`dados` usados hoje (exemplo real, campos irrelevantes pro Dashboard
omitidos):

```jsonc
{
  "nome": "Loja Comercial Centro",
  "uf": "MA",
  "areaConstruidaTotal": "650",   // string — projeto inteiro (soma das estruturas)
  "areaTerreno": "500",           // string — terreno é do projeto, não por estrutura
  "estruturas": [
    {
      "id": "est-1", "nome": "Estrutura 1",
      "areaTotal": "250",         // área construída DESSA estrutura
      "altura": "6",              // altura total da edificação (m)
      "alturaPisoPiso": 0,        // altura piso a piso (m)
      "nPavimentos": 1
    }
  ],
  "pavimentos": [
    // cada pavimento pertence a uma estrutura (estruturaId) e tem um
    // código de ocupação (divisao, ex.: "C-1", "A-1", "G-1" — tabela
    // normativa em lib/normas/<UF>/saidas.py)
    { "id": "est-1-P1", "estruturaId": "est-1", "divisao": "C-1", "area": "250", ... }
  ],
  "cargaState": {
    // carga de incêndio (MJ/m²) por estrutura e por divisão
    "est-1": { "C-1": { "cargaIncendio": 300, ... } }
  }
}
```

`lib/projetoDados.js` deriva disso: resumo pro card de "Conectar um
projeto" (`resumoProjeto`), lista de estruturas (`estruturasDoProjeto`) e
os dados de uma estrutura pro dashboard (`dashboardEstrutura` — Edificação,
Classificação, `divisoes` presentes nela). Quando uma estrutura tem mais
de um código de ocupação (`divisao`) entre seus pavimentos, a tela mostra
"Mista" — mas o código "oficial" que alimenta `dados_projeto.ocupacao_principal`
(usado por ex. em "Dimensionar Saídas") **não pode ser "Mista"**, tem que
ser um código válido da tabela normativa; por isso quem escolhe qual
divisão usar (a mais restritiva, menor distância máxima) é o Python
(`project_link_bridge._divisao_mais_restritiva`, portado do antigo
formulário "Dados do Projeto") — só ele tem acesso a essa tabela
(`lib/normas`). Não há ainda uma classificação de "Risco" (faixa
qualitativa tipo "Médio") nem de "Altura da edificação" (tipo "I -
Edificação Baixa") — o dashboard mostra os valores brutos (carga de
incêndio em MJ/m², altura em metros) até essa tabela de classificação
existir.

RLS: as políticas do Supabase decidem quais `projetos` cada usuário logado
enxerga (`user_id = auth.uid()`) — `projectData.js` não filtra por
usuário, só repassa o que a política deixar. `VITE_SITE_URL` (opcional,
`.env.local`) monta o link "abrir no site" do cabeçalho do dashboard
(`${VITE_SITE_URL}/${projeto.id}`); sem essa env var, o ícone de link
externo simplesmente não aparece.

**`sync_token` em desuso**: antes era o que o Python colava manualmente
(`token`) pra autenticar as Edge Functions `site-sync`/`revit-sync`. Com o
login já acontecendo dentro da dockpane, a ideia é o envio de cálculos
(hidrantes/saídas/extintores) também passar a ser um relay pela própria
dockpane (Python pede, React já-autenticado grava no Supabase) em vez de
um POST direto com token — ver nota em `lib/bridge.js`. Esse relay ainda
não foi implementado; por enquanto `sync.py` (`enviar`/`buscar`) continua
existindo mas não é mais alimentado por nada do vínculo projeto/estrutura
feito aqui.

### Mensagens da bridge (vínculo de projeto)

Documentadas com mais detalhe no topo de `lib/bridge.js`. Resumo:

| Tipo | Direção | Payload |
|---|---|---|
| `GET_PROJECT_LINK` | JS → Python | — |
| `PROJECT_LINK` | Python → JS | `{ docSalvo, projetoId, projetoNome, estruturaId, estruturaNome }` |
| `SET_PROJECT_LINK` | JS → Python | `{ projetoId, projetoNome, estruturaId, estruturaNome, uf, areaConstruida, divisoes }` |
| `PROJECT_LINK_SAVED` | Python → JS | `{ ok, erro? }` |
| `DISCONNECT_PROJECT` | JS → Python | — |
| `GET_DIMENSIONAMENTOS_STATUS` | JS → Python | — |
| `DIMENSIONAMENTOS_STATUS` | Python → JS | `{ hidrantes: boolean, saidaEmergencia: boolean }` |

Do lado Python, tratadas em `Fire Utils.tab/lib/project_link_bridge.py`
(despachado a partir de `family_webview_bridge.py`).

## Estrutura

```
src/
├── lib/
│   ├── supabaseClient.js   cliente Supabase + helpers de URL pública/assinada
│   ├── catalog.js          busca catalog.json (com fallback pro mock local)
│   ├── projectData.js      busca a linha de `projetos` no Supabase (direto, RLS)
│   ├── projetoDados.js     decodifica dados.{estruturas,pavimentos,cargaState}
│   ├── format.js           helpers de formatação (área, metros, "editado há Xh")
│   ├── bridge.js           postMessage <-> host WebView2 (JS <-> Python)
│   └── toasts.js           hook useToasts() — fila de notificações
├── components/
│   ├── LoginScreen.jsx
│   ├── Sidebar.jsx         navegação lateral (Biblioteca + Dashboard + desconectar)
│   ├── Dashboard.jsx       orquestra o fluxo de vínculo projeto/estrutura
│   ├── dashboard/
│   │   ├── ConectarProjeto.jsx
│   │   ├── SelecionarEstrutura.jsx
│   │   ├── DashboardEstrutura.jsx
│   │   └── ProjetoCabecalho.jsx
│   ├── CategoryPills.jsx
│   ├── FamilyCard.jsx
│   ├── ToastStack.jsx      notificações (canto superior direito)
│   └── Icon.jsx            SVG local inline (permite cor via CSS)
├── assets/icons/           SVGs exportados do Figma (fill/stroke="currentColor");
│                           os "-placeholder" (link/external-link/unlink/saida)
│                           são desenhos simples feitos pra este PR, ainda sem
│                           passar pelo Figma
├── mock/catalog.mock.json  exemplo pra dev sem depender do Supabase
├── App.jsx                 shell principal (sidebar, abas Biblioteca/Dashboard)
└── main.jsx
```
