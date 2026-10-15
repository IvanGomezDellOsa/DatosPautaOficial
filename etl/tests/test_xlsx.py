# -*- coding: utf-8 -*-
"""Tests de la lectura de XLSX (comun.leer_xlsx) y de los tipos de CABA publicados solo en XLSX.

Caso real: CABA 2023 publicó Cine, Medios Gráficos y Medios Vecinales solo en XLSX
(data.buenosaires.gob.ar/dataset/pauta-publicitaria). Los montos son números de Excel, que se
guardan en binario ("7427626.3399999999"), y las fechas, números de serie con formato de fecha.

Uso:  python -m unittest discover -s etl/tests -v      (desde la raiz del repo)
"""

import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extractores"))
import comun  # noqa: E402
import extract_caba  # noqa: E402

_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_NS_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

# estilos: 0 general, 1 fecha propia (164, como los XLSX de BA Data), 2 moneda (44), 3 fecha
# predefinida (14)
_ESTILOS = f"""<styleSheet {_NS}><numFmts count="2">
<numFmt numFmtId="44" formatCode="_-&quot;$&quot;\\ * #,##0.00_-;\\-&quot;$&quot;\\ * #,##0.00_-"/>
<numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd;@"/></numFmts>
<cellXfs count="4"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="44"/><xf numFmtId="14"/></cellXfs>
</styleSheet>"""


def _xlsx(path, filas, textos):
    """Escribe un XLSX mínimo: filas = [[(ref, atributos, contenido), ...], ...]."""
    hoja = "".join(
        f'<row r="{i}">' + "".join(f'<c r="{ref}"{at}>{cont}</c>' for ref, at, cont in fila) + "</row>"
        for i, fila in enumerate(filas, 1))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {_NS} {_NS_R}><sheets>'
                                      f'<sheet name="H" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml",
                   f'<sst {_NS}>' + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>")
        z.writestr("xl/styles.xml", _ESTILOS)
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {_NS}><sheetData>{hoja}</sheetData></worksheet>")


def _fila(serie, medio, monto, estilo_monto=' s="2"'):
    return [("A", ' s="1"', f"<v>{serie}</v>"), ("B", ' t="s"', f"<v>{medio}</v>"),
            ("C", estilo_monto, f"<v>{monto}</v>")]


TEXTOS = ["fecha", "medio", "monto_pesos_ars", "FILM  SUEZ S.A. ", "F2F GLOBAL S.A.", "1.234,50"]


class LeerXlsx(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tipos_de_celda(self):
        p = self.dir / "x.xlsx"
        _xlsx(p, [
            [("A", ' t="s"', "<v>0</v>"), ("B", ' t="s"', "<v>1</v>"), ("C", ' t="s"', "<v>2</v>")],
            _fila(44980, 3, "7427626.3399999999"),
            [("A", ' s="3"', "<v>45286</v>"), ("C", ' t="inlineStr"', "<is><t>texto</t></is>")],
            [("A", ' s="1"', "")],                        # celda con estilo y sin valor
        ], TEXTOS)
        filas = comun.leer_xlsx(p)
        self.assertEqual(filas, [
            ["fecha", "medio", "monto_pesos_ars"],
            [date(2023, 2, 23), "FILM  SUEZ S.A. ", 7427626.34],
            [date(2023, 12, 26), None, "texto"],
        ])

    def test_formato_de_fecha(self):
        self.assertTrue(comun._es_formato_fecha("yyyy\\-mm\\-dd;@"))
        self.assertTrue(comun._es_formato_fecha("[$-F800]dddd, mmmm dd, yyyy"))
        self.assertFalse(comun._es_formato_fecha('_-"$"\\ * #,##0.00_-;\\-"$"\\ * #,##0.00_-'))
        self.assertFalse(comun._es_formato_fecha("0.00"))


class CabaPorTipoXlsx(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mismo_criterio_que_los_csv(self):
        p = self.dir / "pauta-publicitaria-cine-2023.xlsx"
        _xlsx(p, [
            [("A", ' t="s"', "<v>0</v>"), ("B", ' t="s"', "<v>1</v>"), ("C", ' t="s"', "<v>2</v>")],
            _fila(44980, 3, "7427626.3399999999"),
            _fila(45286, 4, "1160879.808"),               # 3 decimales: no se lee x1000
            _fila(45286, 4, "5", estilo_monto=' t="s"'),   # monto como texto: "1.234,50"
            _fila(45286, 4, "0"),                         # monto 0: se descarta
        ], TEXTOS)
        cont = comun.Contador("test")
        regs = extract_caba._parse_pertype(p, 2023, cont)
        self.assertEqual([(r["fecha"], r["medio"], r["tipo_de_medio"], r["monto"]) for r in regs], [
            ("2023-02-23", "FILM SUEZ S.A.", "Cine", 7427626.34),
            ("2023-12-26", "F2F GLOBAL S.A.", "Cine", 1160879.808),
            ("2023-12-26", "F2F GLOBAL S.A.", "Cine", 1234.5),
        ])
        self.assertEqual(cont.descartes, {"monto_invalido": 1})
        self.assertTrue(all(r["archivo_origen"] == p.name and r["proveedor"] is None for r in regs))

    def test_solo_xlsx_revisados(self):
        nombre = "pauta-publicitaria-cine-2023.xlsx"
        (self.dir / nombre).write_bytes(b"otro archivo")
        (self.dir / "pauta-publicitaria-radios-2023.xlsx").write_bytes(b"repite un CSV")
        self.assertIn(nombre, extract_caba.XLSX_SIN_CSV)
        self.assertEqual(extract_caba._xlsx_revisados(self.dir), [])


if __name__ == "__main__":
    unittest.main()
