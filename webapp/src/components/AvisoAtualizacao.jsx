/**
 * Faixa no topo avisando que há versão nova do plugin. Pode ser dispensada
 * (o pai lembra qual versão foi dispensada, para avisar de novo só na seguinte).
 */
export default function AvisoAtualizacao({ versaoNova, onBaixar, onDispensar }) {
  return (
    <div className="aviso-atualizacao" role="status">
      <span className="aviso-atualizacao-texto">
        Nova versão do Fire Utils disponível: <strong>{versaoNova}</strong>
      </span>
      <button type="button" className="aviso-atualizacao-botao" onClick={onBaixar}>
        Baixar
      </button>
      <button type="button" className="aviso-atualizacao-dispensar" onClick={onDispensar} title="Lembrar depois">
        Depois
      </button>
    </div>
  );
}
