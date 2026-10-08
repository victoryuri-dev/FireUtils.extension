import { useEffect, useState } from "react";
import ProjetoCabecalho from "./ProjetoCabecalho";
import SaidaEmergenciaPage from "./SaidaEmergenciaPage";
import SistemaHidrantesPage from "./SistemaHidrantesPage";
import CorrelacaoNiveisModal from "./CorrelacaoNiveisModal";
import Icon from "../Icon";
import { formatarArea, formatarMetros, formatarCargaIncendio } from "../../lib/format";
import { fmtNum } from "../../lib/numero";
import { dadosHidrantes, pavimentosCompletos, sistemasAtivos } from "../../lib/projetoDados";
import { getSeNorma, getExtintoresNorma } from "../../lib/normasCentral";
import { capacidadeMinimaPorRisco } from "../../lib/extintoresCapacidadeMinima";
import { contarSaidasPavimento, getDistanciaPavimento, tipoEscadaEstrutura } from "../../data/se_calc";
import { postToHost, escutarMensagensDoHost, BridgeMessageTypes } from "../../lib/bridge";
import hydrantIconSvg from "../../assets/icons/hydrant-icon.svg?raw";
import exitIconSvg from "../../assets/icons/exit-icon.svg?raw";
import stairIconSvg from "../../assets/icons/stair-icon.svg?raw";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";

// A ação de aplicar a classificação no Revit mora na página "Sistema de
// Hidrantes" (SistemaHidrantesPage.jsx, mesmo destino deste cartão) — aqui
// fica só o resumo do que está pendente no site, sem botão. Pressão/vazão
// mínima vêm do Project Information do Revit (classificação já aplicada
// lá — GET_HIDRANTES_DIMENSIONAMENTO, mesmo dado que
// SistemaHidrantesPage.jsx mostra em "Vazão mín."/"Pressão mín."), não do
// Supabase — por isso chegam null até a classificação ser aplicada no
// Revit, mesmo que Tipo/RTI (Supabase) já estejam definidos.
function CartaoClassificacaoHidrantes({ hidrantes, classificacao }) {
  if (hidrantes.tipo == null) {
    return (
      <div className="cartao-info">
        <h3>Sistema de Hidrantes</h3>
        <p className="vazio">Classificação ainda não definida no site.</p>
      </div>
    );
  }

  return (
    <div className="cartao-info">
      <h3>Sistema de Hidrantes</h3>
      <dl>
        <div>
          <dt>Tipo:</dt>
          <dd>{hidrantes.tipo}</dd>
        </div>
        <div>
          <dt>RTI:</dt>
          <dd>{hidrantes.rti != null ? `${hidrantes.rti} m³` : "—"}</dd>
        </div>
        <div>
          <dt>Vazão mínima:</dt>
          <dd>{classificacao?.q_min != null ? `${fmtNum(classificacao.q_min, 0)} L/min` : "—"}</dd>
        </div>
        <div>
          <dt>Pressão mínima:</dt>
          <dd>{classificacao?.p_min != null ? `${fmtNum(classificacao.p_min, 0)} mca` : "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

/** Classifica o risco (baixo/médio/alto) a partir da carga de incêndio e dos
 * limiares da norma de Extintores (NT 21 CBMMA) — mesmos limiares que
 * lib/projetoDados.js:rotuloRisco usa fixos (300/1200), mas lidos aqui da
 * base normativa central pra não duplicar o número em dois lugares. */
function classificarRiscoChave(cargaIncendio, limiares) {
  if (cargaIncendio == null || !limiares) return null;
  if (cargaIncendio <= limiares.baixo) return "baixo";
  if (cargaIncendio <= limiares.medio) return "medio";
  return "alto";
}

/** "X-A:X-B" — capacidade extintora mínima combinada (classes A e B) pro
 * risco atual, extintores portáteis (ver CAPACIDADE_MINIMA_POR_RISCO em
 * lib/extintoresCapacidadeMinima.js). */
function capacidadePortatilCombinada(riscoChave) {
  const a = capacidadeMinimaPorRisco(riscoChave, "A");
  const b = capacidadeMinimaPorRisco(riscoChave, "B");
  if (!a || !b) return "—";
  return `${a.capacidade}:${b.capacidade}`;
}

function CartaoExtintores({ norma, cargaIncendio }) {
  if (norma === undefined) {
    return (
      <div className="cartao-info">
        <h3>Extintores Portáteis</h3>
        <p className="vazio">Não foi possível carregar a norma de extintores.</p>
      </div>
    );
  }
  if (!norma) {
    return (
      <div className="cartao-info">
        <h3>Extintores Portáteis</h3>
        <p className="vazio">Carregando norma...</p>
      </div>
    );
  }

  const riscoChave = classificarRiscoChave(cargaIncendio, norma.LIMIARES_RISCO);
  const distanciaA = capacidadeMinimaPorRisco(riscoChave, "A");
  const distanciaB = capacidadeMinimaPorRisco(riscoChave, "B");

  return (
    <div className="cartao-info">
      <h3>Extintores Portáteis</h3>
      <dl>
        <div>
          <dt>Capacidade Extintora Mínima:</dt>
          <dd>{capacidadePortatilCombinada(riscoChave)}</dd>
        </div>
        <div>
          <dt>Caminhamento máx. (classe A):</dt>
          <dd>{distanciaA ? `${distanciaA.distanciaMaxima} m` : "—"}</dd>
        </div>
        <div>
          <dt>Caminhamento máx. (classe B):</dt>
          <dd>{distanciaB ? `${distanciaB.distanciaMaxima} m` : "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

/** Resumo de Saída de Emergência pro Dashboard — distância máxima mais
 * restritiva entre os pavimentos da estrutura (mesmo cálculo da página
 * cheia, ver SaidaEmergenciaPage.jsx) + tipo de escada exigido (Anexo C,
 * Tabela 3 — data/se_calc.js:tipoEscadaEstrutura), só quando a estrutura
 * tem mais de um pavimento. */
function CartaoSaidaEmergenciaResumo({ norma, projeto, estrutura }) {
  if (norma === undefined) {
    return (
      <div className="cartao-info">
        <h3>Saída de Emergência</h3>
        <p className="vazio">Não foi possível carregar a norma de saída de emergência.</p>
      </div>
    );
  }
  if (!norma) {
    return (
      <div className="cartao-info">
        <h3>Saída de Emergência</h3>
        <p className="vazio">Carregando norma...</p>
      </div>
    );
  }

  const pavimentos = pavimentosCompletos(projeto, estrutura.id);
  const sistemas = sistemasAtivos(projeto, estrutura.id);
  let distanciaMinima = null;
  pavimentos.forEach((pav) => {
    const nSaidas = Math.max(1, contarSaidasPavimento(pav.acessos || []));
    const dist = getDistanciaPavimento(pav, nSaidas, sistemas.sprinklers, sistemas.deteccao, norma.DISTANCIAS_MAXIMAS);
    if (typeof dist === "number") {
      distanciaMinima = distanciaMinima === null ? dist : Math.min(distanciaMinima, dist);
    }
  });

  const escada = tipoEscadaEstrutura(
    { nPavimentos: estrutura.nPavimentos, nSubsolos: estrutura.nSubsolos, alturaPisoPiso: estrutura.alturaPisoAPiso },
    estrutura.divisoes,
    norma.TIPOS_ESCADA
  );
  let escadaLabel = "N/A";
  if (escada?.status === "ok") {
    const t = norma.TIPOS_ESCADA?.tipos?.[escada.exigido];
    const simbolo = escada.exigido === "+" || escada.exigido === "-";
    escadaLabel = t ? (simbolo ? t.nome : `${escada.exigido} — ${t.nome}`) : escada.exigido;
  }

  return (
    <div className="cartao-info">
      <h3>Saída de Emergência</h3>
      <dl>
        <div>
          <dt>Distância máxima a percorrer:</dt>
          <dd>{distanciaMinima != null ? formatarMetros(distanciaMinima) : "—"}</dd>
        </div>
        <div>
          <dt>Tipo de escada:</dt>
          <dd>{escadaLabel}</dd>
        </div>
      </dl>
    </div>
  );
}

/** "4 pav." ou "4 pav. + 1 subsolo"/"+ 2 subsolos" — mesmo formato do site
 * (Step7.jsx, tabela de revisão das estruturas). */
function rotuloPavimentosEstrutura(estrutura) {
  const nPav = estrutura.nPavimentos || 1;
  const nSub = estrutura.nSubsolos || 0;
  return `${nPav} pav.${nSub ? ` + ${nSub} subsolo${nSub !== 1 ? "s" : ""}` : ""}`;
}

function CartaoDimensionamento({ titulo, iconeSvg, dimensionado, onClick, rotuloConcluido = "Dimensionado" }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} className={`cartao-dimensionamento ${onClick ? "cartao-dimensionamento-clicavel" : ""}`} onClick={onClick}>
      <span className="cartao-dimensionamento-icone">
        <Icon svg={iconeSvg} />
      </span>
      <span className="cartao-dimensionamento-titulo">{titulo}</span>
      {dimensionado === undefined ? (
        <span className="status-dimensionamento status-carregando">Verificando...</span>
      ) : dimensionado ? (
        <span className="status-dimensionamento status-ok">
          <Icon svg={checkIconSvg} />
          {rotuloConcluido}
        </span>
      ) : (
        <span className="status-dimensionamento status-pendente">Pendente</span>
      )}
    </Tag>
  );
}

export default function DashboardEstrutura({
  projeto,
  estrutura,
  dimensionamentos,
  adicionarToast,
  onAtualizarProjeto,
  modo = "dashboard",
  onAbrirSaidaEmergencia,
  onAbrirHidrantes,
}) {
  // Normas de Extintores e Saída de Emergência pros cartões-resumo do
  // Dashboard (abaixo) — busca uma vez por UF, só no modo "dashboard" (as
  // páginas cheias de cada sistema buscam a própria norma, independente
  // deste estado). Hooks ficam antes dos `return` condicionais de `modo`
  // logo abaixo (regra dos hooks: sempre chamados, nunca atrás de um if).
  const [seNorma, setSeNorma] = useState(null);
  const [extintoresNorma, setExtintoresNorma] = useState(null);
  const [mostrarCorrelacaoNiveis, setMostrarCorrelacaoNiveis] = useState(false);
  const [classificacaoHidrantes, setClassificacaoHidrantes] = useState(null);

  useEffect(() => {
    if (modo !== "dashboard" || !estrutura?.uf) return;
    setSeNorma(null);
    setExtintoresNorma(null);
    getSeNorma(estrutura.uf)
      .then(setSeNorma)
      .catch((ex) => {
        console.error("[DashboardEstrutura] Falha ao buscar norma de saída de emergência:", ex);
        setSeNorma(undefined);
      });
    getExtintoresNorma(estrutura.uf)
      .then(setExtintoresNorma)
      .catch((ex) => {
        console.error("[DashboardEstrutura] Falha ao buscar norma de extintores:", ex);
        setExtintoresNorma(undefined);
      });
  }, [modo, estrutura?.uf]);

  // Pressão/vazão mínima do cartão "Sistema de Hidrantes" vêm do Project
  // Information do Revit (classificação já aplicada lá), via a mesma
  // mensagem que SistemaHidrantesPage.jsx usa — fica null quando ainda
  // não foi aplicada (`ok: false`), sem bloquear o resto do cartão.
  useEffect(() => {
    if (modo !== "dashboard") return;
    postToHost(BridgeMessageTypes.GET_HIDRANTES_DIMENSIONAMENTO, {});
    return escutarMensagensDoHost((mensagem) => {
      if (!mensagem || mensagem.type !== BridgeMessageTypes.HIDRANTES_DIMENSIONAMENTO) return;
      const { ok, classificacao } = mensagem.payload || {};
      setClassificacaoHidrantes(ok ? classificacao : null);
    });
  }, [modo, estrutura?.id]);

  // Saída de Emergência e Sistema de Hidrantes viraram páginas próprias
  // (mesmo destino do atalho da sidebar e do respectivo cartão) — ver
  // App.jsx/Sidebar.jsx. `modo` chega até aqui (em vez de um estado local)
  // porque quem decide a aba atual é o App, não este componente.
  if (modo === "saidas") {
    return (
      <SaidaEmergenciaPage
        projeto={projeto}
        estruturaId={estrutura.id}
        onProjetoAtualizado={onAtualizarProjeto}
        adicionarToast={adicionarToast}
      />
    );
  }

  if (modo === "hidrantes") {
    return (
      <SistemaHidrantesPage
        projeto={projeto}
        estrutura={estrutura}
        onProjetoAtualizado={onAtualizarProjeto}
        adicionarToast={adicionarToast}
      />
    );
  }

  return (
    <div className="dashboard-tela">
      <ProjetoCabecalho projeto={projeto} estrutura={estrutura} />

      <div className="grade-cartoes-info">
        <div className="cartao-info">
          <h3>Edificação</h3>
          <dl>
            <div>
              <dt>UF:</dt>
              <dd>{estrutura.uf || "—"}</dd>
            </div>
            <div>
              <dt>Área construída:</dt>
              <dd>{formatarArea(estrutura.areaConstruida)}</dd>
            </div>
            <div>
              <dt>Área terreno:</dt>
              <dd>{formatarArea(estrutura.areaTerreno)}</dd>
            </div>
            <div>
              <dt>Pavimentos:</dt>
              <dd>{rotuloPavimentosEstrutura(estrutura)}</dd>
            </div>
          </dl>
        </div>

        <div className="cartao-info">
          <h3>Classificação</h3>
          <dl>
            <div>
              <dt>Ocupação:</dt>
              <dd>{estrutura.ocupacao || "—"}</dd>
            </div>
            <div>
              <dt>Risco de incêndio:</dt>
              <dd>{estrutura.risco?.label || "—"}</dd>
            </div>
            <div>
              <dt>Carga de incêndio:</dt>
              <dd>{formatarCargaIncendio(estrutura.cargaIncendio)}</dd>
            </div>
            <div>
              <dt>Altura piso a piso:</dt>
              <dd>{formatarMetros(estrutura.alturaPisoAPiso)}</dd>
            </div>
          </dl>
        </div>

        <CartaoClassificacaoHidrantes hidrantes={dadosHidrantes(projeto)} classificacao={classificacaoHidrantes} />

        <CartaoExtintores norma={extintoresNorma} cargaIncendio={estrutura.cargaIncendio} />

        <CartaoSaidaEmergenciaResumo norma={seNorma} projeto={projeto} estrutura={estrutura} />
      </div>

      <p className="dashboard-subtitulo">Dimensionamentos</p>
      <div className="grade-dimensionamentos">
        <CartaoDimensionamento
          titulo="Sistema de Hidrantes"
          iconeSvg={hydrantIconSvg}
          dimensionado={dimensionamentos?.hidrantes}
          onClick={onAbrirHidrantes}
        />
        <CartaoDimensionamento
          titulo="Saída de Emergência"
          iconeSvg={exitIconSvg}
          dimensionado={dimensionamentos?.saidaEmergencia}
          onClick={onAbrirSaidaEmergencia}
        />
        <CartaoDimensionamento
          titulo="Correlacionar Níveis"
          iconeSvg={stairIconSvg}
          dimensionado={dimensionamentos?.niveis}
          rotuloConcluido="Correlacionado"
          onClick={() => setMostrarCorrelacaoNiveis(true)}
        />
      </div>

      {mostrarCorrelacaoNiveis && (
        <CorrelacaoNiveisModal
          projeto={projeto}
          estrutura={estrutura}
          adicionarToast={adicionarToast}
          onFechar={() => setMostrarCorrelacaoNiveis(false)}
        />
      )}
    </div>
  );
}
