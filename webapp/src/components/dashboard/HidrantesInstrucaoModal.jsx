import Icon from "../Icon";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";

/**
 * Popup para identificar as referências (RTI, bomba, válvulas de hidrante)
 * no Revit. Aparece só quando o usuário precisa AGIR no Revit (passo
 * "clique" ou "selecao" de HIDRANTES_MAPEAR_PROGRESSO — ver
 * hidrantes_mapear_bridge.py). O botão fechar cancela a seleção (o mesmo
 * efeito do Esc no Revit).
 */
export default function HidrantesInstrucaoModal({ progresso, aberto, onFechar }) {
  if (!aberto) return null;

  return (
    <div className="se-modal-overlay" role="dialog" aria-modal="true" aria-live="polite">
      <div className="hid-instrucao">
        <button type="button" className="hid-instrucao-fechar" onClick={onFechar} title="Cancelar" aria-label="Cancelar">
          <Icon svg={xIconSvg} />
        </button>
        <span className="hid-instrucao-etiqueta">Identificar referência</span>
        <h2 className="hid-instrucao-titulo">{progresso?.titulo || "Selecione o elemento"}</h2>
        <p className="hid-instrucao-texto">{progresso?.instrucao}</p>
      </div>
    </div>
  );
}
