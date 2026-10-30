#!/usr/bin/env python3
"""
test_v6.py — lo que agregó el diseño v6 (01/10/2026), en Chromium real.

1. RESUMEN POR MEDIO: los números al lado de las medidas suman exactamente lo
   mismo que los veredictos de la lista (no hay un segundo cálculo). Tocar uno
   filtra por ese color y abre solo ese grupo; tocarlo de nuevo saca el filtro.
2. (30/10/2026) El buscador de abajo se retiró: se comprueba que no está y que el
   índice sigue enlazando todas las fichas y las guías.
3. PRODUCTOS OCULTOS: con el products.json real (sin productos verificados) el
   bloque de bolsos no aparece. Con un products.json de PRUEBA inyectado, aparece,
   cada bolso dice en cuántas aerolíneas entra gratis según verdictFor(), y
   "Probar" carga sus medidas y muestra qué producto se está probando.
4. VOLVER ARRIBA: aparece al bajar y lleva arriba de todo, en la home y en una ficha.
5. (v9, 20/10/2026) Sin carrusel: en el teléfono las medidas se ven sin bajar, y los
   dos atajos de la cabecera llevan a donde dicen.

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

        # ------------------------------------------------ 2. buscador de abajo: RETIRADO (30/10/2026)
        # "Buscar las reglas de una compañía" se sacó: las fichas y las guías ya
        # están enlazadas en el índice, y "¿Con qué compañía viajas?" lleva a cada ficha.
        print("\n[buscador de abajo retirado]")
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/es/")
        page.wait_for_selector("#modes .cnt", state="attached")
        check(page.locator("#gq, #lookup, .gsearch").count() == 0, "ya no está el buscador de abajo")
        idx = page.eval_on_selector_all(".index a", "els => els.map(a => a.getAttribute('href'))")
        check("/es/aerolineas/ryanair/" in idx and any("medir" in h for h in idx),
              f"el índice sigue enlazando las fichas y la guía de cómo medir ({len(idx)} enlaces)")
        check(all((ROOT / h.strip("/") / "index.html").exists() for h in idx), "los enlaces del índice existen")

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

        # ------------------------------------------------ 5. cabecera sin carrusel (v9)
        print("\n[cabecera: medidas a la vista y atajos]")
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        for path in ("/", "/es/"):
            page.goto(BASE + path)
            check(page.locator("#slides, .slides").count() == 0, f"{path}: no hay carrusel")
            box = page.evaluate("""() => { const r = document.getElementById('dim-a').getBoundingClientRect();
                                         const c = document.getElementById('cta-results').getBoundingClientRect();
                                         return [Math.round(r.top), Math.round(c.bottom)]; }""")
            check(box[0] < 844, f"{path}: el primer campo de medidas se ve sin bajar (empieza en {box[0]} px)")
            page.click('[data-quick="banned"]')
            page.wait_for_timeout(1500)  # el sitio usa desplazamiento suave
            t = page.evaluate("Math.round(document.getElementById('banned').getBoundingClientRect().top)")
            check(-5 <= t < 200, f"{path}: el atajo «qué no puedo llevar» lleva a la franja ({t} px)")
            page.goto(BASE + path)
            page.click('[data-quick="rules"]')
            page.wait_for_timeout(1500)
            top = page.evaluate("Math.round(document.getElementById('mine').getBoundingClientRect().top)")
            check(-5 <= top < 300 and page.evaluate("document.activeElement.id") == "mine-q",
                  f"{path}: el atajo de reglas lleva a «¿Con qué compañía viajas?» con el cursor puesto ({top} px)")
        ctx.close()

        # ------------------------------------------------ 6. objetos prohibidos (10/10/2026)
        # Solo enlaces a páginas oficiales; nunca una lista propia.
        print("\n[objetos prohibidos]")
        for path, eu in (("/", "index_en.htm"), ("/es/", "index_es.htm")):
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            page = ctx.new_page()
            page.goto(BASE + path)
            check(page.locator("#banned").count() == 1, f"{path}: la franja existe")
            check(page.locator("#banned").get_attribute("open") is None, f"{path}: arranca cerrada")
            page.click("#banned summary")
            check(page.locator("#banned .banned__links").is_visible(), f"{path}: al tocarla se abre")
            hrefs = page.eval_on_selector_all("#banned a", "els => els.map(e => e.href)")
            official = ("https://europa.eu/", "https://www.gov.uk/", "https://www.dgac.gob.cl/",
                        "https://www.aeropuertosgap.com.mx/", "https://www.aerocivil.gov.co/")
            ok_domains = all(h.startswith(official) for h in hrefs)
            check(len(hrefs) >= 2 and ok_domains, f"{path}: solo enlaza páginas oficiales ({hrefs})")
            check(any(h.endswith(eu) for h in hrefs), f"{path}: la página de la UE va en el idioma de la página")
            rels = page.eval_on_selector_all("#banned a", "els => els.map(e => e.rel)")
            check(all("noopener" in r for r in rels), f"{path}: los enlaces externos llevan noopener")
            check(page.evaluate("document.documentElement.scrollWidth") <= 390, f"{path}: abierta, no desborda en el teléfono")
            ctx.close()

        # ------------------------------------------------ 6b. fichas con íconos: candado de verificación
        # Las fichas son condiciones de equipaje: sin la fecha de Marcos
        # (BANNED_VERIFIED_ON) NO se publican, y "BORRADOR" nunca llega a public/.
        print("\n[objetos prohibidos: fichas y candado]")
        sys.path.insert(0, str(ROOT.parent))
        import importlib
        bs = importlib.import_module("build_site")
        for lang in ("en", "es"):
            html_pub = (ROOT / ("index.html" if lang == "en" else "es/index.html")).read_text(encoding="utf-8")
            date = bs.BANNED_VERIFIED_ON.strip()
            n_pub = html_pub.count('<li class="nogo__tile')
            check(n_pub == (len(bs.BANNED_ITEMS) if date else 0),
                  f"{lang}: fichas publicadas solo con fecha humana (fecha={date or 'vacía'}, fichas={n_pub})")
            check("BORRADOR" not in html_pub, f"{lang}: la marca BORRADOR nunca se publica")
            S = bs.load_strings(lang)
            sample = bs.block_banned(lang, S, verified_on="2000-01-01")
            check(sample.count('<li class="nogo__tile') == 6, f"{lang}: con fecha salen las 6 fichas")
            check("2000-01-01" in sample and "europa.eu/youreurope" in sample,
                  f"{lang}: con fecha, muestra la fecha y enlaza la fuente de la UE")
            states = [st for _, st, _ in bs.BANNED_ITEMS]
            check(all(f'nogo__tile--{st}' in sample for st in set(states)), f"{lang}: cada estado tiene su estilo")
            check(sample.count('class="nogo__state"') == 6, f"{lang}: cada ficha dice su estado en texto, no solo con color")
            empty = bs.block_banned(lang, S, verified_on="")
            check('nogo__tile' not in empty and 'banned__links' in empty, f"{lang}: sin fecha, solo los enlaces oficiales")

        # ------------------------------------------------ 7. sin panel flotante (10/10/2026)
        # El panel flotante se quitó a pedido de Marcos. Ni al cargar ni tras
        # un salto al final debe existir.
        print("\n[sin panel flotante]")
        ctx = browser.new_context(viewport={"width": 1100, "height": 560})
        page = ctx.new_page()
        page.goto(BASE + "/")
        page.wait_for_selector(".rcard", state="attached")
        check(page.locator("#dock, #dock-pill").count() == 0, "el panel flotante y su botón no existen")
        page.evaluate("window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'instant'})")
        page.wait_for_timeout(300)
        check(page.locator("#dock, #dock-pill").count() == 0, "después del salto al final, sigue sin aparecer")
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
