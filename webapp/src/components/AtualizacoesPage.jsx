import Icon from "./Icon";
import { emAndamento, textoDoEstado } from "../lib/atualizacaoEstado";
import { notasDaAtualizacao } from "../lib/patchNotes";
import { PATCH_NOTES } from "../data/patchNotes";
import downloadIconSvg from "../assets/icons/download-icon.svg?raw";

const ROTULO_TIPO = { novo: "Novo", melhoria: "Melhoria", correcao: "Correção" };

function formatarData(texto) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(texto || "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}

/**
 * Página "Atualizações": o que muda na versão nova (notas de atualização), o
 * andamento e o botão para atualizar. O botão abre a confirmação "salve o
 * projeto" (App.jsx → ConfirmarAtualizacao).
 *
 * @param instalada  versão do código instalado (texto, "dev" ou null)
 * @param atualizacao  { versao, tipo } da versão disponível, ou null
 * @param estado  andamento (lib/atualizacaoEstado.js)
 */
export default function AtualizacoesPage({ instalada, atualizacao, estado, onAtualizar }) {
  const notas = atualizacao ? notasDaAtualizacao(PATCH_NOTES, instalada, atualizacao.versao) : [];
  const fase = estado?.fase;
  const ocupado = emAndamento(estado);
  const concluido = ["agendada", "manual", "aplicada"].includes(fase);

  return (
    <div className="se-pagina atualizacoes-pagina">
      <div className="se-pagina-header">
        <span className="se-pagina-icone">
          <Icon svg={downloadIconSvg} />
        </span>
        <h1>Atualizações</h1>
      </div>

      {!atualizacao ? (
        <p className="vazio">Você está com a versão mais recente do Fire Utils{instalada ? ` (v${instalada})` : ""}.</p>
      ) : (
        <>
          <section className="atualizacoes-resumo">
            <div className="atualizacoes-versoes">
              <div>
                <span className="atualizacoes-rotulo">Instalada</span>
                <strong>{instalada && instalada !== "dev" ? `v${instalada}` : "—"}</strong>
              </div>
              <span className="atualizacoes-seta" aria-hidden="true">→</span>
              <div>
                <span className="atualizacoes-rotulo">Disponível</span>
                <strong className="atualizacoes-nova">v{atualizacao.versao}</strong>
              </div>
            </div>

            <div className="atualizacoes-acao">
              {fase && <p className={`atualizacoes-estado ${fase === "erro" ? "erro" : ""}`}>{textoDoEstado(estado)}</p>}
              {!ocupado && !concluido && (
                <button type="button" className="se-botao se-botao-accent" onClick={onAtualizar}>
                  <Icon svg={downloadIconSvg} />
                  {fase === "erro" ? "Tentar de novo" : "Atualizar"}
                </button>
              )}
            </div>
          </section>

          <p className="dashboard-subtitulo se-secao-titulo-pagina">O que há de novo</p>
          {notas.length === 0 ? (
            <p className="vazio">Esta versão ainda não tem notas de atualização.</p>
          ) : (
            <div className="atualizacoes-lista">
              {notas.map((nota) => (
                <article key={nota.versao} className="atualizacoes-nota">
                  <header>
                    <h2>v{nota.versao}</h2>
                    {nota.data && <span className="atualizacoes-data">{formatarData(nota.data)}</span>}
                  </header>
                  {nota.titulo && <p className="atualizacoes-titulo-nota">{nota.titulo}</p>}
                  <ul>
                    {nota.itens.map((item, i) => (
                      <li key={i}>
                        <span className={`atualizacoes-tag atualizacoes-tag-${item.tipo}`}>{ROTULO_TIPO[item.tipo] || "Novo"}</span>
                        <span>{item.texto}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
