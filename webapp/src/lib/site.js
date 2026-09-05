/** URLs do site (fora do Supabase) — usadas só pra montar links externos
 * abertos pelo Dashboard (nunca chamadas via fetch/XHR daqui). */

const SITE_URL = import.meta.env.VITE_SITE_URL || "";
const NOVO_PROJETO_PATH = import.meta.env.VITE_SITE_NOVO_PROJETO_PATH || "/novo";

/** Link "abrir no site" do cabeçalho do dashboard, ou null sem VITE_SITE_URL
 * configurada (nesse caso o botão/ícone correspondente some). */
export function urlProjeto(projetoId) {
  return SITE_URL && projetoId ? `${SITE_URL}/${projetoId}` : null;
}

/** Link do botão "Criar novo projeto" — o cadastro completo (endereço,
 * RT/ART, sistemas, etc.) continua acontecendo no site; o Revit só linka
 * com o projeto recém-criado depois, pela busca normal. Rota ajustável via
 * VITE_SITE_NOVO_PROJETO_PATH (padrão "/novo") sem precisar mexer em código. */
export function urlNovoProjeto() {
  return SITE_URL ? `${SITE_URL}${NOVO_PROJETO_PATH}` : null;
}
