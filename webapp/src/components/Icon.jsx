/**
 * Renderiza um SVG local inline (em vez de <img src="...">) — só assim a
 * cor do ícone pode ser controlada via CSS (`color`), já que os arquivos em
 * src/assets/icons/ usam fill="currentColor". Um <img> carrega o SVG como
 * documento à parte e não herda `color` do CSS da página.
 */
export default function Icon({ svg, className, title }) {
  return (
    <span
      className={`icon ${className || ""}`}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : "true"}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
