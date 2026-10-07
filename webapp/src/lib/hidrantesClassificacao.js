// hidrantesClassificacao.js — mesmo método de classificação do Sistema de
// Hidrantes/Mangotinhos (Tabela 3, NT 22 CBMMA) usado no site
// (ETOS.FireUtils/src/data/hidrantes_calc.js), portado pra dockpane poder
// classificar e aplicar o sistema direto no Revit, sem depender do site
// pra essa decisão. Funções puras — recebem os dados normativos
// (normaHidrantesMA.js) como parâmetro.

const num = (v) => parseFloat(v) || 0;

/** Coluna da Tabela 3 (1-4) para uma divisão, dada a carga de incêndio
 * (MJ/m²) do pavimento — usa a faixa quando a divisão depende de carga,
 * senão a coluna fixa. Retorna null se a divisão não consta na tabela. */
export function colunaDaDivisao(divisao, cargaMJm2, norma) {
  const porCarga = norma.DIVISOES_POR_CARGA[divisao];
  if (porCarga) {
    const carga = num(cargaMJm2);
    const faixa = porCarga.find((f) => (f.min == null || carga >= f.min) && (f.max == null || carga < f.max));
    return faixa ? faixa.coluna : null;
  }
  return norma.DIVISOES_COLUNA[divisao] ?? null;
}

/** Índice da faixa de área (0-based, Tabela 3) para uma área construída
 * total em m². Retorna -1 se a área for inválida/zero. */
export function faixaAreaIndex(areaTotal, norma) {
  const a = num(areaTotal);
  if (a <= 0) return -1;
  return norma.FAIXAS_AREA.findIndex((f) => (f.min == null || a > f.min) && (f.max == null || a <= f.max));
}

/** Opções de classificação (Tipo + RTI) para uma coluna/faixa, considerando
 * chuveiros automáticos (`possuiSprinklers`, só "está ativo" — a dockpane
 * não sabe se o sistema é EXIGIDO ou instalado por conta própria, só se o
 * RT marcou o toggle manual; ver projetoDados.js:sistemasAtivos). Isso
 * basta pra coluna 4 Tipo 5 (Nota 1 da Tabela 3 conta a exigência, a Nota 2
 * conta "não exigido mas instalado" — os dois casos levam ao MESMO Tipo 4
 * aqui, só muda a nota citada, que a dockpane nem mostra). NÃO basta pra
 * coluna 3 ou coluna 4 Tipo 4: aí só a Nota 2 se aplica, e ela exige que os
 * chuveiros NÃO sejam exigidos — sem esse dado, a dockpane não rebaixa
 * esses dois casos (fica só no Tipo da tabela, sem pills) pra nunca
 * oferecer um rebaixamento que a norma não permitiria se os chuveiros
 * forem exigidos. Classificação completa (as duas notas, os dois sinais)
 * só no site — ver hidrantes_calc.js:opcoesClassificacao. */
export function opcoesClassificacao(coluna, faixaIndex, possuiSprinklers, norma) {
  if (coluna == null || faixaIndex < 0 || faixaIndex >= norma.TABELA3.length) return [];
  const linha = norma.TABELA3[faixaIndex];

  if (coluna === 1) {
    return [
      { tipo: 1, rti: linha.col1.tipo1.rti },
      { tipo: 2, rti: linha.col1.tipo2.rti },
    ];
  }
  if (coluna === 2) {
    return [{ tipo: linha.col2.tipo, rti: linha.col2.rti }];
  }
  if (coluna === 3) {
    return [{ tipo: linha.col3.tipo, rti: linha.col3.rti }];
  }
  if (coluna === 4) {
    const base = { tipo: linha.col4.tipo, rti: linha.col4.rti };
    if (linha.col4.tipo === 5 && possuiSprinklers) {
      return [base, { tipo: 4, rti: linha.col3.rti }];
    }
    return [base];
  }
  return [];
}

/** Divisão de maior carga de incêndio entre uma lista de divisões — mesmo
 * critério do site (a NT 22 não dá regra explícita pra ocupação mista):
 * a de maior carga (mais exigente) vira a referência. */
export function divisaoMaiorCarga(divisoesComCarga, norma) {
  let melhor = null;
  divisoesComCarga.forEach(({ divisao, cargaMJm2 }) => {
    const coluna = colunaDaDivisao(divisao, cargaMJm2, norma);
    if (coluna == null) return;
    if (!melhor || cargaMJm2 > melhor.cargaMJm2) melhor = { divisao, coluna, cargaMJm2 };
  });
  return melhor;
}

/** Sugestão completa de classificação: cruza área construída total +
 * divisão de maior carga de incêndio + presença de sprinklers, devolve as
 * opções de Tipo/RTI prontas pra dockpane exibir/aplicar.
 * `divisoesComCarga`: [{ divisao, cargaMJm2 }]. */
export function sugerirClassificacao(areaTotal, divisoesComCarga, possuiSprinklers, norma) {
  const faixaIndex = faixaAreaIndex(areaTotal, norma);
  if (faixaIndex < 0 || !divisoesComCarga?.length) {
    return { faixaIndex, coluna: null, divisao: null, opcoes: [] };
  }
  const maiorCarga = divisaoMaiorCarga(divisoesComCarga, norma);
  if (!maiorCarga) return { faixaIndex, coluna: null, divisao: null, opcoes: [] };
  const opcoes = opcoesClassificacao(maiorCarga.coluna, faixaIndex, possuiSprinklers, norma);
  return { faixaIndex, coluna: maiorCarga.coluna, divisao: maiorCarga.divisao, opcoes };
}
