#!/usr/bin/env python3
"""
test_comparacion.py — sección "Cómo se compara X" de las fichas (18/10/2026).

Recalcula cada cifra por su cuenta, directo de public/operators.json, con una
cuenta escrita aparte de la de build_site.py, y la busca en el HTML generado.
Si las dos cuentas no coinciden, falla. Uso: python3 pruebas/test_comparacion.py
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
ops = json.loads((PUB / "operators.json").read_text(encoding="utf-8"))["operators"]
SEG = {"air": {"en": "airlines", "es": "es/aerolineas"},
       "rail": {"en": "trains", "es": "es/trenes"},
       "ferry": {"en": "ferries", "es": "es/ferris"}}
fails = []


def check(ok, msg):
    print(("  OK  " if ok else "  FALLA ") + msg)
    if not ok:
        fails.append(msg)


def dims(o, key):
    c = (o.get(key) or {}).get("max_cm") or {}
    v = [c.get("length"), c.get("width"), c.get("height")]
    return None if None in v else sorted(v, reverse=True)


def fits(bag, lim):
    b = sorted(bag, reverse=True)
    return b[0] <= lim[0] and b[1] <= lim[1] and b[2] <= lim[2]


def page(o, lang):
    p = PUB / SEG[o["type"]][lang] / o["id"] / "index.html"
    if not p.exists():  # el segmento en español puede tener otro nombre
        found = list(PUB.glob(f"es/*/{o['id']}/index.html")) if lang == "es" else []
        p = found[0] if found else p
    return p.read_text(encoding="utf-8")


def section_text(h):
    m = re.search(r'<section class="glass tile--cmpx.*?</section>', h, re.S)
    if not m:
        return None
    t = re.sub(r"<[^>]+>", " ", m.group(0))
    return re.sub(r"\s+", " ", html.unescape(t))


air = [o for o in ops if o["type"] == "air" and o["limit_type"] == "dimensional"
       and dims(o, "personal_item") and dims(o, "cabin_bag")]
n = len(air)
print(f"[comparación] {n} aerolíneas comparables")

for o in ops:
    for lang in ("en", "es"):
        txt = section_text(page(o, lang))
        if o not in air:
            check(txt is None, f"{lang}/{o['id']}: sin sección (no es aerolínea con medidas)")
            continue
        if txt is None:
            check(False, f"{lang}/{o['id']}: falta la sección")
            continue
        peers = [p for p in air if p is not o]
        m = len(peers)
        ok = True
        for key in ("cabin_bag", "personal_item"):
            k = sum(fits(dims(o, key), dims(p, key)) for p in peers)
            if k == m:
                want = f"all {m} other" if lang == "en" else f"en las otras {m}"
            elif k == 0:
                want = f"none of the other {m}" if lang == "en" else f"ninguna de las otras {m}"
            else:
                want = f"{k} of the other {m}" if lang == "en" else f"{k} de las otras {m}"
            if want not in txt:
                ok = False
                print(f"      {lang}/{o['id']} {key}: esperaba «{want}»")
            for p in peers:  # cada aerolínea que no la acepta, nombrada
                if not fits(dims(o, key), dims(p, key)) and p["name"] not in txt:
                    ok = False
        inc = sum(1 for p in air if p["cabin_bag"].get("included") is True)
        if inc and (f"{inc} of {n}" if lang == "en" else f"{inc} de {n}") not in txt:
            ok = False
            print(f"      {lang}/{o['id']}: esperaba {inc} de {n} incluidas")
        for bag in ((40, 25, 20), (55, 40, 23), (60, 42, 26)):
            k = sum(fits(bag, dims(p, "cabin_bag")) for p in air)
            want = ((f"Fits all {n}" if k == n else "Fits none" if k == 0 else f"Fits {k}") if lang == "en"
                    else (f"Entra en las {n}" if k == n else "No entra en ninguna" if k == 0 else f"Entra en {k}"))
            if want not in txt:
                ok = False
                print(f"      {lang}/{o['id']} {bag}: esperaba «{want}»")
        check(ok, f"{lang}/{o['id']}: cifras = recálculo independiente")

# el ejemplo que se mostró en el mockup del 18/10
r = section_text(page(next(o for o in ops if o["id"] == "ryanair"), "en"))
check("20 cm front to back" in r and "23 to 25 cm" in r and "Vueling" in r,
      "Ryanair: la menos profunda, 20 cm contra 23–25, empatada con Vueling")
check("Too big by 3 cm" in r, "Ryanair: el trolley 55×40×23 se pasa 3 cm")

print()
if fails:
    print(f"{len(fails)} fallas.")
    sys.exit(1)
print("Todo bien.")
