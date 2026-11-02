import Icon from "./Icon";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";
import xIconSvg from "../assets/icons/x-icon.svg?raw";

// Aviso usa um "!" em texto dentro do círculo; sucesso e erro, o ícone.
const ICONE_POR_TIPO = {
  sucesso: checkIconSvg,
  erro: xIconSvg,
};

export default function ToastStack({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;

  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tipo}`}>
          <div className="toast-icone">
            {ICONE_POR_TIPO[toast.tipo] ? <Icon svg={ICONE_POR_TIPO[toast.tipo]} /> : "!"}
          </div>
          <div className="toast-corpo">
            {toast.titulo && <p className="toast-titulo">{toast.titulo}</p>}
            {toast.mensagem && <p className="toast-mensagem">{toast.mensagem}</p>}
          </div>
          <button
            type="button"
            className="toast-fechar"
            onClick={() => onDismiss(toast.id)}
            aria-label="Fechar notificação"
          >
            <Icon svg={xIconSvg} />
          </button>
        </div>
      ))}
    </div>
  );
}
