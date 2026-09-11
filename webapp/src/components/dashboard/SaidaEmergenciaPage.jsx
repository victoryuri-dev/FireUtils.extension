import { useEffect, useState } from "react";
import Icon from "../Icon";
import { pavimentosCompletos, sistemasAtivos } from "../../lib/projetoDados";
import { getSeNorma } from "../../lib/normasCentral";
import { calcPopPav, contarSaidasPavimento, getDistanciaPavimento } from "../../data/se_calc";
import { OCUPACOES } from "../../data/ocupacoesMA";
import { supabase } from "../../lib/supabaseClient";
import { aplicarAcaoSaida, idAmbienteSE } from "../../lib/seReducer";
import { salvarComRetry } from "../../lib/projectData";
import { useProjetoChannel } from "../../lib/useProjetoChannel";
import AcessosDescargasView, { StatCol } from "./AcessosDescargasView";
import exitIconSvg from "../../assets/icons/exit-icon.svg?raw";

// ── Importação "Buscar do Revit" ────────────────────────────────────────
// Casa o pavimento pelo NOME que o plugin manda (ver Fire Utils.tab/lib/
// saidas/calc.py -> montar_payload_ambientes) contra os pavimentos já
// cadastrados nesta estrutura — mesma lógica de ETOS.FireUtils/src/pages/
// medidas/SaidaEmergenciaPage.jsx (resolverPavimentoSite), só que aqui já
// chega restrito a uma única estrutura (pavimentosCompletos).
function norm(s) {
  return (s || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function resolverPavimentoSite(nomeImportado, pavimentos) {
  const porLabel = pavimentos.find((p) => norm(p.label) === norm(nomeImportado));
  if (porLabel) return porLabel;
  const m = norm(nomeImportado).match(/^(?:n[ií]vel|piso|level)\s*(\d+)$/);
  if (m) {
    const porNivel = pavimentos.find((p) => p.id.endsWith(`-P${parseInt(m[1], 10)}`));
    if (porNivel) return porNivel;
  }
  return pavimentos.find((p) => p.pisoDescarga) || null;
}

// Resolve cada pavimento do payload contra o cadastro real e devolve só as
// atualizações (pavimentoId -> ambientes já com id) — quem chama decide
// como aplicar (mesclar via IMPORT_AMBIENTES_SE, não substituir a lista
// inteira de pavimentos).
//
// Ambiente já existente no pavimento (casado pelo NOME, normalizado) é
// ATUALIZADO no lugar — mantém `id` e `acessoId`, só troca os dados que
// vêm do Revit (divisão/área/população) — em vez de recriado do zero, o
// que soltava (órfão) qualquer ambiente que já estivesse dentro de um
// Acesso/Saída a cada nova importação. `assentos` não vem do Revit (ver
// montar_payload_ambientes em Fire Utils.tab/lib/saidas/calc.py):
// preserva o valor já cadastrado em vez de zerar. `origem: "revit"` marca
// todo ambiente que passa por aqui — distingue do `origem: "manual"` de
// quem nasce pelo botão "Adicionar Ambiente" (ver AcessosDescargasView.jsx).
function resolverImportacaoSaidas(payloadSE, pavimentos) {
  if (!payloadSE?.pavimentos) throw new Error('Chave "pavimentos" não encontrada nos dados.');

  const erros = [];
  const atualizacoes = [];

  payloadSE.pavimentos.forEach((p, pi) => {
    const nomeImportado = p.nome || `Pavimento ${pi + 1}`;
    const pavSite = resolverPavimentoSite(nomeImportado, pavimentos);
    if (!pavSite) {
      erros.push(`"${nomeImportado}": nenhum pavimento correspondente encontrado no projeto.`);
      return;
    }
    const existentesPorNome = new Map((pavSite.ambientes || []).map((a) => [norm(a.nome), a]));
    atualizacoes.push({
      pavimentoId: pavSite.id,
      ambientes: (p.ambientes || []).map((a, ai) => {
        const nome = a.nome || `Ambiente ${ai + 1}`;
        const existente = existentesPorNome.get(norm(nome));
        return {
          id: existente?.id ?? idAmbienteSE(),
          acessoId: existente?.acessoId ?? null,
          nome,
          divisao: a.divisao || "",
          area: a.area ?? 0,
          popTipo: a.popTipo || "area",
          assentos: a.assentos ?? existente?.assentos ?? 0,
          popManual: a.popManual ?? 0,
          origem: "revit",
        };
      }),
    });
  });

  return { atualizacoes, erros, timestamp: payloadSE._timestamp || null };
}

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
  const [buscando, setBuscando] = useState(false);

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

  // Canal Realtime do projeto — recebe ao vivo as ações de Saída de
  // Emergência de outras sessões (o site, ou outra instância da dockpane)
  // e as aplica localmente (nunca salva de novo: quem mandou já
  // persistiu). `enviarAcao` é repassado pro despachar() de
  // AcessosDescargasView.jsx e usado aqui mesmo no handleBuscarRevit, pra
  // avisar as outras sessões depois de CADA ação salva com sucesso.
  const enviarAcao = useProjetoChannel(projeto.id, (action) => {
    const novosDados = aplicarAcaoSaida(projeto.dados, action);
    onProjetoAtualizado({ ...projeto, dados: novosDados });
  });

  // Lê a última sincronização do plugin (revit_syncs_latest, gravada pela
  // Edge Function revit-sync — ver Fire Utils.tab/lib/sync.py) e mescla os
  // ambientes nos pavimentos já cadastrados desta estrutura, casando pelo
  // NOME do pavimento. Mesmo fluxo do botão "Buscar do Revit" do site
  // (ETOS.FireUtils/src/pages/medidas/SaidaEmergenciaPage.jsx).
  async function handleBuscarRevit() {
    setBuscando(true);
    try {
      const { data, error } = await supabase
        .from("revit_syncs_latest")
        .select("payload")
        .eq("projeto_id", projeto.id)
        .eq("estrutura_id", estruturaId)
        .eq("medida", "saidas_emergencia")
        .maybeSingle();

      if (error) throw error;
      if (!data) {
        adicionarToast?.({
          tipo: "erro",
          titulo: "Nada sincronizado ainda",
          mensagem: "Nenhum dado de saídas de emergência sincronizado do Revit para esta estrutura.",
          duracaoMs: 7000,
        });
        return;
      }

      const { atualizacoes, erros } = resolverImportacaoSaidas(data.payload, pavimentos);
      if (atualizacoes.length > 0) {
        const acao = { type: "IMPORT_AMBIENTES_SE", atualizacoes };
        const { dados: novosDados, version: novaVersao } = await salvarComRetry(projeto.id, projeto, (dados) =>
          aplicarAcaoSaida(dados, acao)
        );
        onProjetoAtualizado({ ...projeto, dados: novosDados, version: novaVersao });
        enviarAcao(acao);
      }

      if (erros.length > 0) {
        adicionarToast?.({ tipo: "erro", titulo: "Alguns pavimentos não foram importados", mensagem: erros.join(" "), duracaoMs: 9000 });
      } else {
        adicionarToast?.({ tipo: "sucesso", titulo: "Ambientes importados do Revit", duracaoMs: 4000 });
      }
    } catch (ex) {
      adicionarToast?.({ tipo: "erro", titulo: "Não foi possível buscar do Revit", mensagem: ex.message, duracaoMs: 9000 });
    } finally {
      setBuscando(false);
    }
  }

  return (
    <div className="se-pagina">
      <div className="se-pagina-header">
        <span className="se-pagina-icone">
          <Icon svg={exitIconSvg} />
        </span>
        <h1>Saídas de Emergência</h1>
        <button type="button" className="se-botao se-pagina-header-botao" onClick={handleBuscarRevit} disabled={buscando}>
          {buscando ? "Recarregando…" : "Recarregar"}
        </button>
      </div>

      {viewPav && seNorma ? (
        <AcessosDescargasView
          projeto={projeto}
          enviarAcao={enviarAcao}
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
