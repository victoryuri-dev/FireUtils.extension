import Icon from "./Icon";
import infoIconSvg from "../assets/icons/info-icon.svg?raw";

/**
 * Indicador de conceito — ícone "i" que, no hover/foco, abre uma caixinha
 * com a definição do campo. Equivalente ao InfoTip do site
 * (ETOS.FireUtils, src/components/ui/InfoTip.jsx), só que com CSS puro
 * em vez de utilitários Tailwind (ver index.css, ".info-tip*").
 * `align` escolhe pra que lado a caixinha abre em relação ao ícone —
 * "end" evita que ela vaze pra fora da dockpane quando o ícone está perto
 * da borda direita (ex.: cabeçalho de coluna de tabela).
 */
export default function InfoTip({ text, align = "center" }) {
  return (
    <span className="info-tip" tabIndex={0} aria-label="Mais informações">
      <Icon svg={infoIconSvg} className="info-tip-icone" />
      <span className={`info-tip-balao info-tip-balao-${align}`} role="tooltip">
        {text}
      </span>
    </span>
  );
}
