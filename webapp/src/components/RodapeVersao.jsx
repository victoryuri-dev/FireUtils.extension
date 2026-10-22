import Icon from "./Icon";
import logoSvg from "../assets/icons/fireutils-logo.svg?raw";

/** Texto da versão: "v3.1.0", "v3.2.1 · instalador 3.2.0" (plugin atualizado
 * por pacote), "dev" (clone do repositório) ou "plugin antigo" (sem versão). */
export function textoDaVersao(versao, base) {
  if (versao === undefined) return "…";
  if (versao === null) return "plugin anterior à 3.1";
  if (versao === "dev") return "dev";
  return base && base !== versao ? `v${versao} · instalador ${base}` : `v${versao}`;
}

/**
 * Rodapé de todas as páginas: logo pequena em branco e a versão do plugin
 * instalado (informada pelo Python junto das licenças). Serve para conferir,
 * em teste, qual versão está rodando sem mudar nada na tela.
 */
export default function RodapeVersao({ versao, base }) {
  return (
    <footer className="rodape-versao" title="Versão do plugin instalado">
      <Icon svg={logoSvg} />
      <span>Fire Utils {textoDaVersao(versao, base)}</span>
    </footer>
  );
}
