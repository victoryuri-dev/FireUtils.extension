import Icon from "../Icon";
import Loader from "../Loader";
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
 * RTI e bomba salvas no projeto: "Mapear Trechos" reaproveita as duas, sem
 * pedir o clique de novo. O usuário confere se continuam as mesmas (e
 * localiza no Revit) e troca só a que mudou.
 */
function ReferenciasSalvas({ referencias, atualizando, instrucao, popupAberto, desabilitado, onAtualizar }) {
  const linhas = ["rti", "bomba"].map((qual) => ({ qual, ref: referencias?.[qual] }));
  const familias = referencias?.familiasValvula || [];

  return (
    <div style={{ marginTop: 10 }}>
      <div className="hiddim-tabela-wrap">
        <table className="hiddim-tabela">
          <thead>
            <tr>
              <th className="hiddim-th hiddim-align-center" style={{ width: 40 }} />
              <th className="hiddim-th hiddim-align-left">Referência</th>
              <th className="hiddim-th hiddim-align-left">Elemento salvo</th>
              <th className="hiddim-th hiddim-align-center" />
            </tr>
          </thead>
          <tbody>
            {linhas.map(({ qual, ref }) => (
              <tr key={qual}>
                <td className="hiddim-td hiddim-align-center">
                  <BotaoLocalizar eids={ref?.existe ? ref.eids : null} />
                </td>
                <td className="hiddim-td hiddim-align-left">{NOME_REFERENCIA[qual]}</td>
                <td className="hiddim-td hiddim-align-left hiddim-cor-muted">
                  {!ref
                    ? "Não definida — será pedida no próximo mapeamento"
                    : ref.existe
                      ? ref.descricao
                      : `${ref.descricao || "Elemento"} (não existe mais no modelo)`}
                </td>
                <td className="hiddim-td hiddim-align-center">
                  <button
                    type="button"
                    className="se-botao"
                    onClick={() => onAtualizar(qual)}
                    disabled={desabilitado}
                  >
                    {atualizando === qual ? "Selecionando…" : ref ? "Atualizar" : "Definir"}
                  </button>
                </td>
              </tr>
            ))}
            {familias.length > 0 && (
              <tr>
                <td className="hiddim-td hiddim-align-center"><span className="hiddim-td-vazio">—</span></td>
                <td className="hiddim-td hiddim-align-left">Famílias da válvula de hidrante</td>
                <td className="hiddim-td hiddim-align-left hiddim-cor-muted" colSpan={2}>
                  {familias.join(", ")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {atualizando && !popupAberto && (
        <div className="hid-aviso" style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
          <Loader size={16} />
          <span>{instrucao || "Preparando…"} (Esc no Revit cancela)</span>
        </div>
      )}
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
  mapeando, instrucao, pendente, inconsistencia, onDimensionar, onContinuar,
  referencias, atualizandoReferencia, onAtualizarReferencia, popupAberto,
}) {
  return (
    <div className="cartao-info" style={{ marginBottom: 14 }}>
      <div className="se-pagina-header" style={{ marginBottom: 0 }}>
        <h3 style={{ margin: 0 }}>Referências</h3>
      </div>

      <ReferenciasSalvas
        referencias={referencias}
        atualizando={atualizandoReferencia}
        instrucao={instrucao}
        popupAberto={popupAberto}
        desabilitado={mapeando || !!atualizandoReferencia}
        onAtualizar={onAtualizarReferencia}
      />

      {mapeando && !popupAberto && (
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

      {/* Mesma formatação da nota "Sempre que trocar o sistema…" do cartão de
          classificação (.hid-nota-aviso), no pé do cartão. */}
      <p className="hid-nota-aviso">
        A RTI e a bomba são pedidas no Revit na primeira vez e depois ficam salvas. Ao dimensionar,
        a rede é mapeada de novo (válvulas, rotas e numeração dos hidrantes), então basta clicar em
        Dimensionar depois de qualquer mudança no modelo.
      </p>
    </div>
  );
}
