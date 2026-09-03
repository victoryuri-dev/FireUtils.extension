import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { supabase, criarSignedUrlFamilia } from "./lib/supabaseClient";
import { fetchCatalog } from "./lib/catalog";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "./lib/bridge";
import LoginScreen from "./components/LoginScreen";
import Sidebar from "./components/Sidebar";
import CategoryPills, { TODAS_ID } from "./components/CategoryPills";
import FamilyCard from "./components/FamilyCard";

// Título da seção muda pra bater com o nome curto da categoria ativa (ex.:
// "Extintor de Incêndio" -> "EXTINTOR"), conforme o mockup — a primeira
// palavra já cobre os nomes de categoria atuais do catálogo.
function tituloDaSecao(categorias, categoriaAtual) {
  if (categoriaAtual === TODAS_ID) return "FAMÍLIAS";
  const categoria = categorias.find((c) => c.id === categoriaAtual);
  if (!categoria) return "FAMÍLIAS";
  return categoria.name.split(/\s+/)[0].toUpperCase();
}

export default function App() {
  const [sessao, setSessao] = useState(undefined); // undefined = ainda verificando
  const [catalogo, setCatalogo] = useState(null);
  const [categoriaAtual, setCategoriaAtual] = useState(TODAS_ID);
  const [busca, setBusca] = useState("");
  const [selecionadas, setSelecionadas] = useState(() => new Set());
  const [carregadas, setCarregadas] = useState(() => new Set());
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

  // Assim que o catálogo estiver pronto, pergunta ao host quais famílias já
  // estão no documento ativo do Revit — popula o indicador "carregada" nos
  // cards e o contador correspondente.
  useEffect(() => {
    if (catalogo) {
      postToHost(BridgeMessageTypes.REQUEST_LOADED_FAMILIES, {});
    }
  }, [catalogo]);

  useEffect(() => {
    return escutarMensagensDoHost((mensagem) => {
      if (mensagem && mensagem.type === BridgeMessageTypes.LOADED_FAMILIES) {
        setCarregadas(new Set(mensagem.payload?.names || []));
      }
    });
  }, []);

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

  async function carregarSelecionadas() {
    if (selecionadas.size === 0 || enviando) return;
    setEnviando(true);
    try {
      const alvo = catalogo.families.filter((f) => selecionadas.has(f.id));
      const familiasComUrl = await Promise.all(
        alvo.map(async (familia) => ({
          name: familia.name,
          categoryId: familia.category_id,
          storageKey: familia.storage_key,
          sha256: familia.sha256,
          signedUrl: await criarSignedUrlFamilia(familia.storage_key),
        }))
      );
      postToHost(BridgeMessageTypes.LOAD_FAMILIES, { familias: familiasComUrl });
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

  return (
    <div className="app-shell">
      <Sidebar abaAtual="biblioteca" />

      <div className="app">
        <header className="header">
          <p className="eyebrow">FIRE UTILS</p>
          <h1>Biblioteca de Famílias</h1>
        </header>

        <div className="search-bar">
          <span className="icone">⌕</span>
          <input
            type="text"
            placeholder="Que equipamento você procura?"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>

        {!catalogo ? (
          <p className="vazio">Carregando catálogo...</p>
        ) : (
          <>
            <CategoryPills
              categorias={catalogo.categories}
              todasIconKey={catalogo.todas_icon_key}
              categoriaAtual={categoriaAtual}
              onSelect={setCategoriaAtual}
            />

            <div className="secao-titulo-linha">
              <h2 className="secao-titulo">{tituloDaSecao(catalogo.categories, categoriaAtual)}</h2>
              <div className="contadores">
                <span className="contador">
                  <strong>{String(selecionadas.size).padStart(2, "0")}</strong> selecionados
                </span>
                <span className="contador">
                  <strong>{String(carregadas.size).padStart(2, "0")}</strong> carregadas
                </span>
              </div>
            </div>

            <div className="catalogo">
              {familiasFiltradas.length === 0 ? (
                <p className="vazio">
                  {catalogo.families.length === 0
                    ? "Nenhuma família encontrada na biblioteca."
                    : "Nenhuma família encontrada com esse filtro."}
                </p>
              ) : (
                <div className="grade">
                  {familiasFiltradas.map((familia) => (
                    <FamilyCard
                      key={familia.id}
                      familia={familia}
                      selecionado={selecionadas.has(familia.id)}
                      carregada={carregadas.has(familia.name)}
                      onToggle={alternarSelecao}
                    />
                  ))}
                </div>
              )}
            </div>

            {selecionadas.size > 0 && (
              <div className="acoes">
                <button type="button" className="botao" onClick={marcarTodosFiltrados}>
                  Selecionar todos
                </button>
                <button type="button" className="botao" onClick={desmarcarTodos}>
                  Desmarcar todos
                </button>
                <button
                  type="button"
                  className="botao accent"
                  disabled={enviando}
                  onClick={carregarSelecionadas}
                >
                  Carregar no projeto
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
