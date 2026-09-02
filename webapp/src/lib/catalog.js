import { SUPABASE_URL } from "./supabaseClient";
import mockCatalog from "../mock/catalog.mock.json";

const CATALOG_URL =
  import.meta.env.VITE_CATALOG_URL ||
  (SUPABASE_URL ? `${SUPABASE_URL}/storage/v1/object/public/plugin-assets/catalog.json` : null);

/**
 * Busca o catalog.json do bucket público. Sem Supabase configurado (ou se
 * a busca falhar), cai no catálogo de exemplo local (src/mock/catalog.mock.json,
 * gerado por migration/generate_catalog.py a partir da family_library real)
 * — permite desenvolver a UI sem depender do Supabase já estar no ar.
 */
export async function fetchCatalog() {
  if (!CATALOG_URL) {
    console.warn(
      "[catalog] VITE_SUPABASE_URL não configurada — usando catálogo de exemplo local (mock)."
    );
    return mockCatalog;
  }
  try {
    const resposta = await fetch(CATALOG_URL, { cache: "no-store" });
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    return await resposta.json();
  } catch (erro) {
    console.error("[catalog] Falha ao buscar catalog.json remoto, caindo pro mock local:", erro);
    return mockCatalog;
  }
}
