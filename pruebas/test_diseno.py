#!/usr/bin/env python3
"""
test_diseno.py — rediseño v4 (23/09/2026), en Chromium real.

Lo que verifica
---------------
1. Modo claro por defecto (fondo blanco) en las tres clases de página, y el
   botón sol/luna cambia a oscuro. La elección NO se guarda: /cookies/ promete
   que el sitio no escribe nada en el navegador.
2. La home arranca "liviana": cada resultado es una fila plegada con nombre y
   veredicto; el detalle y el comparador aparecen solo si se piden.
3. Una fila abierta sigue abierta mientras se cambian las medidas (la lista se
   redibuja en cada tecla).
4. "+ Comparar" abre el comparador.
5. El enlace "Todas las reglas de…" de cada fila lleva a una ficha que existe.
6. Con prefers-reduced-motion la ilustración se queda quieta.
7. En el teléfono no hay scroll horizontal y la barra superior va en una línea.

Uso:  python3 pruebas/test_diseno.py
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
PORT = 8793
BASE = f"http://127.0.0.1:{PORT}"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FAIL ") + label)


def bg(page) -> str:
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


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
        # el sistema pide oscuro a propósito: el sitio igual tiene que arrancar en claro
        ctx = browser.new_context(viewport={"width": 1200, "height": 900}, color_scheme="dark")
        ctx.route("**://fonts.googleapis.com/**", lambda r: r.abort())
        ctx.route("**://fonts.gstatic.com/**", lambda r: r.abort())

        print("\n[tema claro / oscuro]")
        for path in ("/", "/es/", "/airlines/ryanair/", "/es/trenes/eurostar/", "/es/cookies/"):
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            check(bg(page) == "rgb(255, 255, 255)",
                  f"{path}: arranca en blanco aunque el sistema pida oscuro ({bg(page)})")
            page.click("#theme-toggle")
            page.wait_for_timeout(350)
            dark = page.get_attribute("html", "data-theme") == "dark"
            check(dark and bg(page) != "rgb(255, 255, 255)" and
                  page.get_attribute("#theme-toggle", "aria-pressed") == "true",
                  f"{path}: el botón pasa a modo noche")
            store = page.evaluate("[document.cookie, localStorage.length, sessionStorage.length]")
            check(store == ["", 0, 0], f"{path}: no se guarda nada en el navegador ({store})")
            page.reload()
            check(page.get_attribute("html", "data-theme") == "light",
                  f"{path}: al recargar vuelve a claro (no se guarda la elección)")
            page.close()

        print("\n[home liviana]")
        for path in ("/", "/es/"):
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            page.wait_for_selector(".rcard")
            n_open = page.eval_on_selector_all("#results details[open]", "els => els.length")
            check(n_open == 0, f"{path}: todas las filas arrancan plegadas")
            vis_more = page.eval_on_selector_all(".rrow__more", "els => els.filter(e => e.checkVisibility()).length")
            check(vis_more == 0, f"{path}: no se ven barras ni detalle de entrada")
            names_ok = page.evaluate("""() => [...document.querySelectorAll('.rcard')].every(c =>
                c.querySelector('.op__name').checkVisibility() && c.querySelector('.rcard__verdict').checkVisibility())""")
            check(names_ok, f"{path}: cada fila muestra nombre y veredicto a simple vista")
            check(page.get_attribute("#compare", "open") is None, f"{path}: el comparador arranca plegado")

            first = page.locator(".rcard").first
            first.locator(".rrow__sum").click()
            page.click('.panel .nudge[data-nudge="dim-a"][data-dir="1"]')
            still = first.locator("details").evaluate("d => d.open")
            check(still, f"{path}: una fila abierta sigue abierta al cambiar una medida")

            # agregar al comparador lo abre
            page.click("#compare > summary")          # abrir
            page.click("#cmp-clear")
            page.click("#compare > summary")          # y cerrar de nuevo
            check(page.get_attribute("#compare", "open") is None, f"{path}: el comparador se puede cerrar")
            first.locator(".rcard__cmp").click()
            check(page.get_attribute("#compare", "open") is not None,
                  f"{path}: '+ Comparar' abre el comparador")
            badge = page.inner_text("#cmp-badge")
            check(badge == "1", f"{path}: el encabezado del comparador cuenta 1 ({badge!r})")

            links = page.eval_on_selector_all(".rrow__fiche", "els => els.map(a => a.getAttribute('href'))")
            ok = [l for l in links if (ROOT / l.strip("/") / "index.html").exists()]
            check(links and len(ok) == len(links),
                  f"{path}: los {len(links)} enlaces a fichas existen ({len(ok)} OK)")
            want_prefix = "/es/" if path == "/es/" else "/"
            check(all(l.startswith(want_prefix) for l in links) and
                  (path == "/es/" or not any(l.startswith("/es/") for l in links)),
                  f"{path}: los enlaces a fichas quedan en el mismo idioma")
            page.close()

        print("\n[movimiento reducido]")
        rm = browser.new_context(reduced_motion="reduce")
        page = rm.new_page()
        page.goto(BASE + "/")
        anim = page.evaluate("getComputedStyle(document.querySelector('.art-bag')).animationName")
        check(anim == "none", f"con prefers-reduced-motion la maleta no se mueve ({anim})")
        rm.close()

        print("\n[teléfono 390 px]")
        m = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page = m.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        for path in ("/", "/es/", "/es/aerolineas/ryanair/"):
            page.goto(BASE + path)
            w = page.evaluate("document.documentElement.scrollWidth")
            check(w <= 390, f"{path}: sin scroll horizontal ({w}px)")
            h = page.evaluate("document.querySelector('.topbar').getBoundingClientRect().height")
            check(h < 60, f"{path}: barra superior en una sola línea ({h:.0f}px)")
        m.close()
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
