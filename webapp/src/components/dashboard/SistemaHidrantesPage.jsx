import { useEffect, useMemo, useState } from "react";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import { salvarComRetry } from "../../lib/projectData";
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
 * Tipo/variante/RTI são a MESMA escolha que o site faz na Etapa 1
 * (Classificação do Sistema) — só editável nos dois lugares. Clicar aqui
 * grava em dois destinos, mas não os mesmos três campos nos dois: Project
 * Information recebe só o que "Dimensionar Hidrantes"/"Mapear Trechos" de
 * fato leem pra calcular (tipo, tipoVariante, método de cálculo, dados de
 * sucção — via SET_HIDRANTES_CLASSIFICACAO); RTI nunca vai pro Project
 * Information (o motor de cálculo nunca lê RTI de lá — é reservatório, não
 * rede hidráulica) e fica só no Supabase (dados.hidrantes.rti, via
 * salvarHidrantes() abaixo), mesmo lugar que tipo/tipoVariante TAMBÉM são
 * gravados (esses dois, nos dois destinos). Pra decidir o que mostrar
 * como "ativo" nas pills e no card "Sistema Classificado", o Supabase (o
 * que o site também vê) tem prioridade sobre o Project Information — que
 * pode estar desatualizado se a mudança veio do site e ainda não foi
 * reaplicada aqui.
 *
 * A potência da bomba é sempre calculada aqui (JS, lib/hidrantesCalc.js) a
 * partir de Qt/Ht do ponto de operação + a eficiência informada — nunca no
 * Python. Eficiência e potência adotada são gravadas direto no Supabase
 * (dados.hidrantes.bombaEficiencia/bombaPotenciaAdotada, via
 * lib/projectData.salvarComRetry — mesmo mecanismo de
 * SaidaEmergenciaPage.jsx), NÃO em Project Information: é o mesmo par de
 * campos que o site edita na Etapa 3 ("Dimensionamento da Bomba de
 * Incêndio"), então os dois lados precisam ler/escrever o mesmo lugar.
 */
export default function SistemaHidrantesPage({ projeto, estrutura, onProjetoAtualizado, adicionarToast }) {
  const [carregando, setCarregando] = useState(true);
  const [resposta, setResposta] = useState(null);
  // Valor inicial vem do Supabase (dados.hidrantes), não do Revit — mesmo
  // campo que o site preenche na Etapa 3. Lazy initializer: só lido uma vez
  // no mount; depois disso o próprio salvar() mantém local e Supabase em
  // sincronia.
  const [eficiencia, setEficiencia] = useState(() => {
    const v = dadosHidrantes(projeto).bombaEficiencia;
    return v != null ? String(v) : "";
  });
  const [salvandoEficiencia, setSalvandoEficiencia] = useState(false);
  // Potência realmente escolhida pro conjunto motobomba (catálogo do
  // fabricante só vem em potências padronizadas — quase nunca bate exato
  // com a potência mínima calculada) — mesmo esquema de sincronia direta
  // com o Supabase que a eficiência, acima.
  const [potenciaAdotada, setPotenciaAdotada] = useState(() => {
    const v = dadosHidrantes(projeto).bombaPotenciaAdotada;
    return v != null ? String(v) : "";
  });
  const [salvandoPotencia, setSalvandoPotencia] = useState(false);
  const [aplicando, setAplicando] = useState(false);
  // Seleção local de Tipo — null até o usuário clicar em algum; até lá, o
  // Tipo "efetivo" (pra saber se mostra pills de variante e qual marcar
  // como ativa) é o que está salvo no Supabase ou, na falta disso, o que
  // já está aplicado no Revit (classificacao.tipo) — ver tipoEfetivo abaixo.
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
  // site ainda não preencheu). tipo/tipoVariante já salvos no Supabase
  // (possivelmente escolhidos pelo site) alimentam o "tipo efetivo" abaixo.
  const { tipo: tipoSalvo, tipoVariante: varianteSalva, rti: rtiSalvo, succaoAltitude, succaoTemperatura } = dadosHidrantes(projeto);

  const classificacao = resposta?.classificacao;
  const ponto = resposta?.pontoOperacao;

  async function aplicar(tipo, rti, tipoVariante) {
    setAplicando(true);
    // RTI não vai pro Project Information — o motor de cálculo nunca lê
    // RTI de lá (dimensiona o reservatório, não a rede hidráulica). Só o
    // que "Dimensionar Hidrantes"/"Mapear Trechos" de fato consomem.
    postToHost(BridgeMessageTypes.SET_HIDRANTES_CLASSIFICACAO, {
      tipo,
      tipoVariante,
      metodoCalculo: normaHidrantesMA.REFERENCIA_PRESSAO_VAZAO,
      succaoAltitude,
      succaoTemperatura,
    });
    try {
      await salvarHidrantes({ tipo, tipoVariante, rti });
    } catch (ex) {
      adicionarToast?.({
        tipo: "erro",
        titulo: "Não foi possível sincronizar a classificação com o site",
        mensagem: ex.message,
        duracaoMs: 9000,
      });
    }
    setTimeout(() => setAplicando(false), 1500);
  }

  // Tipo efetivo pra decidir o que mostrar: a seleção local (clique ainda
  // não confirmado), senão o que está salvo no Supabase (a mesma escolha
  // que o site vê/edita), senão o que já está aplicado no Revit — mesmo
  // sem nenhum clique ainda, um Tipo com mais de uma variante (Tipo 4) já
  // mostra as pills de variante.
  const tipoEfetivo = tipoSelecionado ?? tipoSalvo ?? classificacao?.tipo ?? null;
  const variantesDoTipoEfetivo = tipoEfetivo ? normaHidrantesMA.TIPOS_SISTEMA[tipoEfetivo]?.variantes || [] : [];

  function rtiParaTipo(tipo) {
    return sugestao.opcoes.find((o) => o.tipo === tipo)?.rti ?? (tipoSalvo === tipo ? rtiSalvo : null);
  }

  function escolherTipo(opcao) {
    setTipoSelecionado(opcao.tipo);
    const variantes = normaHidrantesMA.TIPOS_SISTEMA[opcao.tipo]?.variantes || [];
    if (variantes.length <= 1) aplicar(opcao.tipo, opcao.rti, 0);
  }

  function escolherVariante(i) {
    aplicar(tipoEfetivo, rtiParaTipo(tipoEfetivo), i);
  }

  // Mescla `changes` em dados.hidrantes e grava direto no Supabase — mesmo
  // padrão de compare-and-swap com retry usado por SaidaEmergenciaPage.jsx
  // (lib/projectData.salvarComRetry), só que aqui não há canal Realtime pra
  // avisar outras sessões: a própria SET faz o dado convergir na próxima
  // leitura (o site já faz polling/refetch normal do projeto).
  async function salvarHidrantes(changes) {
    const { dados: novosDados, version: novaVersao } = await salvarComRetry(projeto.id, projeto, (dados) => ({
      ...dados,
      hidrantes: { ...(dados.hidrantes || {}), ...changes },
    }));
    onProjetoAtualizado?.({ ...projeto, dados: novosDados, version: novaVersao });
  }

  async function salvarEficiencia() {
    const valor = parseFloat(eficiencia);
    if (!valor || valor <= 0) return;
    setSalvandoEficiencia(true);
    try {
      await salvarHidrantes({ bombaEficiencia: valor });
    } catch (ex) {
      adicionarToast?.({
        tipo: "erro",
        titulo: "Não foi possível salvar a eficiência",
        mensagem: ex.message,
        duracaoMs: 9000,
      });
    } finally {
      setSalvandoEficiencia(false);
    }
  }

  async function salvarPotenciaAdotada() {
    const texto = potenciaAdotada.trim();
    const valor = texto === "" ? null : parseFloat(texto);
    if (valor != null && (Number.isNaN(valor) || valor <= 0)) return;
    setSalvandoPotencia(true);
    try {
      await salvarHidrantes({ bombaPotenciaAdotada: valor });
    } catch (ex) {
      adicionarToast?.({
        tipo: "erro",
        titulo: "Não foi possível salvar a potência adotada",
        mensagem: ex.message,
        duracaoMs: 9000,
      });
    } finally {
      setSalvandoPotencia(false);
    }
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
                      active={(tipoSalvo ?? classificacao?.tipo) === tipoEfetivo && (varianteSalva ?? classificacao?.variante_idx) === i}
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
                <Linha label="RTI" valor={rtiSalvo != null ? `${rtiSalvo} m³` : "—"} />
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
                    onCommit={salvarPotenciaAdotada}
                    sufixo="cv"
                    placeholder="ex.: 5"
                  />
                </Cartao>
              </div>
              {(salvandoEficiencia || salvandoPotencia) && <div className="hid-salvando">Salvando...</div>}
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
