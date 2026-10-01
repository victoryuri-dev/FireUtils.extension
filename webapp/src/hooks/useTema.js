import { useEffect, useState } from "react";

const CHAVE_STORAGE = "fireutils-tema";

function temaInicial() {
  try {
    const salvo = localStorage.getItem(CHAVE_STORAGE);
    if (salvo === "light" || salvo === "dark") return salvo;
  } catch {
    // localStorage indisponível (ex.: WebView2 com storage bloqueado) — segue com o padrão
  }
  return "dark";
}

// Tema padrão da dockpane é escuro — este hook só alterna pra claro quando o
// usuário pede (botão da sidebar), persistindo a escolha entre sessões.
export function useTema() {
  const [tema, setTema] = useState(temaInicial);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tema);
    try {
      localStorage.setItem(CHAVE_STORAGE, tema);
    } catch {
      // só perde a persistência — não impede o tema de aplicar nesta sessão
    }
  }, [tema]);

  function alternar() {
    setTema((t) => (t === "dark" ? "light" : "dark"));
  }

  return { tema, alternar };
}
