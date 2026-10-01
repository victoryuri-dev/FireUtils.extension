/**
 * Decodifica a coluna `dados` (jsonb) de uma linha da tabela `projetos` —
 * schema real do site, sem tabela "estruturas" separada: um projeto tem
 * `dados.estruturas[]` (id, nome, areaTotal, alturaPisoPiso, altura, ...) e
 * `dados.pavimentos[]` (cada um com `estruturaId` + `divisao`, o código de
 * ocupação daquele pavimento). Tudo derivado aqui é client-side, a partir
 * de uma linha já buscada (lib/projectData.js) — sem chamada adicional.
 *
 * Importante: o código de ocupação "oficial" usado pelos módulos de
 * dimensionamento (dados_projeto.ocupacao_principal, ex.: "Dimensionar
 * Saídas") não é decidido aqui — quando uma estrutura tem mais de uma
 * divisão, o Python escolhe a mais restritiva (menor distância máxima,
 * tabela normativa do estado) ao receber SET_PROJECT_LINK, porque só ele
 * tem acesso a essa tabela (lib/normas). Este arquivo manda a lista de
 * divisões (`divisoes`) e mostra "Mista" na tela quando há mais de uma —
 * são coisas propositalmente diferentes.
 *
 * `resumoProjeto()` replica os cálculos do cartão de projeto do site
 * (ETOS.FireUtils, src/pages/ProjetosPage.jsx — ocupacaoInfo/maxCarga/
 * riscoInfo/pavimentosLabel/calcCompletude), pra mostrar o mesmo cartão
 * aqui na dockpane. `calcCompletude` é uma versão simplificada: o site
 * também confere, por pavimento, se tem CNAE cadastrado quando a divisão
 * não tem um (via tabela normativa própria dele, data/normas) — aqui só
 * confere se a divisão foi preenchida, sem essa tabela.
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
 * quando há mais de uma, "—" sem nenhuma. */
function rotuloOcupacao(pavimentos) {
  const divisoes = divisoesDe(pavimentos);
  if (divisoes.length === 0) return "—";
  if (divisoes.length === 1) return divisoes[0];
  return "Mista";
}

/** Pavimentos (com subsolos) da estrutura que tem mais pavimentos;
 * "Térrea" se só tiver 1 — mesma leitura do site. */
function rotuloPavimentos(estruturas) {
  const total = (estruturas || []).reduce(
    (max, e) => Math.max(max, (Number(e.nPavimentos) || 1) + (Number(e.nSubsolos) || 0)),
    0
  );
  if (!total) return null;
  return total === 1 ? "Térrea" : `${total} pavimentos`;
}

/** Maior carga de incêndio (MJ/m²) entre todas as estruturas/divisões do
 * projeto — mesma leitura direta de cargaState que o site usa no cartão. */
function maiorCargaIncendio(cargaState) {
  let maior = 0;
  Object.values(cargaState || {}).forEach((porEstrutura) => {
    Object.values(porEstrutura || {}).forEach((c) => {
      const valor = c?.metodo === "levantamento" ? paraNumero(c?.valorManual) || 0 : c?.cargaIncendio || 0;
      if (valor > maior) maior = valor;
    });
  });
  return maior;
}

/** Mesmos limiares de risco (300/1200 MJ/m²) do site. */
function rotuloRisco(cargaIncendio) {
  if (!cargaIncendio) return { label: "—", tom: "neutral" };
  if (cargaIncendio <= 300) return { label: "Baixo", tom: "green" };
  if (cargaIncendio <= 1200) return { label: "Médio", tom: "amber" };
  return { label: "Alto", tom: "red" };
}

function calcCompletude(dados) {
  const areaEstruturas = (dados.estruturas || []).reduce((soma, e) => soma + (paraNumero(e.areaTotal) || 0), 0);
  const area = paraNumero(dados.areaConstruidaTotal) || areaEstruturas;
  const checks = [
    !!(dados.nome && dados.endereco && dados.cidade),
    !!(dados.estruturas?.length && dados.estruturas.every((e) => e.areaTotal && e.altura)),
    !!dados.propNome,
    !!(dados.rtNome && (!dados.usaArt || dados.artNumero)),
    !!(dados.pavimentos?.length > 0 && dados.pavimentos.every((p) => !!p.divisao)),
    !!(Object.keys(dados.cargaState || {}).length > 0),
    true,
    !!(dados.nome && area > 0 && dados.pavimentos?.length > 0),
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

function tomPorCompletude(pct) {
  if (pct === 100) return "green";
  if (pct >= 30) return "amber";
  return "red";
}

/** Resumo de um projeto pra grade da tela "Conectar um projeto" — mesmos
 * campos do cartão de projeto do site. */
export function resumoProjeto(linha) {
  const dados = linha.dados || {};
  const pct = calcCompletude(dados);
  return {
    id: linha.id,
    nome: dados.nome || linha.nome,
    uf: dados.uf || null,
    ocupacao: rotuloOcupacao(dados.pavimentos),
    risco: rotuloRisco(maiorCargaIncendio(dados.cargaState)),
    pavimentosLabel: rotuloPavimentos(dados.estruturas),
    tipoProjetoLabel: dados.tipoProjeto === "dimensionamento" ? "Dimensionamento" : "Técnico",
    completude: { pct, tom: tomPorCompletude(pct) },
    createdAt: dados.createdAt || linha.created_at || null,
    updatedAt: dados.updatedAt || linha.updated_at,
  };
}

/** Estruturas cadastradas no projeto — pra tela "Selecione uma estrutura"
 * e o seletor de estrutura do dashboard. */
export function estruturasDoProjeto(linha) {
  return ((linha.dados && linha.dados.estruturas) || []).map((e) => ({ id: e.id, nome: e.nome }));
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
