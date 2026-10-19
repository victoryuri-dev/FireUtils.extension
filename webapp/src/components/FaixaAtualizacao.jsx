/**
 * Faixa de "versão nova disponível" dos scripts instalados no Revit.
 *
 * Só o plugin dentro do Revit precisa de atualização — esta interface vem
 * do servidor e já está sempre na última versão. Quem responde o que está
 * instalado é o Python (ver atualizacao.py); aqui só se mostra e se pede a
 * confirmação, porque atualizar troca arquivos no disco do usuário e isso
 * nunca deve acontecer sem ele saber.
 *
 * `estado` conduz a faixa: "disponivel" (pergunta), "aplicando" (baixando e
 * trocando — sem botão nenhum, para ninguém tentar fechar o Revit no meio),
 * "concluida" (pedir o reinício) e "erro".
 */
export default function FaixaAtualizacao({ situacao, onAtualizar, onDispensar }) {
  if (!situacao) return null;

  const { instalada, disponivel, notas, estado, erro } = situacao;

  if (estado === "aplicando") {
    return (
      <div className="faixa-atualizacao">
        <div className="faixa-atualizacao-titulo">
          <span className="loading-spinner" />
          <strong>Atualizando o Fire Utils…</strong>
        </div>
        <p>Não feche o Revit até terminar.</p>
      </div>
    );
  }

  if (estado === "concluida") {
    return (
      <div className="faixa-atualizacao">
        <div className="faixa-atualizacao-titulo">
          <strong>Versão {disponivel} instalada</strong>
        </div>
        {/* Os módulos desta sessão já estão carregados na memória do Revit:
            os arquivos novos só passam a valer na próxima abertura. */}
        <p>Reinicie o Revit para começar a usar.</p>
        <div className="faixa-atualizacao-acoes">
          <button type="button" className="faixa-atualizacao-secundario" onClick={onDispensar}>
            Entendi
          </button>
        </div>
      </div>
    );
  }

  if (estado === "erro") {
    return (
      <div className="faixa-atualizacao">
        <div className="faixa-atualizacao-titulo">
          <strong>Não foi possível atualizar</strong>
        </div>
        <p>{erro || "Tente de novo mais tarde."}</p>
        <div className="faixa-atualizacao-acoes">
          <button type="button" className="faixa-atualizacao-botao" onClick={onAtualizar}>
            Tentar de novo
          </button>
          <button type="button" className="faixa-atualizacao-secundario" onClick={onDispensar}>
            Agora não
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="faixa-atualizacao">
      <div className="faixa-atualizacao-titulo">
        <strong>Fire Utils {disponivel} disponível</strong>
      </div>
      <p>
        {instalada ? `Você está na versão ${instalada}.` : "Atualização dos scripts do Revit."}
      </p>
      {notas && <p className="faixa-atualizacao-notas">{notas}</p>}
      <div className="faixa-atualizacao-acoes">
        <button type="button" className="faixa-atualizacao-botao" onClick={onAtualizar}>
          Atualizar
        </button>
        <button type="button" className="faixa-atualizacao-secundario" onClick={onDispensar}>
          Agora não
        </button>
      </div>
    </div>
  );
}
