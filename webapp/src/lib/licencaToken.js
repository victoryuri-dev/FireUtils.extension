import { supabase } from "./supabaseClient";

// Quanto antes do vencimento a dockpane pede um token novo. O token vale
// LICENCA_TTL_DIAS (hoje 7, no servidor); com a margem igual à validade, cada
// abertura do painel com internet renova o token (janela deslizante), e quem
// abre o painel pelo menos uma vez por semana nunca fica sem licença.
const MARGEM_RENOVACAO_DIAS = 7;

/**
 * O Python guardou um token que ainda serve? Plugins antigos não mandam
 * `suportaToken` (conferiam a licença na rede com o refresh token), e para
 * eles não há o que renovar.
 */
export function precisaRenovarToken(resumo, agoraS = Date.now() / 1000) {
  const { suportaToken, tokenValido, tokenExpiraEm } = resumo || {};
  if (!suportaToken) return false;
  if (!tokenValido) return true;
  return typeof tokenExpiraEm === "number" && tokenExpiraEm - agoraS < MARGEM_RENOVACAO_DIAS * 86400;
}

/**
 * O plugin RECUSOU o token que acabou de receber? Só é recusa se ele não guardou
 * um token válido. Não use `precisaRenovarToken` para isso: com a margem de
 * renovação igual à validade do token (7 dias), um token recém-emitido sempre
 * "precisa renovar", e isso virava um aviso falso de licença recusada.
 */
export function tokenRecusado(resumo) {
  const { suportaToken, tokenValido } = resumo || {};
  return !!suportaToken && !tokenValido;
}

/**
 * Busca no servidor o token de licença assinado, com a sessão do usuário (o
 * supabase-js manda o access token sozinho). Devolve a string do token, ou
 * null se não foi possível — sem sessão, sem internet, function fora do ar.
 * Quem chama decide o que mostrar; aqui só o motivo vai para o console.
 */
export async function buscarTokenDeLicenca() {
  if (!supabase) return null;

  const { data: sessao } = await supabase.auth.getSession();
  if (!sessao?.session) return null;

  try {
    const { data, error } = await supabase.functions.invoke("emitir-licenca", { body: {} });
    if (error || !data?.token) {
      console.warn("[licenças] não foi possível obter o token:", error?.message || "resposta sem token");
      return null;
    }
    return data.token;
  } catch (ex) {
    console.warn("[licenças] não foi possível obter o token:", ex?.message || ex);
    return null;
  }
}
