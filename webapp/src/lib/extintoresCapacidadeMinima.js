// extintoresCapacidadeMinima.js — Tabelas 4 e 5 (capacidade extintora
// mínima e distância máxima a percorrer por classe de incêndio A/B,
// conforme o nível de risco da Tabela 3), portado pra dockpane do mesmo
// jeito que hidrantesClassificacao.js porta a Tabela 3 de Hidrantes: fonte
// de verdade em ETOS.FireUtils/src/data/extintores_calc.js (função
// capacidadeMinimaPorRisco). Tabela de referência comum a vários Corpos de
// Bombeiros estaduais (mesmo texto-base citado pela NT 21 CBMMA e pela
// NBR 12693) — valores gerais, não variam por estado, por isso não vem do
// Supabase (normasCentral.js) como o resto da norma de Extintores.

export const CAPACIDADE_MINIMA_POR_RISCO = {
  A: {
    baixo: [{ capacidade: "2-A", distanciaMaxima: 20 }],
    medio: [{ capacidade: "3-A", distanciaMaxima: 20 }],
    alto: [
      { capacidade: "3-A", distanciaMaxima: 15 },
      { capacidade: "4-A", distanciaMaxima: 20 },
    ],
  },
  B: {
    baixo: [{ capacidade: "20-B", distanciaMaxima: 15 }],
    medio: [{ capacidade: "40-B", distanciaMaxima: 15 }],
    alto: [
      { capacidade: "40-B", distanciaMaxima: 10 },
      { capacidade: "80-B", distanciaMaxima: 15 },
    ],
  },
};

/** Opções de capacidade extintora mínima (+ distância máxima a percorrer)
 * para a classe de incêndio informada ("A" ou "B"), dado o risco
 * predominante ("baixo"/"medio"/"alto") — ver CAPACIDADE_MINIMA_POR_RISCO
 * acima. Nível "alto" devolve duas opções equivalentes (unidade menor com
 * percurso mais curto, ou unidade maior com percurso mais longo). */
export function capacidadeMinimaPorRisco(risco, classeIncendio) {
  return CAPACIDADE_MINIMA_POR_RISCO[classeIncendio]?.[risco] ?? [];
}
