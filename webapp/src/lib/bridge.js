/**
 * Ponte JS <-> Python (Fase 3/4 do plano de migração): o host pyRevit hospeda
 * este app num Microsoft.Web.WebView2.Wpf.WebView2.
 *
 * JS -> Python via CoreWebView2.WebMessageReceived (args.WebMessageAsJson,
 * string JSON). Python -> JS via CoreWebView2.PostWebMessageAsJson, que
 * chega aqui em window.chrome.webview "message" (event.data já vem
 * desserializado do JSON, sem precisar de JSON.parse).
 *
 * Fora do WebView2 (ex.: `npm run dev` no navegador comum, durante o
 * desenvolvimento isolado do frontend), postToHost só loga no console em
 * vez de quebrar — permite testar a UI sem o Revit aberto.
 *
 * Mensagens JS -> Python (payload sempre um objeto serializável em JSON):
 *
 *   { type: "LOAD_FAMILIES", payload: { familias: [{ name, categoryId, storageKey, sha256, signedUrl }] } }
 *     -> Python baixa cada .rfa pra um arquivo temporário e chama
 *        Document.LoadFamily (sem posicionar — ver family_loader.py).
 *        Ao terminar, o host manda de volta um LOADED_FAMILIES atualizado.
 *
 *   { type: "REQUEST_LOADED_FAMILIES", payload: {} }
 *     -> Pede ao host a lista de famílias do catálogo já carregadas no
 *        documento ativo do Revit (pra popular o indicador "carregada" nos
 *        cards e o contador correspondente).
 *
 * Mensagens Python -> JS:
 *
 *   { type: "LOADED_FAMILIES", payload: { names: string[] } }
 *     -> nomes (Family.Name, mesma convenção do campo "name" do catálogo)
 *        de todas as famílias do catálogo já presentes no documento ativo.
 */
export const BridgeMessageTypes = {
  LOAD_FAMILIES: "LOAD_FAMILIES",
  REQUEST_LOADED_FAMILIES: "REQUEST_LOADED_FAMILIES",
  LOADED_FAMILIES: "LOADED_FAMILIES",
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

/**
 * Escuta mensagens vindas do host (Python -> JS). Retorna uma função pra
 * cancelar a inscrição (chamar no cleanup de um useEffect). Fora do
 * WebView2, não há nada pra escutar — retorna um no-op.
 */
export function escutarMensagensDoHost(aoReceber) {
  const webview = obterWebView();
  if (!webview || typeof webview.addEventListener !== "function") {
    return () => {};
  }
  const handler = (evento) => aoReceber(evento.data);
  webview.addEventListener("message", handler);
  return () => webview.removeEventListener("message", handler);
}
