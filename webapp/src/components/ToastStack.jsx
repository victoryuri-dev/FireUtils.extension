import Icon from "./Icon";
import checkIconSvg from "../assets/icons/check-icon.svg?raw";
import xIconSvg from "../assets/icons/x-icon.svg?raw";
import avisoIconSvg from "../assets/icons/pasta-icon.svg?raw";

// Mesmo ícone preto de "pasta" usado no indicador de card já carregado —
// aqui representa o mesmo significado ("já estava no projeto").
const ICONE_POR_TIPO = {
  sucesso: checkIconSvg,
  erro: xIconSvg,
  aviso: avisoIconSvg,
};

export default function ToastStack({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;

  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tipo}`}>
          <div className="toast-icone">
            <Icon svg={ICONE_POR_TIPO[toast.tipo] || avisoIconSvg} />
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
