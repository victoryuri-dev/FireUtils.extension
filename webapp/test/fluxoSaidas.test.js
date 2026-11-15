import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

// seReducer.js e as cópias de se_calc/se_fluxo importam sem extensão (como o
// resto do webapp, resolvido pelo Vite) — por isso o carregamento via Vite SSR.
const server = await createServer({ root: new URL("..", import.meta.url).pathname, server: { middlewareMode: true }, appType: "custom", logLevel: "silent" });
after(() => server.close());
const calc = await server.ssrLoadModule("/src/data/se_calc.js");
const fluxo = await server.ssrLoadModule("/src/data/se_fluxo.js");
const { aplicarAcaoSaida, garantirFluxoMigrado } = await server.ssrLoadModule("/src/lib/seReducer.js");

// Projeto no formato ANTIGO (antes do fluxograma): sem grupos/tipo/faixaPos.
const legado = () => ({
  estruturas: [{ id: "e1", nome: "Bloco A" }],
  pavimentos: [
    { id: "e1-P1", estruturaId: "e1", label: "Térreo", tipo: "terreo", pisoDescarga: true, ambientes: [{ id: "m0", nome: "Loja", divisao: "C-1", area: "100", acessoId: "r0" }], acessos: [{ id: "r0", nome: "Saída 01", alimentaEm: null }] },
    { id: "e1-P2", estruturaId: "e1", label: "1º Pavimento", tipo: "pav", pisoDescarga: false, ambientes: [{ id: "m1", nome: "Sala", divisao: "C-1", area: "300", acessoId: "a1" }], acessos: [{ id: "r1", nome: "Escada", alimentaEm: null }, { id: "a1", nome: "Acesso 1", alimentaEm: "r1" }] },
    { id: "e1-P3", estruturaId: "e1", label: "2º Pavimento", tipo: "pav", pisoDescarga: false, ambientes: [], acessos: [] },
  ],
});
const pav = (dados, id) => dados.pavimentos.find((p) => p.id === id);
const raiz = (dados, id) => pav(dados, id).acessos.find((a) => a.fixo);

test("projeto antigo é migrado: grupo por acesso, saída/escada padrão em todo pavimento, faixas empilhadas", () => {
  const d = garantirFluxoMigrado(legado());
  assert.deepEqual(d.pavimentos.map((p) => raiz(d, p.id).tipo), ["saida", "escada", "escada"]);
  assert.equal(raiz(d, "e1-P3").id, "acs-fixo-e1-P3");
  // Sala estava ligada ao Acesso 1: agora num grupo ligado a ele (e continua alimentando o mesmo nó).
  const p2 = pav(d, "e1-P2");
  assert.deepEqual(p2.grupos.map((g) => g.acessoId), ["a1"]);
  assert.equal(p2.ambientes[0].acessoId, "a1");
  // Escadas padrão já ligadas em cadeia até a saída do piso de descarga.
  assert.deepEqual(d.pavimentos.map((p) => raiz(d, p.id).ligadoA ?? null), [null, "r0", "r1"]);
  // Faixas: todas com origem, a do 2º pavimento (mais alto) acima da do 1º, acima da do térreo.
  const y = (id) => pav(d, id).faixaPos.y;
  assert.ok(y("e1-P3") < y("e1-P2") && y("e1-P2") < y("e1-P1"));
});

test("migração é idempotente e não depende da ordem das chaves (jsonb do Postgres reordena)", () => {
  const d = garantirFluxoMigrado(legado());
  assert.equal(garantirFluxoMigrado(d), d);
  const reordenado = JSON.parse(JSON.stringify(d), (_, v) => (v && typeof v === "object" && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).reverse()) : v));
  assert.equal(garantirFluxoMigrado(reordenado), reordenado);
});

test("o cálculo antigo não muda: população e larguras dos nós já existentes são as mesmas", () => {
  const taxa = { "C-1": { A: 3, AD: 100, ER: 75, PT: 100 } };
  const larg = { AD: 1.1, ER: 1.2, LARG_UP: 0.55, PT: [{ n_up: 1, largura: 0.8, tipo: "1 folha" }, { n_up: 2, largura: 1.2, tipo: "2 folhas" }] };
  const antes = legado();
  const depois = garantirFluxoMigrado(antes);
  for (const id of ["e1-P1", "e1-P2"]) {
    const a = pav(antes, id), d = pav(depois, id);
    for (const ac of a.acessos) {
      const x = calc.calcDimsAcesso(ac.id, a.ambientes, a.acessos, taxa, larg, calc.dimsDoAcesso(ac, !!a.pisoDescarga));
      const y = calc.calcDimsAcesso(ac.id, d.ambientes, d.acessos, taxa, larg, calc.dimsDoAcesso(d.acessos.find((n) => n.id === ac.id), !!d.pisoDescarga));
      assert.deepEqual([y.pop, y.ad?.la, y.er?.la, y.pt?.la], [x.pop, x.ad?.la, x.er?.la, x.pt?.la]);
    }
  }
});

test("ações: criar nó e grupo, ligar, soltar ambiente na área e voltar pra lista", () => {
  let d = garantirFluxoMigrado(legado());
  d = aplicarAcaoSaida(d, { type: "CRIAR_NO_FLUXO", pavimentoId: "e1-P3", id: "n1", tipo: "acesso", nome: "Acesso 1", pos: { x: 100, y: 200 } });
  d = aplicarAcaoSaida(d, { type: "ADD_AMBIENTE_SE", pavimentoId: "e1-P3", id: "m9", ambiente: { nome: "Auditório", divisao: "C-1", area: 90, grupoId: null, origem: "manual" } });
  d = aplicarAcaoSaida(d, { type: "SOLTAR_AMBIENTES_NA_AREA", pavimentoId: "e1-P3", posicoes: { m9: { x: 10, y: 10 } } });
  d = aplicarAcaoSaida(d, { type: "LIGAR_AMBIENTE", pavimentoId: "e1-P3", ambienteId: "m9", acessoId: "n1" });
  d = aplicarAcaoSaida(d, { type: "MOVER_ACESSO", pavimentoId: "e1-P3", acessoId: "n1", novoAlimentaEm: "acs-fixo-e1-P3" });
  const p3 = pav(d, "e1-P3");
  assert.equal(p3.ambientes[0].acessoId, "n1");
  assert.equal(calc.calcPopAcesso("acs-fixo-e1-P3", p3.ambientes, p3.acessos, { "C-1": { A: 3 } }), 30);
  d = aplicarAcaoSaida(d, { type: "MOVER_AMBIENTES_GRUPO", pavimentoId: "e1-P3", ambienteIds: ["m9"], grupoId: null });
  assert.deepEqual([pav(d, "e1-P3").ambientes[0].acessoId, pav(d, "e1-P3").fluxoPos.m9], [null, undefined]);
});

test("a saída/escada padrão não se exclui nem troca de tipo; mais de um piso de descarga; escada vira saída", () => {
  let d = garantirFluxoMigrado(legado());
  d = aplicarAcaoSaida(d, { type: "REMOVER_ACESSO", pavimentoId: "e1-P2", acessoId: "r1" }); // r1 é a padrão (1ª raiz que já existia)
  assert.ok(pav(d, "e1-P2").acessos.some((a) => a.id === "r1"));
  d = aplicarAcaoSaida(d, { type: "SET_ACESSO_TIPO", pavimentoId: "e1-P2", acessoId: "r1", tipo: "acesso" });
  assert.equal(raiz(d, "e1-P2").tipo, "escada");
  d = aplicarAcaoSaida(d, { type: "SET_PISO_DESCARGA", pavimentoId: "e1-P2", valor: true });
  assert.deepEqual(d.pavimentos.map((p) => [p.pisoDescarga, raiz(d, p.id).tipo]), [[true, "saida"], [true, "saida"], [false, "escada"]]);
  // A escada do 2º agora liga na saída do 1º (piso de descarga mais próximo).
  assert.equal(raiz(d, "e1-P3").ligadoA, "r1");
});

test("ligação entre pavimentos guarda ligadoA e some com o nó de destino", () => {
  let d = garantirFluxoMigrado(legado());
  d = aplicarAcaoSaida(d, { type: "CRIAR_NO_FLUXO", pavimentoId: "e1-P2", id: "ex", tipo: "escada", nome: "Escada/Rampa 02", pos: { x: 1, y: 1 } });
  d = aplicarAcaoSaida(d, { type: "LIGAR_ENTRE_PAVIMENTOS", pavimentoId: "e1-P3", acessoId: "acs-fixo-e1-P3", destinoId: "ex" });
  assert.equal(raiz(d, "e1-P3").ligadoA, "ex");
  d = aplicarAcaoSaida(d, { type: "REMOVER_ACESSO", pavimentoId: "e1-P2", acessoId: "ex" });
  assert.equal(raiz(d, "e1-P3").ligadoA, null);
});

test("importação do Revit mantém grupo e ligação dos ambientes que já existiam", () => {
  let d = garantirFluxoMigrado(legado());
  const atual = pav(d, "e1-P2").ambientes[0];
  d = aplicarAcaoSaida(d, { type: "IMPORT_AMBIENTES_SE", atualizacoes: [{ pavimentoId: "e1-P2", ambientes: [{ ...atual, nome: "Sala renomeada" }] }] });
  const depois = pav(d, "e1-P2").ambientes[0];
  assert.deepEqual([depois.nome, depois.grupoId, depois.acessoId], ["Sala renomeada", atual.grupoId, "a1"]);
});

test("ação desconhecida (de outra medida, vinda do canal) devolve os dados sem quebrar", () => {
  const d = garantirFluxoMigrado(legado());
  assert.equal(aplicarAcaoSaida(d, { type: "SET_ALGUMA_OUTRA_COISA" }), d);
});
