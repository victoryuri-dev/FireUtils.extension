import { useEffect, useState } from "react";
import { listarProjetosDoUsuario } from "../../lib/projectData";
import { resumoProjeto } from "../../lib/projetoDados";
import { urlNovoProjeto } from "../../lib/site";
import Icon from "../Icon";
import ProjetoCard from "./ProjetoCard";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";
import linkIconSvg from "../../assets/icons/link-icon.svg?raw";

// Debounce curto pra não disparar uma consulta a cada tecla digitada.
const DEBOUNCE_BUSCA_MS = 300;

export default function ConectarProjeto({ onSelecionar }) {
  const [busca, setBusca] = useState("");
  const [projetos, setProjetos] = useState(null); // null = ainda carregando
  const [erro, setErro] = useState(null);
  const linkNovoProjeto = urlNovoProjeto();

  useEffect(() => {
    let cancelado = false;
    setErro(null);
    const timer = setTimeout(
      () => {
        listarProjetosDoUsuario(busca)
          .then((lista) => {
            if (!cancelado) setProjetos(lista.map(resumoProjeto));
          })
          .catch((ex) => {
            console.error("[ConectarProjeto] Falha ao listar projetos:", ex);
            if (!cancelado) setErro(ex.message);
          });
      },
      busca ? DEBOUNCE_BUSCA_MS : 0
    );
    return () => {
      cancelado = true;
      clearTimeout(timer);
    };
  }, [busca]);

  return (
    <div className="dashboard-tela">
      <div className="dashboard-cabecalho-secao">
        <Icon svg={linkIconSvg} />
        <h2>Conectar um projeto</h2>
      </div>

      <div className="busca-linha">
        <div className="search-bar">
          <Icon svg={searchIconSvg} className="icone" />
          <input
            type="text"
            placeholder="Pesquise pelo nome ou ID do projeto"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        {linkNovoProjeto && (
          <a href={linkNovoProjeto} target="_blank" rel="noreferrer" className="botao accent botao-criar-projeto">
            + Criar novo projeto
          </a>
        )}
      </div>

      {erro && <p className="vazio">Não foi possível buscar os projetos: {erro}</p>}
      {!erro && projetos === null && <p className="vazio">Buscando projetos...</p>}
      {!erro && projetos && projetos.length === 0 && (
        <p className="vazio">Nenhum projeto encontrado{busca ? " com esse filtro" : ""}.</p>
      )}

      {!erro && projetos && projetos.length > 0 && (
        <div className="grade-projetos">
          {projetos.map((projeto) => (
            <ProjetoCard key={projeto.id} projeto={projeto} onClick={() => onSelecionar(projeto)} />
          ))}
        </div>
      )}
    </div>
  );
}
