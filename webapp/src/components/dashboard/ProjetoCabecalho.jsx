import Icon from "../Icon";
import linkIconSvg from "../../assets/icons/link-icon-placeholder.svg?raw";
import externalLinkIconSvg from "../../assets/icons/external-link-icon-placeholder.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";
import { urlProjeto as montarUrlProjeto } from "../../lib/site";

/** Cabeçalho reaproveitado nas telas "Selecione uma estrutura" e Dashboard:
 * id do projeto + status "Salvo" + nome com link pro site. `projeto` é a
 * linha crua da tabela `projetos` (id/nome/dados/updated_at, ver
 * lib/projectData.js) — não há uma coluna separada de "código público",
 * o `id` (text) já cumpre esse papel. */
export default function ProjetoCabecalho({ projeto }) {
  if (!projeto) return null;
  const link = montarUrlProjeto(projeto.id);

  return (
    <div className="projeto-cabecalho">
      <div className="projeto-cabecalho-linha">
        {projeto.id && (
          <span className="projeto-codigo">
            <Icon svg={linkIconSvg} />
            {projeto.id}
          </span>
        )}
        <span className="projeto-status-salvo">
          <Icon svg={checkIconSvg} />
          Salvo
        </span>
      </div>
      <h2 className="projeto-nome">
        {projeto.nome}
        {link && (
          <a href={link} target="_blank" rel="noreferrer" className="projeto-link-externo" title="Abrir no site">
            <Icon svg={externalLinkIconSvg} />
          </a>
        )}
      </h2>
    </div>
  );
}
