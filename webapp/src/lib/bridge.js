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
 * Mensagens do Dashboard (vínculo projeto/estruturas — ver
 * lib/projectData.js e project_link_bridge.py do lado Python):
 *
 * Um arquivo Revit pode conter várias estruturas modeladas juntas — o
 * vínculo é com um CONJUNTO de estruturas (`estruturas`, lista de
 * {id, nome}), não mais uma só. Esse conjunto não atribui nada sozinho:
 * é só a lista de opções da ferramenta "Atribuir seleção à estrutura"
 * (ver ASSIGN_ESTRUTURA_SELECAO abaixo) — cada família/ambiente carrega a
 * própria estrutura no parâmetro Revit "Estrutura", nunca herdada do
 * vínculo. Hidrantes é a exceção: sistema único, compartilhado entre
 * todas as estruturas do projeto, sem relação nenhuma com isso.
 *
 *   { type: "GET_PROJECT_LINK" }
 *     JS -> Python: pede o vínculo salvo no firedata.json do documento
 *     Revit ativo (a busca de projetos/estruturas em si é direto no
 *     Supabase, do lado do React — isto só lê o que já foi vinculado).
 *
 *   { type: "PROJECT_LINK", payload: { docSalvo, projetoId, projetoNome, estruturas: [{id, nome}, ...] } }
 *     Python -> JS: resposta de GET_PROJECT_LINK (e também reenviada depois
 *     de um SET_PROJECT_LINK ou DISCONNECT_PROJECT bem-sucedido).
 *     `docSalvo: false` quando não há documento Revit aberto ou ele ainda
 *     não foi salvo em disco — nesse caso os demais campos vêm null/[] e o
 *     Dashboard deve pedir pra salvar o projeto antes de vincular.
 *     `estruturas: []` com `projetoId` preenchido é um vínculo de projeto
 *     sem nenhuma estrutura escolhida ainda (tela "Selecione as estruturas").
 *
 *   { type: "SET_PROJECT_LINK", payload: { projetoId, projetoNome, estruturas: [{id, nome}, ...], uf, areaConstruida } }
 *     JS -> Python: grava o vínculo escolhido (projeto + 1 ou mais
 *     estruturas, já resolvidas no Supabase) no firedata.json do
 *     documento ativo. `estruturas` não pode vir vazio.
 *
 *   { type: "PROJECT_LINK_SAVED", payload: { ok, erro? } }
 *     Python -> JS: resultado de um SET_PROJECT_LINK ou DISCONNECT_PROJECT
 *     que falhou antes de conseguir persistir (ex.: documento não salvo).
 *     Em caso de sucesso, um PROJECT_LINK também é reenviado logo em
 *     seguida com o estado atualizado.
 *
 *   { type: "DISCONNECT_PROJECT" }
 *     JS -> Python: apaga o vínculo (projeto + estruturas) do documento
 *     ativo — usado pelo botão "Desconectar projeto" da sidebar.
 *
 *   { type: "GET_DIMENSIONAMENTOS_STATUS", payload?: { estruturaId } }
 *     JS -> Python: pede o status (feito/não feito) dos dimensionamentos já
 *     calculados localmente. `estruturaId` é a estrutura sendo vista no
 *     momento no Dashboard — escopa Saída de Emergência/Correlacionar
 *     Níveis a ela; omitido, os dois caem pra "existe algo sincronizado, de
 *     qualquer estrutura?". Hidrantes (`hidrantes`) nunca depende disso —
 *     sistema único do projeto inteiro.
 *
 *   { type: "DIMENSIONAMENTOS_STATUS", payload: { hidrantes: boolean, saidaEmergencia: boolean, niveis: boolean } }
 *     Python -> JS: resposta de GET_DIMENSIONAMENTOS_STATUS.
 *
 *   { type: "ASSIGN_ESTRUTURA_SELECAO", payload: { estruturaNome } }
 *     JS -> Python: escreve `estruturaNome` no parâmetro de instância
 *     "Estrutura" de todos os elementos selecionados no momento no Revit
 *     (seleção nativa — esta mensagem não manda a lista de elementos, só
 *     o nome; quem decide o que está selecionado é o Revit). Categorias
 *     sem o parâmetro (fora de Proteção contra Incêndio, Dispositivos de
 *     Segurança, Luminárias, Ambientes e Dispositivos de Alarme de
 *     Incêndio) são ignoradas, não dá erro. Selecionar a TAG de um
 *     ambiente vale o mesmo que selecionar o ambiente (resolvido pro
 *     Room por trás). Botão "Atribuir seleção à estrutura" do Dashboard.
 *
 *   { type: "ESTRUTURA_ATRIBUIDA", payload: { ok, erro?, estruturaNome?, marcados?, ignorados? } }
 *     Python -> JS: resultado de um ASSIGN_ESTRUTURA_SELECAO. `ok: false`
 *     também quando nada foi selecionado no Revit, ou nenhum elemento
 *     selecionado tinha o parâmetro (`erro` explica qual caso).
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
 *     uma mudança), o cache completo do último "Dimensionar Hidrantes" e os
 *     limites normativos de velocidade.
 *
 *   { type: "HIDRANTES_DIMENSIONAMENTO", payload: { ok, erro?,
 *     classificacao?: { tipo, variante_idx, descricao, esguicho_dn, mang_dn,
 *       mang_comp, expedicoes, q_min, p_min, valorSistema, metodo, chw },
 *     norma?: string,
 *     limites?: { vMaxTubulacao, vMaxSuccaoPositiva, vMaxSuccaoNegativa },
 *     dimensionamento?: object | null,
 *     erroDimensionamento?: string | null } }
 *     `classificacao` não inclui `rti` — quem quiser mostrar RTI lê direto
 *     do Supabase (dadosHidrantes(projeto).rti, ver lib/projetoDados.js),
 *     nunca do Project Information (ver comentário de
 *     SET_HIDRANTES_CLASSIFICACAO acima pra por quê).
 *     Python -> JS: resposta de GET_HIDRANTES_DIMENSIONAMENTO. `dimensionamento`
 *     é o cache cru de "Dimensionar Hidrantes" (res, dados_sistema,
 *     valor_sistema, metodo, C_HW, succao, ranking_hidrantes, cotas... —
 *     mesmo formato que o site lê de state.hidrantes.dimensionamento, ver
 *     HidrantesPage.jsx lá), repassado sem reduzir — `res.P_RTI` é a altura
 *     manométrica total que a bomba precisa desenvolver (pressão que
 *     precisaria existir na RTI, referência atmosférica, pra alimentar o
 *     sistema por gravidade; já inclui sucção e recalque) e `res.Qt` a
 *     vazão total. Vem `null` quando "Dimensionar Hidrantes" ainda não
 *     rodou nesta sessão do projeto (ver erroDimensionamento).
 *     A eficiência da bomba e a potência adotada NÃO vêm daqui — são lidas/
 *     gravadas direto no Supabase (dados.hidrantes.bombaEficiencia/
 *     bombaPotenciaAdotada, ver lib/projetoDados.js e
 *     SistemaHidrantesPage.jsx), o mesmo campo que o site edita na Etapa 3
 *     ("Dimensionamento da Bomba de Incêndio"), sem passar pelo Project
 *     Information do Revit.
 *
 *   { type: "DIMENSIONAR_HIDRANTES", payload: { accessToken } }
 *     JS -> Python: dimensiona o sistema de hidrantes (método da marcha HD01
 *     → Ponto A → Descarga da Bomba → RTI). O Python lê o modelo (trechos
 *     por diâmetro, cotas, classificação — ver hidrantes_dimensionar_bridge.py)
 *     e manda para o motor de cálculo na nuvem (Edge Function motor-hidrantes);
 *     nenhuma fórmula roda no plugin. `accessToken` é o token da sessão do
 *     Supabase, que o motor exige — a anon key não basta. Precisa de
 *     classificação já aplicada (Etapa 1, "Aplicar no Revit"), de "Mapear
 *     Trechos" já executado alguma vez nesse projeto (cache de rotas) e de
 *     internet.
 *
 *   { type: "HIDRANTES_DIMENSIONAR_RESULTADO", payload: { ok, erro?, categoria? } }
 *     Python -> JS: resultado de um DIMENSIONAR_HIDRANTES. `erro` é texto
 *     pronto pra exibir e `categoria` diz por que falhou, pra escolher o
 *     título do aviso: "norma" (o motor rodou e o sistema não atende, ou os
 *     dados não fecham), "requisito" (falta classificação, mapeamento ou a
 *     elevação de algum ponto), "conexao" (sem internet), "sessao"
 *     (expirada), "licenca" (módulo não contratado), "limite" (pedidos
 *     demais) e "servidor". Quem precisar localizar o elemento problemático
 *     usa SELECIONAR_TRECHO_HIDRANTE.
 *     Em caso de sucesso (`ok: true`), o cache de dimensionamento já foi
 *     gravado — quem recebe essa mensagem deve mandar
 *     GET_HIDRANTES_DIMENSIONAMENTO em seguida pra buscar o resultado
 *     completo, em vez de esta mensagem carregar os dados duas vezes.
 *
 *   { type: "GRAVAR_QUANTITATIVOS" }
 *     JS -> Python: dispara a coleta de TODAS as medidas de quantitativo
 *     (Extintores, Sinalização de Emergência, Iluminação de Emergência)
 *     do modelo Revit ativo, separa os itens de cada uma pela estrutura do
 *     parâmetro "Estrutura" (ver estrutura_param.py), grava o firedata.json
 *     e envia pro site um lote por (medida, estrutura) — sem seleção
 *     nenhuma (sempre todas as medidas) e sem abrir nenhum outro painel
 *     (nem janela WPF, nem o output window do pyRevit).
 *
 *   { type: "QUANTITATIVOS_GRAVADOS", payload: { ok, erro?,
 *     medidas?: [{ chave, rotulo, estruturaNome, quantidade, enviado, motivo?,
 *       erro?, naoReconhecidos?: string[] }] } }
 *     Python -> JS: resultado de um GRAVAR_QUANTITATIVOS. `ok: false` só
 *     quando nem chegou a rodar (ex.: projeto não salvo) — `erro` traz o
 *     motivo. Com `ok: true`, `medidas` traz uma entrada POR ESTRUTURA
 *     resolvida de cada medida (uma mesma `chave`/`rotulo` pode aparecer
 *     várias vezes, uma por estrutura, se o modelo tiver mais de uma) —
 *     `estruturaNome` identifica qual; `quantidade` é o nº de itens
 *     gravados nela; `enviado` é null quando a medida falhou antes de
 *     chegar no envio, `false` quando gravou local mas não conseguiu
 *     enviar pro site (ver `motivo`), e `true` quando gravou e enviou.
 *     Também pode vir uma entrada com `estruturaNome: null` e
 *     `naoReconhecidos` preenchido — itens cujo parâmetro "Estrutura"
 *     estava vazio ou não bateu com nenhuma estrutura do projeto, listados
 *     por nome/texto cru pra ajudar a achar o quê corrigir; esses itens
 *     NÃO são enviados. `erro`, por medida (ou por medida+estrutura), é só
 *     pra falha ao preparar/coletar/gravar — vira uma notificação (ver
 *     ToastStack.jsx), nunca interrompe as demais.
 *
 *   { type: "SELECIONAR_TRECHO_HIDRANTE", payload: { rota: number[] } }
 *     JS -> Python: seleciona e enquadra, na view ativa do Revit, todo o
 *     trecho (Bomba -> válvula) de um hidrante — botão "Localizar" da
 *     tabela "Verificação do Hidrante Mais Desfavorável"
 *     (HidrantesDimensionamento.jsx). `rota` é o campo de mesmo nome de um
 *     item de `ranking_hidrantes` (dentro de `dimensionamento`, ver
 *     HIDRANTES_DIMENSIONAMENTO acima) — ausente/vazio num ranking salvo
 *     antes dessa rota existir (reexecute "Mapear Trechos" pra preencher).
 *     Fire-and-forget: não há resposta — sucesso já aparece no Revit, e uma
 *     falha mostra um alerta nativo por lá (mesmo botão "Localizar"/
 *     "Mostrar no Projeto" das janelas do pushbutton "Mapear Trechos").
 *
 *   { type: "GET_REVIT_LEVELS", payload: { estruturaId } }
 *     JS -> Python: pede os níveis (Level) do documento Revit ativo,
 *     ordenados por elevação, pro painel "Correlacionar Níveis"
 *     (CorrelacaoNiveisModal.jsx) — nem sempre o nome do nível no Revit
 *     bate com o pavimento cadastrado no site (ex.: "Nível 1" em vez de
 *     "Térreo"), então o usuário alinha as duas listas manualmente
 *     arrastando, em vez do plugin tentar adivinhar por nome.
 *     `estruturaId` também traz de volta a correlação já salva (se houver)
 *     pra essa estrutura, pronta pra reabrir o painel já no estado salvo.
 *
 *   { type: "REVIT_LEVELS", payload: { levels: [{ uniqueId, nome, elevacao }],
 *     correlacao: [{ pavimentoId, nivelUniqueId, nivelNome }], erro? } }
 *     Python -> JS: resposta de GET_REVIT_LEVELS. `correlacao` é a
 *     correlação salva por último (ver SET_NIVEIS_CORRELACAO) — vazia se
 *     a estrutura nunca foi correlacionada ainda.
 *
 *   { type: "SET_NIVEIS_CORRELACAO", payload: { estruturaId,
 *     correlacao: [{ pavimentoId, nivelUniqueId, nivelNome }] } }
 *     JS -> Python: grava a correlação Nível do Revit <-> Pavimento do
 *     FireUtils no firedata.json do documento ativo, por estrutura — fica
 *     só local (não vai pro Supabase): um `Level` é um elemento deste
 *     documento Revit, não faz sentido compartilhar entre documentos
 *     diferentes vinculados à mesma estrutura. Chave persistida é o
 *     `Level.UniqueId` (sobrevive a um rename do nível no Revit).
 *
 *   { type: "NIVEIS_CORRELACAO_SAVED", payload: { ok, erro? } }
 *     Python -> JS: resultado de um SET_NIVEIS_CORRELACAO.
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
  DIMENSIONAR_HIDRANTES: "DIMENSIONAR_HIDRANTES",
  HIDRANTES_DIMENSIONAR_RESULTADO: "HIDRANTES_DIMENSIONAR_RESULTADO",
  GRAVAR_QUANTITATIVOS: "GRAVAR_QUANTITATIVOS",
  QUANTITATIVOS_GRAVADOS: "QUANTITATIVOS_GRAVADOS",
  ASSIGN_ESTRUTURA_SELECAO: "ASSIGN_ESTRUTURA_SELECAO",
  ESTRUTURA_ATRIBUIDA: "ESTRUTURA_ATRIBUIDA",
  SELECIONAR_TRECHO_HIDRANTE: "SELECIONAR_TRECHO_HIDRANTE",
  GET_REVIT_LEVELS: "GET_REVIT_LEVELS",
  REVIT_LEVELS: "REVIT_LEVELS",
  SET_NIVEIS_CORRELACAO: "SET_NIVEIS_CORRELACAO",
  NIVEIS_CORRELACAO_SAVED: "NIVEIS_CORRELACAO_SAVED",
  // Licenças: o Python precisa da sessão para verificar quais módulos a
  // conta pode usar — inclusive no startup do Revit seguinte, antes de esta
  // dockpane existir. Só o refresh token é enviado; o access token expira em
  // uma hora e não serviria para isso.
  SET_SESSAO: "SET_SESSAO",
  LIMPAR_SESSAO: "LIMPAR_SESSAO",
  GET_LICENCAS: "GET_LICENCAS",
  LICENCAS: "LICENCAS",
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
