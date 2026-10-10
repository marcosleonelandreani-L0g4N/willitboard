#!/usr/bin/env python3
"""
test_interaccion.py — espejos de la maleta y botón de compartir, en Chromium real.

Lo importante que verifica
--------------------------
1. La franja de medidas de la pestaña Comparar es un ESPEJO: cambiar una
   medida ahí da exactamente la misma clasificación que cambiarla en el panel
   principal. Nunca puede haber dos medidas distintas en juego.
2. El panel flotante se quitó el 10/10/2026 (pedido de Marcos): no existe, y
   al bajar por la página no aparece nada fijo encima del contenido (salvo
   el botón chico de "volver arriba").
3. Un enlace compartido reproduce las mismas medidas, los mismos operadores
   comparados y, por lo tanto, los mismos veredictos. El enlace lleva medidas,
   nunca veredictos.
4. Cambiar de unidad (cm <-> in, kg <-> lb) no cambia ningún veredicto ni
   deja las medidas corridas. Error real encontrado el 23/09/2026: 55 cm se
   mostraba como 21.7 in, que son 55.1 cm, y Ryanair pasaba a "no entra".
5. Parámetros basura en el enlace se ignoran sin romper nada.
6. Nada de esto escribe cookies ni almacenamiento del navegador (/cookies/ lo
   promete).

Uso:  python3 pruebas/test_interaccion.py
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent / "public"
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FAIL ") + label)


def classes(page) -> dict:
    """nombre del operador -> grupo (pass/paid/fail/rule/unknown)."""
    return page.evaluate("""() => {
        const out = {};
        document.querySelectorAll('.rcard').forEach(c => {
            const band = [...c.classList].find(k => k.startsWith('band--'));
            out[c.querySelector('.op__name').textContent] = band;
        });
        return out;
    }""")


def compared(page) -> list:
    return page.eval_on_selector_all(".cmp__name", "els => els.map(e => e.textContent)")


def ready(page, url):
    page.goto(url)
    # v5: las filas viven dentro de grupos plegados; alcanza con que existan
    page.wait_for_selector(".rcard", state="attached")


def fixed_on_screen(page) -> list:
    """Elementos visibles con position: fixed, salvo el botón de volver arriba."""
    return page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => {
        if (e.closest('#totop')) return false;
        const cs = getComputedStyle(e);
        if (cs.position !== 'fixed' || cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return false;
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight;
    }).map(e => e.id || e.className)""")


def scroll_to_compare(page):
    # rediseño v4: la home es más corta y el comparador arranca plegado;
    # se baja hasta el pie para dejar el panel de medidas bien arriba
    page.locator("footer").scroll_into_view_if_needed()
    page.wait_for_timeout(350)


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
        ctx = browser.new_context(viewport={"width": 1100, "height": 800})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)

        for path, lang in (("/", "en"), ("/es/", "es")):
            print(f"\n[{lang}] sin panel flotante")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)
            check(page.locator("#dock, #dock-pill").count() == 0, f"{lang}: el panel flotante ya no existe")
            scroll_to_compare(page)
            fixed = fixed_on_screen(page)
            check(not fixed, f"{lang}: al bajar no aparece nada fijo encima de la página ({fixed})")
            page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")
            page.wait_for_timeout(200)
            check(not fixed_on_screen(page), f"{lang}: tampoco al saltar al final")
            page.close()

            print(f"\n[{lang}] espejo en la pestaña Comparar")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)
            page.click("#tab-compare")
            check(page.input_value("#cmp-a") == page.input_value("#dim-a"),
                  f"{lang}: arranca con la misma medida que el panel principal")

            page.click('.bagstrip button[data-nudge="dim-a"][data-dir="1"]')
            main_val = page.input_value("#dim-a")
            check(main_val == "51", f"{lang}: + de la franja mueve el campo principal (50 -> {main_val})")
            check(page.input_value("#cmp-a") == "51", f"{lang}: y la franja lo refleja")
            page.click("#tab-check")
            after_mirror = classes(page)

            ref = ctx.new_page()
            ready(ref, BASE + path)
            ref.fill("#dim-a", "51")
            check(classes(ref) == after_mirror,
                  f"{lang}: misma clasificación que escribiendo 51 en el panel principal")
            ref.close()

            page.click("#tab-compare")
            page.fill("#cmp-c", "19")
            check(page.input_value("#dim-c") == "19", f"{lang}: escribir en la franja actualiza el principal")
            page.fill("#cmp-w", "7")
            check(page.input_value("#weight") == "7", f"{lang}: también el peso")

            page.focus("#cmp-b")
            page.keyboard.press("ArrowDown")
            check(page.input_value("#dim-b") == "37" and page.input_value("#cmp-b") == "37",
                  f"{lang}: flecha abajo en la franja baja 1 cm en los dos")

            page.click("#tab-check")
            page.click("#unit-in")
            page.click("#tab-compare")
            units = page.eval_on_selector_all('.bagstrip [data-unit="length"]', "els => els.map(e => e.textContent)")
            check(units == ["in", "in", "in"], f"{lang}: al pasar a pulgadas la franja dice 'in'")
            check(page.input_value("#cmp-a") == page.input_value("#dim-a"),
                  f"{lang}: y muestra el valor convertido ({page.input_value('#cmp-a')} in)")
            page.close()

            print(f"\n[{lang}] unidades")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)
            for sel, v in (("#dim-a", "55"), ("#dim-b", "40"), ("#dim-c", "20"), ("#weight", "10")):
                page.fill(sel, v)
            base_cls = classes(page)
            page.click("#unit-in"); page.click("#unit-lb")
            check(classes(page) == base_cls, f"{lang}: pasar a in/lb no cambia ningún veredicto (caso 55×40×20, 10 kg)")
            page.click("#unit-cm"); page.click("#unit-kg")
            vals = [page.input_value(x) for x in ("#dim-a", "#dim-b", "#dim-c", "#weight")]
            check(vals == ["55", "40", "20", "10"], f"{lang}: ida y vuelta a pulgadas deja las medidas exactas ({vals})")
            check(classes(page) == base_cls, f"{lang}: y los mismos veredictos")
            page.click("#unit-in")
            page.click('.preset[data-cm="55,40,23"]')
            page.click("#unit-cm")
            vals = [page.input_value(x) for x in ("#dim-a", "#dim-b", "#dim-c")]
            check(vals == ["55", "40", "23"], f"{lang}: un ejemplo cargado en pulgadas vuelve exacto a cm ({vals})")
            page.close()

            print(f"\n[{lang}] compartir")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)
            page.fill("#dim-a", "54")
            page.fill("#dim-b", "39")
            page.fill("#dim-c", "21")
            page.fill("#weight", "8.5")
            # v5: el comparador tiene su propia pestaña, con una lista para marcar
            page.click("#tab-compare")
            page.click("#cmp-clear")
            first_ops = page.eval_on_selector_all(".opt .opt__name", "els => els.map(e => e.textContent)")
            # elegir dos operadores cualquiera, en orden inverso al de la lista
            chosen_names = [first_ops[-1], first_ops[1]]
            for name in chosen_names:
                page.locator(".opt", has_text=name).locator("input").check()
            want_classes = classes(page)
            want_cmp = compared(page)
            check(want_cmp == chosen_names, f"{lang}: el comparador muestra lo marcado, en ese orden ({want_cmp})")

            page.click("#tab-check")
            page.click("#share-btn")
            page.wait_for_selector("#share-status.is-on")
            clip = page.evaluate("navigator.clipboard.readText()")
            url = clip.split(" ")[-1]
            q = parse_qs(urlparse(url).query)
            check(q.get("l") == ["54"] and q.get("w") == ["39"] and q.get("h") == ["21"] and q.get("kg") == ["8.5"],
                  f"{lang}: el enlace lleva las medidas en cm/kg ({urlparse(url).query})")
            check(urlparse(url).path == path, f"{lang}: el enlace apunta a la misma versión de idioma")
            check("54 × 39 × 21 cm" in clip, f"{lang}: el texto copiado incluye la valija")
            for bad in ("fits", "Doesn't fit", "No entra", "pass", "fail"):
                if bad in clip:
                    check(False, f"{lang}: el texto copiado NO lleva veredicto ('{bad}')")
                    break
            else:
                check(True, f"{lang}: el texto copiado no lleva veredictos")

            other = ctx.new_page()
            other.on("pageerror", lambda e: errors.append(str(e)))
            ready(other, url)
            check(classes(other) == want_classes, f"{lang}: quien abre el enlace ve la misma clasificación")
            check(compared(other) == want_cmp, f"{lang}: y los mismos operadores comparados ({', '.join(want_cmp)})")
            check(other.is_visible("#shared-note"), f"{lang}: con el aviso de que las medidas vienen de un enlace")
            check(not page.is_visible("#shared-note"), f"{lang}: sin enlace, no hay aviso")
            other.close()

            # enlace en pulgadas: el enlace sigue en cm
            page.click("#unit-in")
            page.click("#share-btn")
            clip_in = page.evaluate("navigator.clipboard.readText()")
            q_in = parse_qs(urlparse(clip_in.split(" ")[-1]).query)
            check(q_in.get("l") == ["54"], f"{lang}: con la vista en pulgadas el enlace sigue en cm (l={q_in.get('l')})")

            # basura
            junk = ctx.new_page()
            junk.on("pageerror", lambda e: errors.append(str(e)))
            ready(junk, BASE + path + "?l=-5&w=abc&h=9999&kg=1e9&c=%3Cscript%3E,nope")
            check(junk.input_value("#dim-a") == "50" and junk.input_value("#weight") == "9",
                  f"{lang}: parámetros basura se ignoran y quedan los valores por defecto")
            check(len(compared(junk)) > 0, f"{lang}: operadores inexistentes en el enlace no vacían el comparador")
            junk.close()

            store = page.evaluate("[document.cookie, localStorage.length, sessionStorage.length]")
            check(store == ["", 0, 0], f"{lang}: no se escribió ninguna cookie ni almacenamiento ({store})")
            page.close()

        # teléfono: nada fijo encima, y la franja de Comparar entra y se puede tocar
        print("\n[móvil 375 px]")
        m = browser.new_context(viewport={"width": 375, "height": 740}, is_mobile=True, has_touch=True)
        page = m.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        ready(page, BASE + "/es/")
        scroll_to_compare(page)
        fixed = fixed_on_screen(page)
        check(not fixed, f"móvil: al bajar no aparece nada fijo encima ({fixed})")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.click("#tab-compare")
        box = page.locator(".bagstrip").bounding_box()
        check(box["x"] >= 0 and box["x"] + box["width"] <= 375,
              f"móvil: la franja de Comparar entra en el ancho ({box['x']:.0f}–{box['x'] + box['width']:.0f} px)")
        tap = page.locator('.bagstrip button[data-nudge="weight"][data-dir="1"]').bounding_box()
        check(tap["width"] >= 30 and tap["height"] >= 30,
              f"móvil: los botones se pueden tocar ({tap['width']:.0f}×{tap['height']:.0f} px)")
        width = page.evaluate("document.documentElement.scrollWidth")
        check(width <= 375, f"móvil: sin scroll horizontal (ancho {width})")
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
