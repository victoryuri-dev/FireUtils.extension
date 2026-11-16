import { dimsPadrao } from "../data/se_calc";
import { ligarEscadasPadrao, migrarFluxoPavimento, posicionarFaixas, sincronizarAmbientes } from "../data/se_fluxo";

/**
 * seReducer.js — Ações do fluxograma de saídas (Grupo de ambientes -> Acesso
 * -> Saída/Escada-Rampa), portadas de ProjetoContext.jsx (ETOS.FireUtils/src/
 * context/ProjetoContext.jsx) pro contexto da dockpane: aqui não existe um
 * reducer vivo com useReducer — cada ação recebe o `dados` (coluna jsonb da
 * linha `projetos`) inteiro e devolve uma cópia nova com `pavimentos` já
 * atualizado; quem chama (components/dashboard/FluxogramaSaidas.jsx,
 * SaidaEmergenciaPage.jsx) é responsável por persistir o resultado via
 * lib/projectData.js (salvarComRetry, compare-and-swap por versão com
 * retry em falso conflito).
 *
 * Mesmo modelo de dados do site (ver data/se_fluxo.js e data/se_calc.js, que
 * são cópias dos do site): grupo de ambientes (`grupos`) liga ambientes a um
 * nó; nó = acesso/saída/escada (`acessos`, com `tipo`); `fluxoPos` guarda a
 * posição dos nós relativa à origem da faixa do pavimento (`faixaPos`).
 * `ambiente.acessoId` é derivado do grupo — o reducer mantém sincronizado.
 * Todo pavimento tem a saída/escada padrão (`fixo`), que não se exclui.
 *
 * Projetos que ainda não passaram pelo fluxograma (nem no site, nem aqui)
 * chegam sem `grupos`/`faixaPos`/`tipo`: garantirFluxoMigrado traz tudo pro
 * formato novo, de forma determinística (mesmos ids, mesmas posições) — por
 * isso pode rodar em toda leitura e em toda ação sem divergir do site.
 */

let _seq = 0;
function _id(prefixo) {
  _seq += 1;
  return `${prefixo}-${Date.now().toString(36)}-${_seq}-${Math.random().toString(36).slice(2, 5)}`;
}

export function idAcesso() {
  return _id("acs");
}

export function idAmbienteSE() {
  return _id("amb");
}

export function idGrupo() {
  return _id("grp");
}

// Igualdade profunda sem depender da ordem das chaves (o jsonb do Postgres
// reordena as chaves dos objetos que devolve).
function iguais(a, b) {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  // Chave com valor undefined equivale a chave ausente (o JSON do Supabase a descarta).
  const definidas = (o) => Object.keys(o).filter((k) => o[k] !== undefined);
  const chavesA = definidas(a);
  const chavesB = definidas(b);
  return chavesA.length === chavesB.length && chavesA.every((k) => chavesB.includes(k) && iguais(a[k], b[k]));
}

/** Pavimentos já no formato do fluxograma. Devolve a MESMA referência de
 * `dados` quando nada precisa mudar (barato de repetir a cada leitura). */
export function garantirFluxoMigrado(dados) {
  const antigos = dados?.pavimentos;
  if (!antigos?.length) return dados;
  const migrados = posicionarFaixas(
    ligarEscadasPadrao(antigos.map((p) => migrarFluxoPavimento({ ambientes: [], acessos: [], pisoDescarga: p.tipo === "terreo", ...p })))
  );
  return iguais(migrados, antigos) ? dados : { ...dados, pavimentos: migrados };
}

function atualizarPavimento(dados, pavimentoId, atualizar) {
  return {
    ...dados,
    pavimentos: (dados.pavimentos || []).map((p) => (p.id === pavimentoId ? atualizar(p) : p)),
  };
}

// Aplica `fn` ao pavimento e re-sincroniza `ambiente.acessoId` com o grupo de
// cada ambiente — toda mudança no fluxo (nós, ligações, ambientes) passa por
// aqui, então o motor de cálculo sempre lê um `acessoId` consistente.
function atualizarPavSE(dados, pavimentoId, fn) {
  return atualizarPavimento(dados, pavimentoId, (p) => {
    const novo = fn(p);
    return { ...novo, ambientes: sincronizarAmbientes(novo.ambientes, novo.grupos, novo.acessos) };
  });
}

// Cópia do objeto sem uma chave (posição de um nó removido do fluxo).
function omitirChave(obj, chave) {
  const copia = { ...(obj || {}) };
  delete copia[chave];
  return copia;
}

// A saída/escada padrão (`fixo`) acompanha o piso de descarga: piso de
// descarga -> Saída; qualquer outro -> Escada/Rampa. Ao mudar, volta pro
// dimensionamento padrão do novo tipo e troca o prefixo do nome, se ainda for
// o nome padrão ("Saída 01" <-> "Escada/Rampa 01").
function acompanharPisoDescarga(p, eraPisoDescarga) {
  if (!!p.pisoDescarga === !!eraPisoDescarga) return p;
  const tipo = p.pisoDescarga ? "saida" : "escada";
  return {
    ...p,
    acessos: (p.acessos || []).map((ac) =>
      ac.fixo
        ? {
            ...ac,
            tipo,
            dims: dimsPadrao(tipo),
            nome: ac.nome.replace(/^(Saída|Escada\/Rampa)( \d+)$/, `${tipo === "saida" ? "Saída" : "Escada/Rampa"}$2`),
          }
        : ac
    ),
  };
}

/**
 * Aplica uma ação do fluxograma de Saída de Emergência em `dados` (a coluna
 * jsonb inteira do projeto) e devolve uma cópia nova — nunca muta o objeto
 * recebido. `action.type` segue os mesmos nomes/formatos do reducer do site,
 * restrito às ações que esta tela dispara; todo id necessário já vem
 * resolvido no ponto de disparo (idAcesso/idGrupo/idAmbienteSE).
 */
export function aplicarAcaoSaida(dadosRecebidos, action) {
  const dados = garantirFluxoMigrado(dadosRecebidos);
  switch (action.type) {
    // Substitui os ambientes de um ou mais pavimentos de uma vez — usado pela
    // importação "Buscar do Revit" (ver SaidaEmergenciaPage.jsx), que já
    // resolve cada pavimento do payload contra o cadastro real antes de
    // despachar esta ação.
    case "IMPORT_AMBIENTES_SE": {
      const porPavimento = new Map(action.atualizacoes.map((a) => [a.pavimentoId, a.ambientes]));
      return {
        ...dados,
        pavimentos: (dados.pavimentos || []).map((p) =>
          porPavimento.has(p.id) ? { ...p, ambientes: sincronizarAmbientes(porPavimento.get(p.id), p.grupos, p.acessos) } : p
        ),
      };
    }

    // `ambiente.grupoId` (grupo) opcional; `acessoId` nasce do grupo, nunca é
    // informado direto — ver sincronizarAmbientes. `pos`: já nasce solto na área.
    case "ADD_AMBIENTE_SE":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: [...(p.ambientes || []), { id: action.id, ...action.ambiente }],
        fluxoPos: action.pos ? { ...(p.fluxoPos || {}), [action.id]: action.pos } : p.fluxoPos,
      }));

    case "UPDATE_AMBIENTE_SE":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) => (a.id === action.ambienteId ? { ...a, ...action.changes } : a)),
      }));

    case "REMOVE_AMBIENTE_SE":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).filter((a) => a.id !== action.ambienteId),
        fluxoPos: omitirChave(p.fluxoPos, action.ambienteId),
      }));

    // ── Fluxograma (Grupo de ambientes -> Acesso -> Saída/Escada) ──
    // Nó = acesso (`tipo` 'acesso'|'saida'|'escada', escolhido por nó) ou
    // grupo de ambientes. Cada nó alimenta no máximo UM seguinte
    // (`alimentaEm` / `grupo.acessoId`); saída e escada são as raízes.
    case "CRIAR_NO_FLUXO":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: [...(p.acessos || []), { id: action.id, nome: action.nome, tipo: action.tipo, alimentaEm: null, dims: dimsPadrao(action.tipo) }],
        fluxoPos: { ...(p.fluxoPos || {}), [action.id]: action.pos },
      }));

    // Grupo novo; com `ambienteIds`, já nasce com esses ambientes dentro (e eles
    // deixam de ser nós soltos na área). `acessoId`: já nasce ligado.
    case "CRIAR_GRUPO_AMBIENTES": {
      const idsMovidos = new Set(action.ambienteIds || []);
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        grupos: [...(p.grupos || []), { id: action.id, nome: action.nome, acessoId: action.acessoId || null }],
        fluxoPos: {
          ...Object.fromEntries(Object.entries(p.fluxoPos || {}).filter(([id]) => !idsMovidos.has(id))),
          [action.id]: action.pos,
        },
        ambientes: (p.ambientes || []).map((a) => (idsMovidos.has(a.id) ? { ...a, grupoId: action.id } : a)),
      }));
    }

    // Liga/desliga um dimensionamento (AD/ER/PT) de um nó específico — um nó
    // pode precisar de mais de um ao mesmo tempo (ex.: o ponto de descarga que
    // é ao mesmo tempo corredor de saída e chegada da escada que desce até ali).
    case "SET_ACESSO_DIM":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) =>
          ac.id === action.acessoId ? { ...ac, dims: { ...(ac.dims || {}), [action.dim]: action.valor } } : ac
        ),
      }));

    case "RENOMEAR_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) => (ac.id === action.acessoId ? { ...ac, nome: action.nome } : ac)),
      }));

    case "RENOMEAR_GRUPO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        grupos: (p.grupos || []).map((g) => (g.id === action.grupoId ? { ...g, nome: action.nome } : g)),
      }));

    // Liga um acesso a outro nó (`novoAlimentaEm`) — por consequência do
    // cálculo recursivo em se_calc.js, leva junto tudo que já o alimentava. null
    // desliga. Validar ciclo é de quem despacha (ver tipoDeLigacao).
    case "MOVER_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) => (ac.id === action.acessoId ? { ...ac, alimentaEm: action.novoAlimentaEm } : ac)),
      }));

    // Liga uma saída/escada a qualquer acesso, saída ou escada, de qualquer
    // pavimento (ou null pra desligar). Não altera o cálculo — o dimensionamento
    // da escada é único por estrutura (ver calcErEstrutura); a ligação registra o
    // desenho do fluxo. Validar (destino, ciclo) é de quem despacha — ver
    // tipoDeLigacao. (O nome da ação é mantido: faz parte do protocolo em tempo real.)
    case "LIGAR_ENTRE_PAVIMENTOS":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) =>
          ac.id === action.acessoId ? { ...ac, ligadoA: action.destinoId, ligacaoPadrao: false } : ac
        ),
      }));

    // Liga um grupo de ambientes a um nó (ou null pra desligar) — os ambientes
    // dentro dele passam a alimentar esse nó.
    case "LIGAR_GRUPO":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        grupos: (p.grupos || []).map((g) => (g.id === action.grupoId ? { ...g, acessoId: action.acessoId } : g)),
      }));

    // Move ambientes pra dentro de um grupo — inclusive entre grupos diferentes
    // — ou de volta pra lista lateral (`grupoId` null: sem grupo, sem posição na
    // área e sem ligação). Em qualquer caso o ambiente deixa de ser um nó solto.
    case "MOVER_AMBIENTES_GRUPO": {
      const idsMovidos = new Set(action.ambienteIds);
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) => (idsMovidos.has(a.id) ? { ...a, grupoId: action.grupoId, acessoId: null } : a)),
        fluxoPos: Object.fromEntries(Object.entries(p.fluxoPos || {}).filter(([id]) => !idsMovidos.has(id))),
      }));
    }

    // Coloca ambientes soltos na área de trabalho (sem grupo), cada um na sua
    // posição. Quem vinha de um grupo perde a ligação dele; quem já estava
    // solto só muda de lugar e mantém a ligação direta.
    case "SOLTAR_AMBIENTES_NA_AREA":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) =>
          action.posicoes[a.id] ? { ...a, grupoId: null, acessoId: a.grupoId ? null : a.acessoId } : a
        ),
        fluxoPos: { ...(p.fluxoPos || {}), ...action.posicoes },
      }));

    // Liga um ambiente solto na área direto a um nó (ou null pra desligar).
    case "LIGAR_AMBIENTE":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) =>
          a.id === action.ambienteId && !a.grupoId ? { ...a, acessoId: action.acessoId } : a
        ),
      }));

    // Remove um acesso/saída/escada sem apagar em cascata: o que alimentava ele
    // (grupos e/ou outros acessos) fica sem ligação em vez de sumir. A
    // saída/escada padrão (`fixo`) de cada pavimento não pode ser excluída.
    case "REMOVER_ACESSO": {
      const alvo = (dados.pavimentos || []).find((p) => p.id === action.pavimentoId)?.acessos?.find((ac) => ac.id === action.acessoId);
      if (alvo?.fixo) return dados;
      const aposRemover = atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        fluxoPos: omitirChave(p.fluxoPos, action.acessoId),
        acessos: (p.acessos || [])
          .filter((ac) => ac.id !== action.acessoId)
          .map((ac) => (ac.alimentaEm === action.acessoId ? { ...ac, alimentaEm: null } : ac)),
        grupos: (p.grupos || []).map((g) => (g.acessoId === action.acessoId ? { ...g, acessoId: null } : g)),
      }));
      // Saídas/escadas de outros pavimentos que estavam ligadas a este nó também desligam.
      return {
        ...aposRemover,
        pavimentos: aposRemover.pavimentos.map((p) =>
          (p.acessos || []).some((ac) => ac.ligadoA === action.acessoId)
            ? { ...p, acessos: p.acessos.map((ac) => (ac.ligadoA === action.acessoId ? { ...ac, ligadoA: null } : ac)) }
            : p
        ),
      };
    }

    // Remove um grupo; os ambientes dentro dele voltam pra lista (sem grupo),
    // nunca são apagados junto.
    case "REMOVER_GRUPO":
      return atualizarPavSE(dados, action.pavimentoId, (p) => ({
        ...p,
        fluxoPos: omitirChave(p.fluxoPos, action.grupoId),
        grupos: (p.grupos || []).filter((g) => g.id !== action.grupoId),
        ambientes: (p.ambientes || []).map((a) => (a.grupoId === action.grupoId ? { ...a, grupoId: null, acessoId: null } : a)),
      }));

    // Origem da faixa do pavimento na área de trabalho (arrastar a faixa) — os
    // nós dentro dela (`fluxoPos`) são relativos a esse ponto.
    case "SET_FAIXA_POS":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({ ...p, faixaPos: action.pos }));

    // Posição dos nós na área de trabalho — despachada só ao soltar o arrasto
    // (não a cada movimento), pra não gravar a cada pixel.
    case "SET_POSICOES_FLUXO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({ ...p, fluxoPos: { ...(p.fluxoPos || {}), ...action.posicoes } }));

    // Uma estrutura pode ter mais de um piso de descarga (ex.: dois pavimentos
    // com saída direta pra rua): marcar/desmarcar só afeta o próprio
    // pavimento. A saída/escada padrão dele acompanha.
    case "SET_PISO_DESCARGA":
      return {
        ...dados,
        pavimentos: ligarEscadasPadrao(
          (dados.pavimentos || []).map((p) => (p.id === action.pavimentoId ? acompanharPisoDescarga({ ...p, pisoDescarga: action.valor }, p.pisoDescarga) : p))
        ),
      };

    default:
      return dados;
  }
}
