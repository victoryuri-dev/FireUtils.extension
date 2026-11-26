import { emAndamento, textoDoEstado } from "../lib/atualizacaoEstado";

/**
 * Faixa vermelha no topo da dockpane para a atualização do plugin. O download
 * começa sozinho; a faixa mostra o andamento (sem poder ser fechada enquanto
 * baixa) e, quando termina, o que a pessoa precisa fazer (lib/atualizacaoEstado.js):
 *   - só a interface mudou        → "Recarregar painel"
 *   - mudou a faixa do pyRevit    → "Reiniciar pyRevit e aplicar" (salvar o projeto antes)
 *   - mudou código do painel      → "Reiniciar pyRevit" e a faixa fica até reiniciar o Revit;
 *                                   o painel continua utilizável
 *   - instalador (agendada/manual)→ só a mensagem, pode ser fechada
 * Sem `estado` (plugin sem suporte a baixar sozinho) é o aviso simples de versão
 * nova, que pode ser dispensado.
 */
export default function AvisoAtualizacao({
  versaoNova, estado, onVerNovidades, onTentarNovamente, onRecarregarPyrevit, onRecarregarPagina, onDispensar,
}) {
  const fase = estado?.fase;
  const ocupado = emAndamento(estado);
  const concluidaSemAcao = fase === "agendada" || fase === "manual";
  const progressoDefinido = fase === "baixando" && typeof estado.percentual === "number";

  let acao = null;
  if (!fase) {
    acao = (
      <>
        <button type="button" className="aviso-atualizacao-botao" onClick={onVerNovidades}>Ver novidades</button>
        <button type="button" className="aviso-atualizacao-dispensar" onClick={onDispensar} title="Lembrar depois">Depois</button>
      </>
    );
  } else if (fase === "erro") {
    acao = <button type="button" className="aviso-atualizacao-botao" onClick={onTentarNovamente}>Tentar de novo</button>;
  } else if (fase === "aplicada" && estado.reinicio === "pyrevit") {
    acao = <button type="button" className="aviso-atualizacao-botao" onClick={onRecarregarPyrevit}>Reiniciar pyRevit e aplicar</button>;
  } else if (fase === "aplicada" && estado.reinicio !== "nenhum") {
    // Pede reiniciar o Revit: o que dá para aplicar agora é recarregar o pyRevit;
    // a faixa continua até o Revit reiniciar.
    acao = <button type="button" className="aviso-atualizacao-botao" onClick={onRecarregarPyrevit}>Reiniciar pyRevit</button>;
  } else if (fase === "aplicada" && estado.reinicio === "nenhum") {
    acao = <button type="button" className="aviso-atualizacao-botao" onClick={onRecarregarPagina}>Recarregar painel</button>;
  } else if (concluidaSemAcao) {
    acao = <button type="button" className="aviso-atualizacao-dispensar" onClick={onDispensar}>Ok</button>;
  }

  return (
    <div className="aviso-atualizacao" role="status">
      <div className="aviso-atualizacao-corpo">
        <span className="aviso-atualizacao-texto">
          {fase ? textoDoEstado(estado) : <>Nova versão do Fire Utils disponível: <strong>{versaoNova}</strong></>}
        </span>
        {ocupado && fase !== "recarregando" && (
          <div
            className={`aviso-atualizacao-progresso${progressoDefinido ? "" : " indeterminado"}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressoDefinido ? estado.percentual : undefined}
          >
            <div
              className="aviso-atualizacao-progresso-barra"
              style={progressoDefinido ? { width: `${estado.percentual}%` } : undefined}
            />
          </div>
        )}
      </div>
      {acao}
    </div>
  );
}
