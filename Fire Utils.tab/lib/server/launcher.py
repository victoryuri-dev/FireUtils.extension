# -*- coding: utf-8 -*-
"""
launcher.py — Fire Utils · Gerenciador do servidor local (IronPython)

Usa System.Diagnostics.Process para iniciar o servidor Flask (CPython)
como processo filho sem janela de console.

API pública:
    iniciar_servidor()   -> bool   # inicia se não estiver rodando
    parar_servidor()                # mata o processo
    servidor_ativo()     -> bool   # testa /api/status via HTTP
    url_servidor()       -> str    # "http://127.0.0.1:5000"
"""

import os
import time

# .NET assemblies (disponíveis em IronPython dentro do Revit)
import clr
clr.AddReference("System")
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import Path

# ---- constantes ---------------------------------------------------------------
_PORT    = 5000
_HOST    = u"127.0.0.1"
_BASE    = u"http://{}:{}".format(_HOST, _PORT)
_APP_PY  = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"app.py")

# Processo filho armazenado para poder encerrar depois
_proc = None


# ==============================================================================
def url_servidor():
    """Retorna a URL base do servidor."""
    return _BASE


# ==============================================================================
def servidor_ativo():
    """
    Testa se o servidor está respondendo.
    Retorna True se /api/status devolver 200, False caso contrário.
    """
    try:
        import clr as _clr
        _clr.AddReference("System.Net")
        from System.Net import WebClient
        wc = WebClient()
        wc.DownloadString(u"{}/api/status".format(_BASE))
        return True
    except Exception:
        return False


# ==============================================================================
def _encontrar_python():
    """
    Tenta localizar o executável CPython na máquina (IronPython-safe).
    Ordem de preferência:
      1. Variável de ambiente FIREUTILS_PYTHON
      2. Varredura de %LOCALAPPDATA%\\Python\\ (instalações pythoncore/nuget)
      3. Caminhos fixos comuns (instalador oficial + Programs\\Python)
      4. Varredura de %PATH%  procurando python.exe real (não o stub da Store)
    Retorna o caminho completo ou None.
    """
    # 1 — variável de ambiente explícita (prioridade máxima)
    env = os.environ.get(u"FIREUTILS_PYTHON")
    if env and os.path.isfile(env):
        return env

    user    = os.environ.get(u"USERNAME",   u"")
    appdata = os.environ.get(u"LOCALAPPDATA", u"C:\\Users\\{}\\AppData\\Local".format(user))

    # 2 — %LOCALAPPDATA%\Python\* — cobre pythoncore, nuget, winget
    try:
        clr.AddReference("System.IO")
        from System.IO import Directory
        py_root = os.path.join(appdata, u"Python")
        if os.path.isdir(py_root):
            subdirs = list(Directory.GetDirectories(py_root))
            # preferir versões maiores primeiro (ordem reversa alfabética)
            subdirs.sort(reverse=True)
            for d in subdirs:
                exe = os.path.join(d, u"python.exe")
                if os.path.isfile(exe):
                    return exe
    except Exception:
        pass

    # 3 — caminhos fixos (instalador oficial em C:\ e Programs\Python)
    versoes = [u"314", u"313", u"312", u"311", u"310", u"39", u"38"]
    candidatos = []
    for v in versoes:
        candidatos += [
            u"C:\\Python{}\\python.exe".format(v),
            u"C:\\Users\\{}\\AppData\\Local\\Programs\\Python\\Python{}\\python.exe".format(user, v),
        ]
    for c in candidatos:
        if os.path.isfile(c):
            return c

    # 4 — varrer PATH procurando python.exe real (exclui stub da Windows Store)
    path_env = os.environ.get(u"PATH", u"")
    _store_marker = u"WindowsApps"
    for folder in path_env.split(u";"):
        if not folder.strip():
            continue
        if _store_marker in folder:
            continue  # stub da Windows Store — não serve
        exe = os.path.join(folder.strip(), u"python.exe")
        if os.path.isfile(exe):
            return exe

    return None


# ==============================================================================
def iniciar_servidor():
    """
    Inicia o servidor Flask em background se ainda não estiver rodando.
    Retorna True em caso de sucesso, False caso contrário.
    """
    global _proc

    # Já está ativo?
    if servidor_ativo():
        return True

    python_exe = _encontrar_python()
    if not python_exe:
        return False

    try:
        psi = ProcessStartInfo()
        psi.FileName        = python_exe
        psi.Arguments       = u'"{}"'.format(_APP_PY)
        psi.UseShellExecute = False
        psi.CreateNoWindow  = True
        # Redirecionar stdout/stderr (evita janela de console)
        psi.RedirectStandardOutput = True
        psi.RedirectStandardError  = True

        _proc = Process()
        _proc.StartInfo = psi
        _proc.Start()

        # Aguarda até 8 s o servidor responder
        for _ in range(16):
            time.sleep(0.5)
            if servidor_ativo():
                return True

        return False

    except Exception:
        return False


# ==============================================================================
def parar_servidor():
    """Encerra o processo do servidor se ele foi iniciado por este launcher."""
    global _proc
    if _proc is not None:
        try:
            _proc.Kill()
        except Exception:
            pass
        _proc = None
