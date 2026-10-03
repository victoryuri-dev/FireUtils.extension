import Icon from "../Icon";
import checkStrokeIconSvg from "../../assets/icons/check-stroke-icon.svg?raw";
import { fmtNum } from "../../lib/numero";

/**
 * Etapa "Bomba de Incêndio" da dockpane — réplica da Etapa 3 do site
 * (ETOS.FireUtils, src/pages/medidas/HidrantesPage.jsx: componente `Bomba`
 * + src/components/hidrantes/BombaESuccaoForm.jsx: `SelecaoBombas`), em
 * CSS puro (ver App.css, "Bomba de Incêndio (HidrantesBomba.jsx)") no
 * lugar dos utilitários Tailwind de lá. Sucção da bomba (NPSH) fica de
 * fora — a dockpane não edita altitude/temperatura nesta página (ver
 * SistemaHidrantesPage.jsx: succaoAltitude/succaoTemperatura só são lidos
 * do que o site já tem salvo, pra aplicar a classificação).
 */
const ACIONAMENTOS_BOMBA = [
  { key: "eletrico", label: "Motor elétrico" },
  { key: "combustao", label: "Motor de combustão interna" },
];

const f2 = (n) => fmtNum(n, 2, "0");
const lpm = (m3h) => `${fmtNum((Number(m3h) * 1000) / 60, 1, "0")} L/min`;
const kpa = (mca) => `${fmtNum(Number(mca) * 9.80665, 1, "0")} kPa`;

function ValorOperacao({ rotulo, valor, unidade, conversao }) {
  return (
    <div className="hid-ponto-operacao-col">
      <div className="hid-ponto-operacao-label">{rotulo}</div>
      <div className="hid-ponto-operacao-linha">
        <span className="hid-ponto-operacao-valor">{valor}</span>
        <span className="hid-ponto-operacao-unidade">{unidade}</span>
        {conversao && <span className="hid-ponto-operacao-unidade">· {conversao}</span>}
      </div>
    </div>
  );
}

// Só os valores que o RT leva pro catálogo do fabricante — mesmo recorte
// do site (Qt/Ht já aparecem com o cálculo completo na etapa anterior).
function PontoDeOperacao({ qt, ht }) {
  const qtM3h = qt != null ? (qt / 1000) * 60 : null;
  return (
    <div className="hid-secao">
      <p className="dashboard-subtitulo">Ponto de Operação do Sistema</p>
      <p className="hid-secao-desc">Vazão e altura manométrica que a bomba deve atender.</p>
      <div className="hid-ponto-operacao">
        <ValorOperacao
          rotulo="Vazão (Q)"
          valor={qtM3h != null ? f2(qtM3h) : "—"}
          unidade="m³/h"
          conversao={qt != null ? `${f2(qt)} L/min` : null}
        />
        <ValorOperacao
          rotulo="Altura Manométrica (Hm)"
          valor={ht != null ? f2(ht) : "—"}
          unidade="mca"
          conversao={ht != null ? `${fmtNum(ht * 9.80665, 1)} kPa` : null}
        />
      </div>
    </div>
  );
}

function CartaoBomba({ titulo, descricao, checked, onChange, bloqueado }) {
  return (
    <button
      type="button"
      className={`hid-bomba-cartao ${checked ? "hid-bomba-cartao-ativa" : ""}`}
      onClick={() => onChange(!checked)}
      disabled={bloqueado}
    >
      <span className="hid-bomba-cartao-textos">
        <span className="hid-bomba-cartao-titulo">{titulo}</span>
        {descricao && <span className="hid-bomba-cartao-desc">{descricao}</span>}
      </span>
      <span className={`hid-bomba-check ${checked ? "hid-bomba-check-ativo" : ""}`}>
        {checked && <Icon svg={checkStrokeIconSvg} />}
      </span>
    </button>
  );
}

function Acionamento({ valor, onChange }) {
  return (
    <div>
      <div className="hid-espec-label">Tipo de Acionamento</div>
      <div className="hid-acionamento-lista">
        {ACIONAMENTOS_BOMBA.map((op) => (
          <button
            key={op.key}
            type="button"
            className={`hid-acionamento-pill ${valor === op.key ? "hid-acionamento-pill-ativa" : ""}`}
            onClick={() => onChange(op.key)}
          >
            {op.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Dado({ rotulo, valor, unidade, tom }) {
  return (
    <div>
      <div className="hid-espec-label">{rotulo}</div>
      <div className={`hid-dado-valor ${tom ? `hid-dado-valor-${tom}` : ""}`}>
        <span>{valor}</span>
        {unidade && <span className="hid-dado-unidade">{unidade}</span>}
      </div>
    </div>
  );
}

function Campo({ rotulo, value, onChange, onCommit, sufixo, placeholder }) {
  return (
    <div>
      <div className="hid-espec-label">{rotulo}</div>
      <div className="hid-campo-input-wrap">
        <input
          type="number"
          className="se-input hid-campo-input"
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          onBlur={onCommit}
          onKeyDown={(e) => e.key === "Enter" && onCommit?.()}
        />
        {sufixo && <span className="hid-campo-input-sufixo">{sufixo}</span>}
      </div>
    </div>
  );
}

function EspecBomba({ children }) {
  return (
    <div className="hid-espec">
      <div className="hid-espec-titulo">Especificações</div>
      <div className="hid-espec-corpo">{children}</div>
    </div>
  );
}

function BombasDoSistema({
  qt,
  ht,
  potCv,
  campoEficiencia,
  campoPotenciaAdotada,
  bombaExiste,
  onToggleBombaExiste,
  bombaAcionamento,
  onChangeBombaAcionamento,
  bombaReserva,
  onToggleBombaReserva,
  bombaReservaAcionamento,
  onChangeBombaReservaAcionamento,
  bombaJockey,
  onToggleBombaJockey,
  campoJockeyVazao,
  campoJockeyPressao,
  campoJockeyPotencia,
}) {
  const reservaAtiva = bombaExiste && bombaReserva;
  const jockeyAtiva = bombaExiste && bombaJockey;
  const qtM3h = qt != null ? (qt / 1000) * 60 : null;

  return (
    <div className="hid-secao">
      <p className="dashboard-subtitulo">Bombas do Sistema</p>
      <p className="hid-secao-desc">Ative as bombas que a casa de bombas terá; a especificação de cada uma aparece logo abaixo.</p>

      <div className="hid-bomba-grid">
        <div className="hid-bomba-coluna">
          <CartaoBomba titulo="Bomba principal" descricao="Bomba de recalque do sistema" checked={bombaExiste} onChange={onToggleBombaExiste} />
          {bombaExiste && (
            <EspecBomba>
              <Acionamento valor={bombaAcionamento} onChange={onChangeBombaAcionamento} />
              <Dado rotulo="Vazão" valor={qtM3h != null ? f2(qtM3h) : "—"} unidade={qtM3h != null ? `m³/h · ${lpm(qtM3h)}` : ""} />
              <Dado rotulo="Pressão" valor={ht != null ? f2(ht) : "—"} unidade={ht != null ? `mca · ${kpa(ht)}` : ""} />
              <Campo rotulo="Eficiência Global (η)" sufixo="%" placeholder="ex.: 65" {...campoEficiencia} />
              <Dado rotulo="Potência Calculada" valor={potCv != null ? f2(potCv) : "—"} unidade={potCv != null ? "cv" : "informe a eficiência"} tom={potCv == null ? "amber" : undefined} />
              <Campo rotulo="Potência Adotada" sufixo="cv" placeholder="ex.: 5" {...campoPotenciaAdotada} />
            </EspecBomba>
          )}
        </div>

        <div className="hid-bomba-coluna">
          <CartaoBomba
            titulo="Bomba reserva"
            descricao="Mesmas características da principal"
            checked={reservaAtiva}
            onChange={onToggleBombaReserva}
            bloqueado={!bombaExiste}
          />
          {reservaAtiva && (
            <EspecBomba>
              <Acionamento valor={bombaReservaAcionamento} onChange={onChangeBombaReservaAcionamento} />
              <Dado rotulo="Vazão" valor={qtM3h != null ? f2(qtM3h) : "—"} unidade={qtM3h != null ? `m³/h · ${lpm(qtM3h)}` : ""} />
              <Dado rotulo="Pressão" valor={ht != null ? f2(ht) : "—"} unidade={ht != null ? `mca · ${kpa(ht)}` : ""} />
              <Dado rotulo="Eficiência Global (η)" valor={campoEficiencia.value || "—"} unidade={campoEficiencia.value ? "%" : ""} />
              <Dado rotulo="Potência" valor={campoPotenciaAdotada.value || "—"} unidade={campoPotenciaAdotada.value ? "cv" : ""} />
            </EspecBomba>
          )}
        </div>

        <div className="hid-bomba-coluna">
          <CartaoBomba titulo="Bomba jockey" descricao="Pressurização da rede" checked={jockeyAtiva} onChange={onToggleBombaJockey} bloqueado={!bombaExiste} />
          {jockeyAtiva && (
            <EspecBomba>
              <Campo rotulo="Vazão" sufixo="L/min" placeholder="ex.: 50" {...campoJockeyVazao} />
              <Campo rotulo="Pressão" sufixo="mca" placeholder="ex.: 40" {...campoJockeyPressao} />
              <Campo rotulo="Potência" sufixo="cv" placeholder="ex.: 2" {...campoJockeyPotencia} />
            </EspecBomba>
          )}
        </div>
      </div>
    </div>
  );
}

export default function HidrantesBomba(props) {
  const { qt, ht } = props;
  return (
    <>
      <PontoDeOperacao qt={qt} ht={ht} />
      <BombasDoSistema {...props} />
    </>
  );
}
