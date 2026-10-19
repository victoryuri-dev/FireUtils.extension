/**
 * Ocupa o lugar do conteúdo quando o plugin instalado é mais antigo do que
 * esta interface aceita (PLUGIN_MINIMO, em lib/versoes.js). Sem isso, as funções
 * que dependem do Revit falhariam sem explicação.
 */
export default function AtualizacaoNecessaria({ versaoNova, onBaixar }) {
  return (
    <div className="sem-licenca">
      <h2>Atualize o plugin do Fire Utils</h2>
      <p>
        A versão instalada no seu Revit é anterior à mínima que esta tela exige.
        Instale a versão {versaoNova} para continuar.
      </p>
      <button type="button" className="sem-licenca-botao" onClick={onBaixar}>
        Baixar atualização
      </button>
      <p className="sem-licenca-nota">
        Feche o Revit antes de rodar o instalador. Suas licenças e projetos não são afetados.
      </p>
    </div>
  );
}
