# WebView2 SDK — assemblies necessários

O `family_loader_webview_forms.py` (Fase 3 do plano de migração) precisa de
dois `.dll` do SDK do WebView2 que **não vêm com o Revit/pyRevit** e por
isso não são commitados aqui (binários de terceiros, ~1-2 MB cada) — baixe
e copie pra esta pasta antes de usar o painel web.

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

## Por que esses arquivos não estão no git

São binários redistribuíveis da Microsoft, não código deste projeto — indo
pro `.gitignore` (`*.dll` nesta pasta) pra não inchar o repositório com
binário de terceiros a cada atualização de versão do SDK.
