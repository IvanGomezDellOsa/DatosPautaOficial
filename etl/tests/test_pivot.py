# -*- coding: utf-8 -*-
"""Tests del parser de pivots de Nacion por rubro (2010-2012).

Caso real (investigacion de atipicos 2026-10-14): en los textos "(nuevo v2)" convertidos desde
PDF, las paginas sin encabezado vienen corridas y el "Total general" de cada proveedor caia por
posicion en "Web" o "Via Publica": se cargaba como una orden mas (2.586 filas).
Los montos de los fixtures son los de los PDFs oficiales (evidencia_pdf/).

Uso:  python -m unittest discover -s etl/tests -v      (desde la raiz del repo)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extractores"))
import comun  # noqa: E402
import extract_nacion  # noqa: E402

# posicion (en caracteres) donde empieza cada encabezado
COL = {"CABLE": 32, "GRAFICA": 48, "RADIO": 64, "T.V.": 80, "VIA PUBLIC": 96, "WEB": 112,
       "Total general": 128}
ENCABEZADO = "Rótulos de fila"
for _lab, _x in COL.items():
    ENCABEZADO = ENCABEZADO.ljust(_x) + _lab


def linea(nombre, celdas):
    """celdas: [(posicion, texto)] en orden de izquierda a derecha."""
    s = nombre
    for x, txt in celdas:
        assert len(s) + 2 <= x, (nombre, celdas)
        s = s.ljust(x) + txt
    return s


def alineada(nombre, celdas):
    """Fila con cada monto debajo de su encabezado: celdas = [(encabezado, texto)]."""
    return linea(nombre, [(COL[c], t) for c, t in celdas])


# Filas de la pagina 1 del PDF 2010-S1 (con encabezado): bien alineadas
PAGINA_1 = [
    alineada("103.9 S R L", [("RADIO", "19.360,00"), ("Total general", "19.360,00")]),
    alineada("ADMINISTRADORA RING S.R.L.", [("CABLE", "2.403.999,90"), ("WEB", "9.680,00"),
                                            ("Total general", "2.413.679,90")]),
]
# Paginas siguientes, corridas como en el texto real: el total cae en "Via Publica" o "Web"
# (en la base quedaron EDITORIAL LA PAGINA Grafica / "TV" / "Via Publica", BAE Grafica / "Web",
# RTA "Radio" / "Via Publica")
CORRIDAS = [
    linea("EDITORIAL LA PAGINA S.A.", [(COL["GRAFICA"], "21.448.330,12"), (COL["T.V."], "102.099,80"),
                                       (COL["VIA PUBLIC"], "21.550.429,92")]),
    linea("BAE NEGOCIOS S.A.", [(COL["GRAFICA"], "4.602.451,63"), (COL["WEB"] - 2, "4.602.451,63")]),
    linea("RADIO Y TELEVISION ARGENT. SE", [(COL["RADIO"], "6.581.413,67"),
                                            (COL["VIA PUBLIC"], "6.581.413,67")]),
]


def total_general(filas_celdas):
    """Fila "Total general" de la tabla: suma de los totales de cada fila."""
    return alineada("Total general", [("Total general", filas_celdas)])


class PivotRubro(unittest.TestCase):

    def _parse(self, lineas, anio=2010):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pivot.csv"
            # cada linea es un unico campo entre comillas, como los "(nuevo v2)"
            p.write_text("\n".join(f'"{l}"' for l in [ENCABEZADO] + lineas) + "\n", encoding="utf-8")
            cont = comun.Contador("test")
            regs = extract_nacion._parse_pivot(p, anio, cont)
        return [(r["proveedor"], r["tipo_de_medio"], r["monto"]) for r in regs], cont

    def test_archivo_alineado_carga_rubros_sin_el_total(self):
        regs, cont = self._parse(PAGINA_1 + [
            alineada("TOTAL PUBLIVIA SA", [("VIA PUBLIC", "70.785,00"), ("Total general", "70.785,00")]),
            total_general("2.503.824,90"),
        ])
        self.assertEqual(regs, [
            ("103.9 S R L", "Radio", 19360.0),
            ("ADMINISTRADORA RING S.R.L.", "TV Cable", 2403999.9),
            ("ADMINISTRADORA RING S.R.L.", "Web", 9680.0),
            # un proveedor que empieza con "TOTAL" no es la fila de totales (antes se descartaba)
            ("TOTAL PUBLIVIA SA", "Via Publica", 70785.0),
        ])
        self.assertEqual(cont.avisos, {})

    def test_paginas_corridas_no_cargan_el_total_general(self):
        regs, cont = self._parse(PAGINA_1 + CORRIDAS + [total_general("35.167.335,12")])
        # solo los montos por rubro del PDF: ningun "Total general" cargado como orden
        self.assertEqual([(p, m) for p, _, m in regs], [
            ("103.9 S R L", 19360.0),
            ("ADMINISTRADORA RING S.R.L.", 2403999.9),
            ("ADMINISTRADORA RING S.R.L.", 9680.0),
            ("EDITORIAL LA PAGINA S.A.", 21448330.12),
            ("EDITORIAL LA PAGINA S.A.", 102099.8),
            ("BAE NEGOCIOS S.A.", 4602451.63),
            ("RADIO Y TELEVISION ARGENT. SE", 6581413.67),
        ])
        # las posiciones no siguen al encabezado: el rubro queda vacio en vez de equivocado
        self.assertEqual({t for _, t, _ in regs}, {None})
        self.assertEqual(cont.avisos, {"pivot_rubro_sin_dato": 7})

    def test_dos_montos_en_la_misma_columna_es_corrimiento(self):
        regs, cont = self._parse([
            # el total cae en su columna, pero dos rubros caen en "GRAFICA"
            linea("BAYRES PUBLICIDAD S.A.", [(COL["GRAFICA"] - 6, "11.050,00"), (COL["GRAFICA"] + 5, "29.040,00"),
                                             (COL["Total general"], "40.090,00")]),
            total_general("40.090,00"),
        ])
        self.assertEqual(regs, [("BAYRES PUBLICIDAD S.A.", None, 11050.0),
                                ("BAYRES PUBLICIDAD S.A.", None, 29040.0)])
        self.assertIn("pivot_rubro_sin_dato", cont.avisos)

    def test_no_concilia_con_el_total_de_la_tabla(self):
        regs, cont = self._parse(PAGINA_1 + [total_general("9.999.999,99")])
        self.assertEqual(len(regs), 3)
        self.assertEqual(cont.avisos, {"pivot_no_concilia_total_general": 1})

    def test_sin_fila_total_general(self):
        _, cont = self._parse(PAGINA_1)
        self.assertEqual(cont.avisos, {"pivot_sin_total_general": 1})

    def test_desescapa_las_comillas_del_campo(self):
        # cada linea es un campo CSV entre comillas: las comillas internas vienen duplicadas
        regs, _ = self._parse([
            alineada('ASOC.CIV.S/FIN.LUCRO""NOSOTROS""', [("RADIO", "25.700,00"), ("Total general", "25.700,00")]),
            total_general("25.700,00"),
        ])
        self.assertEqual(regs, [('ASOC.CIV.S/FIN.LUCRO"NOSOTROS"', "Radio", 25700.0)])

    def test_fila_que_no_concilia_usa_la_posicion(self):
        # falta el total: no se puede reconocer por aritmetica, se usa la posicion
        regs, cont = self._parse([
            alineada("AGUERO SONIA SILVIA", [("CABLE", "8.000,00"), ("GRAFICA", "6.630,00")]),
            alineada("ALCAI S.R.L.", [("RADIO", "2.420,00"), ("Total general", "2.420,00")]),
            total_general("17.050,00"),
        ])
        self.assertEqual(regs, [("AGUERO SONIA SILVIA", "TV Cable", 8000.0),
                                ("AGUERO SONIA SILVIA", "Gráfica", 6630.0),
                                ("ALCAI S.R.L.", "Radio", 2420.0)])
        self.assertEqual(cont.avisos, {"pivot_fila_no_concilia": 1})


class PivotMes(unittest.TestCase):
    """Los pivots por mes (2009) no cambian: se saltan los subtotales "Total <proveedor>"."""

    def test_subtotales_y_columna_total(self):
        enc = linea("DENOMINACION", [(32, "MEDIO"), (56, "may-09"), (72, "jun-09"), (88, "Total")])
        lineas = [
            enc,
            linea("ACME SA", [(32, "RADIO ACME"), (56, "1.000,00"), (72, "500,00"), (88, "1.500,00")]),
            linea("Total ACME SA", [(56, "1.000,00"), (72, "500,00"), (88, "1.500,00")]),
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pivot_mes.csv"
            p.write_text("\n".join(f'"{l}"' for l in lineas) + "\n", encoding="utf-8")
            regs = extract_nacion._parse_pivot(p, 2009, comun.Contador("test"))
        self.assertEqual([(r["proveedor"], r["medio"], r["fecha"], r["monto"]) for r in regs], [
            ("ACME SA", "RADIO ACME", "2009-05-01", 1000.0),
            ("ACME SA", "RADIO ACME", "2009-06-01", 500.0),
        ])


if __name__ == "__main__":
    unittest.main()
