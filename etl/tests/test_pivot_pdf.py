# -*- coding: utf-8 -*-
"""Tests del lector de pivots de Nacion desde el PDF oficial (por coordenadas).

En el texto "(nuevo v2)" convertido desde PDF las paginas sin encabezado vienen corridas: la
columna (rubro o mes) de cada monto no se puede leer de ahi. En el PDF cada palabra tiene su
posicion real.

Fragmentos: lineas reales de los PDFs oficiales, con las coordenadas que da pdfplumber
(texto, x0, x1). La fila de totales de cada fragmento es la suma de sus filas, ubicada donde
terminan los montos de cada columna en el PDF. fixtures/ tiene dos PDFs oficiales completos
(argentina.gob.ar/sites/default/files/<nombre>).

Uso:  python -m unittest discover -s etl/tests -v      (desde la raiz del repo)
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extractores"))
import comun  # noqa: E402
import extract_nacion  # noqa: E402

try:
    import pdfplumber  # noqa: F401
    HAY_PDFPLUMBER = True
except ImportError:
    HAY_PDFPLUMBER = False

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PDF_2010_S1 = FIXTURES / "pauta_por_proveedor_coniva_ene_jun_2010.pdf"
PDF_2009_NOV_DIC = FIXTURES / "pauta_por_proveedor_coniva_nov_dic_2009.pdf"


def linea(*palabras):
    return [{"text": t, "x0": x0, "x1": x1} for t, x0, x1 in palabras]


def totales(etiqueta, montos):
    """Fila de totales del fragmento: [(texto, x1)]; x0 no importa (montos alineados a la derecha)."""
    ws = [(etiqueta, 52.8, 85.9)] if etiqueta else []
    return linea(*ws, *[(t, x1 - 40, x1) for t, x1 in montos])


# --- 2010-S2 (segundo_semestre_prov_rubro_2010.pdf) -----------------------------------------
ENC_2010_S2 = linea(
    ("RAZON", 52.8, 70.7), ("SOCIAL", 72.2, 90.3), ("CABLE", 168.1, 184.1), ("CINE", 216.4, 228.4),
    ("GRAFICA", 256.4, 278.7), ("RADIO", 308.3, 324.8), ("T.V.", 356.6, 366.3), ("VIA", 408.6, 417.3),
    ("PUBLIC", 418.7, 436.8), ("WEB", 456.8, 468.7), ("Total", 505.1, 517.8), ("general", 519.2, 538.2))
# pagina 9: sin encabezado (en el texto convertido, estas filas venian corridas)
MOSCA = linea(
    ("MOSCA", 52.8, 72.0), ("MAXIMILIANO", 73.4, 110.0), ("EZEQUIEL", 111.3, 135.6), ("$", 256.4, 259.5),
    ("67.760,00", 277.9, 302.9), ("$", 308.3, 311.5), ("99.220,00", 326.1, 351.1), ("$", 356.6, 359.8),
    ("206.374,00", 374.9, 403.1), ("$", 456.8, 460.0), ("52.030,00", 474.6, 499.6), ("$", 505.1, 508.2),
    ("425.384,00", 523.4, 551.5))
# el PDF parte el total en "9" y ".680,00" (lo une _lineas_pdf)
MOTOR_MEDIA = linea(
    ("MOTOR", 52.8, 72.6), ("MEDIA", 74.0, 91.3), ("S.A.", 92.7, 102.4), ("$", 456.8, 460.0),
    ("9.680,00", 477.7, 499.6), ("$", 505.1, 508.2), ("9.680,00", 529.7, 551.5))
# todos los rubros en "-": no es una orden
MOTORPRESS = linea(
    ("MOTORPRESS", 52.8, 87.9), ("ARGENTINA", 89.4, 119.6), ("SA", 121.0, 127.5), ("$", 256.4, 259.5),
    ("-", 294.6, 296.6), ("$", 505.1, 508.2), ("-", 543.4, 545.3))
MOVIEGROUP = linea(
    ("MOVIEGROUP", 52.8, 88.9), ("S.A.", 90.3, 100.0), ("$", 308.3, 311.5), ("59.991,80", 326.1, 351.1),
    ("$", 505.1, 508.2), ("59.991,80", 526.5, 551.5))
TOTALES_PAG9 = totales("Total general", [
    ("67.760,00", 302.9), ("159.211,80", 351.1), ("206.374,00", 403.1), ("61.710,00", 499.6),
    ("495.055,80", 551.5)])

# --- 2009 (pauta_por_proveedor_coniva_nov_dic_2009.pdf y pauta_por_proveedor_con_iva_2009.pdf) -
ENC_NOV_DIC = linea(("DENOMINACION", 128.3, 199.6), ("MEDIO", 345.1, 374.7), ("nov-09", 602.9, 631.9),
                    ("dic-09", 669.0, 695.1))
TITULO_NOV_DIC = linea(("Pauta_por_proveedor_conIVA_nov_dic_2009", 320.0, 521.1))
# sin medio: el lector de texto tomaba el primer monto como medio y perdia esa celda
CK = linea(("C&K", 128.1, 144.7), ("AUDIOVISUAL", 147.0, 201.1), ("S.A.", 203.4, 218.7),
           ("383.075,59", 607.5, 647.7), ("436.703,05", 672.2, 712.3))
ZMS = linea(("ZMS", 128.1, 145.0), ("SOCIEDAD", 147.3, 189.4), ("ANONIMA", 191.6, 229.0), ("ZMS", 345.0, 361.9),
            ("SOCIEDAD", 364.2, 406.2), ("ANONIMA", 408.5, 445.9), ("30.250,00", 676.7, 712.3))

ENC_MAYO_OCT = linea(("DENOMINACION", 53.3, 124.6), ("MEDIO", 270.0, 299.6), ("may-09", 457.1, 487.8),
                     ("jul-09", 525.1, 548.7), ("ago-09", 586.8, 615.9), ("sep-09", 651.5, 680.1),
                     ("oct-09", 716.9, 743.5))
# un proveedor que se llama "TOTAL ...": el lector de texto lo descartaba como subtotal
TOTAL_FM = linea(("TOTAL", 53.2, 79.1), ("F.M.", 81.4, 97.4), ("S.R.L.", 99.7, 122.1), ("TOTAL", 269.9, 295.8),
                 ("F.M.", 298.1, 314.1), ("484,00", 478.1, 502.6), ("1.210,00", 535.8, 567.0),
                 ("1.210,00", 600.2, 631.5))
NOSTALGIE = linea(("NOSTALGIE", 53.1, 99.2), ("AMSUD", 101.5, 130.5), ("S.A.", 132.7, 148.0), ("X", 269.9, 275.2),
                  ("4", 277.3, 281.8), ("605,00", 478.1, 502.6), ("5.082,00", 535.8, 567.0),
                  ("5.082,00", 600.2, 631.5))
# sin montos en ningun mes (no hay columna jun-09 en el PDF)
TORNEOS = linea(("TORNEOS", 53.1, 92.8), ("Y", 95.1, 100.5), ("COMPETENCIAS", 102.8, 167.1), ("S.A.", 169.4, 184.7),
                ("TORNEOS", 269.9, 309.6), ("Y", 311.9, 317.2), ("COMPETENCIAS", 319.5, 383.8),
                ("S.A.", 386.1, 401.5))


def con(fila, **cambios):
    """Copia de una linea cambiando el texto o el x1 de algunas palabras: {indice: (texto, x1)}."""
    out = [dict(w) for w in fila]
    for i, (t, x1) in cambios.items():
        out[int(i[1:])].update(text=t, x1=x1)
    return out


class LineasPdf(unittest.TestCase):

    def test_une_los_pedazos_pegados_de_un_numero(self):
        class Pagina:
            def extract_words(self, **_):
                return [dict(w, top=420.7) for w in linea(
                    ("MOTOR", 52.8, 72.6), ("$", 505.1, 508.2), ("9", 529.7, 532.8), (".680,00", 532.8, 551.5))
                ] + [dict(w, top=495.2) for w in linea(
                    ("Total", 52.8, 65.5), ("$", 256.4, 259.5), ("1", 263.8, 267.0),
                    ("69.860.514,46", 266.9, 302.9))]
        self.assertEqual([[w["text"] for w in l] for l in extract_nacion._lineas_pdf(Pagina())],
                         [["MOTOR", "$", "9.680,00"], ["Total", "$", "169.860.514,46"]])


class TablaPdfRubro(unittest.TestCase):

    def test_columna_por_el_borde_derecho_del_numero(self):
        modo, cols, filas, problemas = extract_nacion._tabla_pdf(
            [ENC_2010_S2, MOSCA, MOTOR_MEDIA, MOTORPRESS, MOVIEGROUP, TOTALES_PAG9])
        self.assertEqual((modo, problemas), ("rubro", []))
        self.assertEqual(cols, ["CABLE", "CINE", "GRAFICA", "RADIO", "T.V.", "VIA PUBLIC", "WEB",
                                "Total general"])
        self.assertEqual([(p, m, [(cols[c], t) for c, t in cs]) for p, m, cs in filas], [
            ("MOSCA MAXIMILIANO EZEQUIEL", None, [("GRAFICA", "67.760,00"), ("RADIO", "99.220,00"),
                                                  ("T.V.", "206.374,00"), ("WEB", "52.030,00"),
                                                  ("Total general", "425.384,00")]),
            ("MOTOR MEDIA S.A.", None, [("WEB", "9.680,00"), ("Total general", "9.680,00")]),
            ("MOVIEGROUP S.A.", None, [("RADIO", "59.991,80"), ("Total general", "59.991,80")]),
        ])

    def test_fila_cuyos_rubros_no_suman_su_total(self):
        _, _, _, problemas = extract_nacion._tabla_pdf(
            [ENC_2010_S2, MOSCA, MOTOR_MEDIA, con(MOVIEGROUP, w5=("59.991,81", 551.5)), TOTALES_PAG9])
        self.assertTrue(any(p.startswith("MOVIEGROUP S.A.: los rubros suman") for p in problemas), problemas)

    def test_monto_que_no_termina_donde_los_de_su_columna(self):
        # sigue cayendo en WEB, pero 10 puntos a la izquierda del resto de esa columna
        _, _, _, problemas = extract_nacion._tabla_pdf(
            [ENC_2010_S2, con(MOSCA, w10=("52.030,00", 489.6)), MOTOR_MEDIA, MOVIEGROUP, TOTALES_PAG9])
        self.assertEqual(problemas, ["columna WEB: los montos no estan alineados (terminan entre "
                                     "x=489.6 y x=499.6)"])

    def test_columna_que_no_suma_su_total(self):
        _, _, _, problemas = extract_nacion._tabla_pdf([ENC_2010_S2, MOSCA, MOTOR_MEDIA, TOTALES_PAG9])
        self.assertIn("columna RADIO: las filas suman 99,220.00 y el total es 159,211.80", problemas)

    def test_sin_fila_de_totales(self):
        _, _, _, problemas = extract_nacion._tabla_pdf([ENC_2010_S2, MOSCA])
        self.assertEqual(problemas, ["sin fila de totales"])

    def test_sin_encabezado(self):
        self.assertEqual(extract_nacion._tabla_pdf([MOSCA, MOVIEGROUP])[3], ["sin encabezado"])


class TablaPdfMes(unittest.TestCase):

    def test_encabezado_repetido_y_fila_sin_medio(self):
        modo, cols, filas, problemas = extract_nacion._tabla_pdf([
            TITULO_NOV_DIC, ENC_NOV_DIC, CK, TITULO_NOV_DIC, ENC_NOV_DIC, ZMS,
            totales(None, [("383.075,59", 647.7), ("466.953,05", 712.3)])])
        self.assertEqual((modo, cols, problemas), ("mes", ["nov-09", "dic-09"], []))
        # el encabezado de cada pagina no es una orden (el texto cargaba "nov-09" como $9)
        self.assertEqual(filas, [
            ("C&K AUDIOVISUAL S.A.", None, [(0, "383.075,59"), (1, "436.703,05")]),
            ("ZMS SOCIEDAD ANONIMA", "ZMS SOCIEDAD ANONIMA", [(1, "30.250,00")]),
        ])

    def test_redondeo_de_los_totales_por_mes(self):
        # dic-09 tiene 2 celdas: se acepta hasta (2 + 1) // 2 = 1 centavo de diferencia
        def problemas(total_dic):
            return extract_nacion._tabla_pdf([ENC_NOV_DIC, CK, ZMS, totales(
                None, [("383.075,59", 647.7), (total_dic, 712.3)])])[3]
        self.assertEqual(problemas("466.953,06"), [])
        self.assertEqual(problemas("466.953,07"),
                         ["columna dic-09: las filas suman 466,953.05 y el total es 466,953.07"])

    def test_proveedor_total_y_fila_sin_montos(self):
        modo, cols, filas, problemas = extract_nacion._tabla_pdf([
            ENC_MAYO_OCT, TOTAL_FM, TORNEOS, NOSTALGIE,
            totales(None, [("1.089,00", 502.6), ("6.292,00", 567.0), ("6.292,00", 631.5)])])
        self.assertEqual(problemas, [])
        self.assertEqual([(p, m, [(cols[c], t) for c, t in cs]) for p, m, cs in filas], [
            ("TOTAL F.M. S.R.L.", "TOTAL F.M.", [("may-09", "484,00"), ("jul-09", "1.210,00"),
                                                 ("ago-09", "1.210,00")]),
            ("NOSTALGIE AMSUD S.A.", "X 4", [("may-09", "605,00"), ("jul-09", "5.082,00"),
                                             ("ago-09", "5.082,00")]),
        ])


@unittest.skipUnless(HAY_PDFPLUMBER, "falta pdfplumber (pip install pdfplumber)")
class ParsePivotPdf(unittest.TestCase):
    """PDFs oficiales completos: cada fila, cada columna y el total de la tabla concilian."""

    def test_2010_s1_por_rubro(self):
        cont = comun.Contador("test")
        regs = extract_nacion._parse_pivot_pdf(PDF_2010_S1, 2010, "pivot.csv", cont)
        self.assertEqual(len(regs), 884)
        por_rubro = {}
        for r in regs:
            por_rubro[r["tipo_de_medio"]] = por_rubro.get(r["tipo_de_medio"], 0) + round(r["monto"] * 100)
        # fila "Total general" del PDF (pagina 20)
        self.assertEqual(por_rubro, {"TV Cable": 2383441179, "Gráfica": 12613617289, "Radio": 3357257886,
                                     "TV": 4881911255, "Via Publica": 454010494, "Web": 722576441})
        self.assertEqual(sum(por_rubro.values()), 24412814544)
        self.assertIn(("TOTAL PUBLIVIA SA", "Via Publica", 70785.0),
                      [(r["proveedor"], r["tipo_de_medio"], r["monto"]) for r in regs])
        self.assertEqual({(r["anio"], r["archivo_origen"], r["fecha"], r["medio"]) for r in regs},
                         {(2010, "pivot.csv", None, None)})
        self.assertEqual(cont.avisos, {})

    def test_2009_nov_dic_por_mes(self):
        regs = extract_nacion._parse_pivot_pdf(PDF_2009_NOV_DIC, 2009, "pivot.csv", comun.Contador("test"))
        self.assertEqual(len(regs), 513)
        por_mes = {}
        for r in regs:
            por_mes[r["fecha"]] = por_mes.get(r["fecha"], 0) + round(r["monto"] * 100)
        # totales del PDF: 53.754.561,17 y 24.076.604,12 (nov difiere 2 centavos por redondeo)
        self.assertEqual(por_mes, {"2009-11-01": 5375456115, "2009-12-01": 2407660412})
        self.assertEqual([(r["medio"], r["fecha"], r["monto"]) for r in regs
                          if r["proveedor"] == "C&K AUDIOVISUAL S.A."],
                         [(None, "2009-11-01", 383075.59), (None, "2009-12-01", 436703.05)])
        self.assertNotIn("DENOMINACION", {r["proveedor"] for r in regs})


@unittest.skipUnless(HAY_PDFPLUMBER, "falta pdfplumber (pip install pdfplumber)")
class ExtraerPrefiereElPdf(unittest.TestCase):
    """extraer() lee el PDF oficial si esta junto al CSV y es el revisado; si no, el texto."""

    CSV = "(nuevo v2Pauta_por_proveedor_conIVA_ene_jun_2010.csv"

    def _extraer(self, pdf_bytes):
        with tempfile.TemporaryDirectory() as d:
            ydir = Path(d) / "Nacion" / "2010"
            ydir.mkdir(parents=True)
            enc = "Rótulos de fila".ljust(32) + "RADIO".ljust(16) + "Total general"
            fila = "103.9 S R L".ljust(32) + "19.360,00".ljust(16) + "19.360,00"
            tot = "Total general".ljust(48) + "19.360,00"
            (ydir / self.CSV).write_text("\n".join(f'"{l}"' for l in (enc, fila, tot)) + "\n", encoding="utf-8")
            if pdf_bytes is not None:
                (ydir / PDF_2010_S1.name).write_bytes(pdf_bytes)
            with mock.patch.object(extract_nacion, "DIR_NACION", ydir.parent), \
                    mock.patch.object(extract_nacion, "DIR_CURADO", Path(d) / "no_existe"):
                return extract_nacion.extraer()

    def test_con_el_pdf_revisado_lee_el_pdf(self):
        regs = self._extraer(PDF_2010_S1.read_bytes())
        self.assertEqual(len(regs), 884)
        self.assertEqual({r["archivo_origen"] for r in regs}, {self.CSV})
        self.assertNotIn(None, {r["tipo_de_medio"] for r in regs})

    def test_con_otro_pdf_lee_el_texto(self):
        regs = self._extraer(PDF_2010_S1.read_bytes() + b"\n")
        self.assertEqual([(r["proveedor"], r["tipo_de_medio"], r["monto"]) for r in regs],
                         [("103.9 S R L", "Radio", 19360.0)])

    def test_sin_pdf_lee_el_texto(self):
        self.assertEqual(len(self._extraer(None)), 1)


if __name__ == "__main__":
    unittest.main()
