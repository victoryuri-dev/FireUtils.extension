import { publicAssetUrl } from "../lib/supabaseClient";

function monograma(nome) {
  const palavras = nome
    .replace(/[-_]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (palavras.length === 0) return "?";
  if (palavras.length === 1) return palavras[0].slice(0, 2).toUpperCase();
  return (palavras[0][0] + palavras[1][0]).toUpperCase();
}

export default function FamilyCard({ familia, selecionado, onToggle }) {
  const thumbUrl = publicAssetUrl(familia.thumbnail_key);

  return (
    <div
      className={`cartao ${selecionado ? "selecionado" : ""}`}
      onClick={() => onToggle(familia)}
      role="button"
      tabIndex={0}
    >
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
      {selecionado && <div className="badge">✓</div>}
    </div>
  );
}
