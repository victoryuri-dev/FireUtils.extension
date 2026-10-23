/**
 * Estado da atualização do plugin feita pela dockpane (plugin_atualizacao.py).
 * `fase`: null (parado) | "preparando" | "baixando" | "verificando" |
 *         "aplicando" | "aplicada" (pacote instalado; falta reiniciar o Revit) |
 *         "agendada" (instala quando o Revit fechar) | "manual" (baixado e
 *         conferido; o usuário executa) | "erro".
 */

export const EM_ANDAMENTO = ["preparando", "baixando", "verificando", "aplicando"];

export function emAndamento(estado) {
  return EM_ANDAMENTO.includes(estado?.fase);
}

/**
 * O que a pessoa precisa fazer depois de um pacote aplicado, conforme o que
 * mudou (plugin_pacote.py): reiniciar o Revit, só recarregar o pyRevit ou nada.
 * Sem o campo (plugin que não informa), pede o reinício, que é o caso seguro.
 */
export function textoDaAplicada(reinicio) {
  if (reinicio === "nenhum") return "Atualização instalada. Já está valendo, não precisa reiniciar.";
  if (reinicio === "pyrevit") {
    return "Atualização instalada. Recarregue o pyRevit (aba pyRevit › Recarregar) para aplicar.";
  }
  return "Atualização instalada. Reinicie o Revit para concluir.";
}

/** Título do aviso (toast) depois de um pacote aplicado. */
export function tituloDaAplicada(reinicio) {
  if (reinicio === "pyrevit") return "Atualização instalada: recarregue o pyRevit";
  return reinicio === "nenhum" ? "Atualização instalada" : "Atualização instalada: reinicie o Revit";
}

/** Frase para a faixa, a tela de bloqueio e o tooltip do ícone. */
export function textoDoEstado(estado) {
  switch (estado?.fase) {
    case "preparando":
      return "Preparando o download…";
    case "baixando":
      return typeof estado.percentual === "number"
        ? `Baixando a atualização… ${estado.percentual}%`
        : "Baixando a atualização…";
    case "verificando":
      return "Conferindo o arquivo baixado…";
    case "aplicando":
      return "Aplicando a atualização…";
    case "aplicada":
      return textoDaAplicada(estado.reinicio);
    case "agendada":
      return "Atualização pronta. Ela será instalada quando você fechar o Revit.";
    case "manual":
      return "Instalador baixado e conferido. Feche o Revit e execute o arquivo na pasta que foi aberta.";
    case "erro":
      return estado.erro || "Não foi possível atualizar.";
    default:
      return "";
  }
}

/** Reduz uma mensagem da bridge ao próximo estado. */
export function estadoDaMensagem(tipo, payload) {
  const p = payload || {};
  if (tipo === "ATUALIZACAO_PROGRESSO") {
    const fase = ["verificando", "aplicando"].includes(p.etapa) ? p.etapa : "baixando";
    return { fase, percentual: p.percentual ?? null };
  }
  if (tipo === "ATUALIZACAO_RESULTADO") {
    return p.ok
      ? {
          fase: ["agendada", "aplicada"].includes(p.estado) ? p.estado : "manual",
          versao: p.versao,
          reinicio: p.reinicio,
        }
      : { fase: "erro", erro: p.erro };
  }
  return null;
}
