// ─────────────────────────────────────────────────────────────────────────────
// se_calc.js — Funções universais de dimensionamento de Saídas de Emergência
// Recebem os dados normativos do estado como parâmetro; não importam nenhum
// arquivo de estado diretamente.
// ─────────────────────────────────────────────────────────────────────────────

/** Largura mínima de PT para N UPs (recebe array LARGURAS_MINIMAS.PT) */
export function getLargMinPT(nUp, ptTable) {
  return ptTable.find(e => e.n_up === nUp) ?? (nUp > ptTable.at(-1).n_up ? ptTable.at(-1) : ptTable[0])
}

/** Capacidades por UP (mínima entre divisões presentes) para uma lista
 * qualquer de ambientes — generaliza capPavimento pra poder ser aplicada
 * também a um nó de Acesso (subconjunto de ambientes), não só ao
 * pavimento inteiro. */
export function capAmbientes(ambientes, taxaPopulacional) {
  const divs = [...new Set(ambientes.map(a => a.divisao).filter(d => d && taxaPopulacional[d]))]
  if (!divs.length) return { AD: 100, ER: 75, PT: 100 }
  return {
    AD: Math.min(...divs.map(d => taxaPopulacional[d].AD)),
    ER: Math.min(...divs.map(d => taxaPopulacional[d].ER)),
    PT: Math.min(...divs.map(d => taxaPopulacional[d].PT)),
  }
}

/** Capacidades por UP para um pavimento inteiro (mínima entre divisões presentes) */
export function capPavimento(pav, taxaPopulacional) {
  return capAmbientes(pav.ambientes, taxaPopulacional)
}

/** Taxa da arquibancada (nota Q): 1 pessoa por 0,50 m linear de banco. */
export const ARQUIBANCADA_TAXA = { M: 0.5, obs: '1 pessoa por 0,50 m linear' }

/** Só a ocupação F-3 (centro esportivo e de exibição) tem arquibancada. */
export const divisaoComArquibancada = divisao => divisao === 'F-3'

/** População da arquibancada: comprimento de banco (m) / 0,50 m por pessoa. */
export function calcPopArquibancada(amb) {
  if (!amb.arquibancada || !divisaoComArquibancada(amb.divisao)) return 0
  return Math.ceil((parseFloat(amb.arquibancadaComprimento) || 0) / ARQUIBANCADA_TAXA.M)
}

function calcPopBase(amb, taxaPopulacional) {
  if (amb.popTipo === 'fixo')   return Math.max(0, parseInt(amb.assentos)  || 0)
  if (amb.popTipo === 'manual') return Math.max(0, parseInt(amb.popManual) || 0)
  const taxa = taxaPopulacional[amb.divisao]
  if (!taxa || taxa.A === null) return Math.max(0, parseInt(amb.popManual) || 0)
  return Math.ceil((parseFloat(amb.area) || 0) / taxa.A)
}

/** Calcula a população de um ambiente (+ arquibancada, quando houver) */
export function calcPopAmb(amb, taxaPopulacional) {
  return calcPopBase(amb, taxaPopulacional) + calcPopArquibancada(amb)
}

/** População que o ambiente soma no total da edificação (pavimento, acessos,
 * escadas, brigada). Área de apoio (`areaApoio`) usa a população de outros
 * ambientes — não soma aqui; calcPopAmb continua valendo pra sua própria porta. */
export function calcPopContada(amb, taxaPopulacional) {
  return amb.areaApoio ? 0 : calcPopAmb(amb, taxaPopulacional)
}

/** Calcula a população total de um pavimento */
export function calcPopPav(pav, taxaPopulacional) {
  return pav.ambientes.reduce((s, a) => s + calcPopContada(a, taxaPopulacional), 0)
}

/** Pavimento mais populoso excluindo piso de descarga */
export function pavMaisPopuloso(pavimentos, taxaPopulacional) {
  return pavimentos
    .filter(p => p.tipo !== 'descarga')
    .reduce((mx, p) => calcPopPav(p, taxaPopulacional) > (mx ? calcPopPav(mx, taxaPopulacional) : -1) ? p : mx, null)
}

/** Cálculo de largura/UPs a partir de população e capacidade por UP —
 * fórmula compartilhada por AD (Acessos/Descarga) e ER (Escadas/Rampas):
 * só muda qual capacidade e largura mínima entram. */
function calcLarguraFluxo(pop, cap, minimo, larguras) {
  const n  = Math.ceil(pop / cap)
  const lc = +(n * larguras.LARG_UP).toFixed(2)
  return { n, lc, la: Math.max(lc, minimo), lMin: minimo }
}

/** Cálculo de AD (Acessos/Descarga) para um pavimento ou nó de Acesso */
export function calcAD(pop, capAD, larguras) {
  return calcLarguraFluxo(pop, capAD, larguras.AD, larguras)
}

/** Cálculo de ER (Escadas/Rampas) */
export function calcER(pop, capER, larguras) {
  return calcLarguraFluxo(pop, capER, larguras.ER, larguras)
}

/** Largura de porta pra N UP: dentro da faixa tabelada (n_up com entrada
 * exata em larguras.PT), o valor cadastrado na tabela manda — mesmo que
 * N×LARG_UP desse um número maior, é a norma (a tabela) que define a
 * largura pra essa faixa, não a multiplicação. Só extrapola
 * multiplicando por LARG_UP quando N passa do maior n_up tabelado (fora
 * da faixa coberta — ver getLargMinPT). Sem isso, editar a tabela
 * (ex.: via Supabase) não tinha efeito nenhum nas faixas onde
 * N×LARG_UP já era maior que o valor cadastrado. */
function larguraPT(n, larguras) {
  const ptInfo = getLargMinPT(n, larguras.PT)
  const lc     = +(n * larguras.LARG_UP).toFixed(2)
  const dentroTabela = larguras.PT.some(e => e.n_up === n)
  return { lc, ptInfo, la: dentroTabela ? ptInfo.largura : Math.max(lc, ptInfo.largura) }
}

/** Cálculo de PT — recebe a população e a capacidade já resolvidas por
 * quem chama (um ambiente sozinho, na rede de saída; ou um pavimento
 * inteiro, no modelo antigo) */
export function calcPT(pop, capPT, larguras) {
  const n = Math.ceil(pop / capPT)
  const { lc, ptInfo, la } = larguraPT(n, larguras)
  return { n, lc, la, lMin: ptInfo.largura, tipo: ptInfo.tipo }
}

// ── Rede de saída (Ambiente -> Acesso -> Saída ou Escada/Rampa) ──────────────
//
// Fluxograma montado pelo usuário por pavimento (ver pages/medidas/
// FluxogramaSaidas.jsx), sem limite de profundidade:
//
//   ambiente.acessoId : string|null
//     -- a qual nó (acesso/saída/escada) este ambiente alimenta. Derivado do
//        grupo de ambientes (`grupo`) em que o ambiente está: o reducer mantém
//        `ambiente.acessoId === grupo.acessoId` — null = grupo ainda sem
//        ligação (ou ambiente fora de qualquer grupo).
//
//   acesso = { id, nome, tipo, alimentaEm: string|null, dims }
//     -- `tipo`: 'acesso' (nó intermediário, corredor/porta de passagem),
//        'saida' ou 'escada' (Escada/Rampa) — o usuário escolhe por nó.
//     -- `alimentaEm` aponta pro id do nó seguinte (cascata: a população
//        deste nó soma na do próximo). Saída e escada são as RAÍZES do
//        fluxo (alimentaEm null); um 'acesso' sem `alimentaEm` ainda não
//        foi ligado a nenhuma saída/escada e não conta como raiz.
//     -- Nós salvos antes de `tipo` existir (sem o campo): raiz vira
//        saída/escada conforme `pavimento.pisoDescarga`, o resto é acesso.
//     -- A "quantidade de saídas" do pavimento NÃO é um campo armazenado —
//        é sempre a contagem de raízes (ver contarSaidasPavimento).
//
// O dimensionamento padrão de um nó (ver dimsPadrao) vem do `tipo`: escada
// -> ER, saída/acesso -> AD. Cada nó ainda liga/desliga AD/ER/PT à parte
// (`dims`).
//
// Portas (PT) não passam por essa rede: são por ambiente, direto —
// ver calcNoAmbientePT.

/** Raiz do fluxo = saída ou escada/rampa (nó que não alimenta outro).
 * Acesso solto (tipo 'acesso' sem `alimentaEm`) não é raiz. */
export function ehRaiz(acesso) {
  return acesso.alimentaEm === null && acesso.tipo !== 'acesso'
}

/** Raízes do pavimento (saídas e escadas/rampas). */
export function raizesDoPavimento(acessos) {
  return (acessos || []).filter(ehRaiz)
}

/** Quantidade de saídas de um pavimento = quantidade de raízes do
 * fluxo — nunca um campo indicado manualmente. */
export function contarSaidasPavimento(acessos) {
  return raizesDoPavimento(acessos).length
}

/** Tipo do nó ('acesso'|'saida'|'escada'), com fallback pros nós antigos
 * sem o campo — ver explicação acima. `pisoDescarga` é do pavimento. */
export function tipoNo(acesso, pisoDescarga) {
  if (acesso.tipo) return acesso.tipo
  if (acesso.alimentaEm !== null) return 'acesso'
  return pisoDescarga ? 'saida' : 'escada'
}

function ambientesDiretosDoAcesso(acessoId, ambientes) {
  return ambientes.filter(a => a.acessoId === acessoId)
}

function acessosFilhosDiretos(acessoId, acessos) {
  return acessos.filter(ac => ac.alimentaEm === acessoId)
}

/** Todos os ambientes que alimentam um nó de Acesso, direta ou
 * indiretamente (atravessando quantos níveis de cascata houver) — usado
 * pra achar a capacidade (mínimo AD/ER) do nó. */
export function ambientesDoAcesso(acessoId, ambientes, acessos) {
  const diretos = ambientesDiretosDoAcesso(acessoId, ambientes)
  const dosFilhos = acessosFilhosDiretos(acessoId, acessos)
    .flatMap(ac => ambientesDoAcesso(ac.id, ambientes, acessos))
  return [...diretos, ...dosFilhos]
}

/** População acumulada de um nó de Acesso: soma dos ambientes que o
 * alimentam direto + a população (já acumulada) de qualquer outro acesso
 * que também o alimente (cascata) — recursivo, sem limite de profundidade. */
export function calcPopAcesso(acessoId, ambientes, acessos, taxaPopulacional) {
  const diretos = ambientesDiretosDoAcesso(acessoId, ambientes)
    .reduce((s, a) => s + calcPopContada(a, taxaPopulacional), 0)
  const dosFilhos = acessosFilhosDiretos(acessoId, acessos)
    .reduce((s, ac) => s + calcPopAcesso(ac.id, ambientes, acessos, taxaPopulacional), 0)
  return diretos + dosFilhos
}

/** Pacote pronto (população, capacidade, dimensionamento) pra um nó de
 * Acesso da rede de saída. `tipo` ('AD'|'ER') vem de tipoDoNo — decide se
 * usa a capacidade/largura mínima de Acessos/Descarga ou de Escadas/Rampas. */
export function calcNoAcesso(acessoId, ambientes, acessos, taxaPopulacional, larguras, tipo = 'AD') {
  const pop      = calcPopAcesso(acessoId, ambientes, acessos, taxaPopulacional)
  const cap      = capAmbientes(ambientesDoAcesso(acessoId, ambientes, acessos), taxaPopulacional)
  const capValor = tipo === 'ER' ? cap.ER : cap.AD
  const dim      = tipo === 'ER' ? calcER(pop, capValor, larguras) : calcAD(pop, capValor, larguras)
  return { pop, cap, capValor, dim, tipo }
}

/** Pacote pronto (população, capacidade, dimensionamento PT) pra um
 * ambiente — a porta é sempre por ambiente, nunca agregada com outros. */
export function calcNoAmbientePT(amb, taxaPopulacional, larguras) {
  const pop   = calcPopAmb(amb, taxaPopulacional)
  const capPT = taxaPopulacional[amb.divisao]?.PT ?? 100
  const pt    = calcPT(pop, capPT, larguras)
  return { pop, capPT, pt }
}

/** Dimensionamentos padrão de um nó pelo `tipo` ('acesso'|'saida'|
 * 'escada'): escada/rampa nasce só com ER; saída e acesso só com AD. PT
 * sempre nasce ligado. O usuário pode depois ligar/desligar cada um
 * independente (ver SET_ACESSO_DIM) — ex.: o ponto de descarga que recebe
 * tanto o corredor (AD) quanto a escada que desce até ali (ER) precisa dos
 * dois ao mesmo tempo. */
export function dimsPadrao(tipo) {
  return tipo === 'escada' ? { AD: false, ER: true, PT: true } : { AD: true, ER: false, PT: true }
}

/** `acesso.dims` com fallback pro padrão do tipo — projetos criados antes
 * deste campo existir não têm `dims` gravado; sem isso, um nó antigo
 * apareceria sem nenhum dimensionamento marcado. */
export function dimsDoAcesso(acesso, pisoDescarga) {
  return acesso.dims || dimsPadrao(tipoNo(acesso, pisoDescarga))
}

/** Dimensionamento de um nó de Acesso pra cada AD/ER/PT independentemente
 * habilitado em `dims` — ao contrário do modelo antigo (um nó só podia ser
 * AD OU ER), agora os dois podem coexistir no mesmo nó (ex.: o piso de
 * descarga que é ao mesmo tempo corredor de saída e chegada da escada).
 * Portas reaproveita o maior N de UP entre AD/ER habilitados (a porta
 * precisa comportar o maior fluxo que passa por ali) — mesmo N mínimo de 1
 * mesmo que nenhum dos dois esteja ligado, pra nunca calcular porta com
 * 0 UP. Retorna null em cada campo cujo dimensionamento está desligado. */
export function calcDimsAcesso(acessoId, ambientes, acessos, taxaPopulacional, larguras, dims, erDaEstrutura = null) {
  const pop = calcPopAcesso(acessoId, ambientes, acessos, taxaPopulacional)
  const cap = capAmbientes(ambientesDoAcesso(acessoId, ambientes, acessos), taxaPopulacional)
  const ad  = dims.AD ? calcAD(pop, cap.AD, larguras) : null
  // `erDaEstrutura` (ver calcErEstrutura): um único cálculo de escada/rampa vale
  // pra todas as escadas da estrutura — sem ele, cada nó calcula pela própria população.
  const er  = dims.ER ? (erDaEstrutura?.er ?? calcER(pop, cap.ER, larguras)) : null
  const nPorta = Math.max(ad?.n || 0, er?.n || 0, 1)
  const pt  = dims.PT ? calcPortaNoAcesso(nPorta, larguras) : null
  return { pop, cap, ad, er, pt, nPorta }
}

/** Dimensionamento ÚNICO de escada/rampa de uma estrutura: população do
 * pavimento mais populoso EXCETO o piso de descarga (o térreo), com a
 * capacidade por UP das divisões desse pavimento. O mesmo resultado vale pra
 * toda escada/rampa da estrutura. Sem nenhum pavimento acima do piso de
 * descarga (ou todos sem ambientes) devolve null — quem chama cai no
 * cálculo local do nó. `pavimentos` = pavimentos da estrutura. */
export function calcErEstrutura(pavimentos, taxaPopulacional, larguras) {
  const candidatos = (pavimentos || []).filter(p => !p.pisoDescarga)
  if (!candidatos.length) return null
  const [pav, pop] = candidatos
    .map(p => [p, calcPopPav({ ambientes: p.ambientes || [] }, taxaPopulacional)])
    .reduce((mx, par) => (par[1] > mx[1] ? par : mx))
  if (pop <= 0) return null
  const cap = capAmbientes(pav.ambientes || [], taxaPopulacional)
  return { pavimento: pav, pop, cap, er: calcER(pop, cap.ER, larguras) }
}

/** Largura mínima da porta de um nó de Acesso/Saída/Escada-Rampa —
 * reaproveita o mesmo N de UP já calculado pro AD/ER daquele nó (ver
 * calcNoAcesso) em vez de recalcular população/capacidade: a mesma vazão
 * que passa pelo corredor/escada precisa caber na porta daquele ponto.
 * Só busca a largura mínima de porta pra esse N na tabela PT — mesma
 * lógica de calcPT, sem o passo de `Math.ceil(pop / capacidade)`. */
export function calcPortaNoAcesso(n, larguras) {
  const { lc, ptInfo, la } = larguraPT(n, larguras)
  return { n, lc, la, lMin: ptInfo.largura, tipo: ptInfo.tipo }
}

/** Retorna o grupo de distância (terreo/demais) para uma divisão, a
 * partir do formato { mapa_ocupacao, grupos } (divisão -> id do grupo -> dados). */
export function getGrupoDistancia(divisao, distanciasMaximas) {
  const id = distanciasMaximas?.mapa_ocupacao?.[divisao]
  return id ? (distanciasMaximas.grupos?.[id] ?? null) : null
}

/** Distância máxima para uma divisão com os parâmetros dados.
 * `nSaidas`: quantidade de saídas do ponto em questão — no modelo de
 * rede, vem de contarSaidasPavimento (raízes da árvore daquele
 * pavimento), não mais indicado manualmente nem inferido do n de UPs. */
export function getDistancia(divisao, pisoDescarga, nSaidas, temChuveiros, temDeteccao, distanciasMaximas) {
  const grupo = getGrupoDistancia(divisao, distanciasMaximas)
  if (!grupo) return null
  const andar  = pisoDescarga ? grupo.terreo : grupo.demais
  const chuv   = temChuveiros ? 'com_chuveiro' : 'sem_chuveiro'
  const saidas = nSaidas > 1 ? 'mais_saidas' : 'saida_unica'
  const detec  = temDeteccao ? 'com_deteccao' : 'sem_deteccao'
  return andar?.[chuv]?.[saidas]?.[detec] ?? null
}

/** Distância máxima de um pavimento — usa a classificação de ocupação já
 * configurada nele na Etapa 4 (pav.divisao, ver Step4.jsx), não as
 * divisões dos ambientes cadastrados aqui em Saída de Emergência. Assim
 * aparece pra qualquer pavimento classificado, mesmo sem nenhum ambiente
 * ainda cadastrado no fluxograma de saídas. `pav.pisoDescarga` é
 * um booleano explícito por pavimento — ver ProjetoContext.jsx. */
export function getDistanciaPavimento(pav, nSaidas, temChuveiros, temDeteccao, distanciasMaximas) {
  if (!pav.divisao) return null
  return getDistancia(pav.divisao, pav.pisoDescarga, nSaidas, temChuveiros, temDeteccao, distanciasMaximas)
}

/** Rótulo da taxa global "população estimada" (popTipo 'manual'). */
export const POPULACAO_ESTIMADA_LABEL = 'População estimada'

/** Retorna as opções de taxa disponíveis para a divisão */
export function taxaOpcoes(divisao, taxaPopulacional) {
  const taxa = taxaPopulacional[divisao]
  if (!taxa) return []
  const opts = []
  if (taxa.A !== null) opts.push({ value:'area',   label: taxa.obs })
  if (taxa.notas?.includes('N')) opts.push({ value:'fixo', label:'Assentos fixos' })
  if (taxa.A === null)  opts.push({ value:'manual', label: taxa.obs })
  // Taxa global, vale pra qualquer ocupação: o usuário informa direto a população.
  else opts.push({ value:'manual', label: POPULACAO_ESTIMADA_LABEL })
  return opts
}

/** Tipo de população padrão para uma divisão */
export function popTipoPadrao(divisao, taxaPopulacional) {
  return taxaOpcoes(divisao, taxaPopulacional)[0]?.value || 'manual'
}

// ── Tipo de escada de emergência (Anexo C, Tabela 3) ────────────────────
// Só identifica o tipo pela altura piso a piso da estrutura x divisão de
// ocupação; as notas da tabela são apenas exibidas (por divisão + gerais).
// Aplica-se a edificação com mais de 1 pavimento (contando subsolos).
// Ocupação mista: vale o tipo mais restritivo (NE < EP < PF).

/** Faixa da Tabela 3 (índice em faixas_altura) para a altura H em metros. */
export function faixaAlturaEscada(altura, faixas) {
  const h = parseFloat(altura)
  if (!(h > 0) || !faixas?.length) return -1
  return faixas.findIndex(f => (f.min == null || h > f.min) && (f.max == null || h <= f.max))
}

/**
 * @param {object} estrutura       — usa alturaPisoPiso, nPavimentos, nSubsolos
 * @param {string[]} divisoes      — divisões de ocupação presentes na estrutura
 * @param {object} tiposEscada     — TIPOS_ESCADA da norma (null/undefined = UF sem tabela)
 * @returns {null | {status, faixa, porDivisao, exigido, notas}}
 *   status: 'nao_aplica' (1 pavimento) | 'sem_altura' | 'sem_divisao' | 'ok'
 */
export function tipoEscadaEstrutura(estrutura, divisoes, tiposEscada) {
  if (!tiposEscada) return null
  const totalPav = (parseInt(estrutura.nPavimentos) || 1) + (parseInt(estrutura.nSubsolos) || 0)
  if (totalPav <= 1) return { status: 'nao_aplica' }

  const idx = faixaAlturaEscada(estrutura.alturaPisoPiso, tiposEscada.faixas_altura)
  if (idx < 0) return { status: 'sem_altura' }
  // Chave da divisão na tabela: a própria divisão ("E-1") ou, quando a norma
  // só traz a linha do grupo inteiro ("D"), o grupo.
  const chaveDe = d => (tiposEscada.tabela[d] ? d : d.split('-')[0])
  const divs = [...new Set((divisoes || []).filter(Boolean))].filter(d => tiposEscada.tabela[chaveDe(d)])
  if (divs.length === 0) return { status: 'sem_divisao', faixa: tiposEscada.faixas_altura[idx] }

  // "EP+"/"PF+": o tipo indicado e, além dele, consultar normas específicas.
  const porDivisao = divs.map(d => {
    const celula = tiposEscada.tabela[chaveDe(d)][idx]
    const comConsulta = celula?.length > 1 && celula.endsWith('+')
    return { divisao: d, tipo: comConsulta ? celula.slice(0, -1) : celula, consultar: comConsulta || celula === '+' }
  })
  const ranks = porDivisao.map(p => tiposEscada.tipos[p.tipo]?.rank).filter(r => r != null)
  const maxRank = ranks.length ? Math.max(...ranks) : null
  // Mais restritivo entre os que têm ranking; sem nenhum, mostra o símbolo
  // (+ = consultar NT, - = não se aplica) da primeira divisão.
  const exigido = maxRank != null
    ? porDivisao.find(p => tiposEscada.tipos[p.tipo]?.rank === maxRank).tipo
    : porDivisao[0].tipo
  const consultar = porDivisao.some(p => p.consultar)

  // Notas: as específicas das divisões presentes + as gerais.
  const chaves = [
    ...divs.flatMap(d => tiposEscada.notas_por_divisao?.[d] || tiposEscada.notas_por_divisao?.[chaveDe(d)] || []),
    ...(tiposEscada.notas_gerais || []),
  ]
  const notas = [...new Set(chaves)].map(k => ({ chave: k, texto: tiposEscada.notas[k] }))

  return { status: 'ok', faixa: tiposEscada.faixas_altura[idx], porDivisao, exigido, consultar, notas }
}
