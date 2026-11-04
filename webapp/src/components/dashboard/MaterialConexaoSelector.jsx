import { useEffect, useRef, useState } from "react";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";
import checkStrokeIconSvg from "../../assets/icons/check-stroke-icon.svg?raw";

// Mesmas chaves curtas que hazen_c usa no perfil normativo (ver
// ALIAS_MATERIAL_TUBULACAO em perfil.ts, ETOS.FireUtils / MATERIAIS_VALIDOS
// em material_conexao.py) — evita qualquer tradução de chave no caminho
// até o motor. Rótulos copiados do catálogo do site
// (src/data/hidrantesCatalogos.js, ETOS.FireUtils).
// "galvanizado" não entra aqui — já é a opção padrão do <select> (sem
// escolha = galvanizado); listar os dois deixava "Galvanizado" duas vezes.
const MATERIAIS = [
  { key: "ff_sem_revest", label: "Ferro fundido/dúctil sem revestimento" },
  { key: "aco_preto_seco", label: "Aço preto (tubo seco)" },
  { key: "aco_preto_molhado", label: "Aço preto (tubo molhado)" },
  { key: "plastico", label: "Plástico (PVC/PEAD)" },
  { key: "ff_revest_cimento", label: "Ferro fundido/dúctil com cimento" },
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

function localizarGrupo(eids) {
  if (!eids?.length) return;
  postToHost(BridgeMessageTypes.SELECIONAR_TRECHO_HIDRANTE, { rota: eids });
}

function BotaoLocalizar({ eids }) {
  return eids?.length > 0 ? (
    <button type="button" className="hiddim-localizar-btn" onClick={() => localizarGrupo(eids)} title="Selecionar no Revit">
      <Icon svg={searchIconSvg} />
    </button>
  ) : null;
}

/** Linha "rótulo em cima, campo embaixo" — empilha bem em telas estreitas,
 * nunca corta texto de select/botão (ao contrário de colunas de tabela). */
function Campo({ rotulo, children }) {
  return (
    <div>
      <div className="hid-espec-label">{rotulo}</div>
      {children}
    </div>
  );
}

function SeletorMaterial({ value, onChange }) {
  return (
    <select className="se-select" style={{ width: "100%" }} value={value || ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">Galvanizado (padrão)</option>
      {MATERIAIS.map((m) => (
        <option key={m.key} value={m.key}>{m.label}</option>
      ))}
    </select>
  );
}

function SeletorSistema({ value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6 }}>
      {Object.keys(ROTULO_SISTEMA).map((sistema) => (
        <button
          key={sistema}
          type="button"
          className={`hid-acionamento-pill ${(value || "bsp") === sistema ? "hid-acionamento-pill-ativa" : ""}`}
          style={{ flex: 1, textAlign: "center" }}
          onClick={() => onChange(sistema)}
        >
          {ROTULO_SISTEMA[sistema]}
        </button>
      ))}
    </div>
  );
}

/** Um grupo (tipo de tubo detectado) dentro de uma etapa — card próprio,
 * campos empilhados (nunca lado a lado): é o que se comporta bem numa
 * dockpane estreita, sem truncar o nome do material nem espremer os
 * botões de sistema. */
function CartaoGrupo({ grupo, escolha, onEscolher }) {
  const diametros = grupo.diametros || [];
  const nome = grupo.nome || "Tipo de tubo não identificado";
  return (
    <div className="hiddim-segmento">
      <div className="hiddim-segmento-topo">
        {diametros.map((d) => (
          <span key={d} className="hiddim-dn-badge">DN{Math.round(d)}</span>
        ))}
        <span className="hiddim-segmento-tubo" style={{ flex: "1 1 auto" }}>{nome}</span>
        <BotaoLocalizar eids={grupo.eids} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Campo rotulo="Material">
          <SeletorMaterial value={escolha.material} onChange={(v) => onEscolher("material", v)} />
        </Campo>
        <Campo rotulo="Sistema de conexão">
          <SeletorSistema value={escolha.sistema} onChange={(v) => onEscolher("sistema", v)} />
        </Campo>
      </div>
    </div>
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
 * Layout em cards empilhados (não tabela): a dockpane é estreita, e uma
 * tabela de 3-4 colunas (tipo de tubo / material / sistema) espreme ou
 * corta texto sempre que o painel do Revit fica mais estreito. Cada grupo
 * vira um card com rótulo em cima do campo — mesmo padrão já usado em
 * "Perdas de Carga por Trecho" (.hiddim-segmento) e no card de
 * Acionamento da Bomba (.hid-acionamento-lista), pra ficar familiar pra
 * quem já usa o resto da dockpane todo dia.
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

  function alternarMesmoParaTodos() {
    const ligando = !mesmoParaTodos;
    setMesmoParaTodos(ligando);
    if (ligando) aplicarParaTodos(escolhaUnica);
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
      {/* .hid-secao-desc tem margin-top negativo (compensa o line-height de
          outro card, "Bomba de Incêndio") — sobrescrito aqui pra não colar
          no título. */}
      <p className="hid-secao-desc" style={{ marginTop: 6 }}>
        Material (coeficiente C) e sistema de conexão de cotovelo/tê, por trecho e tipo de tubo. Sem escolha,
        usa galvanizado (C=120) e BSP.
      </p>
      {!carregado ? (
        <p className="vazio">Carregando…</p>
      ) : etapasComTubo.length === 0 ? (
        <p className="vazio">Mapeie a rede (acima) para configurar material e conexão por trecho.</p>
      ) : (
        <>
          <button type="button" className={`hid-bomba-cartao ${mesmoParaTodos ? "hid-bomba-cartao-ativa" : ""}`} onClick={alternarMesmoParaTodos} style={{ marginTop: 16 }}>
            <span className="hid-bomba-cartao-textos">
              <span className="hid-bomba-cartao-titulo">Mesmo material e conexão para todos os trechos</span>
            </span>
            <span className={`hid-bomba-check ${mesmoParaTodos ? "hid-bomba-check-ativo" : ""}`}>
              {mesmoParaTodos && <Icon svg={checkStrokeIconSvg} />}
            </span>
          </button>

          {mesmoParaTodos ? (
            <div className="hiddim-segmento" style={{ marginTop: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Campo rotulo="Material">
                  <SeletorMaterial value={escolhaUnica.material} onChange={(v) => escolherUnica("material", v)} />
                </Campo>
                <Campo rotulo="Sistema de conexão">
                  <SeletorSistema value={escolhaUnica.sistema} onChange={(v) => escolherUnica("sistema", v)} />
                </Campo>
              </div>
              <p className="hid-nota-aviso" style={{ marginBottom: 0 }}>Aplicado a todos os trechos e tipos de tubo encontrados no mapeamento.</p>
            </div>
          ) : (
            etapasComTubo.map((etapa, i) => (
              <div key={etapa} style={{ marginTop: i === 0 ? 20 : 24 }}>
                <p className="dashboard-subtitulo" style={{ margin: "0 0 10px" }}>{NOME_ETAPA[etapa]}</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {pipeTypesPorEtapa[etapa].map((grupo) => (
                    <CartaoGrupo
                      key={chavePipeType(grupo.id)}
                      grupo={grupo}
                      escolha={porEtapa[etapa]?.[chavePipeType(grupo.id)] || { material: null, sistema: "bsp" }}
                      onEscolher={(campo, valor) => escolher(etapa, grupo.id, campo, valor)}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
