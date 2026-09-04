# -*- coding: utf-8 -*-
"""
family_error_utils.py — Fire Utils · lib/
Um único helper: converte uma exceção pra texto sem correr o risco de
lançar uma SEGUNDA exceção no processo.

`str(excecao)` força uma conversão pra bytes (encode) — sob o IronPython
do pyRevit, isso falha com "'unknown' codec can't decode byte..." sempre
que a mensagem da exceção (ou algo que ela referencia, como um caminho de
arquivo com "ç"/"á"/etc.) tiver um caractere acentuado e a codepage do
Windows não for reconhecida pelo IronPython. Como isso normalmente
acontece dentro de um `except` que só queria reportar o erro original,
quem chama via de regra só vê esse erro de codificação mascarando o
problema de verdade (é exatamente esse sintoma que motivou este módulo —
ver commit que adicionou este arquivo).

`unicode(excecao)` evita o passo de encode (a .Message de uma exceção
.NET já é Unicode de verdade) — e, por segurança, se mesmo assim falhar,
cai pra `repr()`, que nunca decodifica nada.
"""


def texto_erro(excecao):
    try:
        return unicode(excecao)
    except Exception:
        try:
            return repr(excecao)
        except Exception:
            return u"(erro sem descrição)"
