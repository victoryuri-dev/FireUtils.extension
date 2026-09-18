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
 * IMPORTANTE — evolução do sync com o site: o `sync_token` da tabela
 * `projetos` (usado antes pro Python empurrar cálculos pra uma Edge
 * Function via token) está sendo aposentado; com o login já acontecendo
 * dentro da dockpane (sessão do Supabase no próprio React), a ideia é o
 * envio de dados de cálculo (hidrantes/saídas/extintores) também passar a
 * ser um relay por aqui — Python pede, React (já autenticado) grava no
 * Supabase — em vez de um POST direto do lado Python com token. Esse
 * relay ainda não existe (é o próximo passo depois do vínculo
 * projeto/estrutura abaixo); quando existir, ganha seu próprio tipo de
 * mensagem aqui.
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
 *   { type: "SET_PROJECT_LINK", payload: { projetoId, projetoNome, estruturaId, estruturaNome, uf, areaConstruida } }
 *     JS -> Python: grava o vínculo escolhido (projeto + estrutura, já
 *     resolvidos no Supabase) no firedata.json do documento ativo — mesmo
 *     formato que o antigo pushbutton "Dados do Projeto" gravava, pra não
 *     quebrar os módulos de hidrantes/saidas/extintores.
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
 *
 *   { type: "SET_HIDRANTES_CLASSIFICACAO", payload: { tipo: number, tipoVariante?: number,
 *     metodoCalculo?: "valvula" | "esguicho", succaoAltitude?: number, succaoTemperatura?: number } }
 *     JS -> Python: manda pro Project Information do documento Revit ativo
 *     só o que o motor de cálculo ("Dimensionar Hidrantes"/"Mapear
 *     Trechos") de fato lê pra dimensionar: Tipo + variante (resolve
 *     Q/Pmin/mangueira/esguicho contra o perfil normativo do próprio
 *     plugin — Tabela 2 nunca vem do site, pra nunca ter dois lugares
 *     dando valores potencialmente diferentes), método de cálculo (onde a
 *     norma exige verificar Q/Pmin) e os dados de sucção (altitude/
 *     temperatura, usados no NPSH disponível). RTI (Reserva Técnica de
 *     Incêndio, Tabela 3) NÃO entra aqui: o motor de cálculo nunca lê RTI
 *     do Project Information (dimensiona o reservatório, não a rede
 *     hidráulica) — fica só no Supabase (dados.hidrantes.rti), gravado
 *     direto por quem classifica (site ou a própria dockpane — ver
 *     SistemaHidrantesPage.jsx:salvarHidrantes()), sem essa terceira cópia
 *     local que podia divergir sem ninguém perceber. Mesmo método de
 *     classificação em ambos os lados (ver lib/hidrantesClassificacao.js
 *     aqui e src/data/hidrantes_calc.js no site) — gravado no Project
 *     Information via hidrantes_classificacao_bridge.py do lado Python.
 *
 *   { type: "HIDRANTES_CLASSIFICACAO_SAVED", payload: { ok, erro?, valorSistema?, metodoCalculo? } }
 *     Python -> JS: resultado de um SET_HIDRANTES_CLASSIFICACAO.
 *
 *   { type: "GET_HIDRANTES_DIMENSIONAMENTO" }
 *     JS -> Python: pede, pra página "Sistema de Hidrantes" (ver
 *     components/dashboard/SistemaHidrantesPage.jsx), o sistema classificado
 *     que está de fato aplicado no Revit (Project Information, resolvido
 *     pelo perfil normativo — pode divergir do que está pendente no site
 *     se "Aplicar classificação no Revit" ainda não foi clicado depois de
 *     uma mudança), o ponto de operação do último "Dimensionar Hidrantes"
 *     (cache local) e a eficiência da bomba já salva, se houver.
 *
 *   { type: "HIDRANTES_DIMENSIONAMENTO", payload: { ok, erro?,
 *     classificacao?: { tipo, variante_idx, descricao, esguicho_dn, mang_dn,
 *       mang_comp, expedicoes, q_min, p_min, valorSistema },
 *     pontoOperacao?: { qt, ht, pHd01, pHd02, qHd01, qHd02, hidGoverna, timestamp } | null,
 *     erroDimensionamento?: string | null } }
 *     `classificacao` não inclui `rti` — quem quiser mostrar RTI lê direto
 *     do Supabase (dadosHidrantes(projeto).rti, ver lib/projetoDados.js),
 *     nunca do Project Information (ver comentário de
 *     SET_HIDRANTES_CLASSIFICACAO acima pra por quê).
 *     Python -> JS: resposta de GET_HIDRANTES_DIMENSIONAMENTO. `ht` é a
 *     altura manométrica total que a bomba precisa desenvolver (P_RTI do
 *     motor de cálculo — pressão que precisaria existir na RTI, referência
 *     atmosférica, pra alimentar o sistema por gravidade; já inclui sucção
 *     e recalque). `pontoOperacao` vem null quando "Dimensionar Hidrantes"
 *     ainda não rodou nesta sessão do projeto (ver erroDimensionamento).
 *     A eficiência da bomba e a potência adotada NÃO vêm daqui — são lidas/
 *     gravadas direto no Supabase (dados.hidrantes.bombaEficiencia/
 *     bombaPotenciaAdotada, ver lib/projetoDados.js e
 *     SistemaHidrantesPage.jsx), o mesmo campo que o site edita na Etapa 3
 *     ("Dimensionamento da Bomba de Incêndio"), sem passar pelo Project
 *     Information do Revit.
 *
 *   { type: "ABRIR_HIDRANTES" }
 *     Python -> JS: manda a aba do Dashboard trocar pra "hidrantes" (ver
 *     App.jsx, mesmo destino do cartão/atalho "Sistema de Hidrantes") —
 *     enviada por "Dimensionar Hidrantes" (family_loader_webview_forms.
 *     abrir_secao_hidrantes) ao final de um dimensionamento bem-sucedido,
 *     pra o RT já cair direto nos resultados na dockpane, sem precisar
 *     abrir o painel e navegar até lá manualmente. Sem payload.
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
  SET_HIDRANTES_CLASSIFICACAO: "SET_HIDRANTES_CLASSIFICACAO",
  HIDRANTES_CLASSIFICACAO_SAVED: "HIDRANTES_CLASSIFICACAO_SAVED",
  GET_HIDRANTES_DIMENSIONAMENTO: "GET_HIDRANTES_DIMENSIONAMENTO",
  HIDRANTES_DIMENSIONAMENTO: "HIDRANTES_DIMENSIONAMENTO",
  ABRIR_HIDRANTES: "ABRIR_HIDRANTES",
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
