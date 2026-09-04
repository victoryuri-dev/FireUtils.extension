import { useCallback, useRef, useState } from "react";

let proximoId = 0;

/**
 * Fila de notificações (toasts) — canto superior direito, empilhadas,
 * cada uma some sozinha depois de `duracaoMs` ou quando o usuário clica
 * em fechar. Sem lib externa: é só um array de estado + um setTimeout por
 * toast (cancelado se fechada manualmente antes de vencer).
 */
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const temporizadores = useRef(new Map());

  const removerToast = useCallback((id) => {
    setToasts((atual) => atual.filter((toast) => toast.id !== id));
    const temporizador = temporizadores.current.get(id);
    if (temporizador) {
      clearTimeout(temporizador);
      temporizadores.current.delete(id);
    }
  }, []);

  const adicionarToast = useCallback(
    ({ tipo = "aviso", titulo, mensagem, duracaoMs = 6000 }) => {
      const id = ++proximoId;
      setToasts((atual) => [...atual, { id, tipo, titulo, mensagem }]);
      if (duracaoMs) {
        temporizadores.current.set(id, setTimeout(() => removerToast(id), duracaoMs));
      }
      return id;
    },
    [removerToast]
  );

  return { toasts, adicionarToast, removerToast };
}
