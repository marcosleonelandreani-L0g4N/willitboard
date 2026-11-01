"""
Guardián de las preguntas frecuentes de las fichas (01/11/2026).

Las respuestas se arman solo con campos del dataset. Esta prueba lee las
páginas generadas y falla si:

  - una aerolínea con medidas no tiene el bloque, o un tren o ferri sí lo tiene;
  - aparece en el bloque una cifra que no está en el registro de ese operador
    en public/operators.json (medidas, pesos);
  - la respuesta sobre el extra no nombra el extra del dataset;
  - una respuesta dice "incluido" cuando el dataset dice que no, o al revés;
  - el bloque trae tuteo en imperativo ("compra", "mide"...).

    python3 pruebas/test_faq.py
"""
from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLIC = RAIZ / "public"
sys.path.insert(0, str(RAIZ))
import build_site  # noqa: E402

DATA = json.loads((PUBLIC / "operators.json").read_text(encoding="utf-8"))
OPS = [op for op in DATA["operators"] if build_site.is_publishable(op)[0]]
LANGS = ("en", "es")

BLOQUE = re.compile(r'<section class="glass tile--faq[^"]*"[^>]*>.*?</section>', re.S)


def bloque(op, lang):
    page = build_site.op_outfile(op, lang).read_text(encoding="utf-8")
    m = BLOQUE.search(page)
    return m.group(0) if m else None


def texto(fragmento: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragmento))).strip()


def cifras_permitidas(op) -> set[str]:
    out = set()
    for key in ("personal_item", "cabin_bag"):
        a = op.get(key) or {}
        for v in (a.get("max_cm") or {}).values():
            if v is not None:
                out.add(build_site.fmt_num(v))
        if a.get("max_kg") is not None:
            out.add(build_site.fmt_num(a["max_kg"]))
    if op.get("combined_max_kg") is not None:
        out.add(build_site.fmt_num(op["combined_max_kg"]))
    return out


def respuestas(fragmento: str) -> list[tuple[str, str]]:
    pares = re.findall(r"<h3>(.*?)</h3>.*?</summary>\s*<p>(.*?)</p>", fragmento, re.S)
    return [(texto(q), texto(a)) for q, a in pares]


class FaqTests(unittest.TestCase):
    def test_solo_aerolineas_con_medidas(self):
        for op in OPS:
            for lang in LANGS:
                con = op["type"] == "air" and op["limit_type"] == "dimensional"
                with self.subTest(op=op["id"], lang=lang):
                    if con:
                        self.assertIsNotNone(bloque(op, lang), "falta el bloque de preguntas")
                    else:
                        self.assertIsNone(bloque(op, lang), "un tren o ferri no lleva preguntas")

    def test_cifras_salen_del_dataset(self):
        for op in OPS:
            permitidas = cifras_permitidas(op)
            for lang in LANGS:
                b = bloque(op, lang)
                if not b:
                    continue
                # sacamos el nombre del operador y del extra, que pueden traer números ("Jet2")
                limpio = texto(b).replace(op["name"], "")
                addon = (op.get("cabin_bag") or {}).get("requires_addon") or ""
                limpio = limpio.replace(addon, "")
                for n in re.findall(r"\d+(?:[.,]\d+)?", limpio):
                    with self.subTest(op=op["id"], lang=lang, cifra=n):
                        self.assertIn(n.replace(",", "."), permitidas)

    def test_medidas_completas_y_en_orden(self):
        for op in OPS:
            for lang in LANGS:
                b = bloque(op, lang)
                if not b:
                    continue
                t = texto(b)
                for key in ("personal_item", "cabin_bag"):
                    d = build_site.triple((op.get(key) or {}).get("max_cm"))
                    if d and (key == "cabin_bag" or (op[key].get("included") is True)):
                        with self.subTest(op=op["id"], lang=lang, bulto=key):
                            self.assertIn(" × ".join(str(x) for x in d), t)

    def test_incluido_o_extra_coincide(self):
        for op in OPS:
            cab = op.get("cabin_bag") or {}
            for lang in LANGS:
                b = bloque(op, lang)
                if not b:
                    continue
                pares = respuestas(b)
                ambos = [a for q, a in pares if q.startswith(("Can I bring", "¿Puedo llevar"))]
                if not ambos:
                    continue
                a = ambos[0]
                with self.subTest(op=op["id"], lang=lang):
                    if cab.get("included") is True:
                        self.assertTrue(a.startswith(("Yes.", "Sí.")), a)
                    else:
                        self.assertFalse(a.startswith(("Yes.", "Sí.")), a)
                        if cab.get("requires_addon"):
                            self.assertIn(cab["requires_addon"], a)

    def test_sin_tuteo_en_imperativo(self):
        prohibidas = re.compile(r"\b(compra|mide|paga|lleva|revisa|consulta|comprueba)\b", re.I)
        for op in OPS:
            b = bloque(op, "es")
            if b:
                with self.subTest(op=op["id"]):
                    self.assertIsNone(prohibidas.search(texto(b)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
