import { useEffect, useState } from "react";
import { listarProjetosDoUsuario } from "../../lib/projectData";
import { formatarArea, formatarEditadoHa } from "../../lib/format";
import Icon from "../Icon";
import searchIconSvg from "../../assets/icons/search-icon.svg?raw";
import linkIconSvg from "../../assets/icons/link-icon-placeholder.svg?raw";

// Debounce curto pra não disparar uma consulta a cada tecla digitada.
const DEBOUNCE_BUSCA_MS = 300;

export default function ConectarProjeto({ onSelecionar }) {
  const [busca, setBusca] = useState("");
  const [projetos, setProjetos] = useState(null); // null = ainda carregando
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let cancelado = false;
    setErro(null);
    const timer = setTimeout(
      () => {
        listarProjetosDoUsuario(busca)
          .then((lista) => {
            if (!cancelado) setProjetos(lista);
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

      <div className="search-bar">
        <Icon svg={searchIconSvg} className="icone" />
        <input
          type="text"
          placeholder="Pesquise pelo nome ou ID do projeto"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
      </div>

      {erro && <p className="vazio">Não foi possível buscar os projetos: {erro}</p>}
      {!erro && projetos === null && <p className="vazio">Buscando projetos...</p>}
      {!erro && projetos && projetos.length === 0 && (
        <p className="vazio">Nenhum projeto encontrado{busca ? " com esse filtro" : ""}.</p>
      )}

      {!erro && projetos && projetos.length > 0 && (
        <div className="grade-projetos">
          {projetos.map((projeto) => (
            <button
              key={projeto.id}
              type="button"
              className="cartao-projeto"
              onClick={() => onSelecionar(projeto)}
            >
              <h3 className="cartao-projeto-nome">{projeto.nome}</h3>
              <div className="cartao-projeto-grade">
                <span>
                  <span className="rotulo">UF</span> <strong>{projeto.uf || "—"}</strong>
                </span>
                <span>
                  <span className="rotulo">Ocupação:</span> <strong>{projeto.ocupacao_principal || "—"}</strong>
                </span>
                <span>
                  <span className="rotulo">Área Construída:</span> <strong>{formatarArea(projeto.area_construida)}</strong>
                </span>
                <span>
                  <span className="rotulo">Pavimentos:</span> <strong>{projeto.pavimentos_label || "—"}</strong>
                </span>
              </div>
              {projeto.updated_at && (
                <p className="cartao-projeto-rodape">{formatarEditadoHa(projeto.updated_at)}</p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
