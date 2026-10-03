import { useState } from "react";
import Icon from "../Icon";
import InfoTip from "../InfoTip";
import chevronDownSvg from "../../assets/icons/chevron-down-icon.svg?raw";
import { fmtNum } from "../../lib/numero";

// Mesmos formatadores da seção equivalente do site (ETOS.FireUtils,
// src/pages/medidas/HidrantesPage.jsx) — ver docstring de lib/numero.js.
const f2 = (n) => fmtNum(n, 2, "0");
const f3 = (n) => fmtNum(n, 3, "0");
const f4 = (n) => fmtNum(n, 4, "0");
const fmca = (n) => `${f4(n)} mca`;
const lmin = (n) => `${f2(n)} L/min`;
const ms = (n) => `${f3(n)} m/s`;

// Pressão de referência no hidrante (o que se compara contra Pmin): na
// ponta do esguicho quando o método é "Ponta do Esguicho Regulável", na
// válvula quando é "Válvula do Hidrante" — mesma lógica do site.
function pressaoHidrante(res, hd) {
  if (!res.esguicho) return hd === "hd01" ? res.P_hd01 : res.P_hd02;
  return res.esg[hd].P_esg;
}

// ── Primitivas de tabela/cartão — equivalentes aos helpers Tailwind do
// site (Table/TH/TD/Card/CardHeader/VelChip/AtendeChip em HidrantesPage.jsx),
// com classes CSS próprias (ver App.css, seção "Dimensionamento do Sistema
// (hidrantes)") em vez de utilitários Tailwind.
function Tabela({ children }) {
  return (
    <div className="hiddim-tabela-wrap">
      <table className="hiddim-tabela">{children}</table>
    </div>
  );
}
function TH({ children, right, center, w }) {
  const alinhamento = right ? "right" : center ? "center" : "left";
  return (
    <th style={w ? { width: w } : undefined} className={`hiddim-th hiddim-align-${alinhamento}`}>
      {children}
    </th>
  );
}
function TD({ children, red, green, bold, muted, right, center, mono }) {
  const alinhamento = right ? "right" : center ? "center" : "left";
  const cor = red ? "red" : green ? "green" : muted ? "muted" : "normal";
  return (
    <td
      className={`hiddim-td hiddim-align-${alinhamento} hiddim-cor-${cor} ${bold ? "hiddim-bold" : ""} ${
        mono ? "hiddim-mono" : ""
      }`}
    >
      {children}
    </td>
  );
}
function VelChip({ v, limite }) {
  const ok = v <= limite;
  return (
    <span className={`hiddim-chip ${ok ? "hiddim-chip-ok" : "hiddim-chip-bad"}`}>
      {ok ? "✓" : "✗"} {ms(v)}
    </span>
  );
}
function AtendeChip({ ok }) {
  return <span className={`hiddim-chip hiddim-chip-grande ${ok ? "hiddim-chip-ok" : "hiddim-chip-bad"}`}>{ok ? "ATENDE" : "NÃO ATENDE"}</span>;
}
function Cartao({ children, className = "" }) {
  return <div className={`hiddim-cartao ${className}`}>{children}</div>;
}
function CartaoHeader({ children }) {
  return <div className="hiddim-cartao-header">{children}</div>;
}

// ── Dados do Sistema (resumo compacto) ───────────────────────────────────
export function DadosDoSistema({ d }) {
  const { dados_sistema, valor_sistema, metodo, C_HW, res } = d;
  const stats = [
    { label: "Classificação", val: valor_sistema },
    { label: "Método", val: metodo },
    { label: "Vazão mínima", val: `${f2(dados_sistema.q_min)} L/min` },
    { label: "Pressão mín.–máx.", val: `${dados_sistema.p_min}–100 mca` },
    { label: "Coef. C", val: String(C_HW) },
  ];
  if (res.esguicho) {
    stats.push({ label: "Mangueira", val: `DN${dados_sistema.mang_dn} · ${f2(dados_sistema.mang_comp)} m` });
  }
  return (
    <div className="hiddim-stat-grid">
      {stats.map((s) => (
        <div key={s.label} className="hiddim-stat-box">
          <div className="hiddim-stat-label">{s.label}</div>
          <div className="hiddim-stat-val">{s.val}</div>
        </div>
      ))}
    </div>
  );
}

// Cabeçalho de coluna em sigla + InfoTip com o significado — equivalente ao
// THSigla do site (HidrantesPage.jsx).
function THSigla({ sigla, tip, align = "center" }) {
  return (
    <span className={`hiddim-th-sigla hiddim-th-sigla-${align}`}>
      {sigla}
      <InfoTip text={tip} align={align} />
    </span>
  );
}

// ── Verificação do Hidrante Mais Desfavorável ────────────────────────────
function situacaoHidrante(indice, total) {
  if (indice === 0) return { texto: "1º Hidrante Mais Desfavorável", classe: "hiddim-situacao-red" };
  if (indice === 1) return { texto: "2º Hidrante Mais Desfavorável", classe: "hiddim-situacao-amber" };
  if (indice === total - 1) return { texto: "Hidrante Mais Favorável", classe: "hiddim-situacao-neutro" };
  return null;
}

export function VerificacaoHidranteDesfavoravel({ ranking }) {
  const [expandido, setExpandido] = useState(false);
  if (!ranking || ranking.length === 0) return null;

  const total = ranking.length;
  const temOcultos = total > 3;
  const linhas = expandido || !temOcultos
    ? ranking.map((h, i) => [h, i])
    : [[ranking[0], 0], [ranking[1], 1], [ranking[total - 1], total - 1]];

  return (
    <div className="hiddim-secao">
      <h4 className="hiddim-secao-titulo">Verificação do Hidrante Mais Desfavorável</h4>
      <Tabela>
        <thead>
          <tr>
            <TH>Hidrante</TH>
            <TH right>
              <THSigla sigla="J" align="end" tip="Perda de carga do trecho Bomba → Hidrante, por Hazen-Williams, com a vazão nominal de um único hidrante — sem equilíbrio hidráulico. Usada só para ranquear." />
            </TH>
            <TH right>
              <THSigla sigla="∆Z" align="end" tip="Desnível geométrico entre a bomba e o hidrante." />
            </TH>
            <TH right>
              <THSigla sigla="J + ∆Z" align="end" tip="Perda de Carga Total = perda de carga (J) + desnível (∆Z) — usada só para ranquear os hidrantes. O 1º e o 2º mais desfavoráveis recebem a marcha de cálculo completa, com equilíbrio hidráulico, no restante desta etapa." />
            </TH>
            <TH center>Situação</TH>
          </tr>
        </thead>
        <tbody>
          {linhas.map(([h, i]) => {
            const situacao = situacaoHidrante(i, total);
            return (
              <tr key={h.id}>
                <TD bold>{h.id}</TD>
                <TD right mono muted>{fmca(h.J)}</TD>
                <TD right mono muted>{f4(h.dZ)} m</TD>
                <TD right bold mono>{fmca(h.score)}</TD>
                <td className="hiddim-td hiddim-align-center">
                  {situacao ? <span className={`hiddim-situacao ${situacao.classe}`}>{situacao.texto}</span> : <span className="hiddim-td-vazio">—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </Tabela>
      {temOcultos && (
        <button type="button" onClick={() => setExpandido((e) => !e)} className="hiddim-expand-btn">
          {expandido ? "Mostrar menos" : `Mostrar todos os ${total} hidrantes`}
          <Icon svg={chevronDownSvg} className={`hiddim-expand-icon ${expandido ? "hiddim-expand-icon-aberto" : ""}`} />
        </button>
      )}
      <div className="hiddim-nota">
        Perda de Carga Total = perda de carga (vazão nominal de um hidrante, sem equilíbrio hidráulico) + desnível
        geométrico até a bomba — usado só pra ranquear. O 1º e o 2º hidrante mais desfavorável recebem a marcha de
        cálculo completa, com equilíbrio hidráulico, no restante desta etapa.
      </div>
    </div>
  );
}

// ── Resumo Executivo ──────────────────────────────────────────────────
export function ResumoExecutivo({ d }) {
  const { res, dados_sistema } = d;
  const pmin = dados_sistema.p_min;
  const pmax = 100;
  const p01 = pressaoHidrante(res, "hd01");
  const p02 = pressaoHidrante(res, "hd02");
  const labelPressao = res.esguicho ? "Pressão no esguicho" : "Pressão na válvula";

  const cards = [
    {
      id: "HID-01",
      label: "1º MAIS DESFAVORÁVEL",
      cor: "red",
      rows: [
        { label: labelPressao, val: fmca(p01) },
        { label: "Vazão real", val: lmin(res.Q_hd01) },
      ],
      atende: p01 >= pmin && p01 <= pmax,
    },
    {
      id: "HID-02",
      label: "2º MAIS DESFAVORÁVEL",
      cor: "amber",
      rows: [
        { label: labelPressao, val: fmca(p02) },
        { label: "Vazão real", val: lmin(res.Q_hd02) },
      ],
      atende: p02 >= pmin && p02 <= pmax,
    },
  ];

  return (
    <div className="hiddim-resumo-grid">
      {cards.map((c) => (
        <Cartao key={c.id}>
          <CartaoHeader>
            <span className={`hiddim-id-badge hiddim-id-badge-${c.cor}`}>{c.id}</span>
            <span className="hiddim-label-fraco">{c.label}</span>
          </CartaoHeader>
          <div className="hiddim-resumo-corpo">
            {c.rows.map((r, i) => (
              <div key={i} className="hiddim-resumo-linha">
                <span className="hiddim-resumo-linha-label">{r.label}</span>
                <span className="hiddim-resumo-linha-val">{r.val}</span>
              </div>
            ))}
            <div className="hiddim-resumo-chip">
              <AtendeChip ok={c.atende} />
            </div>
          </div>
        </Cartao>
      ))}
    </div>
  );
}

// ── Resultado Hidráulico ─────────────────────────────────────────────────
export function ResultadoHidraulico({ d }) {
  const { res } = d;
  return (
    <div className="hiddim-resultado-grid">
      <div className="hiddim-resultado-box">
        <div className="hiddim-resultado-label">Altura Manométrica Total (Ht)</div>
        <div className="hiddim-resultado-val">{fmca(res.P_RTI)}</div>
      </div>
      <div className="hiddim-resultado-box">
        <div className="hiddim-resultado-label">Vazão Total (Qt)</div>
        <div className="hiddim-resultado-val">{lmin(res.Qt)}</div>
      </div>
      <div className="hiddim-resultado-box">
        <div className="hiddim-resultado-label">Ramal Governante</div>
        <div className="hiddim-resultado-val hiddim-resultado-val-neutro">{res.hid_governa}</div>
      </div>
    </div>
  );
}

// ── Verificação de Velocidade ────────────────────────────────────────────
const ORDEM_TRECHOS = ["t3", "t4", "t2", "t1"];

function limiteVelocidade(trechoId, succao, limites) {
  if (trechoId === "t1") return succao === "positiva" ? limites.vMaxSuccaoPositiva : limites.vMaxSuccaoNegativa;
  return limites.vMaxTubulacao;
}

export function VerificacaoVelocidade({ d, limites }) {
  const trechos = ORDEM_TRECHOS.map((id) => [id, d.res.j[id]]);
  return (
    <div className="hiddim-secao">
      <h4 className="hiddim-secao-titulo">Verificação de Velocidade</h4>
      <Tabela>
        <thead>
          <tr>
            <TH>Trecho</TH>
            <TH>DN</TH>
            <TH right>Limite Normativo</TH>
            <TH>Velocidade</TH>
          </tr>
        </thead>
        <tbody>
          {trechos.flatMap(([id, t]) => {
            const vLimite = limiteVelocidade(id, d.succao, limites);
            return t.segmentos.map((seg, i) => (
              <tr key={`${id}-${i}`}>
                <TD bold>{t.label}</TD>
                <TD mono muted>DN{Number(seg.d_mm).toFixed(0)}</TD>
                <TD right mono muted>{ms(vLimite)}</TD>
                <td className="hiddim-td">
                  <VelChip v={seg.V} limite={vLimite} />
                </td>
              </tr>
            ));
          })}
        </tbody>
      </Tabela>
    </div>
  );
}

// ── Perdas de Carga por Trecho ───────────────────────────────────────────
function MiniStat({ label, nivel = "secundario", val }) {
  return (
    <div className="hiddim-ministat">
      <div className="hiddim-ministat-label">{label}</div>
      <div className={`hiddim-ministat-val hiddim-ministat-${nivel}`}>{val}</div>
    </div>
  );
}

function SegmentoTrecho({ seg }) {
  return (
    <div className="hiddim-segmento">
      <div className="hiddim-segmento-topo">
        <span className="hiddim-dn-badge">DN{Number(seg.d_mm).toFixed(0)}</span>
        <span className="hiddim-segmento-tubo">
          Tubo reto: <strong>{f4(seg.L)} m</strong>
        </span>
      </div>

      {seg.acessorios.length > 0 && (
        <div className="hiddim-segmento-acessorios">
          <div className="hiddim-segmento-acessorios-titulo">Conexões e Acessórios (perda localizada)</div>
          <Tabela>
            <thead>
              <tr>
                <TH>Componente</TH>
                <TH center w={52}>Qtd</TH>
                <TH right>Leq unit.</TH>
                <TH right>Leq total</TH>
              </tr>
            </thead>
            <tbody>
              {seg.acessorios.map((a, i) => (
                <tr key={i}>
                  <TD>{a.nome}</TD>
                  <TD center bold>{a.qtd}</TD>
                  <TD right mono muted>{f2(a.leq_unit)} m</TD>
                  <TD right mono bold>{f2(a.leq_tot)} m</TD>
                </tr>
              ))}
            </tbody>
          </Tabela>
        </div>
      )}

      <div className="hiddim-ministat-grid">
        <MiniStat label="Comp. Equivalente (Leq)" nivel="terciario" val={`${f4(seg.Leq)} m`} />
        <MiniStat label="Comp. Total (Ltotal)" nivel="secundario" val={`${f4(seg.Ltotal)} m`} />
        <MiniStat label="Perda de Carga do Trecho (J)" nivel="primario" val={fmca(seg.J)} />
      </div>
    </div>
  );
}

function TrechoDetalhe({ id, t }) {
  return (
    <Cartao className="hiddim-trecho-cartao">
      <CartaoHeader>
        <span className="hiddim-trecho-id">{id.toUpperCase()}</span>
        <span className="hiddim-trecho-label">{t.label}</span>
        <span className="hiddim-trecho-info">
          Q = {lmin(t.Q_lmin)} · J total = {fmca(t.J)}
        </span>
      </CartaoHeader>
      <div className="hiddim-trecho-corpo">
        {t.segmentos.map((seg, i) => (
          <SegmentoTrecho key={i} seg={seg} />
        ))}
      </div>
    </Cartao>
  );
}

export function PerdasPorTrecho({ d }) {
  const trechos = ORDEM_TRECHOS.map((id) => [id, d.res.j[id]]);
  return (
    <div className="hiddim-secao">
      <h4 className="hiddim-secao-titulo">Perdas de Carga por Trecho</h4>
      {trechos.map(([id, t]) => (
        <TrechoDetalhe key={id} id={id} t={t} />
      ))}
    </div>
  );
}

// ── Seção completa — composição das peças acima, na mesma ordem do site
// (ver "etapa === 2" em HidrantesPage.jsx lá). `d` é o cache cru de
// "Dimensionar Hidrantes" (payload.dimensionamento, ver bridge.js) e
// `limites` os limites normativos de velocidade (payload.limites).
export default function HidrantesDimensionamento({ d, limites }) {
  return (
    <>
      <DadosDoSistema d={d} />
      <VerificacaoHidranteDesfavoravel ranking={d.ranking_hidrantes} />
      <ResumoExecutivo d={d} />
      <ResultadoHidraulico d={d} />
      <VerificacaoVelocidade d={d} limites={limites} />
      <PerdasPorTrecho d={d} />
    </>
  );
}
