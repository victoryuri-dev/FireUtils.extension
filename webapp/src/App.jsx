import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { supabase, criarSignedUrlFamilia } from "./lib/supabaseClient";
import { fetchCatalog } from "./lib/catalog";
import { postToHost, BridgeMessageTypes } from "./lib/bridge";
import LoginScreen from "./components/LoginScreen";
import CategoryPills, { TODAS_ID } from "./components/CategoryPills";
import FamilyCard from "./components/FamilyCard";

export default function App() {
  const [sessao, setSessao] = useState(undefined); // undefined = ainda verificando
  const [catalogo, setCatalogo] = useState(null);
  const [categoriaAtual, setCategoriaAtual] = useState(TODAS_ID);
  const [busca, setBusca] = useState("");
  const [selecionadas, setSelecionadas] = useState(() => new Set());
  const [enviando, setEnviando] = useState(false);

  // Sessão do Supabase: verifica a atual e escuta login/logout. Sem
  // Supabase configurado, trata como "sem sessão nenhuma" — LoginScreen já
  // mostra o aviso de configuração pendente nesse caso.
  useEffect(() => {
    if (!supabase) {
      setSessao(null);
      return;
    }
    supabase.auth.getSession().then(({ data }) => setSessao(data.session));
    const { data: assinatura } = supabase.auth.onAuthStateChange((_evento, novaSessao) => {
      setSessao(novaSessao);
    });
    return () => assinatura.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (sessao) {
      fetchCatalog().then(setCatalogo);
    }
  }, [sessao]);

  const secoesVisiveis = useMemo(() => {
    if (!catalogo) return [];
    const textoFiltro = busca.trim().toLowerCase();
    const porCategoria = new Map();

    for (const familia of catalogo.families) {
      if (categoriaAtual !== TODAS_ID && familia.category_id !== categoriaAtual) continue;
      if (textoFiltro && !familia.name.toLowerCase().includes(textoFiltro)) continue;
      if (!porCategoria.has(familia.category)) porCategoria.set(familia.category, []);
      porCategoria.get(familia.category).push(familia);
    }

    for (const lista of porCategoria.values()) {
      lista.sort((a, b) => a.name.localeCompare(b.name));
    }

    return Array.from(porCategoria.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [catalogo, categoriaAtual, busca]);

  const familiasFiltradas = useMemo(
    () => secoesVisiveis.flatMap(([, familias]) => familias),
    [secoesVisiveis]
  );

  function alternarSelecao(familia) {
    setSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(familia.id)) nova.delete(familia.id);
      else nova.add(familia.id);
      return nova;
    });
  }

  function marcarTodosFiltrados() {
    setSelecionadas((atual) => {
      const nova = new Set(atual);
      familiasFiltradas.forEach((f) => nova.add(f.id));
      return nova;
    });
  }

  function desmarcarTodos() {
    setSelecionadas(new Set());
  }

  async function enviarSelecionadas(posicionar) {
    if (selecionadas.size === 0 || enviando) return;
    setEnviando(true);
    try {
      const alvo = catalogo.families.filter((f) => selecionadas.has(f.id));
      const familiasComUrl = await Promise.all(
        alvo.map(async (familia) => ({
          name: familia.name,
          categoryId: familia.category_id,
          storageKey: familia.storage_key,
          signedUrl: await criarSignedUrlFamilia(familia.storage_key),
        }))
      );
      postToHost(BridgeMessageTypes.LOAD_FAMILIES, { posicionar, familias: familiasComUrl });
    } catch (erro) {
      console.error("[App] Falha ao gerar Signed URL / enviar pro host:", erro);
      window.alert(`Não foi possível carregar as famílias selecionadas: ${erro.message}`);
    } finally {
      setEnviando(false);
    }
  }

  if (sessao === undefined) {
    return null; // verificando sessão — evita "piscar" a tela de login
  }
  if (!sessao) {
    return <LoginScreen onLogin={setSessao} />;
  }
  if (!catalogo) {
    return (
      <div className="app" style={{ alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "var(--text-2)" }}>Carregando catálogo...</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="logo">{/* logo entra aqui quando tivermos um asset público pra ela */}</div>
        <div className="titulos">
          <p className="eyebrow">FIRE UTILS · BIBLIOTECA</p>
          <h1>Carregador de Famílias</h1>
          <p>Combate a incêndio — pesquise, filtre por categoria e carregue no projeto</p>
        </div>
      </header>

      <div className="search-bar">
        <span className="icone">⌕</span>
        <input
          type="text"
          placeholder="Pesquisar famílias..."
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
      </div>

      <div className="categorias">
        <div className="cabecalho">
          <span className="rotulo">CATEGORIAS</span>
          <button type="button" className="atualizar" onClick={() => fetchCatalog().then(setCatalogo)}>
            ↻ Atualizar catálogo
          </button>
        </div>
        <CategoryPills
          categorias={catalogo.categories}
          todasIconKey={catalogo.todas_icon_key}
          categoriaAtual={categoriaAtual}
          onSelect={setCategoriaAtual}
        />
      </div>

      <div className="catalogo">
        {secoesVisiveis.length === 0 ? (
          <p className="vazio">
            {catalogo.families.length === 0
              ? "Nenhuma família encontrada na biblioteca."
              : "Nenhuma família encontrada com esse filtro."}
          </p>
        ) : (
          secoesVisiveis.map(([categoria, familias]) => (
            <section key={categoria}>
              <div className="secao-header">
                {categoria} ({familias.length})
              </div>
              <div className="grade">
                {familias.map((familia) => (
                  <FamilyCard
                    key={familia.id}
                    familia={familia}
                    selecionado={selecionadas.has(familia.id)}
                    onToggle={alternarSelecao}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </div>

      <p className="status">
        {selecionadas.size} selecionada(s) · {familiasFiltradas.length} exibida(s) de {catalogo.families.length} no
        total
      </p>

      <div className="acoes">
        <button type="button" className="botao" onClick={marcarTodosFiltrados}>
          Marcar todos (filtrados)
        </button>
        <button type="button" className="botao" onClick={desmarcarTodos}>
          Desmarcar todos
        </button>
        <button
          type="button"
          className="botao accent-outline"
          disabled={selecionadas.size === 0 || enviando}
          onClick={() => enviarSelecionadas(true)}
        >
          Carregar e posicionar
        </button>
        <button
          type="button"
          className="botao accent"
          disabled={selecionadas.size === 0 || enviando}
          onClick={() => enviarSelecionadas(false)}
        >
          Carregar selecionadas
        </button>
      </div>
    </div>
  );
}
