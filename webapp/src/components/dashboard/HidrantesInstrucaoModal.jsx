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
          {/* X fino desenhado com traço (o ícone cheio do app é grosso demais). */}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" strokeWidth="1" strokeLinecap="square" />
          </svg>
        </button>
        <span className="hid-instrucao-etiqueta">Identificar referência</span>
        <h2 className="hid-instrucao-titulo">{progresso?.titulo || "Selecione o elemento"}</h2>
        <p className="hid-instrucao-texto">{progresso?.instrucao}</p>
      </div>
    </div>
  );
}
