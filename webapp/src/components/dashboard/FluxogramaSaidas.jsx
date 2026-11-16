import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow, ReactFlowProvider, Background, Controls, Handle, Panel, Position, MarkerType, applyNodeChanges, useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./FluxogramaSaidas.css";
import Icon from "../Icon";
import { AmbienteForm, fmtM } from "./seShared";
import {
  calcPopAmb, calcNoAmbientePT, calcDimsAcesso, calcErEstrutura, dimsDoAcesso, contarSaidasPavimento, ehRaiz,
} from "../../data/se_calc";
import { FAIXA_CAB, FAIXA_PAD, ORIGEM_X, ORIGEM_Y, caminhoAteSaida, ladosMaisProximos, proximoNomeGrupo, tipoDeLigacao } from "../../data/se_fluxo";
import { aplicarAcaoSaida, idAcesso, idAmbienteSE, idGrupo } from "../../lib/seReducer";
import { salvarComRetry } from "../../lib/projectData";
import gripIconSvg from "../../assets/icons/grip-icon.svg?raw";
import pencilIconSvg from "../../assets/icons/pencil-icon.svg?raw";
import trashIconSvg from "../../assets/icons/trash-icon.svg?raw";
import plusIconSvg from "../../assets/icons/plus-icon.svg?raw";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";
import exitBoxIconSvg from "../../assets/icons/exit-box-icon.svg?raw";
import perfilIconSvg from "../../assets/icons/perfil-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";
import arrowLeftIconSvg from "../../assets/icons/arrow-left-icon.svg?raw";
import lockIconSvg from "../../assets/icons/lock-icon.svg?raw";

/**
 * FluxogramaSaidas.jsx — fluxograma de saídas de uma ESTRUTURA (Grupo de
 * ambientes -> Acesso -> Saída/Escada), portado de ETOS.FireUtils/src/pages/
 * medidas/FluxogramaSaidas.jsx. Uma área de trabalho com uma faixa por
 * pavimento (o de cima no topo); cada pavimento já traz a sua saída (piso de
 * descarga) ou escada/rampa padrão, que não pode ser excluída. O usuário
 * arrasta os nós, liga um ao outro com setas e escolhe por nó se ele é acesso,
 * saída ou escada/rampa. Nós só se ligam dentro do mesmo pavimento — exceto
 * saídas e escadas/rampas, que também se ligam a saídas/escadas de outros
 * pavimentos (ver tipoDeLigacao em data/se_fluxo.js). A escada/rampa é
 * dimensionada uma única vez por estrutura (calcErEstrutura): vale pra todas.
 *
 * Diferença de arquitetura pro site: lá existe um reducer vivo (useReducer +
 * broadcast em tempo real entre abas). Aqui não há reducer nem sessão
 * compartilhada — cada ação aplica lib/seReducer.aplicarAcaoSaida sobre uma
 * cópia de `dados` e persiste na hora via lib/projectData.salvarComRetry
 * (compare-and-swap pela versão da linha). As ações saem em fila, uma de cada
 * vez, sempre em cima da linha mais recente. Se a escrita falhar, avisa e a
 * área volta ao que está salvo.
 */

const MIME_AMBIENTES = "application/x-fireutils-ambientes";
const FluxoCtx = createContext(null);

// Busca sem diferenciar maiúsculas/acentos ("deposito" acha "Depósito").
const normalizar = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

// Tamanho de um nó ainda não medido pelo React Flow (só vale até a 1ª medição).
const TAM_PADRAO = { grupo: [340, 260], acesso: [300, 200], ambiente: [300, 80] };
// Quanto além da faixa ainda vale soltar um ambiente arrastado da lista.
const MARGEM_SOLTAR = 400;

// Faixa do pavimento = retângulo que envolve os nós dele (posições absolutas e
// tamanhos medidos) mais uma folga, com espaço em cima pro nome. Acompanha os
// nós em tempo real, inclusive durante o arrasto.
function calcFaixa(pav, nosDoPavimento) {
  const caixas = nosDoPavimento.map((n) => {
    const [w0, h0] = TAM_PADRAO[n.type] || [300, 200];
    return { x: n.position.x, y: n.position.y, w: n.measured?.width ?? w0, h: n.measured?.height ?? h0 };
  });
  const o = pav.faixaPos || { x: 0, y: 0 };
  const minX = caixas.length ? Math.min(...caixas.map((c) => c.x)) : o.x;
  const minY = caixas.length ? Math.min(...caixas.map((c) => c.y)) : o.y;
  const maxX = caixas.length ? Math.max(...caixas.map((c) => c.x + c.w)) : o.x + 300;
  const maxY = caixas.length ? Math.max(...caixas.map((c) => c.y + c.h)) : o.y + 200;
  return {
    id: `faixa-${pav.id}`,
    pav,
    x: minX - FAIXA_PAD,
    y: minY - FAIXA_PAD - FAIXA_CAB,
    w: maxX - minX + 2 * FAIXA_PAD,
    h: maxY - minY + 2 * FAIXA_PAD + FAIXA_CAB,
  };
}
// Distância de um ponto até um retângulo (0 se estiver dentro).
const distanciaAteRetangulo = (p, r) => Math.hypot(Math.max(r.x - p.x, 0, p.x - (r.x + r.w)), Math.max(r.y - p.y, 0, p.y - (r.y + r.h)));

const arredondar = (pos) => ({ x: Math.round(pos.x), y: Math.round(pos.y) });

// Agrupa uma lista de ids por pavimento: Map(pavimentoId -> ids).
function porPavimento(ids, pavDe) {
  const m = new Map();
  ids.forEach((id) => {
    const p = pavDe.get(id);
    if (p) m.set(p, [...(m.get(p) || []), id]);
  });
  return m;
}

// ── Peças pequenas ──────────────────────────────────────────────────────
// Nome editável inline — clique vira input; Enter/blur salva, Escape cancela.
function InlineEditableNome({ value, onCommit, className }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const commit = () => {
    setEditing(false);
    const novo = draft.trim();
    if (novo && novo !== value) onCommit(novo);
  };
  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setEditing(false);
        }}
        onClick={(e) => e.stopPropagation()}
        style={{ width: `${Math.max(draft.length, 1) + 1}ch` }}
        className={`se-nome-input ${className || ""}`}
      />
    );
  }
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      className={`se-nome-editavel ${className || ""}`}
    >
      <span className="se-nome-texto">{value}</span>
      <Icon svg={pencilIconSvg} className="se-nome-icone" />
    </button>
  );
}

// Checkbox próprio (botão + ícone) em vez de <input type="checkbox"> nativo.
function Checkbox({ checked, onChange, title }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onChange();
      }}
      title={title}
      className={`se-checkbox ${checked ? "se-checkbox-marcado" : ""}`}
    >
      {checked && <Icon svg={checkIconSvg} />}
    </button>
  );
}

function CampoBusca({ value, onChange, placeholder }) {
  return (
    <div className="fx-busca">
      <Icon svg={searchIconSvg} />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      {value && (
        <button type="button" onClick={() => onChange("")} title="Limpar busca">
          <Icon svg={xIconSvg} />
        </button>
      )}
    </div>
  );
}

// Quebra "ACESSO/DESCARGA" -> "ACESSO/" + quebra de linha + "DESCARGA".
function LabelQuebrado({ texto }) {
  const partes = texto.split("/");
  if (partes.length !== 2) return texto;
  return (
    <>
      {partes[0]}/<br />
      {partes[1]}
    </>
  );
}

function PisoDescargaSwitch({ checked, onChange }) {
  return (
    <div className="se-piso-descarga">
      <span>
        Este pavimento é <strong>piso de descarga</strong>?
      </span>
      <button type="button" onClick={() => onChange(!checked)} className="se-piso-descarga-botao">
        <span className={`se-toggle-track ${checked ? "se-toggle-track-on" : ""}`}>
          <span className="se-toggle-thumb" />
        </span>
        <span className={checked ? "se-piso-descarga-sim" : "se-piso-descarga-nao"}>{checked ? "Sim" : "Não"}</span>
      </button>
    </div>
  );
}

// Caixa de confirmação do próprio painel (no lugar do window.confirm).
function ConfirmacaoModal({ titulo, texto, rotuloConfirmar, onConfirmar, onCancelar }) {
  useEffect(() => {
    const aoTeclar = (e) => {
      if (e.key === "Escape") onCancelar();
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onCancelar]);
  return (
    <div
      className="fx-confirma-fundo"
      onClick={(e) => {
        e.stopPropagation();
        onCancelar();
      }}
    >
      <div role="alertdialog" aria-modal="true" className="fx-confirma" onClick={(e) => e.stopPropagation()}>
        <div className="fx-confirma-titulo">{titulo}</div>
        <div className="fx-confirma-texto">{texto}</div>
        <div className="fx-confirma-botoes">
          <button type="button" className="se-botao" onClick={onCancelar}>
            Cancelar
          </button>
          <button type="button" autoFocus className="fx-confirma-perigo" onClick={onConfirmar}>
            {rotuloConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Ambiente (cartão dentro de um grupo, solto na área ou na lista) ───────
// Arrastável por HTML5 DnD (solta num grupo, na área de trabalho ou na lista
// lateral); marcar vários pelo checkbox e arrastar um leva a seleção inteira.
// Checkbox e botão do canto só aparecem no hover — ou em todos os cartões
// enquanto houver algum marcado. Com pelo menos um marcado, o clique no cartão
// marca/desmarca em vez de abrir o formulário. `noGrupo`: já está posicionado
// (em grupo ou solto na área) — o botão do canto devolve pra lista; na lista,
// o botão exclui o ambiente.
function AmbienteLinha({ amb, noGrupo, naArea = false }) {
  const c = useContext(FluxoCtx);
  const pop = calcPopAmb(amb, c.taxa);
  const { pt } = calcNoAmbientePT(amb, c.taxa, c.larguras);
  const selecionado = c.selecionados.has(amb.id);
  const controles = `fx-amb-ctl ${c.selecionados.size > 0 ? "fx-amb-ctl-visivel" : ""}`;
  return (
    <div
      draggable={!naArea}
      onDragStart={
        naArea
          ? undefined
          : (e) => {
              e.dataTransfer.setData(MIME_AMBIENTES, JSON.stringify(c.idsDoArrasto(amb.id)));
              e.dataTransfer.effectAllowed = "move";
            }
      }
      onClick={() => (c.selecionados.size > 0 ? c.toggleSelecao(amb.id) : c.editarAmbiente(amb))}
      className={`${naArea ? "" : "nodrag"} fx-amb ${selecionado ? "fx-amb-sel" : ""}`}
    >
      <div className="fx-amb-linha">
        <div className="fx-amb-esq">
          <span className={`nodrag ${controles}`}>
            <Checkbox checked={selecionado} onChange={() => c.toggleSelecao(amb.id)} title="Selecionar pra mover em massa" />
          </span>
          <span className="fx-amb-nome">{amb.nome}</span>
          {amb.origem === "manual" && (
            <span title="Ambiente criado manualmente (não veio do Revit)" className="fx-badge-manual">
              <Icon svg={perfilIconSvg} />
            </span>
          )}
        </div>
        {noGrupo ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              c.moverParaGrupo([amb.id], null);
            }}
            className={`nodrag fx-amb-botao ${controles}`}
            title="Voltar pra lista de ambientes (fora da área)"
          >
            <Icon svg={exitBoxIconSvg} />
          </button>
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              c.removerAmbiente(amb.id);
            }}
            className={`fx-amb-botao ${controles}`}
            title="Excluir ambiente"
          >
            <Icon svg={trashIconSvg} />
          </button>
        )}
      </div>
      <div className="fx-amb-info">
        <span>{pop} pessoas</span>
        <b>|</b>
        <span className="fx-amb-porta">
          <span>Porta</span>
          <strong>{fmtM(pt.la)}</strong>
        </span>
      </div>
    </div>
  );
}

// ── Alças de ligação ───────────────────────────────────────────────────
// A alça vermelha (origem) é por onde o usuário puxa a seta — no centro dos
// quatro lados, só visível com o mouse sobre o nó ou o nó selecionado (ver
// FluxogramaSaidas.css). O destino não precisa de alça: o usuário solta a seta
// em qualquer ponto do corpo do nó. As alças de destino existem só pro React
// Flow ter onde encaixar a ponta da seta (invisíveis, sem clique). A seta sai e
// chega sempre pelos lados mais próximos entre os dois nós (ladosMaisProximos).
const LADOS = [
  ["top", Position.Top],
  ["right", Position.Right],
  ["bottom", Position.Bottom],
  ["left", Position.Left],
];
function Alcas({ origem, destino }) {
  return LADOS.flatMap(([lado, posicao]) => [
    origem && <Handle key={`s-${lado}`} id={`s-${lado}`} type="source" position={posicao} />,
    destino && <Handle key={`t-${lado}`} id={`t-${lado}`} type="target" position={posicao} isConnectable={false} />,
  ]);
}

// ── Ambiente solto na área de trabalho (sem grupo) ──────────────────────
// Nó próprio: o cartão inteiro arrasta o nó (clique sem mover abre o formulário
// de edição), e a seta sai direto dele pra um acesso/saída/escada. Soltar o nó
// em cima de um grupo o coloca no grupo; em cima da lista lateral, devolve à
// lista; em cima de outro ambiente solto, forma um grupo com ele.
function AmbienteNode({ data }) {
  const c = useContext(FluxoCtx);
  const [sobre, setSobre] = useState(false);
  const soltarAqui = (e) => {
    setSobre(false);
    let ids = [];
    try {
      ids = JSON.parse(e.dataTransfer.getData(MIME_AMBIENTES));
    } catch {
      /* arrasto de outra origem */
    }
    if (!ids.length) return;
    e.preventDefault();
    e.stopPropagation();
    c.agruparAmbientes(data.amb.id, ids);
  };
  return (
    <div
      className={`fx-no-amb ${sobre || c.noQuente(data.amb.id) ? "fx-realce" : ""}`}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(MIME_AMBIENTES)) {
          e.preventDefault();
          setSobre(true);
        }
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={soltarAqui}
    >
      <AmbienteLinha amb={data.amb} noGrupo naArea />
      <Alcas origem />
    </div>
  );
}

// ── Grupo de ambientes ──────────────────────────────────────────────────
// Agrupa ambientes e liga o conjunto a UM nó (seta pela alça vermelha). Grupo
// sem ligação = ambientes com acesso direto à área de relativa segurança — não
// gera pendência.
function GrupoNode({ data }) {
  const c = useContext(FluxoCtx);
  const { grupo, ambientes, pop } = data;
  const [sobre, setSobre] = useState(false);
  const drop = c.dropProps(grupo.id, setSobre);
  return (
    <div {...drop} className={`fx-grupo ${sobre ? "fx-grupo-sobre" : ""} ${c.noQuente(grupo.id) ? "fx-realce" : ""}`}>
      <div className="fx-grupo-cab">
        <div className="fx-nome-linha">
          <Icon svg={gripIconSvg} />
          <span className="nodrag" style={{ minWidth: 0 }}>
            <InlineEditableNome
              value={grupo.nome}
              onCommit={(nome) => c.despachar({ type: "RENOMEAR_GRUPO", pavimentoId: c.pavDe(grupo.id), grupoId: grupo.id, nome })}
              className="fx-nome"
            />
          </span>
        </div>
        <div className="fx-cab-dir">
          <span className="fx-pop">{pop} pessoas</span>
          <button type="button" onClick={() => c.removerGrupo(grupo)} className="nodrag fx-lixeira" title="Remover grupo (os ambientes ficam soltos)">
            <Icon svg={trashIconSvg} />
          </button>
        </div>
      </div>
      <div className="fx-grupo-corpo">
        {ambientes.map((a) => (
          <AmbienteLinha key={a.id} amb={a} noGrupo />
        ))}
        {ambientes.length === 0 && <div className="fx-grupo-vazio">Arraste ambientes para trazê-los pra cá.</div>}
        <button type="button" className="nodrag se-botao" onClick={() => c.abrirEscolhaAmbientes(grupo.id)}>
          <Icon svg={plusIconSvg} /> ADICIONAR AMBIENTE
        </button>
      </div>
      {!data.ligado && <div className="fx-grupo-aviso">Sem ligação — acesso direto à área de relativa segurança</div>}
      <Alcas origem />
    </div>
  );
}

// ── Acesso / Saída / Escada-Rampa ──────────────────────────────────────
// O tipo é escolhido ao criar (barra do topo e clique direito) e não muda depois.
function AcessoNode({ data }) {
  const c = useContext(FluxoCtx);
  const { acesso, tipo, dims, pop, entradas, raiz, erUnico } = data;
  const alvoValido = c.podeReceberLigacao(acesso.id);
  const pavimentoId = c.pavDe(acesso.id);
  const toggleDim = (d) => c.despachar({ type: "SET_ACESSO_DIM", pavimentoId, acessoId: acesso.id, dim: d, valor: !dims[d] });
  return (
    <div
      className={`fx-acesso ${tipo === "saida" ? "fx-acesso-saida" : tipo === "escada" ? "fx-acesso-escada" : ""} ${alvoValido ? "fx-alvo-valido" : ""} ${
        c.noQuente(acesso.id) ? "fx-realce" : ""
      }`}
    >
      <div className="fx-acesso-cab">
        <div className="fx-nome-linha">
          <Icon svg={gripIconSvg} />
          <span className="nodrag" style={{ minWidth: 0 }}>
            <InlineEditableNome
              value={acesso.nome}
              onCommit={(nome) => c.despachar({ type: "RENOMEAR_ACESSO", pavimentoId, acessoId: acesso.id, nome })}
              className="fx-nome"
            />
          </span>
        </div>
        <div className="fx-cab-dir">
          <span className="fx-pop">{pop} pessoas</span>
          {acesso.fixo ? (
            <span title="Padrão do pavimento: não pode ser excluída" className="fx-cadeado">
              <Icon svg={lockIconSvg} />
            </span>
          ) : (
            <button type="button" onClick={() => c.removerAcesso(acesso)} className="nodrag fx-lixeira" title="Remover (o que alimentava este nó fica sem ligação)">
              <Icon svg={trashIconSvg} />
            </button>
          )}
        </div>
      </div>
      <div className="fx-dims">
        {["AD", "PT", "ER"].map((d) => (
          <button key={d} type="button" onClick={() => toggleDim(d)} className={`nodrag fx-dim-btn ${dims[d] ? "fx-dim-btn-on" : ""}`}>
            {d}
          </button>
        ))}
      </div>
      <div className="fx-entradas">
        {entradas.map((e) => (
          <div key={e.label} className="fx-entrada">
            <div className="fx-entrada-rotulo">
              <LabelQuebrado texto={e.label} />
            </div>
            <div className="fx-entrada-valor">{e.value}</div>
          </div>
        ))}
      </div>
      {erUnico && (
        <div
          className="fx-acesso-nota"
          title="A escada/rampa é dimensionada uma única vez por estrutura, com a população do pavimento mais populoso (sem o piso de descarga) — vale pra todas."
        >
          Escada/rampa: {erUnico.pop} pessoas · {erUnico.label}
        </div>
      )}
      {!raiz && tipo === "acesso" && !acesso.alimentaEm && <div className="fx-acesso-aviso">Sem ligação a uma saída ou escada/rampa</div>}
      <Alcas origem destino />
    </div>
  );
}

// ── Faixa de um pavimento ───────────────────────────────────────────────
// Retângulo que envolve os nós do pavimento (calcFaixa), com o nome em letra
// grande (dá pra ler com zoom afastado). Só o cabeçalho pega o mouse: arrastar
// por ele move a faixa com tudo que há dentro; o resto da faixa deixa nós e
// ligações trabalharem por cima. Só a faixa do pavimento em edição tem fundo e
// borda branca — as opções do topo (criar nós, piso de descarga) valem pra ela.
function FaixaNode({ data }) {
  const c = useContext(FluxoCtx);
  const { pav } = data;
  const ativa = c.pavAtivoId === pav.id;
  return (
    <div className={`fx-faixa ${ativa ? "fx-faixa-ativa" : ""}`}>
      <div style={{ pointerEvents: "auto" }} title="Arraste para mover o pavimento inteiro" className="faixa-cab fx-faixa-cab">
        <span className="fx-faixa-nome">{pav.label}</span>
        {pav.pisoDescarga && <span className="fx-faixa-tag">PISO DE DESCARGA</span>}
      </div>
    </div>
  );
}

// ── Popup "Adicionar ambiente" de um grupo ──────────────────────────────
// Lista os ambientes do MESMO pavimento do grupo que ainda não estão nele (na
// lista lateral, soltos na área ou em outro grupo) e deixa marcar vários pra
// trazer pro grupo; "Novo ambiente" cria um ambiente manual já dentro dele.
function EscolherAmbientesModal({ grupo, candidatos, onAdicionar, onNovo, onFechar }) {
  const [busca, setBusca] = useState("");
  const [marcados, setMarcados] = useState(new Set());
  const termo = normalizar(busca);
  const visiveis = candidatos.filter((c) => normalizar(c.amb.nome).includes(termo));
  const alternar = (id) =>
    setMarcados((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const todosVisiveisMarcados = visiveis.length > 0 && visiveis.every((c) => marcados.has(c.amb.id));
  const alternarTodos = () =>
    setMarcados((prev) => {
      const n = new Set(prev);
      visiveis.forEach((c) => (todosVisiveisMarcados ? n.delete(c.amb.id) : n.add(c.amb.id)));
      return n;
    });
  useEffect(() => {
    const aoTeclar = (e) => {
      if (e.key === "Escape") onFechar();
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onFechar]);
  return (
    <div
      className="se-modal-overlay"
      onClick={(e) => {
        e.stopPropagation();
        onFechar();
      }}
    >
      <div role="dialog" aria-modal="true" className="fx-escolher" onClick={(e) => e.stopPropagation()}>
        <div className="fx-escolher-cab">
          <div style={{ minWidth: 0 }}>
            <div className="fx-escolher-titulo">Adicionar ambientes</div>
            <div className="fx-escolher-sub">
              em <strong>{grupo.nome}</strong>
            </div>
          </div>
          <button type="button" onClick={onFechar} className="se-icon-botao" title="Fechar">
            <Icon svg={xIconSvg} />
          </button>
        </div>
        <div className="fx-escolher-busca">
          <CampoBusca value={busca} onChange={setBusca} placeholder="Buscar ambiente…" />
          {visiveis.length > 0 && (
            <button type="button" className="fx-link" onClick={alternarTodos}>
              {todosVisiveisMarcados ? "Desmarcar todos" : "Marcar todos"}
            </button>
          )}
        </div>
        <div className="fx-escolher-lista">
          {candidatos.length === 0 && <div className="fx-lista-vazio">Não há outros ambientes deste pavimento. Use "Novo ambiente".</div>}
          {candidatos.length > 0 && visiveis.length === 0 && <div className="fx-lista-vazio">Nenhum ambiente corresponde à busca.</div>}
          {visiveis.map(({ amb, onde, pop }) => (
            <div key={amb.id} onClick={() => alternar(amb.id)} className={`fx-escolher-item ${marcados.has(amb.id) ? "fx-escolher-item-marcado" : ""}`}>
              <div className="fx-amb-esq">
                <Checkbox checked={marcados.has(amb.id)} onChange={() => alternar(amb.id)} />
                <span className="fx-amb-nome">{amb.nome}</span>
              </div>
              <div className="fx-escolher-info">
                <span>{pop} pessoas</span>
                <b>|</b>
                <span>{onde}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="fx-escolher-rodape">
          <button type="button" className="se-botao" onClick={onNovo}>
            <Icon svg={plusIconSvg} /> Novo ambiente
          </button>
          <button type="button" className="se-botao se-botao-accent" disabled={marcados.size === 0} onClick={() => onAdicionar([...marcados])}>
            Adicionar ambiente{marcados.size > 1 ? "s" : ""}
            {marcados.size > 0 ? ` (${marcados.size})` : ""}
          </button>
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { faixa: FaixaNode, grupo: GrupoNode, acesso: AcessoNode, ambiente: AmbienteNode };

const NOVO_GRUPO = "__novo_grupo__";
const SEM_GRUPO = "__sem_grupo__";
const NA_AREA = "__na_area__";

// Opções de criar nós: a barra do topo (pavimento em edição) e a barra
// flutuante do clique direito (pavimento sob o clique, nó nasce no ponto).
const OPCOES_CRIAR = [
  ["grupo", "Grupo de ambientes"],
  ["ambiente", "Ambiente"],
  ["acesso", "Acesso"],
  ["saida", "Saída"],
  ["escada", "Escada/Rampa"],
];

function Fluxograma({ projeto, estrutura, pavimentos, focoPavId, seNorma, ocupacoes, onVoltar, onProjetoAtualizado, adicionarToast, enviarAcao }) {
  const { TAXA_POPULACIONAL, LARGURAS_MINIMAS } = seNorma;
  // Faixas de cima pra baixo: pavimento mais alto no topo, subsolos embaixo.
  const pavs = useMemo(() => [...pavimentos].reverse(), [pavimentos]);
  const ambientes = useMemo(() => pavimentos.flatMap((p) => p.ambientes || []), [pavimentos]);
  const acessos = useMemo(() => pavimentos.flatMap((p) => p.acessos || []), [pavimentos]);
  const grupos = useMemo(() => pavimentos.flatMap((p) => p.grupos || []), [pavimentos]);
  // Quem é de qual pavimento (os ids de nós são únicos no projeto).
  const pavDe = useMemo(() => {
    const m = new Map();
    pavimentos.forEach((p) => {
      (p.ambientes || []).forEach((a) => m.set(a.id, p.id));
      (p.acessos || []).forEach((a) => m.set(a.id, p.id));
      (p.grupos || []).forEach((g) => m.set(g.id, p.id));
    });
    return m;
  }, [pavimentos]);
  const pavPorId = useMemo(() => new Map(pavimentos.map((p) => [p.id, p])), [pavimentos]);
  const posDe = (id) => pavPorId.get(pavDe.get(id))?.fluxoPos?.[id];

  const [editAmb, setEditAmb] = useState(null);
  const [selecionados, setSelecionados] = useState(new Set());
  const [alvoSelecao, setAlvoSelecao] = useState("");
  const [listaAberta, setListaAberta] = useState(() => typeof window === "undefined" || window.innerWidth >= 900);
  const [salvando, setSalvando] = useState(false);
  // Maximizar: a área de trabalho passa a ocupar a janela inteira do painel (por
  // cima do menu e do cabeçalho da página); Esc ou o botão voltam ao normal.
  const [maximizado, setMaximizado] = useState(false);
  const [reinicio, setReinicio] = useState(0);
  const wrapRef = useRef(null);
  const rf = useReactFlow();

  // ── Persistência: ações em fila, sempre sobre a linha mais recente ──
  const ultimoProjeto = useRef(projeto);
  const filaRef = useRef(Promise.resolve());
  useEffect(() => {
    ultimoProjeto.current = projeto;
  }, [projeto]);
  // Aplica a ação e persiste na hora — se a escrita falhar (versão
  // desatualizada, sem rede), avisa e a área volta ao que está salvo, pra tela
  // nunca ficar mostrando algo que não foi gravado de verdade. Depois de salvar,
  // `enviarAcao` avisa o site (ou outra sessão da dockpane) em tempo real.
  const despachar = (action) => {
    setSalvando(true);
    filaRef.current = filaRef.current
      .then(async () => {
        const base = ultimoProjeto.current;
        const { dados, version } = await salvarComRetry(base.id, base, (d) => aplicarAcaoSaida(d, action));
        const novo = { ...base, dados, version };
        ultimoProjeto.current = novo;
        onProjetoAtualizado(novo);
        enviarAcao?.(action);
      })
      .catch((erro) => {
        adicionarToast?.({ tipo: "erro", titulo: "Não foi possível salvar", mensagem: erro.message, duracaoMs: 9000 });
        setReinicio((n) => n + 1);
      })
      .finally(() => setSalvando(false));
  };

  // Id de quem está sendo puxado agora (null = nenhuma ligação em andamento);
  // os nós que podem receber a seta se destacam. Vem de onConnectStart/End, não
  // de useConnection(): esse hook re-renderiza a cada movimento do ponteiro e,
  // junto com as props novas a cada render do <ReactFlow>, entra em loop.
  const [origemLigacao, setOrigemLigacao] = useState(null);
  // Pavimento em edição: as opções do topo (criar nós, piso de descarga) valem
  // pra ele. Muda ao escolher no seletor ou ao clicar/arrastar algo dentro da
  // faixa do pavimento (nó, cabeçalho ou o fundo da faixa) — navegar pela área
  // não troca o pavimento em edição.
  const [pavAtivoId, setPavAtivoId] = useState(focoPavId || pavimentos[pavimentos.length - 1]?.id);

  // Nó sob o mouse: ele e tudo até a saída (nós e setas) ficam vermelhos. Não
  // vale durante o arrasto de uma seta nova.
  const [noHover, setNoHover] = useState(null);
  const caminhoQuente = useMemo(
    () => (noHover && !origemLigacao ? caminhoAteSaida(noHover, { acessos, grupos, ambientes }) : null),
    [noHover, origemLigacao, acessos, grupos, ambientes]
  );

  const [filtroSoltos, setFiltroSoltos] = useState("");
  // Lista lateral: ambientes sem grupo e sem posição na área de trabalho.
  const soltos = ambientes.filter((a) => !a.grupoId && !posDe(a.id));
  const soltosFiltrados = soltos.filter((a) => normalizar(a.nome).includes(normalizar(filtroSoltos)));

  // ── Seleção em massa / arrasto de ambientes ──
  const toggleSelecao = (id) =>
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const limparSelecao = () => setSelecionados(new Set());
  const idsDoArrasto = (id) => (selecionados.size > 1 && selecionados.has(id) ? [...selecionados] : [id]);

  // ── Nós (a partir do estado do projeto) ──
  // Posição de um nó na área = origem da faixa do pavimento + `fluxoPos` (relativo).
  // Dimensionamento único das escadas/rampas da estrutura.
  const erEstrutura = useMemo(() => calcErEstrutura(pavimentos, TAXA_POPULACIONAL, LARGURAS_MINIMAS), [pavimentos, TAXA_POPULACIONAL, LARGURAS_MINIMAS]);
  const nosBase = useMemo(() => {
    const nos = [];
    pavs.forEach((p) => {
      const pambs = p.ambientes || [];
      const pacs = p.acessos || [];
      const o = p.faixaPos || { x: 0, y: 0 };
      const filho = (id, type, data) => ({
        id,
        type,
        zIndex: 1,
        position: { x: o.x + (p.fluxoPos?.[id]?.x ?? ORIGEM_X), y: o.y + (p.fluxoPos?.[id]?.y ?? ORIGEM_Y) },
        data,
      });
      (p.grupos || []).forEach((g) => {
        const ambs = pambs.filter((a) => a.grupoId === g.id);
        nos.push(filho(g.id, "grupo", { grupo: g, ambientes: ambs, ligado: !!g.acessoId, pop: ambs.reduce((s, a) => s + calcPopAmb(a, TAXA_POPULACIONAL), 0) }));
      });
      pambs.filter((a) => !a.grupoId && p.fluxoPos?.[a.id]).forEach((a) => nos.push(filho(a.id, "ambiente", { amb: a })));
      pacs.forEach((ac) => {
        const dims = dimsDoAcesso(ac, !!p.pisoDescarga);
        const { pop, ad, er, pt } = calcDimsAcesso(ac.id, pambs, pacs, TAXA_POPULACIONAL, LARGURAS_MINIMAS, dims, erEstrutura);
        nos.push(
          filho(ac.id, "acesso", {
            acesso: ac,
            tipo: ac.tipo,
            dims,
            pop,
            raiz: ehRaiz(ac),
            erUnico: dims.ER && erEstrutura ? { pop: erEstrutura.pop, label: erEstrutura.pavimento.label } : null,
            entradas: [
              ad && { label: "ACESSO/DESCARGA", value: fmtM(ad.la) },
              pt && { label: "PORTAS", value: fmtM(pt.la) },
              er && { label: "ESCADA/RAMPA", value: fmtM(er.la) },
            ].filter(Boolean),
          })
        );
      });
    });
    return nos;
  }, [pavs, erEstrutura, TAXA_POPULACIONAL, LARGURAS_MINIMAS]);

  // Estado local dos nós (React Flow precisa dele pra animar o arrasto);
  // reabastecido a cada mudança do projeto (ou depois de uma falha ao salvar),
  // preservando seleção/medidas e a posição de quem está sendo arrastado agora.
  const [nodes, setNodes] = useState(nosBase);
  const [nosBaseVisto, setNosBaseVisto] = useState(nosBase);
  const [reinicioVisto, setReinicioVisto] = useState(reinicio);
  if (nosBaseVisto !== nosBase || reinicioVisto !== reinicio) {
    setNosBaseVisto(nosBase);
    setReinicioVisto(reinicio);
    const antigos = new Map(nodes.map((n) => [n.id, n]));
    const refeito = reinicioVisto !== reinicio;
    setNodes(
      nosBase.map((n) => {
        const o = antigos.get(n.id);
        if (!o) return n;
        return { ...o, ...n, position: o.dragging && !refeito ? o.position : n.position };
      })
    );
  }

  // ── Faixas (uma por pavimento), ajustadas aos nós em tempo real ──
  const faixas = useMemo(() => pavs.map((p) => calcFaixa(p, nodes.filter((n) => pavDe.get(n.id) === p.id))), [pavs, nodes, pavDe]);
  const nodesComFaixas = useMemo(
    () => [
      ...faixas.map((f) => ({
        id: f.id,
        type: "faixa",
        position: { x: f.x, y: f.y },
        width: f.w,
        height: f.h,
        data: { pav: f.pav },
        // Só o cabeçalho pega o mouse (e arrasta a faixa com tudo que há nela).
        dragHandle: ".faixa-cab",
        selectable: false,
        focusable: false,
        connectable: false,
        style: { width: f.w, height: f.h, pointerEvents: "none" },
        zIndex: 0,
      })),
      ...nodes,
    ],
    [faixas, nodes]
  );
  // Mover uma faixa = mover junto todos os nós dela (a faixa em si é derivada deles).
  const aoMudarNos = (changes) => {
    const deFaixa = changes.filter((c) => c.type === "position" && c.position && String(c.id).startsWith("faixa-"));
    const resto = changes.filter((c) => !String(c.id).startsWith("faixa-"));
    setNodes((ns) => {
      let prox = applyNodeChanges(resto, ns);
      deFaixa.forEach((ch) => {
        const pav = pavs.find((p) => `faixa-${p.id}` === ch.id);
        if (!pav) return;
        const atual = calcFaixa(pav, prox.filter((n) => pavDe.get(n.id) === pav.id));
        const dx = ch.position.x - atual.x;
        const dy = ch.position.y - atual.y;
        if (dx || dy) prox = prox.map((n) => (pavDe.get(n.id) === pav.id ? { ...n, position: { x: n.position.x + dx, y: n.position.y + dy } } : n));
      });
      return prox;
    });
  };
  const faixaDe = (pavId) => faixas.find((f) => f.pav.id === pavId);
  const origemFaixa = (pavId) => pavPorId.get(pavId)?.faixaPos || { x: 0, y: 0 };
  // Enquadra a faixa de um pavimento na tela (com o retângulo calculado aqui, não
  // pelo fitView com `nodes`, que caía no "mostrar tudo").
  const enquadrarFaixa = (inst, pavId, duration) => {
    const f = faixaDe(pavId);
    if (f) inst.fitBounds({ x: f.x, y: f.y, width: f.w, height: f.h }, { padding: 0.03, duration });
  };
  const arrastoFaixa = useRef(null);
  const desvioNovo = useRef(0);

  // ── Posição de nó novo (relativa à origem da faixa): centro da área visível
  // se estiver na faixa, senão o centro da faixa; com um leve desvio pra não
  // empilhar vários nós criados em sequência. `ponto` (coordenadas da área):
  // nó nasce ali (clique direito), sem desvio.
  const posicaoNova = (pavId, ponto) => {
    const faixa = faixaDe(pavId);
    const o = origemFaixa(pavId);
    if (ponto) return arredondar({ x: ponto.x - o.x - 20, y: ponto.y - o.y - 10 });
    const r = wrapRef.current.getBoundingClientRect();
    const vista = rf.screenToFlowPosition({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    const c = distanciaAteRetangulo(vista, faixa) === 0 ? vista : { x: faixa.x + faixa.w / 2, y: faixa.y + faixa.h / 2 };
    // Desvio em escada (0, 20, 40, 60) pra não empilhar nós criados em sequência.
    desvioNovo.current = (desvioNovo.current + 20) % 80;
    return arredondar({ x: c.x - o.x - 150 + desvioNovo.current, y: c.y - o.y - 80 + desvioNovo.current });
  };

  const pavAtivo = pavPorId.get(pavAtivoId) || pavs[0];

  const criarNo = (pavId, tipo, ponto) => {
    const n = acessos.filter((a) => pavDe.get(a.id) === pavId && a.tipo === tipo).length + 1;
    const nome = { acesso: `Acesso ${n}`, saida: `Saída ${String(n).padStart(2, "0")}`, escada: `Escada/Rampa ${String(n).padStart(2, "0")}` }[tipo];
    despachar({ type: "CRIAR_NO_FLUXO", pavimentoId: pavId, id: idAcesso(), tipo, nome, pos: posicaoNova(pavId, ponto) });
  };
  const criarGrupo = (pavId, ambienteIds, ponto) => {
    despachar({
      type: "CRIAR_GRUPO_AMBIENTES",
      pavimentoId: pavId,
      id: idGrupo(),
      nome: proximoNomeGrupo(pavPorId.get(pavId).grupos || []),
      pos: posicaoNova(pavId, ponto),
      ambienteIds,
    });
  };

  // ── Ambientes ──
  // Com `grupoId`, nasce dentro do grupo (do pavimento dele); senão solto na
  // área do pavimento `pavId`.
  const criarAmbiente = (grupoId, pavId, ponto) => {
    const pavimentoId = grupoId ? pavDe.get(grupoId) : pavId;
    const id = idAmbienteSE();
    const nome = `Ambiente ${ambientes.length + 1}`;
    const ambiente = { nome, divisao: "", popTipo: "area", area: 0, assentos: 0, popManual: 0, grupoId: grupoId || null, origem: "manual" };
    despachar({ type: "ADD_AMBIENTE_SE", pavimentoId, id, pos: grupoId ? null : posicaoNova(pavimentoId, ponto), ambiente });
    setEditAmb({ id, ...ambiente });
  };
  const removerAmbiente = (id) => {
    despachar({ type: "REMOVE_AMBIENTE_SE", pavimentoId: pavDe.get(id), ambienteId: id });
    if (editAmb?.id === id) setEditAmb(null);
    setSelecionados((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };
  // Move ambientes pra dentro de um grupo (só os do mesmo pavimento do grupo
  // entram) ou de volta pra lista (`grupoId` null).
  const moverParaGrupo = (ids, grupoId) => {
    const pavDoGrupo = grupoId ? pavDe.get(grupoId) : null;
    porPavimento(ids, pavDe).forEach((lista, pavimentoId) => {
      if (pavDoGrupo && pavimentoId !== pavDoGrupo) return;
      despachar({ type: "MOVER_AMBIENTES_GRUPO", pavimentoId, ambienteIds: lista, grupoId });
    });
    limparSelecao();
  };
  // Coloca ambientes soltos na faixa `pavId`, a partir de `pos` (relativa à
  // origem da faixa), em coluna. Só os ambientes desse pavimento.
  const soltarNaArea = (ids, pavId, pos) => {
    const meus = ids.filter((id) => pavDe.get(id) === pavId);
    if (!meus.length) return;
    despachar({
      type: "SOLTAR_AMBIENTES_NA_AREA",
      pavimentoId: pavId,
      posicoes: Object.fromEntries(meus.map((id, i) => [id, { x: pos.x, y: pos.y + i * 80 }])),
    });
    limparSelecao();
  };
  // Ambiente arrastado da lista (ou de um grupo) e solto no fundo da área: vale
  // perto da faixa do próprio pavimento do ambiente.
  const soltarNoFundo = (e) => {
    if (!e.dataTransfer.types.includes(MIME_AMBIENTES)) return;
    let ids = [];
    try {
      ids = JSON.parse(e.dataTransfer.getData(MIME_AMBIENTES));
    } catch {
      /* arrasto de outra origem */
    }
    if (!ids.length) return;
    e.preventDefault();
    const ponto = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    porPavimento(ids, pavDe).forEach((lista, pavId) => {
      const f = faixaDe(pavId);
      if (!f || distanciaAteRetangulo(ponto, f) > MARGEM_SOLTAR) return;
      const o = origemFaixa(pavId);
      soltarNaArea(lista, pavId, arredondar({ x: ponto.x - o.x, y: ponto.y - o.y }));
    });
  };
  // Junta o ambiente solto `alvoId` com os ambientes `ids` (do mesmo pavimento)
  // num grupo novo, no lugar do alvo e herdando a ligação direta dele (se tinha).
  const agruparAmbientes = (alvoId, ids) => {
    const alvo = ambientes.find((a) => a.id === alvoId);
    const pavimentoId = pavDe.get(alvoId);
    if (!alvo) return;
    despachar({
      type: "CRIAR_GRUPO_AMBIENTES",
      pavimentoId,
      id: idGrupo(),
      nome: proximoNomeGrupo(pavPorId.get(pavimentoId).grupos || []),
      pos: posDe(alvoId) || posicaoNova(pavimentoId),
      acessoId: alvo.acessoId || null,
      ambienteIds: [alvoId, ...ids.filter((id) => id !== alvoId && pavDe.get(id) === pavimentoId)],
    });
    limparSelecao();
  };
  const moverSelecionados = () => {
    if (!selecionados.size || !alvoSelecao) return;
    const ids = [...selecionados];
    if (alvoSelecao === NOVO_GRUPO) porPavimento(ids, pavDe).forEach((lista, pavimentoId) => criarGrupo(pavimentoId, lista));
    else if (alvoSelecao === NA_AREA) porPavimento(ids, pavDe).forEach((lista, pavimentoId) => soltarNaArea(lista, pavimentoId, posicaoNova(pavimentoId)));
    else moverParaGrupo(ids, alvoSelecao === SEM_GRUPO ? null : alvoSelecao);
    limparSelecao();
    setAlvoSelecao("");
  };
  const renomearAmbiente = (nome) => {
    despachar({ type: "UPDATE_AMBIENTE_SE", pavimentoId: pavDe.get(editAmb.id), ambienteId: editAmb.id, changes: { nome } });
    setEditAmb((prev) => ({ ...prev, nome }));
  };

  // Confirmação de remover grupo/nó: caixa do próprio painel (ConfirmacaoModal).
  const [confirmacao, setConfirmacao] = useState(null);
  // Popup de "Adicionar ambiente" de um grupo (id do grupo, ou null).
  const [escolhaGrupoId, setEscolhaGrupoId] = useState(null);
  const removerGrupo = (grupo) => {
    const n = ambientes.filter((a) => a.grupoId === grupo.id).length;
    const remover = () => despachar({ type: "REMOVER_GRUPO", pavimentoId: pavDe.get(grupo.id), grupoId: grupo.id });
    if (n === 0) {
      remover();
      return;
    }
    setConfirmacao({
      titulo: `Remover o grupo "${grupo.nome}"?`,
      texto: `Os ${n} ambiente${n > 1 ? "s" : ""} dentro dele voltarão pra lista de ambientes, mas não serão apagados.`,
      rotulo: "Remover grupo",
      onConfirmar: remover,
    });
  };
  const removerAcesso = (acesso) => {
    if (acesso.fixo) return;
    setConfirmacao({
      titulo: `Remover "${acesso.nome}"?`,
      texto: "O que alimentava este nó ficará sem ligação, mas não será apagado.",
      rotulo: "Remover",
      onConfirmar: () => despachar({ type: "REMOVER_ACESSO", pavimentoId: pavDe.get(acesso.id), acessoId: acesso.id }),
    });
  };

  // Props de uma zona que recebe ambientes arrastados (grupo ou lista de soltos).
  const dropProps = (grupoId, setSobre) => ({
    onDragOver: (e) => {
      if (!e.dataTransfer.types.includes(MIME_AMBIENTES)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setSobre?.(true);
    },
    onDragLeave: () => setSobre?.(false),
    onDrop: (e) => {
      setSobre?.(false);
      let ids = [];
      try {
        ids = JSON.parse(e.dataTransfer.getData(MIME_AMBIENTES));
      } catch {
        /* arrasto de outra origem */
      }
      if (!ids.length) return;
      e.preventDefault();
      e.stopPropagation();
      moverParaGrupo(ids, grupoId);
    },
  });

  // ── Barra flutuante do clique direito (mesmas opções da barra do topo) ──
  const criarDaOpcao = (op, pavId, ponto) => {
    if (op === "grupo") criarGrupo(pavId, undefined, ponto);
    else if (op === "ambiente") criarAmbiente(null, pavId, ponto);
    else criarNo(pavId, op, ponto);
  };
  const [menu, setMenu] = useState(null); // { x, y (px no quadro), ponto (área), pavId }
  const abrirMenu = (e) => {
    e.preventDefault();
    const ponto = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const f = faixas.find((x) => distanciaAteRetangulo(ponto, x) === 0);
    const pavId = f ? f.pav.id : pavAtivo.id;
    setPavAtivoId(pavId);
    const r = wrapRef.current.getBoundingClientRect();
    setMenu({
      x: Math.max(8, Math.min(e.clientX - r.left, r.width - 240)),
      y: Math.max(8, Math.min(e.clientY - r.top, r.height - 270)),
      ponto,
      pavId,
    });
  };
  useEffect(() => {
    if (!menu) return undefined;
    const fechar = (e) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("keydown", fechar);
    return () => window.removeEventListener("keydown", fechar);
  }, [menu]);

  const ctx = {
    pavAtivoId,
    pavDe: (id) => pavDe.get(id),
    despachar,
    taxa: TAXA_POPULACIONAL,
    larguras: LARGURAS_MINIMAS,
    selecionados,
    toggleSelecao,
    idsDoArrasto,
    editarAmbiente: setEditAmb,
    criarAmbiente,
    abrirEscolhaAmbientes: setEscolhaGrupoId,
    removerAmbiente,
    moverParaGrupo,
    agruparAmbientes,
    removerGrupo,
    removerAcesso,
    dropProps,
    noQuente: (id) => !!caminhoQuente?.nos.includes(id),
    podeReceberLigacao: (id) => !!origemLigacao && conexaoValida({ source: origemLigacao, target: id }),
  };

  // Seta selecionada (clique) — a única coisa que Delete/"Desligar" apaga.
  const [setaSelecionada, setSetaSelecionada] = useState(null);
  const ambientesNaArea = new Set(ambientes.filter((a) => !a.grupoId && posDe(a.id)).map((a) => a.id));
  const edges = useMemo(() => {
    const existe = new Set(acessos.map((a) => a.id));
    const na = ambientes.filter((a) => !a.grupoId && posDe(a.id));
    const liga = [
      ...grupos.filter((g) => existe.has(g.acessoId)).map((g) => ({ id: `e-${g.id}`, source: g.id, target: g.acessoId })),
      ...acessos.filter((a) => existe.has(a.alimentaEm)).map((a) => ({ id: `e-${a.id}`, source: a.id, target: a.alimentaEm })),
      ...acessos.filter((a) => existe.has(a.ligadoA)).map((a) => ({ id: `e-${a.id}`, source: a.id, target: a.ligadoA, entre: true })),
      ...na.filter((a) => existe.has(a.acessoId)).map((a) => ({ id: `e-${a.id}`, source: a.id, target: a.acessoId })),
    ];
    const retangulo = (id) => {
      const n = nodes.find((x) => x.id === id);
      const [w0, h0] = TAM_PADRAO[n.type] || [300, 200];
      return { x: n.position.x, y: n.position.y, w: n.measured?.width ?? w0, h: n.measured?.height ?? h0 };
    };
    return liga
      .filter((e) => nodes.some((n) => n.id === e.source) && nodes.some((n) => n.id === e.target))
      .map((e) => {
        const { de, para } = ladosMaisProximos(retangulo(e.source), retangulo(e.target));
        return { ...e, sourceHandle: `s-${de}`, targetHandle: `t-${para}` };
      })
      .map((e) => ({
        ...e,
        type: "smoothstep",
        selected: e.id === setaSelecionada,
        ...(caminhoQuente?.setas.includes(e.id)
          ? {
              markerEnd: { type: MarkerType.ArrowClosed, color: "var(--accent)" },
              style: { strokeWidth: 3, stroke: "var(--accent)", strokeDasharray: e.entre ? "8 5" : undefined },
              zIndex: 10,
            }
          : {
              markerEnd: { type: MarkerType.ArrowClosed, color: "var(--text-3)" },
              style: { strokeWidth: 2, strokeDasharray: e.entre ? "8 5" : undefined },
            }),
      }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grupos, acessos, ambientes, pavimentos, nodes, setaSelecionada, caminhoQuente]);

  // Cada nó alimenta no máximo UM seguinte; que ligação vale entre dois nós
  // (mesmo pavimento, ou saída/escada entre pavimentos) está em tipoDeLigacao.
  const tipoLigacao = (source, target) => tipoDeLigacao(source, target, { acessos, grupos, pavDe, ambientesNaArea });
  const conexaoValida = ({ source, target }) => !!tipoLigacao(source, target);
  // O destino é o nó sob o ponteiro quando o usuário solta a seta — corpo do nó
  // inteiro, sem alça de recepção.
  const terminarLigacao = (evento, estado) => {
    setOrigemLigacao(null);
    const ponto = evento.changedTouches?.[0] ?? evento;
    const alvo = document.elementFromPoint(ponto.clientX, ponto.clientY)?.closest(".react-flow__node")?.getAttribute("data-id");
    if (alvo && estado.fromNode) ligar({ source: estado.fromNode.id, target: alvo });
  };
  // Fim do arrasto de nós: ambiente solto largado em cima de outro ambiente solto
  // (do mesmo pavimento) forma um grupo com ele; em cima de um grupo do mesmo
  // pavimento entra nele; em cima da lista lateral, volta pra lista; do contrário
  // só guarda a nova posição de tudo que foi arrastado.
  const soltarNo = (evento, _no, arrastadosRecebidos) => {
    let arrastados = arrastadosRecebidos;
    // Faixa arrastada: a origem do pavimento anda o mesmo tanto que a faixa andou.
    if (_no.type === "faixa") {
      const ini = arrastoFaixa.current;
      const pavId = _no.id.slice("faixa-".length);
      arrastoFaixa.current = null;
      if (!ini || ini.id !== _no.id) return;
      const o = origemFaixa(pavId);
      setPavAtivoId(pavId);
      despachar({ type: "SET_FAIXA_POS", pavimentoId: pavId, pos: arredondar({ x: o.x + _no.position.x - ini.pos.x, y: o.y + _no.position.y - ini.pos.y }) });
      return;
    }
    if (pavDe.get(_no.id)) setPavAtivoId(pavDe.get(_no.id));
    const ponto = evento.changedTouches?.[0] ?? evento;
    // O próprio nó arrastado fica sob o ponteiro — procura o que está por baixo.
    const abaixo = document.elementsFromPoint(ponto.clientX, ponto.clientY);
    const ambientesArrastados = arrastados.filter((n) => n.type === "ambiente").map((n) => n.id);
    const mesmoPav = (id) => !!id && ambientesArrastados.every((a) => pavDe.get(a) === pavDe.get(id));
    const grupoAbaixo = abaixo.map((el) => el.closest(".react-flow__node-grupo")).find(Boolean)?.getAttribute("data-id");
    const grupoValido = mesmoPav(grupoAbaixo) ? grupoAbaixo : null;
    const naLista = abaixo.some((el) => el.closest(".fx-lista"));
    // Outro ambiente solto por baixo do ponteiro: os dois viram um grupo.
    const ambienteAbaixo = abaixo
      .map((el) => el.closest(".react-flow__node-ambiente"))
      .find((n) => n && !ambientesArrastados.includes(n.getAttribute("data-id")))
      ?.getAttribute("data-id");
    const ambienteValido = mesmoPav(ambienteAbaixo) ? ambienteAbaixo : null;
    if (ambientesArrastados.length && !grupoValido && !naLista && ambienteValido) {
      agruparAmbientes(ambienteValido, ambientesArrastados);
      arrastados = arrastados.filter((n) => n.type !== "ambiente");
    } else if (ambientesArrastados.length && (grupoValido || naLista)) {
      moverParaGrupo(ambientesArrastados, grupoValido || null);
      arrastados = arrastados.filter((n) => n.type !== "ambiente");
    }
    // Posições (relativas à origem da faixa), um despacho por pavimento.
    porPavimento(arrastados.map((n) => n.id), pavDe).forEach((lista, pavimentoId) => {
      const o = origemFaixa(pavimentoId);
      despachar({
        type: "SET_POSICOES_FLUXO",
        pavimentoId,
        posicoes: Object.fromEntries(
          lista.map((id) => {
            const { x, y } = arrastados.find((n) => n.id === id).position;
            return [id, arredondar({ x: x - o.x, y: y - o.y })];
          })
        ),
      });
    });
  };
  const ligar = ({ source, target }) => {
    const tipo = tipoLigacao(source, target);
    const pavimentoId = pavDe.get(source);
    if (tipo === "entre-pavimentos") despachar({ type: "LIGAR_ENTRE_PAVIMENTOS", pavimentoId, acessoId: source, destinoId: target });
    else if (tipo === "local") {
      if (grupos.some((g) => g.id === source)) despachar({ type: "LIGAR_GRUPO", pavimentoId, grupoId: source, acessoId: target });
      else if (ambientesNaArea.has(source)) despachar({ type: "LIGAR_AMBIENTE", pavimentoId, ambienteId: source, acessoId: target });
      else despachar({ type: "MOVER_ACESSO", pavimentoId, acessoId: source, novoAlimentaEm: target });
    }
  };
  const desligar = (removidas) =>
    removidas.forEach((e) => {
      setSetaSelecionada(null);
      const pavimentoId = pavDe.get(e.source);
      if (grupos.some((g) => g.id === e.source)) despachar({ type: "LIGAR_GRUPO", pavimentoId, grupoId: e.source, acessoId: null });
      else if (ambientesNaArea.has(e.source)) despachar({ type: "LIGAR_AMBIENTE", pavimentoId, ambienteId: e.source, acessoId: null });
      else if (acessos.find((a) => a.id === e.source)?.ligadoA === e.target) despachar({ type: "LIGAR_ENTRE_PAVIMENTOS", pavimentoId, acessoId: e.source, destinoId: null });
      else despachar({ type: "MOVER_ACESSO", pavimentoId, acessoId: e.source, novoAlimentaEm: null });
    });

  // Maximizar/restaurar e reenquadrar o pavimento em edição quando o tamanho da
  // área muda. Esc restaura — a menos que haja menu, confirmação ou formulário
  // aberto por cima (eles fecham primeiro com o próprio Esc).
  const alternarMaximizado = () => {
    setMaximizado((v) => !v);
    requestAnimationFrame(() => requestAnimationFrame(() => enquadrarFaixa(rf, pavAtivoId, 250)));
  };
  useEffect(() => {
    if (!maximizado || menu || confirmacao || editAmb) return undefined;
    const aoTeclar = (e) => {
      if (e.key === "Escape") setMaximizado(false);
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [maximizado, menu, confirmacao, editAmb]);

  const [sobreSoltos, setSobreSoltos] = useState(false);
  const alvosGrupo = pavs.flatMap((p) => (p.grupos || []).map((g) => ({ id: g.id, label: `${p.label} · ${g.nome}` })));

  return (
    <div className={`fx-raiz ${maximizado ? "fx-raiz-max" : ""}`}>
      {/* Topo */}
      <div className="fx-topo">
        <div className="fx-topo-esq">
          <button type="button" onClick={onVoltar} className="se-icon-botao" title="Voltar para Pavimentos">
            <Icon svg={arrowLeftIconSvg} />
          </button>
          <span className="fx-topo-nome">{estrutura?.nome}</span>
          <select
            value={pavAtivo.id}
            title="Pavimento em edição"
            onChange={(e) => {
              setPavAtivoId(e.target.value);
              enquadrarFaixa(rf, e.target.value, 300);
            }}
            className="fx-topo-select"
          >
            {pavs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <span className="fx-topo-info">
            Quantidade de saídas (automático): <strong>{Math.max(1, contarSaidasPavimento(pavAtivo.acessos))}</strong>
          </span>
          {salvando && <span className="fx-salvando">Salvando…</span>}
        </div>
        <div className="fx-topo-dir">
          {erEstrutura && (
            <span
              className="fx-topo-info"
              title="A escada/rampa é dimensionada uma única vez por estrutura, com a população do pavimento mais populoso (sem o piso de descarga) — vale pra todas."
            >
              Escada/rampa (única): <strong>{erEstrutura.pop} pessoas</strong> · {erEstrutura.pavimento.label} · <strong className="fx-vermelho">{fmtM(erEstrutura.er.la)}</strong>
            </span>
          )}
          <button type="button" className="se-botao" onClick={() => setListaAberta((v) => !v)}>
            {listaAberta ? "Ocultar lista" : `Ambientes (${soltos.length})`}
          </button>
          <button type="button" className="se-botao" onClick={alternarMaximizado} title={maximizado ? "Voltar ao tamanho normal (Esc)" : "Ocupar a janela inteira do painel"}>
            {maximizado ? "Restaurar" : "Maximizar"}
          </button>
          <PisoDescargaSwitch
            checked={!!pavAtivo.pisoDescarga}
            onChange={(v) => despachar({ type: "SET_PISO_DESCARGA", pavimentoId: pavAtivo.id, valor: v })}
          />
        </div>
      </div>

      <FluxoCtx.Provider value={ctx}>
        <div className="fx-corpo">
          {/* Ambientes (lista lateral) */}
          {listaAberta && (
            <aside {...dropProps(null, setSobreSoltos)} className={`fx-lista ${sobreSoltos ? "fx-lista-sobre" : ""}`}>
              <div className="fx-lista-cab">
                <div className="fx-lista-titulo">Ambientes</div>
                <div className="fx-lista-texto">Ambientes nesta lista serão considerados com comunicação direta para uma área segura.</div>
              </div>
              <div className="fx-lista-busca">
                <CampoBusca value={filtroSoltos} onChange={setFiltroSoltos} placeholder="Filtrar ambientes da lista…" />
              </div>
              <div className="fx-lista-corpo">
                {pavs.map((p) => {
                  const lista = soltosFiltrados.filter((a) => pavDe.get(a.id) === p.id);
                  if (!lista.length) return null;
                  return (
                    <div key={p.id} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <div className="fx-lista-pav">{p.label}</div>
                      {lista.map((a) => (
                        <AmbienteLinha key={a.id} amb={a} noGrupo={false} />
                      ))}
                    </div>
                  );
                })}
                {soltos.length === 0 && <div className="fx-lista-vazio">Todos os ambientes já estão na área de trabalho.</div>}
                {soltos.length > 0 && soltosFiltrados.length === 0 && <div className="fx-lista-vazio">Nenhum ambiente da lista corresponde à busca.</div>}
              </div>
              {selecionados.size > 0 && (
                <div className="fx-lista-selecao">
                  <strong>
                    {selecionados.size} ambiente{selecionados.size > 1 ? "s" : ""} selecionado{selecionados.size > 1 ? "s" : ""}
                  </strong>
                  <select value={alvoSelecao} onChange={(e) => setAlvoSelecao(e.target.value)} className="fx-select">
                    <option value="">Mover para...</option>
                    <option value={NOVO_GRUPO}>+ Novo grupo (no pavimento de cada um)</option>
                    <option value={NA_AREA}>— Soltos na área —</option>
                    <option value={SEM_GRUPO}>— Voltar pra lista —</option>
                    {alvosGrupo.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                  <div className="fx-lista-selecao-linha">
                    <button type="button" className="se-botao" disabled={!alvoSelecao} onClick={moverSelecionados}>
                      <Icon svg={checkIconSvg} /> Mover
                    </button>
                    <button type="button" className="fx-link" onClick={limparSelecao}>
                      Cancelar seleção
                    </button>
                  </div>
                </div>
              )}
            </aside>
          )}

          {/* Área de trabalho */}
          <div
            ref={wrapRef}
            onDragOver={(e) => {
              if (e.dataTransfer.types.includes(MIME_AMBIENTES)) e.preventDefault();
            }}
            onDrop={soltarNoFundo}
            className={`fx-area ${origemLigacao ? "fx-conectando" : ""}`}
          >
            <ReactFlow
              nodes={nodesComFaixas}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={aoMudarNos}
              onNodeDragStart={(_, no) => {
                if (no.type === "faixa") arrastoFaixa.current = { id: no.id, pos: { ...no.position } };
              }}
              onNodeDragStop={soltarNo}
              nodeDragThreshold={4}
              onNodeMouseEnter={(_, no) => setNoHover(no.id)}
              onNodeMouseLeave={() => setNoHover(null)}
              onConnectStart={(_, { nodeId }) => setOrigemLigacao(nodeId)}
              onConnectEnd={terminarLigacao}
              onEdgesDelete={desligar}
              // Delete só desliga a seta selecionada — nó some pelo botão de
              // lixeira (com confirmação), nunca por um Delete solto, e
              // selecionar um nó não leva as setas dele junto.
              onBeforeDelete={async ({ edges: es }) => ({ nodes: [], edges: es.filter((e) => e.id === setaSelecionada) })}
              onEdgeClick={(_, edge) => setSetaSelecionada(edge.id)}
              onNodeClick={(_, no) => {
                setSetaSelecionada(null);
                setMenu(null);
                const pavId = no.type === "faixa" ? no.data.pav.id : pavDe.get(no.id);
                if (pavId) setPavAtivoId(pavId);
              }}
              // Clique no fundo: se caiu dentro da faixa de um pavimento, ele passa a ser o em edição.
              onPaneClick={(e) => {
                setSetaSelecionada(null);
                setMenu(null);
                const ponto = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY });
                const f = faixas.find((x) => distanciaAteRetangulo(ponto, x) === 0);
                if (f) setPavAtivoId(f.pav.id);
              }}
              onPaneContextMenu={abrirMenu}
              onNodeContextMenu={(e, no) => {
                if (no.type === "faixa") abrirMenu(e);
              }}
              onMoveStart={() => setMenu(null)}
              edgesReconnectable={false}
              deleteKeyCode={["Delete", "Backspace"]}
              // Abre focado na faixa do pavimento clicado (ou mostrando tudo).
              fitView={!focoPavId}
              fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
              minZoom={0.1}
              onInit={focoPavId ? (inst) => enquadrarFaixa(inst, focoPavId, 0) : undefined}
            >
              <Background gap={20} />
              <Controls showInteractive={false} />
              <Panel position="top-left" className="fx-barra">
                {OPCOES_CRIAR.map(([op, rotulo]) => (
                  <button key={op} type="button" className="se-botao" onClick={() => criarDaOpcao(op, pavAtivo.id)}>
                    <Icon svg={plusIconSvg} /> {rotulo}
                  </button>
                ))}
                <span className="fx-barra-em">
                  em <strong>{pavAtivo.label}</strong>
                </span>
              </Panel>
              {setaSelecionada && (
                <Panel position="top-center">
                  <button type="button" className="se-botao" onClick={() => desligar(edges.filter((e) => e.id === setaSelecionada))}>
                    <Icon svg={xIconSvg} /> Desligar seta selecionada
                  </button>
                </Panel>
              )}
            </ReactFlow>
            {menu && (
              <div style={{ left: menu.x, top: menu.y }} onContextMenu={(e) => e.preventDefault()} className="fx-menu">
                <span>
                  Criar em <strong>{pavPorId.get(menu.pavId)?.label}</strong>
                </span>
                <div className="fx-menu-itens">
                  {OPCOES_CRIAR.map(([op, rotulo]) => (
                    <button
                      key={op}
                      type="button"
                      className="se-botao"
                      onClick={() => {
                        criarDaOpcao(op, menu.pavId, menu.ponto);
                        setMenu(null);
                      }}
                    >
                      <Icon svg={plusIconSvg} /> {rotulo}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </FluxoCtx.Provider>

      {escolhaGrupoId && grupos.find((g) => g.id === escolhaGrupoId) && (() => {
        const grupo = grupos.find((g) => g.id === escolhaGrupoId);
        const pavId = pavDe.get(grupo.id);
        const nomeGrupo = new Map(grupos.map((g) => [g.id, g.nome]));
        const candidatos = ambientes
          .filter((a) => pavDe.get(a.id) === pavId && a.grupoId !== grupo.id)
          .map((a) => ({
            amb: a,
            pop: calcPopAmb(a, TAXA_POPULACIONAL),
            onde: a.grupoId ? `em ${nomeGrupo.get(a.grupoId) || "outro grupo"}` : posDe(a.id) ? "solto na área" : "na lista",
          }));
        return (
          <EscolherAmbientesModal
            grupo={grupo}
            candidatos={candidatos}
            onFechar={() => setEscolhaGrupoId(null)}
            onAdicionar={(ids) => {
              moverParaGrupo(ids, grupo.id);
              setEscolhaGrupoId(null);
            }}
            onNovo={() => {
              setEscolhaGrupoId(null);
              criarAmbiente(grupo.id);
            }}
          />
        );
      })()}

      {confirmacao && (
        <ConfirmacaoModal
          titulo={confirmacao.titulo}
          texto={confirmacao.texto}
          rotuloConfirmar={confirmacao.rotulo}
          onConfirmar={() => {
            confirmacao.onConfirmar();
            setConfirmacao(null);
          }}
          onCancelar={() => setConfirmacao(null)}
        />
      )}

      {editAmb && (
        <div className="se-modal-overlay" onClick={() => setEditAmb(null)}>
          <div onClick={(e) => e.stopPropagation()} className="se-ambiente-modal">
            <div className="se-ambiente-modal-header">
              <InlineEditableNome value={editAmb.nome} onCommit={renomearAmbiente} className="se-ambiente-modal-nome" />
              <button type="button" onClick={() => setEditAmb(null)} className="se-icon-botao">
                <Icon svg={xIconSvg} />
              </button>
            </div>
            <AmbienteForm
              initial={editAmb}
              seNorma={seNorma}
              ocupacoes={ocupacoes}
              larguras={LARGURAS_MINIMAS}
              onSave={(changes) => {
                despachar({ type: "UPDATE_AMBIENTE_SE", pavimentoId: pavDe.get(editAmb.id), ambienteId: editAmb.id, changes });
                setEditAmb(null);
              }}
              onCancel={() => setEditAmb(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// `pavimentos` = pavimentos CRUS da estrutura (dados.pavimentos filtrados, já no
// formato do fluxograma — ver pavimentosCompletos), na ordem do estado
// (subsolos, térreo, demais) — o fluxo lê/grava `grupos`, `acessos`, `fluxoPos`
// e `pisoDescarga` tal como vivem em `dados`. `focoPavId`: pavimento em que a
// tela abre. Detecção de incêndio e chuveiros automáticos não aparecem aqui:
// vêm das Medidas de Segurança da estrutura (ver SaidaEmergenciaPage.jsx).
export default function FluxogramaSaidas(props) {
  return (
    <ReactFlowProvider>
      <Fluxograma {...props} />
    </ReactFlowProvider>
  );
}
