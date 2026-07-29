# -*- coding: utf-8 -*-
"""
app.py — Fire Utils · Servidor Flask local (CPython)
Executa em http://127.0.0.1:5000

Rotas:
  GET  /                      — redireciona para /login
  GET  /login /dashboard /memorial /project /medida — páginas do site
  GET  /site/<arquivo>        — assets estáticos
  GET  /api/status            — health check
  POST /api/hidrantes         — recebe payload de hidrantes (JSON)
  GET  /api/hidrantes         — retorna payload de hidrantes
  POST /api/se_import         — recebe se_import compacto de saídas (JSON)
  GET  /api/se_import         — retorna se_import
  GET  /api/dados             — retorna hidrantes + se_import juntos
  GET  /api/recarregar        — lê firedata.json e devolve saídas computadas ao browser

Inicialização:
  python app.py               — inicia na porta 5000 (debug=False)
"""

import os
import sys
import json
import datetime

# Adiciona lib/ ao path (este arquivo vive em lib/server/app.py)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR  = os.path.dirname(_THIS_DIR)
_SITE_DIR = os.path.join(_THIS_DIR, "site")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from flask import Flask, request, jsonify, Response, send_from_directory, redirect

app = Flask(__name__)

# ---- armazenamento em memória ------------------------------------------------
_store = {
    "hidrantes":     None,
    "se_import":     None,   # formato compacto de saídas de emergência
    "dados_projeto": None,
}

_TEMP = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~")
_CACHE_DADOS  = "firedata.json"
_LAST_PROJ    = os.path.join(_TEMP, "fireutils_last_project.txt")


def _salvar_ultimo_projeto(projeto_dir):
    try:
        with open(_LAST_PROJ, "w", encoding="utf-8") as f:
            f.write(projeto_dir)
    except Exception:
        pass


def _ler_ultimo_projeto():
    try:
        if os.path.exists(_LAST_PROJ):
            with open(_LAST_PROJ, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return None


def _json_safe(obj):
    """Converte recursivamente tipos não-serializáveis (ex: Fraction) para float."""
    try:
        from fractions import Fraction
        if isinstance(obj, Fraction):
            return float(obj)
    except Exception:
        pass
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(i) for i in obj]
    return obj


def _computar_saidas_de_se_import(se_import, dados_projeto=None):
    """
    Computa o payload completo de saídas (compatível com renderSaidas() do JS)
    a partir do formato compacto se_import.
    """
    try:
        uf = se_import.get("uf")
        if not uf:
            return None
        from estados import get_estado
        estado = get_estado(uf)
        if not estado:
            return None
        from saidas.calc import calcular_saidas_from_se_import
        res, rooms_data, nome_terreo = calcular_saidas_from_se_import(se_import, estado)

        # Reconstrói config_distancias; ocupacao_principal vem de dados_projeto
        ocup_principal = (dados_projeto or {}).get("ocupacao_principal")
        config_distancias = {
            "ocupacao_principal": ocup_principal,
            "saida_unica": se_import.get("saida_unica", False),
            "chuveiro":    se_import.get("temChuveiros", False),
            "deteccao":    se_import.get("temDeteccao",  False),
        } if ocup_principal else None

        return {
            "resultados":        res,
            "rooms_data":        rooms_data,
            "nome_terreo":       nome_terreo,
            "timestamp":         se_import.get("_timestamp", ""),
            "sigla_estado":      uf,
            "_estado":           _json_safe(estado),
            "config_distancias": config_distancias,
        }
    except Exception:
        return None


def _carregar_caches_do_disco():
    """Carrega o cache unificado salvo pelo plugin na pasta do último projeto usado."""
    projeto_dir = _ler_ultimo_projeto() or _TEMP
    path = os.path.join(projeto_dir, _CACHE_DADOS)
    if not os.path.exists(path):
        path = os.path.join(_TEMP, _CACHE_DADOS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                arquivo = json.load(f)
            if "hidrantes" in arquivo:
                _store["hidrantes"] = arquivo["hidrantes"]
            raw = arquivo.get("saidas_emergencia") or arquivo.get("se_import")
            if raw:
                _store["se_import"] = raw
            if "dados_projeto" in arquivo:
                _store["dados_projeto"] = arquivo["dados_projeto"]
        except Exception:
            pass


# =============================================================================
# /api/status
# =============================================================================
@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "ok":           True,
        "timestamp":    datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "hidrantes":    _store["hidrantes"]    is not None,
        "se_import":    _store["se_import"]    is not None,
        "dados_projeto": _store["dados_projeto"] is not None,
    })


# =============================================================================
# /api/hidrantes
# =============================================================================
@app.route("/api/hidrantes", methods=["POST"])
def post_hidrantes():
    try:
        data = request.get_json(force=True)
        _store["hidrantes"] = data
        proj = data.get("_projeto_dir")
        if proj:
            _salvar_ultimo_projeto(proj)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 400


@app.route("/api/hidrantes", methods=["GET"])
def get_hidrantes():
    if _store["hidrantes"] is None:
        return jsonify({"ok": False, "erro": "sem dados"}), 404
    return jsonify(_store["hidrantes"])


# =============================================================================
# /api/se_import
# =============================================================================
@app.route("/api/se_import", methods=["POST"])
def post_se_import():
    try:
        data = request.get_json(force=True)
        proj = data.get("_projeto_dir")
        if proj:
            _salvar_ultimo_projeto(proj)
        _store["se_import"] = data
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 400


@app.route("/api/se_import", methods=["GET"])
def get_se_import():
    if _store["se_import"] is None:
        return jsonify({"ok": False, "erro": "sem dados"}), 404
    return jsonify(_store["se_import"])


# =============================================================================
# Páginas do site
# =============================================================================
@app.route("/")
def root():
    return redirect("/login")


@app.route("/login")
def login():
    return send_from_directory(_SITE_DIR, "login.html")


@app.route("/dashboard")
def dashboard():
    return send_from_directory(_SITE_DIR, "dashboard.html")


@app.route("/memorial")
def memorial():
    return send_from_directory(_SITE_DIR, "memorial.html")


@app.route("/project")
def project():
    return send_from_directory(_SITE_DIR, "project.html")


@app.route("/medida")
def medida():
    return send_from_directory(_SITE_DIR, "medida.html")


@app.route("/site/<path:filename>")
def site_static(filename):
    return send_from_directory(_SITE_DIR, filename)


# =============================================================================
# /api/recarregar — lê firedata.json do disco e devolve ao browser
# =============================================================================
@app.route("/api/recarregar", methods=["GET"])
def recarregar():
    """
    Lê o firedata.json da pasta do projeto e retorna o conteúdo enriquecido.
    Parâmetro opcional: ?dir=C%3A%5C...  (pasta do projeto — URL-encoded).
    Se não fornecido, usa o último projeto registrado em _LAST_PROJ.
    """
    projeto_dir = request.args.get("dir") or _ler_ultimo_projeto() or _TEMP

    # Tenta na pasta fornecida, depois no último projeto registrado, depois em %TEMP%
    candidatos = [projeto_dir]
    last = _ler_ultimo_projeto()
    if last and last != projeto_dir:
        candidatos.append(last)
    candidatos.append(_TEMP)

    path = None
    for d in candidatos:
        p = os.path.join(d, _CACHE_DADOS)
        if os.path.exists(p):
            path = p
            break

    if not path:
        return jsonify({
            "ok": False,
            "erro": u"Arquivo '{}' não encontrado. Execute Dimensionar no Revit primeiro.".format(_CACHE_DADOS)
        }), 404

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Converte saidas_emergencia → saidas computada (formato esperado pelo JS renderSaidas)
        _se = data.get("saidas_emergencia") or data.get("se_import")
        if _se:
            dados_proj = data.get("dados_projeto")
            saidas_computada = _computar_saidas_de_se_import(_se, dados_proj)
            if saidas_computada:
                data["saidas"] = saidas_computada

        return jsonify({"ok": True, "data": data, "path": path})

    except Exception as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 500


# =============================================================================
# /api/dados — retorna ambos os caches em um só JSON (útil para debug/sync)
# =============================================================================
@app.route("/api/dados", methods=["GET"])
def dados():
    return jsonify({
        "dados_projeto": _store["dados_projeto"],
        "hidrantes":     _store["hidrantes"],
        "se_import":     _store["se_import"],
    })


# =============================================================================
# /api/shutdown — encerra o servidor limpo
# =============================================================================
@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    import threading
    def _stop():
        import time
        time.sleep(0.3)   # dá tempo da resposta ser enviada antes de sair
        os._exit(0)
    threading.Thread(target=_stop, daemon=True).start()
    return jsonify({"ok": True, "msg": "Servidor encerrando..."})


# =============================================================================
# /api/reload — descarta módulos em memória para forçar reimport na próxima
#               requisição a /memorial (útil durante desenvolvimento)
# =============================================================================
@app.route("/api/reload", methods=["POST"])
def reload_modules():
    prefixos = ("memorial", "estados", "saidas", "hidrantes")
    cleared = []
    for key in list(sys.modules.keys()):
        if key.startswith(prefixos):
            del sys.modules[key]
            cleared.append(key)
    return jsonify({"ok": True, "cleared": cleared})


# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    _carregar_caches_do_disco()
    port = int(os.environ.get("FIREUTILS_PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
