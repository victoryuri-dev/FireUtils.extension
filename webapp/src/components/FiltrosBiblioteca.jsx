import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { rotuloDaCategoria } from "../lib/categorias";
import chevronIconSvg from "../assets/icons/chevron-right-icon.svg?raw";

/**
 * Filtros da Biblioteca, sempre visíveis abaixo da busca:
 *  - Categorias: seletor que abre uma lista com caixas de marcação; várias
 *    podem ficar marcadas ao mesmo tempo (nenhuma marcada = todas).
 *  - Ordem: alfabética (A–Z) ou as mais recentes primeiro.
 */
export default function FiltrosBiblioteca({ categorias, selecionadas, onSelecionadas, ordem, onOrdem }) {
  const [aberto, setAberto] = useState(false);
  const raizRef = useRef(null);

  // Fecha ao clicar fora ou apertar Esc.
  useEffect(() => {
    if (!aberto) return undefined;
    function aoClicar(e) {
      if (raizRef.current && !raizRef.current.contains(e.target)) setAberto(false);
    }
    function aoTeclar(e) {
      if (e.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", aoClicar);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("mousedown", aoClicar);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto]);

  function alternar(id) {
    const nova = new Set(selecionadas);
    if (nova.has(id)) nova.delete(id);
    else nova.add(id);
    onSelecionadas(nova);
  }

  const total = selecionadas.size;

  return (
    <div className="filtros-biblioteca">
      <div className="filtro-categorias" ref={raizRef}>
        <button
          type="button"
          className={`filtro-botao ${aberto ? "aberto" : ""} ${total > 0 ? "ativo" : ""}`}
          onClick={() => setAberto((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={aberto}
        >
          <span>Categorias</span>
          {total > 0 && <span className="filtro-contagem">{total}</span>}
          <Icon svg={chevronIconSvg} className="filtro-seta" />
        </button>

        {aberto && (
          <div className="filtro-popover" role="listbox" aria-multiselectable="true" aria-label="Categorias">
            {categorias.map((categoria) => (
              <label key={categoria.id} className="filtro-opcao">
                <input
                  type="checkbox"
                  checked={selecionadas.has(categoria.id)}
                  onChange={() => alternar(categoria.id)}
                />
                <span>{rotuloDaCategoria(categoria)}</span>
              </label>
            ))}
            <button
              type="button"
              className="filtro-limpar"
              disabled={total === 0}
              onClick={() => onSelecionadas(new Set())}
            >
              Limpar seleção
            </button>
          </div>
        )}
      </div>

      <div className="filtro-ordem" role="group" aria-label="Ordenar famílias">
        <button
          type="button"
          className={ordem === "az" ? "ativo" : ""}
          aria-pressed={ordem === "az"}
          onClick={() => onOrdem("az")}
        >
          A–Z
        </button>
        <button
          type="button"
          className={ordem === "recentes" ? "ativo" : ""}
          aria-pressed={ordem === "recentes"}
          onClick={() => onOrdem("recentes")}
        >
          Mais recentes
        </button>
      </div>
    </div>
  );
}
