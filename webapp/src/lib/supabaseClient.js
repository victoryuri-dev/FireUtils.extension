import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "";
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "";

export const SUPABASE_URL = supabaseUrl;

// Sem as env vars configuradas (ex.: enquanto o projeto Supabase ainda está
// sendo criado), o cliente fica null — o resto do app trata isso como
// "modo mock" em vez de quebrar com uma exceção de inicialização.
export const supabase =
  supabaseUrl && supabaseAnonKey ? createClient(supabaseUrl, supabaseAnonKey) : null;

/** Monta a URL pública de um arquivo do bucket plugin-assets a partir da
 * chave relativa salva no catalog.json (ex.: "icons/hidrantes.png"). */
export function publicAssetUrl(key) {
  if (!key || !SUPABASE_URL) return null;
  return `${SUPABASE_URL}/storage/v1/object/public/plugin-assets/${key}`;
}

const SIGNED_URL_TTL_SECONDS = 60;

/** Gera uma Signed URL temporária pro .rfa no bucket privado
 * (revit-families) — só funciona com o usuário autenticado, é o RLS do
 * bucket que decide isso no lado do Supabase. */
export async function criarSignedUrlFamilia(storageKey) {
  if (!supabase) {
    throw new Error("Supabase não configurado (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY ausentes).");
  }
  const { data, error } = await supabase.storage
    .from("revit-families")
    .createSignedUrl(storageKey, SIGNED_URL_TTL_SECONDS);
  if (error) throw error;
  return data.signedUrl;
}
