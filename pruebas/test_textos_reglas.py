"""
Guardián de textos de las reglas escritas (27/10/2026).

El sitio decía que los operadores de regla escrita "describen qué se puede
llevar en lugar de publicar medidas". Era falso para Eurostar (85 / 75 cm),
Stena Line (60 x 50 x 40 cm en las rutas de Irlanda) y Renfe (85 x 55 x 35 cm):
publican medidas, pero su regla no se reduce a una sola medida por maleta.

Es el mismo error que se corrigió el 25/10/2026 en la meta description. Esta
prueba falla si alguna de esas frases vuelve a un diccionario o a una página
generada.

    python3 pruebas/test_textos_reglas.py
"""
from __future__ import annotations

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLIC = RAIZ / "public"
I18N = RAIZ / "sitio" / "i18n"

PROHIBIDAS = (
    "en lugar de publicar medidas",
    "en vez de publicar un tamaño",
    "No publica medidas: describe una regla",
    "Operadores que publican una regla, no medidas",
    "instead of publishing measurements",
    "instead of publishing a size",
    "No measurements published — they describe a rule instead",
    "Operators that publish a rule, not measurements",
)


class TextosReglasTests(unittest.TestCase):
    def _buscar(self, archivos):
        hallazgos = []
        for f in archivos:
            texto = f.read_text(encoding="utf-8")
            for frase in PROHIBIDAS:
                if frase.lower() in texto.lower():
                    hallazgos.append(f"{f.relative_to(RAIZ)}: «{frase}»")
        return hallazgos

    def test_diccionarios_sin_la_frase_falsa(self):
        archivos = sorted(I18N.glob("*.json"))
        self.assertTrue(archivos, "no se encontraron diccionarios")
        self.assertEqual(self._buscar(archivos), [])

    def test_paginas_generadas_sin_la_frase_falsa(self):
        archivos = sorted(PUBLIC.rglob("*.html"))
        self.assertTrue(archivos, "no hay páginas generadas en public/")
        self.assertEqual(self._buscar(archivos), [])

    def test_las_fichas_de_regla_escrita_usan_el_texto_nuevo(self):
        for ruta, frase in (("trains/renfe/index.html", "doesn't come down to one size per bag"),
                            ("es/trenes/renfe/index.html", "no se reduce a una sola medida por maleta"),
                            ("trains/eurostar/index.html", "doesn't come down to one size per bag"),
                            ("ferries/stena-line/index.html", "doesn't come down to one size per bag")):
            texto = (PUBLIC / ruta).read_text(encoding="utf-8")
            self.assertIn(frase, texto, ruta)


if __name__ == "__main__":
    unittest.main(verbosity=1)
