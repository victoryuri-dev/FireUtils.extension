# -*- coding: utf-8 -*-
"""
sync.py — Fire Utils · lib/
Ponte HTTP com o site (Supabase) nos dois sentidos:
  - enviar(): push best-effort do que o plugin calculou (extintores,
    hidrantes, saidas_emergencia) pra Edge Function `revit-sync`.
  - buscar(): pull sob demanda de dados cadastrados no site (estruturas,
    ocupação/área por pavimento) via Edge Function `site-sync`.

Identificação por projetoId (não mais por token): o vínculo agora é
escolhido direto no Dashboard da dockpane, consultando o Supabase com a
sessão do usuário logado (RLS) — não existe mais um token secreto colado
manualmente. `projetoId` é o uuid interno do projeto na tabela `projetos`
do Supabase (ver webapp/src/lib/projectData.js e webapp/README.md).

Config de vínculo (projetoId + estrutura escolhida) fica na chave 'sync' do
próprio firedata.json — mesmo padrão ler-arquivo-inteiro → mesclar chave
→ regravar que extintores/calc.py, hidrantes/calc.py e saidas/calc.py
já usam.

Uso:
    from sync import enviar, buscar, config_sync, salvar_config_sync
    enviar(u"extintores", payload, projeto_dir)
    resultado, erro = buscar(u"listar_estruturas", projeto_dir)
"""

import io
import os
import json

_SYNC_URL   = u"https://lngvagifcukglgdjildw.supabase.co/functions/v1/revit-sync"
_BUSCA_URL  = u"https://lngvagifcukglgdjildw.supabase.co/functions/v1/site-sync"
_ANON_KEY   = u"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxuZ3ZhZ2lmY3VrZ2xnZGppbGR3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDUwNzksImV4cCI6MjEwMjMyMTA3OX0.hApUcA5wunyv21JdL8XAVVD1TnGU9oRvyew1uCIlZRw"
_CACHE_NOME = u"firedata.json"
_MEDIDAS_VALIDAS = (u"extintores", u"hidrantes", u"saidas_emergencia")


def _cache_path(projeto_dir):
    return os.path.join(projeto_dir, _CACHE_NOME)


def config_sync(projeto_dir):
    """Retorna o dict salvo na chave 'sync' do firedata.json
    (projetoId, estruturaId, estruturaNome, projetoNome), ou {} se não
    houver nada."""
    try:
        with io.open(_cache_path(projeto_dir), u"r", encoding=u"utf-8") as f:
            dados = json.loads(f.read())
        return dados.get(u"sync") or {}
    except Exception:
        return {}


def salvar_config_sync(projeto_dir, **campos):
    """Mescla `campos` (projetoId, estruturaId, estruturaNome, ...) na chave
    'sync' do firedata.json, preservando as demais chaves do arquivo —
    mesmo padrão ler-arquivo-inteiro→mesclar→regravar dos outros
    salvar_cache* deste plugin."""
    path = _cache_path(projeto_dir)
    try:
        with io.open(path, u"r", encoding=u"utf-8") as f:
            dados = json.loads(f.read())
    except Exception:
        dados = {}
    sync = dados.get(u"sync") or {}
    sync.update(campos)
    dados[u"sync"] = sync
    with io.open(path, u"w", encoding=u"utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _post_json(url, corpo):
    """POST JSON com os headers do Supabase. Retorna (resultado, erro) —
    `erro` é None em caso de sucesso, senão uma mensagem legível (extraída
    do corpo de erro `{"error": "..."}` quando o servidor manda um)."""
    import clr
    clr.AddReference(u"System.Net")
    from System.Net import WebRequest, WebException
    from System.Text import Encoding
    from System.IO import StreamReader

    # Força TLS1.2 em .NET Framework antigo, que não negocia isso por padrão
    # (o Supabase exige TLS1.2+). Em runtimes mais novos (.NET Core/5+, usado
    # por versões recentes do Revit) ServicePointManager nem existe mais —
    # TLS1.2+ já é o padrão do sistema nesse caso, então só ignoramos.
    try:
        from System.Net import ServicePointManager, SecurityProtocolType
        ServicePointManager.SecurityProtocol = (
            ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
        )
    except Exception:
        pass

    dados_bytes = Encoding.UTF8.GetBytes(json.dumps(corpo, ensure_ascii=False))

    req = WebRequest.Create(url)
    req.Method = u"POST"
    req.ContentType = u"application/json"
    req.Timeout = 5000
    req.Headers.Add(u"Authorization", u"Bearer " + _ANON_KEY)
    req.Headers.Add(u"apikey", _ANON_KEY)
    req.ContentLength = dados_bytes.Length

    try:
        stream = req.GetRequestStream()
        stream.Write(dados_bytes, 0, dados_bytes.Length)
        stream.Close()

        resp = req.GetResponse()
        leitor = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
        texto = leitor.ReadToEnd()
        resp.Close()
    except WebException as werr:
        if werr.Response:
            leitor_erro = StreamReader(werr.Response.GetResponseStream(), Encoding.UTF8)
            texto_erro = leitor_erro.ReadToEnd()
            werr.Response.Close()
            try:
                return None, (json.loads(texto_erro).get(u"error") or texto_erro)
            except Exception:
                return None, texto_erro or u"{}".format(werr)
        return None, u"Falha de rede: {}".format(werr)

    try:
        return json.loads(texto), None
    except Exception:
        return None, u"Resposta inválida do servidor."


def enviar(medida, payload, projeto_dir, estruturaId=None):
    """Envia `payload` pra Edge Function revit-sync, best-effort.

    `estruturaId` é obrigatório pro site pra 'extintores' e
    'saidas_emergencia' (o site resolve a estrutura por esse id, não mais
    por nome) — passe o valor salvo em config_sync(projeto_dir). Pra
    'hidrantes' não deve ser passado: é a única medida que fica geral,
    compartilhada entre todas as estruturas do projeto.

    Nunca lança exceção nem retorna nada útil pro chamador — qualquer
    falha (sem projeto vinculado, sem rede, timeout, erro do servidor,
    estruturaId desatualizado) é silenciosamente ignorada, porque o
    firedata.json local já foi gravado antes desta chamada e continua
    sendo a fonte de verdade offline.
    """
    if medida not in _MEDIDAS_VALIDAS:
        return
    projeto_id = config_sync(projeto_dir).get(u"projetoId")
    if not projeto_id:
        return
    corpo = {u"projetoId": projeto_id, u"medida": medida, u"payload": payload}
    if estruturaId:
        corpo[u"estruturaId"] = estruturaId
    try:
        _post_json(_SYNC_URL, corpo)
    except Exception:
        pass


def buscar(acao, projeto_dir, **params):
    """Consulta a Edge Function site-sync (ex.: 'listar_estruturas',
    'ocupacao_area'). Retorna (resultado, erro) — 'erro' é None em caso de
    sucesso, senão uma mensagem pronta pra mostrar ao usuário. Ao contrário
    de `enviar`, o resultado importa pro chamador, então os erros não são
    engolidos — só nunca viram exceção não tratada.
    """
    projeto_id = config_sync(projeto_dir).get(u"projetoId")
    if not projeto_id:
        return None, u"Nenhum projeto vinculado a este arquivo Revit."
    corpo = {u"projetoId": projeto_id, u"acao": acao}
    corpo.update(params)
    try:
        return _post_json(_BUSCA_URL, corpo)
    except Exception as ex:
        return None, u"Falha ao consultar o site: {}".format(ex)
