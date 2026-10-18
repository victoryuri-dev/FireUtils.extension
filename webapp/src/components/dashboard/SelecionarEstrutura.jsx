import { useState } from "react";
import ProjetoCabecalho from "./ProjetoCabecalho";
import Icon from "../Icon";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

/**
 * Um arquivo Revit pode conter várias estruturas modeladas juntas — por
 * isso multi-seleção, não mais "clique numa pra entrar". O conjunto
 * escolhido aqui vira só a lista de opções da ferramenta "Atribuir seleção
 * à estrutura" (ver DashboardEstrutura.jsx) — não atribui nada sozinho a
 * nenhuma família/ambiente (ver lib/bridge.js, SET_PROJECT_LINK).
 */
export default function SelecionarEstrutura({ projeto, estruturas, onConfirmar }) {
  const [selecionadas, setSelecionadas] = useState(() => new Set());

  function alternar(id) {
    setSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(id)) nova.delete(id);
      else nova.add(id);
      return nova;
    });
  }

  function confirmar() {
    const escolhidas = estruturas.filter((e) => selecionadas.has(e.id));
    if (escolhidas.length === 0) return;
    onConfirmar(escolhidas);
  }

  return (
    <div className="dashboard-tela">
      <ProjetoCabecalho projeto={projeto} />
      <p className="dashboard-subtitulo">Selecione as estruturas modeladas neste arquivo</p>
      <div className="lista-estruturas">
        {estruturas.map((estrutura) => {
          const marcada = selecionadas.has(estrutura.id);
          return (
            <button
              key={estrutura.id}
              type="button"
              className={`botao-estrutura ${marcada ? "botao-estrutura-marcada" : ""}`}
              onClick={() => alternar(estrutura.id)}
              aria-pressed={marcada}
            >
              <span className="botao-estrutura-check">{marcada && <Icon svg={checkIconSvg} />}</span>
              {estrutura.nome}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="botao accent botao-confirmar-estruturas"
        disabled={selecionadas.size === 0}
        onClick={confirmar}
      >
        Confirmar {selecionadas.size > 0 ? `(${selecionadas.size})` : ""}
      </button>
    </div>
  );
}
