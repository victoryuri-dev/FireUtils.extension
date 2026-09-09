import { supabase } from "./supabaseClient";

/**
 * Acesso cru à tabela `projetos` do usuário logado — direto no Supabase
 * (RLS por user_id = auth.uid()), no mesmo espírito de como o catálogo de
 * famílias já é lido direto do bucket público (ver lib/catalog.js): sem
 * Edge Function no meio, sem token.
 *
 * Schema real (uma tabela só — sem "estruturas" separada, tudo mora dentro
 * da coluna `dados` jsonb):
 *
 *   projetos (id text PK, user_id uuid, nome text, dados jsonb,
 *             sync_token uuid, created_at timestamptz, updated_at timestamptz,
 *             version integer)
 *
 * A forma de `dados` (uf, areaConstruidaTotal, areaTerreno, estruturas[],
 * pavimentos[], cargaState, ...) é decodificada em lib/projetoDados.js —
 * este arquivo busca a linha crua e (a partir da tela "Saída de
 * Emergência" da dockpane) também grava de volta em `dados`.
 */

function exigirSupabase() {
  if (!supabase) {
    throw new Error("Supabase não configurado (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY ausentes).");
  }
}

const CAMPOS_PROJETO = "id, nome, dados, updated_at, version";

/** Lista os projetos do usuário logado (RLS), opcionalmente filtrados por
 * nome/id — usado pela tela "Conectar um projeto". */
export async function listarProjetosDoUsuario(busca) {
  exigirSupabase();

  let query = supabase.from("projetos").select(CAMPOS_PROJETO).order("updated_at", { ascending: false });

  const termo = (busca || "").trim();
  if (termo) {
    query = query.or(`nome.ilike.%${termo}%,id.ilike.%${termo}%`);
  }

  const { data, error } = await query;
  if (error) throw error;
  return data || [];
}

/** Uma linha de projeto por id — usado pra retomar um vínculo já salvo no
 * firedata.json sem precisar listar tudo de novo. */
export async function buscarProjeto(projetoId) {
  exigirSupabase();
  const { data, error } = await supabase.from("projetos").select(CAMPOS_PROJETO).eq("id", projetoId).single();
  if (error) throw error;
  return data;
}

/**
 * Grava `novosDados` na coluna `dados` da linha do projeto — compare-and-
 * swap pela `versaoConhecida` (mesmo espírito do autosave do site, ver
 * ProjetoContext.jsx): se a versão no banco já mudou (outra sessão/aba —
 * ou o próprio site — salvou por cima enquanto esta tela estava aberta),
 * a escrita não acontece e a função lança, em vez de sobrescrever
 * silenciosamente. Diferente do site, não tenta re-mesclar e salvar de
 * novo sozinha — quem chama decide (normalmente: avisar o usuário e
 * pedir pra reabrir a tela). Retorna a nova versão em caso de sucesso.
 */
export async function salvarDadosProjeto(projetoId, versaoConhecida, novosDados) {
  exigirSupabase();
  const { data, error } = await supabase
    .from("projetos")
    .update({ dados: novosDados, version: versaoConhecida + 1, updated_at: new Date().toISOString() })
    .eq("id", projetoId)
    .eq("version", versaoConhecida)
    .select("version");
  if (error) throw error;
  if (!data || data.length === 0) {
    throw new Error("Este projeto foi alterado em outro lugar (outra sessão, ou o site) enquanto você editava. Feche e reabra a tela de Saída de Emergência para ver a versão mais recente antes de tentar de novo.");
  }
  return data[0].version;
}
