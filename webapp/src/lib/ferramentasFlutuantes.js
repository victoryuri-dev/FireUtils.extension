// Pedidos vindos da barra flutuante de ferramentas (ferramentas_flutuantes.py).
//
// O clique chega ao App (sempre montado), mas quem executa a ferramenta é um
// componente da página Saídas — que pode nem estar montado ainda (outra aba,
// ou estrutura por escolher). Por isso o pedido fica guardado aqui até alguém
// consumir, em vez de depender de o destino estar ouvindo na hora.

// Um pedido que ninguém consumiu (ex.: aba bloqueada pela licença) não deve
// disparar do nada minutos depois, quando o usuário abrir a página.
const VALIDADE_MS = 10000;

let pendente = null; // { acao, em }
const ouvintes = new Set();

export function solicitarFerramenta(acao) {
  pendente = { acao, em: Date.now() };
  ouvintes.forEach((ouvinte) => ouvinte());
}

/** Devolve a ação pendente (e a limpa), ou null se não há/venceu. */
export function consumirFerramenta() {
  const atual = pendente;
  pendente = null;
  return atual && Date.now() - atual.em <= VALIDADE_MS ? atual.acao : null;
}

export function observarFerramenta(ouvinte) {
  ouvintes.add(ouvinte);
  return () => ouvintes.delete(ouvinte);
}
