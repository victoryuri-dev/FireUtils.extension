# -*- coding: utf-8 -*-
"""
app.py — Fire Utils · Servidor Flask local (CPython)
Executa em http://127.0.0.1:5000

Rotas:
  GET  /api/status            — health check
  POST /api/hidrantes         — recebe cache de hidrantes (JSON)
  GET  /api/hidrantes         — retorna cache de hidrantes
  POST /api/saidas            — recebe cache de saídas (JSON)
  GET  /api/saidas            — retorna cache de saídas
  GET  /memorial              — gera e exibe memorial HTML completo

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
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---- armazenamento em memória ------------------------------------------------
_store = {
    "hidrantes": None,   # dict com o payload
    "saidas":    None,
}


# =============================================================================
# /api/status
# =============================================================================
@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "ok":        True,
        "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "hidrantes": _store["hidrantes"] is not None,
        "saidas":    _store["saidas"]    is not None,
    })


# =============================================================================
# /api/hidrantes
# =============================================================================
@app.route("/api/hidrantes", methods=["POST"])
def post_hidrantes():
    try:
        _store["hidrantes"] = request.get_json(force=True)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 400


@app.route("/api/hidrantes", methods=["GET"])
def get_hidrantes():
    if _store["hidrantes"] is None:
        return jsonify({"ok": False, "erro": "sem dados"}), 404
    return jsonify(_store["hidrantes"])


# =============================================================================
# /api/saidas
# =============================================================================
@app.route("/api/saidas", methods=["POST"])
def post_saidas():
    try:
        _store["saidas"] = request.get_json(force=True)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 400


@app.route("/api/saidas", methods=["GET"])
def get_saidas():
    if _store["saidas"] is None:
        return jsonify({"ok": False, "erro": "sem dados"}), 404
    return jsonify(_store["saidas"])


# =============================================================================
# /memorial — gera HTML usando memorial.geral e entrega ao browser
# =============================================================================
@app.route("/memorial", methods=["GET"])
def memorial():
    try:
        from memorial.geral import build_html_geral

        cache_hid    = _store["hidrantes"]
        cache_saidas = _store["saidas"]

        if not cache_hid and not cache_saidas:
            return Response(
                u"<h2>Nenhum dado disponível.</h2>"
                u"<p>Execute <strong>Dimensionar Hidrantes</strong> e/ou "
                u"<strong>Dimensionar Saídas</strong> no Revit para atualizar o memorial.</p>",
                status=200,
                mimetype="text/html; charset=utf-8",
            )

        html = build_html_geral(
            cache_hid    = cache_hid,
            cache_saidas = cache_saidas,
        )
        return Response(html, status=200, mimetype="text/html; charset=utf-8")

    except Exception:
        import traceback
        tb = traceback.format_exc()
        return Response(
            u"<h2>Erro ao gerar memorial:</h2><pre>{}</pre>".format(tb),
            status=500,
            mimetype="text/html; charset=utf-8",
        )


# =============================================================================
# /api/dados — retorna ambos os caches em um só JSON (útil para debug/sync)
# =============================================================================
@app.route("/api/dados", methods=["GET"])
def dados():
    return jsonify({
        "hidrantes": _store["hidrantes"],
        "saidas":    _store["saidas"],
    })


# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("FIREUTILS_PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
