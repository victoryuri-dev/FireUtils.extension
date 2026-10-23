/**
 * Pergunta, antes de atualizar o plugin, se o usuário já salvou o projeto: o
 * fundo turvo cobre a dockpane inteira e só os dois botões fecham o aviso.
 * `tipo`: "pacote" (aplicado com o Revit aberto; depois é preciso reiniciar) ou
 * "instalador" (baixa o instalador; é preciso fechar o Revit para instalar).
 */
export default function ConfirmarAtualizacao({ versaoNova, tipo, onCancelar, onConfirmar }) {
  return (
    <div className="confirmar-overlay" onClick={onCancelar} role="presentation">
      <div
        className="confirmar-caixa"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirmar-titulo"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirmar-titulo" className="confirmar-titulo">Salve o projeto antes de atualizar</h2>
        <p className="confirmar-texto">
          Vamos atualizar o Fire Utils para a versão <strong>{versaoNova}</strong>.{" "}
          {tipo === "pacote"
            ? "Dependendo do que mudar, pode ser preciso reiniciar o Revit depois (a dockpane avisa). Salve o seu trabalho agora para não perder nada."
            : "Para instalar, o Revit precisa estar fechado. Salve o seu trabalho agora para não perder nada."}
        </p>
        <div className="confirmar-botoes">
          <button type="button" className="se-botao" onClick={onCancelar} autoFocus>
            Cancelar
          </button>
          <button type="button" className="se-botao se-botao-accent" onClick={onConfirmar}>
            Atualizar
          </button>
        </div>
      </div>
    </div>
  );
}
