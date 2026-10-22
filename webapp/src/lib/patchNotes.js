import { compararVersoes, versaoValida } from "./versoes";

/**
 * As notas que interessam a quem vai atualizar: das versões MAIORES que a
 * instalada até a nova (inclusive), da mais nova para a mais antiga. Instalada
 * desconhecida ("dev", plugin antigo): só a nota da versão nova, para não
 * despejar o histórico inteiro.
 *
 * @param notas  PATCH_NOTES (data/patchNotes.js)
 */
export function notasDaAtualizacao(notas, instalada, nova) {
  if (!versaoValida(nova)) return [];
  const validas = notas.filter((n) => versaoValida(n.versao) && compararVersoes(n.versao, nova) <= 0);

  const doIntervalo = versaoValida(instalada)
    ? validas.filter((n) => compararVersoes(n.versao, instalada) > 0)
    : validas.filter((n) => compararVersoes(n.versao, nova) === 0);

  return [...doIntervalo].sort((a, b) => compararVersoes(b.versao, a.versao));
}
