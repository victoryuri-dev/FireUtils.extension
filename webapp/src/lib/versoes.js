/**
 * Versão do plugin instalado × versão publicada.
 *
 * O manifesto (`manifest.json`, no bucket privado `plugin-releases` do
 * Supabase) diz qual é a versão mais nova e qual a mínima que esta interface
 * aceita (`hostMinVersion`). Como a interface é publicada na hora (Vercel) e
 * o plugin só muda com um instalador novo, as duas podem ficar desencontradas
 * — daí a comparação aqui.
 */

// O que o plugin responde quando roda direto do repositório (sem VERSION do
// instalador): é ambiente de desenvolvimento, não há o que atualizar.
export const VERSAO_DEV = "dev";

const PADRAO = /^\d+(\.\d+){0,3}$/;

export function versaoValida(versao) {
  return typeof versao === "string" && PADRAO.test(versao.trim());
}

/** -1, 0 ou 1. Partes que faltam valem 0 ("2.1" = "2.1.0"). */
export function compararVersoes(a, b) {
  const pa = a.trim().split(".").map(Number);
  const pb = b.trim().split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] ?? 0;
    const y = pb[i] ?? 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

/**
 * Em que pé está o plugin instalado.
 *
 * @param instalada  string da versão; `null` = plugin antigo, que não informa
 *                   versão (é anterior a qualquer versão publicada)
 * @param manifesto  { versao, hostMinVersion? } ou null (sem manifesto)
 * @returns {{estado: "desconhecido"|"em_dia"|"disponivel"|"obrigatoria", versaoNova?: string, minima?: string}}
 *   - "obrigatoria": abaixo da `hostMinVersion` — esta interface não funciona direito
 *   - "disponivel":  há versão mais nova, mas a atual ainda serve
 */
export function avaliarVersao({ instalada, manifesto }) {
  if (instalada === undefined) return { estado: "desconhecido" };
  if (!manifesto || !versaoValida(manifesto.versao)) return { estado: "desconhecido" };
  if (instalada === VERSAO_DEV) return { estado: "em_dia" };

  const atual = versaoValida(instalada) ? instalada : "0";
  const minima = versaoValida(manifesto.hostMinVersion) ? manifesto.hostMinVersion : null;

  if (minima && compararVersoes(atual, minima) < 0) {
    return { estado: "obrigatoria", versaoNova: manifesto.versao, minima };
  }
  if (compararVersoes(atual, manifesto.versao) < 0) {
    return { estado: "disponivel", versaoNova: manifesto.versao };
  }
  return { estado: "em_dia" };
}
