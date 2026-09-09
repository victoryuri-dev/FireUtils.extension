import { useEffect, useState } from "react";
import Icon from "../Icon";
import { pavimentosCompletos, sistemasAtivos } from "../../lib/projetoDados";
import { getSeNorma } from "../../lib/normasCentral";
import { calcPopPav, contarSaidasPavimento, getDistanciaPavimento } from "../../data/se_calc";
import { OCUPACOES } from "../../data/ocupacoesMA";
import AcessosDescargasView from "./AcessosDescargasView";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";
import chevronRightIconSvg from "../../assets/icons/chevron-right-icon.svg?raw";

/**
 * SaidaEmergenciaLista.jsx — lista de pavimentos de uma estrutura, com
 * população/quantidade de saídas/distância máxima já calculados, portada
 * de ETOS.FireUtils/src/pages/medidas/SaidaEmergenciaPage.jsx (só a
 * listagem — a árvore em si é AcessosDescargasView.jsx). Sem a parte de
 * importar do Revit/arquivo .json: aqui já se está dentro do Revit, então
 * não faz sentido "importar" de volta pra ele mesmo — a edição é direta,
 * igual o site.
 */

// Badge somente-leitura (chuveiros/detecção vêm das Medidas de Segurança
// do site — ver lib/projetoDados.sistemasAtivos).
function SistemaBadge({ ativo, label }) {
  return (
    <span className={`se-sistema-badge ${ativo ? "se-sistema-badge-ativo" : ""}`}>
      <span className="se-sistema-badge-dot" />
      {label}
    </span>
  );
}

export default function SaidaEmergenciaLista({ projeto, estruturaId, onClose, onProjetoAtualizado, adicionarToast }) {
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

  const viewPav = viewPavId ? pavimentos.find((p) => p.id === viewPavId) : null;

  return (
    <>
      <div className="se-modal-overlay" onClick={onClose}>
        <div onClick={(e) => e.stopPropagation()} className="se-lista-caixa">
          <div className="se-lista-header">
            <div>
              <div className="se-lista-eyebrow">Medidas de Segurança</div>
              <h2 className="se-lista-titulo">Saídas de Emergência</h2>
            </div>
            <div className="se-lista-header-dir">
              <SistemaBadge ativo={sistemas.sprinklers} label="Chuveiros automáticos" />
              <SistemaBadge ativo={sistemas.deteccao} label="Detecção de incêndio" />
              <button className="se-icon-botao" onClick={onClose}>
                <Icon svg={xIconSvg} />
              </button>
            </div>
          </div>

          <div className="se-lista-corpo">
            {erro ? (
              <p className="vazio">{erro}</p>
            ) : !seNorma ? (
              <p className="vazio">Carregando dados normativos...</p>
            ) : pavimentos.length === 0 ? (
              <p className="vazio">Nenhum pavimento cadastrado no site para esta estrutura.</p>
            ) : (
              <div className="se-lista-tabela-wrap">
                <table className="se-lista-tabela">
                  <thead>
                    <tr>
                      <th>Pavimento</th>
                      <th className="se-th-center">Amb.</th>
                      <th className="se-th-center">Pop.</th>
                      <th className="se-th-center">Saídas</th>
                      <th className="se-th-right">Dist. máxima</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {dadosPav.map(({ pav, pop, nSaidas, dist, semAcessoCount }) => (
                      <tr key={pav.id} onClick={() => setViewPavId(pav.id)} className="se-lista-linha">
                        <td className="se-td-bold">
                          {pav.label}
                          {pav.pisoDescarga && <span className="se-tag-descarga">DESCARGA</span>}
                        </td>
                        <td className="se-td-center se-td-muted">
                          {(pav.ambientes || []).length}
                          {semAcessoCount > 0 && <div className="se-aviso-pequeno">{semAcessoCount} sem acesso</div>}
                        </td>
                        <td className="se-td-center se-td-red se-td-bold">{pop}</td>
                        <td className="se-td-center se-td-red se-td-bold">{nSaidas}</td>
                        <td className="se-td-right">
                          {dist !== null ? <span className="se-chip-verde">{dist} m</span> : <span className="se-td-muted-sm">Consultar NT</span>}
                        </td>
                        <td className="se-td-right">
                          <Icon svg={chevronRightIconSvg} className="se-chevron-linha" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {viewPav && seNorma && (
        <AcessosDescargasView
          projeto={projeto}
          pav={viewPav}
          seNorma={seNorma}
          // OCUPACOES (grupo/divisão) é só do estado MA por enquanto — ver data/ocupacoesMA.js.
          ocupacoes={OCUPACOES}
          onClose={() => setViewPavId(null)}
          onProjetoAtualizado={onProjetoAtualizado}
          adicionarToast={adicionarToast}
        />
      )}
    </>
  );
}
