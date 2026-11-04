/**
 * Ocupa o lugar do conteúdo depois que um pacote mudou código que a dockpane já
 * tem carregado (plugin_pacote.py → reinicio "revit"): os arquivos novos estão
 * no disco, mas o Revit ainda roda o código antigo. Usar o painel assim
 * misturaria as duas versões, então ele fica indisponível até o Revit reiniciar.
 */
export default function ReiniciarRevit({ versao }) {
  return (
    <div className="sem-licenca">
      <h2>Reinicie o Revit para concluir a atualização</h2>
      <p>
        O Fire Utils{versao ? ` v${versao}` : ""} já foi instalado, mas só passa a valer quando o Revit abrir de novo.
        Até lá o painel fica indisponível, para não misturar a versão nova com a antiga.
      </p>
      <p className="sem-licenca-nota">
        Salve o projeto, feche o Revit e abra-o novamente. Seus projetos e licenças não são afetados.
      </p>
    </div>
  );
}
