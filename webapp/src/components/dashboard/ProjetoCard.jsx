import Icon from "../Icon";
import flameIconSvg from "../../assets/icons/flame-icon.svg?raw";
import stairIconSvg from "../../assets/icons/stair-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-stroke-icon.svg?raw";
import { formatarDataCurta, tempoDecorrido } from "../../lib/format";

const CLASSE_POR_TOM = {
  green: "card-projeto-chip-green",
  amber: "card-projeto-chip-amber",
  red: "card-projeto-chip-red",
  neutral: "card-projeto-chip-neutral",
};

function Chip({ tom = "neutral", icone, children }) {
  return (
    <span className={`card-projeto-chip ${CLASSE_POR_TOM[tom]}`}>
      {icone && <Icon svg={icone} />}
      {children}
    </span>
  );
}

const COR_POR_TOM = { green: "#1D9E75", amber: "#c98a1a", red: "#C0152A" };

function CompletudeAnel({ pct, tom }) {
  const raio = 9.5;
  const perimetro = 2 * Math.PI * raio;
  return (
    <span className="card-projeto-anel" style={{ color: COR_POR_TOM[tom] }} title={`Completude: ${pct}%`}>
      <svg width="20" height="20" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r={raio} fill="none" stroke="currentColor" strokeOpacity=".2" strokeWidth="1.5" />
        <circle
          cx="12"
          cy="12"
          r={raio}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeDasharray={perimetro}
          strokeDashoffset={perimetro * (1 - pct / 100)}
        />
      </svg>
      {pct === 100 && <Icon svg={checkIconSvg} />}
    </span>
  );
}

/** Cartão de projeto — mesmo layout do site (ETOS.FireUtils), copiado de
 * src/pages/ProjetosPage.jsx (ProjectCard): anel de completude + nome,
 * chips de ocupação/risco/pavimentos, UF + tipo de projeto, e o rodapé
 * com as datas de criação/edição. `projeto` é o resumo montado por
 * lib/projetoDados.js (resumoProjeto). */
export default function ProjetoCard({ projeto, onClick }) {
  return (
    <button type="button" className="card-projeto" onClick={onClick}>
      <div className="card-projeto-topo">
        <CompletudeAnel pct={projeto.completude.pct} tom={projeto.completude.tom} />
        <h3 className="card-projeto-nome">{projeto.nome}</h3>
      </div>

      <div className="card-projeto-chips">
        <Chip tom="red">{projeto.ocupacao}</Chip>
        <Chip tom={projeto.risco.tom} icone={flameIconSvg}>
          {projeto.risco.label}
        </Chip>
        {projeto.pavimentosLabel && <Chip icone={stairIconSvg}>{projeto.pavimentosLabel}</Chip>}
      </div>

      <dl className="card-projeto-stats">
        <div>
          <dt>UF</dt>
          <dd>{projeto.uf || "—"}</dd>
        </div>
        <div>
          <dt>Projeto</dt>
          <dd>{projeto.tipoProjetoLabel}</dd>
        </div>
      </dl>

      <div className="card-projeto-rodape">
        <span>Criado em {formatarDataCurta(projeto.createdAt)}</span>
        <span>Editado {tempoDecorrido(projeto.updatedAt)}</span>
      </div>
    </button>
  );
}
