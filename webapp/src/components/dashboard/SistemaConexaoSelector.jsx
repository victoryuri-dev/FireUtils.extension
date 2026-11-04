import { useEffect, useState } from "react";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";

// Diâmetros com tabela de Leq própria por sistema (ver leqConexoes.ts, lado
// motor) — fontes citadas (NFPA 13 x Victaulic 10.06) só cobrem essa faixa
// por enquanto. Fora dela a conexão usa uma estimativa genérica (L/D),
// igual pros dois sistemas, então não tem o que escolher aqui ainda.
const DIAMETROS_COM_TABELA = [32, 40, 50, 65];

const ROTULO_SISTEMA = { bsp: "BSP (roscado)", grooved: "Grooved (ranhurado)" };

function PillSistema({ active, onClick, children }) {
  return (
    <button type="button" className={`hid-pill ${active ? "hid-pill-ativa" : ""}`} onClick={onClick}>
      {children}
    </button>
  );
}

/**
 * Sistema de conexão (BSP roscado x Grooved ranhurado) do aço galvanizado,
 * POR DIÂMETRO — cotovelo/tê roscado e ranhurado têm Leq bem diferente pro
 * mesmo diâmetro, e isso não dá mais pra inferir da família do Revit (ver
 * get_tipo_conexao em rede.py). Escolha salva no Project Information do
 * projeto (sistema_conexao.py); lida pelo "Dimensionar Hidrantes" seguinte,
 * não precisa mapear/dimensionar de novo só por causa da leitura — mas o
 * dimensionamento já feito só reflete a troca depois de "Dimensionar
 * Novamente".
 */
export default function SistemaConexaoSelector({ adicionarToast }) {
  const [sistemaPorDiametro, setSistemaPorDiametro] = useState({});
  const [carregado, setCarregado] = useState(false);

  useEffect(() => {
    postToHost(BridgeMessageTypes.GET_SISTEMA_CONEXAO, {});
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (mensagem.type === BridgeMessageTypes.SISTEMA_CONEXAO) {
        const { ok, sistemaPorDiametro: salvo, erro } = mensagem.payload || {};
        setCarregado(true);
        if (!ok) {
          adicionarToast?.({ tipo: "erro", titulo: "Não foi possível ler o sistema de conexão", mensagem: erro, duracaoMs: 9000 });
          return;
        }
        setSistemaPorDiametro(salvo || {});
        return;
      }

      if (mensagem.type === BridgeMessageTypes.SISTEMA_CONEXAO_SAVED) {
        const { ok, sistemaPorDiametro: salvo, erro } = mensagem.payload || {};
        if (!ok) {
          adicionarToast?.({ tipo: "erro", titulo: "Não foi possível salvar o sistema de conexão", mensagem: erro, duracaoMs: 9000 });
          return;
        }
        setSistemaPorDiametro(salvo || {});
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function escolher(dn, sistema) {
    const atual = sistemaPorDiametro[String(dn)] || "bsp";
    if (atual === sistema) return;
    const novo = { ...sistemaPorDiametro, [String(dn)]: sistema };
    setSistemaPorDiametro(novo);
    postToHost(BridgeMessageTypes.SET_SISTEMA_CONEXAO, { sistemaPorDiametro: novo });
  }

  return (
    <div className="cartao-info" style={{ marginBottom: 14 }}>
      <h3 style={{ margin: 0 }}>Sistema de Conexão (Cotovelo/Tê)</h3>
      <p className="hid-secao-desc">
        Define a tabela de perda de carga de cotovelo e tê usada no cálculo, por diâmetro — aço galvanizado
        roscado (BSP) ou ranhurado (Grooved). Sem escolha, usa BSP.
      </p>
      {!carregado ? (
        <p className="vazio">Carregando…</p>
      ) : (
        <div className="hiddim-tabela-wrap" style={{ marginTop: 10 }}>
          <table className="hiddim-tabela">
            <thead>
              <tr>
                <th className="hiddim-th hiddim-align-left">DN (mm)</th>
                <th className="hiddim-th hiddim-align-left">Sistema</th>
              </tr>
            </thead>
            <tbody>
              {DIAMETROS_COM_TABELA.map((dn) => {
                const atual = sistemaPorDiametro[String(dn)] || "bsp";
                return (
                  <tr key={dn}>
                    <td className="hiddim-td hiddim-align-left">{dn}</td>
                    <td className="hiddim-td hiddim-align-left">
                      <div style={{ display: "flex", gap: 6 }}>
                        {Object.keys(ROTULO_SISTEMA).map((sistema) => (
                          <PillSistema key={sistema} active={atual === sistema} onClick={() => escolher(dn, sistema)}>
                            {ROTULO_SISTEMA[sistema]}
                          </PillSistema>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="hid-nota-aviso">
        Outros diâmetros ainda não têm tabela própria por sistema e usam uma estimativa genérica.
      </p>
    </div>
  );
}
