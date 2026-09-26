#!/usr/bin/env python3
"""
test_adsense.py — el interruptor de AdSense de build_site.py.

Lo que tiene que valer siempre
------------------------------
1. Sin ID de editor (hoy): ninguna página menciona AdSense y no hay ads.txt.
2. Con ID (paso 1, verificación): TODAS las páginas llevan la etiqueta meta con
   ese ID y public/ads.txt tiene exactamente la línea de la guía de Google.
3. En ningún caso aparece el código que muestra anuncios (adsbygoogle.js):
   eso es el paso 2 y tiene que llegar junto con privacidad, cookies y
   divulgación reescritas. Cuando llegue, esta prueba cambia con él.
4. Un ID mal copiado frena el build.

Uso:  python3 -m unittest pruebas.test_adsense
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_site  # noqa: E402

PUBLIC = ROOT / "public"
PAGES = sorted(p for p in PUBLIC.rglob("*.html") if "fonts" not in p.parts)


class AdsenseSwitch(unittest.TestCase):
    def tearDown(self):
        build_site.ADSENSE_PUB_ID = self._saved

    def setUp(self):
        self._saved = build_site.ADSENSE_PUB_ID

    def test_public_matches_switch(self):
        """Lo publicado en public/ coincide con el valor del interruptor."""
        self.assertTrue(PAGES, "public/ está vacío: correr build_site.py primero")
        pub = build_site.adsense_pub_id()
        ads = PUBLIC / "ads.txt"
        for page in PAGES:
            html = page.read_text(encoding="utf-8")
            metas = re.findall(r'<meta name="google-adsense-account" content="([^"]+)">', html)
            if pub:
                self.assertEqual(metas, [f"ca-{pub}"], page)
            else:
                self.assertEqual(metas, [], page)
            # Paso 2 todavía no: nada que cargue anuncios.
            self.assertNotIn("adsbygoogle", html, page)
            self.assertNotIn("googlesyndication", html, page)
        if pub:
            self.assertEqual(ads.read_text(encoding="utf-8"), build_site.ads_txt_line(pub) + "\n")
        else:
            self.assertFalse(ads.exists(), "hay un ads.txt sin ID de editor")

    def test_meta_when_id_is_set(self):
        build_site.ADSENSE_PUB_ID = "pub-1234567890123456"
        S = build_site.load_strings("en")
        head = build_site.head_extra("en", S, "https://willitboard.com/", "T", "D")
        self.assertIn('<meta name="google-adsense-account" content="ca-pub-1234567890123456">', head)
        self.assertEqual(build_site.ads_txt_line("pub-1234567890123456"),
                         "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0")

    def test_no_meta_when_empty(self):
        build_site.ADSENSE_PUB_ID = ""
        S = build_site.load_strings("es")
        head = build_site.head_extra("es", S, "https://willitboard.com/es/", "T", "D")
        self.assertNotIn("google-adsense-account", head)

    def test_both_id_forms_are_accepted(self):
        for good in ("pub-1234567890123456", "ca-pub-1234567890123456", "  pub-1234567890123456 "):
            build_site.ADSENSE_PUB_ID = good
            self.assertEqual(build_site.adsense_pub_id(), "pub-1234567890123456", good)

    def test_bad_ids_stop_the_build(self):
        for bad in ("pub-123", "pub-12345678901234567", "ca-pub-12345",
                    "1234567890123456", "pub-12345678901234a6", "ca-1234567890123456"):
            build_site.ADSENSE_PUB_ID = bad
            with self.assertRaises(SystemExit, msg=bad):
                build_site.adsense_pub_id()


if __name__ == "__main__":
    unittest.main()
