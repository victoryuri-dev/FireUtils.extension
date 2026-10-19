import { supabase } from "./supabaseClient";

// Bucket PRIVADO: só contas com licença lêem (política em
// supabase/migrations/*plugin_releases* no ETOS.FireUtils). O instalador e o
// manifesto vão para lá a cada versão publicada.
const BUCKET = "plugin-releases";
const ARQUIVO_MANIFESTO = "manifest.json";

// Validade do link de download — o suficiente para o navegador começar.
const VALIDADE_LINK_S = 600;

/**
 * Lê o manifesto da última versão publicada.
 * Devolve `{ versao, hostMinVersion, arquivo, notas }` ou null. Nunca lança:
 * sem manifesto (bucket ainda vazio, sem licença, sem internet) a dockpane
 * simplesmente não mostra aviso de atualização.
 */
export async function buscarManifesto() {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.storage.from(BUCKET).download(ARQUIVO_MANIFESTO);
    if (error || !data) {
      console.info("[atualização] sem manifesto:", error?.message || "vazio");
      return null;
    }
    const manifesto = JSON.parse(await data.text());
    return manifesto && typeof manifesto === "object" ? manifesto : null;
  } catch (ex) {
    console.info("[atualização] manifesto ilegível:", ex?.message || ex);
    return null;
  }
}

/**
 * Abre o download do instalador no navegador do sistema. O WebView2 da
 * dockpane manda qualquer janela nova para o navegador padrão
 * (family_loader_webview_forms.py:_ao_pedir_nova_janela), então um
 * window.open basta. Devolve false se não deu para gerar o link.
 */
export async function abrirDownloadDoInstalador(manifesto) {
  if (!supabase || typeof manifesto?.arquivo !== "string") return false;
  try {
    const { data, error } = await supabase.storage
      .from(BUCKET)
      .createSignedUrl(manifesto.arquivo, VALIDADE_LINK_S, { download: manifesto.arquivo });
    if (error || !data?.signedUrl) return false;
    window.open(data.signedUrl, "_blank");
    return true;
  } catch {
    return false;
  }
}
