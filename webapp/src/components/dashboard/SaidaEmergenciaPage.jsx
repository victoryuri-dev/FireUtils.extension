import { useEffect, useState } from "react";
import Icon from "../Icon";
import { pavimentosCompletos, sistemasAtivos } from "../../lib/projetoDados";
import { getSeNorma } from "../../lib/normasCentral";
import { calcPopPav, contarSaidasPavimento, getDistanciaPavimento } from "../../data/se_calc";
import { OCUPACOES } from "../../data/ocupacoesMA";
import AcessosDescargasView, { StatCol } from "./AcessosDescargasView";
import exitIconSvg from "../../assets/icons/exit-icon.svg?raw";

/**
 * SaidaEmergenciaPage.jsx — página própria de Saída de Emergência dentro da
 * dockpane (mesmo destino do atalho da sidebar e do cartão "Saída de
 * Emergência" no Dashboard — ver Sidebar.jsx/App.jsx/DashboardEstrutura.jsx).
 *
 * Ao contrário do site (onde AcessosDescargasView é um popup — ver
 * ETOS.FireUtils/src/pages/medidas/SaidaEmergenciaPage.jsx), aqui a árvore
 * de um pavimento troca o CONTEÚDO desta página (clicar num pavimento não
 * abre popup, navega pra tela de dimensionamento; um botão "voltar" com
 * seta volta pra lista) — só o formulário de Ambiente continua sendo um
 * popup de verdade (ver editAmb dentro de AcessosDescargasView.jsx). O
 * título "Saídas de Emergência" no topo fica fixo nos dois passos.
 */
export default function SaidaEmergenciaPage({ projeto, estruturaId, onProjetoAtualizado, adicionarToast }) {
  const uf = (projeto.dados && projeto.dados.uf) || "MA";
  const [seNorma, setSeNorma] = useState(null);
  const [erro, setErro] = useState(null);
  const [viewPavId, setViewPavId] = useState(null);

  useEffect(() => {
    let cancelado = false;
    getSeNorma(uf)
      .then((dados) => {
        if (!cancelado) setSeNorma(dados);
      })
      .catch((ex) => {
        if (!cancelado) setErro(ex.message);
      });
    return () => {
      cancelado = true;
    };
  }, [uf]);

  const pavimentos = pavimentosCompletos(projeto, estruturaId);
  const sistemas = sistemasAtivos(projeto, estruturaId);

  const dadosPav = seNorma
    ? pavimentos.map((p) => {
        const pop = calcPopPav(p, seNorma.TAXA_POPULACIONAL);
        const nSaidas = Math.max(1, contarSaidasPavimento(p.acessos || []));
        const dist = getDistanciaPavimento(p, nSaidas, sistemas.sprinklers, sistemas.deteccao, seNorma.DISTANCIAS_MAXIMAS);
        const semAcessoCount = (p.ambientes || []).filter((a) => !a.acessoId).length;
        return { pav: p, pop, nSaidas, dist, semAcessoCount };
      })
    : [];

  // Pavimento de maior população da estrutura — só marcado quando há mais
  // de um pavimento e população de fato (evita destacar tudo com 0).
  const maiorPop = dadosPav.length > 1 ? Math.max(...dadosPav.map((d) => d.pop)) : -1;

  const viewPav = viewPavId ? pavimentos.find((p) => p.id === viewPavId) : null;

  return (
    <div className="se-pagina">
      <div className="se-pagina-header">
        <span className="se-pagina-icone">
          <Icon svg={exitIconSvg} />
        </span>
        <h1>Saídas de Emergência</h1>
      </div>

      {viewPav && seNorma ? (
        <AcessosDescargasView
          projeto={projeto}
          pav={viewPav}
          seNorma={seNorma}
          // OCUPACOES (grupo/divisão) é só do estado MA por enquanto — ver data/ocupacoesMA.js.
          ocupacoes={OCUPACOES}
          onVoltar={() => setViewPavId(null)}
          onProjetoAtualizado={onProjetoAtualizado}
          adicionarToast={adicionarToast}
        />
      ) : (
        <>
          <p className="dashboard-subtitulo">Pavimentos</p>

          {erro ? (
            <p className="vazio">{erro}</p>
          ) : !seNorma ? (
            <p className="vazio">Carregando dados normativos...</p>
          ) : pavimentos.length === 0 ? (
            <p className="vazio">Nenhum pavimento cadastrado no site para esta estrutura.</p>
          ) : (
            <div className="se-pavimentos-lista">
              {dadosPav.map(({ pav, pop, nSaidas, dist, semAcessoCount }) => (
                <div
                  key={pav.id}
                  className="se-card se-card-header se-card-clicavel"
                  onClick={() => setViewPavId(pav.id)}
                >
                  <div className="se-card-header-esq">
                    <div>
                      <span className="se-acesso-nome">{pav.label}</span>
                      {pav.pisoDescarga && <span className="se-tag-descarga">DESCARGA</span>}
                      {pop === maiorPop && <span className="se-tag-populoso">MAIS POPULOSO</span>}
                      {semAcessoCount > 0 && <div className="se-aviso-pequeno">{semAcessoCount} sem acesso</div>}
                    </div>
                  </div>
                  <div className="se-card-header-dir">
                    <StatCol label="População" value={pop} big />
                    <StatCol label={pav.pisoDescarga ? "Saídas" : "Escadas/Rampas"} value={nSaidas} big />
                    <StatCol label="Dist. máxima" value={dist !== null ? `${dist} m` : "Consultar NT"} big={dist !== null} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
