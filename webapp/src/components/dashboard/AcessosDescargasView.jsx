import { useState } from "react";
import { DndContext, useDraggable, useDroppable, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import Icon from "../Icon";
import { AmbienteForm, DivBadge, fmtM } from "./seShared";
import { calcPopAmb, calcNoAcesso, calcNoAmbientePT, calcPortaNoAcesso, contarSaidasPavimento, tipoDoNo } from "../../data/se_calc";
import { aplicarAcaoSaida, idAcesso, idAmbienteSE } from "../../lib/seReducer";
import { salvarComRetry } from "../../lib/projectData";
import gripIconSvg from "../../assets/icons/grip-icon.svg?raw";
import chevronDownIconSvg from "../../assets/icons/chevron-down-icon.svg?raw";
import chevronRightIconSvg from "../../assets/icons/chevron-right-icon.svg?raw";
import pencilIconSvg from "../../assets/icons/pencil-icon.svg?raw";
import trashIconSvg from "../../assets/icons/trash-icon.svg?raw";
import plusIconSvg from "../../assets/icons/plus-icon.svg?raw";
import arrowLeftIconSvg from "../../assets/icons/arrow-left-icon.svg?raw";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";

/**
 * AcessosDescargasView.jsx — árvore de Acessos e Descargas de um pavimento
 * (Ambiente -> Acesso -> Acesso/Saída ou Escada-Rampa), portada de
 * ETOS.FireUtils/src/pages/medidas/AcessosDescargasView.jsx.
 *
 * Diferença de arquitetura pro site: lá existe um reducer vivo
 * (useReducer + broadcast em tempo real entre abas). Aqui não há reducer
 * nem sessão compartilhada — cada ação (arrastar, renomear, criar/remover)
 * aplica lib/seReducer.aplicarAcaoSaida sobre uma cópia local de `dados`
 * e persiste na hora via lib/projectData.salvarComRetry (compare-and-swap
 * pela versão da linha, com uma segunda tentativa em cima da versão
 * atual se a primeira esbarrar num conflito — ver docstring de
 * salvarComRetry). `onProjetoAtualizado` propaga o novo `{...projeto,
 * dados, version}` pro Dashboard, que é quem guarda a fonte de verdade
 * (estado.linha) — assim reabrir a árvore ou fechar e reabrir o popup de
 * ambiente sempre parte do dado mais recente.
 */

function acessosFilhos(acessos, parentId) {
  return acessos.filter((a) => a.alimentaEm === parentId);
}
function ambientesDe(ambientes, acessoId) {
  return ambientes.filter((a) => a.acessoId === acessoId);
}
// Todo o subconjunto que um Acesso arrasta consigo (ele mesmo + descendentes)
// — usado só pra impedir soltar um nó dentro do seu próprio galho (ciclo).
function descendentesDe(acessoId, acessos) {
  const set = new Set([acessoId]);
  acessosFilhos(acessos, acessoId).forEach((f) => descendentesDe(f.id, acessos).forEach((id) => set.add(id)));
  return set;
}

// ── Nome editável inline — clique vira input; Enter/blur salva, Escape
// cancela — em vez de window.prompt (diálogo nativo do navegador).
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

// Quebra "ACESSO/DESCARGA" -> "ACESSO/" + quebra de linha + "DESCARGA"
// (idem "ESCADA/RAMPA") — os únicos rótulos com "/" que chegam aqui (ver
// tipoDoNo em data/se_calc.js). Sem "/", mostra o texto como veio (ex.: "Portas").
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

export function StatCol({ label, value, big }) {
  return (
    <div className="se-stat-col">
      <div className="se-stat-col-label">{label}</div>
      <div className={`se-stat-col-value ${big ? "se-stat-col-value-big" : ""}`}>{value}</div>
    </div>
  );
}

// ── Ambiente (folha da árvore) — arrastável, card inteiro clicável ─────
function AmbienteChip({ amb, taxaPopulacional, larguras, onEdit, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `amb:${amb.id}`,
    data: { kind: "amb", id: amb.id },
  });
  const pop = calcPopAmb(amb, taxaPopulacional);
  const { capPT, pt } = calcNoAmbientePT(amb, taxaPopulacional, larguras);
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={() => onEdit(amb)}
      className={`se-card se-card-leaf se-card-header ${isDragging ? "se-dragging" : ""}`}
    >
      <div className="se-card-header-esq">
          <button {...attributes} {...listeners} onClick={(e) => e.stopPropagation()} className="se-grip" title="Arrastar ambiente">
            <Icon svg={gripIconSvg} />
          </button>
          <span className="se-ambiente-nome">{amb.nome}</span>
          <DivBadge label={amb.divisao || "?"} />
        
        <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(amb.id);
        }}
        className="se-card-lixeira se-icon-botao"
      >
        <Icon svg={trashIconSvg} />
      </button>
      </div>
      <div className="se-card-header-dir">
        <span className="se-label">PORTA</span>
        <span className="se-sep">|</span>
        <span>C {capPT}</span>
        <span className="se-sep">|</span>
        <span>{pop} pessoas</span>
        <span className="se-sep">|</span>
        <span className="se-ambiente-up">{pt.n} UP</span>
        <span className="se-sep">|</span>
        <span>
          L. MÍN.: <strong className="se-vermelho">{fmtM(pt.la)}</strong>
        </span>
      </div>
    </div>
  );
}

// ── Acesso/Saída/Escada-Rampa (nó da árvore) — arrastável, soltável,
// cabeçalho inteiro retrai/expande. Só a raiz pode abrir novos Acessos
// filhos; qualquer nó pode receber ambientes direto.
function AcessoCard({
  acesso,
  ambientes,
  acessos,
  taxaPopulacional,
  larguras,
  pisoDescarga,
  onRenomear,
  onRemover,
  onCriarAcessoFilho,
  pavimentoId,
  onEditAmbiente,
  onRemoveAmbiente,
  onCreateAmbiente,
  colapsados,
  toggleColapsado,
}) {
  const { tipo, label } = tipoDoNo(acesso, pisoDescarga);
  const { pop, cap, capValor, dim } = calcNoAcesso(acesso.id, ambientes, acessos, taxaPopulacional, larguras, tipo);
  // Porta do box: reaproveita o mesmo N de UP do AD/ER (não recalcula
  // população) — só a capacidade de unidade de passagem (C) usada pra
  // achar a largura mínima é a normativa de PORTA (cap.PT), não a de
  // AD/ER já mostrada acima.
  const porta = calcPortaNoAcesso(dim.n, larguras);
  const filhos = acessosFilhos(acessos, acesso.id);
  const filhosAmbientes = ambientesDe(ambientes, acesso.id);
  const isRaiz = acesso.alimentaEm === null;

  const { attributes, listeners, setNodeRef: setDragRef, transform, isDragging } = useDraggable({
    id: `acs:${acesso.id}`,
    data: { kind: "acs", id: acesso.id },
  });
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-acs:${acesso.id}`,
    data: { kind: "acesso", id: acesso.id },
  });
  const aberto = !colapsados[acesso.id];
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;

  const remover = (e) => {
    e.stopPropagation();
    if (window.confirm(`Remover "${acesso.nome}"? Os ambientes/acessos dentro dele ficarão sem posição, mas não serão apagados.`)) {
      onRemover(acesso.id);
    }
  };

  return (
    <div
      ref={(node) => {
        setDragRef(node);
        setDropRef(node);
      }}
      style={style}
      className={`se-card ${isOver ? "se-card-over" : ""} ${isDragging ? "se-dragging" : ""} ${isRaiz ? "" : "se-acesso-card-filho"}`}
    >
      <div className="se-card-header" onClick={() => toggleColapsado(acesso.id)}>
        <div className="se-card-header-esq">
          <button {...attributes} {...listeners} onClick={(e) => e.stopPropagation()} className="se-grip" title="Arrastar (leva tudo dentro)">
            <Icon svg={gripIconSvg} />
          </button>
          <Icon svg={aberto ? chevronDownIconSvg : chevronRightIconSvg} className="se-chevron" />
          <InlineEditableNome value={acesso.nome} onCommit={(novoNome) => onRenomear(acesso.id, novoNome)} className="se-acesso-nome" />
        </div>
        {/* Duas linhas alinhadas em grid — Acesso/Descarga (ou Escada/Rampa)
            em cima, Portas embaixo — em vez de espremer as duas dimensões
            (fluxo + porta) numa linha só com rótulos "C (PORTA)"/"PORTA". */}
        <div className="se-card-header-dir">
          <div className="se-acesso-stats-grid">
            <div className="se-acesso-stats-label">
              <LabelQuebrado texto={label} />
            </div>
            <StatCol label="POP." value={pop} />
            <StatCol label="C" value={capValor} />
            <StatCol label="U.P." value={dim.n} />
            <StatCol label="LARGURA MÍN." value={fmtM(dim.la)} big />
            <div className="se-acesso-stats-label">Portas</div>
            <StatCol label="POP." value={pop} />
            <StatCol label="C" value={cap.PT} />
            <StatCol label="U.P." value={dim.n} />
            <StatCol label="LARGURA MÍN." value={fmtM(porta.la)} big />
          </div>
        </div>
        <button onClick={remover} className="se-card-lixeira se-icon-botao">
          <Icon svg={trashIconSvg} />
        </button>
      </div>
      {aberto && (
        <div className="se-card-body">
          {filhos.map((f) => (
            <AcessoCard
              key={f.id}
              acesso={f}
              ambientes={ambientes}
              acessos={acessos}
              taxaPopulacional={taxaPopulacional}
              larguras={larguras}
              pisoDescarga={pisoDescarga}
              onRenomear={onRenomear}
              onRemover={onRemover}
              onCriarAcessoFilho={onCriarAcessoFilho}
              pavimentoId={pavimentoId}
              onEditAmbiente={onEditAmbiente}
              onRemoveAmbiente={onRemoveAmbiente}
              onCreateAmbiente={onCreateAmbiente}
              colapsados={colapsados}
              toggleColapsado={toggleColapsado}
            />
          ))}
          {filhosAmbientes.map((a) => (
            <AmbienteChip key={a.id} amb={a} taxaPopulacional={taxaPopulacional} larguras={larguras} onEdit={onEditAmbiente} onRemove={onRemoveAmbiente} />
          ))}
          {filhos.length === 0 && filhosAmbientes.length === 0 && <div className="se-vazio-italico">Arraste ambientes para cá.</div>}
          <div className="se-acesso-acoes">
            {isRaiz && (
              <button type="button" className="se-botao" onClick={() => onCriarAcessoFilho(acesso.id)}>
                <Icon svg={plusIconSvg} /> CRIAR ACESSO
              </button>
            )}
            <button type="button" className="se-botao" onClick={() => onCreateAmbiente(acesso.id)}>
              <Icon svg={plusIconSvg} /> ADICIONAR AMBIENTE
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RootDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: "drop-root", data: { kind: "root" } });
  return (
    <div ref={setNodeRef} className={`se-root-drop ${isOver ? "se-root-drop-over" : ""}`}>
      Solte um acesso aqui para desprendê-lo, tornando-o uma nova raiz da árvore
    </div>
  );
}

function SemAcessoDropZone({ ambientes, taxaPopulacional, larguras, onEdit, onRemove }) {
  const { setNodeRef, isOver } = useDroppable({ id: "drop-null", data: { kind: "null" } });
  return (
    <div ref={setNodeRef} className={`se-sem-acesso ${isOver ? "se-sem-acesso-over" : ""}`}>
      {ambientes.length === 0 && <div className="se-vazio-italico">Todos os ambientes já estão posicionados na árvore.</div>}
      {ambientes.map((a) => (
        <AmbienteChip key={a.id} amb={a} taxaPopulacional={taxaPopulacional} larguras={larguras} onEdit={onEdit} onRemove={onRemove} />
      ))}
    </div>
  );
}

function PisoDescargaSwitch({ checked, onChange }) {
  return (
    <div className="se-piso-descarga">
      <span>
        Este pavimento é o <strong>piso de descarga</strong>?
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

// ── Seção de detalhe do pavimento ───────────────────────────────────────
// Vive direto na página de Saída de Emergência (ver SaidaEmergenciaPage.jsx)
// — não é mais um popup: só o formulário de Ambiente (`editAmb` abaixo)
// continua sendo um popup de verdade. `pav` é o pavimento cru
// (dados.pavimentos[i]). `onProjetoAtualizado` recebe a linha inteira já
// atualizada (dados + version novos) depois de cada ação persistida com
// sucesso. `onVoltar` volta pra lista de pavimentos.
export default function AcessosDescargasView({ projeto, pav, seNorma, ocupacoes, onVoltar, onProjetoAtualizado, adicionarToast }) {
  const { TAXA_POPULACIONAL, LARGURAS_MINIMAS } = seNorma;
  const ambientes = pav.ambientes || [];
  const acessos = pav.acessos || [];
  const [editAmb, setEditAmb] = useState(null);
  const [colapsados, setColapsados] = useState({});
  const [salvando, setSalvando] = useState(false);
  const toggleColapsado = (id) => setColapsados((prev) => ({ ...prev, [id]: !prev[id] }));

  const raizes = acessosFilhos(acessos, null);
  const semAcesso = ambientes.filter((a) => !a.acessoId);
  const nSaidas = Math.max(1, contarSaidasPavimento(acessos));
  const rotuloRaiz = pav.pisoDescarga ? "Saída" : "Escada/Rampa";

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  // Aplica a ação e persiste na hora — se a escrita falhar (versão
  // desatualizada, sem rede), avisa e NÃO aplica a mudança local, pra
  // tela nunca ficar mostrando algo que não foi salvo de verdade.
  // salvarComRetry já absorve o "falso conflito de versão" (outra aba/o
  // site salvou algo nesse meio-tempo, sem conflito real de conteúdo) —
  // só chega a dar erro aqui se a segunda tentativa também falhar.
  async function despachar(action) {
    setSalvando(true);
    try {
      const { dados: novosDados, version: novaVersao } = await salvarComRetry(projeto.id, projeto, (dados) =>
        aplicarAcaoSaida(dados, action)
      );
      onProjetoAtualizado({ ...projeto, dados: novosDados, version: novaVersao });
    } catch (erro) {
      adicionarToast?.({ tipo: "erro", titulo: "Não foi possível salvar", mensagem: erro.message, duracaoMs: 9000 });
    } finally {
      setSalvando(false);
    }
  }

  const criarRaiz = () =>
    despachar({ type: "CRIAR_SAIDA", pavimentoId: pav.id, id: idAcesso(), nome: `${rotuloRaiz} ${String(raizes.length + 1).padStart(2, "0")}` });

  const criarAcessoFilho = (alimentaEm) => {
    const filhos = acessosFilhos(acessos, alimentaEm);
    despachar({ type: "CRIAR_ACESSO", pavimentoId: pav.id, id: idAcesso(), alimentaEm, nome: `Acesso ${filhos.length + 1}` });
  };

  const renomearAcesso = (acessoId, nome) => despachar({ type: "RENOMEAR_ACESSO", pavimentoId: pav.id, acessoId, nome });
  const removerAcesso = (acessoId) => despachar({ type: "REMOVER_ACESSO", pavimentoId: pav.id, acessoId });

  // `acessoId` opcional: quando vem de dentro de um card de Acesso ("+
  // Adicionar Ambiente" ali dentro), o ambiente já nasce atribuído a ele.
  const criarAmbiente = (acessoId = null) => {
    const id = idAmbienteSE();
    const nome = `Ambiente ${ambientes.length + 1}`;
    const ambiente = { nome, divisao: "", popTipo: "area", area: 0, assentos: 0, popManual: 0, acessoId };
    despachar({ type: "ADD_AMBIENTE_SE", pavimentoId: pav.id, id, ambiente });
    setEditAmb({ id, ...ambiente });
  };
  const removerAmbiente = (id) => {
    despachar({ type: "REMOVE_AMBIENTE_SE", pavimentoId: pav.id, ambienteId: id });
    if (editAmb?.id === id) setEditAmb(null);
  };
  const renomearAmbiente = (novoNome) => {
    despachar({ type: "UPDATE_AMBIENTE_SE", pavimentoId: pav.id, ambienteId: editAmb.id, changes: { nome: novoNome } });
    setEditAmb((prev) => ({ ...prev, nome: novoNome }));
  };

  const handleDragEnd = ({ active, over }) => {
    if (!over) return;
    const activeData = active.data.current;
    const overData = over.data.current;
    if (!activeData || !overData) return;

    if (activeData.kind === "amb") {
      const novoAcessoId = overData.kind === "acesso" ? overData.id : null;
      despachar({ type: "MOVER_AMBIENTE_ACESSO", pavimentoId: pav.id, ambienteId: activeData.id, novoAcessoId });
      return;
    }
    if (activeData.kind === "acs") {
      const acessoId = activeData.id;
      const novoAlimentaEm = overData.kind === "acesso" ? overData.id : null;
      if (novoAlimentaEm === acessoId) return;
      const proibidos = descendentesDe(acessoId, acessos);
      if (novoAlimentaEm !== null && proibidos.has(novoAlimentaEm)) return; // evitaria um ciclo
      despachar({ type: "MOVER_ACESSO", pavimentoId: pav.id, acessoId, novoAlimentaEm });
    }
  };

  return (
    <>
      <div className="se-detalhe-header">
        <div className="se-modal-header-esq">
          <button onClick={onVoltar} className="se-icon-botao" title="Voltar para Pavimentos">
            <Icon svg={arrowLeftIconSvg} />
          </button>
          <span className="se-modal-titulo">{pav.label}</span>
          {salvando && <span className="se-salvando">Salvando…</span>}
        </div>
        <PisoDescargaSwitch
          checked={!!pav.pisoDescarga}
          onChange={(v) => despachar({ type: "SET_PISO_DESCARGA", pavimentoId: pav.id, estruturaId: pav.estruturaId, valor: v })}
        />
      </div>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="se-modal-corpo">
          <div className="se-qtd-saidas">
            Quantidade de saídas (automático): <strong>{nSaidas}</strong>
          </div>

          <div className="se-arvore">
            <RootDropZone />

            <div className="se-raizes">
              {raizes.map((r) => (
                <AcessoCard
                  key={r.id}
                  acesso={r}
                  ambientes={ambientes}
                  acessos={acessos}
                  taxaPopulacional={TAXA_POPULACIONAL}
                  larguras={LARGURAS_MINIMAS}
                  pisoDescarga={!!pav.pisoDescarga}
                  onRenomear={renomearAcesso}
                  onRemover={removerAcesso}
                  onCriarAcessoFilho={criarAcessoFilho}
                  pavimentoId={pav.id}
                  onEditAmbiente={setEditAmb}
                  onRemoveAmbiente={removerAmbiente}
                  onCreateAmbiente={criarAmbiente}
                  colapsados={colapsados}
                  toggleColapsado={toggleColapsado}
                />
              ))}
              {raizes.length === 0 && (
                <div className="se-vazio-grande">Nenhuma {rotuloRaiz.toLowerCase()} criada ainda. Clique abaixo para começar a montar a árvore.</div>
              )}
            </div>

            <div className="se-centralizado">
              <button type="button" className="se-botao" onClick={criarRaiz}>
                <Icon svg={plusIconSvg} /> CRIAR {rotuloRaiz.toUpperCase()}
              </button>
            </div>
          </div>

          <div>
            <div className="se-secao-titulo-linha">
              <div className="se-secao-titulo">Ambientes sem acesso atribuído</div>
              <button type="button" className="se-botao" onClick={() => criarAmbiente()}>
                <Icon svg={plusIconSvg} /> Adicionar Ambiente
              </button>
            </div>
            <SemAcessoDropZone ambientes={semAcesso} taxaPopulacional={TAXA_POPULACIONAL} larguras={LARGURAS_MINIMAS} onEdit={setEditAmb} onRemove={removerAmbiente} />
          </div>
        </div>
      </DndContext>

      {editAmb && (
        <div className="se-modal-overlay" onClick={() => setEditAmb(null)}>
          <div onClick={(e) => e.stopPropagation()} className="se-ambiente-modal">
            <div className="se-ambiente-modal-header">
              <InlineEditableNome value={editAmb.nome} onCommit={renomearAmbiente} className="se-ambiente-modal-nome" />
              <button onClick={() => setEditAmb(null)} className="se-icon-botao">
                <Icon svg={xIconSvg} />
              </button>
            </div>
            <AmbienteForm
              initial={editAmb}
              seNorma={seNorma}
              ocupacoes={ocupacoes}
              larguras={LARGURAS_MINIMAS}
              onSave={(changes) => {
                despachar({ type: "UPDATE_AMBIENTE_SE", pavimentoId: pav.id, ambienteId: editAmb.id, changes });
                setEditAmb(null);
              }}
              onCancel={() => setEditAmb(null)}
            />
          </div>
        </div>
      )}
    </>
  );
}
