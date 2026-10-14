# -*- coding: utf-8 -*-
"""Tests del parseo de montos: separador decimal decidido por columna.

Caso real (investigacion de atipicos 2026-10-14): CABA pauta-publicitaria-2016.csv usa punto
decimal y algunas celdas traen 3 decimales ("1160879.808"); la regla celda por celda las leia
como miles y quedaban x1000.

Uso:  python -m unittest discover -s etl/tests -v      (desde la raiz del repo)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extractores"))
import comun  # noqa: E402
import extract_caba  # noqa: E402
from comun import detectar_decimal, normalizar_monto, parser_montos  # noqa: E402


# Columna IMPORTE de CABA pauta-publicitaria-2016.csv (punto decimal, sin separador de miles)
COLUMNA_PUNTO = ["13000", "2452234.4", "48000", "392120.34", "1160879.808", "392120.344"]
# Columna europea (pauta-publicitaria-en-tv-2017.csv y similares)
COLUMNA_COMA = ["48.000,00", "6036629,5", "1151594,994", "4.500", "6747956"]


class DetectarDecimal(unittest.TestCase):

    def test_columna_con_punto_decimal(self):
        self.assertEqual(detectar_decimal(COLUMNA_PUNTO), ".")

    def test_columna_europea(self):
        self.assertEqual(detectar_decimal(COLUMNA_COMA), ",")

    def test_celdas_ambiguas_no_deciden(self):
        # un separador seguido de exactamente 3 digitos puede ser de miles o decimal
        self.assertIsNone(detectar_decimal(["1160879.808", "4.500", "48000"]))

    def test_columna_contradictoria_no_decide(self):
        self.assertIsNone(detectar_decimal(["392120.34", "2452234.4", "48.000,00", "1.234,5"]))

    def test_un_solo_voto_no_alcanza(self):
        # una celda mal tipeada ("1.5") no debe reinterpretar los miles de toda la columna
        col = ["4.500", "12.000", "1.5"]
        self.assertIsNone(detectar_decimal(col))
        self.assertEqual(parser_montos(col, "test")("4.500"), 4500.0)


class NormalizarMontoConSeparador(unittest.TestCase):

    def test_tres_decimales_en_columna_con_punto(self):
        leer = parser_montos(COLUMNA_PUNTO, "test")
        self.assertAlmostEqual(leer("1160879.808"), 1160879.808)
        self.assertAlmostEqual(leer("392120.344"), 392120.344)
        self.assertAlmostEqual(leer("392120.34"), 392120.34)
        self.assertEqual(leer("48000"), 48000.0)

    def test_columna_europea(self):
        leer = parser_montos(COLUMNA_COMA, "test")
        self.assertEqual(leer("48.000,00"), 48000.0)
        self.assertAlmostEqual(leer("1151594,994"), 1151594.994)
        self.assertEqual(leer("4.500"), 4500.0)
        self.assertEqual(leer("6036629,5"), 6036629.5)

    def test_separador_explicito(self):
        self.assertAlmostEqual(normalizar_monto("$ 1,160,879.808", "."), 1160879.808)
        self.assertEqual(normalizar_monto("$ 4.500", ","), 4500.0)
        self.assertEqual(normalizar_monto("(1.210,00)", ","), 1210.0)
        self.assertIsNone(normalizar_monto("0,00", ","))
        self.assertIsNone(normalizar_monto("", "."))


class NormalizarMontoSinSeparador(unittest.TestCase):
    """Sin separador de columna se mantiene la regla anterior, celda por celda."""

    def test_regla_anterior(self):
        self.assertEqual(normalizar_monto("1.210,00"), 1210.0)
        self.assertEqual(normalizar_monto("$ 28,991.36"), 28991.36)
        self.assertEqual(normalizar_monto(" $  300,000 "), 300000.0)
        self.assertEqual(normalizar_monto("10000.0"), 10000.0)
        self.assertEqual(normalizar_monto("1.234.567"), 1234567.0)
        self.assertEqual(normalizar_monto("1210,50"), 1210.5)
        self.assertEqual(normalizar_monto("(1.210,00)"), 1210.0)
        self.assertEqual(normalizar_monto("-5"), 5.0)
        self.assertEqual(normalizar_monto("4.500"), 4500.0)
        self.assertIsNone(normalizar_monto("0"))
        self.assertIsNone(normalizar_monto(""))
        self.assertIsNone(normalizar_monto(None))
        self.assertIsNone(normalizar_monto("s/d"))


class CabaCombinado(unittest.TestCase):
    """El extractor CABA lee el archivo completo con el separador de su columna IMPORTE."""

    def _parse(self, contenido, nombre):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / nombre
            p.write_text(contenido, encoding="utf-8")
            cont = comun.Contador("test")
            return extract_caba._parse_combinado(p, 2016, cont)

    def test_punto_decimal_con_tres_decimales(self):
        # lineas 2, 3943, 5275, 3985 y 361 de pauta-publicitaria-2016.csv
        regs = self._parse(
            "FECHA PUBLICACIÓN,TIPO MEDIO,MEDIO,IMPORTE,RAZON SOCIAL MEDIO,CAMPAÑA\n"
            "01/01/2016,WEB,REVISTA DIGITAL EVIDENCIAS,13000,TELÉMACO S.A.,BUENOS AIRES PLAYA\n"
            "09/21/2016,TV,TELEFE,2452234.4,TELEVISION FEDERAL S.A.,DISFRUTE\n"
            "11/02/2016,TV,CANAL 26,1160879.808,EVENTOS PRODUCCIONES SA,SEPARACION DE RECICLABLES\n"
            "09/25/2016,MEDIOS GRAFICOS,POPULAR,392120.344,IMPREBA S.A.,DISFRUTE\n"
            "05/29/2016,MEDIOS GRAFICOS,POPULAR,392120.34,IMPREBA S.A.,PARTICIPACION CIUDADANA\n",
            "pauta-publicitaria-2016.csv")
        self.assertEqual([r["monto"] for r in regs],
                         [13000.0, 2452234.4, 1160879.808, 392120.344, 392120.34])
        self.assertEqual(regs[2]["proveedor"], "EVENTOS PRODUCCIONES SA")

    def test_coma_decimal_con_tres_decimales(self):
        # pauta-publicitaria-en-medios-graficos-2016.csv: el mismo aviso con coma decimal
        regs = self._parse(
            "FECHA-PUBLICACION;TIPO;MEDIO;IMPORTE\n"
            "01/01/2016;MEDIOS GRAFICOS;FUNDAMIND;15600\n"
            "09/01/2016;MEDIOS GRAFICOS;LA PRENSA;16882,49\n"
            "25/09/2016;MEDIOS GRAFICOS;POPULAR;392120,344\n"
            "14/10/2016;MEDIOS GRAFICOS;EL ECONOMISTA;38085,831\n"
            "15/10/2016;MEDIOS GRAFICOS;PERFIL;48.000,00\n"
            "16/10/2016;MEDIOS GRAFICOS;PERFIL;4.500\n",
            "pauta-publicitaria-en-medios-graficos-2016.csv")
        self.assertEqual([r["monto"] for r in regs],
                         [15600.0, 16882.49, 392120.344, 38085.831, 48000.0, 4500.0])


if __name__ == "__main__":
    unittest.main()
