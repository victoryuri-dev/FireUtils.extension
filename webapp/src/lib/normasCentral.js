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

// A linha de "saida_emergencia" guarda as chaves em minúsculo (tabela/
// notas/larguras_minimas/distancias_maximas — mesma convenção que o lado
// Python já usava, ver Fire Utils.tab/lib/normas/__init__.py.
// _CHAVES_SAIDAS), mas o motor de cálculo e a UI portados do site
// (data/se_calc.js, components/dashboard/seShared.jsx,
// AcessosDescargasView.jsx) esperam os nomes em maiúsculo que o arquivo
// estático do site usa (TAXA_POPULACIONAL, NOTAS_NORMATIVAS,
// LARGURAS_MINIMAS, DISTANCIAS_MAXIMAS) — sem esse adaptador, a estrutura
// batia campo a campo mas com nome de chave diferente, e a tela quebrava
// (`Cannot read properties of undefined`) assim que a tabela central
// tivesse dados de verdade. Mesmo adaptador existe no site (ver
// getSE/adaptarSEDaBaseCentral em src/data/normas/index.js lá).
export async function getSeNorma(uf) {
  const remoto = await getNormaCentral(uf, "saida_emergencia");
  return {
    ...remoto,
    TAXA_POPULACIONAL: remoto.tabela,
    NOTAS_NORMATIVAS: remoto.notas,
    LARGURAS_MINIMAS: remoto.larguras_minimas,
    DISTANCIAS_MAXIMAS: remoto.distancias_maximas,
  };
}
