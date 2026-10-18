# Instalador do Fire Utils

Gera um `.exe` que instala a extensão no Revit do cliente, sem exigir Git,
Node ou Python na máquina dele.

## O que o cliente precisa

| Dependência | Como é resolvida |
|---|---|
| Autodesk Revit | Pré-requisito. O instalador avisa se não encontrar. |
| pyRevit | Instalado automaticamente se faltar (winget, com download do GitHub como alternativa). |
| WebView2 Runtime | Instalado automaticamente se faltar. Já vem no Windows 10/11 com Edge atualizado. |
| Node / npm | **Não precisa.** A interface da dockpane vem do servidor. |
| Python / pip | **Não precisa.** O pyRevit traz o IronPython, e o código usa apenas a biblioteca padrão e o .NET. |
| Git | **Não precisa.** Os arquivos vão embutidos no `.exe`. |
| Internet | **Precisa**, para a dockpane e para o dimensionamento (o cálculo roda no servidor). As ferramentas de produtividade — inserir, conectar, medir — funcionam offline. |

A instalação é por usuário, em `%APPDATA%\pyRevit\Extensions\FireUtils.extension`,
e por isso não pede privilégio de administrador. O Windows pode pedir
elevação ao instalar o pyRevit ou o WebView2, que são de terceiros.

## O que o instalador não carrega

**A interface da dockpane.** Ela é carregada da URL em
`fireutils.config.json` toda vez que o painel abre — o instalador leva
apenas essa configuração. Publicar interface nova é um deploy, não um
instalador novo.

**Quase toda a biblioteca de famílias.** O acervo vive no Supabase e a
dockpane baixa sob demanda; `garantir_familia_no_projeto()` só verifica se a
família já está no documento, sem carregar do disco. Vão no payload apenas
as famílias listadas em `$FamiliasNecessarias` no `build.ps1` — hoje só a
`Valvula para Hidrante.rfa`, a única que o Python abre com `LoadFamily`.

Isso leva o instalador de ~45 MB para poucos MB. A pasta continua no
repositório porque alimenta o `migration/generate_catalog.py`.

Se o build parar com "familia necessaria nao encontrada", alguém renomeou ou
removeu um `.rfa` que o código ainda carrega — corrija nos dois lugares.

## Gerando o instalador

Precisa de Windows com [Inno Setup 6](https://jrsoftware.org/isdl.php).

```powershell
cd installer
.\build.ps1 -Version 1.0.0
```

Sem `-Version`, o script usa o conteúdo de `installer/VERSION`.

O `build.ps1` recria `installer/payload/` do zero a cada execução — nunca
edite nada lá dentro. Ele copia apenas `Fire Utils.tab/`, `startup.py` e
`fireutils.config.json`; `installer/`, `migration/` e `webapp/` ficam de
fora.

### Proteções do build

- **Aborta** se `_CHAVE_PUBLICA_MODULO`/`_CHAVE_PUBLICA_EXPOENTE` estiverem
  vazios em `Fire Utils.tab/lib/licenca.py`: sem a chave pública nenhum token
  de licença confere e as ferramentas ficam bloqueadas no cliente.
- **Aborta** se `fireutils.config.json` não existir, não for JSON válido,
  não tiver `webappUrl`, a URL não for `https://` ou apontar para
  `localhost` (configuração de desenvolvimento esquecida).
- **Aborta** se alguma família de `$FamiliasNecessarias` não existir no
  repositório.
- **Avisa** quando aparece algo novo na raiz do repositório que não está na
  lista do payload, para nenhum arquivo novo ficar de fora sem querer.

### Proteções na instalação

- **Exige o Revit fechado.** As DLLs do WebView2 ficam carregadas dentro do
  processo do Revit (`clr.AddReferenceToFileAndPath` no startup do pyRevit)
  e o Windows não deixa sobrescrever DLL em uso — a cópia falharia no meio.
  O instalador detecta por WMI e oferece repetir depois de fechar.
- **Apaga a versão anterior antes de copiar** (`[InstallDelete]`). O Inno
  sobrescreve o que existe mas nunca remove o que saiu entre versões, e numa
  extensão pyRevit uma pasta `.pushbutton` órfã continua virando botão na
  faixa de opções, chamando um script que talvez nem exista mais.

## Antes de distribuir: assine o executável

Sem assinatura digital, o SmartScreen mostra "editor desconhecido" e um
botão de "Executar assim mesmo" escondido atrás de "Mais informações".
Para um produto pago isso custa caro em confiança e em chamados de suporte.

É preciso um certificado de Code Signing (OV ou EV) de uma autoridade
certificadora. Depois de obtê-lo, assine com `signtool.exe`.

## Arquivos

```
installer/
├── build.ps1              Monta o payload e chama o compilador
├── FireUtils.iss          Script do Inno Setup (UI, cópia, desinstalador)
├── VERSION                Versão padrão quando -Version não é passado
├── scripts/
│   ├── ensure-deps.ps1    Detecta e instala pyRevit + WebView2
│   └── gerar-imagens.ps1  Converte a logo em ícone e imagens do assistente
├── assets/                Ícone e .bmp gerados (fora do git)
├── payload/               Gerado pelo build (fora do git)
└── output/                .exe gerado (fora do git)
```

### Identidade visual

O Inno Setup não aceita PNG: exige `.ico` para o ícone e `.bmp` para as
imagens do assistente. O `gerar-imagens.ps1` faz essa conversão a partir de
`Fire Utils.tab/lib/assets/fireutils-logo-h.png`, usando o `System.Drawing`
do .NET — sem dependência para instalar.

O `build.ps1` o executa sozinho quando os arquivos ainda não existem. Depois
de trocar a logo, regere com:

```powershell
.\scripts\gerar-imagens.ps1 -Forcar
```

Dois detalhes que o script resolve: o ícone sai com sete resoluções (16 a
256 px), porque o Windows escolhe conforme o contexto e um tamanho único
fica borrado; e as imagens do assistente levam fundo escuro, porque o nome
na logo é branco e sumiria sobre o fundo claro padrão.

O símbolo do ícone é recortado detectando os pixels vermelhos da marca, em
vez de uma região fixa — assim o script continua correto se a logo for
redesenhada com outras proporções.

### Por que não usamos o CLI do pyRevit

O caminho aparentemente natural seria registrar a extensão com
`pyrevit extensions paths add`. Não fazemos isso por dois motivos: esse
comando tem histórico de falhar sem reportar erro
([pyrevitlabs/pyRevit#1032](https://github.com/pyrevitlabs/pyRevit/issues/1032)),
e o CLI é distribuído como um pacote separado do instalador principal —
depender dele acrescentaria uma dependência que pode simplesmente não
existir na máquina do cliente.

Copiar a pasta para o diretório de extensões do pyRevit não tem nenhum
desses problemas. O nome da pasta precisa terminar em `.extension`, que é
como o pyRevit identifica uma extensão.

## Diagnóstico

O `ensure-deps.ps1` grava tudo em `%TEMP%\FireUtils-install.log`. Quando um
cliente relatar falha na instalação, peça esse arquivo primeiro.

Para testar a detecção de dependências isoladamente, sem gerar o
instalador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ensure-deps.ps1
# 0 = tudo pronto | 1 = pyRevit ausente | 2 = falha inesperada
```

## Clientes que já usam a versão instalada por git

O instalador detecta se o pyRevit tem pastas de extensão configuradas
manualmente e avisa antes de prosseguir. Isso cobre quem instalou por
`git clone`: sem remover a cópia antiga, o Revit carrega as duas ao mesmo
tempo e a aba aparece duplicada.

A remoção não é automática — o instalador não tem como saber com segurança
qual pasta é a cópia antiga do Fire Utils e qual é outra extensão que o
cliente usa. A instrução no aviso é remover por
**pyRevit > Settings > Custom Extension Directories**.

## Motor de cálculo na nuvem

O dimensionamento não roda mais dentro do plugin: o código do plugin fica no
computador do usuário, e quem o edita altera o resultado. O motor virou uma
Edge Function do Supabase (`motor-hidrantes`, no repositório ETOS.FireUtils,
`supabase/functions/`), e o plugin só lê o modelo do Revit, envia e grava o
que volta (`lib/motor_nuvem.py`, `lib/hidrantes_dimensionar_bridge.py`).

- **Fluxo:** a dockpane manda `DIMENSIONAR_HIDRANTES` com o access token da
  sessão → o Python lê trechos, cotas e classificação (thread da API do Revit)
  → a chamada ao motor vai numa thread de fundo, para uma conexão ruim não
  congelar o Revit → o resultado é gravado no mesmo `firedata.json` de sempre.
- **Norma:** o motor lê `normas_dados` sozinho. O plugin nunca envia Pmin,
  vazão, coeficiente C nem tolerância — quem manda o próprio requisito
  poderia "aprovar" um sistema que não atende.
- **Sem internet:** o dimensionamento avisa e não calcula. A última resposta
  continua visível (vem do `firedata.json`).
- **O que ainda é local:** a perda de carga usada no ranking de "Mapear
  Trechos" (`calc_j_trecho`), a classificação do sistema (Tabela 3, em JS na
  dockpane) e os demais cálculos (saídas, extintores, sinalização, iluminação).
  Migram para o mesmo motor nas próximas etapas.
- **Botão "Dimensionar Hidrantes" da faixa de opções:** virou atalho que abre
  a dockpane, porque quem autentica o pedido é a sessão dela.

**Ordem de publicação:** primeiro `supabase functions deploy motor-hidrantes`
(e os secrets, ver o README da function); só depois gere o instalador. Um
plugin novo com a function ainda não publicada não dimensiona.

## Licença assinada (ferramentas de produtividade offline)

As ferramentas de produtividade funcionam sem internet porque a licença é um
**token assinado pelo servidor** (`emitir-licenca`, no ETOS.FireUtils) que o
plugin só consegue *conferir*:

1. A dockpane, com a sessão do usuário, busca o token e o entrega ao Python
   (`SET_LICENCA_TOKEN`). Ela pede um novo quando o computador não tem um
   válido ou faltam menos de 7 dias para vencer — ou seja, a renovação é
   automática sempre que o painel abre com internet.
2. `lib/licenca.py` confere a assinatura com a chave pública embutida (RSA,
   .NET nativo) e só então grava `%LOCALAPPDATA%\FireUtils\licenca.token`.
3. Cada ferramenta confere o token na hora (`licenca_guard.exigir`), sem rede.

Editar o arquivo ou trocar o módulo no payload invalida a assinatura. Quem
edita o código Python para pular a conferência ainda consegue — por isso o
dimensionamento exige licença no servidor a cada chamada, e o token só decide
o que é offline. Validade padrão de 30 dias (`LICENCA_TTL_DIAS`): é o tempo
máximo que uma licença cancelada ainda funciona para quem nunca abre o painel
com internet.

O plugin não guarda mais o refresh token da sessão: renová-lo girava o token
que a dockpane também usa, e os dois podiam se derrubar.

**Primeiro uso após atualizar o plugin:** não há token guardado ainda, então
as ferramentas pedem para abrir o painel Fire Utils com internet uma vez.

**Antes do primeiro instalador com este recurso** (ver
`supabase/functions/emitir-licenca/README.md` no ETOS.FireUtils):
`node scripts/gerar-chave-licenca.mjs`, guardar a chave privada no secret
`LICENCA_CHAVE_PRIVADA` e num cofre de senhas, publicar a function e colar a
chave pública em `lib/licenca.py`. Trocar a chave depois exige reinstalar o
plugin em todos os clientes.

## Atualização pela dockpane (planejado, ainda não implementado)

A interface da dockpane já se atualiza sozinha (deploy no Vercel). A parte
Python (`Fire Utils.tab/`, `startup.py`, DLLs do WebView2) só muda com um
instalador novo, e o instalador exige o Revit fechado. A atualização pela
dockpane reaproveita esse instalador em vez de trocar arquivos com o Revit
aberto.

Fluxo:

1. Cada release publica o `FireUtils-Setup-X.Y.Z.exe` e um manifesto
   (`{ "versao", "arquivo", "sha256", "hostMinVersion" }`) num bucket
   **privado** do Supabase Storage. Privado: o acesso é por URL assinada de
   curta duração, gerada para usuários autenticados (e com licença válida,
   reaproveitando `licencas.js`/`licenca.py`), nunca por link público.
2. O `installer/VERSION` entra no payload, para o plugin saber qual versão
   está instalada.
3. A dockpane compara a versão instalada com o manifesto e mostra um aviso
   de atualização disponível.
4. Ao clicar em atualizar, o Python baixa o `.exe` para a pasta temporária,
   confere o `sha256` e abre um script auxiliar desvinculado do Revit. Esse
   script espera o `Revit.exe` fechar e então roda o instalador com
   `/SILENT`.

Pontos a tratar na implementação:

- **Web × Python:** como a web atualiza na hora e o Python não, a web deve
  conferir `hostMinVersion` e bloquear a função (ou pedir a atualização)
  quando o Python instalado for anterior ao que ela precisa.
- **Assinatura do `.exe`:** obrigatória neste fluxo, já que o instalador é
  executado automaticamente (ver "Antes de distribuir").
- **Publicação:** `build.ps1` deve gerar o manifesto (com o `sha256`) e
  enviar os dois arquivos ao bucket, para não depender de passo manual.

## Pendências de validação

Já validado em Windows: o build compila e gera o `.exe` (~45 MB), e o ID do
winget é `pyRevit.pyRevit`, confirmado por `winget search pyrevit`.

Falta confirmar antes da primeira distribuição:

1. **Filtro do instalador do pyRevit no GitHub.** `Resolve-PyRevitInstallerUrl`
   descarta os arquivos com `admin` e `CLI` no nome, esperando sobrar
   exatamente um `.exe`. Se a release passar a ter outros arquivos, a função
   devolve `$null` de propósito (em vez de baixar o errado) e a instalação
   pede ação manual. Rode o script numa máquina sem pyRevit e verifique o
   log.

O teste mínimo antes de mandar para um cliente é uma máquina virtual limpa,
com Revit e sem pyRevit.
