import { useEffect, useRef, useState } from "react";
import Icon from "../Icon";
import Loader from "../Loader";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import { consumirFerramenta, observarFerramenta } from "../../lib/ferramentasFlutuantes";
import ocupacaoIconSvg from "../../assets/icons/ocupacao-icon.svg?raw";
import porNivelIconSvg from "../../assets/icons/pornivel-icon.svg?raw";
import todosIconSvg from "../../assets/icons/todos-icon.svg?raw";
import sincronizarIconSvg from "../../assets/icons/sincronizar-ambiente-icon.svg?raw";
import chevronDownIconSvg from "../../assets/icons/chevron-down-icon.svg?raw";
import chevronRightIconSvg from "../../assets/icons/chevron-right-icon.svg?raw";

// As quatro ferramentas de ocupação e população, ex-painel "Saídas" da faixa
// do Revit (ver saidas_ocupacao_bridge.py). Trocam dados com o site, então só
// existem aqui. Os três primeiros modos pedem uma ocupação (como o antigo
// formulário WPF: Grupo -> Tipo, com taxa e notas); "Por nível" pede também os
// níveis.
const FERRAMENTAS = [
  {
    modo: "selecao",
    titulo: "Identificar por ambiente",
    ajuda: "Você clica nos ambientes no Revit.",
    icone: ocupacaoIconSvg,
    pedeNiveis: false,
  },
  {
    modo: "niveis",
    titulo: "Identificar por nível",
    ajuda: "Todos os ambientes dos níveis que você escolher.",
    icone: porNivelIconSvg,
    pedeNiveis: true,
  },
  {
    modo: "todos",
    titulo: "Identificar todos sem ocupação",
    ajuda: "Todos os ambientes que ainda não têm ocupação.",
    icone: todosIconSvg,
    pedeNiveis: false,
  },
];

function Cartao({ titulo, icone, onClick, ocupado, desabilitado }) {
  return (
    <button
      type="button"
      className="cartao-dimensionamento cartao-dimensionamento-clicavel"
      onClick={onClick}
      disabled={desabilitado || ocupado}
    >
      <span className="cartao-dimensionamento-icone">
        <Icon svg={icone} />
      </span>
      <span className="cartao-dimensionamento-titulo">{titulo}</span>
      {ocupado && <span className="status-dimensionamento status-carregando">Em andamento…</span>}
    </button>
  );
}

function ModalOcupacao({ ferramenta, opcoes, estruturas, estruturaPadraoId, onCancelar, onConfirmar }) {
  const [uso, setUso] = useState("");
  const [codigo, setCodigo] = useState("");
  const [niveis, setNiveis] = useState([]);
  const [notasAbertas, setNotasAbertas] = useState(false);
  const [estruturaId, setEstruturaId] = useState(estruturaPadraoId || estruturas[0]?.id || "");
  const estrutura = estruturas.find((e) => e.id === estruturaId);

  const grupos = opcoes?.grupos || [];
  const grupo = grupos.find((g) => g.uso === uso) || grupos[0];
  const item = grupo?.itens.find((i) => i.codigo === codigo) || grupo?.itens[0];

  function alternarNivel(nome) {
    setNiveis((atuais) => (atuais.includes(nome) ? atuais.filter((n) => n !== nome) : [...atuais, nome]));
  }

  const podeConfirmar = !!item && !!estrutura && (!ferramenta.pedeNiveis || niveis.length > 0);

  return (
    <div className="niveis-modal-overlay" onClick={onCancelar}>
      <div className="niveis-modal-caixa" onClick={(e) => e.stopPropagation()}>
        <div className="niveis-modal-header">
          <span className="niveis-modal-titulo">{ferramenta.titulo}</span>
        </div>

        {/* Corpo rolável: cabeçalho e botões ficam fixos e o miolo rola quando
            não cabe na altura do painel. */}
        <div className="niveis-modal-corpo">
        {!opcoes ? (
          <div className="tela-carregando">
            <Loader size={32} />
          </div>
        ) : !opcoes.ok ? (
          <p className="vazio">{opcoes.erro}</p>
        ) : (
          <>
            <p className="niveis-modal-ajuda">
              {ferramenta.ajuda} Ocupação ({opcoes.estadoNome}):
            </p>
            <p className="niveis-modal-ajuda">
              Ambientes sem estrutura no parâmetro "Estrutura" recebem a estrutura escolhida; os que já têm mantêm a sua.
            </p>

            <div className="saidas-ocup-campos">
              <label>
                <span className="saidas-ocup-rotulo">Estrutura</span>
                <select className="se-select" value={estruturaId} onChange={(e) => setEstruturaId(e.target.value)}>
                  {estruturas.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.nome}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="saidas-ocup-rotulo">Grupo</span>
                <select
                  className="se-select"
                  value={grupo?.uso || ""}
                  onChange={(e) => {
                    setUso(e.target.value);
                    setCodigo("");
                  }}
                >
                  {grupos.map((g) => (
                    <option key={g.uso} value={g.uso}>
                      {g.uso}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="saidas-ocup-rotulo">Tipo</span>
                <select className="se-select" value={item?.codigo || ""} onChange={(e) => setCodigo(e.target.value)}>
                  {(grupo?.itens || []).map((i) => (
                    <option key={i.codigo} value={i.codigo}>
                      {i.descricao ? `${i.codigo}  —  ${i.descricao}` : i.codigo}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {item && (
              <div className="saidas-ocup-info">
                <div className="saidas-ocup-taxa">Taxa: {item.taxa}</div>
                <div className="saidas-ocup-caps">
                  <div><span>AD / UP</span><strong>{item.ad}</strong></div>
                  <div><span>ER / UP</span><strong>{item.er}</strong></div>
                  <div><span>PT / UP</span><strong>{item.pt}</strong></div>
                </div>
                {item.notas.length > 0 && (
                  <div className="saidas-ocup-notas">
                    <button
                      type="button"
                      className="saidas-ocup-notas-toggle"
                      onClick={() => setNotasAbertas((a) => !a)}
                      aria-expanded={notasAbertas}
                    >
                      <Icon svg={notasAbertas ? chevronDownIconSvg : chevronRightIconSvg} />
                      Notas específicas ({item.notas.length})
                    </button>
                    {notasAbertas && (
                      <div className="saidas-ocup-notas-corpo">
                        {item.notas.map((n, i) => (
                          <p key={i}>{n}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {ferramenta.pedeNiveis && (
              <div className="saidas-ocup-niveis">
                <span className="saidas-ocup-rotulo">Níveis</span>
                {opcoes.niveis.length === 0 && <p className="vazio">Nenhum nível no projeto.</p>}
                {opcoes.niveis.map((nome) => (
                  <label key={nome} className="saidas-ocup-nivel">
                    <input type="checkbox" checked={niveis.includes(nome)} onChange={() => alternarNivel(nome)} />
                    {nome}
                  </label>
                ))}
              </div>
            )}
          </>
        )}
        </div>

        <div className="niveis-modal-rodape">
          <button type="button" className="se-botao" onClick={onCancelar}>
            Cancelar
          </button>
          <button
            type="button"
            className="se-botao se-botao-accent"
            disabled={!podeConfirmar}
            onClick={() => onConfirmar({ modo: ferramenta.modo, ocupacao: item.codigo, estruturaNome: estrutura.nome, niveis })}
          >
            Identificar
          </button>
        </div>
      </div>
    </div>
  );
}

// Linhas do resumo em "deu certo" e "deu errado". O plugin novo já manda as
// duas listas; o antigo só manda `resumo` (texto), então separa por padrão.
function separarResumo(r) {
  if (Array.isArray(r.resumoOk) || Array.isArray(r.resumoFalhas)) {
    return { ok: r.resumoOk || [], falhas: r.resumoFalhas || [] };
  }
  const linhas = (r.resumo || "").split("\n").filter(Boolean);
  return {
    ok: linhas.filter((l) => /enviado\(s\)$/.test(l)),
    falhas: linhas.filter((l) => !/enviado\(s\)$/.test(l)),
  };
}

// Resultado de uma ação vira notificações: uma verde por estrutura que deu
// certo (com o detalhe por pavimento) e uma de erro por estrutura que falhou,
// mais uma de erro para as falhas gerais.
function notificarResultado(r, adicionarToast) {
  const rotulo = r.acao === "sincronizar" ? "sincronizar ambientes" : "identificar ambientes";
  const tituloFalha = `Falha ao ${rotulo}`;
  if (!r.ok) {
    adicionarToast?.({ tipo: "erro", titulo: tituloFalha, mensagem: r.erro, duracaoMs: 10000 });
    return;
  }

  const { ok, falhas } = separarResumo(r);
  const gerais = [];
  const porEstrutura = [];
  falhas.forEach((linha) => (/falha ao enviar/.test(linha) ? porEstrutura : gerais).push(linha));
  if (r.erroEnvio && !falhas.includes(r.erroEnvio)) gerais.push(r.erroEnvio);

  const populacaoOk = [];
  if (r.populacao) {
    if (r.populacao.erro) {
      gerais.push(`População não sincronizada: ${r.populacao.erro}`);
    } else {
      populacaoOk.push(`${r.populacao.atualizados} ambiente(s) com população atualizada a partir do site.`);
      if (r.populacao.naoEncontrados > 0) {
        gerais.push(
          `${r.populacao.naoEncontrados} ambiente(s) do site não foram encontrados neste modelo (apagados ou em outro arquivo).`
        );
      }
    }
  }
  if (r.populacaoManual?.length > 0) {
    gerais.push(
      `${r.populacaoManual.length} ambiente(s) sem taxa por área: informe a população no parâmetro "População" do ambiente.`
    );
  }

  const titulo = r.acao === "sincronizar" ? "Ambientes sincronizados" : "Ambientes identificados";
  ok.forEach((bloco) => adicionarToast?.({ tipo: "sucesso", titulo, mensagem: bloco, duracaoMs: 8000 }));
  if (populacaoOk.length > 0) {
    adicionarToast?.({ tipo: "sucesso", titulo: "População atualizada", mensagem: populacaoOk.join("\n"), duracaoMs: 8000 });
  }
  porEstrutura.forEach((linha) =>
    adicionarToast?.({ tipo: "erro", titulo: tituloFalha, mensagem: linha, duracaoMs: 12000 })
  );
  if (gerais.length > 0) {
    adicionarToast?.({ tipo: "erro", titulo: tituloFalha, mensagem: gerais.join("\n"), duracaoMs: 12000 });
  }
  if (ok.length === 0 && populacaoOk.length === 0 && porEstrutura.length === 0 && gerais.length === 0) {
    adicionarToast?.({ tipo: "sucesso", titulo, mensagem: r.resumo || undefined, duracaoMs: 6000 });
  }
}

/**
 * Botões das ferramentas de ocupação, no estilo dos cartões do Dashboard.
 * `onConcluido` é chamado quando uma ação termina sem erro (a página usa para
 * recarregar os ambientes que o plugin acabou de enviar ao site).
 */
export default function SaidasFerramentas({ onConcluido, estruturas = [], estruturaPadraoId, adicionarToast }) {
  const [opcoes, setOpcoes] = useState(null); // null = ainda não carregou
  const [ferramenta, setFerramenta] = useState(null);
  const [executando, setExecutando] = useState(null); // { acao, instrucao }
  const concluidoRef = useRef(onConcluido);
  concluidoRef.current = onConcluido;
  const toastRef = useRef(adicionarToast);
  toastRef.current = adicionarToast;

  useEffect(() => {
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;
      if (mensagem.type === BridgeMessageTypes.SAIDAS_OPCOES) {
        setOpcoes(mensagem.payload || { ok: false, erro: "Sem resposta do Revit." });
      } else if (mensagem.type === BridgeMessageTypes.SAIDAS_AMBIENTES_PROGRESSO) {
        setExecutando((atual) => (atual ? { ...atual, instrucao: mensagem.payload?.instrucao || "" } : atual));
      } else if (mensagem.type === BridgeMessageTypes.SAIDAS_AMBIENTES_RESULTADO) {
        const r = mensagem.payload || {};
        setExecutando(null);
        notificarResultado(r, toastRef.current);
        if (r.ok && !r.erroEnvio) concluidoRef.current?.();
      }
    });
  }, []);

  function abrir(f) {
    setFerramenta(f);
    // Recarrega a cada abertura: os níveis podem ter mudado no modelo.
    setOpcoes(null);
    postToHost(BridgeMessageTypes.GET_SAIDAS_OPCOES, {});
  }

  function confirmar(pedido) {
    setFerramenta(null);
    setExecutando({ acao: "identificar", modo: pedido.modo, instrucao: "Gravando a ocupação nos ambientes…" });
    postToHost(BridgeMessageTypes.IDENTIFICAR_AMBIENTES, pedido);
  }

  function sincronizar() {
    setExecutando({ acao: "sincronizar", instrucao: "Sincronizando com o site…" });
    postToHost(BridgeMessageTypes.SINCRONIZAR_AMBIENTES, {});
  }

  const ocupado = !!executando;

  // Cliques da barra flutuante (ferramentas_flutuantes.py) chegam como se o
  // usuário tivesse clicado no cartão. A ref aponta sempre para a versão mais
  // recente das funções acima (elas fecham sobre o estado atual) e o efeito
  // roda uma vez só: ao montar também consome o pedido que chegou antes.
  const executarPedidoRef = useRef(null);
  executarPedidoRef.current = () => {
    const acao = consumirFerramenta();
    if (!acao || ocupado) return;
    if (acao === "sincronizar") {
      sincronizar();
      return;
    }
    const f = FERRAMENTAS.find((item) => item.modo === acao);
    if (f) abrir(f);
  };
  useEffect(() => {
    const executar = () => executarPedidoRef.current?.();
    executar();
    return observarFerramenta(executar);
  }, []);

  return (
    <section className="saidas-secao">
      <p className="dashboard-subtitulo se-secao-titulo-pagina">Ocupação e população</p>
      <div className="saidas-grade">
        {FERRAMENTAS.map((f) => (
          <Cartao
            key={f.modo}
            titulo={f.titulo}
            icone={f.icone}
            onClick={() => abrir(f)}
            desabilitado={ocupado}
            ocupado={executando?.acao === "identificar" && executando.modo === f.modo}
          />
        ))}
        <Cartao
          titulo="Sincronizar ambientes"
          icone={sincronizarIconSvg}
          onClick={sincronizar}
          desabilitado={ocupado}
          ocupado={executando?.acao === "sincronizar"}
        />
      </div>

      {executando && (
        <div className="hid-aviso saidas-andamento">
          <Loader size={16} />
          <span>{executando.instrucao}</span>
        </div>
      )}

      {ferramenta && (
        <ModalOcupacao
          ferramenta={ferramenta}
          opcoes={opcoes}
          estruturas={estruturas}
          estruturaPadraoId={estruturaPadraoId}
          onCancelar={() => setFerramenta(null)}
          onConfirmar={confirmar}
        />
      )}
    </section>
  );
}
