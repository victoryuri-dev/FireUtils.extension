/**
 * Estado da atualização do plugin feita pela dockpane (plugin_atualizacao.py).
 * `fase`: null (parado) | "preparando" | "baixando" | "verificando" |
 *         "agendada" (instala quando o Revit fechar) | "manual" (baixado e
 *         conferido; o usuário executa) | "erro".
 */

export const EM_ANDAMENTO = ["preparando", "baixando", "verificando"];

export function emAndamento(estado) {
  return EM_ANDAMENTO.includes(estado?.fase);
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
    return { fase: p.etapa === "verificando" ? "verificando" : "baixando", percentual: p.percentual ?? null };
  }
  if (tipo === "ATUALIZACAO_RESULTADO") {
    return p.ok
      ? { fase: p.estado === "agendada" ? "agendada" : "manual", versao: p.versao }
      : { fase: "erro", erro: p.erro };
  }
  return null;
}
