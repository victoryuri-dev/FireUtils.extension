// normaHidrantesMA.js — dados normativos da NT 22/2021 CBMMA (Tabelas 2 e 3)
// necessários pra classificar o Sistema de Hidrantes/Mangotinhos direto na
// dockpane, sem depender do site pra essa decisão. Cópia fiel de
// ETOS.FireUtils/src/data/normas/MA/hidrantes.js (só o subconjunto usado
// pela classificação — Tabela 2/3; reservatório, bomba, rede etc.
// continuam decisões só do site) — os dois lados precisam concordar
// nesses valores, por isso qualquer mudança na Tabela 3 do site tem que
// ser replicada aqui também.

// Onde a norma exige que a vazão/pressão mínima do sistema seja
// verificada — usado pra derivar o token "metodoCalculo" mandado ao
// aplicar a classificação (ver hidrantes_classificacao_bridge.py).
export const REFERENCIA_PRESSAO_VAZAO = "valvula";

// ── Tabela 2 — Tipos de sistema ─────────────────────────────────────────
// Tipo 4 tem duas variantes válidas (mesma vazão mínima, esguicho/mangueira/
// pressão diferentes) — o projetista escolhe qual adotar.
export const TIPOS_SISTEMA = {
  1: {
    label: "Tipo 1 — Mangotinho",
    expedicoes: "simples",
    vazaoMin: 100, pressaoMin: 80,
    variantes: [{ esguicho: 25, mangueiraDn: 25, mangueiraComprimento: 30, pressaoMin: 80 }],
  },
  2: {
    label: "Tipo 2",
    expedicoes: "simples",
    vazaoMin: 150, pressaoMin: 30,
    variantes: [{ esguicho: 40, mangueiraDn: 40, mangueiraComprimento: 30, pressaoMin: 30 }],
  },
  3: {
    label: "Tipo 3",
    expedicoes: "simples",
    vazaoMin: 200, pressaoMin: 40,
    variantes: [{ esguicho: 40, mangueiraDn: 40, mangueiraComprimento: 30, pressaoMin: 40 }],
  },
  4: {
    label: "Tipo 4",
    expedicoes: "simples",
    vazaoMin: 300, pressaoMin: 65,
    variantes: [
      { esguicho: 40, mangueiraDn: 40, mangueiraComprimento: 30, pressaoMin: 65 },
      { esguicho: 60, mangueiraDn: 65, mangueiraComprimento: 30, pressaoMin: 30 },
    ],
  },
  5: {
    label: "Tipo 5",
    expedicoes: "duplo",
    vazaoMin: 600, pressaoMin: 60,
    variantes: [{ esguicho: 65, mangueiraDn: 65, mangueiraComprimento: 30, pressaoMin: 60 }],
  },
};

// ── Tabela 3 — Faixas de área construída (m²) ───────────────────────────
export const FAIXAS_AREA = [
  { max: 2500, label: "Até 2.500 m²" },
  { min: 2500, max: 5000, label: "Acima de 2.500 até 5.000 m²" },
  { min: 5000, max: 10000, label: "Acima de 5.000 até 10.000 m²" },
  { min: 10000, max: 20000, label: "Acima de 10.000 até 20.000 m²" },
  { min: 20000, max: 50000, label: "Acima de 20.000 até 50.000 m²" },
  { min: 50000, label: "Acima de 50.000 m²" },
];

// ── Tabela 3 — Colunas de risco (por linha/faixa de área) ───────────────
// col1: Tipo 1 OU Tipo 2 (projetista escolhe). col2: Tipo 3 fixo. col3:
// Tipo 4 fixo. col4: Tipo 4 ou 5, já definido pela própria tabela.
export const TABELA3 = [
  { col1: { tipo1: { rti: 6 }, tipo2: { rti: 8 } }, col2: { tipo: 3, rti: 12 }, col3: { tipo: 4, rti: 28 }, col4: { tipo: 4, rti: 32 } },
  { col1: { tipo1: { rti: 8 }, tipo2: { rti: 12 } }, col2: { tipo: 3, rti: 18 }, col3: { tipo: 4, rti: 32 }, col4: { tipo: 4, rti: 48 } },
  { col1: { tipo1: { rti: 12 }, tipo2: { rti: 18 } }, col2: { tipo: 3, rti: 25 }, col3: { tipo: 4, rti: 48 }, col4: { tipo: 5, rti: 64 } },
  { col1: { tipo1: { rti: 18 }, tipo2: { rti: 25 } }, col2: { tipo: 3, rti: 35 }, col3: { tipo: 4, rti: 64 }, col4: { tipo: 5, rti: 96 } },
  { col1: { tipo1: { rti: 25 }, tipo2: { rti: 35 } }, col2: { tipo: 3, rti: 48 }, col3: { tipo: 4, rti: 96 }, col4: { tipo: 5, rti: 120 } },
  { col1: { tipo1: { rti: 35 }, tipo2: { rti: 48 } }, col2: { tipo: 3, rti: 70 }, col3: { tipo: 4, rti: 120 }, col4: { tipo: 5, rti: 180 } },
];

// Divisões com coluna fixa (não dependem da carga de incêndio)
export const DIVISOES_COLUNA = {
  "A-2": 1, "A-3": 1, "C-1": 1, "D-2": 1,
  "E-1": 1, "E-2": 1, "E-3": 1, "E-4": 1, "E-5": 1, "E-6": 1,
  "F-2": 1, "F-3": 1, "F-4": 1, "F-8": 1,
  "G-1": 1, "G-2": 1, "G-3": 1, "G-4": 1,
  "H-1": 1, "H-2": 1, "H-3": 1, "H-5": 1, "H-6": 1,
  "I-1": 1, "J-1": 1, "M-3": 1,

  "B-1": 2, "B-2": 2, "C-3": 2,
  "F-5": 2, "F-6": 2, "F-7": 2, "F-9": 2, "F-10": 2, "F-11": 2,
  "H-4": 2, "K-1": 2,

  "L-1": 3, "M-1": 3,

  "G-5": 4, "I-3": 4, "J-4": 4, "L-2": 4, "L-3": 4, "M-7": 4,
};

// Divisões cuja coluna depende da carga de incêndio (MJ/m²) do pavimento —
// faixas avaliadas em ordem, a primeira que bater vence.
export const DIVISOES_POR_CARGA = {
  "D-1": [{ max: 300, coluna: 1 }, { min: 300, coluna: 2 }],
  "D-3": [{ max: 300, coluna: 1 }, { min: 300, coluna: 2 }],
  "D-4": [{ max: 300, coluna: 1 }, { min: 300, coluna: 2 }],
  "F-1": [{ max: 300, coluna: 1 }, { min: 300, coluna: 2 }],
  "J-2": [{ max: 300, coluna: 1 }, { min: 300, coluna: 2 }],
  "C-2": [{ max: 1000, coluna: 2 }, { min: 1000, coluna: 3 }],
  "I-2": [{ max: 800, coluna: 2 }, { min: 800, coluna: 3 }],
  "J-3": [{ max: 300, coluna: 1 }, { min: 300, max: 800, coluna: 2 }, { min: 800, coluna: 3 }],
};
