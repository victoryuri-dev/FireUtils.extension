import ProjetoCabecalho from "./ProjetoCabecalho";
import SaidaEmergenciaPage from "./SaidaEmergenciaPage";
import Icon from "../Icon";
import { formatarArea, formatarMetros, formatarCargaIncendio } from "../../lib/format";
import hydrantIconSvg from "../../assets/icons/hydrant-icon.svg?raw";
import exitIconSvg from "../../assets/icons/exit-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

function CartaoDimensionamento({ titulo, iconeSvg, dimensionado, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} className={`cartao-dimensionamento ${onClick ? "cartao-dimensionamento-clicavel" : ""}`} onClick={onClick}>
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
    </Tag>
  );
}

export default function DashboardEstrutura({
  projeto,
  estrutura,
  dimensionamentos,
  adicionarToast,
  onAtualizarProjeto,
  modo = "dashboard",
  onAbrirSaidaEmergencia,
}) {
  // Saída de Emergência virou página própria (mesmo destino do atalho da
  // sidebar e deste cartão) — ver App.jsx/Sidebar.jsx. `modo` chega até
  // aqui (em vez de um estado local tipo `saidaAberta`) porque quem decide
  // a aba atual é o App, não este componente.
  if (modo === "saidas") {
    return (
      <SaidaEmergenciaPage
        projeto={projeto}
        estruturaId={estrutura.id}
        onProjetoAtualizado={onAtualizarProjeto}
        adicionarToast={adicionarToast}
      />
    );
  }

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
          iconeSvg={hydrantIconSvg}
          dimensionado={dimensionamentos?.hidrantes}
        />
        <CartaoDimensionamento
          titulo="Saída de Emergência"
          iconeSvg={exitIconSvg}
          dimensionado={dimensionamentos?.saidaEmergencia}
          onClick={onAbrirSaidaEmergencia}
        />
      </div>
    </div>
  );
}
