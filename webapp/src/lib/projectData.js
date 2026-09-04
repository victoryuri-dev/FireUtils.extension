import { supabase } from "./supabaseClient";

/**
 * Acesso aos dados de projeto/estrutura do site — direto no Supabase (RLS
 * pela sessão do usuário logado), no mesmo espírito de como o catálogo de
 * famílias já é lido direto do bucket público (ver lib/catalog.js): sem
 * Edge Function no meio, sem token.
 *
 * Schema assumido (documentado em detalhe no README.md, seção "Schema do
 * Dashboard") — ajuste os nomes de tabela/coluna abaixo se o schema real
 * do Supabase for diferente:
 *
 *   projetos   (id uuid pk, owner_id uuid, nome text, codigo text,
 *               uf text, ocupacao_principal text, area_construida numeric,
 *               pavimentos_label text, updated_at timestamptz)
 *
 *   estruturas (id uuid pk, projeto_id uuid fk->projetos.id, nome text,
 *               uf text, ocupacao_principal text, ocupacao_label text,
 *               area_construida numeric, area_terreno numeric,
 *               altura_piso_a_piso numeric, risco_label text,
 *               altura_label text)
 *
 * RLS: as políticas do Supabase decidem quais linhas cada usuário pode
 * `select` (dono ou membro do projeto) — este arquivo não filtra por
 * usuário, só repassa o que a política deixar passar.
 */

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function exigirSupabase() {
  if (!supabase) {
    throw new Error("Supabase não configurado (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY ausentes).");
  }
}

const CAMPOS_PROJETO = "id, nome, codigo, uf, ocupacao_principal, area_construida, pavimentos_label, updated_at";

/**
 * Lista os projetos visíveis pro usuário logado (RLS), opcionalmente
 * filtrados por nome/código/id — usado pela tela "Conectar um projeto".
 */
export async function listarProjetosDoUsuario(busca) {
  exigirSupabase();

  let query = supabase.from("projetos").select(CAMPOS_PROJETO).order("updated_at", { ascending: false });

  const termo = (busca || "").trim();
  if (termo) {
    const filtros = [`nome.ilike.%${termo}%`, `codigo.ilike.%${termo}%`];
    if (UUID_REGEX.test(termo)) filtros.push(`id.eq.${termo}`);
    query = query.or(filtros.join(","));
  }

  const { data, error } = await query;
  if (error) throw error;
  return data || [];
}

/** Estruturas cadastradas num projeto — usado pra decidir se pula direto
 * pro dashboard (1 estrutura) ou mostra a tela "Selecione uma estrutura"
 * (mais de uma). */
export async function buscarEstruturasDoProjeto(projetoId) {
  exigirSupabase();
  const { data, error } = await supabase
    .from("estruturas")
    .select("id, nome")
    .eq("projeto_id", projetoId)
    .order("nome", { ascending: true });
  if (error) throw error;
  return data || [];
}

/** Dados do projeto (nome, código público, timestamp) — usado no
 * cabeçalho do dashboard ("NOME DO PROJETO", código, link pro site). */
export async function buscarProjeto(projetoId) {
  exigirSupabase();
  const { data, error } = await supabase
    .from("projetos")
    .select("id, nome, codigo, updated_at")
    .eq("id", projetoId)
    .single();
  if (error) throw error;
  return data;
}

/** Dados completos de uma estrutura (Edificação + Classificação) — usado
 * pra montar o dashboard depois de escolhida/resolvida a estrutura. */
export async function buscarDashboardEstrutura(estruturaId) {
  exigirSupabase();
  const { data, error } = await supabase
    .from("estruturas")
    .select(
      "id, nome, projeto_id, uf, ocupacao_principal, ocupacao_label, area_construida, area_terreno, altura_piso_a_piso, risco_label, altura_label"
    )
    .eq("id", estruturaId)
    .single();
  if (error) throw error;
  return data;
}
