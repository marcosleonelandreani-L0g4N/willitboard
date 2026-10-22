#!/usr/bin/env python3
"""Pruebas de los feeds de Pinterest (herramientas/generar_feed.py).

Lo central:
  - Ningún Pin lleva cifras de equipaje (ni en el texto ni en el título): el Pin
    queda fijo en Pinterest y el operador puede cambiar sus límites.
  - Se suelta de a poco: un operador por día, la lista de liberados solo crece y
    nunca repite. Correrlo dos veces el mismo día no suelta más.
  - Cada enlace es la ficha real del operador en willitboard.com, y cada imagen
    existe y pesa lo que dice el feed.

Uso: python3 -m unittest pruebas/test_pinterest.py -v
"""
from __future__ import annotations

import io
import json
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "herramientas"))
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402
import generar_feed as gf  # noqa: E402

OPS = {o["id"]: o for o in json.loads(gf.DATASET.read_text(encoding="utf-8"))["operators"]}


class Base(unittest.TestCase):
    """Corre generar_feed.py con el estado y los feeds en una carpeta temporal."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (gf.ESTADO, dict(gf.FEEDS))
        gf.ESTADO = self.tmp / "estado.json"
        gf.FEEDS = {"en": self.tmp / "pins.xml", "es": self.tmp / "es" / "pins.xml"}

    def tearDown(self):
        gf.ESTADO, gf.FEEDS = self._orig[0], self._orig[1]
        shutil.rmtree(self.tmp)

    def run_feed(self, *args):
        with redirect_stdout(io.StringIO()):
            gf.main(list(args))

    def items(self, lang):
        root = ET.parse(gf.FEEDS[lang]).getroot()
        return root.findall("./channel/item")

    def ids(self, lang):
        return [i.findtext("guid").split(f"willitboard-pin-{lang}-", 1)[1] for i in self.items(lang)]


class SoltarDeAPocoTests(Base):
    def test_antes_de_empezar_hay_un_solo_pin_y_no_hay_estado(self):
        for dia in ("2026-11-01", "2026-11-02", "2026-11-09"):
            self.run_feed("--hoy", dia)
        self.assertFalse(gf.ESTADO.exists())
        for lang in gf.FEEDS:
            self.assertEqual(self.ids(lang), [gf.cola(list(OPS.values()))[0]])

    def test_antes_de_empezar_el_feed_no_cambia_de_un_dia_a_otro(self):
        self.run_feed("--hoy", "2026-11-01")
        a = gf.FEEDS["en"].read_bytes()
        self.run_feed("--hoy", "2026-11-05")
        self.assertEqual(a, gf.FEEDS["en"].read_bytes())

    def test_al_empezar_el_primer_pin_no_cambia(self):
        self.run_feed("--hoy", "2026-11-01")
        antes = {lang: ET.tostring(self.items(lang)[0]) for lang in gf.FEEDS}
        self.run_feed("--empezar", "--hoy", "2026-11-04")
        self.run_feed("--hoy", "2026-11-05")
        for lang in gf.FEEDS:
            self.assertEqual(ET.tostring(self.items(lang)[-1]), antes[lang])

    def test_un_operador_por_dia_y_mismo_dia_no_suelta_mas(self):
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        self.assertEqual(len(self.ids("en")), 1)
        self.run_feed("--hoy", "2026-11-01")          # la tarea corre dos veces el mismo día
        self.assertEqual(len(self.ids("en")), 1)
        self.run_feed("--hoy", "2026-11-02")
        self.run_feed("--hoy", "2026-11-03")
        self.assertEqual(len(self.ids("en")), 3)
        self.assertEqual(self.ids("en"), self.ids("es"))   # mismo operador en los dos idiomas

    def test_un_dia_sin_correr_no_suelta_de_golpe(self):
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        self.run_feed("--hoy", "2026-11-09")          # GitHub se saltó días: sale uno solo
        self.assertEqual(len(self.ids("en")), 2)

    def test_empezar_dos_veces_no_reinicia(self):
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        self.run_feed("--hoy", "2026-11-02")
        self.run_feed("--empezar", "--hoy", "2026-11-03")
        estado = json.loads(gf.ESTADO.read_text())
        self.assertEqual(estado["inicio"], "2026-11-01")
        self.assertEqual(len(estado["publicados"]), 3)

    def test_la_cola_completa_sale_sin_repetir_y_despues_para(self):
        q = gf.cola(list(OPS.values()))
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        from datetime import date, timedelta
        d = date(2026, 11, 1)
        for k in range(1, len(q) + 5):
            self.run_feed("--hoy", (d + timedelta(days=k)).isoformat())
        ids = self.ids("en")
        self.assertEqual(len(ids), len(q))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(sorted(ids), sorted(q))

    def test_lo_liberado_no_cambia_de_lugar_si_cambia_el_orden(self):
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        self.run_feed("--hoy", "2026-11-02")
        antes = json.loads(gf.ESTADO.read_text())["publicados"]
        orig = list(gf.ORDEN)
        try:
            gf.ORDEN[:] = list(reversed(orig))
            self.run_feed("--hoy", "2026-11-03")
        finally:
            gf.ORDEN[:] = orig
        despues = json.loads(gf.ESTADO.read_text())["publicados"]
        self.assertEqual(despues[:2], antes)
        self.assertEqual(len(despues), 3)

    def test_operador_sin_imagen_no_entra_en_la_cola(self):
        q = gf.cola(list(OPS.values()))
        falso = dict(OPS[q[0]], id="operador-sin-imagen")
        with redirect_stdout(io.StringIO()):
            self.assertNotIn("operador-sin-imagen", gf.cola(list(OPS.values()) + [falso]))

    def test_operador_nuevo_va_al_final(self):
        nuevo = dict(next(iter(OPS.values())), id="zz-nuevo")
        real = gf.imagen
        try:
            gf.imagen = lambda op_id, lang: real(next(iter(OPS)), lang)   # simula que ya tiene imagen
            q = gf.cola(list(OPS.values()) + [nuevo])
        finally:
            gf.imagen = real
        self.assertEqual(q[-1], "zz-nuevo")
        self.assertEqual(q[:3], [i for i in gf.ORDEN if i in OPS][:3])


class ContenidoTests(Base):
    def setUp(self):
        super().setUp()
        from datetime import date, timedelta
        self.run_feed("--empezar", "--hoy", "2026-11-01")
        for k in range(1, 40):
            self.run_feed("--hoy", (date(2026, 11, 1) + timedelta(days=k)).isoformat())

    def test_xml_valido_rss2(self):
        for lang, f in gf.FEEDS.items():
            root = ET.parse(f).getroot()
            self.assertEqual(root.tag, "rss")
            self.assertEqual(root.get("version"), "2.0")
            self.assertEqual(root.findtext("./channel/language"), lang)

    def test_ningun_pin_lleva_cifras_de_equipaje(self):
        for lang in gf.FEEDS:
            for it in self.items(lang):
                op = OPS[it.findtext("guid").split(f"willitboard-pin-{lang}-", 1)[1]]
                for campo in ("title", "description"):
                    txt = it.findtext(campo).replace(op["name"], "")
                    self.assertNotRegex(txt, r"\d", f"{op['id']} {lang} {campo}: {txt!r}")
                    self.assertNotRegex(txt.lower(), r"\b(cm|kg|lbs?)\b|€|£|\$")

    def test_enlace_es_la_ficha_del_operador(self):
        for lang in gf.FEEDS:
            for it in self.items(lang):
                op = OPS[it.findtext("guid").split(f"willitboard-pin-{lang}-", 1)[1]]
                link = it.findtext("link")
                self.assertEqual(link, build_site.BASE_URL + build_site.op_path(op, lang))
                ficha = build_site.op_outfile(op, lang)
                self.assertTrue(ficha.exists(), f"no existe {ficha}")

    def test_imagen_existe_pesa_lo_que_dice_y_es_del_dominio(self):
        for lang in gf.FEEDS:
            for it in self.items(lang):
                enc = it.find("enclosure")
                url = enc.get("url")
                self.assertTrue(url.startswith(build_site.BASE_URL + f"/pins/{lang}/"))
                f = build_site.OUT_DIR / url[len(build_site.BASE_URL) + 1:]
                self.assertTrue(f.exists(), f"falta {f}")
                self.assertEqual(int(enc.get("length")), f.stat().st_size)
                self.assertEqual(enc.get("type"), "image/jpeg")
                self.assertEqual(f.read_bytes()[:3], b"\xff\xd8\xff")   # JPEG de verdad

    def test_una_sola_imagen_por_pin(self):
        # Pinterest crea un Pin por cada imagen del item: dos etiquetas = dos Pines.
        for lang, f in gf.FEEDS.items():
            txt = f.read_text(encoding="utf-8")
            self.assertEqual(txt.count("<enclosure"), len(self.items(lang)))
            self.assertNotIn("media:content", txt)
            self.assertNotIn("<image>", txt)

    def test_posesivo_ingles(self):
        txt = gf.FEEDS["en"].read_text(encoding="utf-8")
        self.assertNotRegex(txt, r"s's\b")

    def test_espanol_sin_voseo(self):
        txt = gf.FEEDS["es"].read_text(encoding="utf-8").lower()
        for v in ("escribí", "mirá", "leéla", "fijate", "valija"):
            self.assertNotIn(v, txt)


class ImagenesTests(unittest.TestCase):
    def test_hay_imagen_jpeg_1000x1500_por_operador_y_por_idioma(self):
        import struct
        for op in OPS:
            for lang in gf.FEEDS:
                f = gf.imagen(op, lang)
                self.assertTrue(f.exists(), f"falta {f}")
                b = f.read_bytes()
                # dimensiones desde el marcador SOF del JPEG
                i = 2
                while i < len(b):
                    marker, size = b[i + 1], struct.unpack(">H", b[i + 2:i + 4])[0]
                    if marker in (0xC0, 0xC2):
                        h, w = struct.unpack(">HH", b[i + 5:i + 9])
                        self.assertEqual((w, h), (1000, 1500), str(f))
                        break
                    i += 2 + size
                else:
                    self.fail(f"sin dimensiones: {f}")

    def test_el_generador_de_imagenes_no_lee_cifras_del_dataset(self):
        src = (ROOT / "herramientas" / "generar_pines.py").read_text(encoding="utf-8")
        cuerpo = src.split("def pin_html", 1)[1].split("async def render", 1)[0]
        for campo in ("max_cm", "max_kg", "requires_addon", "included", "source_url", "verified_on"):
            self.assertNotIn(campo, cuerpo)


if __name__ == "__main__":
    unittest.main()
