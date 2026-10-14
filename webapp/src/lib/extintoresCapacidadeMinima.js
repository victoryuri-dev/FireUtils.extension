// extintoresCapacidadeMinima.js — capacidade extintora mínima e distância
// máxima a percorrer por classe de incêndio A/B, conforme o nível de risco
// (extintores portáteis), portado pra dockpane do mesmo jeito que
// hidrantesClassificacao.js porta a Tabela 3 de Hidrantes: fonte de
// verdade em ETOS.FireUtils/src/data/extintores_calc.js (função
// capacidadeMinimaPorRisco). Tabela de referência comum a vários Corpos de
// Bombeiros estaduais (mesmo texto-base citado pela NT 21 CBMMA e pela
// NBR 12693) — valores gerais, não variam por estado, por isso não vem do
// Supabase (normasCentral.js) como o resto da norma de Extintores. A
// distância da classe A coincide com DISTANCIA_MAXIMA.portatil (mesma
// tabela, vista por dois ângulos); a da classe B é fixa em 15 m,
// independente do risco.

export const CAPACIDADE_MINIMA_POR_RISCO = {
  A: {
    baixo: { capacidade: "2-A", distanciaMaxima: 25 },
    medio: { capacidade: "3-A", distanciaMaxima: 20 },
    alto: { capacidade: "4-A", distanciaMaxima: 15 },
  },
  B: {
    baixo: { capacidade: "20-B", distanciaMaxima: 15 },
    medio: { capacidade: "40-B", distanciaMaxima: 15 },
    alto: { capacidade: "80-B", distanciaMaxima: 15 },
  },
};

/** Capacidade extintora mínima (+ distância máxima a percorrer) para a
 * classe de incêndio informada ("A" ou "B"), dado o risco predominante
 * ("baixo"/"medio"/"alto") — ver CAPACIDADE_MINIMA_POR_RISCO acima. */
export function capacidadeMinimaPorRisco(risco, classeIncendio) {
  return CAPACIDADE_MINIMA_POR_RISCO[classeIncendio]?.[risco] ?? null;
}
