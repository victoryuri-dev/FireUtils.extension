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
    versao: "3.1.3",
    data: "2026-10-30",
    titulo: "As funções de ocupação agora estão dentro do Painel.",
    itens: [
      { tipo: "Saídas de Emergência", texto: "Por questões de segurança e melhor sincronização Revit-Servidor os botões Identificar por ambiente, Identificar por nível, Identificar todos sem ocupação e Sincronizar ambientes  foram alocados na DockPane." },
      { tipo: "Atualização sem Instalador", texto: "As atualizações a partir dessa versão serão feitas dentro do próprio painel, dispensando a necessidade de baixar novos instaladores." },
    ],
  },
];
