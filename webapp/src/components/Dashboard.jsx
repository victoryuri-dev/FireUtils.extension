import { useEffect, useState } from "react";
import Loader from "./Loader";
import saveIconPng from "../assets/icons/save-icon.png";
import { postToHost, BridgeMessageTypes } from "../lib/bridge";
import { buscarProjeto } from "../lib/projectData";
import { estruturasDoProjeto, dashboardEstrutura, pavimentosCompletos } from "../lib/projetoDados";
import ConectarProjeto from "./dashboard/ConectarProjeto";
import SelecionarEstrutura from "./dashboard/SelecionarEstrutura";
import DashboardEstrutura from "./dashboard/DashboardEstrutura";
import CorrelacaoNiveisModal from "./dashboard/CorrelacaoNiveisModal";

const ESTADO_INICIAL = { carregando: false, erro: null, linha: null, estruturaId: null };

// Timeout defensivo pra qualquer chamada ao Supabase feita aqui — sem
// isso, uma sessão de auth restaurada de forma inconsistente após um
// reload/reabertura do Revit (o supabase-js às vezes fica esperando uma
// renovação de token que nunca resolve, sem lançar erro nenhum: nem no
// console do navegador, nem no do pyRevit) deixava o Dashboard preso em
// "Carregando..." pra sempre, sem nenhum jeito de perceber o que
// aconteceu. Isso converte esse tipo de trava silenciosa num erro visível.
const TIMEOUT_SUPABASE_MS = 12000;

function comTimeout(promessa, ms, mensagem) {
  return Promise.race([
    promessa,
    new Promise((_, rejeitar) => setTimeout(() => rejeitar(new Error(mensagem)), ms)),
  ]);
}

/** Espera o status da estrutura chegar do Revit; se demorar, oferece tentar
 * de novo em vez de ficar carregando para sempre. */
function StatusAguardando({ estruturaId }) {
  const [demorou, setDemorou] = useState(false);
  useEffect(() => {
    setDemorou(false);
    const t = setTimeout(() => setDemorou(true), 8000);
    return () => clearTimeout(t);
  }, [estruturaId]);

  if (!demorou) return <div className="tela-carregando"><Loader size={40} /></div>;
  return (
    <div className="dashboard-tela">
      <p className="vazio">O Revit não respondeu ao verificar a correlação de níveis.</p>
      <button
        type="button"
        className="se-botao"
        onClick={() => {
          setDemorou(false);
          postToHost(BridgeMessageTypes.GET_DIMENSIONAMENTOS_STATUS, { estruturaId });
          setTimeout(() => setDemorou(true), 8000);
        }}
      >
        Tentar de novo
      </button>
    </div>
  );
}

/**
 * Orquestra o fluxo: Conectar um projeto -> (Selecione as estruturas, se
 * nenhuma ainda vinculada) -> Dashboard de UMA estrutura por vez. `vinculo`
 * vem do firedata.json do documento Revit ativo (ver lib/bridge.js e
 * project_link_bridge.py do lado Python) — a busca do projeto em si é
 * direto no Supabase (lib/projectData.js + lib/projetoDados.js), com a
 * sessão do usuário logado. `linha` guarda a linha crua da tabela
 * `projetos` (id/nome/dados/updated_at) já buscada — as telas derivam
 * dela via lib/projetoDados.js, sem chamada adicional ao trocar de
 * estrutura.
 *
 * Um arquivo Revit pode ter VÁRIAS estruturas vinculadas (`vinculo.estruturas`,
 * ver bridge.js) — isso não atribui nada a nenhuma família/ambiente (ver
 * docstring de project_link_bridge.py); é só o conjunto que a ferramenta
 * "Atribuir seleção à estrutura" oferece, e a lista de abas pra navegar
 * entre os dashboards de cada uma (`estado.estruturaId` escolhe qual tela
 * aparece agora — troca local, não manda SET_PROJECT_LINK de novo).
 */
export default function Dashboard({
  vinculo,
  dimensionamentos,
  adicionarToast,
  modo,
  onAbrirSaidaEmergencia,
  onAbrirHidrantes,
  onGravarQuantitativos,
  gravandoQuantitativos,
  onAtribuirEstrutura,
  atribuindoEstrutura,
}) {
  const [estado, setEstado] = useState(ESTADO_INICIAL);

  function persistirVinculo(linha, estruturasEscolhidas) {
    postToHost(BridgeMessageTypes.SET_PROJECT_LINK, {
      projetoId: linha.id,
      projetoNome: (linha.dados && linha.dados.nome) || linha.nome,
      estruturas: estruturasEscolhidas.map((e) => ({ id: e.id, nome: e.nome })),
      uf: linha.dados?.uf,
      areaConstruida: linha.dados?.areaConstruidaTotal,
    });
  }

  async function carregarProjeto(projetoId, estruturaIdPreferida) {
    setEstado((s) => ({ ...s, carregando: true, erro: null }));
    try {
      const linha =
        estado.linha && estado.linha.id === projetoId
          ? estado.linha
          : await comTimeout(
              buscarProjeto(projetoId),
              TIMEOUT_SUPABASE_MS,
              "O Supabase demorou demais pra responder. Feche e reabra a dockpane (ou o Revit) e tente de novo."
            );
      const estruturas = estruturasDoProjeto(linha);

      if (estruturas.length === 0) {
        setEstado({
          carregando: false,
          erro: "Este projeto ainda não tem nenhuma estrutura cadastrada no site.",
          linha,
          estruturaId: null,
        });
        return;
      }

      // Vínculo salvo de uma sessão anterior (vinculo.estruturas, ver
      // Dashboard useEffect abaixo) pode ter estruturas que não existem
      // mais (removidas/recriadas no site nesse meio tempo) — filtra só
      // as que ainda batem.
      const idsVinculados = new Set((vinculo?.estruturas || []).map((e) => e.id));
      const vinculadasValidas = estruturas.filter((e) => idsVinculados.has(e.id));

      if (vinculadasValidas.length === 0) {
        // Nenhuma estrutura vinculada ainda (ou nenhuma válida) — mostra a
        // tela de seleção em vez de já cravar um vínculo inválido/vazio.
        setEstado({ carregando: false, erro: null, linha, estruturaId: null });
        return;
      }

      const alvoId =
        estruturaIdPreferida && vinculadasValidas.some((e) => e.id === estruturaIdPreferida)
          ? estruturaIdPreferida
          : vinculadasValidas[0].id;
      setEstado({ carregando: false, erro: null, linha, estruturaId: alvoId });
    } catch (ex) {
      console.error("[Dashboard] Falha ao carregar projeto/estrutura:", ex);
      adicionarToast?.({
        tipo: "erro",
        titulo: "Não foi possível carregar os dados do projeto",
        mensagem: ex.message,
        duracaoMs: 9000,
      });
      setEstado((s) => ({ ...s, carregando: false, erro: ex.message }));
    }
  }

  function confirmarEstruturas(linha, escolhidas) {
    persistirVinculo(linha, escolhidas);
    setEstado({ carregando: false, erro: null, linha, estruturaId: escolhidas[0].id });
  }

  // Sincroniza com o vínculo salvo no documento Revit ativo — dispara ao
  // entrar na aba (vinculo já vem preenchido de uma sessão anterior) e
  // depois de desconectar (projetoId vira null, reseta o estado local).
  useEffect(() => {
    if (!vinculo || vinculo.docSalvo === false) return;

    if (!vinculo.projetoId) {
      if (estado.linha) setEstado(ESTADO_INICIAL);
      return;
    }

    const estruturaAindaVinculada =
      !estado.estruturaId || (vinculo.estruturas || []).some((e) => e.id === estado.estruturaId);
    const jaCarregado = estado.linha?.id === vinculo.projetoId && estruturaAindaVinculada;
    if (jaCarregado || estado.carregando) return;

    carregarProjeto(vinculo.projetoId, estado.estruturaId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vinculo]);

  // Status dos dimensionamentos locais — só faz sentido pedir depois que
  // uma estrutura está de fato carregada na tela. Saída de Emergência e
  // Correlacionar Níveis ficam escopados à estrutura sendo vista agora
  // (Hidrantes é sistema único do projeto, sempre geral — ver
  // project_link_bridge.py).
  useEffect(() => {
    if (estado.estruturaId) {
      postToHost(BridgeMessageTypes.GET_DIMENSIONAMENTOS_STATUS, { estruturaId: estado.estruturaId });
    }
  }, [estado.estruturaId]);

  if (!vinculo) {
    return <div className="tela-carregando"><Loader size={40} /></div>;
  }

  if (vinculo.docSalvo === false) {
    return (
      <div className="dashboard-tela dashboard-aviso-salvar">
        <img src={saveIconPng} alt="" className="dashboard-aviso-salvar-icone" />
        <p className="dashboard-aviso-salvar-texto">
          Salve o projeto Revit
          <br />
          antes de conectar.
        </p>
        <button type="button" className="se-botao" onClick={() => window.location.reload()}>
          Recarregar página
        </button>
      </div>
    );
  }

  if (estado.carregando && !estado.linha) {
    return <div className="tela-carregando"><Loader size={40} /></div>;
  }

  if (estado.erro) {
    return (
      <div className="dashboard-tela">
        <p className="vazio">{estado.erro}</p>
      </div>
    );
  }

  if (!estado.linha) {
    return <ConectarProjeto onSelecionar={(projeto) => carregarProjeto(projeto.id, null)} />;
  }

  if (!estado.estruturaId) {
    return (
      <SelecionarEstrutura
        projeto={estado.linha}
        estruturas={estruturasDoProjeto(estado.linha)}
        onConfirmar={(escolhidas) => confirmarEstruturas(estado.linha, escolhidas)}
      />
    );
  }

  // Trava de etapa: 1) estruturas vinculadas -> 2) níveis correlacionados
  // -> dashboard. O status só vale se for da estrutura atual (o Python
  // ecoa `estruturaId`); até chegar, espera em vez de piscar o modal.
  // Plugin antigo (sem o eco de `estruturaId`) responde sem o campo: aceita
  // a resposta mesmo assim, senão o carregamento nunca terminaria.
  const statusAtual =
    !!dimensionamentos &&
    (dimensionamentos.estruturaId === undefined || dimensionamentos.estruturaId === estado.estruturaId);
  if (!statusAtual) {
    return <StatusAguardando estruturaId={estado.estruturaId} />;
  }
  // Estrutura sem pavimentos cadastrados não tem o que correlacionar.
  if (!dimensionamentos.niveis && pavimentosCompletos(estado.linha, estado.estruturaId).length > 0) {
    const estruturaAtual = dashboardEstrutura(estado.linha, estado.estruturaId);
    return (
      <CorrelacaoNiveisModal
        key={estado.estruturaId}
        obrigatorio
        projeto={estado.linha}
        estrutura={estruturaAtual}
        adicionarToast={adicionarToast}
      />
    );
  }

  const estruturasVinculadas = (vinculo.estruturas || []).length > 0
    ? vinculo.estruturas
    : estruturasDoProjeto(estado.linha).filter((e) => e.id === estado.estruturaId);

  return (
    <DashboardEstrutura
      projeto={estado.linha}
      estrutura={dashboardEstrutura(estado.linha, estado.estruturaId)}
      estruturasVinculadas={estruturasVinculadas}
      onTrocarEstrutura={(estruturaId) => setEstado((s) => ({ ...s, estruturaId }))}
      dimensionamentos={dimensionamentos}
      adicionarToast={adicionarToast}
      modo={modo}
      onAbrirSaidaEmergencia={onAbrirSaidaEmergencia}
      onAbrirHidrantes={onAbrirHidrantes}
      onGravarQuantitativos={onGravarQuantitativos}
      gravandoQuantitativos={gravandoQuantitativos}
      onAtribuirEstrutura={onAtribuirEstrutura}
      atribuindoEstrutura={atribuindoEstrutura}
      // A tela de Saída de Emergência edita e persiste direto no Supabase
      // (ver AcessosDescargasView.jsx) — isso atualiza `estado.linha` aqui
      // pra manter uma única fonte de verdade (a mesma linha que o resto
      // do Dashboard já lê), sem precisar buscar o projeto de novo.
      onAtualizarProjeto={(novaLinha) => setEstado((s) => ({ ...s, linha: novaLinha }))}
    />
  );
}
