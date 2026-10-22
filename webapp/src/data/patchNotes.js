/**
 * Notas de atualização do plugin, mostradas na página "Atualizações" da dockpane
 * quando há versão nova. A interface é publicada na hora (Vercel), então ESTE
 * arquivo pode ser editado e publicado antes ou depois do plugin: a página só
 * lista as versões maiores que a instalada e até a que está disponível.
 *
 * Como escrever uma nota (uma entrada por versão, a mais nova primeiro):
 *   versao  "3.2.0" — igual ao nome do instalador/pacote publicado
 *   data    "AAAA-MM-DD"
 *   titulo  frase curta do que a versão traz (opcional)
 *   itens   [{ tipo: "novo" | "melhoria" | "correcao", texto }]
 */
export const PATCH_NOTES = [
  {
    versao: "3.2.0",
    data: "2026-10-23",
    titulo: "Mais ferramentas na dockpane e atualização sem instalador",
    itens: [
      { tipo: "novo", texto: "Mapear trechos agora é feito direto na dockpane (Sistema de Hidrantes)." },
      { tipo: "novo", texto: "Ferramentas de ocupação e população na página Saídas de Emergência: identificar por ambiente, por nível, todos e sincronizar." },
      { tipo: "novo", texto: "Atualizações rápidas, só de código, sem precisar rodar o instalador." },
      { tipo: "melhoria", texto: "Instalador com visual novo, tema escuro e opção de desinstalar." },
      { tipo: "melhoria", texto: "Biblioteca de famílias: filtro por categoria recolhido por padrão." },
    ],
  },
];
