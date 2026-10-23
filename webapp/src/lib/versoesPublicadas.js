/**
 * Versões publicadas pelo painel de administração (tabela `plugin_releases`,
 * só as publicadas chegam aqui: a política do banco filtra). Funções puras,
 * cobertas por test/versoesPublicadas.test.js.
 *
 * Cada linha: { versao, tipo: "instalador"|"pacote", arquivo, base_minima,
 *               titulo, notas: [{ tipo, texto }], publicada_em }
 */

/**
 * Nomes de arquivo no formato que `escolherAtualizacao` (versoes.js) espera —
 * os mesmos que existiam no bucket: o arquivo e o que fica ao lado dele (o
 * `.sig` do pacote, o `.sha256` do instalador).
 */
export function nomesDosArquivos(linhas) {
  const nomes = [];
  for (const l of linhas) {
    if (typeof l?.arquivo !== "string") continue;
    nomes.push(l.arquivo, `${l.arquivo}${l.tipo === "pacote" ? ".sig" : ".sha256"}`);
  }
  return nomes;
}

// "AAAA-MM-DD" no horário do Brasil (UTC-3), o formato que a página "Atualizações" exibe.
function dataBrasil(iso) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  return new Date(t - 3 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/**
 * As linhas viram o formato de `PATCH_NOTES` (data/patchNotes.js):
 * { versao, data, titulo, itens: [{ tipo, texto }] }. Instalador e pacote da
 * mesma versão viram UMA nota (título do primeiro que tiver, itens juntos sem
 * repetir). Versões sem título e sem itens não geram nota.
 */
export function notasDasVersoes(linhas) {
  const porVersao = new Map();
  for (const l of linhas) {
    if (typeof l?.versao !== "string") continue;
    const nota = porVersao.get(l.versao) ?? { versao: l.versao, data: "", titulo: "", itens: [] };
    if (!nota.titulo && l.titulo) nota.titulo = l.titulo;
    if (!nota.data && l.publicada_em) nota.data = dataBrasil(l.publicada_em);
    for (const item of Array.isArray(l.notas) ? l.notas : []) {
      const texto = typeof item?.texto === "string" ? item.texto.trim() : "";
      if (!texto) continue;
      if (!nota.itens.some((i) => i.tipo === item.tipo && i.texto === texto)) nota.itens.push({ tipo: item.tipo, texto });
    }
    porVersao.set(l.versao, nota);
  }
  return [...porVersao.values()].filter((n) => n.titulo || n.itens.length);
}

/** As notas do painel prevalecem; as locais (patchNotes.js) cobrem só as versões que o painel não tem. */
export function mesclarNotas(doPainel, locais) {
  const versoes = new Set(doPainel.map((n) => n.versao));
  return [...doPainel, ...locais.filter((n) => !versoes.has(n.versao))];
}
