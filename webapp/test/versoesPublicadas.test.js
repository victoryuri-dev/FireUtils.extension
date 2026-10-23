import { test } from "node:test";
import assert from "node:assert/strict";
import { mesclarNotas, nomesDosArquivos, notasDasVersoes } from "../src/lib/versoesPublicadas.js";

const instalador = { versao: "3.1.2", tipo: "instalador", arquivo: "FireUtils-Setup-3.1.2.exe", base_minima: null, titulo: "Autoatualização", notas: [{ tipo: "novo", texto: "A" }], publicada_em: "2026-10-23T02:00:00Z" };
const pacote = { versao: "3.1.3", tipo: "pacote", arquivo: "FireUtils-Pacote-3.1.3-base-3.1.2.zip", base_minima: "3.1.2", titulo: "", notas: [{ tipo: "correcao", texto: "Falhas de conexão" }], publicada_em: "2026-10-23T14:13:00Z" };

test("nomesDosArquivos inclui o arquivo e o que fica ao lado (.sha256 / .sig)", () => {
  assert.deepEqual(nomesDosArquivos([instalador, pacote]), [
    "FireUtils-Setup-3.1.2.exe", "FireUtils-Setup-3.1.2.exe.sha256",
    "FireUtils-Pacote-3.1.3-base-3.1.2.zip", "FireUtils-Pacote-3.1.3-base-3.1.2.zip.sig",
  ]);
  assert.deepEqual(nomesDosArquivos([{ versao: "1" }]), []);
});

test("notasDasVersoes converte para o formato de PATCH_NOTES, com a data no horário do Brasil", () => {
  const [a, b] = notasDasVersoes([instalador, pacote]);
  assert.deepEqual(a, { versao: "3.1.2", data: "2026-10-22", titulo: "Autoatualização", itens: [{ tipo: "novo", texto: "A" }] });
  assert.deepEqual(b, { versao: "3.1.3", data: "2026-10-23", titulo: "", itens: [{ tipo: "correcao", texto: "Falhas de conexão" }] });
});

test("instalador e pacote da mesma versão viram uma nota, sem repetir itens", () => {
  const a = { ...instalador, versao: "3.2.0", titulo: "", notas: [{ tipo: "novo", texto: "X" }] };
  const b = { ...pacote, versao: "3.2.0", titulo: "Título", notas: [{ tipo: "novo", texto: "X" }, { tipo: "melhoria", texto: "Y" }] };
  const notas = notasDasVersoes([a, b]);
  assert.equal(notas.length, 1);
  assert.equal(notas[0].titulo, "Título");
  assert.deepEqual(notas[0].itens, [{ tipo: "novo", texto: "X" }, { tipo: "melhoria", texto: "Y" }]);
});

test("versão sem título e sem itens não gera nota; itens vazios são descartados", () => {
  assert.deepEqual(notasDasVersoes([{ ...instalador, titulo: "", notas: [] }]), []);
  assert.deepEqual(notasDasVersoes([{ ...instalador, titulo: "", notas: [{ tipo: "novo", texto: "  " }] }]), []);
  assert.deepEqual(notasDasVersoes([{ ...instalador, notas: null }]).map((n) => n.itens), [[]]);
});

test("mesclarNotas: o painel prevalece, as locais cobrem o que falta", () => {
  const painel = [{ versao: "3.1.3", itens: [] }];
  const locais = [{ versao: "3.1.3", itens: [{ tipo: "novo", texto: "velha" }] }, { versao: "3.1.2", itens: [] }];
  assert.deepEqual(mesclarNotas(painel, locais).map((n) => n.versao), ["3.1.3", "3.1.2"]);
  assert.deepEqual(mesclarNotas(painel, locais)[0].itens, []);
});
