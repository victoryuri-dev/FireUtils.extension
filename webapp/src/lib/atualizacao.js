import { supabase } from "./supabaseClient";
import { nomesDosArquivos, notasDasVersoes } from "./versoesPublicadas";

// Bucket PRIVADO: só contas com licença lêem (política em
// supabase/migrations/*plugin_releases* no ETOS.FireUtils). Cada versão
// publicada é só o instalador lá dentro, com o nome que o build.ps1 gera.
const BUCKET = "plugin-releases";

/**
 * Os nomes de arquivo do bucket (instaladores e pacotes). A escolha da versão a
 * oferecer é de `escolherAtualizacao` (versoes.js), que também precisa da versão
 * instalada. null se não deu para listar: bucket sem acesso (conta sem licença)
 * ou sem internet significam só "sem aviso de atualização".
 */
export async function listarArquivosPublicados() {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.storage.from(BUCKET).list("", { limit: 1000 });
    if (error || !data) {
      console.info("[atualização] não foi possível listar as versões:", error?.message || "vazio");
      return null;
    }
    return data.map((item) => item.name);
  } catch (ex) {
    console.info("[atualização] falha ao listar as versões:", ex?.message || ex);
    return null;
  }
}

/**
 * As versões publicadas pelo painel de administração (tabela `plugin_releases`):
 * os nomes de arquivo (para `escolherAtualizacao`) e as notas de atualização.
 * Se a tabela não responder ou vier vazia, cai na listagem do bucket (os
 * arquivos continuam com os mesmos nomes), sem notas do painel — assim a
 * atualização não deixa de ser avisada. null se nada deu certo.
 *
 * @returns {Promise<{arquivos: string[], notas: object[]}|null>}
 */
export async function listarVersoesPublicadas() {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from("plugin_releases")
      .select("versao, tipo, arquivo, base_minima, titulo, notas, publicada_em")
      .eq("publicada", true);
    if (!error && data?.length) {
      return { arquivos: nomesDosArquivos(data), notas: notasDasVersoes(data) };
    }
    console.info("[atualização] tabela de versões indisponível, usando o bucket:", error?.message || "vazia");
  } catch (ex) {
    console.info("[atualização] falha ao ler as versões publicadas:", ex?.message || ex);
  }
  const arquivos = await listarArquivosPublicados();
  return arquivos ? { arquivos, notas: [] } : null;
}

/**
 * Links temporários do instalador e do hash (`<instalador>.sha256`, ao lado
 * dele no bucket) para o Python baixar — é ele quem baixa, confere e instala
 * (plugin_atualizacao.py). Devolve `{ urlInstalador, urlHash }` ou `{ erro }`.
 */
export async function gerarLinksDaAtualizacao(publicada) {
  if (!supabase || typeof publicada?.arquivo !== "string") {
    return { erro: "Não foi possível gerar o link de download." };
  }
  // Pacote: o arquivo de conferência é a assinatura (.sig); instalador: o hash.
  const pacote = publicada.tipo === "pacote";
  const conferencia = `${publicada.arquivo}${pacote ? ".sig" : ".sha256"}`;
  try {
    const bucket = supabase.storage.from(BUCKET);
    const [principal, confere] = await Promise.all([
      bucket.createSignedUrl(publicada.arquivo, 1800),
      bucket.createSignedUrl(conferencia, 1800),
    ]);
    // Diz QUAL arquivo falhou: o mais comum é a versão ter sido publicada sem
    // o arquivo de conferência ao lado (a atualização pela dockpane exige os dois).
    if (!principal.data?.signedUrl) {
      console.warn("[atualização] arquivo:", principal.error?.message);
      return { erro: `Não foi possível gerar o link de ${publicada.arquivo}. Confira se ele está no bucket e se a conta tem licença.` };
    }
    if (!confere.data?.signedUrl) {
      console.warn("[atualização] conferência:", confere.error?.message);
      return { erro: `Falta o arquivo de conferência ${conferencia} no bucket (ele precisa ficar ao lado do arquivo).` };
    }
    return pacote
      ? { urlPacote: principal.data.signedUrl, urlAssinatura: confere.data.signedUrl }
      : { urlInstalador: principal.data.signedUrl, urlHash: confere.data.signedUrl };
  } catch (ex) {
    return { erro: `Falha ao preparar o download: ${ex?.message || ex}` };
  }
}

// Sem o instalar-pela-dockpane (plugin antigo), o caminho é o site: o perfil no site tem a
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
