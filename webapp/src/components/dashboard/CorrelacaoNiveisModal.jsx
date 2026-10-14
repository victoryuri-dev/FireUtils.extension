import { useEffect, useState } from "react";
import { DndContext, useDraggable, useDroppable, PointerSensor, useSensor, useSensors, pointerWithin } from "@dnd-kit/core";
import Icon from "../Icon";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import { pavimentosCompletos } from "../../lib/projetoDados";
import gripIconSvg from "../../assets/icons/grip-icon.svg?raw";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";

/**
 * Painel "Correlacionar Níveis": nem sempre o nome do nível no Revit bate
 * com o pavimento cadastrado no site (ex.: "Nível 1" em vez de "Térreo"),
 * então em vez de tentar adivinhar por nome o usuário alinha as duas
 * colunas manualmente — a da esquerda (Pavimentos do FireUtils) fica fixa,
 * na mesma ordem já cadastrada no site; a da direita (Níveis do Revit) é
 * arrastável, e a linha i de cada coluna vira um par (pavimento <-> nível)
 * assim que salvo. Ver niveis_bridge.py (lado Python) e
 * lib/bridge.js (contrato GET_REVIT_LEVELS/SET_NIVEIS_CORRELACAO).
 */

/** Monta a ordem inicial da coluna de níveis a partir da correlação já
 * salva: cada pavimento que já tem um nível correlacionado mostra esse
 * nível na própria linha; pavimentos ainda sem par são preenchidos (na
 * ordem de elevação) com os níveis que sobraram, e o que não coube em
 * nenhuma linha (mais níveis do que pavimentos) vai pro final da lista —
 * ainda visível e arrastável, só sem um pavimento correspondente ainda. */
function montarOrdemInicial(levels, pavimentos, correlacaoSalva) {
  const porUniqueId = new Map(levels.map((nivel) => [nivel.uniqueId, nivel]));
  const nivelIdPorPavimento = new Map((correlacaoSalva || []).map((c) => [c.pavimentoId, c.nivelUniqueId]));
  const usados = new Set();

  const linhas = pavimentos.map((pav) => {
    const uniqueId = nivelIdPorPavimento.get(pav.id);
    const nivel = uniqueId ? porUniqueId.get(uniqueId) : null;
    if (nivel) usados.add(nivel.uniqueId);
    return nivel || null;
  });

  const sobrando = levels.filter((nivel) => !usados.has(nivel.uniqueId));
  let cursor = 0;
  const completo = linhas.map((linha) => linha || sobrando[cursor++] || null);
  return [...completo, ...sobrando.slice(cursor)];
}

/** Move um item de `de` pra `para`, deslocando os demais — mesmo
 * resultado de @dnd-kit/sortable:arrayMove, escrito à mão aqui porque o
 * resto do app só usa @dnd-kit/core (ver AcessosDescargasView.jsx). */
function mover(lista, de, para) {
  const nova = [...lista];
  const [item] = nova.splice(de, 1);
  nova.splice(para, 0, item);
  return nova;
}

function LinhaNivel({ nivel, indice }) {
  const { attributes, listeners, setNodeRef: setDragRef, transform, isDragging } = useDraggable({
    id: `nivel:${nivel.uniqueId}`,
    data: { index: indice },
  });
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `slot:${indice}`,
    data: { index: indice },
  });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;

  return (
    <div
      ref={(no) => {
        setDragRef(no);
        setDropRef(no);
      }}
      style={style}
      className={`niveis-linha ${isOver ? "niveis-linha-sobre" : ""} ${isDragging ? "niveis-linha-arrastando" : ""}`}
    >
      <button {...attributes} {...listeners} type="button" className="niveis-grip" title="Arrastar para reordenar">
        <Icon svg={gripIconSvg} />
      </button>
      <span className="niveis-linha-nome">{nivel.nome}</span>
    </div>
  );
}

function LinhaVazia({ indice }) {
  const { setNodeRef, isOver } = useDroppable({ id: `slot:${indice}`, data: { index: indice } });
  return (
    <div ref={setNodeRef} className={`niveis-linha niveis-linha-vazia ${isOver ? "niveis-linha-sobre" : ""}`}>
      <span className="niveis-linha-nome">—</span>
    </div>
  );
}

export default function CorrelacaoNiveisModal({ projeto, estrutura, adicionarToast, onFechar }) {
  const [niveis, setNiveis] = useState(null); // null = ainda carregando
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));
  const pavimentos = pavimentosCompletos(projeto, estrutura.id);

  useEffect(() => {
    postToHost(BridgeMessageTypes.GET_REVIT_LEVELS, { estruturaId: estrutura.id });
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (mensagem.type === BridgeMessageTypes.REVIT_LEVELS) {
        const { levels = [], correlacao = [], erro: erroRevit } = mensagem.payload || {};
        if (erroRevit) {
          setErro(erroRevit);
          return;
        }
        setNiveis(montarOrdemInicial(levels, pavimentos, correlacao));
        return;
      }

      if (mensagem.type === BridgeMessageTypes.NIVEIS_CORRELACAO_SAVED) {
        setSalvando(false);
        const { ok, erro: erroSalvar } = mensagem.payload || {};
        if (ok) {
          adicionarToast?.({ tipo: "sucesso", titulo: "Níveis correlacionados", duracaoMs: 4000 });
          postToHost(BridgeMessageTypes.GET_DIMENSIONAMENTOS_STATUS, {});
          onFechar?.();
        } else {
          adicionarToast?.({
            tipo: "erro",
            titulo: "Não foi possível salvar a correlação",
            mensagem: erroSalvar,
            duracaoMs: 9000,
          });
        }
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estrutura.id]);

  function aoSoltar({ active, over }) {
    if (!over) return;
    const de = active.data.current?.index;
    const para = over.data.current?.index;
    if (de == null || para == null || de === para) return;
    setNiveis((atual) => mover(atual, de, para));
  }

  function salvar() {
    const correlacao = pavimentos
      .map((pav, indice) => {
        const nivel = niveis[indice];
        return nivel ? { pavimentoId: pav.id, nivelUniqueId: nivel.uniqueId, nivelNome: nivel.nome } : null;
      })
      .filter(Boolean);
    setSalvando(true);
    postToHost(BridgeMessageTypes.SET_NIVEIS_CORRELACAO, { estruturaId: estrutura.id, correlacao });
  }

  const linhas = Math.max(pavimentos.length, niveis?.length || 0);

  return (
    <div className="niveis-modal-overlay" onClick={onFechar}>
      <div className="niveis-modal-caixa" onClick={(e) => e.stopPropagation()}>
        <div className="niveis-modal-header">
          <span className="niveis-modal-titulo">Correlacionar Níveis</span>
          <button type="button" className="se-icon-botao" onClick={onFechar}>
            <Icon svg={xIconSvg} />
          </button>
        </div>

        <p className="niveis-modal-ajuda">
          Arraste os níveis do Revit (direita) até alinhar cada linha com o pavimento correspondente do FireUtils
          (esquerda) — nem sempre o nome do nível no Revit bate com o pavimento cadastrado no site.
        </p>

        {erro && <p className="vazio">{erro}</p>}

        {!erro && niveis === null && <p className="vazio">Carregando níveis do Revit...</p>}

        {!erro && niveis !== null && (
          <>
            <div className="niveis-colunas">
              <div className="niveis-coluna">
                <h4 className="niveis-coluna-titulo">Pavimentos (FireUtils)</h4>
                {Array.from({ length: linhas }).map((_, indice) => (
                  <div key={pavimentos[indice]?.id || `pav-vazio-${indice}`} className="niveis-linha niveis-linha-fixa">
                    <span className="niveis-linha-nome">{pavimentos[indice]?.label || "—"}</span>
                  </div>
                ))}
              </div>

              <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragEnd={aoSoltar}>
                <div className="niveis-coluna">
                  <h4 className="niveis-coluna-titulo">Níveis (Revit)</h4>
                  {Array.from({ length: linhas }).map((_, indice) =>
                    niveis[indice] ? (
                      <LinhaNivel key={niveis[indice].uniqueId} nivel={niveis[indice]} indice={indice} />
                    ) : (
                      <LinhaVazia key={`nivel-vazio-${indice}`} indice={indice} />
                    )
                  )}
                </div>
              </DndContext>
            </div>

            <div className="niveis-modal-rodape">
              <button type="button" className="botao" onClick={onFechar} disabled={salvando}>
                Cancelar
              </button>
              <button type="button" className="botao accent" onClick={salvar} disabled={salvando}>
                {salvando ? "Salvando..." : "Salvar correlação"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
