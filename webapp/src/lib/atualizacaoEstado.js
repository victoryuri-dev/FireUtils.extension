/**
 * Estado da atualização do plugin feita pela dockpane (plugin_atualizacao.py).
 * `fase`: null (parado) | "preparando" | "baixando" | "verificando" |
 *         "aplicando" | "recarregando" (pyRevit sendo recarregado) |
 *         "aplicada" (pacote instalado; falta uma ação: `reinicio` diz qual) |
 *         "agendada" (instala quando o Revit fechar) | "manual" (baixado e
 *         conferido; o usuário executa) | "erro".
 */

export const EM_ANDAMENTO = ["preparando", "baixando", "verificando", "aplicando", "recarregando"];

export function emAndamento(estado) {
  return EM_ANDAMENTO.includes(estado?.fase);
}

/** Frase para a faixa, a tela de bloqueio e o tooltip do ícone. */
export function textoDoEstado(estado) {
  const v = estado?.versao ? ` v${estado.versao}` : "";
  switch (estado?.fase) {
    case "preparando":
      return "Preparando a atualização…";
    case "baixando":
      return typeof estado.percentual === "number"
        ? `Baixando a atualização${v}… ${estado.percentual}%`
        : `Baixando a atualização${v}…`;
    case "verificando":
      return "Conferindo o arquivo baixado…";
    case "aplicando":
      return "Instalando a atualização…";
    case "recarregando":
      return "Recarregando o pyRevit…";
    case "aplicada":
      if (estado.reinicio === "nenhum") {
        return `Atualização${v} instalada. Recarregue o painel para concluir.`;
      }
      if (estado.reinicio === "pyrevit") {
        return estado.recarga === "falhou"
          ? "O pyRevit não recarregou sozinho. Salve o projeto e use o botão Recarregar da aba pyRevit, no Revit."
          : `Atualização${v} pronta. Salve o projeto e reinicie o pyRevit para aplicá-la.`;
      }
      return `Atualização${v} instalada. Salve o projeto e reinicie o Revit para concluir. Até lá, o painel continua funcionando.`;
    case "agendada":
      return `Atualização${v} baixada. Ela será instalada quando você fechar o Revit; salve o projeto antes.`;
    case "manual":
      return `Atualização${v} baixada na pasta Downloads. Salve o projeto, feche o Revit e execute o instalador.`;
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
    return { fase, percentual: p.percentual ?? null, versao: p.versao };
  }
  if (tipo === "ATUALIZACAO_RESULTADO") {
    return p.ok
      ? {
          fase: ["agendada", "aplicada"].includes(p.estado) ? p.estado : "manual",
          versao: p.versao,
          reinicio: p.reinicio,
          recarga: p.recarga,
        }
      : { fase: "erro", erro: p.erro };
  }
  return null;
}
