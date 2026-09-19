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

// Sistema de Hidrantes e Saídas de Emergência são páginas próprias (ver
// App.jsx/SistemaHidrantesPage.jsx/SaidaEmergenciaPage.jsx) — mesmo atalho
// que o respectivo cartão de dimensionamento dentro do Dashboard.
const ITENS_NAV = [
  { id: "biblioteca", label: "Biblioteca de Famílias", svg: libraryIconSvg },
  { id: "dashboard", label: "Dashboard", svg: dashboardIconSvg },
  { id: "hidrantes", label: "Sistema de Hidrantes", svg: hydrantIconSvg },
  { id: "saidas", label: "Saídas de Emergência", svg: exitIconSvg },
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
        {projetoVinculado && (
          <button
            type="button"
            className="sidebar-item"
            onClick={onDesconectar}
            title="Vincular projeto"
          >
            <Icon svg={unlinkIconSvg} title="Vincular projeto" />
          </button>
        )}
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
