// hidrantesCalc.js — cálculo de potência mínima da bomba de incêndio, do
// lado da dockpane. Mesma fórmula do site (ETOS.FireUtils, ver
// src/data/hidrantes_calc.js:calcPotenciaBomba) — potência é sempre
// calculada em JS (site OU dockpane, nunca no plugin Python), a partir de
// Qt/Ht (vindos do último "Dimensionar Hidrantes", ver
// hidrantes_dimensionamento_bridge.py) e da eficiência informada aqui.
export function calcPotenciaBomba(qtLmin, htMca, etaPercent) {
  const etaDec = (parseFloat(etaPercent) || 0) / 100
  if (etaDec <= 0 || !qtLmin || !htMca) return { potCv: null, potKw: null }
  const qtM3s = qtLmin / 60000
  const potCv = (1000 * qtM3s * htMca) / (75 * etaDec)
  return { potCv, potKw: potCv / 1.36 }
}
