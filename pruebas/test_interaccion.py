#!/usr/bin/env python3
"""
test_interaccion.py — panel flotante y botón de compartir, en Chromium real.

Lo importante que verifica
--------------------------
1. El panel flotante es un ESPEJO: cambiar una medida ahí da exactamente la
   misma clasificación que cambiarla en el panel principal. Nunca puede haber
   dos medidas distintas en juego.
2. Solo aparece cuando el panel principal quedó arriba de la pantalla, y
   mientras está oculto es inerte (no se puede tabular a él).
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
    page.wait_for_selector(".rcard")


def dock_on(page) -> bool:
    return page.evaluate("""() => {
        const d = document.getElementById('dock');
        return d.classList.contains('is-on') && !d.hasAttribute('inert');
    }""")


def scroll_to_compare(page):
    page.locator("#compare").scroll_into_view_if_needed()
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
            print(f"\n[{lang}] panel flotante")
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            ready(page, BASE + path)

            check(not dock_on(page), f"{lang}: arriba de todo, el panel flotante no se ve")
            check(page.get_attribute("#dock", "inert") is not None, f"{lang}: oculto = inerte")

            scroll_to_compare(page)
            check(dock_on(page), f"{lang}: al bajar hasta el comparador aparece")
            check(page.input_value("#dock-a") == page.input_value("#dim-a"),
                  f"{lang}: arranca con la misma medida que el panel principal")

            # + en el panel flotante
            page.click('#dock button[data-nudge="dim-a"][data-dir="1"]')
            after_dock = classes(page)
            main_val = page.input_value("#dim-a")
            check(main_val == "51", f"{lang}: + del panel flotante mueve el campo principal (50 -> {main_val})")
            check(page.input_value("#dock-a") == "51", f"{lang}: y el panel flotante lo refleja")

            # misma medida escrita en el panel principal, en una página nueva
            ref = ctx.new_page()
            ready(ref, BASE + path)
            ref.fill("#dim-a", "51")
            check(classes(ref) == after_dock,
                  f"{lang}: misma clasificación que escribiendo 51 en el panel principal")
            ref.close()

            # escribir a mano en el panel flotante
            page.fill("#dock-c", "19")
            check(page.input_value("#dim-c") == "19", f"{lang}: escribir en el panel flotante actualiza el principal")
            page.fill("#dock-w", "7")
            check(page.input_value("#weight") == "7", f"{lang}: también el peso")

            # flechas del teclado en el panel flotante
            page.focus("#dock-b")
            page.keyboard.press("ArrowDown")
            check(page.input_value("#dim-b") == "37" and page.input_value("#dock-b") == "37",
                  f"{lang}: flecha abajo en el panel flotante baja 1 cm en los dos")

            # ocultar y volver a abrir
            page.click("#dock-hide")
            check(not dock_on(page), f"{lang}: se puede ocultar")
            check(page.evaluate("document.getElementById('dock-pill').classList.contains('is-on')"),
                  f"{lang}: y queda el botón para reabrirlo")
            page.click("#dock-pill")
            check(dock_on(page), f"{lang}: el botón lo vuelve a abrir")

            # unidades
            page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            page.wait_for_timeout(350)
            check(not dock_on(page), f"{lang}: al volver arriba desaparece")
            page.click("#unit-in")
            scroll_to_compare(page)
            units = page.eval_on_selector_all('#dock [data-unit="length"]', "els => els.map(e => e.textContent)")
            check(units == ["in", "in", "in"], f"{lang}: al pasar a pulgadas el panel flotante dice 'in'")
            check(page.input_value("#dock-a") == page.input_value("#dim-a"),
                  f"{lang}: y muestra el valor convertido ({page.input_value('#dock-a')} in)")
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
            page.click("#cmp-clear")
            first_ops = page.eval_on_selector_all(".rcard .op__name", "els => els.map(e => e.textContent)")
            # elegir dos operadores cualquiera, en orden inverso al de la grilla
            chosen_names = [first_ops[-1], first_ops[1]]
            for name in chosen_names:
                page.locator(".rcard", has_text=name).locator(".rcard__cmp").click()
            want_classes = classes(page)
            want_cmp = compared(page)

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

        # teléfono: el panel flotante no se sale de la pantalla
        print("\n[móvil 375 px]")
        m = browser.new_context(viewport={"width": 375, "height": 740}, is_mobile=True, has_touch=True)
        page = m.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        ready(page, BASE + "/es/")
        scroll_to_compare(page)
        box = page.locator("#dock").bounding_box()
        check(dock_on(page) and box["x"] >= 0 and box["x"] + box["width"] <= 375,
              f"móvil: el panel flotante entra en el ancho ({box['x']:.0f}–{box['x'] + box['width']:.0f} px)")
        tap = page.locator('#dock button[data-nudge="weight"][data-dir="1"]').bounding_box()
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
