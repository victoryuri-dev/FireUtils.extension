import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { supabase, criarSignedUrlFamilia } from "./lib/supabaseClient";
import { fetchCatalog } from "./lib/catalog";
import { postToHost, escutarMensagensDoHost, estaDentroDoWebView2, BridgeMessageTypes } from "./lib/bridge";
import LoginScreen from "./components/LoginScreen";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import SemLicenca from "./components/SemLicenca";
import AvisoAtualizacao from "./components/AvisoAtualizacao";
import AtualizacaoNecessaria from "./components/AtualizacaoNecessaria";
import { avaliarVersao, escolherAtualizacao } from "./lib/versoes";
import { listarArquivosPublicados, gerarLinksDaAtualizacao, abrirPerfilNoSite } from "./lib/atualizacao";
import { emAndamento, estadoDaMensagem } from "./lib/atualizacaoEstado";
import { buscarTokenDeLicenca, precisaRenovarToken } from "./lib/licencaToken";
import { abaLiberada, rotuloDoModuloDaAba } from "./lib/licencas";
import Icon from "./components/Icon";
import ToastStack from "./components/ToastStack";
import { useToasts } from "./lib/toasts";
import CategoryPills, { TODAS_ID, ROTULO_CURTO_POR_CATEGORIA } from "./components/CategoryPills";
import FamilyCard from "./components/FamilyCard";
import carregarIconSvg from "./assets/icons/carregado-icon-placeholder.svg?raw";
import checkIconSvg from "./assets/icons/check-icon.svg?raw";
import xIconSvg from "./assets/icons/x-icon.svg?raw";
import searchIconSvg from "./assets/icons/search-icon.svg?raw";
import libraryIconSvg from "./assets/icons/library-icon.svg?raw";

// Tempo máximo esperando o LOAD_RESULT antes de desistir do indicador de
// carregamento — rede de segurança pra não deixar o spinner girando pra
// sempre se o host nunca responder (ex.: falha inesperada do lado Python).
const TIMEOUT_CARREGAMENTO_MS = 30000;

// Título da seção usa o mesmo rótulo curto exibido no pill (ex.: "Extintor"
// -> "EXTINTOR"), conforme o mockup — categorias sem rótulo curto caem no
// nome cheio do catálogo, só em maiúsculas.
/**
 * Informa ao Python quem está logado.
 *
 * O plugin atual não usa o refresh token: a licença é um token assinado que
 * esta dockpane busca (ver LICENCAS, abaixo) e o Python confere offline. O
 * SET_SESSAO só continua indo para as versões antigas do plugin, que ainda
 * conferiam a licença na rede com o refresh token — o plugin novo o ignora e
 * apenas responde com o estado da licença. Pode sair quando nenhum cliente
 * estiver numa versão antiga.
 *
 * Sem sessão (logout, ou sessão expirada), manda limpar — assim cancelar o
 * login aqui também corta o acesso às ferramentas do Revit.
 */
function enviarSessaoAoHost(sessao) {
  // Sem checar estaDentroDoWebView2() antes: fora do Revit o postToHost já
  // avisa no console que não encontrou a ponte. Sair caladinho aqui deixaria
  // o caso "logado na dockpane, barrado nas ferramentas" sem pista alguma.
  if (sessao?.refresh_token) {
    postToHost(BridgeMessageTypes.SET_SESSAO, { refreshToken: sessao.refresh_token });
  } else {
    postToHost(BridgeMessageTypes.LIMPAR_SESSAO, {});
  }
}

function tituloDaSecao(categorias, categoriaAtual) {
  if (categoriaAtual === TODAS_ID) return "FAMÍLIAS";
  const categoria = categorias.find((c) => c.id === categoriaAtual);
  if (!categoria) return "FAMÍLIAS";
  return (ROTULO_CURTO_POR_CATEGORIA[categoria.id] || categoria.name).toUpperCase();
}

// Notificações de sucesso/aviso somem sozinhas rápido — uma por família,
// só pra confirmar rapidamente o que aconteceu com cada uma.
const DURACAO_TOAST_FAMILIA_MS = 3000;

// Navegação por URL (?aba=...) — sem isso, um F5/reload (ou o reload
// forçado ao desconectar um projeto, ver onDesconectar abaixo) sempre
// voltava pra Biblioteca de Famílias, perdendo a aba em que o usuário
// estava. Sem lib de rotas: só a aba atual precisa sobreviver a um
// reload (o estado interno do Dashboard — estrutura selecionada etc. —
// já se reconstrói sozinho a partir do vínculo salvo no firedata.json).
// Intervalo mínimo entre dois pedidos de token de licença ao servidor.
const TOKEN_INTERVALO_MIN_MS = 5 * 60 * 1000;

const ABAS_VALIDAS = ["biblioteca", "dashboard", "hidrantes", "saidas"];

function lerAbaDaUrl() {
  const aba = new URLSearchParams(window.location.search).get("aba");
  return ABAS_VALIDAS.includes(aba) ? aba : "biblioteca";
}

// Qual versão nova o usuário dispensou ("Depois"): o aviso só volta quando sair
// outra. localStorage pode estar indisponível — nesse caso o aviso só reaparece
// a cada abertura, o que é aceitável.
const CHAVE_AVISO_DISPENSADO = "fireutils.atualizacaoDispensada";

function lerAvisoDispensado() {
  try {
    return window.localStorage.getItem(CHAVE_AVISO_DISPENSADO);
  } catch {
    return null;
  }
}

export default function App() {
  const [sessao, setSessao] = useState(undefined); // undefined = ainda verificando
  const [abaAtual, setAbaAtual] = useState(lerAbaDaUrl);
  const [catalogo, setCatalogo] = useState(null);
  const [categoriaAtual, setCategoriaAtual] = useState(TODAS_ID);
  const [busca, setBusca] = useState("");
  const [selecionadas, setSelecionadas] = useState(() => new Set());
  const [carregando, setCarregando] = useState(false);
  const [vinculo, setVinculo] = useState(undefined); // undefined = ainda não respondeu
  // Módulos que esta conta pode usar, resolvidos pelo Python uma vez por
  // sessão do Revit. null = ainda não respondeu (não é o mesmo que "nenhum":
  // tratar os dois igual faria a tela piscar um bloqueio indevido).
  const [modulosLiberados, setModulosLiberados] = useState(null);
  // Versão do plugin instalado, informada junto das licenças: undefined = o
  // Python ainda não respondeu; null = plugin antigo, que não informa versão.
  const [versaoPlugin, setVersaoPlugin] = useState(undefined);
  const [arquivosPublicados, setArquivosPublicados] = useState(null); // nomes no bucket
  // Versão do instalador de base e se o plugin aplica pacotes (ver LICENCAS).
  const [baseInstalador, setBaseInstalador] = useState(null);
  const [suportaPacote, setSuportaPacote] = useState(false);
  // O plugin instalado sabe baixar e instalar atualizações (informado junto
  // das licenças); sem isso o botão leva ao perfil no site.
  const [suportaAtualizacao, setSuportaAtualizacao] = useState(false);
  const [estadoAtualizacao, setEstadoAtualizacao] = useState(null);
  const [avisoDispensado, setAvisoDispensado] = useState(lerAvisoDispensado);
  const [dimensionamentos, setDimensionamentos] = useState(undefined);
  const [gravandoQuantitativos, setGravandoQuantitativos] = useState(false);
  const [atribuindoEstrutura, setAtribuindoEstrutura] = useState(false);
  const { toasts, adicionarToast, removerToast } = useToasts();
  const timeoutCarregamentoRef = useRef(null);
  // Espelha `catalogo` num ref só pra o listener da bridge (abaixo) poder
  // ler o valor mais atual sem precisar de `catalogo` na dependência do
  // useEffect — ver comentário lá.
  const catalogoRef = useRef(null);
  useEffect(() => {
    catalogoRef.current = catalogo;
  }, [catalogo]);
  // Mesmo motivo do catalogoRef: o listener da bridge é criado uma vez só e
  // precisa saber se há sessão agora, sem depender dela no useEffect.
  const sessaoRef = useRef(undefined);
  useEffect(() => {
    sessaoRef.current = sessao;
  }, [sessao]);
  // Quando o token de licença foi pedido ao servidor pela última vez. Evita
  // laço se o plugin recusar o token que acabou de receber (cada recusa
  // dispara outra mensagem LICENCAS).
  const tokenPedidoEmRef = useRef(0);
  // Em que ponto está a obtenção do token: "idle", "buscando" (esperando o
  // servidor) ou "enviado" (entregue ao Python, esperando a resposta dele).
  const faseTokenRef = useRef("idle");

  // replaceState (não pushState): troca de aba não deve empilhar
  // histórico de navegação — não há botão "voltar" nessa UI, e um
  // histórico crescendo a cada clique na sidebar não serviria pra nada.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("aba") === abaAtual) return;
    params.set("aba", abaAtual);
    window.history.replaceState(null, "", `${window.location.pathname}?${params}${window.location.hash}`);
  }, [abaAtual]);

  function gravarQuantitativos() {
    if (gravandoQuantitativos) return;
    setGravandoQuantitativos(true);
    postToHost(BridgeMessageTypes.GRAVAR_QUANTITATIVOS, {});
  }

  function atribuirEstrutura(estruturaNome) {
    if (atribuindoEstrutura || !estruturaNome) return;
    setAtribuindoEstrutura(true);
    postToHost(BridgeMessageTypes.ASSIGN_ESTRUTURA_SELECAO, { estruturaNome });
  }

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
    supabase.auth.getSession().then(({ data }) => {
      setSessao(data.session);
      enviarSessaoAoHost(data.session);
    });
    const { data: assinatura } = supabase.auth.onAuthStateChange((evento, novaSessao) => {
      setSessao(novaSessao);
      enviarSessaoAoHost(novaSessao);

      // Recarrega ao sair da conta, zerando de uma vez tudo que ficou da
      // sessão anterior (licenças, vínculo de projeto, seleção, busca) —
      // mesmo motivo do reload em onDesconectar. Preso ao evento SIGNED_OUT,
      // e não a "ficou sem sessão": no boot sem login o estado também é
      // nulo, e recarregar ali seria um laço infinito.
      if (evento === "SIGNED_OUT") {
        window.location.reload();
      }
    });
    return () => assinatura.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (sessao) {
      fetchCatalog().then(setCatalogo);
      if (estaDentroDoWebView2()) {
        postToHost(BridgeMessageTypes.GET_PROJECT_LINK, {});
        // O SET_SESSAO do login já responde LICENCAS, mas reabrir o painel
        // numa sessão em que o login aconteceu antes não dispararia nada —
        // aqui o estado é recuperado do que o Python já resolveu.
        postToHost(BridgeMessageTypes.GET_LICENCAS, {});
      } else {
        // Fora do WebView2 (ex.: `npm run dev` no navegador comum) não há
        // Python do outro lado pra responder GET_PROJECT_LINK — sem isso o
        // Dashboard ficaria esperando pra sempre. Simula "documento salvo,
        // sem projeto vinculado ainda", que já cai na tela "Conectar um
        // projeto" e permite testar o resto do fluxo sem o Revit aberto.
        console.warn(
          "[App] WebView2 não detectado — simulando vínculo vazio pra testar o Dashboard no navegador."
        );
        setVinculo({ docSalvo: true, projetoId: null, projetoNome: null, estruturas: [] });
        // Idem para as licenças: sem Python, esperar a resposta deixaria as
        // abas em carregamento eterno.
        //
        // Só o build de desenvolvimento libera tudo. Em produção esta mesma
        // condição vale para qualquer um que abra a URL da dockpane no
        // navegador — liberar ali entregaria Dashboard, Hidrantes e Saídas
        // a quem só tem o link. Quem precisa das telas é o Revit, e lá o
        // Python responde com a licença de verdade.
        setModulosLiberados(import.meta.env.DEV ? ["pro"] : []);
      }
    }
  }, [sessao]);

  // Última versão publicada, para avisar de atualização. Só dentro do Revit:
  // no navegador comum não há plugin instalado para comparar.
  const logado = !!sessao;
  useEffect(() => {
    if (!logado || !estaDentroDoWebView2()) return;
    listarArquivosPublicados().then(setArquivosPublicados);
  }, [logado]);

  // A atualização a oferecer: pacote rápido (só Python) se servir a esta
  // instalação, senão o instalador. { tipo, versao, arquivo } ou null.
  const versaoPublicada = useMemo(
    () =>
      arquivosPublicados && versaoPlugin !== undefined
        ? escolherAtualizacao(arquivosPublicados, {
            instalada: versaoPlugin,
            base: baseInstalador,
            suportaPacote,
          })
        : null,
    [arquivosPublicados, versaoPlugin, baseInstalador, suportaPacote]
  );

  const avaliacaoVersao = useMemo(
    () => avaliarVersao({ instalada: versaoPlugin, publicada: versaoPublicada }),
    [versaoPlugin, versaoPublicada]
  );

  // O Python baixa, confere e instala (plugin_atualizacao.py) — com a sessão
  // daqui só se geram os links do bucket privado. Plugin sem esse suporte, ou
  // sem conseguir os links, cai no perfil do site.
  async function baixarAtualizacao() {
    if (emAndamento(estadoAtualizacao) || ["agendada", "aplicada"].includes(estadoAtualizacao?.fase)) return;
    if (!suportaAtualizacao || !versaoPublicada) {
      abrirPerfilNoSite();
      return;
    }
    setEstadoAtualizacao({ fase: "preparando" });
    const links = await gerarLinksDaAtualizacao(versaoPublicada);
    if (links.erro) {
      setEstadoAtualizacao({ fase: "erro", erro: links.erro });
      return;
    }
    postToHost(
      versaoPublicada.tipo === "pacote"
        ? BridgeMessageTypes.INSTALAR_PACOTE
        : BridgeMessageTypes.INSTALAR_ATUALIZACAO,
      { versao: versaoPublicada.versao, arquivo: versaoPublicada.arquivo, ...links }
    );
  }

  function dispensarAviso() {
    const versao = avaliacaoVersao.versaoNova;
    setAvisoDispensado(versao);
    try {
      window.localStorage.setItem(CHAVE_AVISO_DISPENSADO, versao);
    } catch {
      // sem localStorage: vale só até fechar o painel
    }
  }

  // IMPORTANTE: este listener assina o canal de mensagens do WebView2 (uma
  // vez só, no mount) e NUNCA deve depender de estado que muda logo depois
  // do boot (como `catalogo`, que só carrega depois do login). Um
  // useEffect com `catalogo` na dependência recriaria este listener bem
  // na hora em que GET_PROJECT_LINK normalmente já recebeu resposta —
  // removeEventListener/addEventListener não são atômicos, então uma
  // mensagem (ex.: o PROJECT_LINK que o Python reenvia depois de um
  // SET_PROJECT_LINK) podia chegar bem nesse instantinho e ser
  // simplesmente descartada, sem erro nenhum (nem no console do
  // navegador, nem no do pyRevit) — o Dashboard ficava preso em
  // "Carregando..." pra sempre, sem nenhuma pista do porquê. `catalogoRef`
  // (acima) resolve isso: o handler lê o valor mais atual sem precisar
  // que o efeito seja recriado.
  useEffect(() => {
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem) return;

      if (
        mensagem.type === BridgeMessageTypes.ATUALIZACAO_PROGRESSO ||
        mensagem.type === BridgeMessageTypes.ATUALIZACAO_RESULTADO
      ) {
        const novo = estadoDaMensagem(mensagem.type, mensagem.payload);
        setEstadoAtualizacao(novo);
        if (novo?.fase === "aplicada") {
          // Pacote instalado com o Revit aberto: o Python já carregado só muda
          // depois de reiniciar, e a pessoa precisa saber.
          adicionarToast({
            tipo: "sucesso",
            titulo: "Atualização instalada",
            mensagem: "Reinicie o Revit para concluir a atualização.",
            duracaoMs: 20000,
          });
        }
        return;
      }

      if (mensagem.type === BridgeMessageTypes.LICENCAS) {
        const resumo = mensagem.payload || {};
        const { modulos, erro } = resumo;
        setVersaoPlugin(resumo.versaoPlugin ?? null);
        setSuportaAtualizacao(resumo.suportaAtualizacao === true);
        setSuportaPacote(resumo.suportaPacote === true);
        setBaseInstalador(resumo.baseInstalador ?? null);
        if (erro) {
          // Também no console: é a única janela acessível de dentro do
          // Revit, já que a saída do pyRevit some com o engine que a abriu.
          console.warn("[licenças] falha:", erro);
        } else {
          console.info("[licenças] módulos liberados:", modulos);
        }

        // O Python guarda um token assinado pelo servidor e o confere
        // offline. Sem um válido (primeira vez neste computador, ou perto de
        // vencer), busca um novo com a sessão daqui — é a renovação
        // automática que mantém as ferramentas funcionando offline.
        const precisa = precisaRenovarToken(resumo);
        const semAcessoAinda = !modulos?.length;
        const fase = faseTokenRef.current;

        if (fase === "enviado") {
          // Resposta do Python ao token que acabou de ser entregue.
          faseTokenRef.current = "idle";
          if (precisa) {
            adicionarToast({
              tipo: "erro",
              titulo: "Não foi possível validar a licença",
              mensagem: erro || "O plugin não aceitou a licença recebida do servidor.",
              duracaoMs: 9000,
            });
          }
        } else if (fase === "buscando") {
          // Outra resposta chegou enquanto o servidor ainda é consultado.
          // Quem não tem acesso continua em "carregando": mostrar "sem
          // licença" agora seria um aviso falso para quem só ainda não
          // ativou este computador.
          if (semAcessoAinda) return;
        } else if (
          sessaoRef.current &&
          precisa &&
          Date.now() - tokenPedidoEmRef.current > TOKEN_INTERVALO_MIN_MS
        ) {
          tokenPedidoEmRef.current = Date.now();
          faseTokenRef.current = "buscando";
          buscarTokenDeLicenca().then((token) => {
            if (token) {
              // O Python responde de novo com LICENCAS, já com o token novo.
              faseTokenRef.current = "enviado";
              postToHost(BridgeMessageTypes.SET_LICENCA_TOKEN, { token });
              return;
            }
            // Sem token novo vale o que o computador já tinha; quem não
            // tinha nada fica sem acesso, e vale dizer por quê.
            faseTokenRef.current = "idle";
            setModulosLiberados(modulos || []);
            if (semAcessoAinda) {
              adicionarToast({
                tipo: "erro",
                titulo: "Não foi possível ativar a licença",
                mensagem: "Confira a conexão com a internet e abra o painel de novo.",
                duracaoMs: 9000,
              });
            }
          });
          if (semAcessoAinda) return;
        }

        // Falha vira lista vazia, não null: null significa "ainda não sei" e
        // deixaria a tela em carregamento para sempre.
        setModulosLiberados(modulos || []);
        return;
      }

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

      if (mensagem.type === BridgeMessageTypes.HIDRANTES_CLASSIFICACAO_SAVED) {
        const { ok, erro, valorSistema } = mensagem.payload || {};
        adicionarToast(
          ok
            ? { tipo: "sucesso", titulo: "Classificação aplicada", mensagem: valorSistema, duracaoMs: 6000 }
            : { tipo: "erro", titulo: "Não foi possível aplicar a classificação", mensagem: erro, duracaoMs: 9000 }
        );
        return;
      }

      if (mensagem.type === BridgeMessageTypes.QUANTITATIVOS_GRAVADOS) {
        setGravandoQuantitativos(false);
        const { ok, erro, medidas = [] } = mensagem.payload || {};
        if (!ok) {
          adicionarToast({
            tipo: "erro",
            titulo: "Não foi possível gravar quantitativos",
            mensagem: erro,
            duracaoMs: 9000,
          });
          return;
        }
        // Uma linha por (medida, estrutura) — mais uma por grupo de itens
        // sem Estrutura reconhecida (estruturaNome null, sem erro nem
        // envio: ver quantitativos_core.py:salvar_todos).
        const comFalha = medidas.filter((m) => m.erro);
        const resumo = medidas
          .map((m) => {
            const rotulo = m.estruturaNome ? `${m.rotulo} — ${m.estruturaNome}` : m.rotulo;
            if (m.erro) return `${rotulo}: falhou (${m.erro})`;
            if (m.naoReconhecidos?.length > 0) {
              return `${m.rotulo}: Estrutura não reconhecida em algum item (${m.naoReconhecidos.join(", ")})`;
            }
            if (!m.estruturaNome) return null; // nada coletado pra essa medida
            if (m.enviado === false) return `${rotulo}: ${m.quantidade} (não enviado — ${m.motivo})`;
            return `${rotulo}: ${m.quantidade}`;
          })
          .filter(Boolean)
          .join(" • ");
        adicionarToast({
          tipo: comFalha.length > 0 ? "aviso" : "sucesso",
          titulo: "Quantitativos gravados",
          mensagem: resumo || "Nenhum item encontrado.",
          duracaoMs: 9000,
        });
        return;
      }

      if (mensagem.type === BridgeMessageTypes.ESTRUTURA_ATRIBUIDA) {
        setAtribuindoEstrutura(false);
        const { ok, erro, estruturaNome, marcados, ignorados } = mensagem.payload || {};
        if (!ok) {
          adicionarToast({
            tipo: "erro",
            titulo: "Não foi possível atribuir a estrutura",
            mensagem: erro,
            duracaoMs: 9000,
          });
          return;
        }
        adicionarToast({
          tipo: "sucesso",
          titulo: `Estrutura "${estruturaNome}" atribuída`,
          mensagem: `${marcados} elemento(s) marcado(s)${ignorados ? ` • ${ignorados} ignorado(s) (categoria sem o parâmetro)` : ""}`,
          duracaoMs: 7000,
        });
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
      if (nomesProcessados.size > 0 && catalogoRef.current) {
        setSelecionadas((atual) => {
          const nova = new Set(atual);
          catalogoRef.current.families.forEach((familia) => {
            if (nomesProcessados.has(familia.name)) nova.delete(familia.id);
          });
          return nova;
        });
      }

      pararCarregamento();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adicionarToast]);

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
        onDesconectar={() => {
          // Reload completo em vez de só esperar o PROJECT_LINK de volta:
          // zera estado local que não é derivado do vínculo (seleção de
          // famílias, busca, categoria...), mesmo "limpo" que reabrir o
          // painel. O DISCONNECT_PROJECT já foi enviado ao host antes do
          // reload — é um postMessage síncrono pro lado nativo do
          // WebView2, não depende da página React continuar viva pra
          // completar (mesmo padrão de SELECIONAR_TRECHO_HIDRANTE, ver
          // lib/bridge.js). abaAtual já está salvo na URL (?aba=...), e
          // o Dashboard parte de "Conectar um projeto" assim que
          // GET_PROJECT_LINK voltar sem projetoId, de qualquer forma.
          postToHost(BridgeMessageTypes.DISCONNECT_PROJECT, {});
          window.location.reload();
        }}
        email={sessao?.user?.email}
        modulosLiberados={modulosLiberados}
        versaoPlugin={versaoPlugin}
        baseInstalador={baseInstalador}
        atualizacao={
          avaliacaoVersao.estado === "disponivel" || avaliacaoVersao.estado === "obrigatoria"
            ? {
                versaoNova: avaliacaoVersao.versaoNova,
                estado: estadoAtualizacao,
                onBaixar: baixarAtualizacao,
              }
            : null
        }
      />

      <div className="app">
        {avaliacaoVersao.estado === "obrigatoria" ? (
          <AtualizacaoNecessaria
            versaoNova={avaliacaoVersao.versaoNova}
            estado={estadoAtualizacao}
            onBaixar={baixarAtualizacao}
          />
        ) : (
        <>
        {avaliacaoVersao.estado === "disponivel" && (avisoDispensado !== avaliacaoVersao.versaoNova || estadoAtualizacao?.fase) && (
          <AvisoAtualizacao
            versaoNova={avaliacaoVersao.versaoNova}
            estado={estadoAtualizacao}
            onBaixar={baixarAtualizacao}
            onDispensar={dispensarAviso}
          />
        )}
        {abaAtual === "dashboard" || abaAtual === "saidas" || abaAtual === "hidrantes" ? (
          modulosLiberados === null ? (
            // Ainda sem resposta do Python: esperar, em vez de piscar um
            // bloqueio que pode nem se confirmar.
            <div className="tela-carregando">
              <span className="loading-spinner" />
            </div>
          ) : !abaLiberada(modulosLiberados, abaAtual) ? (
            <SemLicenca
              modulo={rotuloDoModuloDaAba(abaAtual)}
              temAlgumaLicenca={modulosLiberados.length > 0}
              foraDoRevit={!estaDentroDoWebView2()}
            />
          ) : (
          // Sem <header> genérico aqui de propósito: cada tela do Dashboard
          // (ConectarProjeto/SelecionarEstrutura/DashboardEstrutura) já
          // mostra o próprio título ("Conectar um projeto", nome do
          // projeto...) — um "Dashboard" fixo por cima ficaria redundante
          // e nunca bateria com o passo atual do fluxo. `modo` decide, uma
          // vez que a estrutura já está carregada, se DashboardEstrutura
          // mostra o dashboard normal ou uma das páginas próprias (Saída
          // de Emergência / Sistema de Hidrantes — mesmo destino do
          // atalho da sidebar e do respectivo cartão de dimensionamento)
          // — ver DashboardEstrutura.jsx.
          <Dashboard
            vinculo={vinculo}
            dimensionamentos={dimensionamentos}
            adicionarToast={adicionarToast}
            modo={abaAtual}
            onAbrirSaidaEmergencia={() => setAbaAtual("saidas")}
            onAbrirHidrantes={() => setAbaAtual("hidrantes")}
            onGravarQuantitativos={gravarQuantitativos}
            gravandoQuantitativos={gravandoQuantitativos}
            onAtribuirEstrutura={atribuirEstrutura}
            atribuindoEstrutura={atribuindoEstrutura}
          />
          )
        ) : (
          <>
            <div className="biblioteca-scroll">
              <header className="header">
                <span className="se-pagina-icone">
                  <Icon svg={libraryIconSvg} />
                </span>
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
                  <CategoryPills
                    categorias={catalogo.categories}
                    todasIconKey={catalogo.todas_icon_key}
                    categoriaAtual={categoriaAtual}
                    onSelect={setCategoriaAtual}
                  />
                <div>
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
                </>
              )}
            </div>

            {catalogo && selecionadas.size > 0 && (
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
