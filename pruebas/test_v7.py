#!/usr/bin/env python3
"""
test_v7.py — calculadora estilo app (10/10/2026), en Chromium real.

Lo importante que verifica
--------------------------
1. Cada medida tiene flechas ▲▼ (▲ arriba, ▼ abajo). Subir con ▲ da
   EXACTAMENTE la misma clasificación que escribir el número a mano: las
   flechas no son un segundo cálculo.
2. En pantallas táctiles cada flecha mide al menos 44 px de alto, y en el
   teléfono las cuatro medidas van en 2 × 2.
3. La barra de arriba (logo, día/noche, idioma) entra en 320, 375 y 390 px
   en las tres clases de página, sin scroll horizontal. Error real: a 320 px
   ya se salía antes de este cambio.
4. En el teléfono el idioma se ve como EN / ES, pero el enlace se sigue
   llamando "English" / "Español" para lectores de pantalla.
5. El interruptor de día/noche cambia de lado y sigue marcando aria-pressed.

Uso:  python3 pruebas/test_v7.py
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent / "public"
PORT = 8797
BASE = f"http://127.0.0.1:{PORT}"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FALLA ") + label)


def classes(page) -> list:
    return page.eval_on_selector_all(
        "#results .rcard", "els => els.map(e => (e.dataset.op || e.id || '') + ':' + e.className)")


def ready(page, url):
    page.goto(url)
    page.wait_for_selector(".rcard", state="attached")


def main() -> int:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a, **k: None

    class Srv(socketserver.TCPServer):
        allow_reuse_address = True

    srv = Srv(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ------------------------------------------------ 1. flechas ▲▼
        print("\n[flechas de las medidas]")
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        for path, lang in (("/", "en"), ("/es/", "es")):
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)
            for fid in ("dim-a", "dim-b", "dim-c", "weight"):
                dirs = page.eval_on_selector_all(f'.panel .stepper .nudge[data-nudge="{fid}"]',
                                                 "els => els.map(e => e.dataset.dir)")
                check(dirs == ["1", "-1"], f"{lang} {fid}: flecha arriba sube, flecha abajo baja ({dirs})")
            check(page.locator(".panel .field__row .nudge").count() == 8
                  and "−" not in page.inner_text(".panel .fields"),
                  f"{lang}: no quedan botones − / + en la calculadora")
            start = page.input_value("#dim-a")
            page.click('.panel .nudge[data-nudge="dim-a"][data-dir="1"]')
            up = page.input_value("#dim-a")
            check(float(up) == float(start) + 1, f"{lang}: ▲ sube 1 cm ({start} -> {up})")
            after = classes(page)
            ref = ctx.new_page()
            ready(ref, BASE + path)
            ref.fill("#dim-a", up)
            check(classes(ref) == after, f"{lang}: ▲ da la misma clasificación que escribir {up} a mano")
            ref.close()
            page.click('.panel .nudge[data-nudge="weight"][data-dir="-1"]')
            check(page.input_value("#weight") == "8.5", f"{lang}: ▼ baja el peso medio kilo (9 -> {page.input_value('#weight')})")
            page.fill("#dim-c", "0")
            page.click('.panel .nudge[data-nudge="dim-c"][data-dir="-1"]')
            check(page.input_value("#dim-c") == "0", f"{lang}: ▼ nunca baja de 0")
            page.close()
        ctx.close()

        # ------------------------------------------------ 2. teléfono
        print("\n[teléfono]")
        for w in (320, 375, 390):
            m = browser.new_context(viewport={"width": w, "height": 800}, is_mobile=True, has_touch=True)
            page = m.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + "/es/")
            boxes = [page.locator(f"#{i}").locator("xpath=ancestor::div[contains(@class,'field')][1]").bounding_box()
                     for i in ("dim-a", "dim-b", "dim-c", "weight")]
            two_by_two = (abs(boxes[0]["y"] - boxes[1]["y"]) < 2 and abs(boxes[2]["y"] - boxes[3]["y"]) < 2
                          and boxes[2]["y"] > boxes[0]["y"] + 10 and boxes[1]["x"] > boxes[0]["x"] + 10)
            check(two_by_two, f"{w} px: las cuatro medidas van en 2 × 2")
            taps = page.eval_on_selector_all(".panel .stepper .nudge",
                                             "els => els.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; })")
            small = [t for t in taps if t[0] < 39.5 or t[1] < 43.5]
            check(not small, f"{w} px: cada flecha se puede tocar (≥ 40 × 44 px; la más chica "
                             f"{min(t[0] for t in taps):.0f} × {min(t[1] for t in taps):.0f})")
            inside = page.evaluate("""() => [...document.querySelectorAll('.panel .field')].every(f => {
                const r = f.getBoundingClientRect(), n = f.querySelector('input').getBoundingClientRect(),
                      s = f.querySelector('.stepper').getBoundingClientRect();
                return s.right <= r.right + 0.5 && n.right <= s.left + 0.5; })""")
            check(inside, f"{w} px: número, unidad y flechas entran en cada tarjeta")
            m.close()

        # ------------------------------------------------ 3. barra de arriba
        print("\n[barra de arriba sin desbordar]")
        for path in ("/", "/es/", "/es/aerolineas/ryanair/", "/es/privacidad/", "/airlines/easyjet/"):
            for w in (320, 375, 390):
                m = browser.new_context(viewport={"width": w, "height": 700}, is_mobile=True, has_touch=True)
                page = m.new_page()
                page.goto(BASE + path, wait_until="networkidle")
                r = page.evaluate("""() => {
                    const n = document.querySelector('.langnav').getBoundingClientRect(),
                          g = document.getElementById('theme-toggle').getBoundingClientRect(),
                          b = document.querySelector('.wordmark').getBoundingClientRect();
                    return {sw: document.documentElement.scrollWidth, iw: innerWidth,
                            nav: n.right, tog: [g.left, g.right], brand: b.right, navL: n.left}; }""")
                ok = (r["sw"] <= w and r["iw"] == w and r["nav"] <= w - 4
                      and r["brand"] <= r["tog"][0] and r["tog"][1] <= r["navL"])
                check(ok, f"{path} a {w} px: logo, día/noche e idioma entran sin pisarse "
                          f"(idioma termina en {r['nav']:.0f}, ancho de página {r['sw']})")
                m.close()

        # ------------------------------------------------ 4. idioma EN / ES
        print("\n[idioma en el teléfono]")
        m = browser.new_context(viewport={"width": 390, "height": 700}, is_mobile=True, has_touch=True)
        page = m.new_page()
        page.goto(BASE + "/es/")
        seen = page.eval_on_selector_all(".langnav a", """els => els.map(e => [...e.children]
            .filter(c => c.getBoundingClientRect().width > 2).map(c => c.textContent).join(''))""")
        names = [page.locator('.langnav a[hreflang="en"]').evaluate("e => e.textContent.replace('EN','').trim()"),
                 page.locator('.langnav a[hreflang="es"]').evaluate("e => e.textContent.replace('ES','').trim()")]
        check(seen == ["EN", "ES"], f"teléfono: se ve EN / ES ({seen})")
        check(names == ["English", "Español"], f"teléfono: el nombre completo sigue en el enlace ({names})")
        check(page.get_by_role("link", name="English").count() == 1,
              "teléfono: un lector de pantalla encuentra el enlace 'English'")
        m.close()
        d = browser.new_context(viewport={"width": 1200, "height": 700})
        page = d.new_page()
        page.goto(BASE + "/es/")
        seen = page.eval_on_selector_all(".langnav a", """els => els.map(e => [...e.children]
            .filter(c => c.getBoundingClientRect().width > 2).map(c => c.textContent).join(''))""")
        check(seen == ["English", "Español"], f"computadora: se ve English / Español ({seen})")

        # ------------------------------------------------ 5. interruptor día / noche
        print("\n[interruptor día / noche]")
        knob = "getComputedStyle(document.getElementById('theme-toggle'), '::before').transform"
        before = page.evaluate(knob)
        page.click("#theme-toggle")
        page.wait_for_timeout(400)
        after = page.evaluate(knob)
        check(page.get_attribute("#theme-toggle", "aria-pressed") == "true"
              and page.evaluate("document.documentElement.dataset.theme") == "dark",
              "al tocarlo pasa a noche y lo anuncia (aria-pressed)")
        check(before != after, f"la perilla cambia de lado ({before} -> {after})")
        sun, moon = page.evaluate("""() => ['sun','moon'].map(k => +getComputedStyle(
            document.querySelector('.themetoggle__' + k)).opacity)""")
        check(moon == 1 and sun > 0.5, f"de noche se ven la luna (activa) y el sol ({moon}, {sun})")
        page.click("#theme-toggle")
        check(page.get_attribute("#theme-toggle", "aria-pressed") == "false", "y vuelve a día")
        d.close()

        browser.close()
    srv.shutdown()

    check(not errors, "sin errores de JavaScript" + (f": {errors}" if errors else ""))
    bad = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(bad)}/{len(results)} comprobaciones OK")
    if bad:
        print("HAY FALLAS.")
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
