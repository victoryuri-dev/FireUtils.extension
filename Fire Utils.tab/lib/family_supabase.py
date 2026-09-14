# -*- coding: utf-8 -*-
"""
family_supabase.py — Fire Utils · lib/
Garante que uma família específica do catálogo do Supabase — o mesmo
acervo que o Carregador de Famílias da dockpane usa (ver
family_webview_bridge.py) — está carregada e ativada no documento ativo,
baixando-a sob demanda quando ainda não estiver no projeto.

Ao contrário da dockpane, que roda dentro do WebView2 com o usuário
logado (e por isso pede ao supabase-js pra assinar a Signed URL do .rfa
com a sessão dele), os pushbuttons diretos da ribbon (Abrigo, Acionador
Manual, Avisador Sonoro e Visual) rodam fora do WebView2, sem sessão de
usuário — a Signed URL aqui é criada direto por este módulo, via HTTP,
com a mesma anon key pública já usada em sync.py (a política de RLS do
bucket privado revit-families precisa liberar o "sign" pro role anon
pra isso funcionar).

Uso:
    from family_supabase import garantir_familia_supabase

    simbolo, erro = garantir_familia_supabase(doc, u"Abrigo de Mangueira para Hidrante")
    if erro:
        forms.alert(erro, ...)
        script.exit()
"""

import os

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import Transaction, Family, FilteredElementCollector

from sync import SUPABASE_URL, _get_json, _post_json
from family_loader import FamilyEntry, carregar_familias
from family_cache import baixar_temporario, remover_temporario
from family_error_utils import texto_erro

_CATALOG_URL      = SUPABASE_URL + u"/storage/v1/object/public/plugin-assets/catalog.json"
_BUCKET_FAMILIAS  = u"revit-families"
_SIGNED_URL_TTL_S = 60

# Cache em memória do catalog.json — evita rebaixar o mesmo arquivo pra
# cada família garantida dentro da mesma execução (ex.: inserir_alarmes
# garante acionador + avisador em sequência).
_catalogo_cache = None


def _catalogo():
    global _catalogo_cache
    if _catalogo_cache is None:
        catalogo, erro = _get_json(_CATALOG_URL)
        if erro:
            raise IOError(erro)
        _catalogo_cache = catalogo
    return _catalogo_cache


def _entrada_catalogo(nome_familia=None, slug=None):
    """Localiza uma entrada do catalog.json por nome de exibição exato
    (`nome_familia`) ou pelo slug do arquivo .rfa — o nome do storage_key
    sem a pasta de categoria nem a extensão (`slug`), útil quando quem
    chama conhece a convenção de nome do arquivo mas não o nome de
    exibição exato cadastrado no catálogo (ex.: as placas de sinalização,
    ver signage_family.py)."""
    for familia in (_catalogo() or {}).get(u"families") or []:
        if nome_familia is not None and familia.get(u"name") == nome_familia:
            return familia
        if slug is not None:
            storage_key = familia.get(u"storage_key") or u""
            if os.path.splitext(os.path.basename(storage_key))[0] == slug:
                return familia
    return None


def _criar_signed_url(storage_key):
    """Assina `storage_key` no bucket privado revit-families com a anon
    key — mesma chamada que o supabase-js faz por trás de
    createSignedUrl(), só que direto via HTTP (ver sync._post_json)."""
    url = u"{}/storage/v1/object/sign/{}/{}".format(
        SUPABASE_URL, _BUCKET_FAMILIAS, storage_key)
    resposta, erro = _post_json(url, {u"expiresIn": _SIGNED_URL_TTL_S})
    if erro:
        raise IOError(erro)
    caminho_assinado = (resposta or {}).get(u"signedURL") or (resposta or {}).get(u"signedUrl")
    if not caminho_assinado:
        raise IOError(u"Resposta de assinatura do Supabase sem 'signedURL'.")
    return u"{}/storage/v1{}".format(SUPABASE_URL, caminho_assinado)


def _baixar_e_carregar(doc, nome_familia, entrada_catalogo):
    storage_key = entrada_catalogo.get(u"storage_key")
    try:
        signed_url = _criar_signed_url(storage_key)
        caminho_temp = baixar_temporario(storage_key, signed_url, entrada_catalogo.get(u"sha256"))
    except Exception as ex:
        return None, u"Falha ao baixar '{}' do Supabase: {}".format(nome_familia, texto_erro(ex))

    entrada_loader = FamilyEntry(
        name=nome_familia,
        category=entrada_catalogo.get(u"category_id") or u"Geral",
        path=caminho_temp,
        nome_revit=os.path.splitext(os.path.basename(storage_key))[0],
    )
    try:
        _carregadas, _ja_existentes, erros, familias_por_nome = carregar_familias(
            doc, [entrada_loader])
    finally:
        remover_temporario(caminho_temp)

    if erros:
        _nome, msg = erros[0]
        return None, u"Erro ao carregar família:\n{}".format(msg)

    return familias_por_nome.get(nome_familia), None


def _familia_no_documento(doc, nome_familia):
    return next(
        (f for f in FilteredElementCollector(doc).OfClass(Family).ToElements()
         if f.Name == nome_familia),
        None
    )


def _ativar_simbolo(doc, familia, nome_familia):
    if familia is None:
        return None, (u"Não foi possível localizar '{}' no projeto após o "
                      u"carregamento.".format(nome_familia))

    simbolo = next(
        (doc.GetElement(sid) for sid in familia.GetFamilySymbolIds()),
        None
    )
    if simbolo is None:
        return None, u"Família '{}' carregada, mas nenhum tipo encontrado.".format(nome_familia)

    if not simbolo.IsActive:
        with Transaction(doc, u"FireUtils - Ativar Símbolo {}".format(nome_familia)) as t:
            t.Start()
            simbolo.Activate()
            t.Commit()

    return simbolo, None


def garantir_familia_supabase(doc, nome_familia):
    """
    Garante que a família `nome_familia` (nome de exibição, ex.: 'Abrigo
    de Mangueira para Hidrante') está carregada e ativada em `doc`.

    Se a família já estiver no projeto, não faz nenhuma chamada de rede.
    Senão, busca o catalog.json do Supabase, localiza a entrada por nome,
    baixa o .rfa do bucket privado (Signed URL) pra um arquivo temporário
    e carrega no documento via family_loader.carregar_familias — a MESMA
    função que a dockpane usa (ver family_webview_bridge.py) — apagando o
    temporário em seguida.

    Retorno: (FamilySymbol, erro_msg) — erro_msg é None em caso de sucesso.
    """
    familia = _familia_no_documento(doc, nome_familia)

    if familia is None:
        try:
            entrada = _entrada_catalogo(nome_familia=nome_familia)
        except Exception as ex:
            return None, (u"Falha ao consultar o catálogo de famílias no "
                          u"Supabase: {}".format(texto_erro(ex)))
        if entrada is None:
            return None, (u"Família '{}' não encontrada no catálogo do "
                          u"Supabase.".format(nome_familia))

        familia, erro = _baixar_e_carregar(doc, nome_familia, entrada)
        if erro:
            return None, erro

    return _ativar_simbolo(doc, familia, nome_familia)


def garantir_familia_supabase_por_slug(doc, slug):
    """
    Como garantir_familia_supabase, mas localizando a entrada do catálogo
    pelo slug do arquivo .rfa (ex.: 'placa-de-sinalizacao-e8-8m') em vez
    do nome de exibição — útil quando quem chama conhece a convenção de
    nome do arquivo (ver signage_family.py) mas não o nome de exibição
    exato cadastrado no catálogo. O nome de exibição real (`entrada.name`)
    é usado tanto pra checar se a família já está no projeto quanto,
    depois de carregada, pra renomeá-la (ver family_loader.carregar_familias).

    Retorno: (FamilySymbol, nome_exibicao, erro_msg).
    """
    try:
        entrada = _entrada_catalogo(slug=slug)
    except Exception as ex:
        return None, None, (u"Falha ao consultar o catálogo de famílias no "
                            u"Supabase: {}".format(texto_erro(ex)))
    if entrada is None:
        return None, None, (u"Família '{}' não encontrada no catálogo do "
                            u"Supabase.".format(slug))

    nome_familia = entrada.get(u"name") or slug
    familia = _familia_no_documento(doc, nome_familia)

    if familia is None:
        familia, erro = _baixar_e_carregar(doc, nome_familia, entrada)
        if erro:
            return None, nome_familia, erro

    simbolo, erro = _ativar_simbolo(doc, familia, nome_familia)
    return simbolo, nome_familia, erro
