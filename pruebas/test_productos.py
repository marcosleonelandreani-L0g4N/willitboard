"""Pruebas de convert_productos.py.  python3 -m unittest pruebas.test_productos

La regla que protegen: ningún producto se publica sin fecha humana, fuente del
fabricante y enlace de tienda; y nunca se filtran precios ni notas internas."""

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import convert_productos as cp  # noqa: E402

HEAD = ["id", "nombre", "marca", "categoria", "largo_cm", "ancho_cm", "alto_cm", "medidas_incluyen_ruedas",
        "peso_vacio_kg", "capacidad_l", "precio_ref", "rango_precio", "fuente_url", "estado", "verificado_el",
        "disponible_dk", "link_amazon_de", "link_amazon_se", "link_amazon_uk", "link_otro", "notas"]
TODAY = date(2026, 10, 1)


def row(**kw):
    base = dict(id="metz-20l", nombre="Metz 20L", marca="Cabin Max", categoria="underseat-bags",
                largo_cm=40, ancho_cm=25, alto_cm=20, medidas_incluyen_ruedas=None, peso_vacio_kg=0.5,
                capacidad_l=20, precio_ref="GBP 24,95 SECRETO", rango_precio="€", fuente_url="https://cabinmax.com/x",
                estado="listo", verificado_el=TODAY - timedelta(days=1), disponible_dk="SI",
                link_amazon_de="https://www.amazon.de/dp/B0C5RBQMW8", link_amazon_se=None, link_amazon_uk=None,
                link_otro=None, notas="NOTA INTERNA")
    base.update(kw)
    return base


def make_xlsx(path, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Productos"
    ws.append(HEAD)
    ws.append(["ayuda"] * len(HEAD))
    for r in rows:
        ws.append([r.get(h) for h in HEAD])
    wb.save(path)


class ConvertTests(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as d:
            x = Path(d) / "p.xlsx"
            make_xlsx(x, rows)
            return cp.convert_rows(cp.load_rows(x), TODAY)

    def test_publica_solo_con_fecha_fuente_y_enlace(self):
        prods, skipped, errors = self.run_rows([row()])
        self.assertEqual(errors, [])
        self.assertEqual([p["id"] for p in prods], ["metz-20l"])
        self.assertEqual(prods[0]["dims_cm"], [40, 25, 20])

    def test_candidato_no_sale(self):
        prods, skipped, errors = self.run_rows([row(estado="candidato")])
        self.assertEqual(prods, [])
        self.assertEqual(errors, [])

    def test_sin_fecha_no_sale(self):
        prods, skipped, errors = self.run_rows([row(verificado_el=None)])
        self.assertEqual(prods, [])
        self.assertTrue(any("verificado_el" in s for s in skipped))

    def test_fecha_futura_es_error(self):
        _, _, errors = self.run_rows([row(verificado_el=TODAY + timedelta(days=2))])
        self.assertTrue(errors)

    def test_bolso_sin_medidas_es_error(self):
        _, _, errors = self.run_rows([row(alto_cm=None)])
        self.assertTrue(any("medidas" in e for e in errors))

    def test_accesorio_sin_medidas_se_publica(self):
        prods, _, errors = self.run_rows([row(id="balanza", categoria="weigh-measure",
                                              largo_cm=None, ancho_cm=None, alto_cm=None)])
        self.assertEqual(errors, [])
        self.assertIsNone(prods[0]["dims_cm"])

    def test_sin_enlace_es_error(self):
        _, _, errors = self.run_rows([row(link_amazon_de=None)])
        self.assertTrue(any("enlace" in e for e in errors))

    def test_id_repetido(self):
        _, _, errors = self.run_rows([row(), row()])
        self.assertTrue(any("repetido" in e for e in errors))

    def test_no_se_filtran_precio_ni_notas(self):
        prods, _, _ = self.run_rows([row()])
        dump = json.dumps(prods, ensure_ascii=False)
        self.assertNotIn("SECRETO", dump)
        self.assertNotIn("NOTA INTERNA", dump)
        self.assertNotIn("precio_ref", dump)

    def test_error_conserva_json_anterior(self):
        with tempfile.TemporaryDirectory() as d:
            x, out = Path(d) / "p.xlsx", Path(d) / "products.json"
            out.write_text('{"viejo": true}\n', encoding="utf-8")
            make_xlsx(x, [row(categoria="inventada")])
            code = cp.main([str(x), str(out)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.read_text()), {"viejo": True})

    def test_planilla_real_no_publica_nada_sin_verificar(self):
        src = ROOT / "willitboard_productos.xlsx"
        if not src.exists():
            self.skipTest("sin planilla de productos en el repo")
        prods, _, errors = cp.convert_rows(cp.load_rows(src), date.today())
        self.assertEqual(errors, [])
        for p in prods:
            self.assertTrue(p["verified_on"])


if __name__ == "__main__":
    unittest.main()
