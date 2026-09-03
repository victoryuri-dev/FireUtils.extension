import { publicAssetUrl } from "../lib/supabaseClient";
import Icon from "./Icon";
import extintorIconSvg from "../assets/icons/extintor-icon.svg?raw";
import hidranteIconSvg from "../assets/icons/hidrante-icon.svg?raw";
import sireneIconSvg from "../assets/icons/sirene-icon.svg?raw";

const TODAS_ID = "__todas__";

export { TODAS_ID };

// Ícones locais (SVG, cor controlada por CSS) pra quem já tem um desenhado
// no pacote entregue — as categorias sem entrada aqui caem no ícone remoto
// do Supabase (icon_key do catálogo) ou, na falta dele, no monograma.
const ICONES_LOCAIS_POR_CATEGORIA = {
  "extintor-de-incendio": extintorIconSvg,
  "hidrantes": hidranteIconSvg,
  "alarme-de-incendio": sireneIconSvg,
};

function IconePill({ categoryId, iconKey, nomeCategoria }) {
  const svgLocal = ICONES_LOCAIS_POR_CATEGORIA[categoryId];
  if (svgLocal) {
    return <Icon svg={svgLocal} />;
  }

  const url = publicAssetUrl(iconKey);
  if (url) {
    return (
      <img
        src={url}
        alt=""
        onError={(e) => {
          // Sem imagem carregável (ex.: ainda não subiu pro Supabase) —
          // some com a tag <img> quebrada e deixa só o texto do pill.
          e.currentTarget.style.display = "none";
        }}
      />
    );
  }
  const letra = nomeCategoria ? nomeCategoria.trim()[0]?.toUpperCase() : "?";
  return <span className="icone-fallback">{letra}</span>;
}

export default function CategoryPills({ categorias, todasIconKey, categoriaAtual, onSelect }) {
  const itens = [{ id: TODAS_ID, name: "Todas", icon_key: todasIconKey }, ...categorias];

  return (
    <div className="pills">
      {itens.map((categoria) => (
        <button
          key={categoria.id}
          type="button"
          className={`pill ${categoria.id === categoriaAtual ? "ativa" : ""}`}
          onClick={() => onSelect(categoria.id)}
        >
          <IconePill categoryId={categoria.id} iconKey={categoria.icon_key} nomeCategoria={categoria.name} />
          {categoria.name}
        </button>
      ))}
    </div>
  );
}
