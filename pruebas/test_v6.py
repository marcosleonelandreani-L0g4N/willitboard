#!/usr/bin/env python3
"""
test_v6.py — lo que agregó el diseño v6 (01/10/2026), en Chromium real.

1. RESUMEN POR MEDIO: los números al lado de las medidas suman exactamente lo
   mismo que los veredictos de la lista (no hay un segundo cálculo). Tocar uno
   filtra por ese color y abre solo ese grupo; tocarlo de nuevo saca el filtro.
2. BUSCADOR DE ARRIBA: encuentra operadores sin importar tildes ni mayúsculas y
   enlaza a su ficha real; encuentra las guías; dice cuando no hay nada.
3. PRODUCTOS OCULTOS: con el products.json real (sin productos verificados) el
   bloque de bolsos no aparece. Con un products.json de PRUEBA inyectado, aparece,
   cada bolso dice en cuántas aerolíneas entra gratis según verdictFor(), y
   "Probar" carga sus medidas y muestra qué producto se está probando.
4. VOLVER ARRIBA: aparece al bajar y lleva arriba de todo, en la home y en una ficha.
5. Las cuatro diapositivas tienen ilustración y ninguna rompe el ancho del teléfono.

Uso:  python3 pruebas/test_v6.py
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent / "public"
PORT = 8798
BASE = f"http://127.0.0.1:{PORT}"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FAIL ") + label)


# Productos de PRUEBA: no existen. Uno chico (40x25x20) y uno grande (55x40x20).
FAKE_PRODUCTS = {"schema_version": "1.0", "generated_on": "2026-10-01", "products": [
    {"id": "test-chico", "name": "Bolso Chico", "brand": "Marca Test", "category": "underseat-bags",
     "dims_cm": [40, 25, 20], "dims_include_wheels": None, "empty_kg": 0.5, "capacity_l": 20,
     "price_band": "€", "links": {"amazon_de": "https://example.com/chico"},
     "source_url": "https://example.com/f", "verified_on": "2026-10-01", "days_since_verified": 0},
    {"id": "test-grande", "name": "Valija Grande", "brand": "Marca Test", "category": "cabin-suitcases",
     "dims_cm": [55, 40, 20], "dims_include_wheels": True, "empty_kg": 2.5, "capacity_l": 40,
     "price_band": "€€", "links": {"amazon_de": "https://example.com/grande"},
     "source_url": "https://example.com/g", "verified_on": "2026-10-01", "days_since_verified": 0},
]}


def main() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    class Srv(socketserver.TCPServer):
        allow_reuse_address = True

    srv = Srv(("127.0.0.1", PORT), partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []
    real_products = json.loads((ROOT / "products.json").read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ------------------------------------------------ 1. resumen por medio
        print("\n[resumen por medio, en los dos idiomas]")
        for path in ("/", "/es/"):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            page.wait_for_selector("#modes .cnt", state="attached")
            same = page.evaluate("""() => {
                const fromModes = {}; const fromList = {};
                document.querySelectorAll('#modes .mode').forEach((m, i) => {});
                const types = [...document.querySelectorAll('.tgroup')].map(g => g.dataset.type);
                let ok = true;
                document.querySelectorAll('#modes .mode').forEach((m, i) => {
                    const total = [...m.querySelectorAll('.cnt')].reduce((n, b) => n + parseInt(b.textContent.replace(/\\D/g, ''), 10), 0);
                    const g = document.querySelector('.tgroup[data-type="' + types[i] + '"]');
                    if (!g || g.querySelectorAll('.rcard').length !== total) ok = false;
                });
                return ok && document.querySelectorAll('#modes .mode').length === types.length;
            }""")
            check(same, f"{path}: cada medio suma lo mismo que su grupo de la lista")
            page.locator("#modes .mode").first.locator(".cnt").first.click()
            page.wait_for_timeout(200)
            st = page.evaluate("""() => ({
                open: [...document.querySelectorAll('.tgroup')].filter(g => g.open).map(g => g.dataset.type),
                bands: [...new Set([...document.querySelectorAll('.tgroup[open] .rcard')].filter(c => !c.hidden).map(c => c.dataset.band))]
            })""")
            check(st["open"] == ["air"] and len(st["bands"]) == 1,
                  f"{path}: tocar un número abre solo ese grupo y filtra un color ({st})")
            page.locator("#modes .mode").first.locator(".cnt").first.click()
            page.wait_for_timeout(200)
            hidden = page.evaluate("[...document.querySelectorAll('.rcard')].filter(c => c.hidden).length")
            check(hidden == 0, f"{path}: tocarlo otra vez saca el filtro")
            check(page.evaluate("document.documentElement.scrollWidth") <= 390,
                  f"{path}: sin scroll horizontal a 390 px")
            ctx.close()

        # ------------------------------------------------ 2. buscador de arriba
        print("\n[buscador de arriba]")
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/es/")
        page.wait_for_selector("#modes .cnt", state="attached")
        page.fill("#gq", "RYAN")
        page.wait_for_timeout(150)
        hrefs = page.eval_on_selector_all("#gsug a", "els => els.map(a => a.getAttribute('href'))")
        check("/es/aerolineas/ryanair/" in hrefs, f"encuentra Ryanair y enlaza su ficha ({hrefs})")
        check(all((ROOT / h.strip("/") / "index.html").exists() for h in hrefs), "los enlaces del buscador existen")
        page.fill("#gq", "medir")
        page.wait_for_timeout(150)
        check(page.locator("#gsug a").count() >= 1, "encuentra la guía de cómo medir")
        page.fill("#gq", "zzzz")
        page.wait_for_timeout(150)
        check(page.locator("#gsug .gsug__none").count() == 1, "dice cuando no hay resultados")
        page.keyboard.press("Escape")
        check(page.locator("#gsug").is_hidden(), "Escape cierra las sugerencias")

        # ------------------------------------------------ 3a. productos reales
        print("\n[productos]")
        check(page.locator("#reco").is_hidden() or bool(real_products["products"]),
              f"con el products.json real ({len(real_products['products'])} productos) no aparece un bloque vacío")
        ctx.close()

        # ------------------------------------------------ 3b. productos de prueba
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        ctx.route("**/products.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                         body=json.dumps(FAKE_PRODUCTS)))
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/es/")
        page.wait_for_selector("#reco:not([hidden]) .pc", state="attached")
        n_cards = page.locator("#reco .pc").count()
        check(n_cards >= 1, f"con productos verificados, el bloque aparece ({n_cards} bolsos)")
        # el número del bolso chico tiene que coincidir con el comprobador cargado con sus medidas
        badge = page.locator("#reco .pc").first.locator(".pc__badge").inner_text()
        page.locator("#reco .pc").first.locator(".pc__try").click()
        page.wait_for_timeout(250)
        vals = [page.input_value(s) for s in ("#dim-a", "#dim-b", "#dim-c", "#weight")]
        check(vals == ["40", "25", "20", ""], f"Probar carga las medidas del bolso y deja el peso vacío ({vals})")
        free_now = page.evaluate("document.querySelectorAll('.tgroup[data-type=\"air\"] .rcard[data-band=\"pass\"]').length")
        check(str(free_now) in badge, f"el número del bolso coincide con el comprobador ({badge!r} vs {free_now})")
        check("Bolso Chico" in page.inner_text("#chosen"), "se ve qué producto se está probando")
        check(page.get_attribute("#chosen a", "rel") == "sponsored noopener", "el enlace a la tienda va marcado como patrocinado")
        page.fill("#dim-a", "41")
        page.wait_for_timeout(150)
        check(page.locator("#chosen").is_hidden(), "al cambiar una medida a mano, deja de decir que es el producto")
        page.fill("#gq", "valija")
        page.wait_for_timeout(150)
        check(page.locator("#gsug [data-pi]").count() == 1, "el buscador de arriba también encuentra productos")
        ctx.close()

        # ------------------------------------------------ 4. volver arriba
        print("\n[volver arriba]")
        for path in ("/es/", "/es/aerolineas/ryanair/"):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            page.wait_for_timeout(300)
            check(page.locator("#totop").is_hidden(), f"{path}: arriba de todo no se ve")
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(500)
            check(page.locator("#totop").is_visible(), f"{path}: al bajar aparece")
            page.click("#totop")
            page.wait_for_timeout(500)
            check(page.evaluate("window.scrollY") == 0, f"{path}: lleva arriba de todo")
            ctx.close()

        # ------------------------------------------------ 5. carrusel
        print("\n[carrusel]")
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(BASE + "/")
        arts = page.eval_on_selector_all(".slide__art svg", "els => els.length")
        check(arts == 4, f"las cuatro diapositivas tienen ilustración ({arts})")

        # Flechas (10/10/2026): avanzan, retroceden y dan la vuelta.
        cur = "document.querySelector('#slides-dots [aria-current]').getAttribute('aria-controls')"
        page.click("#slides-next"); page.wait_for_timeout(700)
        check(page.evaluate(cur) == "slide-2", "la flecha derecha pasa a la diapositiva 2")
        page.click("#slides-prev"); page.click("#slides-prev"); page.wait_for_timeout(900)
        check(page.evaluate(cur) == "slide-4", "la flecha izquierda da la vuelta hasta la última")
        page.focus("#slides-next"); page.keyboard.press("ArrowRight"); page.wait_for_timeout(900)
        check(page.evaluate(cur) == "slide-1", "la tecla → avanza con el foco en el carrusel")
        check(bool(page.get_attribute("#slides-prev", "aria-label")) and bool(page.get_attribute("#slides-next", "aria-label")),
              "las dos flechas tienen nombre para lectores de pantalla")
        # En el teléfono, la fila de botones no pisa el panel de texto.
        clash = page.evaluate("""() => {
          const n = document.querySelector('.slides__nav').getBoundingClientRect();
          return [...document.querySelectorAll('.slide__text')].some(e => {
            const t = e.getBoundingClientRect();
            return t.left >= 0 && t.left < innerWidth && n.top < t.bottom;
          });
        }""")
        check(not clash, "en el teléfono, las flechas no tapan el texto de la diapositiva")
        ctx.close()
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
