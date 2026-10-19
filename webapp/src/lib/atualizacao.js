import { supabase } from "./supabaseClient";
import { escolherUltimaVersao } from "./versoes";

// Bucket PRIVADO: só contas com licença lêem (política em
// supabase/migrations/*plugin_releases* no ETOS.FireUtils). Cada versão
// publicada é só o instalador lá dentro, com o nome que o build.ps1 gera.
const BUCKET = "plugin-releases";

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

// O instalador não é mais baixado direto da dockpane: o perfil no site tem a
// seção "Ferramentas disponíveis" com o botão "Baixar plugin" (gera o link do
// bucket privado com a sessão da conta) e mostra as licenças.
export const URL_PERFIL_NO_SITE = "https://fireutils.vercel.app/perfil";

/**
 * Abre o perfil no navegador do sistema. O WebView2 da dockpane manda
 * qualquer janela nova para o navegador padrão
 * (family_loader_webview_forms.py:_ao_pedir_nova_janela), então um
 * window.open basta.
 */
export function abrirPerfilNoSite() {
  window.open(URL_PERFIL_NO_SITE, "_blank");
}
