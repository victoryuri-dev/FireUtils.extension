import { useEffect, useRef, useState } from "react";
import Icon from "../Icon";
import Loader from "../Loader";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import pencilIconSvg from "../../assets/icons/pencil-icon.svg?raw";
import stairIconSvg from "../../assets/icons/stair-icon.svg?raw";
import dashboardIconSvg from "../../assets/icons/dashboard-icon.svg?raw";
import linkIconSvg from "../../assets/icons/link-icon.svg?raw";

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
    icone: pencilIconSvg,
    pedeNiveis: false,
  },
  {
    modo: "niveis",
    titulo: "Identificar por nível",
    ajuda: "Todos os ambientes dos níveis que você escolher.",
    icone: stairIconSvg,
    pedeNiveis: true,
  },
  {
    modo: "todos",
    titulo: "Identificar todos sem ocupação",
    ajuda: "Todos os ambientes que ainda não têm ocupação.",
    icone: dashboardIconSvg,
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

function ModalOcupacao({ ferramenta, opcoes, onCancelar, onConfirmar }) {
  const [uso, setUso] = useState("");
  const [codigo, setCodigo] = useState("");
  const [niveis, setNiveis] = useState([]);

  const grupos = opcoes?.grupos || [];
  const grupo = grupos.find((g) => g.uso === uso) || grupos[0];
  const item = grupo?.itens.find((i) => i.codigo === codigo) || grupo?.itens[0];

  function alternarNivel(nome) {
    setNiveis((atuais) => (atuais.includes(nome) ? atuais.filter((n) => n !== nome) : [...atuais, nome]));
  }

  const podeConfirmar = !!item && (!ferramenta.pedeNiveis || niveis.length > 0);

  return (
    <div className="niveis-modal-overlay" onClick={onCancelar}>
      <div className="niveis-modal-caixa" onClick={(e) => e.stopPropagation()}>
        <div className="niveis-modal-header">
          <span className="niveis-modal-titulo">{ferramenta.titulo}</span>
        </div>

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

            <div className="saidas-ocup-campos">
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
                    <span>Notas específicas</span>
                    {item.notas.map((n, i) => (
                      <p key={i}>{n}</p>
                    ))}
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

        <div className="niveis-modal-rodape">
          <button type="button" className="se-botao" onClick={onCancelar}>
            Cancelar
          </button>
          <button
            type="button"
            className="se-botao se-botao-accent"
            disabled={!podeConfirmar}
            onClick={() => onConfirmar({ modo: ferramenta.modo, ocupacao: item.codigo, niveis })}
          >
            Identificar
          </button>
        </div>
      </div>
    </div>
  );
}

function Resultado({ r, onFechar }) {
  const erro = !r.ok ? r.erro : r.erroEnvio;
  return (
    <div className={`saidas-resultado ${erro ? "saidas-resultado-erro" : ""}`} role="status">
      <div className="saidas-resultado-texto">
        {!r.ok && <p>{r.erro}</p>}
        {r.ok && (
          <>
            <p>
              <strong>{r.acao === "sincronizar" ? "Ambientes sincronizados" : "Ambientes identificados"}</strong>
              {typeof r.ambientes === "number" && ` — ${r.ambientes} no Revit`}
            </p>
            {r.resumo && <p className="saidas-resultado-linhas">{r.resumo}</p>}
            {r.populacao &&
              (r.populacao.erro ? (
                <p>População não sincronizada: {r.populacao.erro}</p>
              ) : (
                <p>
                  {r.populacao.atualizados} ambiente(s) com população atualizada a partir do site.
                  {r.populacao.naoEncontrados > 0 &&
                    ` ${r.populacao.naoEncontrados} do site não foram encontrados neste modelo (apagados ou em outro arquivo).`}
                </p>
              ))}
            {r.populacaoManual?.length > 0 && (
              <p>
                {r.populacaoManual.length} ambiente(s) sem taxa por área: informe a população no parâmetro
                "População" do ambiente.
              </p>
            )}
          </>
        )}
      </div>
      <button type="button" className="se-botao" onClick={onFechar}>
        Ok
      </button>
    </div>
  );
}

/**
 * Botões das ferramentas de ocupação, no estilo dos cartões do Dashboard.
 * `onConcluido` é chamado quando uma ação termina sem erro (a página usa para
 * recarregar os ambientes que o plugin acabou de enviar ao site).
 */
export default function SaidasFerramentas({ onConcluido }) {
  const [opcoes, setOpcoes] = useState(null); // null = ainda não carregou
  const [ferramenta, setFerramenta] = useState(null);
  const [executando, setExecutando] = useState(null); // { acao, instrucao }
  const [resultado, setResultado] = useState(null);
  const concluidoRef = useRef(onConcluido);
  concluidoRef.current = onConcluido;

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
        setResultado(r);
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
    setResultado(null);
    setExecutando({ acao: "identificar", modo: pedido.modo, instrucao: "Gravando a ocupação nos ambientes…" });
    postToHost(BridgeMessageTypes.IDENTIFICAR_AMBIENTES, pedido);
  }

  function sincronizar() {
    setResultado(null);
    setExecutando({ acao: "sincronizar", instrucao: "Sincronizando com o site…" });
    postToHost(BridgeMessageTypes.SINCRONIZAR_AMBIENTES, {});
  }

  const ocupado = !!executando;

  return (
    <>
      <p className="dashboard-subtitulo">Ocupação e população</p>
      <div className="grade-dimensionamentos">
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
          icone={linkIconSvg}
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
      {resultado && <Resultado r={resultado} onFechar={() => setResultado(null)} />}

      {ferramenta && (
        <ModalOcupacao
          ferramenta={ferramenta}
          opcoes={opcoes}
          onCancelar={() => setFerramenta(null)}
          onConfirmar={confirmar}
        />
      )}
    </>
  );
}
