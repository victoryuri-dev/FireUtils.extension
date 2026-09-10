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

/** Calcula a população de um ambiente */
export function calcPopAmb(amb, taxaPopulacional) {
  if (amb.popTipo === 'fixo')   return Math.max(0, parseInt(amb.assentos)  || 0)
  if (amb.popTipo === 'manual') return Math.max(0, parseInt(amb.popManual) || 0)
  const taxa = taxaPopulacional[amb.divisao]
  if (!taxa || taxa.A === null) return Math.max(0, parseInt(amb.popManual) || 0)
  return Math.ceil((parseFloat(amb.area) || 0) / taxa.A)
}

/** Calcula a população total de um pavimento */
export function calcPopPav(pav, taxaPopulacional) {
  return pav.ambientes.reduce((s, a) => s + calcPopAmb(a, taxaPopulacional), 0)
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

/** Cálculo de PT — recebe a população e a capacidade já resolvidas por
 * quem chama (um ambiente sozinho, na rede de saída; ou um pavimento
 * inteiro, no modelo antigo) */
export function calcPT(pop, capPT, larguras) {
  const n      = Math.ceil(pop / capPT)
  const lc     = +(n * larguras.LARG_UP).toFixed(2)
  const ptInfo = getLargMinPT(n, larguras.PT)
  return { n, lc, la: Math.max(lc, ptInfo.largura), lMin: ptInfo.largura, tipo: ptInfo.tipo }
}

// ── Rede de saída (Ambiente -> Acesso -> Acesso/Descarga ou Escada/Rampa) ────
//
// Substitui o modelo antigo de "um AD e um ER por pavimento inteiro" por uma
// árvore montada pelo usuário, sem limite de profundidade:
//
//   ambiente.acessoId : string|null
//     -- a qual nó de Acesso este ambiente alimenta (null = ainda não
//        posicionado na árvore).
//
//   acesso = { id, nome, alimentaEm: string|null }
//     -- `alimentaEm` aponta pro id de outro acesso (cascata: a população
//        deste nó soma na do próximo) ou é null quando este acesso É a
//        RAIZ da árvore daquele pavimento.
//     -- A "quantidade de saídas" do pavimento NÃO é um campo armazenado —
//        é sempre a contagem de raízes (ver contarSaidasPavimento), já que
//        a criação de saídas é dinâmica.
//
// O tipo de cálculo de um nó (ver tipoDoNo) depende só da posição na árvore
// e de `pavimento.pisoDescarga`:
//   - Nó raiz (alimentaEm=null) num piso de descarga        -> AD (Saída)
//   - Nó raiz (alimentaEm=null) num pavimento QUALQUER OUTRO -> ER (a raiz
//     ali é a escada/rampa que desce até o piso de descarga — cada
//     pavimento dimensiona a própria escada pela população que chega até
//     ela pela SUA árvore, não mais pelo "pavimento mais populoso da
//     estrutura" fixo).
//   - Qualquer nó que NÃO é raiz (alimenta outro acesso) -> sempre AD,
//     em qualquer pavimento (é sempre um "acesso" interno, corredor/porta
//     de passagem, nunca a escada em si).
//
// Portas (PT) não passam por essa árvore: são por ambiente, direto —
// ver calcNoAmbientePT.

/** Quantidade de saídas de um pavimento = quantidade de raízes da árvore
 * (acessos com alimentaEm null) — nunca um campo indicado manualmente. */
export function contarSaidasPavimento(acessos) {
  return (acessos || []).filter(ac => ac.alimentaEm === null).length
}

/** Decide o tipo de cálculo/rótulo de um nó da árvore — ver explicação
 * acima. `pisoDescarga` é o campo do pavimento (não do nó). */
export function tipoDoNo(acesso, pisoDescarga) {
  const isRaiz = acesso.alimentaEm === null
  if (isRaiz && !pisoDescarga) return { tipo: 'ER', label: 'ESCADA/RAMPA' }
  return { tipo: 'AD', label: 'ACESSO/DESCARGA' }
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
    .reduce((s, a) => s + calcPopAmb(a, taxaPopulacional), 0)
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

/** Largura mínima da porta de um nó de Acesso/Saída/Escada-Rampa —
 * reaproveita o mesmo N de UP já calculado pro AD/ER daquele box (ver
 * calcNoAcesso) em vez de recalcular população/capacidade: a mesma vazão
 * que passa pelo corredor/escada precisa caber na porta daquele ponto.
 * Só busca a largura mínima de porta pra esse N na tabela PT — mesma
 * lógica de calcPT, sem o passo de `Math.ceil(pop / capacidade)`. */
export function calcPortaNoAcesso(n, larguras) {
  const lc     = +(n * larguras.LARG_UP).toFixed(2)
  const ptInfo = getLargMinPT(n, larguras.PT)
  return { n, lc, la: Math.max(lc, ptInfo.largura), lMin: ptInfo.largura, tipo: ptInfo.tipo }
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
 * ainda cadastrado na árvore de Acessos e Descargas. `pav.pisoDescarga` é
 * um booleano explícito por pavimento — ver ProjetoContext.jsx. */
export function getDistanciaPavimento(pav, nSaidas, temChuveiros, temDeteccao, distanciasMaximas) {
  if (!pav.divisao) return null
  return getDistancia(pav.divisao, pav.pisoDescarga, nSaidas, temChuveiros, temDeteccao, distanciasMaximas)
}

/** Retorna as opções de taxa disponíveis para a divisão */
export function taxaOpcoes(divisao, taxaPopulacional) {
  const taxa = taxaPopulacional[divisao]
  if (!taxa) return []
  const opts = []
  if (taxa.A !== null) opts.push({ value:'area',   label: taxa.obs })
  if (taxa.notas?.includes('N')) opts.push({ value:'fixo', label:'Assentos fixos' })
  if (taxa.A === null)  opts.push({ value:'manual', label: taxa.obs })
  return opts
}

/** Tipo de população padrão para uma divisão */
export function popTipoPadrao(divisao, taxaPopulacional) {
  return taxaOpcoes(divisao, taxaPopulacional)[0]?.value || 'manual'
}
