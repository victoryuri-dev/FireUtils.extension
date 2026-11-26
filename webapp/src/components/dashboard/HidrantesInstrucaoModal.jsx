/**
 * Popup grande para identificar as referências (RTI, bomba, válvulas de
 * hidrante) no Revit. Aparece só quando o usuário precisa AGIR no Revit
 * (acao "clique" ou "selecao", vinda de HIDRANTES_MAPEAR_PROGRESSO — ver
 * hidrantes_mapear_bridge.py); enquanto o plugin trabalha sozinho, o
 * cartão "Referências" mostra só um aviso discreto.
 */
export default function HidrantesInstrucaoModal({ progresso, acao, aberto }) {
  if (!aberto) return null;

  return (
    <div className="se-modal-overlay" role="dialog" aria-modal="true" aria-live="polite">
      <div className="hid-instrucao">
        <span className="hid-instrucao-etiqueta">Identificar referência · sua vez no Revit</span>
        <h2 className="hid-instrucao-titulo">{progresso.titulo || "Selecione o elemento"}</h2>
        <p className="hid-instrucao-texto">{progresso.instrucao}</p>
        {progresso.dica && <p className="hid-instrucao-dica">{progresso.dica}</p>}
        <p className="hid-instrucao-rodape">
          {acao === "selecao"
            ? "Depois de selecionar, clique em Concluir na barra do Revit. Esc cancela."
            : "Clique no elemento no Revit, não aqui no painel. Esc cancela."}
        </p>
      </div>
    </div>
  );
}
