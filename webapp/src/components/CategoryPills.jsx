import { useCallback, useEffect, useRef, useState } from "react";
import { publicAssetUrl } from "../lib/supabaseClient";
import Icon from "./Icon";
import libraryIconSvg from "../assets/icons/library-icon.svg?raw";
import extintorIconSvg from "../assets/icons/extintor-icon.svg?raw";
import hidranteIconSvg from "../assets/icons/hidrante-icon.svg?raw";
import sireneIconSvg from "../assets/icons/sirene-icon.svg?raw";
import detectorIconSvg from "../assets/icons/detector-icon.svg?raw";
import chevronRightIconSvg from "../assets/icons/chevron-right-icon.svg?raw";

const TODAS_ID = "__todas__";

export { TODAS_ID };

// Ícones locais (SVG, cor controlada por CSS) pra quem já tem um desenhado
// no pacote entregue — as categorias sem entrada aqui caem no ícone remoto
// do Supabase (icon_key do catálogo) ou, na falta dele, no monograma.
const ICONES_LOCAIS_POR_CATEGORIA = {
  [TODAS_ID]: libraryIconSvg,
  "extintor-de-incendio": extintorIconSvg,
  "hidrantes": hidranteIconSvg,
  "alarme-de-incendio": sireneIconSvg,
  "detector-de-incendio": detectorIconSvg,
};

// Rótulos curtos do mockup — só cosméticos, o filtro continua usando
// categoria.id; category_id sem entrada aqui cai no nome cheio do catálogo.
export const ROTULO_CURTO_POR_CATEGORIA = {
  "extintor-de-incendio": "Extintor",
  "hidrantes": "Sistema de Hidrante",
  "alarme-de-incendio": "Alarme",
  "detector-de-incendio": "Detector",
};

// Não usada por enquanto — ícones dos pills desligados a pedido, texto puro
// até decidirmos o visual definitivo. Mantida pronta pra religar (só
// voltar a chamar <IconePill /> em CategoryPills abaixo).
// eslint-disable-next-line no-unused-vars
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

// Distância de rolagem por clique nas setas — "quase uma tela" do
// carrossel (não a largura toda), pra sempre sobrar um pedaço do pill
// seguinte visível como dica de que tem mais categoria pra esse lado.
const PASSO_ROLAGEM_PX = 180;

function Pill({ categoria, categoriaAtual, onSelect }) {
  return (
    <button
      type="button"
      className={`pill ${categoria.id === categoriaAtual ? "ativa" : ""}`}
      onClick={() => onSelect(categoria.id)}
    >
      {/* Ícones desligados por enquanto (ver IconePill) — só texto. */}
      {ROTULO_CURTO_POR_CATEGORIA[categoria.id] || categoria.name}
    </button>
  );
}

export default function CategoryPills({ categorias, todasIconKey, categoriaAtual, onSelect }) {
  const itens = [{ id: TODAS_ID, name: "Todas", icon_key: todasIconKey }, ...categorias];
  const trilhoRef = useRef(null);
  // Cada seta só existe quando há categoria escondida daquele lado.
  const [escondido, setEscondido] = useState({ esquerda: false, direita: false });

  const medir = useCallback(() => {
    const el = trilhoRef.current;
    if (!el) return;
    const esquerda = el.scrollLeft > 1;
    const direita = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setEscondido((atual) =>
      atual.esquerda === esquerda && atual.direita === direita ? atual : { esquerda, direita }
    );
  }, []);

  useEffect(() => {
    medir();
    const el = trilhoRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const observador = new ResizeObserver(medir);
    observador.observe(el);
    return () => observador.disconnect();
  }, [medir, categorias]);

  // Duas linhas flex empilhadas (cada botão larga só o que o próprio
  // texto pede) dentro do mesmo trilho rolável — ao contrário de um
  // grid de 2 linhas por coluna (tentativa anterior), aqui as duas
  // linhas não compartilham largura de coluna entre si: um pill curto
  // ("Todas") não fica esticado só porque o pill embaixo dele é mais
  // comprido ("Detecção de Incêndio").
  const metade = Math.ceil(itens.length / 2);
  const linha1 = itens.slice(0, metade);
  const linha2 = itens.slice(metade);

  function rolar(delta) {
    trilhoRef.current?.scrollBy({ left: delta, behavior: "smooth" });
  }

  return (
    <div className="pills-carrossel">
      {escondido.esquerda && (
        <button type="button" className="pills-seta pills-seta-esquerda" onClick={() => rolar(-PASSO_ROLAGEM_PX)} aria-label="Categorias anteriores">
          <Icon svg={chevronRightIconSvg} />
        </button>
      )}
      <div className="pills" ref={trilhoRef} onScroll={medir}>
        <div className="pills-linha">
          {linha1.map((categoria) => (
            <Pill key={categoria.id} categoria={categoria} categoriaAtual={categoriaAtual} onSelect={onSelect} />
          ))}
        </div>
        <div className="pills-linha">
          {linha2.map((categoria) => (
            <Pill key={categoria.id} categoria={categoria} categoriaAtual={categoriaAtual} onSelect={onSelect} />
          ))}
        </div>
      </div>
      {escondido.direita && (
        <button type="button" className="pills-seta pills-seta-direita" onClick={() => rolar(PASSO_ROLAGEM_PX)} aria-label="Próximas categorias">
          <Icon svg={chevronRightIconSvg} />
        </button>
      )}
    </div>
  );
}
