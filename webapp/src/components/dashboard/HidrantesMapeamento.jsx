import Icon from "../Icon";
import Loader from "../Loader";
import { postToHost, BridgeMessageTypes } from "../../lib/bridge";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";
import { fmtNum } from "../../lib/numero";

// Título do aviso por categoria da falha de MAPEAR_TRECHOS (ver
// hidrantes_mapear_bridge.py). "inconsistencia" e "cancelado" não viram
// aviso de erro: um tem a lista na própria página, o outro foi escolha do
// usuário.
export const TITULO_FALHA_MAPEAMENTO = {
  requisito: "Falta um passo antes de mapear",
  norma: "Não foi possível ler a norma",
  licenca: "Módulo não contratado",
  servidor: "Não foi possível mapear",
};

function localizar(eids) {
  if (!eids?.length) return;
  postToHost(BridgeMessageTypes.SELECIONAR_TRECHO_HIDRANTE, { rota: eids });
}

function BotaoLocalizar({ eids }) {
  return eids?.length > 0 ? (
    <button type="button" className="hiddim-localizar-btn" onClick={() => localizar(eids)} title="Selecionar no Revit">
      <Icon svg={searchIconSvg} />
    </button>
  ) : (
    <span className="hiddim-td-vazio">—</span>
  );
}

function ListaInconsistencias({ itens }) {
  return (
    <div className="hiddim-tabela-wrap" style={{ marginTop: 10 }}>
      <table className="hiddim-tabela">
        <thead>
          <tr>
            <th className="hiddim-th hiddim-align-center" style={{ width: 40 }} />
            <th className="hiddim-th hiddim-align-left">Trecho</th>
            <th className="hiddim-th hiddim-align-left">Elemento</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((item, i) => (
            <tr key={i}>
              <td className="hiddim-td hiddim-align-center">
                <BotaoLocalizar eids={item.eids} />
              </td>
              <td className="hiddim-td hiddim-align-left">{item.trecho}</td>
              <td className="hiddim-td hiddim-align-left hiddim-cor-muted">{item.elemento}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabelaTrechos({ trechos }) {
  return (
    <div className="hiddim-tabela-wrap" style={{ marginTop: 10 }}>
      <table className="hiddim-tabela">
        <thead>
          <tr>
            <th className="hiddim-th hiddim-align-center" style={{ width: 40 }} />
            <th className="hiddim-th hiddim-align-left">Trecho</th>
            <th className="hiddim-th hiddim-align-right">Perda (mca)</th>
          </tr>
        </thead>
        <tbody>
          {trechos.map((t, i) => (
            <tr key={i}>
              <td className="hiddim-td hiddim-align-center">
                <BotaoLocalizar eids={t.eids} />
              </td>
              <td className="hiddim-td hiddim-align-left">{t.nome}</td>
              <td className="hiddim-td hiddim-align-right hiddim-mono">{fmtNum(t.perda, 2, "0")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * "Mapeamento da rede" — substitui o botão "Mapear trechos" da faixa do
 * Revit. O usuário clica na RTI e na bomba NO REVIT; enquanto isso a
 * dockpane diz o que fazer (`instrucao`). Estados:
 *   mapeando       esperando o usuário/o plugin (botão desligado)
 *   pendente       achou inconsistências que podem ser ignoradas
 *   inconsistencia a rede não fecha: lista do que corrigir, nada foi gravado
 *   trechos        resultado do último mapeamento (ou o salvo no projeto)
 */
export default function HidrantesMapeamento({
  mapeando, instrucao, pendente, inconsistencia, trechos, onMapear, onContinuar,
}) {
  const jaMapeado = trechos?.length > 0;

  return (
    <div className="cartao-info" style={{ marginBottom: 14 }}>
      <div className="se-pagina-header" style={{ marginBottom: 0 }}>
        <h3 style={{ margin: 0 }}>Mapeamento da Rede</h3>
        <button
          type="button"
          className="se-botao se-botao-accent se-pagina-header-botao"
          onClick={onMapear}
          disabled={mapeando}
        >
          {mapeando ? "Mapeando…" : jaMapeado ? "Mapear Novamente" : "Mapear Trechos"}
        </button>
      </div>

      {mapeando && (
        <div className="hid-aviso" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Loader size={16} />
          <span>{instrucao || "Preparando…"} (Esc no Revit cancela)</span>
        </div>
      )}

      {!mapeando && inconsistencia && (
        <div style={{ marginTop: 10 }}>
          <div className="hid-aviso">{inconsistencia.erro}</div>
          {inconsistencia.itens?.length > 0 && <ListaInconsistencias itens={inconsistencia.itens} />}
          <p className="hid-nota-aviso">
            Corrija a tubulação no Revit (o botão localiza cada ponto) e mapeie de novo.
          </p>
        </div>
      )}

      {!mapeando && pendente && (
        <div style={{ marginTop: 10 }}>
          <div className="hid-aviso">
            {pendente.grave
              ? "Há válvulas de hidrante que não chegam à bomba. Se ignorar, elas ficam de fora do ranking e do dimensionamento."
              : "Há pontos soltos na rede, mas todos os hidrantes foram alcançados. Confira se são ramais de propósito (teste de bomba, dreno)."}
          </div>
          <ListaInconsistencias itens={pendente.itens} />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="se-botao se-botao-accent" onClick={onContinuar}>
              Ignorar e continuar
            </button>
            <button type="button" className="se-botao" onClick={onMapear}>
              Corrigi, mapear de novo
            </button>
          </div>
        </div>
      )}

      {!mapeando && !pendente && !inconsistencia && jaMapeado && <TabelaTrechos trechos={trechos} />}

      {/* Mesma formatação da nota "Sempre que trocar o sistema…" do cartão de
          classificação (.hid-nota-aviso), no pé do cartão. */}
      <p className="hid-nota-aviso">
        {jaMapeado
          ? "Rede mapeada. Mapeie de novo se mudar a tubulação no Revit."
          : "Passo antes de dimensionar: clique na RTI e na bomba no Revit."}
      </p>
    </div>
  );
}
