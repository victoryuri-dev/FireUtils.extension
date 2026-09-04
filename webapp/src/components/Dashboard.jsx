import { useEffect, useState } from "react";
import { postToHost, BridgeMessageTypes } from "../lib/bridge";
import { buscarProjeto, buscarEstruturasDoProjeto, buscarDashboardEstrutura } from "../lib/projectData";
import ConectarProjeto from "./dashboard/ConectarProjeto";
import SelecionarEstrutura from "./dashboard/SelecionarEstrutura";
import DashboardEstrutura from "./dashboard/DashboardEstrutura";

const ESTADO_INICIAL = { carregando: false, erro: null, projeto: null, estruturas: null, estruturaAtual: null };

/**
 * Orquestra o fluxo: Conectar um projeto -> (Selecione uma estrutura, se
 * houver mais de uma) -> Dashboard do projeto/estrutura. `vinculo` vem do
 * firedata.json do documento Revit ativo (ver lib/bridge.js e
 * project_link_bridge.py do lado Python) — a busca de projetos/estruturas
 * em si é direto no Supabase (lib/projectData.js), com a sessão do
 * usuário logado.
 */
export default function Dashboard({ vinculo, dimensionamentos, adicionarToast }) {
  const [estado, setEstado] = useState(ESTADO_INICIAL);

  async function carregarProjeto(projetoId, estruturaIdEscolhida) {
    setEstado((s) => ({ ...s, carregando: true, erro: null }));
    try {
      const [projeto, estruturas] = await Promise.all([
        estado.projeto && estado.projeto.id === projetoId ? Promise.resolve(estado.projeto) : buscarProjeto(projetoId),
        buscarEstruturasDoProjeto(projetoId),
      ]);

      if (estruturas.length === 0) {
        setEstado({
          carregando: false,
          erro: "Este projeto ainda não tem nenhuma estrutura cadastrada no site.",
          projeto,
          estruturas,
          estruturaAtual: null,
        });
        return;
      }

      const alvoId = estruturaIdEscolhida || (estruturas.length === 1 ? estruturas[0].id : null);
      if (!alvoId) {
        // Mais de uma estrutura e nenhuma escolhida ainda — mostra a tela
        // de seleção em vez de já cravar um vínculo.
        setEstado({ carregando: false, erro: null, projeto, estruturas, estruturaAtual: null });
        return;
      }

      const dadosEstrutura = await buscarDashboardEstrutura(alvoId);
      const resumoEstrutura = estruturas.find((e) => e.id === alvoId);

      postToHost(BridgeMessageTypes.SET_PROJECT_LINK, {
        projetoId: projeto.id,
        projetoNome: projeto.nome,
        estruturaId: dadosEstrutura.id,
        estruturaNome: resumoEstrutura ? resumoEstrutura.nome : dadosEstrutura.nome,
        uf: dadosEstrutura.uf,
        ocupacaoPrincipal: dadosEstrutura.ocupacao_principal,
        areaConstruida: dadosEstrutura.area_construida,
      });

      setEstado({ carregando: false, erro: null, projeto, estruturas, estruturaAtual: dadosEstrutura });
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
      if (estado.projeto) setEstado(ESTADO_INICIAL);
      return;
    }

    const jaCarregado =
      estado.projeto?.id === vinculo.projetoId &&
      (!vinculo.estruturaId || estado.estruturaAtual?.id === vinculo.estruturaId);
    if (jaCarregado || estado.carregando) return;

    carregarProjeto(vinculo.projetoId, vinculo.estruturaId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vinculo]);

  // Status dos dimensionamentos locais — só faz sentido pedir depois que
  // uma estrutura está de fato carregada na tela.
  useEffect(() => {
    if (estado.estruturaAtual) {
      postToHost(BridgeMessageTypes.GET_DIMENSIONAMENTOS_STATUS, {});
    }
  }, [estado.estruturaAtual?.id]);

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

  if (estado.carregando && !estado.projeto) {
    return <p className="vazio">Carregando projeto...</p>;
  }

  if (estado.erro) {
    return (
      <div className="dashboard-tela">
        <p className="vazio">{estado.erro}</p>
      </div>
    );
  }

  if (!estado.projeto) {
    return <ConectarProjeto onSelecionar={(projeto) => carregarProjeto(projeto.id, null)} />;
  }

  if (!estado.estruturaAtual) {
    return (
      <SelecionarEstrutura
        projeto={estado.projeto}
        estruturas={estado.estruturas}
        onSelecionar={(estrutura) => carregarProjeto(estado.projeto.id, estrutura.id)}
      />
    );
  }

  return (
    <DashboardEstrutura
      projeto={estado.projeto}
      estrutura={estado.estruturaAtual}
      estruturas={estado.estruturas}
      onTrocarEstrutura={(novoEstruturaId) => carregarProjeto(estado.projeto.id, novoEstruturaId)}
      dimensionamentos={dimensionamentos}
    />
  );
}
