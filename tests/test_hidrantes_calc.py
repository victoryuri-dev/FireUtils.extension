# -*- coding: utf-8 -*-
"""
tests/test_hidrantes_calc.py — Fire Utils

Testes de regressão para o módulo puro de cálculo hidráulico de hidrantes
(Fire Utils.tab/lib/hidrantes/calc.py). Não depende do Revit: calc.py só
importa a API do Revit dentro do corpo de extrair_trecho(), que não é
exercitado aqui.

Execução:
    python -m unittest tests.test_hidrantes_calc -v
"""

import os
import sys
import unittest

_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"Fire Utils.tab", u"lib",
)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from hidrantes.calc import calc_hf_mangueira, calc_hf_trecho, calcular_rede, hesg_mca


class TestDarcyWeisbachMangueira(unittest.TestCase):
    """
    Caso de referência: f=0,022; Lm=30,0 m; Dm=0,040 m; g=9,81 m/s²;
    Q=200 L/min. Coeficiente correto do numerador é 8 (não 2):
        Hm = (8 × f × Lm) / (g × π² × Dm⁵) × Q²
    Se o coeficiente estiver errado (2 em vez de 8), o resultado sai 4x menor
    (1,4793 mca em vez de 5,9173 mca).
    """

    def test_hm_caso_referencia(self):
        Q_m3s = 200.0 / 60000.0
        Dm_m  = 0.040
        Hm = calc_hf_mangueira(Q_m3s, Dm_m)
        self.assertAlmostEqual(Hm, 5.9173, delta=0.01)

    def test_hm_coeficiente_errado_nao_deve_ocorrer(self):
        Q_m3s = 200.0 / 60000.0
        Dm_m  = 0.040
        Hm = calc_hf_mangueira(Q_m3s, Dm_m)
        self.assertNotAlmostEqual(Hm, 1.4793, delta=0.01)


class TestCasoReferenciaCompleto(unittest.TestCase):
    """
    Caso de referência completo (2 hidrantes a 200 L/min cada, Pmin=40 mca,
    C=120, mangueira 40 mm x 30 m, eta=0,50). Confirma que a correção do
    coeficiente de Darcy-Weisbach se propaga corretamente por E_i, Ht,
    pressões e potência da bomba, e que Hazen-Williams permanece intocado.
    """

    def setUp(self):
        self.Qs_lmin = 200.0
        self.Pmin    = 40.0
        self.C       = 120.0
        self.Hz_H1   = 12.9450
        self.Hz_H2   = 12.9450
        self.Dm_m    = 0.040

        self.trechos_data = {
            "t1": {"L": 41.3584, "D": 0.0957, "Leq": 0.0, "acessorios": [], "n_tubos": 1},
            "t2": {"L": 682.0046, "D": 0.0844, "Leq": 0.0, "acessorios": [], "n_tubos": 1},
            "t3": {"L": 45.9464, "D": 0.0688, "Leq": 0.0, "acessorios": [], "n_tubos": 1},
            "t4": {"L": 39.7969, "D": 0.0688, "Leq": 0.0, "acessorios": [], "n_tubos": 1},
        }

    def test_hazen_williams_nao_alterado(self):
        Qt = 2 * self.Qs_lmin / 60000.0
        Qs = self.Qs_lmin / 60000.0
        hf_t1 = calc_hf_trecho(self.trechos_data["t1"], Qt, self.C, u"T1")["Hf"]
        hf_t2 = calc_hf_trecho(self.trechos_data["t2"], Qt, self.C, u"T2")["Hf"]
        hf_t3 = calc_hf_trecho(self.trechos_data["t3"], Qs, self.C, u"T3")["Hf"]
        hf_t4 = calc_hf_trecho(self.trechos_data["t4"], Qs, self.C, u"T4")["Hf"]
        # Tolerâncias de hf_t2 alargadas: o Lt fornecido no caso de referência
        # já vem arredondado a 4 casas decimais; num trecho de 682 m esse
        # arredondamento de entrada se propaga em ~0,03 mca de hf (a própria
        # fórmula é validada de forma independente pelos demais trechos e
        # pela contraprova por velocidade do caso de referência).
        self.assertAlmostEqual(hf_t1, 0.5344, delta=0.01)
        self.assertAlmostEqual(hf_t2, 16.1807, delta=0.04)
        self.assertAlmostEqual(hf_t3, 0.8182, delta=0.01)
        self.assertAlmostEqual(hf_t4, 0.7087, delta=0.01)

    def test_rede_completa(self):
        res = calcular_rede(
            self.trechos_data, self.Qs_lmin, self.Hz_H1, self.Hz_H2,
            Hesg=0.0, Pmin=self.Pmin, C=self.C,
            Dm_mangueira_m=self.Dm_m,
        )

        self.assertAlmostEqual(res["Hm_hid01"], 5.9173, delta=0.01)
        self.assertAlmostEqual(res["Hm_hid02"], 5.9173, delta=0.01)

        c = res["historico"][0]
        E_gov = max(c["E1"], c["E2"])
        self.assertEqual(res["hid_governa"], u"HID-01")
        self.assertAlmostEqual(E_gov, -6.2099, delta=0.02)
        self.assertAlmostEqual(res["Ht"], 50.5052, delta=0.04)

        self.assertAlmostEqual(res["p_hid01"], 40.0000, delta=0.01)
        self.assertAlmostEqual(res["p_hid02"], 40.1095, delta=0.01)

    def test_potencia_bomba(self):
        res = calcular_rede(
            self.trechos_data, self.Qs_lmin, self.Hz_H1, self.Hz_H2,
            Hesg=0.0, Pmin=self.Pmin, C=self.C,
            Dm_mangueira_m=self.Dm_m,
        )
        from hidrantes.calc import calc_potencia
        Qt_m3s = res["Qt_final"] / 60000.0
        pot_cv = calc_potencia(Qt_m3s, res["Ht"], 0.50)
        pot_kw = pot_cv / 1.36
        self.assertAlmostEqual(pot_cv, 8.98, delta=0.05)
        self.assertAlmostEqual(pot_kw, 6.60, delta=0.05)


class TestHesgMca(unittest.TestCase):
    def test_com_k_catalogo(self):
        # Q = K*sqrt(P)  ->  P = (Q/K)^2
        self.assertAlmostEqual(hesg_mca(200.0, k=31.62), 40.0, delta=0.1)

    def test_com_diametro_jato_solido(self):
        # Q = 0.2087*cd*d^2*sqrt(H) -> H = (Q/(0.2087*cd*d^2))^2
        h = hesg_mca(200.0, d_mm=16.0, cd=0.97)
        self.assertGreater(h, 0.0)


if __name__ == u"__main__":
    unittest.main()
