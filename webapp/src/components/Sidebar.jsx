import Icon from "./Icon";
import logoSvg from "../assets/icons/fireutils-logo.svg?raw";
import libraryIconSvg from "../assets/icons/library-icon.svg?raw";
import dashboardIconSvg from "../assets/icons/dashboard-icon.svg?raw";
import pastaIconSvg from "../assets/icons/pasta-icon.svg?raw";
import perfilIconSvg from "../assets/icons/perfil-icon.svg?raw";
import configuracoesIconSvg from "../assets/icons/config-icon.svg?raw";

// Só a Biblioteca de Famílias existe de verdade por enquanto — as outras
// abas são placeholders desabilitados (novas abas futuras, ainda sem
// funcionalidade definida). Trocar `disabled: false` quando alguma delas
// virar uma aba de verdade.
const ITENS_NAV = [
  { id: "biblioteca", label: "Biblioteca de Famílias", svg: libraryIconSvg, disabled: false },
  { id: "dashboard", label: "Dashboard (em breve)", svg: dashboardIconSvg, disabled: true },
  { id: "projetos", label: "Projetos (em breve)", svg: pastaIconSvg, disabled: true },
];

export default function Sidebar({ abaAtual }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <Icon svg={logoSvg} title="Fire Utils" />
      </div>

      <div className="sidebar-nav">
        {ITENS_NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`sidebar-item ${item.id === abaAtual ? "ativa" : ""}`}
            disabled={item.disabled}
            title={item.label}
          >
            <Icon svg={item.svg} title={item.label} />
          </button>
        ))}
      </div>

      <div className="sidebar-rodape">
        <button type="button" className="sidebar-item" disabled title="Configurações (em breve)">
          <Icon svg={configuracoesIconSvg} title="Configurações" />
        </button>
        <button type="button" className="sidebar-item sidebar-item-avatar" disabled title="Perfil (em breve)">
          <Icon svg={perfilIconSvg} title="Perfil" />
        </button>
      </div>
    </nav>
  );
}
