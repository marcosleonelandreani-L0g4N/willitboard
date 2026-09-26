#!/usr/bin/env python3
"""
test_v5.py — lo que agregó el rediseño v5 (26/09/2026), en Chromium real.

Lo importante que verifica
--------------------------
1. PESO COMBINADO. Con un operador de prueba que publica un solo peso para los
   dos bultos (y ninguno por bulto): una maleta que pesa menos que el total
   entra; una que pesa más no entra, aunque las medidas den; y el aviso de
   que el peso es compartido aparece. El dataset de prueba se inyecta
   interceptando /operators.json: el dataset real no se toca.
2. El buscador encuentra sin importar mayúsculas ni tildes, y abre solo los
   grupos que tienen algo que mostrar.
3. Las fichas de color filtran y abren los grupos que corresponden.
4. Pestaña Comparar: filtros por tipo, "mi maleta va sin costo extra",
   "maleta de cabina incluida", y el orden por tamaño de cabina.
5. Las pestañas se manejan con el teclado y #compare abre directo la segunda.
6. Los botones del carrusel llevan a donde dicen.
7. CERO terceros: ninguna página pide nada fuera del propio sitio (las
   tipografías se sirven desde /fonts/), y las etiquetas para compartir
   apuntan a archivos que existen.

Uso:  python3 pruebas/test_v5.py
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
PORT = 8797
BASE = f"http://127.0.0.1:{PORT}"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FAIL ") + label)


# Operador de PRUEBA. No existe: solo sirve para ejercitar la lógica del peso
# combinado sin depender de que un operador real esté verificado.
FAKE_OP = {
    "id": "test-air", "name": "Test Air", "type": "air", "country": "ES", "region": "EU",
    "limit_type": "dimensional", "notes": None, "notes_en": None,
    "source_url": "https://example.com/bags", "verified_on": "2026-09-26",
    "personal_item": {"included": True, "max_cm": {"length": 40, "width": 30, "height": 20}, "max_kg": None},
    "cabin_bag": {"included": False, "requires_addon": "Test Plus",
                  "max_cm": {"length": 55, "width": 40, "height": 25}, "max_kg": None},
    "wheels_handles": {"included_in_measurement": True, "tolerance_cm": None},
    "excess_fee": {"currency": None, "online_from": None, "at_gate_from": None},
    "reference_fare": None, "combined_max_kg": 10,
}


def with_fake(real: dict) -> str:
    data = dict(real)
    data["operators"] = [FAKE_OP] + list(real["operators"])
    return json.dumps(data)


def verdict_of(page, op_id: str) -> str | None:
    return page.evaluate(
        "(id) => { const c = document.querySelector(`.rcard[data-id='${id}']`); return c ? c.getAttribute('data-band') : null; }",
        op_id)


def set_bag(page, a, b, c, kg):
    for sel, v in (("#dim-a", a), ("#dim-b", b), ("#dim-c", c), ("#weight", kg)):
        page.fill(sel, str(v))


def main() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # silencio
            pass

    handler = partial(Quiet, directory=str(ROOT))

    class Srv(socketserver.TCPServer):
        allow_reuse_address = True

    srv = Srv(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []
    real = json.loads((ROOT / "operators.json").read_text(encoding="utf-8"))
    ops = real["operators"]

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ------------------------------------------------ 1. peso combinado
        print("\n[peso combinado, con un operador de prueba]")
        ctx = browser.new_context(viewport={"width": 1200, "height": 900}, reduced_motion="reduce")
        ctx.route("**/operators.json", lambda r: r.fulfill(
            status=200, content_type="application/json", body=with_fake(real)))
        per_lang = {}
        for path in ("/", "/es/"):
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path)
            page.wait_for_selector(".rcard[data-id='test-air']", state="attached")
            got = []
            set_bag(page, 40, 30, 20, 9)
            got.append(verdict_of(page, "test-air"))
            page.click('.tgroup[data-type="air"] > summary')
            page.click(".rcard[data-id='test-air'] .rrow__sum")
            flag = page.inner_text(".rcard[data-id='test-air'] .rrow__more")
            check("10" in flag and ("both bags" in flag or "dos bultos" in flag),
                  f"{path}: 9 kg con un total de 10 kg: se avisa que el peso es compartido")
            line = page.inner_text(".rcard[data-id='test-air'] .rcard__line")
            check("10" in line, f"{path}: la línea de la tarjeta muestra el total compartido ({line!r})")
            set_bag(page, 40, 30, 20, 11)
            got.append(verdict_of(page, "test-air"))
            detail = page.inner_text(".rcard[data-id='test-air'] .rrow__more")
            check("10" in detail, f"{path}: 11 kg: el motivo cita el total de 10 kg")
            set_bag(page, 55, 40, 25, 9)
            got.append(verdict_of(page, "test-air"))
            set_bag(page, 55, 40, 25, 10.5)
            got.append(verdict_of(page, "test-air"))
            check(got == ["pass", "fail", "paid", "fail"],
                  f"{path}: 9 kg entra · 11 kg no · la valija se paga aparte · 10,5 kg no ({got})")
            # el comparador muestra el peso compartido, no "sin peso publicado"
            page.click("#tab-compare")
            page.click("#cmp-clear")
            page.locator(".opt[data-id='test-air'] input").check()
            cell = page.inner_text(".cmp")
            check(("in total" in cell) or ("en total" in cell),
                  f"{path}: la tabla del comparador dice que el peso es en total")
            per_lang[path] = got
            page.close()
        check(per_lang["/"] == per_lang["/es/"], "el peso combinado da lo mismo en los dos idiomas")
        ctx.close()

        ctx = browser.new_context(viewport={"width": 1200, "height": 900}, reduced_motion="reduce")

        # ------------------------------------------------ 2. buscador
        print("\n[buscador]")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/es/")
        page.wait_for_selector(".rcard", state="attached")
        target = sorted(ops, key=lambda o: o["name"])[0]
        page.fill("#q", target["name"].upper()[:5])
        vis = page.evaluate("() => [...document.querySelectorAll('.rcard')].filter(c => !c.hidden).map(c => c.dataset.id)")
        check(target["id"] in vis, f"buscar '{target['name'].upper()[:5]}' encuentra a {target['name']}")
        opened = page.eval_on_selector_all(".tgroup[open]", "els => els.map(e => e.dataset.type)")
        check(opened == [target["type"]], f"y abre solo su grupo ({opened})")
        page.fill("#q", "zzzz")
        check(page.is_visible(".groups__none"), "una búsqueda sin resultados lo dice")
        page.fill("#q", "")
        rail = [o for o in ops if o["type"] == "rail"]
        if rail:
            page.fill("#q", "tren")
            vis = page.evaluate("() => [...document.querySelectorAll('.rcard')].filter(c => !c.hidden).map(c => c.dataset.id)")
            check(set(vis) == {o["id"] for o in rail}, "buscar 'tren' deja todos los trenes")
            page.fill("#q", "")

        # ------------------------------------------------ 3. fichas de color
        print("\n[fichas de color]")
        page.goto(BASE + "/")
        page.wait_for_selector("#summary .tile", state="attached")
        page.click("#summary .tile.band--rule")
        opened = set(page.eval_on_selector_all(".tgroup[open]", "els => els.map(e => e.dataset.type)"))
        want = {o["type"] for o in ops if o["limit_type"] != "dimensional"}
        check(opened == want, f"'regla escrita' abre los grupos que tienen reglas ({sorted(opened)})")
        vis = page.evaluate("() => [...document.querySelectorAll('.rcard')].filter(c => !c.hidden).length")
        check(vis == len([o for o in ops if o["limit_type"] != "dimensional"]), "y deja solo esas filas")
        page.close()

        # ------------------------------------------------ 4. pestaña Comparar
        print("\n[pestaña Comparar]")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/#compare")
        page.wait_for_selector(".opt", state="attached")
        check(page.is_visible("#panel-compare") and not page.is_visible("#panel-check"),
              "#compare en la dirección abre directo la pestaña Comparar")
        total = page.eval_on_selector_all(".opt", "els => els.length")
        check(total == len(ops), f"la lista muestra los {len(ops)} operadores ({total})")
        page.click('#cmp-types .chip[data-type="air"]')
        ids = page.eval_on_selector_all(".opt", "els => els.map(e => e.dataset.id)")
        check(set(ids) == {o["id"] for o in ops if o["type"] == "air"}, "el filtro Aerolíneas deja solo aerolíneas")
        page.click('#cmp-types .chip[data-type="all"]')
        page.click("#cmp-f-cabin")
        ids = page.eval_on_selector_all(".opt", "els => els.map(e => e.dataset.id)")
        want = {o["id"] for o in ops if (o.get("cabin_bag") or {}).get("included") is True}
        check(set(ids) == want, f"'maleta de cabina incluida' deja solo esos ({sorted(ids)})")
        page.click("#cmp-f-cabin")
        page.click("#cmp-f-pass")
        ids = set(page.eval_on_selector_all(".opt", "els => els.map(e => e.dataset.id)"))
        passing = set(page.evaluate("() => [...document.querySelectorAll('.rcard')].filter(c => c.dataset.band === 'pass').map(c => c.dataset.id)"))
        check(ids == passing, f"'mi maleta va sin costo extra' coincide con los verdes de la otra pestaña ({sorted(ids)})")
        page.click("#cmp-f-pass")
        page.select_option("#cmp-sort", "cabin")

        def vol(o):
            c = (o.get("cabin_bag") or {}).get("max_cm") if o["limit_type"] == "dimensional" else None
            if not c or any(c.get(k) is None for k in ("length", "width", "height")):
                return -1
            return c["length"] * c["width"] * c["height"]
        order = page.eval_on_selector_all(".opt", "els => els.map(e => e.dataset.id)")
        want = [o["id"] for o in sorted(ops, key=lambda o: (-vol(o), o["name"]))]
        check(order == want, f"ordenar por maleta de cabina sigue el tamaño publicado ({order[:3]}…)")
        page.close()

        # ------------------------------------------------ 5. teclado
        print("\n[pestañas con el teclado]")
        page = ctx.new_page()
        page.goto(BASE + "/")
        page.focus("#tab-check")
        page.keyboard.press("ArrowRight")
        check(page.get_attribute("#tab-compare", "aria-selected") == "true" and
              page.evaluate("document.activeElement.id") == "tab-compare",
              "flecha derecha pasa a Comparar y le da el foco")
        page.keyboard.press("ArrowLeft")
        check(page.get_attribute("#tab-check", "aria-selected") == "true", "flecha izquierda vuelve")

        # ------------------------------------------------ 6. carrusel
        print("\n[botones del carrusel]")
        page.click('#slides-dots button[aria-controls="slide-2"]')
        page.click('#slide-2 [data-go="compare"]')
        check(page.is_visible("#panel-compare"), "'Abrir la comparación' abre la pestaña Comparar")
        page.click('#slides-dots button[aria-controls="slide-1"]')
        page.click('#slide-1 [data-go="measure"]')
        check(page.is_visible("#panel-check") and page.get_attribute("#measure", "open") is not None,
              "'Ver cómo medir' abre la guía en la pestaña de comprobar")
        page.close()
        ctx.close()

        # ------------------------------------------------ 7. cero terceros
        print("\n[cero terceros, en todas las clases de página]")
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        ext: list[str] = []
        fonts: list[str] = []

        def on_req(r):
            if not r.url.startswith(BASE) and not r.url.startswith("data:"):
                ext.append(r.url)
            if "/fonts/" in r.url:
                fonts.append(r.url)
        ctx.on("request", on_req)
        paths = ["/", "/es/", "/airlines/ryanair/", "/es/trenes/eurostar/", "/privacy/",
                 "/es/como-medir-una-maleta/", "/cabin-bag-sizes/", "/about/"]
        for path in paths:
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + path, wait_until="networkidle")
            loaded = page.evaluate("document.fonts.check('700 20px Fredoka') && document.fonts.check('600 16px Nunito')")
            check(loaded, f"{path}: las tipografías cargan desde el propio sitio")
            og = page.get_attribute('meta[property="og:image"]', "content") or ""
            local = ROOT / og.replace("https://willitboard.com/", "")
            check(og.startswith("https://willitboard.com/") and local.exists(),
                  f"{path}: la imagen para compartir existe ({og.rsplit('/', 1)[-1]})")
            check(page.get_attribute('meta[property="og:url"]', "content") ==
                  page.get_attribute('link[rel="canonical"]', "href"),
                  f"{path}: og:url es la dirección canónica")
            icons = page.eval_on_selector_all('link[rel~="icon"], link[rel="apple-touch-icon"]',
                                              "els => els.map(e => e.getAttribute('href'))")
            check(icons and all((ROOT / h.lstrip("/")).exists() for h in icons),
                  f"{path}: los íconos del sitio existen ({len(icons)})")
            page.close()
        check(not ext, f"ninguna página pidió nada a terceros ({ext[:3]})")
        check(bool(fonts), f"las tipografías se pidieron a /fonts/ ({len(fonts)} pedidos)")
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
