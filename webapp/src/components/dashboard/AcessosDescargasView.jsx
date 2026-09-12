import { useState } from "react";
import { DndContext, useDraggable, useDroppable, PointerSensor, useSensor, useSensors, pointerWithin } from "@dnd-kit/core";
import Icon from "../Icon";
import { AmbienteForm, DivBadge, fmtM } from "./seShared";
import { calcPopAmb, calcNoAmbientePT, calcDimsAcesso, dimsDoAcesso, contarSaidasPavimento } from "../../data/se_calc";
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
import exitBoxIconSvg from "../../assets/icons/exit-box-icon.svg?raw";
import perfilIconSvg from "../../assets/icons/perfil-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

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

// Achata a árvore de Acessos/Saídas em opções de <select> (indentadas por
// profundidade) — usado pela barra de mover-em-massa, pra listar todo
// Acesso/Saída/Escada-Rampa do pavimento como destino possível.
function listarAcessosParaSelect(acessos, parentId = null, profundidade = 0) {
  return acessosFilhos(acessos, parentId).flatMap((a) => [
    { id: a.id, label: `${"— ".repeat(profundidade)}${a.nome}` },
    ...listarAcessosParaSelect(acessos, a.id, profundidade + 1),
  ]);
}

const ALVO_SEM_ACESSO = "__sem_acesso__";

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

// Checkbox próprio (botão + ícone) em vez de <input type="checkbox"> nativo
// — o nativo herda a cor de fundo do tema do sistema operacional (fica
// branco em vez de escuro), sem jeito confiável de sobrescrever entre
// navegadores só com CSS.
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

export function StatCol({ label, value, big }) {
  return (
    <div className="se-stat-col">
      <div className="se-stat-col-label">{label}</div>
      <div className={`se-stat-col-value ${big ? "se-stat-col-value-big" : ""}`}>{value}</div>
    </div>
  );
}

// ── Ambiente (folha da árvore) — arrastável, card inteiro clicável ─────
// Só mostra UP (no lugar da ocupação, no cabeçalho) + população + largura
// mínima da porta — capacidade (C) e o código de divisão saíram do card
// (continuam editáveis no formulário, só não aparecem mais aqui). O
// checkbox de seleção fica fora do drag handle e do clique de editar —
// marcar vários ambientes (inclusive em Acessos diferentes) habilita a
// barra de "mover selecionados" no rodapé (ver moverSelecionados). Dentro
// de um Acesso/Saída, o botão de canto é "desvincular" (volta pra "sem
// acesso atribuído" — ver onDesvincular); só quando já está órfão
// (`orfao`) é que vira exclusão de verdade, pra evitar apagar por engano
// um ambiente que só precisava trocar de lugar na árvore. Com pelo menos
// um ambiente já selecionado (`modoSelecao`), clicar em qualquer lugar do
// card seleciona/desmarca em vez de abrir o formulário — só assim dá pra
// marcar vários rápido, sem mirar no checkbox de cada um.
function AmbienteChip({ amb, taxaPopulacional, larguras, onEdit, onRemove, onDesvincular, orfao, selecionado, onToggleSelecao, modoSelecao }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `amb:${amb.id}`,
    data: { kind: "amb", id: amb.id },
  });
  const pop = calcPopAmb(amb, taxaPopulacional);
  const { pt } = calcNoAmbientePT(amb, taxaPopulacional, larguras);
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={() => (modoSelecao ? onToggleSelecao(amb.id) : onEdit(amb))}
      className={`se-card se-card-leaf se-card-header ${selecionado ? "se-card-selecionado" : ""} ${isDragging ? "se-dragging" : ""}`}
    >
      <div className="se-card-header-esq">
        <button {...attributes} {...listeners} onClick={(e) => e.stopPropagation()} className="se-grip" title="Arrastar ambiente">
          <Icon svg={gripIconSvg} />
        </button>
        <Checkbox checked={selecionado} onChange={() => onToggleSelecao(amb.id)} title="Selecionar pra mover em massa" />
        <span className="se-ambiente-nome">{amb.nome}</span>
        <DivBadge label={`${pt.n} UP`} />
        {amb.origem === "manual" && (
          <span className="se-badge-manual" title="Ambiente criado manualmente (não veio do Revit)">
            <Icon svg={perfilIconSvg} />
          </span>
        )}
      </div>
      <div className="se-card-header-dir">
        <span>{pop} pessoas</span>
        <span className="se-sep">|</span>
        <span className="se-ambiente-portas">
          PORTAS: <strong className="se-ambiente-portas-valor">{fmtM(pt.la)}</strong>
        </span>
      </div>
      {orfao ? (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove(amb.id);
          }}
          className="se-card-lixeira se-icon-botao"
          title="Excluir ambiente"
        >
          <Icon svg={trashIconSvg} />
        </button>
      ) : (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDesvincular(amb.id);
          }}
          className="se-card-lixeira se-icon-botao"
          title="Desvincular do Acesso/Saída (volta pra lista sem acesso)"
        >
          <Icon svg={exitBoxIconSvg} />
        </button>
      )}
    </div>
  );
}

// ── Botão de dimensionamento (AD/ER/PT) no cabeçalho de Acesso/Saída —
// liga/desliga qual dimensionamento se aplica àquele nó especificamente
// (um nó pode precisar de mais de um ao mesmo tempo, ex.: o piso de
// descarga que é corredor de saída E chegada da escada). Vermelho
// preenchido = ligado; cinza neutro = desligado.
function DimButton({ label, ativo, onClick }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`se-dim-botao ${ativo ? "se-dim-botao-ativo" : ""}`}
    >
      {label}
    </button>
  );
}

// ── Um par rótulo+valor da linha de larguras mínimas (ex.: "ACESSO/
// DESCARGA  1,20 m") — só aparece quando o dimensionamento correspondente
// está ligado (ver DimButton).
function DimEntry({ label, value }) {
  return (
    <div className="se-dim-entrada">
      <div className="se-stat-col-label">
        <LabelQuebrado texto={label} />
      </div>
      <div className="se-dim-entrada-valor">{value}</div>
    </div>
  );
}

// ── Acesso/Saída/Escada-Rampa (nó da árvore) — arrastável, soltável,
// cabeçalho inteiro retrai/expande. Cada nó decide independentemente
// quais dimensionamentos (AD/ER/PT) se aplicam a ele via `acesso.dims`
// (ver DimButton) — um nó pode precisar de mais de um ao mesmo tempo
// (ex.: o piso de descarga que é ao mesmo tempo corredor de saída e
// chegada da escada que desce até ali). `dimsDoAcesso` resolve o padrão
// (mesmo critério da antiga tipoDoNo) quando o nó ainda não tem `dims`
// gravado (projetos antigos). Só a raiz pode abrir novos Acessos filhos;
// qualquer nó pode receber ambientes direto.
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
  onSetDim,
  pavimentoId,
  onEditAmbiente,
  onRemoveAmbiente,
  onDesvincularAmbiente,
  onCreateAmbiente,
  colapsados,
  toggleColapsado,
  selecionados,
  onToggleSelecaoAmbiente,
}) {
  const dims = dimsDoAcesso(acesso, pisoDescarga);
  const { ad, er, pt, nPorta } = calcDimsAcesso(acesso.id, ambientes, acessos, taxaPopulacional, larguras, dims);
  const entradas = [
    ad && { label: "ACESSO/DESCARGA", value: fmtM(ad.la) },
    pt && { label: "PORTAS", value: fmtM(pt.la) },
    er && { label: "ESCADA/RAMPA", value: fmtM(er.la) },
  ].filter(Boolean);
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
  const toggleDim = (d) => onSetDim(acesso.id, d, !dims[d]);

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
          <DivBadge label={`${nPorta} UP`} />
        </div>
        <div className="se-card-header-dims">
          <DimButton label="AD" ativo={dims.AD} onClick={() => toggleDim("AD")} />
          <DimButton label="ER" ativo={dims.ER} onClick={() => toggleDim("ER")} />
          <DimButton label="PT" ativo={dims.PT} onClick={() => toggleDim("PT")} />
        </div>
        <button onClick={remover} className="se-card-lixeira se-icon-botao">
          <Icon svg={trashIconSvg} />
        </button>
      </div>
      {entradas.length > 0 && (
        <div className="se-dim-entradas">
          {entradas
            .flatMap((e, i) => [
              i > 0 && (
                <span key={`sep-${i}`} className="se-sep">
                  |
                </span>
              ),
              <DimEntry key={e.label} label={e.label} value={e.value} />,
            ])
            .filter(Boolean)}
        </div>
      )}
      {aberto && (
        <div className="se-card-body">
          {/* Ambientes direto deste Acesso vêm antes dos Acessos filhos —
              o que pertence a ele fica visualmente "em cima" do próximo
              nível da árvore, em vez de misturado depois. */}
          {filhosAmbientes.map((a) => (
            <AmbienteChip key={a.id} amb={a} taxaPopulacional={taxaPopulacional} larguras={larguras} onEdit={onEditAmbiente} onRemove={onRemoveAmbiente}
              onDesvincular={onDesvincularAmbiente} orfao={false}
              selecionado={selecionados.has(a.id)} onToggleSelecao={onToggleSelecaoAmbiente} modoSelecao={selecionados.size > 0} />
          ))}
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
              onSetDim={onSetDim}
              pavimentoId={pavimentoId}
              onEditAmbiente={onEditAmbiente}
              onRemoveAmbiente={onRemoveAmbiente}
              onDesvincularAmbiente={onDesvincularAmbiente}
              onCreateAmbiente={onCreateAmbiente}
              colapsados={colapsados}
              toggleColapsado={toggleColapsado}
              selecionados={selecionados}
              onToggleSelecaoAmbiente={onToggleSelecaoAmbiente}
            />
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

function SemAcessoDropZone({ ambientes, taxaPopulacional, larguras, onEdit, onRemove, selecionados, onToggleSelecaoAmbiente }) {
  const { setNodeRef, isOver } = useDroppable({ id: "drop-null", data: { kind: "null" } });
  return (
    <div ref={setNodeRef} className={`se-sem-acesso ${isOver ? "se-sem-acesso-over" : ""}`}>
      {ambientes.length === 0 && <div className="se-vazio-italico">Todos os ambientes já estão posicionados na árvore.</div>}
      {ambientes.map((a) => (
        <AmbienteChip key={a.id} amb={a} taxaPopulacional={taxaPopulacional} larguras={larguras} onEdit={onEdit} onRemove={onRemove} orfao
          selecionado={selecionados.has(a.id)} onToggleSelecao={onToggleSelecaoAmbiente} modoSelecao={selecionados.size > 0} />
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
export default function AcessosDescargasView({ projeto, pav, seNorma, ocupacoes, onVoltar, onProjetoAtualizado, adicionarToast, enviarAcao }) {
  const { TAXA_POPULACIONAL, LARGURAS_MINIMAS } = seNorma;
  const ambientes = pav.ambientes || [];
  const acessos = pav.acessos || [];
  const [editAmb, setEditAmb] = useState(null);
  const [colapsados, setColapsados] = useState({});
  const [salvando, setSalvando] = useState(false);
  const toggleColapsado = (id) => setColapsados((prev) => ({ ...prev, [id]: !prev[id] }));

  // Seleção em massa: marcar vários ambientes (em Acessos diferentes ou
  // ainda sem acesso) e movê-los todos de uma vez pra um Acesso/Saída
  // escolhido (ver MOVER_AMBIENTES_ACESSO no seReducer).
  const [selecionados, setSelecionados] = useState(new Set());
  const [alvoSelecao, setAlvoSelecao] = useState("");
  const toggleSelecaoAmbiente = (id) =>
    setSelecionados((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const limparSelecao = () => setSelecionados(new Set());
  const moverSelecionados = () => {
    if (!selecionados.size || !alvoSelecao) return;
    const novoAcessoId = alvoSelecao === ALVO_SEM_ACESSO ? null : alvoSelecao;
    despachar({ type: "MOVER_AMBIENTES_ACESSO", pavimentoId: pav.id, ambienteIds: [...selecionados], novoAcessoId });
    limparSelecao();
    setAlvoSelecao("");
  };
  // Órfão selecionado é excluído de verdade; dentro de um Acesso/Saída só
  // desvincula (fica órfão) — mesmo critério do botão individual de cada
  // card (ver AmbienteChip), só que pra toda a seleção de uma vez.
  const apagarSelecionados = () => {
    if (!selecionados.size) return;
    if (!window.confirm(`Apagar/desvincular ${selecionados.size} ambiente(s) selecionado(s)? Órfãos são excluídos; os que estiverem dentro de um Acesso/Saída só ficam sem posição.`)) return;
    despachar({ type: "APAGAR_AMBIENTES_SE", pavimentoId: pav.id, ambienteIds: [...selecionados] });
    limparSelecao();
  };

  const raizes = acessosFilhos(acessos, null);
  const semAcesso = ambientes.filter((a) => !a.acessoId);
  const nSaidas = Math.max(1, contarSaidasPavimento(acessos));
  const rotuloRaiz = pav.pisoDescarga ? "Saída" : "Escada/Rampa";
  const alvosSelecao = listarAcessosParaSelect(acessos);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  // Aplica a ação e persiste na hora — se a escrita falhar (versão
  // desatualizada, sem rede), avisa e NÃO aplica a mudança local, pra
  // tela nunca ficar mostrando algo que não foi salvo de verdade.
  // salvarComRetry já absorve o "falso conflito de versão" (outra aba/o
  // site salvou algo nesse meio-tempo, sem conflito real de conteúdo) —
  // só chega a dar erro aqui se a segunda tentativa também falhar. Depois
  // de salvar com sucesso, `enviarAcao` avisa o site (ou outra sessão da
  // dockpane) em tempo real, via o canal Realtime aberto em
  // SaidaEmergenciaPage.jsx — mesmo protocolo do site (ver
  // ProjetoContext.jsx), pra edição ao vivo em várias sessões.
  async function despachar(action) {
    setSalvando(true);
    try {
      const { dados: novosDados, version: novaVersao } = await salvarComRetry(projeto.id, projeto, (dados) =>
        aplicarAcaoSaida(dados, action)
      );
      onProjetoAtualizado({ ...projeto, dados: novosDados, version: novaVersao });
      enviarAcao?.(action);
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
  const setAcessoDim = (acessoId, dim, valor) => despachar({ type: "SET_ACESSO_DIM", pavimentoId: pav.id, acessoId, dim, valor });

  // `acessoId` opcional: quando vem de dentro de um card de Acesso ("+
  // Adicionar Ambiente" ali dentro), o ambiente já nasce atribuído a ele.
  const criarAmbiente = (acessoId = null) => {
    const id = idAmbienteSE();
    const nome = `Ambiente ${ambientes.length + 1}`;
    const ambiente = { nome, divisao: "", popTipo: "area", area: 0, assentos: 0, popManual: 0, acessoId, origem: "manual" };
    despachar({ type: "ADD_AMBIENTE_SE", pavimentoId: pav.id, id, ambiente });
    setEditAmb({ id, ...ambiente });
  };
  const removerAmbiente = (id) => {
    despachar({ type: "REMOVE_AMBIENTE_SE", pavimentoId: pav.id, ambienteId: id });
    if (editAmb?.id === id) setEditAmb(null);
  };
  // Desvincula um ambiente do Acesso/Saída sem apagar — volta pra "sem
  // acesso atribuído" (ver AmbienteChip: só ambiente já órfão ganha botão
  // de exclusão de verdade).
  const desvincularAmbiente = (id) => despachar({ type: "MOVER_AMBIENTE_ACESSO", pavimentoId: pav.id, ambienteId: id, novoAcessoId: null });
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
      // Arrastar um ambiente que faz parte da seleção em massa leva o
      // conjunto inteiro junto, não só o card que a mão pegou.
      if (selecionados.size > 1 && selecionados.has(activeData.id)) {
        despachar({ type: "MOVER_AMBIENTES_ACESSO", pavimentoId: pav.id, ambienteIds: [...selecionados], novoAcessoId });
        limparSelecao();
      } else {
        despachar({ type: "MOVER_AMBIENTE_ACESSO", pavimentoId: pav.id, ambienteId: activeData.id, novoAcessoId });
      }
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

      {/* collisionDetection=pointerWithin: o destino do drag é o card sob
          o ponteiro do mouse — o padrão do dnd-kit (rectIntersection)
          compara a área do card arrastado com a de cada droppable, e com
          Acessos aninhados (um dentro do outro) pode acertar o pai em vez
          do filho que está de fato embaixo do cursor. */}
      <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragEnd={handleDragEnd}>
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
                  onSetDim={setAcessoDim}
                  pavimentoId={pav.id}
                  onEditAmbiente={setEditAmb}
                  onRemoveAmbiente={removerAmbiente}
                  onDesvincularAmbiente={desvincularAmbiente}
                  onCreateAmbiente={criarAmbiente}
                  colapsados={colapsados}
                  toggleColapsado={toggleColapsado}
                  selecionados={selecionados}
                  onToggleSelecaoAmbiente={toggleSelecaoAmbiente}
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
            <SemAcessoDropZone ambientes={semAcesso} taxaPopulacional={TAXA_POPULACIONAL} larguras={LARGURAS_MINIMAS} onEdit={setEditAmb} onRemove={removerAmbiente}
              selecionados={selecionados} onToggleSelecaoAmbiente={toggleSelecaoAmbiente} />
          </div>
        </div>
      </DndContext>

      {/* Barra de seleção em massa — sticky no rodapé do scroll (.se-pagina
          é a ancestral rolável), fica sempre visível enquanto houver
          ambientes selecionados. */}
      {selecionados.size > 0 && (
        <div className="se-selecao-barra">
          <span className="se-selecao-contagem">{selecionados.size} ambiente{selecionados.size > 1 ? "s" : ""} selecionado{selecionados.size > 1 ? "s" : ""}</span>
          <select value={alvoSelecao} onChange={(e) => setAlvoSelecao(e.target.value)} className="se-selecao-select">
            <option value="">Mover para...</option>
            <option value={ALVO_SEM_ACESSO}>— Sem acesso atribuído —</option>
            {alvosSelecao.map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
          <button type="button" className="se-botao" disabled={!alvoSelecao} onClick={moverSelecionados}>
            <Icon svg={checkIconSvg} /> Mover
          </button>
          <button type="button" className="se-selecao-botao-apagar" onClick={apagarSelecionados}>
            <Icon svg={trashIconSvg} /> Apagar selecionados
          </button>
          <button type="button" className="se-selecao-cancelar" onClick={limparSelecao}>
            Cancelar seleção
          </button>
        </div>
      )}

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
