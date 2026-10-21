# Lançamento 3.1.0: guia do que só você consegue fazer e plano de testes

Tudo aqui é para rodar no **seu Windows** (com Revit, Inno Setup 6.7+ e,
no fim, o certificado de assinatura). Nada disto foi executado pelo assistente:
o código foi escrito e a sintaxe conferida, mas o build, o Revit e o Windows
nunca rodaram a versão 3.1.0.

O que entra na 3.1.0 (desde a 3.0.1):

- **Mapear trechos** passa a ser feito pela dockpane (o botão da faixa saiu).
- **Ferramentas de ocupação** (identificar por ambiente/nível/todos, sincronizar)
  passam a ser botões da página Saídas de Emergência (o painel Saídas saiu da faixa).
- **Atualização pela dockpane** (baixar, conferir hash e assinatura, instalar ao
  fechar o Revit). Fica **desligada** até o instalador ser assinado.
- **Instalador:** tema escuro, pergunta "atualizar ou desinstalar", atalho e
  limpeza de dados no desinstalador, modo silencioso para a atualização.
- Dockpane: fontes (Space Grotesk/Inter), logo clicável, ícone de download.

---

## Parte 1. Guia: procedimentos manuais

### 1.1 Antes de gerar

1. **Inno Setup 6.7 ou mais novo** instalado (`C:\Program Files (x86)\Inno Setup 6`).
   Confirme com `ISCC.exe` (a primeira linha mostra a versão do compilador).
2. `git pull` na `main` do FireUtils.extension. Confira:
   - `installer\VERSION` = `3.1.0`;
   - `fireutils.config.json` com `"webappUrl": "https://fire-utils-extension.vercel.app"`
     (o build **recusa** `localhost`). Para o dia a dia de desenvolvimento, lembre
     de voltar para localhost só na sua máquina e **não commitar** (o commit
     `ui update` deixou localhost na `main`; foi corrigido nesta entrega).
   - `lib\licenca.py` com a chave pública (`_CHAVE_PUBLICA_MODULO` e `_EXPOENTE`).
3. **Publique o servidor primeiro** (a ordem importa: plugin novo fala com ele):
   - site (ETOS.FireUtils): `main` no Vercel;
   - `supabase db push` (migrations pendentes, incl. as do PB) e
     `supabase functions deploy motor-hidrantes emitir-licenca` (a partir da pasta
     do repositório do site, não do plugin);
   - webapp da dockpane (FireUtils.extension, `webapp`) no Vercel.

### 1.2 Gerar o instalador

```powershell
cd C:\GIT\fireutils\FireUtils.extension\installer
.\build.ps1
```

Esperado: o log lista `Interface: https://fire-utils-extension.vercel.app`,
`Chave publica de licenca: configurada` e um **aviso amarelo** de
`_PUBLICADOR_ASSINATURA vazio` (normal enquanto não houver assinatura).
Saída: `installer\output\FireUtils-Setup-3.1.0.exe`.

Se der erro de `Unknown preprocessor directive` ou `Invalid section tag`: uma
linha de código do `.iss` começa com `#` ou `[`. Me mande a mensagem.

### 1.3 Assinar (só quando tiver o certificado)

Procedimento completo em `README.md` → "Antes de distribuir: assine o executável".
Resumo:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /n "NOME DO CERTIFICADO" .\output\FireUtils-Setup-3.1.0.exe
signtool verify /pa /v .\output\FireUtils-Setup-3.1.0.exe
```

Para **ligar a atualização automática**:

1. Leia o nome do assinante:
   `(Get-AuthenticodeSignature .\output\FireUtils-Setup-3.1.0.exe).SignerCertificate.Subject`
2. Copie o valor depois de `CN=` para `_PUBLICADOR_ASSINATURA` em
   `Fire Utils.tab\lib\plugin_atualizacao.py` (texto exato, com acentos).
3. Suba a versão (`installer\VERSION` → 3.1.1), gere e assine de novo. **A primeira
   versão com a constante preenchida precisa ser instalada na mão**; a partir da
   seguinte, a dockpane instala sozinha.

### 1.4 Publicar no bucket `plugin-releases`

Depois de assinar, gere o hash **do arquivo já assinado**:

```powershell
$exe = ".\output\FireUtils-Setup-3.1.0.exe"
(Get-FileHash -Algorithm SHA256 $exe).Hash.ToLower() | Set-Content -NoNewline "$exe.sha256"
```

No painel do Supabase → Storage → `plugin-releases`, envie **primeiro** o
`.sha256`, **depois** o `.exe`, sem renomear. **Não suba o 3.1.0 no bucket antes
dos testes da Parte 2**: quem estiver na 3.0.1 passaria a ver o aviso.

### 1.5 Fechar a versão

```powershell
git tag v3.1.0
git push origin v3.1.0
```

---

## Parte 2. Plano de testes

Anote **OK / FALHOU / observação** em cada linha. Se algo falhar, mande o
número do teste e o que apareceu (print ou texto do log).

Logs úteis: `%LOCALAPPDATA%\FireUtils\licenca.log`,
`%LOCALAPPDATA%\FireUtils\atualizacao.log`, `%TEMP%\FireUtils-install.log` e a
janela de saída do pyRevit.

**Ambiente de teste:** idealmente uma máquina virtual limpa (Windows com Revit,
**sem** pyRevit) para o bloco A, e o seu PC (com Revit, projeto real e rede
modelada) para os demais. Contas: uma **com licença PRO** e uma **sem licença**.

### A. Instalação limpa (VM sem pyRevit)

| # | Passo | Esperado |
|---|---|---|
| A1 | Rodar `FireUtils-Setup-3.1.0.exe` | Tema escuro completo; tela de boas-vindas com a lateral da marca |
| A2 | Seguir até concluir | Baixa/instala pyRevit e WebView2 se faltarem; conclui sem erro; tela final com os 3 passos |
| A3 | Abrir o Revit | Aba **Fire Utils** com Biblioteca, Tubos, Produtividade, Ferramentas de Linha. **Sem** painéis Hidrantes nem Saídas |
| A4 | Abrir a dockpane, entrar com a conta PRO | Dashboard carrega; famílias listam; sem tela de "Ative a licença" |
| A5 | Menu Iniciar | Existe "Fire Utils > Desinstalar o Fire Utils" |
| A6 | `%LOCALAPPDATA%\FireUtils\licenca.token` | Existe depois do login |

### B. Atualização por cima e desinstalação

| # | Passo | Esperado |
|---|---|---|
| B1 | Num PC com a **3.0.1**, rodar o instalador 3.1.0 | Aparece "O Fire Utils já está instalado" com Atualizar / Desinstalar / Cancelar |
| B2 | Escolher Atualizar (com o Revit aberto) | Avisa para fechar o Revit; "Repetir" só avança com ele fechado |
| B3 | Concluir e abrir o Revit | Continua logado, licença intacta, painel Saídas e Hidrantes **sumiram** (sem sobras de botão) |
| B4 | Rodar o instalador de novo e escolher **Desinstalar** | Abre o desinstalador; exige Revit fechado; pergunta se remove licença e dados |
| B5 | Responder **Não** à limpeza e reinstalar | Continua logado, sem pedir licença |
| B6 | Desinstalar de novo, responder **Sim** | `%LOCALAPPDATA%\FireUtils` some; pasta da extensão some; aba some do Revit |
| B7 | Desinstalar pelo atalho do Menu Iniciar | Mesmo comportamento de B4 |

### C. Licença e offline

| # | Passo | Esperado |
|---|---|---|
| C1 | Conta **sem licença**, abrir a dockpane | Tela de bloqueio; nada de hidrantes/saídas |
| C2 | Conta PRO, **desligar a internet**, reabrir o Revit | Ferramentas da faixa (Tubos, Produtividade, Linha) funcionam |
| C3 | Sem internet, abrir a dockpane | Falha de conexão tratada; nenhuma tela quebrada |
| C4 | Editar `licenca.token` (trocar um caractere) | Ferramentas da faixa bloqueiam |
| C5 | Sair da conta na dockpane | `licenca.token` apagado |

### D. Mapear trechos (dockpane)

Projeto Revit com RTI, bomba e ao menos 2 válvulas de hidrante, sistema já classificado.

| # | Passo | Esperado |
|---|---|---|
| D1 | Página Sistema de Hidrantes → **Mapear Trechos** | Aviso "Clique no reservatório (RTI)…" na dockpane |
| D2 | Clicar RTI, depois a bomba no Revit | Mensagem "Percorrendo a rede…" e depois a tabela de trechos |
| D3 | Botão de lupa de cada trecho | Seleciona e enquadra o trecho no Revit |
| D4 | Reabrir a dockpane | Tabela de trechos continua lá |
| D5 | Desconectar um tubo da recalque e mapear | Lista de pontos soltos com localizar; opções "Ignorar e continuar" / "Corrigi, mapear de novo" |
| D6 | "Ignorar e continuar" | Mapeamento grava; toast com nº de ignorados |
| D7 | Esc durante a seleção | Cancela sem erro e sem apagar o mapeamento anterior |
| D8 | Sem classificar o sistema | Aviso de requisito faltando |
| D9 | **Dimensionar Hidrantes** em seguida | Resultado igual ao de antes (mesmo cache de rotas) |
| D10 | Mapear **sem internet** | Funciona (só o dimensionar exige internet) |

### E. Ferramentas de ocupação (página Saídas)

| # | Passo | Esperado |
|---|---|---|
| E1 | Abrir Saídas de Emergência | Quatro cartões acima dos pavimentos |
| E2 | **Identificar por ambiente** | Janela com Grupo/Tipo/taxa/AD-ER-PT/notas; depois pede seleção no Revit; ao concluir grava Grupo, Taxa e População |
| E3 | **Por nível** | Lista os níveis do modelo; só habilita com pelo menos um marcado |
| E4 | **Todos sem ocupação** | Só afeta ambientes sem Grupo |
| E5 | **Sincronizar ambientes** | Resumo por estrutura; "N ambientes com população atualizada" |
| E6 | Depois de qualquer ação | Pavimentos da página recarregam sozinhos com os ambientes novos |
| E7 | Ambiente com taxa não por área | Mensagem de população manual (sem abrir a janela do pyRevit) |
| E8 | Com o Revit aberto sem projeto salvo | Mensagem "Salve o projeto Revit" |
| E9 | Conta sem módulo Saídas | Mensagem de licença |
| E10 | Abrir um projeto **diferente** no mesmo Revit e repetir E2 | Grava no projeto ativo (não no primeiro aberto) |

### F. Faixa do Revit (modelagem offline)

| # | Passo | Esperado |
|---|---|---|
| F1 | Tubos: Conectar Abrigo, Conectar Tubulação, Inserir Hidrante (3 variações) | Funcionam como na 3.0.1 |
| F2 | Produtividade: Inserir Alarme, Sinalizar Equipamentos | Idem |
| F3 | Ferramentas de Linha: Comprimento de linha | Idem |

### G. Aviso e atualização pela dockpane

Antes: instalar a **3.1.0** e **só então** subir uma versão maior (por exemplo,
renomeie uma cópia assinada ou use uma 3.1.1 de teste) no bucket, com o `.sha256`.

| # | Passo | Esperado |
|---|---|---|
| G1 | Abrir a dockpane | Faixa "Nova versão disponível" e ícone de download vermelho na barra lateral |
| G2 | "Depois" na faixa | Faixa some; **o ícone continua** |
| G3 | Clicar em Atualizar, **certificado ainda não configurado** | Mostra progresso de download, conferência, e abre a pasta **Downloads** com o instalador; texto "feche o Revit e execute" |
| G4 | Apagar o `.sha256` do bucket e tentar | Erro claro de arquivo de conferência; nada executa |
| G5 | Trocar o `.exe` do bucket por outro arquivo com o mesmo nome (hash diferente) | Erro de hash; arquivo descartado |
| G6 | Subir um `.exe` **de versão menor/igual** | Não é oferecido |
| G7 | Instalação por git clone (versão "dev") | Nenhum aviso |
| G8 | **Com certificado** (depois da Parte 1.3): clicar Atualizar | Texto "será instalada quando você fechar o Revit" |
| G9 | Fechar o Revit | Em segundos aparece o instalador silencioso com barra de progresso; termina sozinho; `atualizacao.log` mostra "Instalador terminou com codigo 0" |
| G10 | Abrir o Revit | Versão nova ativa; aviso de atualização some |
| G11 | Reabrir o Revit antes de o script rodar (instalar em G9 com Revit aberto) | O instalador recusa sem fechar o Revit à força |
| G12 | Assinar com um certificado **de outro nome** e tentar | Erro de assinatura; arquivo descartado; nada instalado |

### H. Interface e links

| # | Passo | Esperado |
|---|---|---|
| H1 | Fontes | Títulos em Space Grotesk; texto e números em Inter; tabelas de hidrantes sem fonte monoespaçada |
| H2 | Clicar na logo da barra lateral | Abre `https://fireutils.vercel.app/projetos` no navegador |
| H3 | Sem ícone de configurações na barra lateral | Confere |
| H4 | Perfil no site (`/perfil`) | "Ferramentas disponíveis" com Memorial e Plugin; "Licenças ativas" com os cartões |
| H5 | Perfil: "Baixar plugin" | Baixa o `.exe` mais recente (conta com licença); conta sem licença não vê o atalho |

### I. Antes de distribuir (resumo)

- [ ] Todos os blocos A–H sem FALHOU.
- [ ] Servidor publicado antes do plugin (Parte 1.1, item 3).
- [ ] Instalador assinado e `.sha256` do arquivo assinado.
- [ ] `.sha256` e `.exe` no bucket, nessa ordem.
- [ ] Tag no git. `PLUGIN_MINIMO` continua `null` até os clientes migrarem.

## Riscos conhecidos (peça atenção ao testar)

1. `.iss`: o código de atualização silenciosa (`WizardSilent`) e a pergunta
   atualizar/desinstalar nunca compilaram com a 6.7 **fora do seu PC**; os
   testes A–B cobrem isso.
2. Seleção de elementos (D1, E2) com a dockpane aberta: é o ponto que mais pode
   se comportar diferente do esperado no Revit.
3. Script de atualização em segundo plano: se o Windows encerrar a sessão antes
   de ele rodar, a dockpane oferece de novo na próxima abertura (G9).
4. Instalação **troca** a pasta da extensão: se interromper no meio, rode o
   instalador de novo.
