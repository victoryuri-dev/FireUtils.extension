import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { supabase } from "../lib/supabaseClient";
import logoSvg from "../assets/icons/fireutils-logo.svg?raw";
import libraryIconSvg from "../assets/icons/library-icon.svg?raw";
import dashboardIconSvg from "../assets/icons/dashboard-icon.svg?raw";
import hydrantIconSvg from "../assets/icons/hydrant-icon.svg?raw";
import exitIconSvg from "../assets/icons/exit-icon.svg?raw";
import perfilIconSvg from "../assets/icons/perfil-icon.svg?raw";
import configuracoesIconSvg from "../assets/icons/config-icon.svg?raw";
import unlinkIconSvg from "../assets/icons/unlinked-icon.svg?raw";

// Hidrantes/Saídas ainda não têm aba própria na dockpane — aparecem
// desabilitadas, preparando o espaço pra quando (se) migrarem pra cá.
const ITENS_NAV = [
  { id: "biblioteca", label: "Biblioteca de Famílias", svg: libraryIconSvg },
  { id: "dashboard", label: "Dashboard", svg: dashboardIconSvg },
  { id: "hidrantes", label: "Hidrantes (em breve)", svg: hydrantIconSvg, disabled: true },
  { id: "saidas", label: "Saídas de Emergência (em breve)", svg: exitIconSvg, disabled: true },
];

export default function Sidebar({ abaAtual, onSelecionarAba, projetoVinculado, onDesconectar, email }) {
  const [menuAberto, setMenuAberto] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuAberto) return;
    function aoClicarFora(evento) {
      if (menuRef.current && !menuRef.current.contains(evento.target)) setMenuAberto(false);
    }
    document.addEventListener("mousedown", aoClicarFora);
    return () => document.removeEventListener("mousedown", aoClicarFora);
  }, [menuAberto]);

  async function sair() {
    setMenuAberto(false);
    await supabase?.auth.signOut();
  }

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
            onClick={() => onSelecionarAba?.(item.id)}
            title={item.label}
          >
            <Icon svg={item.svg} title={item.label} />
          </button>
        ))}
      </div>

      <div className="sidebar-rodape">
        <button type="button" className="sidebar-item sidebar-item-neutro" disabled title="Configurações (em breve)">
          <Icon svg={configuracoesIconSvg} title="Configurações" />
        </button>
        <button
          type="button"
          className="sidebar-item sidebar-item-neutro"
          disabled={!projetoVinculado}
          onClick={onDesconectar}
          title={projetoVinculado ? "Desconectar projeto" : "Nenhum projeto conectado"}
        >
          <Icon svg={unlinkIconSvg} title="Desconectar projeto" />
        </button>
        <div className="sidebar-avatar-wrap" ref={menuRef}>
          <button
            type="button"
            className="sidebar-item sidebar-item-avatar"
            onClick={() => setMenuAberto((v) => !v)}
            title="Perfil"
          >
            <Icon svg={perfilIconSvg} title="Perfil" />
          </button>
          {menuAberto && (
            <div className="avatar-popover">
              <p className="avatar-popover-email">{email}</p>
              <button type="button" className="avatar-popover-sair" onClick={sair}>
                <Icon svg={exitIconSvg} />
                Sair
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
