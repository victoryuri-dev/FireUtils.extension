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

/** "Editado há Xh" / "Editado há Xd" a partir de um timestamp ISO. */
export function formatarEditadoHa(dataIso) {
  if (!dataIso) return null;
  const diffMs = Date.now() - new Date(dataIso).getTime();
  if (Number.isNaN(diffMs)) return null;
  const horas = Math.max(1, Math.round(diffMs / 3_600_000));
  if (horas < 24) return `Editado há ${horas}h`;
  const dias = Math.round(horas / 24);
  return `Editado há ${dias}d`;
}
