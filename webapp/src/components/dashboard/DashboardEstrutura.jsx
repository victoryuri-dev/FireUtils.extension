import ProjetoCabecalho from "./ProjetoCabecalho";
import Icon from "../Icon";
import { formatarArea, formatarMetros } from "../../lib/format";
import hidranteIconSvg from "../../assets/icons/hidrante-icon.svg?raw";
import saidaIconSvg from "../../assets/icons/saida-icon-placeholder.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

function CartaoDimensionamento({ titulo, iconeSvg, dimensionado }) {
  return (
    <div className="cartao-dimensionamento">
      <span className="cartao-dimensionamento-icone">
        <Icon svg={iconeSvg} />
      </span>
      <span className="cartao-dimensionamento-titulo">{titulo}</span>
      {dimensionado === undefined ? (
        <span className="status-dimensionamento status-carregando">Verificando...</span>
      ) : dimensionado ? (
        <span className="status-dimensionamento status-ok">
          <Icon svg={checkIconSvg} />
          Dimensionado
        </span>
      ) : (
        <span className="status-dimensionamento status-pendente">Pendente</span>
      )}
    </div>
  );
}

export default function DashboardEstrutura({ projeto, estrutura, estruturas, onTrocarEstrutura, dimensionamentos }) {
  return (
    <div className="dashboard-tela">
      <div className="dashboard-cabecalho-linha">
        <ProjetoCabecalho projeto={projeto} />
        {estruturas && estruturas.length > 1 && (
          <select
            className="seletor-estrutura"
            value={estrutura.id}
            onChange={(e) => onTrocarEstrutura(e.target.value)}
          >
            {estruturas.map((item) => (
              <option key={item.id} value={item.id}>
                {item.nome}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="grade-cartoes-info">
        <div className="cartao-info">
          <h3>Edificação</h3>
          <dl>
            <div>
              <dt>UF:</dt>
              <dd>{estrutura.uf || "—"}</dd>
            </div>
            <div>
              <dt>Área construída:</dt>
              <dd>{formatarArea(estrutura.area_construida)}</dd>
            </div>
            <div>
              <dt>Área terreno:</dt>
              <dd>{formatarArea(estrutura.area_terreno)}</dd>
            </div>
            <div>
              <dt>Altura piso a piso:</dt>
              <dd>{formatarMetros(estrutura.altura_piso_a_piso)}</dd>
            </div>
          </dl>
        </div>

        <div className="cartao-info">
          <h3>Classificação</h3>
          <dl>
            <div>
              <dt>Ocupação:</dt>
              <dd>{estrutura.ocupacao_label || estrutura.ocupacao_principal || "—"}</dd>
            </div>
            <div>
              <dt>Risco:</dt>
              <dd>{estrutura.risco_label || "—"}</dd>
            </div>
            <div>
              <dt>Altura:</dt>
              <dd>{estrutura.altura_label || "—"}</dd>
            </div>
          </dl>
        </div>
      </div>

      <p className="dashboard-subtitulo">Dimensionamentos</p>
      <div className="grade-dimensionamentos">
        <CartaoDimensionamento
          titulo="Sistema de Hidrantes"
          iconeSvg={hidranteIconSvg}
          dimensionado={dimensionamentos?.hidrantes}
        />
        <CartaoDimensionamento
          titulo="Saída de Emergência"
          iconeSvg={saidaIconSvg}
          dimensionado={dimensionamentos?.saidaEmergencia}
        />
      </div>
    </div>
  );
}
