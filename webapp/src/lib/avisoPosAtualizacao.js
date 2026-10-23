// Depois de aplicar um pacote a dockpane recarrega a página (para pegar a
// interface e a versão novas). O recarregamento apaga o estado do React, então
// o aviso do que fazer em seguida ("reinicie o Revit"...) fica guardado em
// sessionStorage: sobrevive ao recarregamento da página, mas some quando o
// WebView fecha (ou seja, quando o Revit reinicia, que é justamente o que o
// aviso pede).

const CHAVE = "fireutils.posAtualizacao";

// Tempo para o toast e o aviso aparecerem antes de a página recarregar.
export const ATRASO_RECARGA_MS = 1500;

export function guardarAvisoPosAtualizacao(dados) {
  try {
    window.sessionStorage.setItem(CHAVE, JSON.stringify(dados));
  } catch {
    // sem sessionStorage: o aviso só vale até o recarregamento
  }
}

/** { versao, reinicio, recarga } guardado, ou null. */
export function lerAvisoPosAtualizacao() {
  try {
    const bruto = window.sessionStorage.getItem(CHAVE);
    return bruto ? JSON.parse(bruto) : null;
  } catch {
    return null;
  }
}

export function limparAvisoPosAtualizacao() {
  try {
    window.sessionStorage.removeItem(CHAVE);
  } catch {
    // nada a fazer
  }
}
