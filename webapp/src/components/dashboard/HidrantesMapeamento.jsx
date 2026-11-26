import Icon from "../Icon";
import InfoTip from "../InfoTip";
import { postToHost, BridgeMessageTypes } from "../../lib/bridge";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";

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

const NOME_REFERENCIA = { rti: "Reservatório (RTI)", bomba: "Bomba de incêndio" };

/**
 * Linha de uma referência (RTI ou bomba) salva no projeto: "Dimensionar"
 * reaproveita a referência, sem pedir o clique de novo. A linha inteira é
 * clicável e troca a referência no Revit; a lupa localiza o elemento
 * salvo sem acionar a troca. À direita, o estado (Identificado / Não
 * definido); no hover vira a ação ("Alterar referência" / "Definir
 * referência").
 */
function BoxReferencia({ qual, ref, atualizando, desabilitado, onAtualizar }) {
  const ativa = atualizando === qual;
  const encontrada = !!ref?.existe;
  const estado = !ref ? "Não definido" : !encontrada ? "Não encontrado" : "Identificado";
  const acao = ativa ? "Selecionando…" : ref ? "Alterar referência" : "Definir referência";

  function acionar() {
    if (!desabilitado) onAtualizar(qual);
  }

  return (
    <div
      role="button"
      tabIndex={desabilitado ? -1 : 0}
      aria-disabled={desabilitado}
      className={`hid-ref-box ${desabilitado ? "hid-ref-box-desabilitado" : ""} ${ativa ? "hid-ref-box-ativa" : ""}`}
      onClick={acionar}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          acionar();
        }
      }}
    >
      <span className="hid-ref-esq">
        {/* Não aciona a troca da referência ao localizar. */}
        <span className="hid-ref-lupa" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
          {encontrada && ref.eids?.length > 0 && <BotaoLocalizar eids={ref.eids} />}
        </span>
        <span className="hid-ref-rotulo">{NOME_REFERENCIA[qual]}</span>
      </span>
      <span className={`hid-ref-estado ${!ref || !encontrada ? "hid-ref-estado-alerta" : "hid-ref-estado-ok"} ${ativa ? "hid-ref-estado-ativa" : ""}`}>
        <span className="hid-ref-estado-texto">{ativa ? acao : estado}</span>
        {!ativa && <span className="hid-ref-estado-acao">{acao}</span>}
      </span>
    </div>
  );
}

function ReferenciasSalvas({ referencias, atualizando, desabilitado, onAtualizar }) {
  const familias = referencias?.familiasValvula || [];

  return (
    <div className="hid-ref-grade">
      {["rti", "bomba"].map((qual) => (
        <BoxReferencia
          key={qual}
          qual={qual}
          ref={referencias?.[qual]}
          atualizando={atualizando}
          desabilitado={desabilitado}
          onAtualizar={onAtualizar}
        />
      ))}
      {familias.length > 0 && (
        <div className="hid-ref-box hid-ref-box-fixa">
          <span className="hid-ref-esq">
            <span className="hid-ref-lupa" />
            <span className="hid-ref-rotulo">Família da válvula de hidrante</span>
          </span>
          <span className="hid-ref-familia">{familias.join(", ")}</span>
        </div>
      )}
    </div>
  );
}

/**
 * "Mapeamento da rede" — substitui o botão "Mapear trechos" da faixa do
 * Revit. O usuário clica na RTI e na bomba NO REVIT; enquanto isso a
 * dockpane abre um popup com o que fazer (HidrantesInstrucaoModal). Estados:
 *   mapeando       esperando o usuário/o plugin (botão desligado)
 *   pendente       achou inconsistências que podem ser ignoradas
 *   inconsistencia a rede não fecha: lista do que corrigir, nada foi gravado
 *   trechos        resultado do último mapeamento (ou o salvo no projeto)
 */
export default function HidrantesMapeamento({
  mapeando, pendente, inconsistencia, onDimensionar, onContinuar,
  referencias, atualizandoReferencia, onAtualizarReferencia,
}) {
  return (
    <div className="cartao-info" style={{ marginBottom: 14 }}>
      <div className="se-pagina-header" style={{ marginBottom: 0 }}>
        <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
          Referências
          <InfoTip
            align="start"
            text="Identifique os elementos essenciais para mapeamento e dimensionamento da rede de hidrantes."
          />
        </h3>
      </div>

      <ReferenciasSalvas
        referencias={referencias}
        atualizando={atualizandoReferencia}
        desabilitado={mapeando || !!atualizandoReferencia}
        onAtualizar={onAtualizarReferencia}
      />

      {!mapeando && inconsistencia && (
        <div style={{ marginTop: 10 }}>
          <div className="hid-aviso">{inconsistencia.erro}</div>
          {inconsistencia.itens?.length > 0 && <ListaInconsistencias itens={inconsistencia.itens} />}
          <p className="hid-nota-aviso">
            Corrija a tubulação no Revit (o botão localiza cada ponto) e dimensione de novo.
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
            <button type="button" className="se-botao" onClick={onDimensionar}>
              Corrigi, dimensionar de novo
            </button>
          </div>
        </div>
      )}

      {/* A lista de trechos/hidrantes (Trecho → Perda) que aparecia aqui foi
          removida: é a mesma verificação que "Verificação do Hidrante Mais
          Desfavorável" mostra depois de dimensionar — e dimensionar não
          trava mais por velocidade (ver motor-hidrantes), então essa
          segunda exibição sempre aparece. Mostrar as duas era repetir a
          mesma informação. */}

    </div>
  );
}
