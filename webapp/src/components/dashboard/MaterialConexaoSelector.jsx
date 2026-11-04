import { useEffect, useRef, useState } from "react";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";

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

function chavePipeType(id) {
  return id === null || id === undefined ? "none" : String(id);
}

/** Todo (etapa, chave) que o último mapeamento encontrou — usado pra
 * aplicar uma escolha única a tudo de uma vez, e pra inferir se o que já
 * está salvo é, de fato, igual em todo mundo. */
function todasAsChaves(pipeTypesPorEtapa) {
  return ETAPAS.flatMap((etapa) =>
    (pipeTypesPorEtapa?.[etapa] || []).map((g) => ({ etapa, chave: chavePipeType(g.id) }))
  );
}

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

function localizarGrupo(eids) {
  if (!eids?.length) return;
  postToHost(BridgeMessageTypes.SELECIONAR_TRECHO_HIDRANTE, { rota: eids });
}

function BotaoLocalizar({ eids }) {
  return eids?.length > 0 ? (
    <button type="button" className="hiddim-localizar-btn" onClick={() => localizarGrupo(eids)} title="Selecionar no Revit">
      <Icon svg={searchIconSvg} />
    </button>
  ) : (
    <span className="hiddim-td-vazio">—</span>
  );
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
 * "Mesmo material/conexão para todos os trechos": simplifica pra um
 * controle só, que grava A MESMA escolha em TODO (etapa, tipo de tubo)
 * conhecido — sem formato novo nenhum do lado do Python: é só o mesmo
 * SET_MATERIAL_CONEXAO de sempre, com a mesma escolha repetida em cada
 * chave. Ao carregar, se tudo que já está salvo (ou nada) já é igual, o
 * modo único entra ligado sozinho; se há escolhas diferentes entre
 * trechos, começa desligado pra não escondê-las.
 *
 * Escolha salva no Project Information do projeto
 * (material_conexao.py); lida pelo "Dimensionar Hidrantes" seguinte — um
 * dimensionamento já feito só reflete a troca depois de "Dimensionar
 * Novamente".
 */
export default function MaterialConexaoSelector({ pipeTypesPorEtapa, adicionarToast }) {
  const [porEtapa, setPorEtapa] = useState({});
  const [carregado, setCarregado] = useState(false);
  const [mesmoParaTodos, setMesmoParaTodos] = useState(false);
  const [escolhaUnica, setEscolhaUnica] = useState({ material: null, sistema: "bsp" });
  const inferenciaFeitaRef = useRef(false);

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

  // Só uma vez, assim que carrega: se tudo que já está configurado pras
  // combinações do mapeamento é igual (ou nada está configurado ainda),
  // liga o modo único sozinho — sem forçar de novo depois, pra não
  // atrapalhar o usuário trocando manualmente entre os modos.
  useEffect(() => {
    if (!carregado || inferenciaFeitaRef.current) return;
    const chaves = todasAsChaves(pipeTypesPorEtapa);
    if (chaves.length === 0) return; // ainda sem combinações — espera o mapeamento
    inferenciaFeitaRef.current = true;

    const valores = chaves.map(({ etapa, chave }) => porEtapa[etapa]?.[chave] || { material: null, sistema: "bsp" });
    const primeiro = valores[0];
    const todasIguais = valores.every((v) => (v.material || null) === (primeiro.material || null) && (v.sistema || "bsp") === (primeiro.sistema || "bsp"));
    if (todasIguais) {
      setEscolhaUnica({ material: primeiro.material || null, sistema: primeiro.sistema || "bsp" });
      setMesmoParaTodos(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [carregado, pipeTypesPorEtapa]);

  function escolher(etapa, pipeTypeId, campo, valor) {
    const chave = chavePipeType(pipeTypeId);
    const atual = porEtapa[etapa]?.[chave] || { material: null, sistema: "bsp" };
    if (atual[campo] === valor) return;
    const novo = {
      ...porEtapa,
      [etapa]: { ...porEtapa[etapa], [chave]: { ...atual, [campo]: valor } },
    };
    setPorEtapa(novo);
    postToHost(BridgeMessageTypes.SET_MATERIAL_CONEXAO, { porEtapa: novo });
  }

  function aplicarParaTodos(escolha) {
    const chaves = todasAsChaves(pipeTypesPorEtapa);
    const novo = { ...porEtapa };
    for (const { etapa, chave } of chaves) {
      novo[etapa] = { ...novo[etapa], [chave]: escolha };
    }
    setPorEtapa(novo);
    postToHost(BridgeMessageTypes.SET_MATERIAL_CONEXAO, { porEtapa: novo });
  }

  function alternarMesmoParaTodos(ligado) {
    setMesmoParaTodos(ligado);
    if (ligado) aplicarParaTodos(escolhaUnica);
  }

  function escolherUnica(campo, valor) {
    const nova = { ...escolhaUnica, [campo]: valor };
    setEscolhaUnica(nova);
    aplicarParaTodos(nova);
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
        <>
          <label style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={mesmoParaTodos}
              onChange={(e) => alternarMesmoParaTodos(e.target.checked)}
            />
            <span>Mesmo material e conexão para todos os trechos</span>
          </label>

          {mesmoParaTodos ? (
            <div className="hiddim-tabela-wrap">
              <table className="hiddim-tabela">
                <thead>
                  <tr>
                    <th className="hiddim-th hiddim-align-left">Material</th>
                    <th className="hiddim-th hiddim-align-left">Sistema de conexão</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="hiddim-td hiddim-align-left">
                      <select
                        className="se-select"
                        value={escolhaUnica.material || ""}
                        onChange={(e) => escolherUnica("material", e.target.value || null)}
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
                            active={(escolhaUnica.sistema || "bsp") === sistema}
                            onClick={() => escolherUnica("sistema", sistema)}
                          >
                            {ROTULO_SISTEMA[sistema]}
                          </PillSistema>
                        ))}
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="hid-nota-aviso">Aplicado a todos os trechos e tipos de tubo encontrados no mapeamento.</p>
            </div>
          ) : (
            etapasComTubo.map((etapa) => (
              <div key={etapa} style={{ marginTop: 10 }}>
                <p className="dashboard-subtitulo" style={{ margin: "0 0 6px" }}>{NOME_ETAPA[etapa]}</p>
                <div className="hiddim-tabela-wrap">
                  <table className="hiddim-tabela">
                    <thead>
                      <tr>
                        <th className="hiddim-th hiddim-align-center" style={{ width: 40 }} />
                        <th className="hiddim-th hiddim-align-left">Tipo de tubo</th>
                        <th className="hiddim-th hiddim-align-left">Material</th>
                        <th className="hiddim-th hiddim-align-left">Sistema de conexão</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pipeTypesPorEtapa[etapa].map((grupo) => {
                        const chave = chavePipeType(grupo.id);
                        const escolha = porEtapa[etapa]?.[chave] || { material: null, sistema: "bsp" };
                        return (
                          <tr key={chave}>
                            <td className="hiddim-td hiddim-align-center">
                              <BotaoLocalizar eids={grupo.eids} />
                            </td>
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
        </>
      )}
    </div>
  );
}
