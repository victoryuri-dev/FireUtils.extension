import { useEffect, useRef } from "react";
import { supabase } from "./supabaseClient";

/**
 * useProjetoChannel.js — canal Realtime do projeto aberto, pro mesmo
 * protocolo que o site já usa (ver ETOS.FireUtils/src/context/
 * ProjetoContext.jsx): um canal Supabase Realtime por projeto
 * (`projeto:${projetoId}`, `broadcast.self: false`) onde cada ação da
 * árvore de Saída de Emergência é transmitida em tempo real — é o que
 * permite a dockpane e o site (ou duas abas do site) editarem o mesmo
 * projeto ao mesmo tempo sem uma sessão sobrescrever a outra às cegas.
 *
 * Ao contrário do site, a dockpane não tem um reducer vivo nem um
 * autosave debounced: cada ação já é salva na hora, síncrona, via
 * lib/projectData.salvarComRetry (ver AcessosDescargasView.jsx /
 * SaidaEmergenciaPage.jsx). Por isso este hook não persiste nada
 * sozinho — só entrega `enviarAcao(action)` pra quem já salvou avisar as
 * outras sessões, e chama `aoReceberAcao(action)` quando uma ação chega
 * de outra sessão (quem já mandou a ação é responsável por tê-la salvo —
 * aqui só aplica localmente, nunca grava de novo, senão as duas sessões
 * competiriam pra persistir o mesmo conteúdo).
 *
 * Ações desta própria dockpane já nascem com todo id necessário resolvido
 * no ponto de disparo (ver idAcesso()/idAmbienteSE() nos call sites) — ao
 * contrário do reducer do site, aqui não existe geração de id nem
 * inversão de toggle dentro do `case`, então não precisa de um
 * equivalente a resolverAcaoLocal (ProjetoContext.jsx) antes de
 * transmitir: a action já é determinística por construção.
 */
export function useProjetoChannel(projetoId, aoReceberAcao) {
  const channelRef = useRef(null);
  const handlerRef = useRef(aoReceberAcao);
  handlerRef.current = aoReceberAcao;

  useEffect(() => {
    if (!projetoId || !supabase) return undefined;

    const channel = supabase.channel(`projeto:${projetoId}`, { config: { broadcast: { self: false } } });
    channel
      .on("broadcast", { event: "action" }, ({ payload }) => {
        if (payload?.action) handlerRef.current?.(payload.action);
      })
      .subscribe((status) => {
        if (status === "SUBSCRIBED") channelRef.current = channel;
      });

    return () => {
      channelRef.current = null;
      supabase.removeChannel(channel);
    };
  }, [projetoId]);

  return function enviarAcao(action) {
    channelRef.current?.send({ type: "broadcast", event: "action", payload: { action } });
  };
}
