/**
 * seReducer.js — Ações da árvore de Acessos e Descargas (Saída de
 * Emergência), portadas de ProjetoContext.jsx (ETOS.FireUtils/src/context/
 * ProjetoContext.jsx) pro contexto da dockpane: aqui não existe um reducer
 * vivo com useReducer — cada ação recebe o `dados` (coluna jsonb da linha
 * `projetos`) inteiro e devolve uma cópia nova com `pavimentos` já
 * atualizado; quem chama (components/dashboard/AcessosDescargasView.jsx)
 * é responsável por persistir o resultado via lib/projectData.js
 * (salvarDadosProjeto, compare-and-swap por versão).
 *
 * Mesma árvore do site: Ambiente -> Acesso -> Acesso/Saída ou Escada-Rampa
 * (ver data/se_calc.js pro motor de cálculo). Um "Acesso" com
 * alimentaEm=null é uma Saída/Escada-Rampa (raiz da árvore daquele
 * pavimento) — não existe um tipo de nó separado, só a posição na árvore
 * muda (ver tipoDoNo em se_calc.js).
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

function atualizarPavimento(dados, pavimentoId, atualizar) {
  return {
    ...dados,
    pavimentos: (dados.pavimentos || []).map((p) => (p.id === pavimentoId ? atualizar(p) : p)),
  };
}

/**
 * Aplica uma ação da árvore de Saída de Emergência em `dados` (a coluna
 * jsonb inteira do projeto) e devolve uma cópia nova — nunca muta o
 * objeto recebido. `action.type` segue os mesmos nomes/formatos do
 * reducer do site, restrito às ações que esta tela dispara.
 */
export function aplicarAcaoSaida(dados, action) {
  switch (action.type) {
    case "CRIAR_SAIDA":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: [...(p.acessos || []), { id: action.id, nome: action.nome, alimentaEm: null }],
      }));

    case "CRIAR_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: [...(p.acessos || []), { id: action.id, nome: action.nome, alimentaEm: action.alimentaEm }],
      }));

    case "RENOMEAR_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) => (ac.id === action.acessoId ? { ...ac, nome: action.nome } : ac)),
      }));

    // Remove um nó sem apagar em cascata: o que alimentava ele (ambientes
    // e/ou outros acessos) fica órfão (acessoId/alimentaEm voltam a null)
    // em vez de sumir.
    case "REMOVER_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || [])
          .filter((ac) => ac.id !== action.acessoId)
          .map((ac) => (ac.alimentaEm === action.acessoId ? { ...ac, alimentaEm: null } : ac)),
        ambientes: (p.ambientes || []).map((a) => (a.acessoId === action.acessoId ? { ...a, acessoId: null } : a)),
      }));

    // Move um Acesso (e, por consequência do cálculo recursivo em
    // se_calc.js, todo o conjunto de ambientes/acessos que já
    // alimentavam ele) pra alimentar outro nó — ou pra null, virando uma
    // saída nova. Validar ciclo é responsabilidade de quem despacha.
    case "MOVER_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        acessos: (p.acessos || []).map((ac) =>
          ac.id === action.acessoId ? { ...ac, alimentaEm: action.novoAlimentaEm } : ac
        ),
      }));

    case "MOVER_AMBIENTE_ACESSO":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) =>
          a.id === action.ambienteId ? { ...a, acessoId: action.novoAcessoId } : a
        ),
      }));

    case "ADD_AMBIENTE_SE":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: [...(p.ambientes || []), { id: action.id, ...action.ambiente }],
      }));

    case "UPDATE_AMBIENTE_SE":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).map((a) =>
          a.id === action.ambienteId ? { ...a, ...action.changes } : a
        ),
      }));

    case "REMOVE_AMBIENTE_SE":
      return atualizarPavimento(dados, action.pavimentoId, (p) => ({
        ...p,
        ambientes: (p.ambientes || []).filter((a) => a.id !== action.ambienteId),
      }));

    // Só pode haver um piso de descarga por estrutura — marcar um como
    // piso de descarga (valor:true) desmarca automaticamente qualquer
    // outro pavimento da MESMA estrutura.
    case "SET_PISO_DESCARGA":
      return {
        ...dados,
        pavimentos: (dados.pavimentos || []).map((p) => {
          if (p.id === action.pavimentoId) return { ...p, pisoDescarga: action.valor };
          if (action.valor && p.estruturaId === action.estruturaId) return { ...p, pisoDescarga: false };
          return p;
        }),
      };

    default:
      return dados;
  }
}
