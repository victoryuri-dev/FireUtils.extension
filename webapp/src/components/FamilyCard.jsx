import { publicAssetUrl } from "../lib/supabaseClient";
import Icon from "./Icon";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";

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
 * Estados visuais do indicador no canto superior direito:
 *  - selecionada: borda vermelha + indicador vermelho preenchido com check.
 *  - padrão / hover: sem indicador; no hover aparece um contorno vazio
 *    (só CSS, sem estado em React).
 */
export default function FamilyCard({ familia, selecionado, onToggle }) {
  const thumbUrl = publicAssetUrl(familia.thumbnail_key);

  return (
    <div
      className={`cartao ${selecionado ? "selecionado" : ""}`}
      onClick={() => onToggle(familia)}
      role="button"
      tabIndex={0}
    >
      <div className="indicador-cartao">{selecionado && <Icon svg={checkIconSvg} />}</div>

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
