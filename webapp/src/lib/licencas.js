/**
 * Quais abas da dockpane cada licença libera.
 *
 * Os módulos são os mesmos de `public.licencas` no Supabase e da página de
 * preços do site: 'hidrantes', 'saidas', 'memorial' e 'pro'. Quem decide é o
 * Python (lib/licenca.py), que resolve a licença uma vez por sessão do Revit
 * e responde pela bridge — aqui só se traduz o resultado em navegação.
 */

export const MODULO_PRO = "pro";

/**
 * A Biblioteca de Famílias é gratuita de propósito: é a porta de entrada do
 * produto e, principalmente, é onde o login acontece. Bloqueá-la deixaria
 * quem tem licença sem como autenticar, e sem autenticar não há licença
 * nenhuma a verificar.
 */
export const QUALQUER_LICENCA = "*";

export const MODULO_POR_ABA = {
  biblioteca: null,
  dashboard: QUALQUER_LICENCA,
  hidrantes: "hidrantes",
  saidas: "saidas",
};

export const NOME_DO_MODULO = {
  hidrantes: "Hidrantes",
  saidas: "Saídas",
  memorial: "Memorial",
  pro: "FireUtils PRO",
};

/**
 * A conta pode abrir esta aba?
 *
 * @param {string[]|null} modulos — liberados; null enquanto o Python não respondeu
 * @param {string} aba
 */
export function abaLiberada(modulos, aba) {
  const exigido = MODULO_POR_ABA[aba];
  if (!exigido) return true;

  // Ainda sem resposta: não libera, mas quem chama trata como "carregando"
  // em vez de mostrar bloqueio — senão a tela pisca um aviso indevido.
  if (!modulos) return false;

  // PRO libera tudo. Quem contrata os três avulsos recebe a linha 'pro' pela
  // própria assinatura — equivalências de plano são decididas lá, não aqui.
  if (modulos.includes(MODULO_PRO)) return true;
  if (exigido === QUALQUER_LICENCA) return modulos.length > 0;
  return modulos.includes(exigido);
}

export function rotuloDoModuloDaAba(aba) {
  const exigido = MODULO_POR_ABA[aba];
  if (!exigido || exigido === QUALQUER_LICENCA) return null;
  return NOME_DO_MODULO[exigido] || exigido;
}
