import Icon from "./Icon";
import logoSvg from "../assets/icons/fireutils-logo.svg?raw";
import libraryIconSvg from "../assets/icons/library-icon.svg?raw";
import dashboardIconSvg from "../assets/icons/dashboard-icon.svg?raw";
import perfilIconSvg from "../assets/icons/perfil-icon.svg?raw";
import configuracoesIconSvg from "../assets/icons/config-icon.svg?raw";
import unlinkIconSvg from "../assets/icons/unlink-icon-placeholder.svg?raw";

const ITENS_NAV = [
  { id: "biblioteca", label: "Biblioteca de Famílias", svg: libraryIconSvg },
  { id: "dashboard", label: "Dashboard", svg: dashboardIconSvg },
];

export default function Sidebar({ abaAtual, onSelecionarAba, projetoVinculado, onDesconectar }) {
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
            onClick={() => onSelecionarAba?.(item.id)}
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
        <button
          type="button"
          className="sidebar-item"
          disabled={!projetoVinculado}
          onClick={onDesconectar}
          title={projetoVinculado ? "Desconectar projeto" : "Nenhum projeto conectado"}
        >
          <Icon svg={unlinkIconSvg} title="Desconectar projeto" />
        </button>
        <button type="button" className="sidebar-item sidebar-item-avatar" disabled title="Perfil (em breve)">
          <Icon svg={perfilIconSvg} title="Perfil" />
        </button>
      </div>
    </nav>
  );
}
