import ProjetoCabecalho from "./ProjetoCabecalho";
import Icon from "../Icon";
import { formatarArea, formatarMetros, formatarCargaIncendio } from "../../lib/format";
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

export default function DashboardEstrutura({ projeto, estrutura, dimensionamentos }) {
  return (
    <div className="dashboard-tela">
      <ProjetoCabecalho projeto={projeto} />

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
              <dd>{formatarArea(estrutura.areaConstruida)}</dd>
            </div>
            <div>
              <dt>Área terreno:</dt>
              <dd>{formatarArea(estrutura.areaTerreno)}</dd>
            </div>
            <div>
              <dt>Altura piso a piso:</dt>
              <dd>{formatarMetros(estrutura.alturaPisoAPiso)}</dd>
            </div>
          </dl>
        </div>

        <div className="cartao-info">
          <h3>Classificação</h3>
          <dl>
            <div>
              <dt>Ocupação:</dt>
              <dd>{estrutura.ocupacao || "—"}</dd>
            </div>
            <div>
              <dt>Carga de incêndio:</dt>
              <dd>{formatarCargaIncendio(estrutura.cargaIncendio)}</dd>
            </div>
            <div>
              <dt>Altura da edificação:</dt>
              <dd>{formatarMetros(estrutura.alturaEdificacao)}</dd>
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
