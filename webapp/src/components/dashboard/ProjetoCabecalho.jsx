import Icon from "../Icon";
import linkIconSvg from "../../assets/icons/link-icon-placeholder.svg?raw";
import externalLinkIconSvg from "../../assets/icons/external-link-icon-placeholder.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

const SITE_URL = import.meta.env.VITE_SITE_URL || "";

/** Cabeçalho reaproveitado nas telas "Selecione uma estrutura" e Dashboard:
 * código público do projeto + status "Salvo" + nome com link pro site. */
export default function ProjetoCabecalho({ projeto }) {
  if (!projeto) return null;
  const urlProjeto = SITE_URL && projeto.codigo ? `${SITE_URL}/${projeto.codigo}` : null;

  return (
    <div className="projeto-cabecalho">
      <div className="projeto-cabecalho-linha">
        {projeto.codigo && (
          <span className="projeto-codigo">
            <Icon svg={linkIconSvg} />
            {projeto.codigo}
          </span>
        )}
        <span className="projeto-status-salvo">
          <Icon svg={checkIconSvg} />
          Salvo
        </span>
      </div>
      <h2 className="projeto-nome">
        {projeto.nome}
        {urlProjeto && (
          <a href={urlProjeto} target="_blank" rel="noreferrer" className="projeto-link-externo" title="Abrir no site">
            <Icon svg={externalLinkIconSvg} />
          </a>
        )}
      </h2>
    </div>
  );
}
