#!/usr/bin/env python3
"""
Pruebas de la home v9 (20/10/2026): la home guía en tres pasos.

Lo importante que verifica
--------------------------
1. LA MISMA CUENTA. "¿Con qué compañía viajas?" no calcula nada propio: el
   veredicto de cada sugerencia y de cada tarjeta fijada es exactamente el de
   la fila de ese operador en los grupos de resultados, en los dos idiomas.
2. El orden: título, pasos y medidas arriba; sin carrusel; "Ver resultados"
   justo debajo de los campos (en 390 × 844 se ve sin bajar); los ejemplos
   debajo del botón; compartir DESPUÉS del resultado; el buscador de reglas y
   los prohibidos más abajo.
3. "Ver resultados" y los ejemplos llevan hasta el resultado, pasan al paso 2
   y le dan el foco al título de resultados.
4. Tus compañías: arrancan vacías (las tres del comparador de arranque NO son
   "tuyas"); la primera elegida reemplaza a las de arranque; hasta 3; se
   marcan también en los grupos; viajan en el enlace compartido (?c=); el
   botón "Compararlas" abre el paso 3 con esas mismas.
5. Comparador: líneas verticales entre columnas.
6. El botón verde se lee: contraste ≥ 4,5:1 de día y de noche.
7. Computadora: medidas a la izquierda, resultados a la derecha.
8. Sin scroll de costado en 320, 375 y 390 px con tres compañías fijadas, y
   sin errores de JavaScript.

Uso:  python3 pruebas/test_v9.py
"""

from __future__ import annotations

import http.server
import re
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "public"
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(("  OK   " if cond else "  FALLA ") + label)


def rgb(s: str) -> tuple[float, float, float]:
    n = [float(x) for x in re.findall(r"[\d.]+", s)[:3]]
    return n[0], n[1], n[2]


def lum(c: tuple[float, float, float]) -> float:
    def ch(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = lum(rgb(a)), lum(rgb(b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


FLOW = "els => els.map(e => (e.getAttribute('aria-current') || '-') + (e.classList.contains('is-done') ? '+done' : ''))"

# veredicto de un operador en los grupos de resultados (la fuente de verdad de la página)
GROUP_VERDICT = """id => {
  const card = document.querySelector('.rcard[data-id="' + id + '"]');
  return card ? card.querySelector('.rcard__verdict').textContent.trim() : null;
}"""


def pin(page, q: str) -> None:
    page.fill("#mine-q", q)
    page.wait_for_timeout(80)
    page.click("#mine-sug .msug")
    page.wait_for_timeout(80)


def main() -> int:
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

        # ------------------------------------------------ 2. orden de la página
        print("\n[orden de la home]")
        html = (ROOT / "es" / "index.html").read_text(encoding="utf-8")
        check('class="slides' not in html and "slides-track" not in html, "sin carrusel en el HTML")
        order = ['class="flow"', 'id="dim-a"', 'id="weight"', 'id="cta-results"', 'class="presets"',
                 'id="mine"', 'id="results"', 'id="share-btn"', 'id="lookup"', 'id="banned"']
        pos = [html.find(k) for k in order]
        check(all(x >= 0 for x in pos) and pos == sorted(pos),
              "pasos → medidas → «Ver resultados» → ejemplos → tus compañías → resultados → compartir → buscador → prohibidos")
        for lang, path in (("en", "/"), ("es", "/es/")):
            c = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            pg = c.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(BASE + path)
            bottom = pg.evaluate("Math.round(document.getElementById('cta-results').getBoundingClientRect().bottom)")
            check(bottom <= 844, f"{lang}: en 390 × 844, «Ver resultados» se ve sin bajar (termina en {bottom} px)")
            gap = pg.evaluate("""() => {
              const f = [...document.querySelectorAll('.panel .field')].pop().getBoundingClientRect();
              return Math.round(document.getElementById('cta-results').getBoundingClientRect().top - f.bottom);
            }""")
            check(0 <= gap <= 24, f"{lang}: el botón va justo debajo de los campos ({gap} px)")
            c.close()

        # ------------------------------------------------ 3. el "enter"
        print("\n[«Ver resultados» y los ejemplos llevan al resultado]")
        c = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = c.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE + "/es/")
        pg.wait_for_selector("#results .tgroup")
        check(pg.eval_on_selector_all(".flow__b", FLOW) == ["step", "-", "-"], "arranca en el paso 1")
        pg.click("#cta-results")
        pg.wait_for_timeout(1200)
        top = pg.evaluate("Math.round(document.getElementById('results-sec').getBoundingClientRect().top)")
        check(abs(top) <= 2, f"«Ver resultados» lleva hasta el resultado ({top} px)")
        check(pg.evaluate("document.activeElement.id") == "results-h", "y le da el foco al título de resultados")
        check(pg.eval_on_selector_all(".flow__b", FLOW) == ["-+done", "step", "-"], "paso 1 hecho, paso 2 actual")
        pg.evaluate("window.scrollTo(0, 0)")
        pg.click('.preset[data-cm="40,25,20"]')
        pg.wait_for_timeout(1200)
        top = pg.evaluate("Math.round(document.getElementById('results-sec').getBoundingClientRect().top)")
        vals = [pg.input_value(s) for s in ("#dim-a", "#dim-b", "#dim-c", "#weight")]
        check(abs(top) <= 2 and vals == ["40", "25", "20", "6"], f"un ejemplo carga sus medidas y también lleva al resultado ({vals}, {top} px)")
        labels = pg.eval_on_selector_all(".preset", "els => els.map(e => e.firstChild.textContent.trim())")
        check(labels == ["Mochila", "Maleta de cabina", "Maleta grande"], f"los ejemplos se llaman como se pidió ({labels})")
        c.close()

        # ------------------------------------------------ 1 y 4. tus compañías
        print("\n[tus compañías: misma cuenta, arriba y marcadas]")
        for lang, path in (("es", "/es/"), ("en", "/")):
            c = browser.new_context(viewport={"width": 1280, "height": 900})
            pg = c.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(BASE + path + "?region=all")
            pg.wait_for_selector("#results .tgroup")
            check(pg.locator("#mine-list li").count() == 0 and pg.text_content("#cmp-badge") == "",
                  f"{lang}: arranca sin compañías propias (las del comparador de arranque no cuentan)")
            check(pg.locator("#oplist .opt.is-on").count() == 3, f"{lang}: el comparador sigue arrancando con tres")
            check(pg.locator("#mine-cmp").is_hidden(), f"{lang}: sin compañías, no hay botón de comparar")
            pg.fill("#mine-q", "ib")
            pg.wait_for_timeout(80)
            sug = pg.eval_on_selector_all("#mine-sug .msug", "els => els.map(e => [e.dataset.id, e.querySelector('.vbadge').textContent.trim()])")
            check(len(sug) == 1 and sug[0][0] == "iberia", f"{lang}: «ib» sugiere Iberia ({[s[0] for s in sug]})")
            check(sug and sug[0][1] == pg.evaluate(GROUP_VERDICT, "iberia"),
                  f"{lang}: la sugerencia ya dice cómo le va a tu maleta, igual que la fila de Iberia ({sug[0][1] if sug else None})")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(80)
            pin(pg, "easy")
            pin(pg, "ryan")
            cards = pg.eval_on_selector_all("#mine-list .mcard", "els => els.map(e => [e.querySelector('.mcard__name').textContent, e.querySelector('.vbadge').textContent.trim()])")
            check([n for n, _ in cards] == ["Iberia", "easyJet", "Ryanair"], f"{lang}: Enter y clic fijan, en el orden elegido ({[n for n, _ in cards]})")
            same = all(v == pg.evaluate(GROUP_VERDICT, i) for (n, v), i in zip(cards, ("iberia", "easyjet", "ryanair")))
            check(same, f"{lang}: cada tarjeta fijada dice el mismo veredicto que su fila de abajo ({[v for _, v in cards]})")
            check(pg.locator(".rcard.is-mine").count() == 3, f"{lang}: las tres se marcan también en los grupos")
            check(pg.text_content("#cmp-badge") == "3", f"{lang}: el paso 3 cuenta 3")
            pin(pg, "vue")
            check(pg.locator("#mine-list li").count() == 3 and pg.text_content("#mine-note").strip() != "",
                  f"{lang}: una cuarta no entra y se avisa")
            xl = pg.get_attribute("#mine-list .mcard:nth-child(2) .mcard__x", "aria-label")
            check(xl and "easyJet" in xl, f"{lang}: la × tiene nombre para lectores de pantalla ({xl})")
            # enlace compartido: lleva las compañías elegidas (?c=)
            pg.evaluate("window.__copied = ''; navigator.clipboard.writeText = t => { window.__copied = t; return Promise.resolve(); }")
            pg.click("#share-btn")
            pg.wait_for_timeout(200)
            copied = pg.evaluate("window.__copied")
            m = re.search(r"https?://\S+", copied or "")
            qs = parse_qs(urlparse(m.group(0)).query) if m else {}
            check(qs.get("c") == ["iberia,easyjet,ryanair"], f"{lang}: compartir manda tus compañías en el enlace ({qs.get('c')})")
            url = m.group(0) if m else ""
            c2 = browser.new_context(viewport={"width": 1280, "height": 900})
            pg2 = c2.new_page()
            pg2.on("pageerror", lambda e: errors.append(str(e)))
            pg2.goto(url + "&region=all")
            pg2.wait_for_selector("#mine-list .mcard")
            got = pg2.eval_on_selector_all("#mine-list .mcard__name", "els => els.map(e => e.textContent)")
            check(got == ["Iberia", "easyJet", "Ryanair"], f"{lang}: un enlace con ?c= llega con esas compañías fijadas ({got})")
            check(pg2.eval_on_selector_all(".flow__b", FLOW) == ["-+done", "step", "-"], f"{lang}: y en el paso 2")
            c2.close()
            pg.click("#mine-cmp")
            pg.wait_for_timeout(900)
            names = pg.eval_on_selector_all(".cmp .cmp__name", "els => els.map(e => e.textContent)")
            check(pg.is_visible("#panel-compare") and names == ["Iberia", "easyJet", "Ryanair"],
                  f"{lang}: «Compararlas» abre el paso 3 con esas mismas ({names})")
            check(pg.eval_on_selector_all(".flow__b", FLOW) == ["-+done", "-+done", "step"], f"{lang}: pasos 1 y 2 hechos, 3 actual")
            # ------------------------------------------------ 5. líneas del comparador
            bl = pg.evaluate("""() => { const td = document.querySelector('.cmp tbody tr:not(.cmp__label) td + td');
                                        const s = getComputedStyle(td); return [s.borderLeftStyle, parseFloat(s.borderLeftWidth)]; }""")
            check(bl[0] == "solid" and bl[1] >= 1, f"{lang}: líneas verticales entre columnas ({bl})")
            # ------------------------------------------------ 7. computadora en dos columnas
            pg.click("#tab-check")
            pg.wait_for_timeout(600)
            lay = pg.evaluate("""() => { const a = document.querySelector('#panel-check > .panel').getBoundingClientRect(),
                                               b = document.querySelector('#panel-check > .results').getBoundingClientRect();
                                         return [Math.round(a.right), Math.round(b.left), Math.round(Math.abs(a.top - b.top))]; }""")
            check(lay[0] <= lay[1] and lay[2] <= 4, f"{lang}: en computadora, medidas a la izquierda y resultados a la derecha ({lay})")
            pg.click("#mine-list .mcard:first-child .mcard__x")
            pg.wait_for_timeout(80)
            check(pg.locator("#mine-list li").count() == 2, f"{lang}: la × quita una")
            c.close()

        # ------------------------------------------------ 6. contraste del botón
        print("\n[el botón verde se lee]")
        for dark in (False, True):
            c = browser.new_context(viewport={"width": 390, "height": 844})
            if dark:
                c.add_init_script("try{sessionStorage.setItem('wib-theme','dark')}catch(e){}")
            pg = c.new_page()
            pg.goto(BASE + "/es/")
            col = pg.evaluate("[getComputedStyle(document.getElementById('cta-results')).backgroundColor, getComputedStyle(document.getElementById('cta-results')).color]")
            cr = contrast(col[0], col[1])
            check(cr >= 4.5, f"{'noche' if dark else 'día'}: contraste de «Ver resultados» {cr:.2f}:1")
            c.close()

        # ------------------------------------------------ 8. sin desborde, con tres fijadas
        print("\n[sin scroll de costado]")
        over = []
        for w in (320, 375, 390):
            c = browser.new_context(viewport={"width": w, "height": 800}, is_mobile=True, has_touch=True)
            pg = c.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for path in ("/", "/es/"):
                pg.goto(BASE + path + "?l=55&w=40&h=23&kg=9&c=iberia,easyjet,ryanair&region=all")
                pg.wait_for_selector("#mine-list .mcard")
                pg.fill("#mine-q", "a")
                pg.wait_for_timeout(60)
                sw = pg.evaluate("document.documentElement.scrollWidth")
                if sw > w: over.append((w, path, "check", sw))
                pg.click("#tab-compare")
                pg.wait_for_timeout(100)
                sw = pg.evaluate("document.documentElement.scrollWidth")
                if sw > w: over.append((w, path, "compare", sw))
            c.close()
        check(not over, f"/ y /es/ × 3 anchos × 2 pasos sin desborde ({over[:3]})")

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
