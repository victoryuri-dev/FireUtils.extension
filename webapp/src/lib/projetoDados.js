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
