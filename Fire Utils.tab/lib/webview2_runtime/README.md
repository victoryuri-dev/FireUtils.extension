# WebView2 SDK — assemblies necessários

O `family_loader_webview_forms.py` (Fase 3 do plano de migração) precisa de
três arquivos do SDK do WebView2 que **não vêm com o Revit/pyRevit**. Eles
**são commitados nesta pasta** (apesar de serem binário de terceiro, não
código do projeto) — o plugin é distribuído via `git clone`/`git pull`
direto pra cada computador, sem instalador nem CI/CD, então instalar numa
máquina nova precisa funcionar só com o clone do repositório, sem depender
de NuGet/Visual Studio disponíveis ali.

As instruções abaixo são pra quando for **atualizar a versão do SDK** (ou
se por algum motivo os `.dll` sumirem daqui) — no dia a dia, quem só
instala o plugin não precisa fazer nada disso.

## Onde conseguir

Pacote NuGet `Microsoft.Web.WebView2` (Microsoft):
https://www.nuget.org/packages/Microsoft.Web.WebView2

### Opção A — Visual Studio

1. Crie (ou reaproveite) qualquer projeto .NET.
2. **Gerenciar Pacotes NuGet** → procure `Microsoft.Web.WebView2` → instalar.
3. Os `.dll` aparecem em `packages/Microsoft.Web.WebView2.<versão>/lib/net45/`
   (ou `lib/netcoreapp3.0/`, dependendo da versão do pacote).

### Opção B — `nuget.exe` (sem Visual Studio)

```powershell
nuget install Microsoft.Web.WebView2 -Version 1.0.2903.40 -OutputDirectory temp_webview2
```

(baixe o `nuget.exe` em https://www.nuget.org/downloads se não tiver.)

## Arquivos a copiar pra esta pasta

Depois de baixar o pacote (por qualquer uma das opções acima), copie:

```
Microsoft.Web.WebView2.<versão>/lib/net45/Microsoft.Web.WebView2.Core.dll
Microsoft.Web.WebView2.<versão>/lib/net45/Microsoft.Web.WebView2.Wpf.dll
Microsoft.Web.WebView2.<versão>/runtimes/win-x64/native/WebView2Loader.dll
```

(o Revit é sempre 64-bit, então é `win-x64`, não `win-x86`.)

Resultado esperado nesta pasta:

```
webview2_runtime/
├── Microsoft.Web.WebView2.Core.dll
├── Microsoft.Web.WebView2.Wpf.dll
└── WebView2Loader.dll
```

## WebView2 Runtime (diferente do SDK acima!)

O SDK só dá acesso à API — pra o controle renderizar de fato, a **máquina**
precisa ter o WebView2 Runtime instalado. Windows 10/11 atualizados com
Edge já vêm com ele. Se necessário, instale o "Evergreen Bootstrapper":
https://developer.microsoft.com/microsoft-edge/webview2/

## Atualizando pra uma versão nova do SDK

Baixe a nova versão pelos passos acima, substitua os 3 arquivos nesta
pasta e comite a mudança — sem isso, os computadores que só fazem `git
pull` continuam usando os `.dll` antigos.
