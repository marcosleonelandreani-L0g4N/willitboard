#!/usr/bin/env python3
"""
test_v8.py — rediseño "bento", tandas 2 a 4 (11/10/2026), en Chromium real.

Lo importante que verifica
--------------------------
1. LA MISMA CUENTA EN LAS DOS PÁGINAS. Para varias maletas y todos los
   operadores con medidas, el "¿Entra tu maleta en X?" de la ficha dice
   exactamente lo mismo (veredicto y detalle) que la tarjeta de ese
   operador en la home con las mismas medidas. Además, el código de la
   cuenta es el mismo texto en las dos páginas (partials/verdict.js).
2. La ficha muestra solo cifras del dataset: la tarjeta grande de peso es
   el peso de la maleta de cabina, o el total compartido rotulado como
   total, o no aparece.
3. Prohibidos en la ficha: solo en aviones de la región Europa, con fecha
   humana; nunca en Latinoamérica ni en trenes y ferris. Las flechas pasan
   de página y vuelven al principio.
4. Home: sin la tira de cifras, el dibujo de cómo medir a la vista (y
   decorativo), el banner de prohibidos con las 6 fichas y flechas.
5. Mantener apretada una flecha ▲▼ repite, y al soltar no suma un paso de más.
6. (Retirada el 20/10/2026: el banner grande ya no existe.)
7. Fondos: de día liso y sin nubes desde v9; de noche, estrellas que se
   quedan quietas con "menos movimiento". Tarjetas lisas, sin vidrio.
8. Ninguna página nueva tiene scroll de costado en 320, 375 y 390 px.

Uso:  python3 pruebas/test_v8.py
"""

from __future__ import annotations

import http.server
import json
import re
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "public"
PORT = 8798
BASE = f"http://127.0.0.1:{PORT}"

sys.path.insert(0, str(REPO))
import build_site as bs  # noqa: E402

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FALLA ") + label)


def main() -> int:
    ops = json.loads((ROOT / "operators.json").read_text(encoding="utf-8"))["operators"]
    dim_ops = [o for o in ops if o["limit_type"] == "dimensional"]

    # ------------------------------------------------ 1a. mismo código
    print("\n[la cuenta es el mismo código en la home y en la ficha]")
    shared = (REPO / "sitio" / "partials" / "verdict.js").read_text(encoding="utf-8")
    for path in ("index.html", "es/index.html", "airlines/ryanair/index.html", "es/aerolineas/latam/index.html"):
        html = (ROOT / path).read_text(encoding="utf-8")
        check(html.count(shared) == 1, f"{path}: trae partials/verdict.js tal cual, una vez")
    check("function verdictFor" not in (REPO / "sitio" / "template.html").read_text(encoding="utf-8"),
          "template.html ya no tiene su propia copia de verdictFor")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

    handler = partial(Quiet, directory=str(ROOT))

    class Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    srv = Srv(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})

        # ------------------------------------------------ 1b. mismo resultado
        print("\n[mismo veredicto en la ficha y en la home]")
        bags = [(55, 40, 20, 10), (40, 30, 20, 7), (50, 38, 22, 9), (56, 45, 25, 8), (45, 35, 20, 13)]
        for lang in ("es", "en"):
            home = ctx.new_page()
            home.on("pageerror", lambda e: errors.append(str(e)))
            fiche = ctx.new_page()
            fiche.on("pageerror", lambda e: errors.append(str(e)))
            mism = []
            for (l, w, h, kg) in bags:
                home_url = (f"{BASE}{'/es/' if lang == 'es' else '/'}?l={l}&w={w}&h={h}&kg={kg}&region=all")
                home.goto(home_url)
                home.wait_for_selector(".rcard", state="attached")
                cards = home.evaluate("""() => {
                    const o = {};
                    document.querySelectorAll('#results .rcard').forEach(c => {
                      const d = c.querySelector('.rcard__detail');
                      o[c.dataset.id] = { v: c.querySelector('.rcard__verdict').textContent.trim(),
                                         d: d ? d.innerHTML.trim() : '' };
                    });
                    return o; }""")
                for op in dim_ops:
                    fiche.goto(BASE + bs.op_path(op, lang))
                    for fid, val in (("#try-a", l), ("#try-b", w), ("#try-c", h), ("#try-w", kg)):
                        fiche.fill(fid, str(val))
                    got = {"v": fiche.inner_text("#try-v").strip(), "d": fiche.inner_html("#try-d").strip()}
                    want = cards.get(op["id"])
                    if got != want:
                        mism.append((op["id"], (l, w, h, kg), got, want))
            check(not mism, f"{lang}: {len(bags)} maletas × {len(dim_ops)} operadores, ficha = home"
                            + (f" — primera diferencia: {mism[0]}" if mism else ""))
            home.close()
            fiche.close()

        # ------------------------------------------------ 1c. enlace a la home con las medidas
        print("\n[la ficha lleva las medidas a la home]")
        page = ctx.new_page()
        page.goto(BASE + "/es/aerolineas/ryanair/")
        page.fill("#try-a", "48")
        href = page.get_attribute("#try-all", "href")
        check(href.startswith("/es/?") and "l=48" in href and "kg=9" in href, f"enlace con las medidas: {href}")
        page.click('.tryit .nudge[data-nudge="try-b"][data-dir="1"]')
        check(page.input_value("#try-b") == "39", "▲ de la ficha sube 1 cm")
        page.click('.tryit .nudge[data-nudge="try-w"][data-dir="-1"]')
        check(page.input_value("#try-w") == "8.5", "▼ del peso baja medio kilo")
        page.fill("#try-c", "")
        check(page.inner_text("#try-v").strip() in ("Escribe las tres medidas.",), "sin una medida, pide las tres")
        cmp_href = page.get_attribute(".pillbtn", "href")
        check(cmp_href == "/es/?c=ryanair#compare", f"'Comparar con otra' abre el comparador con Ryanair ({cmp_href})")
        page.close()

        # ------------------------------------------------ 2. tarjeta de peso
        print("\n[tarjeta grande de peso: solo cifras del dataset]")
        bad = []
        for op in ops:
            html = (ROOT / bs.op_outfile(op, "es").relative_to(bs.OUT_DIR)).read_text(encoding="utf-8")
            m = re.search(r'<p class="kg__n"[^>]*>([\d.]+)<small>', html)
            k = bs.fiche_kg(op)
            if k is None:
                if m: bad.append((op["id"], "muestra peso sin dato"))
            else:
                if not m or float(m.group(1)) != float(k[0]): bad.append((op["id"], m and m.group(1), k))
                shared_lbl = "en total, sumando los dos bultos" in html.split('class="glass tile--kg')[1][:600]
                if shared_lbl != k[1]: bad.append((op["id"], "rótulo total/propio"))
        check(not bad, f"peso = dataset en las {len(ops)} fichas ({bad[:3]})")

        # ------------------------------------------------ 3. prohibidos en la ficha
        # 18/10/2026: en la ficha va UNA línea con enlace a la lista de la home
        # (el carrusel era el mismo bloque repetido en 16 fichas).
        print("\n[prohibidos en la ficha: una línea]")
        wrong = []
        for op in ops:
            for lang, home in (("es", "/es/#banned"), ("en", "/#banned")):
                html = (ROOT / bs.op_outfile(op, lang).relative_to(bs.OUT_DIR)).read_text(encoding="utf-8")
                has = 'class="glass tile--banline' in html
                want = op["type"] == "air" and op["region"] == "EU" and bool(bs.BANNED_VERIFIED_ON.strip())
                if has != want: wrong.append(f"{lang}/{op['id']}")
                if 'class="glass tile--banned' in html or '<li class="nogo__tile' in html:
                    wrong.append(f"{lang}/{op['id']} (quedó el carrusel)")
                if has and f'href="{home}"' not in html.split('tile--banline')[-1][:900]:
                    wrong.append(f"{lang}/{op['id']} (enlace)")
        check(not wrong, f"solo en aviones de Europa, una línea con enlace a la lista ({wrong})")

        # ------------------------------------------------ 4. home
        print("\n[home]")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/es/")
        page.wait_for_selector(".rcard", state="attached")
        check(page.locator(".stats").count() == 0, "sin la tira de cifras")
        thumb = page.locator(".measure__thumb svg")
        check(thumb.count() == 1 and thumb.get_attribute("aria-hidden") == "true",
              "el dibujo de cómo medir está a la vista y es decorativo")
        ids = page.evaluate("[...document.querySelectorAll('[id]')].map(e => e.id)")
        check(len(ids) == len(set(ids)), "sin id repetidos (el dibujo chico renombra los suyos)")
        check(page.locator("#banned .nogo__tile").count() == 6, "banner de prohibidos con las 6 fichas")
        check(page.locator("#banned .banned__links a").count() >= 5, "y siguen las fuentes oficiales debajo")
        dots = page.locator("#nogo-dots button").count()
        check(dots == 2, f"en computadora, 3 fichas por vez → 2 puntos ({dots})")

        # ------------------------------------------------ 5. mantener apretado
        print("\n[mantener apretada una flecha]")
        for path, inp, btn in (("/es/", "#dim-a", '.panel .nudge[data-nudge="dim-a"][data-dir="1"]'),
                               ("/es/aerolineas/ryanair/", "#try-a", '.tryit .nudge[data-nudge="try-a"][data-dir="1"]')):
            pg = ctx.new_page()
            pg.goto(BASE + path)
            pg.wait_for_timeout(300)
            pg.locator(btn).scroll_into_view_if_needed()
            box = pg.locator(btn).bounding_box()
            pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pg.mouse.down(); pg.wait_for_timeout(1400); pg.mouse.up(); pg.wait_for_timeout(150)
            held = float(pg.input_value(inp))
            check(55 <= held <= 64, f"{path}: 1,4 s apretada sube varias veces (50 → {held:g})")
            pg.click(btn)
            check(float(pg.input_value(inp)) == held + 1, f"{path}: al soltar no suma de más; un toque = +1")
            pg.close()

        # ------------------------------------------------ 6. (v9) el banner grande ya no existe
        page.close()

        # ------------------------------------------------ 7. fondos
        print("\n[fondos de día y de noche]")
        for dark in (False, True):
            c = browser.new_context(viewport={"width": 1200, "height": 800})
            if dark:
                c.add_init_script("try{sessionStorage.setItem('wib-theme','dark')}catch(e){}")
            pg = c.new_page()
            pg.goto(BASE + "/es/aerolineas/ryanair/")
            bg = pg.evaluate("getComputedStyle(document.body, '::before').backgroundImage")
            after = pg.evaluate("[getComputedStyle(document.body, '::after').content, getComputedStyle(document.body, '::after').animationName]")
            check("gradient" in bg, f"{'noche' if dark else 'día'}: hay fondo")
            if dark:
                check(after[1] == "wib-twinkle", f"noche: estrellas que titilan ({after[1]})")
            else:
                # v9 (20/10/2026): fondo de día liso, sin nubes, para que se lea más fácil
                check(after[0] == "none", f"día: sin nubes ({after[0]})")
            c.close()
        c = browser.new_context(viewport={"width": 1200, "height": 800}, reduced_motion="reduce")
        c.add_init_script("try{sessionStorage.setItem('wib-theme','dark')}catch(e){}")
        pg = c.new_page()
        pg.goto(BASE + "/es/")
        anim = pg.evaluate("getComputedStyle(document.body, '::after').animationName")
        check(anim == "none", f"con 'menos movimiento', las estrellas quedan quietas ({anim})")
        c.close()
        css = (REPO / "sitio" / "style.css").read_text(encoding="utf-8")
        # v9: las tarjetas pasan a ser lisas; se comprueba en la página, no en el CSS
        c = browser.new_context(viewport={"width": 1200, "height": 800})
        pg = c.new_page()
        pg.goto(BASE + "/es/aerolineas/ryanair/")
        blur = pg.evaluate("[...document.querySelectorAll('.glass')].map(e => getComputedStyle(e).backdropFilter).filter(v => v && v !== 'none').length")
        check(blur == 0, f"las tarjetas son lisas, sin vidrio esmerilado ({blur} con desenfoque)")
        c.close()

        # ------------------------------------------------ 8. sin scroll de costado
        print("\n[sin scroll de costado en el teléfono]")
        pages = ["/", "/es/"] + [bs.op_path(o, l) for o in ops for l in ("en", "es")]
        over = []
        for w in (320, 375, 390):
            m = browser.new_context(viewport={"width": w, "height": 800}, is_mobile=True, has_touch=True)
            pg = m.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for path in pages:
                pg.goto(BASE + path, wait_until="load")
                sw = pg.evaluate("document.documentElement.scrollWidth")
                if sw > w: over.append((w, path, sw))
            m.close()
        check(not over, f"{len(pages)} páginas × 3 anchos sin desborde ({over[:3]})")

        browser.close()
    srv.shutdown()

    check(not errors, "sin errores de JavaScript" + (f": {errors[:3]}" if errors else ""))
    bad = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(bad)}/{len(results)} comprobaciones OK")
    if bad:
        print("HAY FALLAS.")
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
