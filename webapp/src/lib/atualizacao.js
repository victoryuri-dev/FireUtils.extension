import { supabase } from "./supabaseClient";
import { escolherUltimaVersao } from "./versoes";

// Bucket PRIVADO: só contas com licença lêem (política em
// supabase/migrations/*plugin_releases* no ETOS.FireUtils). Cada versão
// publicada é só o instalador lá dentro, com o nome que o build.ps1 gera.
const BUCKET = "plugin-releases";

// Validade do link de download — o suficiente para o navegador começar.
const VALIDADE_LINK_S = 600;

/**
 * A última versão publicada: a maior entre os `FireUtils-Setup-X.Y.Z.exe` do
 * bucket. Devolve `{ versao, arquivo }` ou null. Nunca lança: bucket vazio,
 * sem licença ou sem internet significam só "sem aviso de atualização".
 */
export async function buscarUltimaVersaoPublicada() {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.storage.from(BUCKET).list("", { limit: 1000 });
    if (error || !data) {
      console.info("[atualização] não foi possível listar as versões:", error?.message || "vazio");
      return null;
    }
    return escolherUltimaVersao(data.map((item) => item.name));
  } catch (ex) {
    console.info("[atualização] falha ao listar as versões:", ex?.message || ex);
    return null;
  }
}

/**
 * Abre o download do instalador no navegador do sistema. O WebView2 da
 * dockpane manda qualquer janela nova para o navegador padrão
 * (family_loader_webview_forms.py:_ao_pedir_nova_janela), então um
 * window.open basta. Devolve false se não deu para gerar o link.
 */
export async function abrirDownloadDoInstalador(publicada) {
  if (!supabase || typeof publicada?.arquivo !== "string") return false;
  try {
    const { data, error } = await supabase.storage
      .from(BUCKET)
      .createSignedUrl(publicada.arquivo, VALIDADE_LINK_S, { download: publicada.arquivo });
    if (error || !data?.signedUrl) return false;
    window.open(data.signedUrl, "_blank");
    return true;
  } catch {
    return false;
  }
}
