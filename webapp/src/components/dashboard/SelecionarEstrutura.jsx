import ProjetoCabecalho from "./ProjetoCabecalho";

export default function SelecionarEstrutura({ projeto, estruturas, onSelecionar }) {
  return (
    <div className="dashboard-tela">
      <ProjetoCabecalho projeto={projeto} />
      <p className="dashboard-subtitulo">Selecione uma estrutura</p>
      <div className="lista-estruturas">
        {estruturas.map((estrutura) => (
          <button
            key={estrutura.id}
            type="button"
            className="botao-estrutura"
            onClick={() => onSelecionar(estrutura)}
          >
            {estrutura.nome}
          </button>
        ))}
      </div>
    </div>
  );
}
