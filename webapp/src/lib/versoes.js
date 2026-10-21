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

// Pacote de atualização rápida (só código Python): o nome traz a menor versão de
// INSTALADOR que o aceita, para decidir sem baixar nada (ver plugin_pacote.py).
const NOME_DO_PACOTE = /^FireUtils-Pacote-(\d+(?:\.\d+){0,3})-base-(\d+(?:\.\d+){0,3})\.zip$/;

/**
 * A atualização a oferecer: a maior versão entre o último instalador e o último
 * PACOTE que serve a esta instalação (versão maior que a instalada, base de
 * instalador compatível, assinatura `.sig` presente, e plugin que sabe aplicar
 * pacotes). Empate: o pacote, que não exige fechar o Revit.
 *
 * @param nomes  nomes dos arquivos do bucket
 * @param instalada  versão instalada ("dev" ou inválida: só instalador)
 * @param base  versão do instalador de base (cai em `instalada` se faltar)
 * @param suportaPacote  o plugin instalado aplica pacotes
 * @returns {{tipo: "instalador"|"pacote", versao, arquivo, base?}|null}
 */
export function escolherAtualizacao(nomes, { instalada, base, suportaPacote }) {
  const instalador = escolherUltimaVersao(nomes);
  const candidatos = [];
  if (instalador) candidatos.push({ tipo: "instalador", ...instalador });

  if (suportaPacote && versaoValida(instalada)) {
    const baseEfetiva = versaoValida(base) ? base : instalada;
    for (const nome of nomes) {
      const achou = NOME_DO_PACOTE.exec(nome);
      if (!achou) continue;
      const [, versao, baseMinima] = achou;
      if (compararVersoes(versao, instalada) <= 0) continue;
      if (compararVersoes(baseMinima, baseEfetiva) > 0) continue;
      if (!nomes.includes(`${nome}.sig`)) continue;
      candidatos.push({ tipo: "pacote", versao, arquivo: nome, base: baseMinima });
    }
  }

  let melhor = null;
  for (const c of candidatos) {
    const cmp = melhor ? compararVersoes(c.versao, melhor.versao) : 1;
    if (cmp > 0 || (cmp === 0 && c.tipo === "pacote")) melhor = c;
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
