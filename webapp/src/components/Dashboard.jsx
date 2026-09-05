import { useEffect, useState } from "react";
import { postToHost, BridgeMessageTypes } from "../lib/bridge";
import { buscarProjeto } from "../lib/projectData";
import { estruturasDoProjeto, dashboardEstrutura } from "../lib/projetoDados";
import ConectarProjeto from "./dashboard/ConectarProjeto";
import SelecionarEstrutura from "./dashboard/SelecionarEstrutura";
import DashboardEstrutura from "./dashboard/DashboardEstrutura";

const ESTADO_INICIAL = { carregando: false, erro: null, linha: null, estruturaId: null };

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
export default function Dashboard({ vinculo, dimensionamentos, adicionarToast }) {
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
      // Lista de códigos de ocupação dos pavimentos desta estrutura — o
      // Python escolhe o mais restritivo (tabela normativa do estado)
      // pra virar dados_projeto.ocupacao_principal; "Mista" (exibido na
      // tela) não é um código válido pra isso.
      divisoes: painel.divisoes,
    });
  }

  async function carregarProjeto(projetoId, estruturaIdEscolhida) {
    setEstado((s) => ({ ...s, carregando: true, erro: null }));
    try {
      const linha =
        estado.linha && estado.linha.id === projetoId ? estado.linha : await buscarProjeto(projetoId);
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

      const alvoId = estruturaIdEscolhida || (estruturas.length === 1 ? estruturas[0].id : null);
      if (!alvoId) {
        // Mais de uma estrutura e nenhuma escolhida ainda — mostra a tela
        // de seleção em vez de já cravar um vínculo.
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
    />
  );
}
