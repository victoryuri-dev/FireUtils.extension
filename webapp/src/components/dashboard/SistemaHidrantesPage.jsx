import { useEffect, useState } from "react";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import { dadosHidrantes } from "../../lib/projetoDados";
import { calcPotenciaBomba } from "../../lib/hidrantesCalc";
import hydrantIconSvg from "../../assets/icons/hydrant-icon.svg?raw";

function fmt(n, casas = 2) {
  return typeof n === "number" && !Number.isNaN(n) ? n.toFixed(casas) : "—";
}

function Cartao({ titulo, children }) {
  return (
    <div className="cartao-info">
      <h3>{titulo}</h3>
      {children}
    </div>
  );
}

function Linha({ label, valor }) {
  return (
    <div>
      <dt>{label}:</dt>
      <dd>{valor}</dd>
    </div>
  );
}

/**
 * Página "Sistema de Hidrantes" da dockpane — mostra o que está de fato
 * aplicado/calculado no Revit (Project Information + cache local do último
 * "Dimensionar Hidrantes", via GET_HIDRANTES_DIMENSIONAMENTO), não o que
 * está pendente no site: são fontes diferentes (ver
 * hidrantes_dimensionamento_bridge.py). A classificação pendente do site
 * aparece à parte, com o botão "Aplicar classificação no Revit" — depois
 * de aplicada, a seção "Sistema Classificado" abaixo reflete o que acabou
 * de ser gravado.
 *
 * A potência da bomba é sempre calculada aqui (JS, lib/hidrantesCalc.js) a
 * partir de Qt/Ht do ponto de operação + a eficiência informada — nunca no
 * Python. A eficiência é persistida em Project Information
 * (SET_HIDRANTES_EFICIENCIA_BOMBA) pra sobreviver fechar/reabrir o Revit.
 */
export default function SistemaHidrantesPage({ projeto, adicionarToast }) {
  const [carregando, setCarregando] = useState(true);
  const [resposta, setResposta] = useState(null);
  const [eficiencia, setEficiencia] = useState("");
  const [salvandoEficiencia, setSalvandoEficiencia] = useState(false);
  const [aplicando, setAplicando] = useState(false);

  function recarregar() {
    setCarregando(true);
    postToHost(BridgeMessageTypes.GET_HIDRANTES_DIMENSIONAMENTO, {});
  }

  useEffect(() => {
    recarregar();
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (mensagem.type === BridgeMessageTypes.HIDRANTES_DIMENSIONAMENTO) {
        setCarregando(false);
        setResposta(mensagem.payload || null);
        const eta = mensagem.payload?.bombaEficiencia;
        if (eta != null) setEficiencia(String(eta));
        return;
      }

      if (mensagem.type === BridgeMessageTypes.HIDRANTES_EFICIENCIA_SAVED) {
        setSalvandoEficiencia(false);
        const { ok, erro } = mensagem.payload || {};
        if (!ok) {
          adicionarToast?.({
            tipo: "erro",
            titulo: "Não foi possível salvar a eficiência",
            mensagem: erro,
            duracaoMs: 9000,
          });
        }
        return;
      }

      if (mensagem.type === BridgeMessageTypes.HIDRANTES_CLASSIFICACAO_SAVED) {
        setAplicando(false);
        const { ok } = mensagem.payload || {};
        // Sucesso muda o que está gravado no Project Information — recarrega
        // pra "Sistema Classificado" refletir a classificação recém-aplicada.
        if (ok) recarregar();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hidrantesSite = dadosHidrantes(projeto);

  function aplicarClassificacaoDoSite() {
    setAplicando(true);
    postToHost(BridgeMessageTypes.SET_HIDRANTES_CLASSIFICACAO, {
      tipo: hidrantesSite.tipo,
      tipoVariante: hidrantesSite.tipoVariante,
      rti: hidrantesSite.rti,
      metodoCalculo: hidrantesSite.metodoCalculo,
      succaoAltitude: hidrantesSite.succaoAltitude,
      succaoTemperatura: hidrantesSite.succaoTemperatura,
    });
    // Sem callback de conclusão aqui — o toast (App.jsx, HIDRANTES_CLASSIFICACAO_SAVED)
    // já avisa, e o próprio listener acima recarrega em caso de sucesso.
    setTimeout(() => setAplicando(false), 1500);
  }

  function salvarEficiencia() {
    const valor = parseFloat(eficiencia);
    if (!valor || valor <= 0) return;
    setSalvandoEficiencia(true);
    postToHost(BridgeMessageTypes.SET_HIDRANTES_EFICIENCIA_BOMBA, { eficiencia: valor });
  }

  const classificacao = resposta?.classificacao;
  const ponto = resposta?.pontoOperacao;
  const { potCv, potKw } = ponto
    ? calcPotenciaBomba(ponto.qt, ponto.ht, eficiencia)
    : { potCv: null, potKw: null };

  return (
    <div className="se-pagina">
      <div className="se-pagina-header">
        <span className="se-pagina-icone">
          <Icon svg={hydrantIconSvg} />
        </span>
        <h1>Sistema de Hidrantes</h1>
        <button type="button" className="se-botao se-pagina-header-botao" onClick={recarregar} disabled={carregando}>
          {carregando ? "Carregando…" : "Recarregar"}
        </button>
      </div>

      {hidrantesSite.tipo != null && (
        <div className="hid-secao">
          <Cartao titulo="Classificação Pendente (Site)">
            <dl>
              <Linha label="Tipo" valor={`Tipo ${hidrantesSite.tipo}`} />
              <Linha label="RTI" valor={hidrantesSite.rti != null ? `${hidrantesSite.rti} m³` : "—"} />
            </dl>
            <button
              type="button"
              className="botao"
              style={{ marginTop: 10 }}
              onClick={aplicarClassificacaoDoSite}
              disabled={aplicando}
            >
              {aplicando ? "Aplicando..." : "Aplicar classificação no Revit"}
            </button>
          </Cartao>
        </div>
      )}

      {carregando && !resposta && <p className="vazio">Carregando...</p>}

      {resposta && !resposta.ok && <p className="vazio">{resposta.erro}</p>}

      {resposta?.ok && classificacao && (
        <>
          <div className="hid-secao">
            <Cartao titulo="Sistema Classificado (aplicado no Revit)">
              <dl>
                <Linha
                  label="Tipo"
                  valor={`Tipo ${classificacao.tipo}${classificacao.descricao ? ` — ${classificacao.descricao}` : ""}`}
                />
                <Linha label="RTI" valor={classificacao.rti != null ? `${classificacao.rti} m³` : "—"} />
                <Linha label="Esguicho" valor={`DN${fmt(classificacao.esguicho_dn, 0)}`} />
                <Linha
                  label="Mangueira"
                  valor={`DN${fmt(classificacao.mang_dn, 0)} — ${fmt(classificacao.mang_comp, 0)} m`}
                />
                <Linha label="Expedições" valor={classificacao.expedicoes || "—"} />
                <Linha label="Vazão mínima" valor={`${fmt(classificacao.q_min, 0)} L/min`} />
                <Linha label="Pressão mínima" valor={`${fmt(classificacao.p_min, 0)} mca`} />
              </dl>
            </Cartao>
          </div>

          <p className="dashboard-subtitulo">Ponto de Operação do Sistema</p>
          {!ponto ? (
            <p className="vazio">
              {resposta.erroDimensionamento || 'Nenhum dimensionamento encontrado. Execute "Dimensionar Hidrantes" primeiro.'}
            </p>
          ) : (
            <div className="hid-grid-3">
              <Cartao titulo={`HD01${ponto.hidGoverna === "HD01" ? " — governante" : ""}`}>
                <dl>
                  <Linha label="Pressão" valor={`${fmt(ponto.pHd01)} mca`} />
                  <Linha label="Vazão" valor={`${fmt(ponto.qHd01)} L/min`} />
                </dl>
              </Cartao>
              <Cartao titulo={`HD02${ponto.hidGoverna === "HD02" ? " — governante" : ""}`}>
                <dl>
                  <Linha label="Pressão" valor={`${fmt(ponto.pHd02)} mca`} />
                  <Linha label="Vazão" valor={`${fmt(ponto.qHd02)} L/min`} />
                </dl>
              </Cartao>
              <Cartao titulo="Ponto de Operação (Bomba)">
                <dl>
                  <Linha label="Altura manométrica (Ht)" valor={`${fmt(ponto.ht)} mca`} />
                  <Linha label="Vazão total (Qt)" valor={`${fmt(ponto.qt)} L/min`} />
                </dl>
              </Cartao>
            </div>
          )}

          {ponto && (
            <div className="hid-secao">
              <p className="dashboard-subtitulo">Dimensionamento da Bomba de Incêndio</p>
              <Cartao titulo="Requisitos da Bomba">
                <div className="hid-eficiencia-linha">
                  <div className="hid-eficiencia-input">
                    <div className="se-label">Eficiência global (η)</div>
                    <input
                      className="se-input"
                      type="number"
                      min="1"
                      max="100"
                      step="1"
                      placeholder="ex.: 65"
                      value={eficiencia}
                      onChange={(e) => setEficiencia(e.target.value)}
                      onBlur={salvarEficiencia}
                      onKeyDown={(e) => e.key === "Enter" && salvarEficiencia()}
                    />
                  </div>
                  {salvandoEficiencia && <span className="hid-salvando">Salvando...</span>}
                </div>
                <dl>
                  <Linha label="Pressão" valor={`${fmt(ponto.ht)} mca`} />
                  <Linha label="Vazão" valor={`${fmt(ponto.qt)} L/min`} />
                  <Linha label="Eficiência" valor={eficiencia ? `${eficiencia}%` : "—"} />
                  <Linha
                    label="Potência mínima"
                    valor={potCv != null ? `${fmt(potCv)} cv (${fmt(potKw)} kW)` : "—"}
                  />
                </dl>
                {potCv == null && (
                  <div className="hid-aviso">Informe a eficiência da bomba pra calcular a potência mínima.</div>
                )}
              </Cartao>
            </div>
          )}
        </>
      )}
    </div>
  );
}
