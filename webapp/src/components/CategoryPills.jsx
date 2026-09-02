import { publicAssetUrl } from "../lib/supabaseClient";

const TODAS_ID = "__todas__";

export { TODAS_ID };

function IconePill({ iconKey, ativa, nomeCategoria }) {
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
          <IconePill iconKey={categoria.icon_key} ativa={categoria.id === categoriaAtual} nomeCategoria={categoria.name} />
          {categoria.name}
        </button>
      ))}
    </div>
  );
}
