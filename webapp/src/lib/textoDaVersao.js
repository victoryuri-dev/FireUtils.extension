/** Texto da versão do plugin: "v3.1.0", "v3.2.1 · instalador 3.2.0" (atualizado
 * por pacote), "dev" (clone do repositório), "plugin anterior à 3.1" (sem
 * versão) ou "…" enquanto o Python não respondeu. */
export function textoDaVersao(versao, base) {
  if (versao === undefined) return "…";
  if (versao === null) return "plugin anterior à 3.1";
  if (versao === "dev") return "dev";
  return base && base !== versao ? `v${versao} · instalador ${base}` : `v${versao}`;
}
