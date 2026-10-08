// numero.js — mesmo formato numérico oficial do site (ETOS.FireUtils,
// src/utils/numero.js): padrão brasileiro, milhar com ponto, decimal com
// vírgula, até `casas` casas decimais, zeros finais cortados. Cópia
// enxuta (só o formatador de exibição, não o parser de digitação — a
// dockpane não tem campo numérico que precise disso) pra "Dimensionamento
// do Sistema" renderizar os mesmos números no mesmo formato que lá.

const cache = new Map();

function formatador(casas) {
  if (!cache.has(casas)) {
    cache.set(
      casas,
      new Intl.NumberFormat("pt-BR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: casas,
        useGrouping: true,
      })
    );
  }
  return cache.get(casas);
}

export function fmtNum(v, casas = 2, vazio = "") {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return vazio;
  const r = Math.abs(n) < 0.5 * 10 ** -casas ? 0 : n;
  return formatador(casas).format(r);
}
