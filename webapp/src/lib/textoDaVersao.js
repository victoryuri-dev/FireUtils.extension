/** Texto da versão do código do plugin: "v3.1.0", "dev" (clone do repositório),
 * "plugin anterior à 3.1" (sem versão) ou "…" enquanto o Python não respondeu.
 * `base` (versão do instalador) é opcional e hoje não é exibida na dockpane. */
export function textoDaVersao(versao, base) {
  if (versao === undefined) return "…";
  if (versao === null) return "plugin anterior à 3.1";
  if (versao === "dev") return "dev";
  return base && base !== versao ? `v${versao} · instalador ${base}` : `v${versao}`;
}
