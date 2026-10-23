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

Precisa de Windows com [Inno Setup 6](https://jrsoftware.org/isdl.php). Use a
**versão 6.7 ou mais nova**: é ela que permite o assistente inteiro escuro
(`WizardStyle=modern dark` + `WizardBackColor`, no início do `FireUtils.iss`).
Na 6.6 sai o tema escuro nativo, com o fundo cinza-azulado padrão do Inno; antes
da 6.6 o assistente fica claro. O arquivo escolhe sozinho conforme a versão do
compilador, então compilar numa versão antiga não quebra — só perde o visual.

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

**1. Obter o certificado.** É um certificado de *Code Signing*, emitido por uma
autoridade certificadora (Sectigo, DigiCert, SSL.com, GlobalSign, Certum e
outras) ou por um serviço de assinatura em nuvem. Para a empresa, a CA valida
o CNPJ e o responsável — leva de alguns dias a algumas semanas, então peça
antes de precisar. Desde 2023 as regras do setor exigem que a chave privada
fique em hardware (token USB) ou num serviço em nuvem: você não recebe um
`.pfx` para guardar. Confirme preços e prazos atuais com as CAs.

- **OV:** mais barato. A reputação no SmartScreen se constrói aos poucos, e
  nos primeiros downloads ainda pode aparecer um aviso.
- **EV:** mais caro e com validação mais rigorosa. Já deu reputação imediata no
  SmartScreen, mas as regras mudam — não conte com isso.
- Certificado **autoassinado** não resolve: não tira o aviso do cliente.

**2. Assinar.** Instale o Windows SDK (traz o `signtool.exe`) e, com o token
conectado (ou o serviço em nuvem configurado), rode:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /n "Nome da empresa no certificado" installer\output\FireUtils-Setup-2.1.0.exe
```

`/tr` e `/td` carimbam a data: a assinatura continua válida depois que o
certificado vence. Não omita. O token pede o PIN; serviços em nuvem têm a
própria ferramenta de login (veja a documentação da CA).

**3. Conferir.**

```powershell
signtool verify /pa /v installer\output\FireUtils-Setup-2.1.0.exe
```

Deve terminar em "Successfully verified". Também aparece em botão direito →
Propriedades → Assinaturas Digitais.

**4. Ordem importa.** Assinar muda o arquivo: gere o `sha256` do manifesto
(ver "Aviso de atualização") **depois** de assinar, e assine todo `.exe` que for
distribuído — um instalador sem assinatura reintroduz o aviso. Mais adiante dá
para assinar de dentro do Inno Setup (diretiva `SignTool`), o que assina
também o desinstalador.

## Arquivos

```
installer/
├── build.ps1              Monta o payload e chama o compilador
├── FireUtils.iss          Script do Inno Setup (UI, textos, cópia, desinstalador)
├── VERSION                Versão padrão quando -Version não é passado
├── scripts/
│   └── ensure-deps.ps1    Detecta e instala pyRevit + WebView2
├── branding/              Ícone e imagens do assistente (versionados)
│   ├── gerar_imagens.py   Ferramenta que desenha tudo (não é usada no build)
│   └── fonts/             Space Grotesk (licença OFL), só para desenhar as imagens
├── payload/               Gerado pelo build (fora do git)
└── output/                .exe gerado (fora do git)
```

### Identidade visual

O assistente segue a identidade da dockpane: fundo escuro, vermelho da marca,
Space Grotesk. A tela de boas-vindas e a de conclusão mostram a lateral escura
com a logo (o nome em branco, que no desenho antigo ficava cinza-escuro e quase
sumia); as telas internas levam o símbolo num ícone escuro no canto superior
direito. O ícone do instalador e do desinstalador segue o mesmo desenho.

O Inno Setup não aceita PNG: exige `.ico` e `.bmp`. As imagens são
**versionadas em `installer/branding/`**, então o build não precisa de Python
nem de navegador. O Inno escolhe, dentre uma imagem por escala de DPI
(100 a 250%), a que mais se aproxima do tamanho necessário na tela; com um
tamanho só o resto sairia borrado.

Para mudar o desenho (textos da lateral, cores, logo), edite
`branding/gerar_imagens.py` e regere:

```bash
pip install pillow playwright
python installer/branding/gerar_imagens.py
```

O script precisa de um Chromium (o do Playwright, ou o caminho em
`CHROMIUM=...`) e desenha cada imagem no tamanho exato, a partir da logo em
`Fire Utils.tab/lib/assets/fireutils-logo-h.png`. Com `--previa <pasta>` ele
também grava PNGs para conferir o resultado a olho. Depois, faça commit dos
`.bmp` e do `.ico` gerados.

Os textos das telas (boas-vindas, conclusão) ficam em `[Messages]`, no
`FireUtils.iss`. A tela de conclusão sempre usou a mensagem
`FinishedLabelNoIcons`, e não `FinishedLabel`, porque o instalador não cria
atalhos: era essa a chave que precisava ser sobrescrita para o aviso aparecer.

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
- **Botões "Dimensionar Hidrantes" e "Mapear trechos" da faixa de opções:**
  removidos (o painel Hidrantes saiu da faixa). Quem autentica o dimensionamento
  é a sessão da dockpane, e o mapeamento vive junto dele (aba Sistema de
  Hidrantes): o usuário clica nos elementos no Revit com a dockpane aberta.

**Ordem de publicação:** primeiro `supabase functions deploy motor-hidrantes`
(e os secrets, ver o README da function); só depois gere o instalador.
Em produção, mantenha `EXIGIR_LICENCA=true` (`supabase secrets set
EXIGIR_LICENCA=true`, e republique a function, porque ela lê o valor ao
iniciar): sem ele o motor atende qualquer usuário logado, com ou sem licença.
Antes de ligar, liste as contas sem licença válida e conceda o que faltar. Um
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

## Aviso de atualização pela dockpane

A interface da dockpane já se atualiza sozinha (deploy no Vercel); a parte
Python (`Fire Utils.tab/`, `startup.py`, DLLs do WebView2) só muda com um
instalador novo, e ele exige o Revit fechado. Como as duas podem ficar
desencontradas, o plugin conhece a própria versão e a dockpane avisa.

**Implementado (a base):**

- `build.ps1` grava a versão (`-Version`, ou `installer/VERSION`) em
  `VERSION`, na raiz da extensão instalada. `lib/plugin_versao.py` a lê; sem o
  arquivo (clone de desenvolvimento) a versão é `dev` e ninguém é avisado.
- O Python informa a versão junto da mensagem `LICENCAS` (campo
  `versaoPlugin`). Plugin antigo não manda o campo, e a dockpane o trata como
  anterior a qualquer versão publicada.
- A dockpane lista o bucket **privado** `plugin-releases` do Supabase (só
  contas com licença leem; ver a migração
  `20261019120000_create_plugin_releases_bucket.sql` no ETOS.FireUtils), pega a
  maior versão entre os arquivos `FireUtils-Setup-X.Y.Z.exe` e compara:
  - **versão nova disponível:** faixa no topo com **Atualizar** (ver "Atualizar
    pela dockpane" abaixo) e **Depois** (some até sair outra versão), mais o
    ícone de download na barra lateral;
  - **abaixo de `PLUGIN_MINIMO`:** a dockpane troca o conteúdo por "Atualize o
    plugin", porque esta interface não funciona direito com um plugin tão
    antigo.
  Bucket vazio, sem internet ou sem licença: nenhum aviso, sem erro. Só vale o
  nome exato `FireUtils-Setup-X.Y.Z.exe`: qualquer outro arquivo (um
  `...-teste.exe`, um `manifest.json` antigo) é ignorado.

**Publicar uma versão** — o trabalho é só construir, assinar e subir:

1. Aumente `installer/VERSION`, faça commit e rode `.\build.ps1`. O `.exe` sai
   com a versão no nome (`FireUtils-Setup-2.1.0.exe`) e o plugin instalado
   informa a mesma versão.
2. Assine o `.exe` (ver "Antes de distribuir").
3. Gere o `.sha256` do `.exe` assinado (ver "Atualizar pela dockpane") e, no
   painel do Supabase, em Storage → `plugin-releases`, envie o `.sha256` e
   depois o `.exe`, **sem renomear**: o nome é a fonte da versão. Quem tem o plugin instalado vê
   o aviso na próxima vez que abrir a dockpane.

Pode deixar as versões antigas no bucket (servem para reinstalar se uma nova
der problema); só a de maior número é oferecida.

`PLUGIN_MINIMO` (em `webapp/src/lib/versoes.js`) é a **menor versão do plugin
que a interface atual aceita**; hoje é `null` (qualquer uma serve). Só a
aumente, no mesmo deploy da interface que passa a exigir algo do plugin (por
exemplo, uma mensagem nova da bridge), depois que o plugin novo já estiver
publicado e os clientes tiveram tempo de atualizar: quem estiver abaixo perde o
acesso até atualizar.

### Atualizar pela dockpane (baixar e instalar)

O botão **Atualizar** da faixa, da tela "Atualize o plugin" e o ícone de download
da barra lateral pedem ao plugin que baixe e instale a versão nova
(`lib/plugin_atualizacao.py`). Plugin antigo, sem esse suporte (o campo
`suportaAtualizacao` da mensagem `LICENCAS`), cai no link do perfil no site.

Isto **executa um programa baixado da internet**, então o plugin não confia no
pedido da dockpane e confere três coisas antes de rodar qualquer coisa:

1. **Origem:** só link assinado do bucket `plugin-releases` deste projeto
   Supabase, para `FireUtils-Setup-X.Y.Z.exe` de versão **maior** que a
   instalada (nunca volta versão).
2. **Integridade:** o SHA-256 do arquivo precisa bater com o `.sha256`
   publicado ao lado dele.
3. **Autenticidade:** a assinatura digital (Authenticode) precisa ser válida e o
   nome do assinante (CN do certificado) precisa ser o `_PUBLICADOR_ASSINATURA`,
   fixado em `lib/plugin_atualizacao.py` como a chave pública de licença. É isto
   que protege contra alguém que invada o bucket e troque o instalador junto
   com o `.sha256`.

**Enquanto `_PUBLICADOR_ASSINATURA` estiver vazio** (instalador ainda não
assinado), a instalação automática fica **desligada**: o plugin baixa e confere
o hash, mas só abre a pasta com o instalador; o usuário decide executar. O
`build.ps1` avisa quando está vazio. Para ligar: assine o instalador, copie o
nome do assinante (`(Get-AuthenticodeSignature .\FireUtils-Setup-X.exe).SignerCertificate.Subject`,
o valor depois de `CN=`), preencha a constante e gere uma versão nova — a
primeira com a chave já ligada precisa ser instalada na mão.

**Como instala:** o instalador não roda com o Revit aberto. Um script
(`lib/atualizar_plugin.ps1`, copiado para `%LOCALAPPDATA%\FireUtils\atualizacao`
porque o instalador apaga a pasta da extensão) roda em segundo plano, espera
todo `Revit.exe` fechar, confere hash e assinatura **de novo** e executa o
instalador com `/SILENT /SUPPRESSMSGBOXES /NORESTART /NOCLOSEAPPLICATIONS`. O
usuário só precisa fechar o Revit; a dockpane diz isso ("será instalada quando
você fechar o Revit"). Log em `%LOCALAPPDATA%\FireUtils\atualizacao.log`. Se o
script morrer antes (logoff, por exemplo), a dockpane oferece de novo na
próxima abertura. Em modo silencioso o instalador não mostra a pergunta
"atualizar ou desinstalar" e recusa se o Revit foi reaberto no intervalo.

**Publicar uma versão, agora com o hash:** depois de assinar o `.exe`, gere o
`.sha256` **do arquivo já assinado** (assinar muda o hash) e suba os dois, com o
mesmo nome-base:

```powershell
$exe = ".\output\FireUtils-Setup-2.1.0.exe"
(Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower() | Set-Content -NoNewline "$exe.sha256"
```

Envie `FireUtils-Setup-2.1.0.exe` e `FireUtils-Setup-2.1.0.exe.sha256` ao bucket
`plugin-releases`. Sem o `.sha256`, a atualização pela dockpane falha com
"arquivo de conferência" e o usuário usa o perfil no site. A dockpane só
oferece a versão quando o `.exe` existe; suba o `.sha256` **antes** dele.

### Atualização rápida por pacote (só Python, sem instalador)

Para mudanças só de código Python (novos bridges, ferramentas, XAML, YAML,
imagens) não precisa de instalador: um **pacote** assinado atualiza o plugin
com o Revit aberto (`lib/plugin_pacote.py`).

- **O que o pacote leva:** `Fire Utils.tab` (`.py .xaml .yaml .json .png .svg
  .ico .txt .md .ps1`) e o manifesto `pacote.json`. **Nunca** leva DLLs
  (`lib/webview2_runtime`), as famílias (`lib/family_library`) nem o `startup.py`.
  Mudou algum desses, dependências, ou qualquer coisa fora disso: gere um
  **instalador**.
- **Confiança sem certificado do Windows:** o `.zip` é assinado com uma chave
  RSA **sua**, e a pública está embutida no plugin (`_CHAVE_PACOTE_*`). A privada
  fica só no seu computador, **fora do Git, do Supabase e do Vercel**; quem a
  tiver publica atualizações que todos aceitam. É outra chave, diferente da licença.
- **Aplicação:** o plugin baixa, confere a assinatura, extrai com regras estritas
  (só dentro de `Fire Utils.tab/`, só essas extensões, sem `..`), copia por cima
  da extensão, apaga os arquivos de código que saíram da versão e grava `VERSION`
  **por último** (se falhar no meio, `VERSION` não muda e a dockpane oferece de
  novo). **Não guarda versão anterior**: a correção de um pacote ruim é o pacote
  seguinte. Depois recarrega o pyRevit (melhor esforço) e a dockpane mostra
  "Atualização instalada. Reinicie o Revit para concluir." (o Python já carregado
  só muda ao reiniciar).
- **`BASE` e `baseMinima`:** o instalador grava `BASE` (sua versão), que pacotes
  não alteram. Cada pacote declara no nome a menor base que o aceita
  (`FireUtils-Pacote-3.2.0-base-3.1.0.zip`) e o plugin recusa se a base for menor.

- **Quanto reiniciar (automático):** antes de copiar, o plugin compara arquivo a
  arquivo o que mudou e o cruza com o que a dockpane usa (os módulos que ela
  carregou e, transitivamente, tudo que eles importam, até imports preguiçosos).
  Resultado, mostrado na dockpane:
  - **`revit`:** mudou código que a dockpane usa (bridges, `hidrantes/`, `saidas/`,
    licença, `family_loader_webview.xaml`...) → "Reinicie o Revit".
  - **`pyrevit`:** mudou a faixa (`bundle.yaml`, ícones, `script.py` de botão, botão
    novo ou removido) → o pyRevit é recarregado.
  - **`nenhum`:** só código de `lib` que apenas os botões usam → já vale no
    próximo clique, sem reiniciar.
  Se vários tipos mudaram, vale o mais exigente. Plugin sem essa informação cai
  em `revit` (o caso seguro). Arquivos idênticos não são nem reescritos.

**Uma vez só (preparar):**

```powershell
cd installer
.\scripts\gerar-chave-pacote.ps1      # grava a privada em %USERPROFILE%; imprime a publica
```
Cole as 2 linhas impressas em `_CHAVE_PACOTE_MODULO` e `_CHAVE_PACOTE_EXPOENTE`
(`lib/plugin_pacote.py`), faça backup OFFLINE da chave privada e gere um
**instalador** novo (ele leva a chave pública). Só depois os pacotes valem.

**A cada atualização só de Python:**

```powershell
cd installer
.\publicar-pacote.ps1 -Versao 3.2.0 -BaseMinima 3.1.0
```
Gera `output\FireUtils-Pacote-3.2.0-base-3.1.0.zip` e `...zip.sig`. Suba os dois no
bucket `plugin-releases` (o `.sig` primeiro). `-BaseMinima` é a versão do
instalador que ficou nos clientes (em geral, a do último instalador). A versão do
pacote precisa ser **maior** que a instalada e não pode repetir.

A dockpane oferece a atualização de maior versão: se um pacote serve, ele; senão o
instalador. Empate: o pacote.

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

## Desinstalar

O instalador gera o desinstalador do Inno. Rodar o instalador de novo, com o plugin já instalado, oferece "Desinstalar". Ele aparece em **Menu Iniciar > Fire
Utils > Desinstalar o Fire Utils** e em Configurações > Aplicativos. Recusa
rodar com o Revit aberto, apaga a pasta da extensão e pergunta se remove também
`%LOCALAPPDATA%\FireUtils` (licença, logs e perfil do WebView2, que guarda o
login). Em desinstalação silenciosa (`/SILENT`) esses dados são removidos.
