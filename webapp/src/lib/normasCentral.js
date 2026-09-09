import { supabase } from "./supabaseClient";

/**
 * normasCentral.js — busca a base normativa central (tabela `normas_dados`
 * no Supabase — mesma tabela que o site lê em src/lib/normasRemote.js, e
 * que o Python do plugin também lê via sync.buscar_norma) direto com
 * supabase-js, já que a dockpane roda num navegador de verdade (WebView2),
 * não precisa do cliente HTTP manual do lado Python.
 *
 * Diferente do site, não existe fallback estático empacotado aqui (as
 * tabelas de dimensionamento — taxa populacional, larguras mínimas,
 * distâncias máximas — são grandes demais pra duplicar só pra um caminho
 * offline que a dockpane não precisa cobrir): sem rede, a tela de Saída
 * de Emergência simplesmente mostra erro e pede pra tentar de novo.
 * Cache em memória por uf+sistema — só busca uma vez por sessão da
 * dockpane.
 */

const _cache = {}; // `${uf}:${sistema}` -> dados

/** Busca `normas_dados.dados` pra (uf, sistema) — ex.: getNormaCentral("MA",
 * "saida_emergencia") retorna { TAXA_POPULACIONAL, LARGURAS_MINIMAS,
 * DISTANCIAS_MAXIMAS, ... }. Lança se não encontrado ou sem Supabase. */
export async function getNormaCentral(uf, sistema) {
  const chave = `${uf}:${sistema}`;
  if (_cache[chave]) return _cache[chave];

  if (!supabase) {
    throw new Error("Supabase não configurado (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY ausentes).");
  }
  const { data, error } = await supabase
    .from("normas_dados")
    .select("dados")
    .eq("uf", uf)
    .eq("sistema", sistema)
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  if (!data) {
    throw new Error(`Norma "${sistema}" não cadastrada para o estado "${uf}".`);
  }
  _cache[chave] = data.dados;
  return data.dados;
}
