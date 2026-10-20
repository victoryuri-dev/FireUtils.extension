import Icon from "../Icon";
import linkIconSvg from "../../assets/icons/link-icon.svg?raw";
import externalLinkIconSvg from "../../assets/icons/external-link-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";
import { urlProjeto as montarUrlProjeto } from "../../lib/site";

/** Cabeçalho reaproveitado nas telas "Selecione as estruturas" e Dashboard:
 * id do projeto + status "Salvo" + nome com link pro site. `projeto` é a
 * linha crua da tabela `projetos` (id/nome/dados/updated_at, ver
 * lib/projectData.js) — não há uma coluna separada de "código público",
 * o `id` (text) já cumpre esse papel. `estrutura` (opcional) é o painel já
 * derivado (lib/projetoDados.js:dashboardEstrutura) — só pra mostrar qual
 * estrutura está sendo vista agora, alinhado ao título; a tela "Selecione
 * as estruturas" não passa esse prop, já que ainda não há nenhuma
 * escolhida.
 *
 * `estruturasVinculadas` (opcional, 2+ itens): o arquivo Revit tem mais de
 * uma estrutura vinculada (ver Dashboard.jsx) — a tag vira um seletor pra
 * trocar qual delas o Dashboard está mostrando agora (`onTrocarEstrutura`),
 * só uma troca de tela, não manda SET_PROJECT_LINK de novo. */
export default function ProjetoCabecalho({ projeto, estrutura, estruturasVinculadas, onTrocarEstrutura }) {
  if (!projeto) return null;
  const link = montarUrlProjeto(projeto.id);
  const podeTrocar = estrutura && estruturasVinculadas && estruturasVinculadas.length > 1;

  return (
    <div className="projeto-cabecalho">
        {projeto.id && (
          <span className="projeto-codigo">
            <Icon svg={linkIconSvg} />
            {projeto.id}
          </span>
        )}
      <h2 className="projeto-nome">
        <div className="projeto-cabecalho-linha">
          {projeto.nome}
          <span className="projeto-status-salvo">
            <Icon svg={checkIconSvg} />
            Salvo
          </span>
        </div>
        {podeTrocar ? (
          <select
            className="projeto-estrutura-select"
            value={estrutura.id}
            onChange={(e) => onTrocarEstrutura(e.target.value)}
          >
            {estruturasVinculadas.map((e) => (
              <option key={e.id} value={e.id}>
                {e.nome}
              </option>
            ))}
          </select>
        ) : (
          estrutura?.nome && <span className="projeto-estrutura-tag">{estrutura.nome}</span>
        )}
        {link && (
          <a href={link} target="_blank" rel="noreferrer" className="projeto-link-externo" title="Abrir no site">
            <Icon svg={externalLinkIconSvg} />
          </a>
        )}
      </h2>
    </div>
  );
}
