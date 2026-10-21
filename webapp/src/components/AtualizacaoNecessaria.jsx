import { emAndamento, textoDoEstado } from "../lib/atualizacaoEstado";

/**
 * Ocupa o lugar do conteúdo quando o plugin instalado é mais antigo do que
 * esta interface aceita (PLUGIN_MINIMO, em lib/versoes.js). Sem isso, as funções
 * que dependem do Revit falhariam sem explicação.
 */
export default function AtualizacaoNecessaria({ versaoNova, estado, onBaixar }) {
  const fase = estado?.fase;
  const ocupado = emAndamento(estado);
  const concluido = ["agendada", "manual", "aplicada"].includes(fase);
  return (
    <div className="sem-licenca">
      <h2>Atualize o plugin do Fire Utils</h2>
      <p>
        A versão instalada no seu Revit é anterior à mínima que esta tela exige.
        Instale a versão {versaoNova} para continuar.
      </p>
      {fase && <p className="sem-licenca-nota">{textoDoEstado(estado)}</p>}
      {!ocupado && !concluido && (
        <button type="button" className="sem-licenca-botao" onClick={onBaixar}>
          {fase === "erro" ? "Tentar de novo" : "Atualizar agora"}
        </button>
      )}
      <p className="sem-licenca-nota">
        Feche o Revit antes de rodar o instalador. Suas licenças e projetos não são afetados.
      </p>
    </div>
  );
}
