import { textoDaAplicada } from "../lib/atualizacaoEstado";

/** Faixa que sobrevive ao recarregamento da página depois de uma atualização:
 * diz o que fazer em seguida (reiniciar o Revit, recarregar o pyRevit ou nada). */
export default function AvisoPosAtualizacao({ aviso, onFechar }) {
  return (
    <div className="aviso-atualizacao" role="status">
      <span className="aviso-atualizacao-texto">
        {aviso.versao && <strong>v{aviso.versao}. </strong>}
        {textoDaAplicada(aviso.reinicio, aviso.recarga)}
      </span>
      <button type="button" className="aviso-atualizacao-dispensar" onClick={onFechar}>
        Ok
      </button>
    </div>
  );
}
