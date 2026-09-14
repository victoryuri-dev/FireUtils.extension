import { useEffect, useMemo, useState } from "react";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import { dadosHidrantes, divisoesComCargaDaEstrutura, sistemasAtivos } from "../../lib/projetoDados";
import { calcPotenciaBomba } from "../../lib/hidrantesCalc";
import { sugerirClassificacao } from "../../lib/hidrantesClassificacao";
import * as normaHidrantesMA from "../../lib/normaHidrantesMA";
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

// Pressão + Vazão (ou qualquer par relacionado) na mesma linha, em vez de
// duas linhas dt/dd empilhadas — layout do card de ponto de operação.
function LinhaInline({ itens }) {
  return (
    <div className="hid-linha-inline">
      {itens.map((it, i) => (
        <span key={i}>
          <span className="hid-linha-inline-label">{it.label}:</span> <strong>{it.valor}</strong>
        </span>
      ))}
    </div>
  );
}

function Pill({ active, onClick, disabled, children }) {
  return (
    <button
      type="button"
      className={`hid-pill ${active ? "hid-pill-ativa" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

// Um valor só, em destaque — cada card de "Ponto de Operação"/"Dimensionamento
// da Bomba" mostra uma única grandeza, com o título do card (Cartao) como
// rótulo, em vez de repetir o rótulo dentro do corpo.
function ValorGrande({ valor, destaque }) {
  return <div className={`hid-valor-grande ${destaque ? "hid-valor-grande-destaque" : ""}`}>{valor}</div>;
}

// Mesmo lugar visual de ValorGrande, mas editável — eficiência e potência
// adotada são digitadas aqui, no próprio card do resultado.
function CampoNumero({ value, onChange, onCommit, sufixo, placeholder }) {
  return (
    <div className="hid-stat-input-linha">
      <input
        className="hid-stat-input"
        type="number"
        min="0"
        step="1"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        onBlur={onCommit}
        onKeyDown={(e) => e.key === "Enter" && onCommit?.()}
      />
      {sufixo && <span className="hid-stat-input-sufixo">{sufixo}</span>}
    </div>
  );
}

/**
 * Página "Sistema de Hidrantes" da dockpane — permite classificar o
 * sistema (Tabela 3, NT 22 CBMMA) direto aqui, com o MESMO método do site
 * (ver lib/hidrantesClassificacao.js — cópia fiel de
 * ETOS.FireUtils/src/data/hidrantes_calc.js), e mostra o que está de fato
 * aplicado/calculado no Revit (Project Information + cache local do
 * último "Dimensionar Hidrantes", via GET_HIDRANTES_DIMENSIONAMENTO).
 * Clicar num Tipo já aplica no Revit — sem botão "Aplicar" separado.
 *
 * A potência da bomba é sempre calculada aqui (JS, lib/hidrantesCalc.js) a
 * partir de Qt/Ht do ponto de operação + a eficiência informada — nunca no
 * Python. A eficiência é persistida em Project Information
 * (SET_HIDRANTES_EFICIENCIA_BOMBA) pra sobreviver fechar/reabrir o Revit.
 */
export default function SistemaHidrantesPage({ projeto, estrutura, adicionarToast }) {
  const [carregando, setCarregando] = useState(true);
  const [resposta, setResposta] = useState(null);
  const [eficiencia, setEficiencia] = useState("");
  const [salvandoEficiencia, setSalvandoEficiencia] = useState(false);
  // Potência realmente escolhida pro conjunto motobomba (catálogo do
  // fabricante só vem em potências padronizadas — quase nunca bate exato
  // com a potência mínima calculada) — só um campo local por enquanto,
  // sem persistir no Revit.
  const [potenciaAdotada, setPotenciaAdotada] = useState("");
  const [aplicando, setAplicando] = useState(false);
  // Seleção local de Tipo — null até o usuário clicar em algum; até lá, o
  // Tipo "efetivo" (pra saber se mostra pills de variante e qual marcar
  // como ativa) é o que já está aplicado no Revit (classificacao.tipo).
  const [tipoSelecionado, setTipoSelecionado] = useState(null);

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
        const { ok, erro } = mensagem.payload || {};
        if (!ok) {
          adicionarToast?.({
            tipo: "erro",
            titulo: "Não foi possível aplicar a classificação",
            mensagem: erro,
            duracaoMs: 9000,
          });
          return;
        }
        // Sucesso muda o que está gravado no Project Information — recarrega
        // pra "Sistema Classificado" refletir a classificação recém-aplicada.
        recarregar();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Classificação (Tabela 3) calculada aqui, com os mesmos dados que o site
  // usa (área da estrutura vinculada + ocupação/carga de incêndio dos
  // pavimentos + sprinklers) — sem depender do site pra essa decisão.
  const divisoesComCarga = useMemo(
    () => divisoesComCargaDaEstrutura(projeto, estrutura?.id),
    [projeto, estrutura?.id]
  );
  const temSprinklers = sistemasAtivos(projeto, estrutura?.id).sprinklers;
  const sugestao = useMemo(
    () => sugerirClassificacao(estrutura?.areaConstruida, divisoesComCarga, temSprinklers, normaHidrantesMA),
    [estrutura?.areaConstruida, divisoesComCarga, temSprinklers]
  );

  // Método de cálculo e dados de sucção (NPSH) não são escolha desta
  // página — método é fixo pela norma (REFERENCIA_PRESSAO_VAZAO) e a
  // sucção continua vindo do que o site já tem salvo (ou o padrão, se o
  // site ainda não preencheu).
  const { succaoAltitude, succaoTemperatura } = dadosHidrantes(projeto);

  const classificacao = resposta?.classificacao;
  const ponto = resposta?.pontoOperacao;

  function aplicar(tipo, rti, tipoVariante) {
    setAplicando(true);
    postToHost(BridgeMessageTypes.SET_HIDRANTES_CLASSIFICACAO, {
      tipo,
      tipoVariante,
      rti,
      metodoCalculo: normaHidrantesMA.REFERENCIA_PRESSAO_VAZAO,
      succaoAltitude,
      succaoTemperatura,
    });
    setTimeout(() => setAplicando(false), 1500);
  }

  // Tipo efetivo pra decidir o que mostrar: a seleção local, se houver, ou
  // o que já está aplicado no Revit — mesmo sem nenhum clique ainda, um
  // Tipo com mais de uma variante (Tipo 4) já mostra as pills de variante.
  const tipoEfetivo = tipoSelecionado ?? classificacao?.tipo ?? null;
  const variantesDoTipoEfetivo = tipoEfetivo ? normaHidrantesMA.TIPOS_SISTEMA[tipoEfetivo]?.variantes || [] : [];

  function rtiParaTipo(tipo) {
    return sugestao.opcoes.find((o) => o.tipo === tipo)?.rti ?? (classificacao?.tipo === tipo ? classificacao.rti : null);
  }

  function escolherTipo(opcao) {
    setTipoSelecionado(opcao.tipo);
    const variantes = normaHidrantesMA.TIPOS_SISTEMA[opcao.tipo]?.variantes || [];
    if (variantes.length <= 1) aplicar(opcao.tipo, opcao.rti, 0);
  }

  function escolherVariante(i) {
    aplicar(tipoEfetivo, rtiParaTipo(tipoEfetivo), i);
  }

  function salvarEficiencia() {
    const valor = parseFloat(eficiencia);
    if (!valor || valor <= 0) return;
    setSalvandoEficiencia(true);
    postToHost(BridgeMessageTypes.SET_HIDRANTES_EFICIENCIA_BOMBA, { eficiencia: valor });
  }

  // Só cv é mostrado (pedido explícito) — calcPotenciaBomba ainda devolve
  // kW junto, mas fica sem uso aqui.
  const { potCv } = ponto ? calcPotenciaBomba(ponto.qt, ponto.ht, eficiencia) : { potCv: null };

  return (
    <div className="se-pagina hid-pagina">
      <div className="se-pagina-header">
        <span className="se-pagina-icone">
          <Icon svg={hydrantIconSvg} />
        </span>
        <h1>Sistema de Hidrantes</h1>
        <button type="button" className="se-botao se-pagina-header-botao" onClick={recarregar} disabled={carregando}>
          {carregando ? "Carregando…" : "Recarregar"}
        </button>
      </div>

      <div className="hid-secao">
        <Cartao titulo="Escolha do Sistema">
          {sugestao.opcoes.length === 0 ? (
            <p className="vazio">
              Classificação automática não disponível — cadastre a ocupação e a carga de incêndio da estrutura no
              site.
            </p>
          ) : (
            <>
              <div className="hid-pills-linha">
                {sugestao.opcoes.map((op) => (
                  <Pill key={op.tipo} active={tipoEfetivo === op.tipo} onClick={() => escolherTipo(op)} disabled={aplicando}>
                    Tipo {op.tipo} — RTI {op.rti} m³
                  </Pill>
                ))}
              </div>
              {variantesDoTipoEfetivo.length > 1 && (
                <div className="hid-pills-linha" style={{ marginTop: 8 }}>
                  {variantesDoTipoEfetivo.map((v, i) => (
                    <Pill
                      key={i}
                      active={classificacao?.tipo === tipoEfetivo && classificacao?.variante_idx === i}
                      onClick={() => escolherVariante(i)}
                      disabled={aplicando}
                    >
                      Esguicho DN{v.esguicho} — mangueira DN{v.mangueiraDn} — {v.pressaoMin} mca
                    </Pill>
                  ))}
                </div>
              )}
              <p className="hid-nota-aviso">
                Sempre que trocar o sistema, execute "Dimensionar Hidrantes" novamente no Revit.
              </p>
            </>
          )}
        </Cartao>
      </div>

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
            <div className="hid-lista-vertical">
              <Cartao titulo="HD01 — 1º Hidrante Mais Desfavorável">
                <LinhaInline
                  itens={[
                    { label: "Pressão", valor: `${fmt(ponto.pHd01)} mca` },
                    { label: "Vazão", valor: `${fmt(ponto.qHd01)} L/min` },
                  ]}
                />
              </Cartao>
              <Cartao titulo="HD02 — 2º Hidrante Mais Desfavorável">
                <LinhaInline
                  itens={[
                    { label: "Pressão", valor: `${fmt(ponto.pHd02)} mca` },
                    { label: "Vazão", valor: `${fmt(ponto.qHd02)} L/min` },
                  ]}
                />
              </Cartao>
              <div className="hid-grid-2">
                <Cartao titulo="Altura Manométrica Total">
                  <ValorGrande valor={`${fmt(ponto.ht)} mca`} />
                </Cartao>
                <Cartao titulo="Vazão Total">
                  <ValorGrande valor={`${fmt(ponto.qt)} L/min`} />
                </Cartao>
              </div>
            </div>
          )}

          {ponto && (
            <div className="hid-secao">
              <p className="dashboard-subtitulo">Dimensionamento da Bomba de Incêndio</p>
              <div className="hid-grid-2" style={{ marginBottom: 12 }}>
                <Cartao titulo="Pressão">
                  <ValorGrande valor={`${fmt(ponto.ht)} mca`} />
                </Cartao>
                <Cartao titulo="Vazão">
                  <ValorGrande valor={`${fmt(ponto.qt)} L/min`} />
                </Cartao>
              </div>
              <div className="hid-grid-3">
                <Cartao titulo="Eficiência Global (η)">
                  <CampoNumero
                    value={eficiencia}
                    onChange={(e) => setEficiencia(e.target.value)}
                    onCommit={salvarEficiencia}
                    sufixo="%"
                    placeholder="ex.: 65"
                  />
                </Cartao>
                <Cartao titulo="Potência Mínima">
                  <ValorGrande valor={potCv != null ? `${fmt(potCv)} cv` : "—"} destaque />
                </Cartao>
                <Cartao titulo="Potência Adotada">
                  <CampoNumero
                    value={potenciaAdotada}
                    onChange={(e) => setPotenciaAdotada(e.target.value)}
                    sufixo="cv"
                    placeholder="ex.: 5"
                  />
                </Cartao>
              </div>
              {salvandoEficiencia && <div className="hid-salvando">Salvando...</div>}
              {potCv == null && (
                <div className="hid-aviso">Informe a eficiência da bomba pra calcular a potência mínima.</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
