/**
 * Ponte JS -> Python (Fase 3/4 do plano de migração): o host pyRevit hospeda
 * este app num Microsoft.Web.WebView2.Wpf.WebView2 e escuta o evento
 * WebMessageReceived. Cada mensagem enviada daqui chega lá como uma string
 * JSON (CoreWebView2.WebMessageReceived -> args.WebMessageAsJson).
 *
 * Fora do WebView2 (ex.: `npm run dev` no navegador comum, durante o
 * desenvolvimento isolado do frontend), só loga no console em vez de
 * quebrar — permite testar a UI sem o Revit aberto.
 *
 * Contrato de mensagens (payload sempre um objeto serializável em JSON):
 *
 *   {
 *     type: "LOAD_FAMILIES",
 *     payload: {
 *       posicionar: boolean,
 *       familias: [{ name, categoryId, storageKey, signedUrl }],
 *     },
 *   }
 *     -> Python baixa cada .rfa (com cache local em %AppData%) e chama
 *        Document.LoadFamily via IExternalEventHandler; se posicionar for
 *        true, encadeia um PromptForFamilyInstancePlacement por família
 *        carregada, na mesma ordem da lista (equivalente ao antigo botão
 *        "Carregar e posicionar" do painel WPF).
 */
export const BridgeMessageTypes = {
  LOAD_FAMILIES: "LOAD_FAMILIES",
};

function obterWebView() {
  return typeof window !== "undefined" && window.chrome && window.chrome.webview
    ? window.chrome.webview
    : null;
}

export function postToHost(type, payload) {
  const mensagem = { type, payload };
  const webview = obterWebView();
  if (webview && typeof webview.postMessage === "function") {
    webview.postMessage(mensagem);
  } else {
    console.log("[bridge:dev] postToHost (WebView2 não detectado):", mensagem);
  }
}

export function estaDentroDoWebView2() {
  return obterWebView() !== null;
}
