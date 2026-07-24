# Biblioteca de Famílias — Fire Utils

Pasta única lida automaticamente pelo **Carregador de Famílias** (aba Fire
Utils → painel Biblioteca). Todas as famílias .rfa da extensão ficam aqui —
inclusive as usadas por outras ferramentas (inserção de hidrante, abrigo,
alarme), que também apontam para dentro desta pasta.

## Como adicionar novas famílias

1. Crie uma subpasta com o nome da categoria (ex.: `Extintores`,
   `Sinalização`, `Sprinklers`), se ela ainda não existir.
2. Copie o(s) arquivo(s) `.rfa` para dentro dessa subpasta.
3. Abra (ou reabra) o Carregador de Famílias no Revit, ou clique em
   "Atualizar pasta" — a lista é gerada em tempo real a partir do conteúdo
   desta pasta, nenhuma alteração de código é necessária.

Arquivos `.rfa` soltos diretamente em `family_library/` (fora de qualquer
subpasta) aparecem na categoria genérica **"Geral"**.

## Subpastas em uso

- `Hidrantes/` → usada pelo Carregador de Famílias **e** por
  `lib/hydrant_family.py` / `lib/shelter_family.py` (inserção de
  hidrante/válvula/abrigo). Não renomeie os arquivos aqui.
- `Alarmes e Detecção/` → usada pelo Carregador de Famílias **e** por
  `lib/alarm_family.py` (inserção de alarme). Não renomeie os arquivos aqui.
- `Extintor/` → apenas para o Carregador de Famílias.
