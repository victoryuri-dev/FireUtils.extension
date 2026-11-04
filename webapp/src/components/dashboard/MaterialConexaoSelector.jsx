import { useEffect, useState } from "react";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";

// Mesmas chaves curtas que hazen_c usa no perfil normativo (ver
// ALIAS_MATERIAL_TUBULACAO em perfil.ts, ETOS.FireUtils / MATERIAIS_VALIDOS
// em material_conexao.py) — evita qualquer tradução de chave no caminho
// até o motor. Rótulos copiados do catálogo do site
// (src/data/hidrantesCatalogos.js, ETOS.FireUtils).
const MATERIAIS = [
  { key: "ff_sem_revest", label: "Ferro fundido ou dúctil sem revestimento interno" },
  { key: "aco_preto_seco", label: "Aço preto (sistema de tubo seco)" },
  { key: "aco_preto_molhado", label: "Aço preto (sistema de tubo molhado)" },
  { key: "galvanizado", label: "Galvanizado" },
  { key: "plastico", label: "Plástico (PVC/PEAD)" },
  { key: "ff_revest_cimento", label: "Ferro fundido ou dúctil com revestimento interno de cimento" },
  { key: "cobre", label: "Cobre" },
];

const ROTULO_SISTEMA = { bsp: "BSP (roscado)", grooved: "Grooved (ranhurado)" };

const NOME_ETAPA = {
  t1: "Sucção (RTI → Bomba)",
  t2: "Recalque (Bomba → Ponto A)",
  t3: "Ramal do hidrante mais desfavorável",
  t4: "Ramal do 2º hidrante mais desfavorável",
};

const ETAPAS = ["t1", "t2", "t3", "t4"];

function PillSistema({ active, onClick, children }) {
  return (
    <button type="button" className={`hid-pill ${active ? "hid-pill-ativa" : ""}`} onClick={onClick}>
      {children}
    </button>
  );
}

function rotuloPipeType(grupo) {
  const diametros = (grupo.diametros || []).map((d) => `DN${Math.round(d)}`).join(", ");
  const nome = grupo.nome || "Tipo de tubo não identificado";
  return diametros ? `${nome} (${diametros})` : nome;
}

/**
 * Material da tubulação + sistema de conexão (BSP x Grooved), escolhidos
 * JUNTOS, por (etapa, tipo de tubo detectado no Revit) — um mesmo trecho
 * (RTI-Bomba, Bomba-Ponto A, ...) pode ter mais de um PipeType ao longo do
 * seu comprimento (troca de material no meio do trecho), e cada um precisa
 * da própria escolha. As combinações (quais tipos de tubo existem em cada
 * etapa) vêm do último "Mapear Trechos" — `pipeTypesPorEtapa` (prop),
 * populado ao vivo pelo resultado do mapeamento ou, depois de reabrir o
 * projeto, pelo cache lido em GET_HIDRANTES_DIMENSIONAMENTO. O componente
 * pai (SistemaHidrantesPage) só o renderiza depois de um mapeamento
 * bem-sucedido (mapeamentoOk) — antes disso ele fica oculto, não aparece
 * nem com um placeholder.
 *
 * Escolha salva no Project Information do projeto
 * (material_conexao.py); lida pelo "Dimensionar Hidrantes" seguinte — um
 * dimensionamento já feito só reflete a troca depois de "Dimensionar
 * Novamente".
 */
export default function MaterialConexaoSelector({ pipeTypesPorEtapa, adicionarToast }) {
  const [porEtapa, setPorEtapa] = useState({});
  const [carregado, setCarregado] = useState(false);

  useEffect(() => {
    postToHost(BridgeMessageTypes.GET_MATERIAL_CONEXAO, {});
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (mensagem.type === BridgeMessageTypes.MATERIAL_CONEXAO) {
        const { ok, porEtapa: salvo, erro } = mensagem.payload || {};
        setCarregado(true);
        if (!ok) {
          adicionarToast?.({ tipo: "erro", titulo: "Não foi possível ler material/conexão", mensagem: erro, duracaoMs: 9000 });
          return;
        }
        setPorEtapa(salvo || {});
        return;
      }

      if (mensagem.type === BridgeMessageTypes.MATERIAL_CONEXAO_SAVED) {
        const { ok, porEtapa: salvo, erro } = mensagem.payload || {};
        if (!ok) {
          adicionarToast?.({ tipo: "erro", titulo: "Não foi possível salvar material/conexão", mensagem: erro, duracaoMs: 9000 });
          return;
        }
        setPorEtapa(salvo || {});
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function escolher(etapa, pipeTypeId, campo, valor) {
    const chave = pipeTypeId === null || pipeTypeId === undefined ? "none" : String(pipeTypeId);
    const atual = porEtapa[etapa]?.[chave] || { material: null, sistema: "bsp" };
    if (atual[campo] === valor) return;
    const novo = {
      ...porEtapa,
      [etapa]: { ...porEtapa[etapa], [chave]: { ...atual, [campo]: valor } },
    };
    setPorEtapa(novo);
    postToHost(BridgeMessageTypes.SET_MATERIAL_CONEXAO, { porEtapa: novo });
  }

  const etapasComTubo = ETAPAS.filter((etapa) => (pipeTypesPorEtapa?.[etapa]?.length || 0) > 0);

  return (
    <div className="cartao-info" style={{ marginBottom: 14 }}>
      <h3 style={{ margin: 0 }}>Material e Sistema de Conexão</h3>
      <p className="hid-secao-desc">
        Define o material da tubulação (coeficiente C) e o sistema de conexão de cotovelo/tê (BSP ou Grooved),
        por trecho e tipo de tubo. Sem escolha, usa galvanizado (C=120) e BSP.
      </p>
      {!carregado ? (
        <p className="vazio">Carregando…</p>
      ) : etapasComTubo.length === 0 ? (
        <p className="vazio">Mapeie a rede (acima) para configurar material e conexão por trecho.</p>
      ) : (
        etapasComTubo.map((etapa) => (
          <div key={etapa} style={{ marginTop: 10 }}>
            <p className="dashboard-subtitulo" style={{ margin: "0 0 6px" }}>{NOME_ETAPA[etapa]}</p>
            <div className="hiddim-tabela-wrap">
              <table className="hiddim-tabela">
                <thead>
                  <tr>
                    <th className="hiddim-th hiddim-align-left">Tipo de tubo</th>
                    <th className="hiddim-th hiddim-align-left">Material</th>
                    <th className="hiddim-th hiddim-align-left">Sistema de conexão</th>
                  </tr>
                </thead>
                <tbody>
                  {pipeTypesPorEtapa[etapa].map((grupo) => {
                    const chave = grupo.id === null ? "none" : String(grupo.id);
                    const escolha = porEtapa[etapa]?.[chave] || { material: null, sistema: "bsp" };
                    return (
                      <tr key={chave}>
                        <td className="hiddim-td hiddim-align-left">{rotuloPipeType(grupo)}</td>
                        <td className="hiddim-td hiddim-align-left">
                          <select
                            className="se-select"
                            value={escolha.material || ""}
                            onChange={(e) => escolher(etapa, grupo.id, "material", e.target.value || null)}
                          >
                            <option value="">Galvanizado (padrão)</option>
                            {MATERIAIS.map((m) => (
                              <option key={m.key} value={m.key}>{m.label}</option>
                            ))}
                          </select>
                        </td>
                        <td className="hiddim-td hiddim-align-left">
                          <div style={{ display: "flex", gap: 6 }}>
                            {Object.keys(ROTULO_SISTEMA).map((sistema) => (
                              <PillSistema
                                key={sistema}
                                active={(escolha.sistema || "bsp") === sistema}
                                onClick={() => escolher(etapa, grupo.id, "sistema", sistema)}
                              >
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
          </div>
        ))
      )}
    </div>
  );
}
