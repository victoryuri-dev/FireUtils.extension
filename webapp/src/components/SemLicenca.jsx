import { urlPlanos } from "../lib/site";

/**
 * Ocupa o lugar de uma aba que a conta não pode abrir.
 *
 * A mensagem muda conforme o caso, porque a ação do usuário é diferente:
 * quem não tem licença nenhuma precisa contratar; quem tem outro módulo só
 * precisa saber qual falta. Um "sem acesso" genérico deixaria os dois sem
 * saber o que fazer.
 */
export default function SemLicenca({ modulo, temAlgumaLicenca }) {
  const planos = urlPlanos();
  const titulo = modulo ? `${modulo} não está na sua assinatura` : "Assinatura necessária";

  const descricao = modulo
    ? `Esta área faz parte do módulo ${modulo}. Sua conta tem acesso aos outros módulos contratados, mas não a este.`
    : temAlgumaLicenca
      ? "Esta área precisa de um módulo ativo na sua conta."
      : "Esta conta ainda não tem nenhum módulo ativo. A Biblioteca de Famílias continua disponível.";

  return (
    <div className="sem-licenca">
      <h2>{titulo}</h2>
      <p>{descricao}</p>

      {planos && (
        <a className="sem-licenca-botao" href={planos} target="_blank" rel="noreferrer">
          Ver planos
        </a>
      )}

      <p className="sem-licenca-nota">
        Se você acabou de contratar, saia e entre de novo na sua conta para
        atualizar o acesso.
      </p>
    </div>
  );
}
