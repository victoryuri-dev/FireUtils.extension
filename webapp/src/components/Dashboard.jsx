import { useEffect, useState } from "react";
import { postToHost, BridgeMessageTypes } from "../lib/bridge";
import { buscarProjeto } from "../lib/projectData";
import { estruturasDoProjeto, dashboardEstrutura } from "../lib/projetoDados";
import ConectarProjeto from "./dashboard/ConectarProjeto";
import SelecionarEstrutura from "./dashboard/SelecionarEstrutura";
import DashboardEstrutura from "./dashboard/DashboardEstrutura";

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

/**
 * Orquestra o fluxo: Conectar um projeto -> (Selecione uma estrutura, se
 * houver mais de uma) -> Dashboard do projeto/estrutura. `vinculo` vem do
 * firedata.json do documento Revit ativo (ver lib/bridge.js e
 * project_link_bridge.py do lado Python) — a busca do projeto em si é
 * direto no Supabase (lib/projectData.js + lib/projetoDados.js), com a
 * sessão do usuário logado. `linha` guarda a linha crua da tabela
 * `projetos` (id/nome/dados/updated_at) já buscada — as telas derivam
 * dela via lib/projetoDados.js, sem chamada adicional ao trocar de
 * estrutura.
 */
export default function Dashboard({ vinculo, dimensionamentos, adicionarToast, modo, onAbrirSaidaEmergencia }) {
  const [estado, setEstado] = useState(ESTADO_INICIAL);

  function persistirVinculo(linha, estruturaId) {
    const painel = dashboardEstrutura(linha, estruturaId);
    if (!painel) return;
    postToHost(BridgeMessageTypes.SET_PROJECT_LINK, {
      projetoId: linha.id,
      projetoNome: (linha.dados && linha.dados.nome) || linha.nome,
      estruturaId: painel.id,
      estruturaNome: painel.nome,
      uf: painel.uf,
      areaConstruida: painel.areaConstruida,
    });
  }

  async function carregarProjeto(projetoId, estruturaIdEscolhida) {
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

      // `estruturaIdEscolhida` pode vir do firedata.json (vínculo salvo de
      // uma sessão anterior) — se a estrutura foi removida/recriada no
      // site nesse meio tempo, o id salvo não bate mais com nenhuma das
      // atuais. Sem essa checagem, `alvoId` virava esse id inválido e o
      // Dashboard tentava renderizar com `estrutura: null`, travando a
      // tela sem nenhum erro visível.
      const escolhidaValida =
        estruturaIdEscolhida && estruturas.some((e) => e.id === estruturaIdEscolhida) ? estruturaIdEscolhida : null;
      const alvoId = escolhidaValida || (estruturas.length === 1 ? estruturas[0].id : null);
      if (!alvoId) {
        // Mais de uma estrutura e nenhuma escolhida (ou a vinculada não
        // existe mais) — mostra a tela de seleção em vez de já cravar um
        // vínculo inválido.
        setEstado({ carregando: false, erro: null, linha, estruturaId: null });
        return;
      }

      persistirVinculo(linha, alvoId);
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

  // Sincroniza com o vínculo salvo no documento Revit ativo — dispara ao
  // entrar na aba (vinculo já vem preenchido de uma sessão anterior) e
  // depois de desconectar (projetoId vira null, reseta o estado local).
  useEffect(() => {
    if (!vinculo || vinculo.docSalvo === false) return;

    if (!vinculo.projetoId) {
      if (estado.linha) setEstado(ESTADO_INICIAL);
      return;
    }

    const jaCarregado =
      estado.linha?.id === vinculo.projetoId && (!vinculo.estruturaId || estado.estruturaId === vinculo.estruturaId);
    if (jaCarregado || estado.carregando) return;

    carregarProjeto(vinculo.projetoId, vinculo.estruturaId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vinculo]);

  // Status dos dimensionamentos locais — só faz sentido pedir depois que
  // uma estrutura está de fato carregada na tela.
  useEffect(() => {
    if (estado.estruturaId) {
      postToHost(BridgeMessageTypes.GET_DIMENSIONAMENTOS_STATUS, {});
    }
  }, [estado.estruturaId]);

  if (!vinculo) {
    return <p className="vazio">Carregando...</p>;
  }

  if (vinculo.docSalvo === false) {
    return (
      <div className="dashboard-tela">
        <p className="vazio">Salve o projeto Revit (.rvt) antes de conectar um projeto.</p>
      </div>
    );
  }

  if (estado.carregando && !estado.linha) {
    return <p className="vazio">Carregando projeto...</p>;
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
        onSelecionar={(estrutura) => carregarProjeto(estado.linha.id, estrutura.id)}
      />
    );
  }

  // A estrutura vinculada não pode mais ser trocada por aqui depois de
  // escolhida — só desconectando o projeto inteiro (botão da sidebar) e
  // conectando de novo. Por isso nem a lista de estruturas é passada pro
  // DashboardEstrutura: sem ela, não tem como montar um seletor.
  return (
    <DashboardEstrutura
      projeto={estado.linha}
      estrutura={dashboardEstrutura(estado.linha, estado.estruturaId)}
      dimensionamentos={dimensionamentos}
      adicionarToast={adicionarToast}
      modo={modo}
      onAbrirSaidaEmergencia={onAbrirSaidaEmergencia}
      // A tela de Saída de Emergência edita e persiste direto no Supabase
      // (ver AcessosDescargasView.jsx) — isso atualiza `estado.linha` aqui
      // pra manter uma única fonte de verdade (a mesma linha que o resto
      // do Dashboard já lê), sem precisar buscar o projeto de novo.
      onAtualizarProjeto={(novaLinha) => setEstado((s) => ({ ...s, linha: novaLinha }))}
    />
  );
}
