/**
 * Decodifica a coluna `dados` (jsonb) de uma linha da tabela `projetos` —
 * schema real do site, sem tabela "estruturas" separada: um projeto tem
 * `dados.estruturas[]` (id, nome, areaTotal, alturaPisoPiso, altura, ...) e
 * `dados.pavimentos[]` (cada um com `estruturaId` + `divisao`, o código de
 * ocupação daquele pavimento). Tudo derivado aqui é client-side, a partir
 * de uma linha já buscada (lib/projectData.js) — sem chamada adicional.
 *
 * `divisoes` (lista de códigos de ocupação dos pavimentos da estrutura)
 * só alimenta a exibição local: mostra "Mista" na tela quando a estrutura
 * tem mais de uma.
 */

function paraNumero(valor) {
  if (valor === undefined || valor === null || valor === "") return null;
  const numero = Number(valor);
  return Number.isNaN(numero) ? null : numero;
}

function divisoesDe(pavimentos) {
  return Array.from(new Set((pavimentos || []).map((p) => p.divisao).filter(Boolean)));
}

/** "D-1" quando só há uma divisão nos pavimentos informados, "Mista"
 * quando há mais de uma, null sem nenhuma. */
function rotuloOcupacao(pavimentos) {
  const divisoes = divisoesDe(pavimentos);
  if (divisoes.length === 0) return null;
  if (divisoes.length === 1) return divisoes[0];
  return "Mista";
}

function rotuloPavimentos(estruturas) {
  const total = (estruturas || []).reduce((soma, e) => soma + (Number(e.nPavimentos) || 0), 0);
  if (total <= 1) return "Térrea";
  return `${total} pavimentos`;
}

/** Resumo de um projeto pra grade da tela "Conectar um projeto". */
export function resumoProjeto(linha) {
  const dados = linha.dados || {};
  return {
    id: linha.id,
    nome: dados.nome || linha.nome,
    uf: dados.uf || null,
    areaConstruida: paraNumero(dados.areaConstruidaTotal),
    ocupacao: rotuloOcupacao(dados.pavimentos),
    pavimentosLabel: rotuloPavimentos(dados.estruturas),
    updatedAt: linha.updated_at,
  };
}

/** Estruturas cadastradas no projeto — pra tela "Selecione uma estrutura"
 * e o seletor de estrutura do dashboard. */
export function estruturasDoProjeto(linha) {
  return ((linha.dados && linha.dados.estruturas) || []).map((e) => ({ id: e.id, nome: e.nome }));
}

/** Pavimentos "crus" de uma estrutura — objetos completos (id, label,
 * estruturaId, pisoDescarga, divisao, ambientes, acessos), na ordem
 * cadastrada no site (do mais baixo pro mais alto). Usado pela tela de
 * Saída de Emergência (lista de pavimentos + árvore de Acessos e
 * Descargas — components/dashboard/SaidaEmergenciaPage.jsx e
 * AcessosDescargasView.jsx), que precisa editar os campos direto, ao
 * contrário de dashboardEstrutura (só deriva valores agregados
 * pro dashboard). */
export function pavimentosCompletos(linha, estruturaId) {
  const dados = linha.dados || {};
  return (dados.pavimentos || []).filter((p) => p.estruturaId === estruturaId);
}

/** Chuveiros automáticos / detecção de incêndio da estrutura — badges
 * somente-leitura na tela de Saída de Emergência (a edição de verdade é
 * na Etapa "Medidas de Segurança" do site). Simplificação: lê só o
 * override manual salvo em `sistemasPorEstrutura` — não recalcula se o
 * sistema é normativamente obrigatório pra essa ocupação/altura/área
 * (esse motor de normas só existe no site, ver useMedidasObrigatorias.js
 * lá); na prática cobre a maioria dos casos, já que nenhum dos dois é
 * obrigatório por padrão na maior parte das ocupações. */
export function sistemasAtivos(linha, estruturaId) {
  const manual = (linha.dados && linha.dados.sistemasPorEstrutura && linha.dados.sistemasPorEstrutura[estruturaId]) || {};
  return {
    sprinklers: !!manual.sprinklers,
    deteccao: !!manual.deteccao,
  };
}

/** Carga de incêndio (MJ/m²) de uma divisão a partir de dados.cargaState —
 * mesmo critério do site (extintores_calc.js:cargaDaDivisao): usa o valor
 * de levantamento quando esse foi o método escolhido, senão o valor de
 * tabela já resolvido e sincronizado (nunca recalcula por CNAE aqui). */
function cargaDaDivisao(divisao, cargaState) {
  const st = cargaState?.[divisao];
  if (!st) return null;
  if (st.metodo === "levantamento") return paraNumero(st.valorManual);
  return typeof st.cargaIncendio === "number" ? st.cargaIncendio : null;
}

/** [{ divisao, cargaMJm2 }] de uma estrutura — cada divisão (principal ou
 * subsidiária de acesso) presente nos pavimentos da estrutura, com a maior
 * carga de incêndio já classificada pra ela. Insumo da classificação do
 * Sistema de Hidrantes (Tabela 3) direto na dockpane — ver
 * lib/hidrantesClassificacao.js:sugerirClassificacao — mesma agregação que
 * FormularioSistema.jsx faz no site (state.pavimentos + state.cargaState),
 * só que lendo direto da linha do Supabase já sincronizada. */
export function divisoesComCargaDaEstrutura(linha, estruturaId) {
  const dados = linha.dados || {};
  const cargaState = (dados.cargaState && dados.cargaState[estruturaId]) || {};
  const porDivisao = new Map();
  (dados.pavimentos || [])
    .filter((p) => p.estruturaId === estruturaId)
    .forEach((p) => {
      const divs = [p.divisao, ...(p.acess || []).map((a) => a.divisao)].filter(Boolean);
      divs.forEach((divisao) => {
        const carga = cargaDaDivisao(divisao, cargaState);
        if (carga == null) return;
        const atual = porDivisao.get(divisao);
        if (atual == null || carga > atual) porDivisao.set(divisao, carga);
      });
    });
  return [...porDivisao.entries()].map(([divisao, cargaMJm2]) => ({ divisao, cargaMJm2 }));
}

/** Classificação do Sistema de Hidrantes/Mangotinhos (Tabela 3 da norma) —
 * decidida no site a partir da área + ocupação + carga de incêndio do
 * projeto inteiro (não por estrutura — ver comentário de state.hidrantes
 * em ETOS.FireUtils/src/context/ProjetoContext.jsx). `tipo` null quando o
 * RT ainda não classificou nada no site.
 *
 * `metodoCalculo`/`succaoAltitude`/`succaoTemperatura` migraram pro site
 * junto com a remoção do pushbutton "Classificar Sistema de Hidrante" do
 * plugin — são enviados ao Revit no mesmo SET_HIDRANTES_CLASSIFICACAO
 * (ver aplicar() em components/dashboard/DashboardEstrutura.jsx). */
export function dadosHidrantes(linha) {
  const h = (linha.dados && linha.dados.hidrantes) || {};
  return {
    tipo: typeof h.tipo === "number" ? h.tipo : null,
    tipoVariante: typeof h.tipoVariante === "number" ? h.tipoVariante : 0,
    rti: paraNumero(h.rti),
    metodoCalculo: h.metodoCalculo || null,
    succaoAltitude: paraNumero(h.succaoAltitude),
    succaoTemperatura: paraNumero(h.succaoTemperatura),
  };
}

/** Dados completos de uma estrutura específica pro dashboard. */
export function dashboardEstrutura(linha, estruturaId) {
  const dados = linha.dados || {};
  const estrutura = (dados.estruturas || []).find((e) => e.id === estruturaId);
  if (!estrutura) return null;

  const pavimentosEstrutura = (dados.pavimentos || []).filter((p) => p.estruturaId === estruturaId);

  const cargas = (dados.cargaState && dados.cargaState[estruturaId]) || {};
  let cargaIncendio = null;
  Object.values(cargas).forEach((c) => {
    if (c && typeof c.cargaIncendio === "number") {
      cargaIncendio = cargaIncendio === null ? c.cargaIncendio : Math.max(cargaIncendio, c.cargaIncendio);
    }
  });

  return {
    id: estrutura.id,
    nome: estrutura.nome,
    uf: dados.uf || null,
    areaConstruida: paraNumero(estrutura.areaTotal),
    areaTerreno: paraNumero(dados.areaTerreno),
    alturaPisoAPiso: paraNumero(estrutura.alturaPisoPiso),
    alturaEdificacao: paraNumero(estrutura.altura),
    ocupacao: rotuloOcupacao(pavimentosEstrutura),
    divisoes: divisoesDe(pavimentosEstrutura),
    cargaIncendio,
  };
}
