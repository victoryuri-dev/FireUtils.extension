import { emAndamento, textoDoEstado } from "../lib/atualizacaoEstado";

/**
 * Faixa no topo avisando que há versão nova do plugin. Pode ser dispensada
 * (o pai lembra qual versão foi dispensada, para avisar de novo só na seguinte).
 * Quando o usuário clica em Baixar, a faixa passa a mostrar o andamento
 * (`estado`, ver lib/atualizacaoEstado.js).
 */
export default function AvisoAtualizacao({ versaoNova, estado, onBaixar, onDispensar }) {
  const fase = estado?.fase;
  const ocupado = emAndamento(estado);
  const concluido = fase === "agendada" || fase === "manual";

  return (
    <div className="aviso-atualizacao" role="status">
      <span className="aviso-atualizacao-texto">
        {fase && fase !== "erro" ? (
          textoDoEstado(estado)
        ) : (
          <>
            {fase === "erro" && <>{textoDoEstado(estado)} </>}
            Nova versão do Fire Utils disponível: <strong>{versaoNova}</strong>
          </>
        )}
      </span>
      {!ocupado && !concluido && (
        <button type="button" className="aviso-atualizacao-botao" onClick={onBaixar}>
          {fase === "erro" ? "Tentar de novo" : "Atualizar"}
        </button>
      )}
      {!ocupado && (
        <button type="button" className="aviso-atualizacao-dispensar" onClick={onDispensar} title="Lembrar depois">
          {concluido ? "Ok" : "Depois"}
        </button>
      )}
    </div>
  );
}
