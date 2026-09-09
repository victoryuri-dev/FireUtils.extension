import { useState } from "react";
import Icon from "../Icon";
import { taxaOpcoes, popTipoPadrao, calcPT } from "../../data/se_calc";
import checkIconSvg from "../../assets/icons/check-icon.svg?raw";
import xIconSvg from "../../assets/icons/x-icon.svg?raw";

/**
 * seShared.jsx — UI compartilhada da árvore de Saída de Emergência
 * (SaidaEmergenciaLista.jsx / AcessosDescargasView.jsx), portada de
 * ETOS.FireUtils/src/pages/medidas/se_shared.jsx — mesmas regras de
 * negócio, reescrita em CSS simples (App.css) em vez das classes utility
 * do Tailwind que o site usa, pra ficar consistente com o resto desta
 * webapp.
 */

export const fmt = (n) => Number(n).toFixed(2).replace(".", ",");
export const fmtM = (n) => `${fmt(n)} m`;

// Tag de ocupação (código da divisão, ex.: "D-1") — cinza neutro. Vermelho
// fica reservado pros valores de largura mínima (o que de fato importa
// dimensionalmente), não pra classificação.
export function DivBadge({ label }) {
  return <span className="se-div-badge">{label || "?"}</span>;
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className={`se-toggle ${checked ? "se-toggle-on" : ""}`}>
      <span className="se-toggle-track">
        <span className="se-toggle-thumb" />
      </span>
      {label}
    </button>
  );
}

function DivisaoSelect({ value, onChange, ocupacoes }) {
  return (
    <select className="se-select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Selecionar divisão...</option>
      {Object.keys(ocupacoes)
        .sort()
        .map((grupo) => (
          <optgroup key={grupo} label={`Grupo ${grupo} — ${ocupacoes[grupo]?.descricao || grupo}`}>
            {Object.keys(ocupacoes[grupo]?.divisoes || {}).map((div) => (
              <option key={div} value={div}>
                {div}: {ocupacoes[grupo].divisoes[div]}
              </option>
            ))}
          </optgroup>
        ))}
    </select>
  );
}

// ── Formulário de ambiente ────────────────────────────────────────────
// Sem campo de nome — o nome do ambiente é editado pelo lápis no título
// do modal que envolve este formulário (ver AcessosDescargasView.jsx).
// `larguras`, se informado, habilita o cálculo de N° UP (porta) no
// rodapé.
export function AmbienteForm({ initial, onSave, onCancel, seNorma, ocupacoes, larguras }) {
  const { TAXA_POPULACIONAL, NOTAS_NORMATIVAS } = seNorma;
  const blank = { divisao: "", popTipo: "area", area: "", assentos: "", popManual: "" };
  const [form, setForm] = useState(() =>
    initial
      ? {
          divisao: initial.divisao,
          popTipo: initial.popTipo,
          area: initial.area ? String(initial.area) : "",
          assentos: initial.assentos ? String(initial.assentos) : "",
          popManual: initial.popManual ? String(initial.popManual) : "",
        }
      : blank
  );

  const taxa = TAXA_POPULACIONAL[form.divisao];
  const opcoes = taxaOpcoes(form.divisao, TAXA_POPULACIONAL);
  const isManual = form.popTipo === "manual";
  const isFixo = form.popTipo === "fixo";
  const isArea = form.popTipo === "area";

  const popCalc = () => {
    if (isFixo) return parseInt(form.assentos) || 0;
    if (isManual) return parseInt(form.popManual) || 0;
    return taxa?.A && form.area ? Math.ceil(parseFloat(form.area) / taxa.A) : 0;
  };

  const setDivisao = (div) =>
    setForm((f) => ({ ...f, divisao: div, popTipo: popTipoPadrao(div, TAXA_POPULACIONAL), area: "", assentos: "", popManual: "" }));
  const setTipo = (tipo) => setForm((f) => ({ ...f, popTipo: tipo, area: "", assentos: "", popManual: "" }));

  const canSave = () => {
    if (!form.divisao) return false;
    if (isArea && !form.area) return false;
    if (isFixo && !form.assentos) return false;
    if (isManual && !form.popManual) return false;
    return true;
  };

  const handleSave = () => {
    if (!canSave()) return;
    onSave({
      divisao: form.divisao,
      popTipo: form.popTipo,
      area: parseFloat(form.area) || 0,
      assentos: parseInt(form.assentos) || 0,
      popManual: parseInt(form.popManual) || 0,
    });
  };

  const inputLabel = isArea ? "Área (m²)" : isFixo ? "Assentos" : "N° de pessoas";
  const pop = popCalc();
  const nUP = larguras ? calcPT(pop, taxa?.PT ?? 100, larguras).n : null;

  return (
    <div className="se-form">
      <div>
        <div className="se-label">Divisão</div>
        <DivisaoSelect value={form.divisao} onChange={setDivisao} ocupacoes={ocupacoes} />
      </div>

      {form.divisao && (
        <div className="se-form-row">
          <div>
            <div className="se-label">Taxa normativa</div>
            {opcoes.length > 1 ? (
              <select className="se-select" value={form.popTipo} onChange={(e) => setTipo(e.target.value)}>
                {opcoes.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : (
              <div className="se-select se-select-fixo">{opcoes[0]?.label || "—"}</div>
            )}
          </div>
          <div>
            <div className="se-label">{inputLabel}</div>
            {isArea && (
              <input
                className="se-input"
                type="number"
                min="0"
                placeholder="ex.: 64,5"
                value={form.area}
                onChange={(e) => setForm((f) => ({ ...f, area: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
              />
            )}
            {isFixo && (
              <input
                className="se-input"
                type="number"
                min="0"
                placeholder="ex.: 120"
                value={form.assentos}
                onChange={(e) => setForm((f) => ({ ...f, assentos: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
              />
            )}
            {isManual && (
              <input
                className="se-input"
                type="number"
                min="0"
                placeholder="ex.: 8"
                value={form.popManual}
                onChange={(e) => setForm((f) => ({ ...f, popManual: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
              />
            )}
          </div>
        </div>
      )}

      {taxa?.notas?.length > 0 && (
        <div>
          <div className="se-label">Notas</div>
          <div className="se-notas">
            {taxa.notas.map((k) => NOTAS_NORMATIVAS[k] && <div key={k} className="se-nota">{NOTAS_NORMATIVAS[k]}</div>)}
          </div>
        </div>
      )}

      <div className="se-form-footer">
        <div className="se-form-stats">
          <div>
            <div className="se-stat-label">População</div>
            <div className={`se-stat-value ${pop > 0 ? "se-stat-value-red" : "se-stat-value-faint"}`}>{pop} Pessoas</div>
          </div>
          {nUP !== null && (
            <div>
              <div className="se-stat-label">U.P.</div>
              <div className="se-stat-value">{nUP} UP</div>
            </div>
          )}
        </div>
        <div className="se-form-botoes">
          <button type="button" className="botao" onClick={onCancel}>
            <Icon svg={xIconSvg} /> Cancelar
          </button>
          <button type="button" className="botao accent" onClick={handleSave} disabled={!canSave()}>
            <Icon svg={checkIconSvg} /> Salvar
          </button>
        </div>
      </div>
    </div>
  );
}
