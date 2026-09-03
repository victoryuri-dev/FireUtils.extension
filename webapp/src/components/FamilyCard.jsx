import { publicAssetUrl } from "../lib/supabaseClient";
import Icon from "./Icon";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";
import carregadoIconSvg from "../assets/icons/carregado-icon-placeholder.svg?raw";

function monograma(nome) {
  const palavras = nome
    .replace(/[-_]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (palavras.length === 0) return "?";
  if (palavras.length === 1) return palavras[0].slice(0, 2).toUpperCase();
  return (palavras[0][0] + palavras[1][0]).toUpperCase();
}

/**
 * Estados visuais (conforme fluxograma do mockup):
 *  - padrão: liso, sem badge.
 *  - hover (não selecionado, não carregada): checkbox vazio (contorno) —
 *    só CSS (:hover), não precisa de estado em React.
 *  - selecionada: borda vermelha + checkbox vermelho preenchido com check.
 *  - carregada no projeto ativo: ícone de download no canto — só
 *    indicador visual, clicar no card não faz nada com ele (não existe
 *    ação de "remover família do projeto" neste app).
 */
export default function FamilyCard({ familia, selecionado, carregada, onToggle }) {
  const thumbUrl = publicAssetUrl(familia.thumbnail_key);

  return (
    <div
      className={`cartao ${selecionado ? "selecionado" : ""} ${carregada ? "carregada" : ""}`}
      onClick={() => onToggle(familia)}
      role="button"
      tabIndex={0}
    >
      {carregada && (
        <div className="indicador-carregada" title="Já carregada no projeto">
          <Icon svg={carregadoIconSvg} />
        </div>
      )}
      <div className="checkbox-cartao">
        {selecionado && <Icon svg={checkIconSvg} />}
      </div>

      <div className="preview-tile">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt={familia.name}
            onError={(e) => {
              e.currentTarget.style.display = "none";
              e.currentTarget.nextSibling.style.display = "flex";
            }}
          />
        ) : null}
        <span className="monograma" style={{ display: thumbUrl ? "none" : "flex" }}>
          {monograma(familia.name)}
        </span>
      </div>
      <div className="nome">{familia.name}</div>
    </div>
  );
}
