// Marca animada (3 barras em cascata) usada em todo indicador de
// carregamento da dockpane — substitui o anel girando (.loading-spinner)
// e o texto solto "Carregando...". Sempre `fill="currentColor"`: a cor
// vem de fora via CSS `color` (herdada do texto ao redor, ou setada
// explicitamente), então o mesmo componente funciona em qualquer
// fundo/tema — preto, cinza, branco, vermelho etc.
export default function Loader({ size = 16, className = "" }) {
  return (
    <svg
      viewBox="0 0 168 216"
      style={{ height: size, width: size * (168 / 216) }}
      className={`loader-mark ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Carregando"
    >
      <path className="loader-bar loader-bar-3" d="M168 0V154.523H121.426L121.426 50.9454L168 0Z" fill="currentColor" />
      <path className="loader-bar loader-bar-2" d="M103.129 61.4769V216H58.2179L58.2178 112.422L103.129 61.4769Z" fill="currentColor" />
      <path className="loader-bar loader-bar-1" d="M44.9109 112.985H0V164.492L44.9109 112.985Z" fill="currentColor" />
    </svg>
  );
}
