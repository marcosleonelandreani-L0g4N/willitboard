#!/usr/bin/env python3
"""
test_region.py — selector de región (03/10/2026), en Chromium real.

1. VALOR INICIAL: zona horaria de Argentina + es-AR arranca en Latinoamérica;
   Madrid + es-ES y Copenhague + en arrancan en Europa; ?region= manda sobre todo.
2. FILTRO: la lista, los números por medio y el "entra gratis en X de Y" de los
   productos cuentan SOLO los operadores de la región elegida (contra el
   operators.json real, no contra números escritos a mano).
3. URL, NO NAVEGADOR: cambiar de región escribe ?region= en la URL y no guarda
   nada en localStorage, sessionStorage ni cookies (lo promete /cookies/).
4. Con una sola región en el dataset, el selector no aparece.
5. Sin scroll horizontal a 390 px.

Uso:  python3 pruebas/test_region.py
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
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
results: list[tuple[bool, str]] = []
DATA = json.loads((ROOT / "operators.json").read_text(encoding="utf-8"))
IDS = {r: sorted(o["id"] for o in DATA["operators"] if o["region"] == r) for r in ("EU", "LATAM")}
AIR = {r: sum(1 for o in DATA["operators"] if o["region"] == r and o["type"] == "air") for r in ("EU", "LATAM")}

FAKE_PRODUCTS = {"schema_version": "1.0", "generated_on": "2026-10-03", "products": [
    {"id": "test-chico", "name": "Bolso Chico", "brand": "Marca Test", "category": "underseat-bags",
     "dims_cm": [30, 20, 15], "dims_include_wheels": None, "empty_kg": 0.5, "capacity_l": 10,
     "price_band": "€", "links": {"amazon_de": "https://example.com/chico"},
     "source_url": "https://example.com/f", "verified_on": "2026-10-03", "days_since_verified": 0}]}


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FAIL ") + label)


def card_ids(page) -> list[str]:
    return sorted(page.eval_on_selector_all(".tgroup .rcard", "els => els.map(e => e.dataset.id || e.id)"))


def main() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    class Srv(socketserver.TCPServer):
        allow_reuse_address = True

    srv = Srv(("127.0.0.1", PORT), partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []
    check(IDS["LATAM"] and IDS["EU"], f"el dataset tiene dos regiones (EU {len(IDS['EU'])}, LATAM {len(IDS['LATAM'])})")

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def open_page(path, locale, tz, products=None, data=None):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale=locale,
                                      timezone_id=tz, reduced_motion="reduce")
            if products is not None:
                ctx.route("**/products.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                 body=json.dumps(products)))
            if data is not None:
                ctx.route("**/operators.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                  body=json.dumps(data)))
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            page.wait_for_selector("#modes .cnt", state="attached")
            page.wait_for_timeout(150)
            return ctx, page

        def pressed(page):
            return page.get_attribute('#region button[aria-pressed="true"]', "data-region")

        def n_cards(page):
            return page.locator(".tgroup .rcard").count()

        def modes_total(page):
            return page.evaluate("""() => [...document.querySelectorAll('#modes .cnt')]
                .reduce((n, b) => n + parseInt(b.textContent.replace(/\\D/g, ''), 10), 0)""")

        print("\n[valor inicial]")
        n_eu = len(IDS["EU"]); n_la = len(IDS["LATAM"]); n_all = len(DATA["operators"])
        for path, locale, tz, want, n in (
            ("/es/", "es-AR", "America/Argentina/Buenos_Aires", "LATAM", n_la),
            ("/es/", "es-MX", "America/Mexico_City", "LATAM", n_la),
            ("/es/", "es-ES", "Europe/Madrid", "EU", n_eu),
            ("/", "en-GB", "Europe/Copenhagen", "EU", n_eu),
            ("/", "en-US", "America/New_York", "all", n_all),
            ("/es/?region=eu", "es-AR", "America/Argentina/Buenos_Aires", "EU", n_eu),
            ("/?region=latam", "en-GB", "Europe/London", "LATAM", n_la),
        ):
            ctx, page = open_page(path, locale, tz)
            check(page.locator("#region").is_visible(), f"{path} {locale}: el selector se ve")
            check(pressed(page) == want and n_cards(page) == n,
                  f"{path} {locale} {tz}: arranca en {want} con {n} operadores ({pressed(page)}, {n_cards(page)})")
            check(modes_total(page) == n, f"{path} {locale}: los números por medio suman {n} ({modes_total(page)})")
            ctx.close()

        print("\n[filtro, URL y nada guardado en el navegador]")
        ctx, page = open_page("/es/", "es-AR", "America/Argentina/Buenos_Aires")
        types = page.eval_on_selector_all(".tgroup", "els => els.map(e => e.dataset.type)")
        check(types == ["air"], f"en Latinoamérica solo aparecen aerolíneas, sin trenes ni ferris ({types})")
        page.click('#region button[data-region="all"]')
        page.wait_for_timeout(150)
        check(n_cards(page) == n_all, f"Todas muestra los {n_all} operadores ({n_cards(page)})")
        check("region=all" in page.url, f"la elección queda en la URL ({page.url})")
        page.reload()
        page.wait_for_selector("#modes .cnt", state="attached")
        check(pressed(page) == "all", "al recargar se mantiene la elección (por la URL)")
        page.click('#region button[data-region="EU"]')
        page.wait_for_timeout(150)
        check(n_cards(page) == n_eu and pressed(page) == "EU", f"Europa muestra {n_eu}")
        stored = page.evaluate("() => ({ls: localStorage.length, ss: sessionStorage.length, ck: document.cookie})")
        check(stored == {"ls": 0, "ss": 0, "ck": ""}, f"no se guarda nada en el navegador ({stored})")
        check(page.evaluate("document.documentElement.scrollWidth") <= 390, "sin scroll horizontal a 390 px")
        cut = page.evaluate("""() => [...document.querySelectorAll('#region button')]
            .filter(b => b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)""")
        check(not cut, f"ningún botón de región queda cortado a 390 px ({cut})")
        ctx.close()

        print("\n[productos cuentan solo la región elegida]")
        for locale, tz, reg in (("es-AR", "America/Argentina/Buenos_Aires", "LATAM"), ("es-ES", "Europe/Madrid", "EU")):
            ctx, page = open_page("/es/", locale, tz, products=FAKE_PRODUCTS)
            page.wait_for_selector("#reco:not([hidden]) .pc", state="attached")
            badge = page.locator("#reco .pc").first.locator(".pc__badge").inner_text()
            check(f"de {AIR[reg]}" in badge, f"{reg}: el bolso cuenta sobre {AIR[reg]} aerolíneas ({badge!r})")
            ctx.close()

        print("\n[una sola región]")
        solo = dict(DATA, operators=[o for o in DATA["operators"] if o["region"] == "EU"])
        ctx, page = open_page("/es/?region=latam", "es-AR", "America/Argentina/Buenos_Aires", data=solo)
        check(page.locator("#region").is_hidden(), "con una sola región, el selector no aparece")
        check(n_cards(page) == len(solo["operators"]), "y un ?region= sin operadores no deja la lista vacía")
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
