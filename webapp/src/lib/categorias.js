// Rótulos curtos das categorias na Biblioteca — só cosméticos: o filtro usa
// categoria.id; category_id sem entrada aqui cai no nome cheio do catálogo.
export const ROTULO_CURTO_POR_CATEGORIA = {
  "extintor-de-incendio": "Extintor",
  "hidrantes": "Sistema de Hidrante",
  "alarme-de-incendio": "Alarme",
  "detector-de-incendio": "Detector",
};

export function rotuloDaCategoria(categoria) {
  return ROTULO_CURTO_POR_CATEGORIA[categoria.id] || categoria.name;
}

/**
 * Ordena as famílias da Biblioteca.
 *  - "az": ordem alfabética pelo nome.
 *  - "recentes": as lançadas mais recentemente primeiro, pela data de criação
 *    (`criado_em` do catálogo). Sem data (catálogo antigo), vale a posição no
 *    catálogo: quem vem depois é tratado como mais novo.
 * Não altera o array recebido.
 */
export function ordenarFamilias(familias, ordem, posicaoNoCatalogo = new Map()) {
  const copia = [...familias];
  if (ordem === "recentes") {
    const data = (f) => Date.parse(f.criado_em) || 0;
    copia.sort(
      (a, b) =>
        data(b) - data(a) ||
        (posicaoNoCatalogo.get(b.id) ?? 0) - (posicaoNoCatalogo.get(a.id) ?? 0) ||
        a.name.localeCompare(b.name)
    );
  } else {
    copia.sort((a, b) => a.name.localeCompare(b.name));
  }
  return copia;
}
