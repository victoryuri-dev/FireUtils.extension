/**
 * Versão do plugin instalado × versão publicada.
 *
 * A versão mais nova é a maior entre os instaladores do bucket privado
 * `plugin-releases` do Supabase (`FireUtils-Setup-X.Y.Z.exe`, nome que o
 * build.ps1 gera). Como a interface é publicada na hora (Vercel) e o plugin só
 * muda com um instalador novo, as duas podem ficar desencontradas — daí a
 * comparação aqui.
 */

/**
 * Menor versão do plugin que ESTA interface aceita, ou null se qualquer uma
 * serve. Fica aqui, no código da interface, porque é ela quem passa a exigir
 * algo do plugin (por exemplo, uma mensagem nova da bridge): a exigência sobe
 * no mesmo deploy que a cria. Quem estiver abaixo vê "Atualize o plugin" e
 * perde o acesso até atualizar — só aumente depois que o plugin novo já
 * estiver publicado e os clientes tiveram tempo de atualizar.
 */
export const PLUGIN_MINIMO = null;

const NOME_DO_INSTALADOR = /^FireUtils-Setup-(\d+(?:\.\d+){0,3})\.exe$/;

/**
 * A maior versão entre os nomes de arquivo do bucket. Só vale o padrão exato
 * `FireUtils-Setup-X.Y.Z.exe` — o manifest.json de uma versão anterior, rascunhos ("...-teste.exe") e
 * qualquer outro arquivo são ignorados, então subir algo de teste ali não
 * dispara aviso para ninguém. Devolve `{ versao, arquivo }` ou null.
 */
export function escolherUltimaVersao(nomes) {
  let melhor = null;
  for (const nome of nomes) {
    const achou = NOME_DO_INSTALADOR.exec(nome);
    if (!achou) continue;
    if (!melhor || compararVersoes(achou[1], melhor.versao) > 0) {
      melhor = { versao: achou[1], arquivo: nome };
    }
  }
  return melhor;
}

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
 * @param publicada  { versao } da última versão publicada, ou null (nada publicado)
 * @returns {{estado: "desconhecido"|"em_dia"|"disponivel"|"obrigatoria", versaoNova?: string, minima?: string}}
 *   - "obrigatoria": abaixo da `hostMinVersion` — esta interface não funciona direito
 *   - "disponivel":  há versão mais nova, mas a atual ainda serve
 */
export function avaliarVersao({ instalada, publicada, minima = PLUGIN_MINIMO }) {
  if (instalada === undefined) return { estado: "desconhecido" };
  if (!publicada || !versaoValida(publicada.versao)) return { estado: "desconhecido" };
  if (instalada === VERSAO_DEV) return { estado: "em_dia" };

  const atual = versaoValida(instalada) ? instalada : "0";

  if (versaoValida(minima) && compararVersoes(atual, minima) < 0) {
    return { estado: "obrigatoria", versaoNova: publicada.versao, minima };
  }
  if (compararVersoes(atual, publicada.versao) < 0) {
    return { estado: "disponivel", versaoNova: publicada.versao };
  }
  return { estado: "em_dia" };
}
