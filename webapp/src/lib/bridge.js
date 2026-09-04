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
 *        Ao terminar, o host manda de volta um LOAD_RESULT.
 *
 * Mensagens Python -> JS:
 *
 *   { type: "LOAD_RESULT", payload: { carregadas: string[], jaExistentes: string[], erros: [{ name, mensagem }] } }
 *     -> resultado de um LOAD_FAMILIES: o que foi carregado de verdade, o
 *        que já existia no projeto (não recarregado) e o que falhou (com
 *        o motivo) — vira notificação (ver components/ToastStack.jsx) e
 *        tira da seleção as famílias já resolvidas (carregadas ou já
 *        existentes), deixando só as que falharam marcadas pra tentar de
 *        novo.
 *
 * Mensagens do Dashboard (vínculo projeto/estrutura — ver
 * lib/projectData.js e project_link_bridge.py do lado Python):
 *
 *   { type: "GET_PROJECT_LINK" }
 *     JS -> Python: pede o vínculo salvo no firedata.json do documento
 *     Revit ativo (a busca de projetos/estruturas em si é direto no
 *     Supabase, do lado do React — isto só lê o que já foi vinculado).
 *
 *   { type: "PROJECT_LINK", payload: { docSalvo, projetoId, projetoNome, estruturaId, estruturaNome } }
 *     Python -> JS: resposta de GET_PROJECT_LINK (e também reenviada depois
 *     de um SET_PROJECT_LINK ou DISCONNECT_PROJECT bem-sucedido).
 *     `docSalvo: false` quando não há documento Revit aberto ou ele ainda
 *     não foi salvo em disco — nesse caso os demais campos vêm null e o
 *     Dashboard deve pedir pra salvar o projeto antes de vincular.
 *
 *   { type: "SET_PROJECT_LINK", payload: { projetoId, projetoNome, estruturaId, estruturaNome, uf, ocupacaoPrincipal, areaConstruida } }
 *     JS -> Python: grava o vínculo escolhido (projeto + estrutura, já
 *     resolvidos no Supabase) no firedata.json do documento ativo — mesmo
 *     formato que o antigo pushbutton "Dados do Projeto" gravava, pra não
 *     quebrar os módulos de dimensionamento (hidrantes/saidas/extintores).
 *
 *   { type: "PROJECT_LINK_SAVED", payload: { ok, erro? } }
 *     Python -> JS: resultado de um SET_PROJECT_LINK ou DISCONNECT_PROJECT
 *     que falhou antes de conseguir persistir (ex.: documento não salvo).
 *     Em caso de sucesso, um PROJECT_LINK também é reenviado logo em
 *     seguida com o estado atualizado.
 *
 *   { type: "DISCONNECT_PROJECT" }
 *     JS -> Python: apaga o vínculo (projeto + estrutura) do documento
 *     ativo — usado pelo botão "Desconectar projeto" da sidebar.
 *
 *   { type: "GET_DIMENSIONAMENTOS_STATUS" }
 *     JS -> Python: pede o status (feito/não feito) dos dimensionamentos
 *     já calculados localmente pra estrutura vinculada.
 *
 *   { type: "DIMENSIONAMENTOS_STATUS", payload: { hidrantes: boolean, saidaEmergencia: boolean } }
 *     Python -> JS: resposta de GET_DIMENSIONAMENTOS_STATUS.
 */
export const BridgeMessageTypes = {
  LOAD_FAMILIES: "LOAD_FAMILIES",
  LOAD_RESULT: "LOAD_RESULT",
  GET_PROJECT_LINK: "GET_PROJECT_LINK",
  PROJECT_LINK: "PROJECT_LINK",
  SET_PROJECT_LINK: "SET_PROJECT_LINK",
  PROJECT_LINK_SAVED: "PROJECT_LINK_SAVED",
  DISCONNECT_PROJECT: "DISCONNECT_PROJECT",
  GET_DIMENSIONAMENTOS_STATUS: "GET_DIMENSIONAMENTOS_STATUS",
  DIMENSIONAMENTOS_STATUS: "DIMENSIONAMENTOS_STATUS",
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
