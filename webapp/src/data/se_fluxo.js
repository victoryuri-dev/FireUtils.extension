// se_fluxo.js — dados do fluxograma de saídas (Ambientes -> Acessos ->
// Saída/Escada) de um pavimento: grupo de ambientes (`grupos`), posição dos
// nós na área de trabalho (`fluxoPos`) e migração dos pavimentos salvos
// antes do fluxograma existir. Funções puras, sem React — o cálculo em si
// continua em se_calc.js.
//
//   pavimento.grupos   = [{ id, nome, acessoId: string|null }]
//     -- grupo de ambientes: agrupa ambientes e liga o conjunto a UM nó
//        (acesso/saída/escada). `acessoId` null = grupo ainda sem ligação.
//   ambiente.grupoId   : string|null   -- grupo em que o ambiente está.
//   ambiente.acessoId  : string|null   -- em grupo, sempre igual ao `acessoId`
//        do grupo; ambiente solto na área (sem grupo, com posição em
//        `fluxoPos`) tem a própria ligação direta. O reducer mantém tudo
//        sincronizado (ver sincronizarAmbientes) — é o que o motor de
//        cálculo e o memorial leem.
//   pavimento.faixaPos = { x, y }
//     -- origem da faixa do pavimento na área de trabalho (ver posicionarFaixas).
//   pavimento.fluxoPos = { [idDoNo]: { x, y } }   (relativo a `faixaPos`)
//     -- posição de cada grupo, de cada acesso/saída/escada e de cada ambiente
//        solto (sem grupo) na área de trabalho. Ambiente sem grupo e sem
//        posição fica só na lista lateral.

import { dimsPadrao, ehRaiz, tipoNo } from './se_calc'

export const COL_W = 400
export const ROW_H = 220
// Canto onde começam os nós dentro da faixa do pavimento (a faixa tem um
// cabeçalho no topo) e versão do formato de `fluxoPos` (2 = relativo à faixa).
export const ORIGEM_X = 60
export const ORIGEM_Y = 120
export const FLUXO_VER = 2
// Faixa de pavimento (retângulo atrás dos nós): folga em volta dos nós, altura
// do cabeçalho e espaço entre faixas. A faixa se ajusta ao que tem dentro; o
// tamanho estimado só serve pra empilhar as faixas na primeira vez.
export const FAIXA_PAD = 60
export const FAIXA_CAB = 70
export const FAIXA_GAP = 80

/** Caminho de um nó até a saída: o próprio nó e cada nó seguinte (grupo ->
 * acesso -> … -> saída/escada), com os ids das setas entre eles (`e-<origem>`).
 * Pára no fim da cadeia (nó sem ligação ou saída/escada). */
export function caminhoAteSaida(id, { acessos, grupos, ambientes }) {
  const proximo = no => {
    const alvo = grupos.find(g => g.id === no)?.acessoId
      ?? acessos.find(a => a.id === no)?.alimentaEm
      ?? acessos.find(a => a.id === no)?.ligadoA
      ?? ambientes.find(a => a.id === no && !a.grupoId)?.acessoId
    return alvo && acessos.some(a => a.id === alvo) ? alvo : null
  }
  const nos = [id]
  const setas = []
  const vistos = new Set(nos)
  for (let atual = id, prox = proximo(atual); prox && !vistos.has(prox); atual = prox, prox = proximo(atual)) {
    nos.push(prox)
    setas.push(`e-${atual}`)
    vistos.add(prox)
  }
  return { nos, setas }
}

/** A ligação `origemId` -> `destinoId` é permitida? Devolve 'local' (mesmo
 * pavimento: grupo/ambiente solto/acesso -> acesso, saída ou escada, sem
 * ciclo), 'entre-pavimentos' (pavimentos diferentes: só saída/escada ->
 * saída/escada, sem ciclo) ou null. `pavDe`: Map id do nó -> id do pavimento;
 * `ambientesNaArea`: ids dos ambientes soltos na área (podem ser origem). */
export function tipoDeLigacao(origemId, destinoId, { acessos, grupos, pavDe, ambientesNaArea }) {
  if (origemId === destinoId) return null
  const destino = acessos.find(a => a.id === destinoId)
  if (!destino) return null
  const origemAcesso = acessos.find(a => a.id === origemId)
  if (pavDe.get(origemId) === pavDe.get(destinoId)) {
    if (grupos.some(g => g.id === origemId) || ambientesNaArea?.has(origemId)) return 'local'
    return origemAcesso?.tipo === 'acesso' && !criaCicloNoFluxo(acessos, origemId, destinoId) ? 'local' : null
  }
  const ehExtremo = a => !!a && a.tipo !== 'acesso'
  if (ehExtremo(origemAcesso) && ehExtremo(destino) && !criaCicloEntrePavimentos(acessos, origemId, destinoId)) return 'entre-pavimentos'
  return null
}

/** Ligar a saída/escada `origemId` a `destinoId` (outro pavimento) fecharia um
 * ciclo na cadeia de ligações entre pavimentos (`acesso.ligadoA`)? */
export function criaCicloEntrePavimentos(acessos, origemId, destinoId) {
  const porId = new Map(acessos.map(a => [a.id, a]))
  const visitados = new Set()
  for (let id = destinoId; id && !visitados.has(id); id = porId.get(id)?.ligadoA) {
    if (id === origemId) return true
    visitados.add(id)
  }
  return false
}

/** Por quais lados uma seta deve sair da origem e chegar ao destino: o par
 * (lado da origem, lado do destino) cujos pontos médios estão mais perto
 * um do outro. Cada nó é { x, y, w, h } (canto superior esquerdo + tamanho). */
export function ladosMaisProximos(origem, destino) {
  const pontos = n => ({
    top: [n.x + n.w / 2, n.y], right: [n.x + n.w, n.y + n.h / 2],
    bottom: [n.x + n.w / 2, n.y + n.h], left: [n.x, n.y + n.h / 2],
  })
  const po = pontos(origem), pd = pontos(destino)
  let melhor = { de: 'right', para: 'left', dist: Infinity }
  for (const de of Object.keys(po)) {
    for (const para of Object.keys(pd)) {
      const dist = Math.hypot(po[de][0] - pd[para][0], po[de][1] - pd[para][1])
      if (dist < melhor.dist) melhor = { de, para, dist }
    }
  }
  return { de: melhor.de, para: melhor.para }
}

/** Nome padrão de um grupo novo: "Grupo 1", "Grupo 2"… — o menor número
 * ainda não usado por outro grupo do pavimento. */
export function proximoNomeGrupo(grupos) {
  const usados = new Set((grupos || []).map(g => g.nome))
  let n = 1
  while (usados.has(`Grupo ${n}`)) n++
  return `Grupo ${n}`
}

/** Mantém `ambiente.acessoId` igual ao do grupo em que ele está — ambiente
 * fora de qualquer grupo (ou em grupo sem ligação) fica com acessoId null.
 * Grupo que aponta pra um acesso que não existe mais também é desligado. */
export function sincronizarAmbientes(ambientes, grupos, acessos) {
  const idsAcesso = new Set((acessos || []).map(a => a.id))
  const acessoDoGrupo = new Map((grupos || []).map(g => [g.id, idsAcesso.has(g.acessoId) ? g.acessoId : null]))
  return (ambientes || []).map(a => {
    const grupoId = acessoDoGrupo.has(a.grupoId) ? a.grupoId : null
    // Em grupo: herda a ligação do grupo. Solto na área (sem grupo): mantém a
    // própria ligação direta, se o nó ainda existir — mas um ambiente que
    // acabou de perder o grupo (grupo removido) não leva a ligação dele.
    const acessoId = grupoId
      ? acessoDoGrupo.get(grupoId)
      : (!a.grupoId && idsAcesso.has(a.acessoId) ? a.acessoId : null)
    return a.grupoId === grupoId && a.acessoId === acessoId ? a : { ...a, grupoId, acessoId }
  })
}

/** Ligar `origemId` -> `destinoId` (origem passa a alimentar o destino)
 * fecharia um ciclo? Verdadeiro quando o destino já é a própria origem ou
 * (direta/indiretamente) é alimentado por ela. */
export function criaCicloNoFluxo(acessos, origemId, destinoId) {
  const porId = new Map(acessos.map(a => [a.id, a]))
  const visitados = new Set()
  for (let id = destinoId; id && !visitados.has(id); id = porId.get(id)?.alimentaEm) {
    if (id === origemId) return true
    visitados.add(id)
  }
  return false
}

/** Posições iniciais (em colunas, da esquerda pra direita: grupos ->
 * acessos -> saídas/escadas) pros nós que ainda não têm posição. */
export function layoutFluxo(acessos, grupos, existentes = {}) {
  const porId = new Map(acessos.map(a => [a.id, a]))
  const nivelAcesso = (ac, visitados = new Set()) => {
    if (ehRaiz(ac)) return 0
    const prox = porId.get(ac.alimentaEm)
    if (!prox || visitados.has(ac.id)) return 1
    return nivelAcesso(prox, new Set(visitados).add(ac.id)) + 1
  }
  const nos = [
    ...acessos.map(ac => ({ id: ac.id, nivel: nivelAcesso(ac) })),
    ...grupos.map(g => ({ id: g.id, nivel: porId.has(g.acessoId) ? nivelAcesso(porId.get(g.acessoId)) + 1 : 2 })),
  ]
  // Pelo menos 2 colunas: a saída/escada de um pavimento recém-criado fica à
  // direita, deixando espaço à esquerda pra acessos e grupos.
  const maxNivel = Math.max(2, ...nos.map(n => n.nivel))
  const linhaPorNivel = {}
  const posicoes = {}
  nos.forEach(({ id, nivel }) => {
    const linha = linhaPorNivel[nivel] = (linhaPorNivel[nivel] ?? -1) + 1
    if (!existentes[id]) posicoes[id] = { x: ORIGEM_X + (maxNivel - nivel) * COL_W, y: ORIGEM_Y + linha * ROW_H }
  })
  return posicoes
}

/** A saída (piso de descarga) ou escada/rampa PADRÃO de um pavimento: `fixo`,
 * nasce com o pavimento e não pode ser excluída. `id` único por pavimento. */
export function raizPadrao(pisoDescarga, id) {
  const tipo = pisoDescarga ? 'saida' : 'escada'
  return { id, nome: pisoDescarga ? 'Saída 01' : 'Escada/Rampa 01', tipo, alimentaEm: null, fixo: true, dims: dimsPadrao(tipo) }
}

/** Fluxo de um pavimento recém-criado: só a saída (piso de descarga) ou a
 * escada/rampa padrão, que não pode ser excluída. `novoId` gera o id do nó. */
export function fluxoPadrao(pisoDescarga, novoId) {
  const acessos = [raizPadrao(pisoDescarga, novoId())]
  return { acessos, grupos: [], fluxoPos: layoutFluxo(acessos, []), fluxoVer: FLUXO_VER }
}

/** Liga as escadas/rampas padrão à saída do piso de descarga: cada pavimento
 * que NÃO é piso de descarga liga a sua escada padrão à saída/escada padrão do
 * pavimento vizinho, na direção do piso de descarga mais próximo (empate: o de
 * baixo) — em cadeia, até chegar à saída. `pavimentos` = lista do estado (a
 * ordem dentro de cada estrutura é a do prédio: subsolos, térreo, demais).
 * Só mexe em ligação que ainda não foi decidida (`ligadoA` ausente) ou que foi
 * feita por aqui (`ligacaoPadrao`) — o que o usuário ligou ou desligou à mão
 * fica como está. A raiz de um pavimento que virou piso de descarga larga a
 * ligação automática. Devolve a mesma lista (mesmas referências) se nada mudar. */
export function ligarEscadasPadrao(pavimentos) {
  const porEstrutura = new Map()
  pavimentos.forEach(p => porEstrutura.set(p.estruturaId, [...(porEstrutura.get(p.estruturaId) || []), p]))
  const novosAcessos = new Map() // id do pavimento -> acessos novos
  porEstrutura.forEach(lista => {
    const pisos = lista.map((p, i) => (p.pisoDescarga ? i : -1)).filter(i => i >= 0)
    lista.forEach((p, i) => {
      const raiz = (p.acessos || []).find(ac => ac.fixo)
      if (!raiz || !(raiz.ligadoA === undefined || raiz.ligacaoPadrao)) return
      let alvoId
      if (!p.pisoDescarga && pisos.length) {
        const j = pisos.reduce((melhor, k) => (Math.abs(k - i) < Math.abs(melhor - i) || (Math.abs(k - i) === Math.abs(melhor - i) && k < melhor) ? k : melhor), pisos[0])
        alvoId = (lista[i + Math.sign(j - i)]?.acessos || []).find(ac => ac.fixo)?.id
      }
      const atual = raiz.ligacaoPadrao ? raiz.ligadoA : undefined
      if (atual === alvoId) return
      const nova = { ...raiz }
      if (alvoId) { nova.ligadoA = alvoId; nova.ligacaoPadrao = true } else { delete nova.ligadoA; delete nova.ligacaoPadrao }
      novosAcessos.set(p.id, p.acessos.map(ac => (ac === raiz ? nova : ac)))
    })
  })
  return novosAcessos.size ? pavimentos.map(p => (novosAcessos.has(p.id) ? { ...p, acessos: novosAcessos.get(p.id) } : p)) : pavimentos
}

/** Dá a cada pavimento sem `faixaPos` a origem da sua faixa na área de trabalho
 * (`fluxoPos` dos nós é relativo a essa origem), empilhando as faixas de cima
 * pra baixo — pavimento mais alto no topo — sem sobrepor, com base no tamanho
 * estimado do que há dentro. Faixa já posicionada (movida pelo usuário) não é
 * tocada. Devolve a mesma lista se nada mudar. */
export function posicionarFaixas(pavimentos) {
  const porEstrutura = new Map()
  pavimentos.forEach(p => porEstrutura.set(p.estruturaId, [...(porEstrutura.get(p.estruturaId) || []), p]))
  const novas = new Map()
  porEstrutura.forEach(lista => {
    let cursor = 0
    ;[...lista].reverse().forEach(p => {
      const pos = Object.values(p.fluxoPos || {})
      const minX = pos.length ? Math.min(...pos.map(q => q.x)) : ORIGEM_X
      const minY = pos.length ? Math.min(...pos.map(q => q.y)) : ORIGEM_Y
      // Fundo do nó mais baixo (altura estimada: grupo cresce com os ambientes).
      const baixo = Object.entries(p.fluxoPos || {}).reduce((mx, [id, q]) => {
        const grupo = (p.grupos || []).find(g => g.id === id)
        const h = grupo ? 170 + 70 * (p.ambientes || []).filter(a => a.grupoId === id).length : (p.ambientes || []).some(a => a.id === id) ? 90 : 230
        return Math.max(mx, q.y + h)
      }, ORIGEM_Y + 230)
      let origem = p.faixaPos
      if (!origem) {
        origem = { x: Math.round(FAIXA_PAD - minX), y: Math.round(cursor + FAIXA_PAD + FAIXA_CAB - minY) }
        novas.set(p.id, origem)
      }
      cursor = Math.max(cursor, origem.y + baixo + FAIXA_PAD + FAIXA_GAP)
    })
  })
  return novas.size ? pavimentos.map(p => (novas.has(p.id) ? { ...p, faixaPos: novas.get(p.id) } : p)) : pavimentos
}

/** Migra um pavimento salvo antes do fluxograma (ou ainda parcial): dá
 * `tipo` explícito a cada nó (congela o que antes dependia de
 * `pisoDescarga`), cria um grupo por acesso que já tinha ambientes ligados
 * direto, sincroniza `acessoId` e completa as posições. Idempotente. */
export function migrarFluxoPavimento(p) {
  let acessos = (p.acessos || []).map(ac => ac.tipo ? ac : { ...ac, tipo: tipoNo(ac, p.pisoDescarga) })
  // Todo pavimento tem a saída/escada padrão (`fixo`): promove a primeira raiz
  // que já existia ou, se não há nenhuma, cria uma.
  if (!acessos.some(ac => ac.fixo)) {
    const i = acessos.findIndex(ac => ehRaiz(ac))
    acessos = i >= 0
      ? acessos.map((ac, j) => (j === i ? { ...ac, fixo: true } : ac))
      : [...acessos, raizPadrao(!!p.pisoDescarga, `acs-fixo-${p.id}`)]
  }
  const grupos = [...(p.grupos || [])]
  // Grupo sem nome (criado quando o grupo ainda não tinha nome) recebe o padrão.
  grupos.forEach((g, i) => { if (!g.nome) grupos[i] = { ...g, nome: proximoNomeGrupo(grupos) } })
  const idsGrupo = new Set(grupos.map(g => g.id))
  const idsAcesso = new Set(acessos.map(ac => ac.id))

  const ambientes = (p.ambientes || []).map(a => {
    if (a.grupoId && idsGrupo.has(a.grupoId)) return a
    // Ambiente solto na área (tem posição própria) com ligação direta já está
    // no formato novo — só o formato antigo (acessoId sem grupo nem posição) vira grupo.
    if (p.fluxoPos?.[a.id]) return { ...a, grupoId: null }
    if (a.acessoId && idsAcesso.has(a.acessoId)) {
      const grupoId = `grp-mig-${a.acessoId}`
      if (!idsGrupo.has(grupoId)) {
        idsGrupo.add(grupoId)
        grupos.push({ id: grupoId, nome: proximoNomeGrupo(grupos), acessoId: a.acessoId })
      }
      return { ...a, grupoId }
    }
    return { ...a, grupoId: null }
  })

  // Posições salvas antes da faixa por pavimento (versão < 2) eram livres na
  // área de trabalho: deslocadas pra caber na faixa, a partir do canto de origem.
  let posSalvas = p.fluxoPos || {}
  const salvas = Object.values(posSalvas)
  if (p.fluxoVer !== FLUXO_VER && salvas.length) {
    const dx = ORIGEM_X - Math.min(...salvas.map(q => q.x))
    const dy = ORIGEM_Y - Math.min(...salvas.map(q => q.y))
    posSalvas = Object.fromEntries(Object.entries(posSalvas).map(([id, q]) => [id, { x: q.x + dx, y: q.y + dy }]))
  }
  const fluxoPos = { ...posSalvas, ...layoutFluxo(acessos, grupos, posSalvas) }
  return { ...p, acessos, grupos, ambientes: sincronizarAmbientes(ambientes, grupos, acessos), fluxoPos, fluxoVer: FLUXO_VER }
}
