import { publicAssetUrl } from "../lib/supabaseClient";
import Icon from "./Icon";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";
import carregadaIconSvg from "../assets/icons/pasta-icon.svg?raw";

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
 * Estados visuais (conforme fluxograma do mockup) — um único indicador no
 * canto superior direito, nunca dois ao mesmo tempo:
 *  - selecionada: borda vermelha + indicador vermelho preenchido com check
 *    (tem prioridade mesmo se a família já estiver carregada — permite
 *    selecionar de novo pra recarregar uma versão atualizada).
 *  - carregada no projeto ativo (e não selecionada): indicador preto —
 *    só visual, clicar no card não remove nem faz nada com o projeto.
 *  - padrão / hover: sem indicador; no hover aparece um contorno vazio
 *    (só CSS, sem estado em React).
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
      <div className="indicador-cartao">
        {selecionado ? (
          <Icon svg={checkIconSvg} />
        ) : carregada ? (
          <Icon svg={carregadaIconSvg} title="Já carregada no projeto" />
        ) : null}
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
