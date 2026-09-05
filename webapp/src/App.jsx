import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { supabase, criarSignedUrlFamilia } from "./lib/supabaseClient";
import { fetchCatalog } from "./lib/catalog";
import { postToHost, escutarMensagensDoHost, estaDentroDoWebView2, BridgeMessageTypes } from "./lib/bridge";
import LoginScreen from "./components/LoginScreen";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import Icon from "./components/Icon";
import ToastStack from "./components/ToastStack";
import { useToasts } from "./lib/toasts";
import CategoryPills, { TODAS_ID, ROTULO_CURTO_POR_CATEGORIA } from "./components/CategoryPills";
import FamilyCard from "./components/FamilyCard";
import carregarIconSvg from "./assets/icons/carregado-icon-placeholder.svg?raw";
import checkIconSvg from "./assets/icons/check-icon.svg?raw";
import xIconSvg from "./assets/icons/x-icon.svg?raw";
import searchIconSvg from "./assets/icons/search-icon.svg?raw";

// Tempo máximo esperando o LOAD_RESULT antes de desistir do indicador de
// carregamento — rede de segurança pra não deixar o spinner girando pra
// sempre se o host nunca responder (ex.: falha inesperada do lado Python).
const TIMEOUT_CARREGAMENTO_MS = 30000;

// Título da seção usa o mesmo rótulo curto exibido no pill (ex.: "Extintor"
// -> "EXTINTOR"), conforme o mockup — categorias sem rótulo curto caem no
// nome cheio do catálogo, só em maiúsculas.
function tituloDaSecao(categorias, categoriaAtual) {
  if (categoriaAtual === TODAS_ID) return "FAMÍLIAS";
  const categoria = categorias.find((c) => c.id === categoriaAtual);
  if (!categoria) return "FAMÍLIAS";
  return (ROTULO_CURTO_POR_CATEGORIA[categoria.id] || categoria.name).toUpperCase();
}

// Notificações de sucesso/aviso somem sozinhas rápido — uma por família,
// só pra confirmar rapidamente o que aconteceu com cada uma.
const DURACAO_TOAST_FAMILIA_MS = 3000;

export default function App() {
  const [sessao, setSessao] = useState(undefined); // undefined = ainda verificando
  const [abaAtual, setAbaAtual] = useState("biblioteca");
  const [catalogo, setCatalogo] = useState(null);
  const [categoriaAtual, setCategoriaAtual] = useState(TODAS_ID);
  const [busca, setBusca] = useState("");
  const [selecionadas, setSelecionadas] = useState(() => new Set());
  const [carregando, setCarregando] = useState(false);
  const [vinculo, setVinculo] = useState(undefined); // undefined = ainda não respondeu
  const [dimensionamentos, setDimensionamentos] = useState(undefined);
  const { toasts, adicionarToast, removerToast } = useToasts();
  const timeoutCarregamentoRef = useRef(null);

  function pararCarregamento() {
    setCarregando(false);
    if (timeoutCarregamentoRef.current) {
      clearTimeout(timeoutCarregamentoRef.current);
      timeoutCarregamentoRef.current = null;
    }
  }

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
      if (estaDentroDoWebView2()) {
        postToHost(BridgeMessageTypes.GET_PROJECT_LINK, {});
      } else {
        // Fora do WebView2 (ex.: `npm run dev` no navegador comum) não há
        // Python do outro lado pra responder GET_PROJECT_LINK — sem isso o
        // Dashboard ficaria esperando pra sempre. Simula "documento salvo,
        // sem projeto vinculado ainda", que já cai na tela "Conectar um
        // projeto" e permite testar o resto do fluxo sem o Revit aberto.
        console.warn(
          "[App] WebView2 não detectado — simulando vínculo vazio pra testar o Dashboard no navegador."
        );
        setVinculo({ docSalvo: true, projetoId: null, projetoNome: null, estruturaId: null, estruturaNome: null });
      }
    }
  }, [sessao]);

  useEffect(() => {
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (mensagem.type === BridgeMessageTypes.PROJECT_LINK) {
        setVinculo(mensagem.payload || {});
        return;
      }

      if (mensagem.type === BridgeMessageTypes.PROJECT_LINK_SAVED) {
        const { ok, erro } = mensagem.payload || {};
        if (!ok) {
          adicionarToast({
            tipo: "erro",
            titulo: "Não foi possível salvar o vínculo do projeto",
            mensagem: erro,
            duracaoMs: 9000,
          });
        }
        return;
      }

      if (mensagem.type === BridgeMessageTypes.DIMENSIONAMENTOS_STATUS) {
        setDimensionamentos(mensagem.payload || {});
        return;
      }

      if (mensagem.type !== BridgeMessageTypes.LOAD_RESULT) return;

      const { carregadas: nomesCarregados = [], jaExistentes = [], erros = [] } = mensagem.payload || {};

      // Uma notificação por família (não agrupada) — empilham conforme vão
      // sendo criadas e somem sozinhas rápido, só pra confirmar o que
      // aconteceu com cada uma.
      nomesCarregados.forEach((nome) => {
        adicionarToast({
          tipo: "sucesso",
          titulo: nome,
          mensagem: "Carregada no projeto",
          duracaoMs: DURACAO_TOAST_FAMILIA_MS,
        });
      });
      jaExistentes.forEach((nome) => {
        adicionarToast({
          tipo: "aviso",
          titulo: nome,
          mensagem: "Já existe no projeto",
          duracaoMs: DURACAO_TOAST_FAMILIA_MS,
        });
      });
      erros.forEach((erro) => {
        adicionarToast({
          tipo: "erro",
          titulo: erro.name ? `Falha ao carregar "${erro.name}"` : "Falha ao carregar",
          mensagem: erro.mensagem,
          duracaoMs: 9000,
        });
      });

      // As famílias que a gente pediu pra carregar (com sucesso ou porque
      // já existiam) saem da seleção — só ficam marcadas as que falharam,
      // prontas pra tentar de novo.
      const nomesProcessados = new Set([...nomesCarregados, ...jaExistentes]);
      if (nomesProcessados.size > 0 && catalogo) {
        setSelecionadas((atual) => {
          const nova = new Set(atual);
          catalogo.families.forEach((familia) => {
            if (nomesProcessados.has(familia.name)) nova.delete(familia.id);
          });
          return nova;
        });
      }

      pararCarregamento();
    });
  }, [adicionarToast, catalogo]);

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
    if (selecionadas.size === 0 || carregando) return;
    setCarregando(true);
    timeoutCarregamentoRef.current = setTimeout(() => {
      pararCarregamento();
      adicionarToast({
        tipo: "erro",
        titulo: "O carregamento demorou demais pra responder",
        mensagem: "Confira o projeto — as famílias podem ter sido carregadas mesmo assim.",
        duracaoMs: 9000,
      });
    }, TIMEOUT_CARREGAMENTO_MS);

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
      adicionarToast({
        tipo: "erro",
        titulo: "Não foi possível carregar as famílias selecionadas",
        mensagem: erro.message,
        duracaoMs: 9000,
      });
      pararCarregamento();
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
      <div className="notificacoes-topo">
        {carregando && (
          <div className="loading-badge">
            <span>Carregando Famílias</span>
            <span className="loading-spinner" />
          </div>
        )}
        <ToastStack toasts={toasts} onDismiss={removerToast} />
      </div>
      <Sidebar
        abaAtual={abaAtual}
        onSelecionarAba={setAbaAtual}
        projetoVinculado={!!vinculo?.projetoId}
        onDesconectar={() => postToHost(BridgeMessageTypes.DISCONNECT_PROJECT, {})}
      />

      <div className="app">
        {abaAtual === "dashboard" ? (
          // Sem <header> genérico aqui de propósito: cada tela do Dashboard
          // (ConectarProjeto/SelecionarEstrutura/DashboardEstrutura) já
          // mostra o próprio título ("Conectar um projeto", nome do
          // projeto...) — um "Dashboard" fixo por cima ficaria redundante
          // e nunca bateria com o passo atual do fluxo.
          <Dashboard vinculo={vinculo} dimensionamentos={dimensionamentos} adicionarToast={adicionarToast} />
        ) : (
          <>
            <header className="header">
              <h1>Biblioteca de Famílias</h1>
            </header>

            <div className="search-bar">
              <Icon svg={searchIconSvg} className="icone" />
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
                <p className="categorias-rotulo">Categorias</p>
                <CategoryPills
                  categorias={catalogo.categories}
                  todasIconKey={catalogo.todas_icon_key}
                  categoriaAtual={categoriaAtual}
                  onSelect={setCategoriaAtual}
                />

                <div className="secao-titulo-linha">
                  <h2 className="secao-titulo">{tituloDaSecao(catalogo.categories, categoriaAtual)}</h2>
                  {selecionadas.size > 0 && (
                    <div className="contadores">
                      <span className="contador">
                        <strong>{String(selecionadas.size).padStart(2, "0")}</strong> selecionados
                      </span>
                    </div>
                  )}
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
                          onToggle={alternarSelecao}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {selecionadas.size > 0 && (
                  <div className="acoes">
                    <button
                      type="button"
                      className="botao accent"
                      disabled={carregando}
                      onClick={carregarSelecionadas}
                    >
                      <Icon svg={carregarIconSvg} />
                      Carregar no projeto
                    </button>
                    <button type="button" className="botao" onClick={marcarTodosFiltrados}>
                      <Icon svg={checkIconSvg} />
                      Selecionar todos
                    </button>
                    <button type="button" className="botao" onClick={desmarcarTodos}>
                      <Icon svg={xIconSvg} />
                      Desmarcar todos
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
