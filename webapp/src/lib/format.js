export function formatarArea(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const numero = Number(valor);
  if (Number.isNaN(numero)) return "—";
  return `${numero.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} m²`;
}

export function formatarMetros(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const numero = Number(valor);
  if (Number.isNaN(numero)) return "—";
  return `${numero.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m`;
}

export function formatarCargaIncendio(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const numero = Number(valor);
  if (Number.isNaN(numero)) return "—";
  return `${numero.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} MJ/m²`;
}

/** "há X min" / "há Xh" / "há X dia(s)" / "há X mês(es)" — mesma leitura
 * do cartão de projeto do site (ETOS.FireUtils, ProjetosPage.jsx/timeAgo),
 * pra bater exatamente com o que ele mostra pro mesmo projeto. */
export function tempoDecorrido(dataIso) {
  if (!dataIso) return "—";
  const diffMs = Date.now() - new Date(dataIso).getTime();
  if (Number.isNaN(diffMs)) return "—";
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h}h`;
  const dias = Math.floor(h / 24);
  if (dias < 30) return `há ${dias} dia${dias !== 1 ? "s" : ""}`;
  const meses = Math.floor(dias / 30);
  return `há ${meses} ${meses !== 1 ? "meses" : "mês"}`;
}

/** Data curta (dd/mm/aaaa) — mesmo formato do cartão de projeto do site. */
export function formatarDataCurta(dataIso) {
  if (!dataIso) return "—";
  const data = new Date(dataIso);
  if (Number.isNaN(data.getTime())) return "—";
  return data.toLocaleDateString("pt-BR");
}
