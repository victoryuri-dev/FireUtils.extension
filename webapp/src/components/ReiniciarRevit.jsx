import Loader from "./Loader";

/**
 * Tela inteira, sem menu nem faixa, depois que um pacote mudou código que a
 * dockpane já tem carregado (plugin_pacote.py → reinicio "revit"): os arquivos
 * novos estão no disco, mas o Revit ainda roda o código antigo. Usar o painel
 * assim misturaria as duas versões, então ele fica indisponível até o Revit
 * reiniciar.
 */
export default function ReiniciarRevit({ versao }) {
  return (
    <div className="reiniciar-revit">
      <div className="sem-licenca">
        <Loader size={48} className="reiniciar-revit-logo" />
        <h2>Reinicie o Revit para concluir a atualização</h2>
        <p>
          Fire Utils{versao ? ` v${versao}` : ""} foi instalado. Salve o projeto, feche o Revit e abra-o novamente.
          Até lá o painel ficará indisponível.
        </p>
      </div>
    </div>
  );
}
