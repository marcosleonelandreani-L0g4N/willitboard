#!/usr/bin/env python3
"""
test_fichas.py — comprueba las fichas por operador en un navegador real.

Lo importante que verifica
--------------------------
1. LA CIFRA QUE SE VE ES LA DEL DATASET. Para cada franquicia dimensional, el
   texto que aparece en la ficha se compara carácter por carácter contra
   operators.json. Es la comprobación central: una ficha que muestre un número
   distinto del dato verificado es exactamente el modo de falla que el
   proyecto existe para evitar.
2. Las notas internas NUNCA se publican. El campo `notes` está en español, con
   marcas [SIN VERIFICAR], referencias a la hoja Leyenda y correcciones de
   errores del asistente. Si alguna vez se filtra a una página pública, esto
   falla.
3. Fuente oficial y fecha humana presentes en las dos versiones, y coincidentes
   con el dataset.
4. Las citas de los operadores salen sin traducir, marcadas lang y translate.
5. canonical propio, hreflang recíprocos y x-default al inglés.
6. Las fichas son alcanzables: la home enlaza a todas y ninguna da 404.
7. El sitemap lista todas las páginas y todas responden.
8. No quedan cadenas de interfaz en inglés en las fichas españolas.
9. A 375 px no hay desbordamiento horizontal.

Uso:  python3 pruebas/test_fichas.py
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
PORT = 8098
BASE_URL = "https://willitboard.com"

# Mismo mapa que build_site.py. Está duplicado a propósito: si alguien cambia
# una ruta en el generador, esta prueba tiene que fallar, no seguirlo.
TYPE_SEGMENT = {
    "air":   {"en": "airlines", "es": "es/aerolineas"},
    "rail":  {"en": "trains",   "es": "es/trenes"},
    "ferry": {"en": "ferries",  "es": "es/ferris"},
}

LEGAL = {
    "privacy":    {"en": "privacy",    "es": "es/privacidad"},
    "cookies":    {"en": "cookies",    "es": "es/cookies"},
    "disclosure": {"en": "disclosure", "es": "es/divulgacion"},
}

# Fecha de edición declarada de cada página de texto. Duplicada a propósito,
# igual que las rutas: si alguien la mueve en build_site.py sin tocarla acá, la
# prueba falla. La fecha es una afirmación y cambiarla tiene que costar algo.
LEGAL_UPDATED = {"privacy": "2026-09-26", "cookies": "2026-09-26",
                 "disclosure": "2026-09-20"}

# Guías y páginas propias (v5, 26/09/2026). "sizes" no tiene fecha manual: su
# lastmod es la última verificación humana del dataset.
GUIDES = {
    "measure": {"en": "how-to-measure-luggage", "es": "es/como-medir-una-maleta"},
    "sizes":   {"en": "cabin-bag-sizes",        "es": "es/medidas-equipaje-de-mano"},
    "about":   {"en": "about",                  "es": "es/sobre-willitboard"},
}
GUIDE_UPDATED = {"measure": "2026-09-26", "about": "2026-09-26"}
TEXT_PAGES = {**LEGAL, **GUIDES}

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FALLA {label}" + (f"  -> {detail}" if detail else ""))
        failures.append(label)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve() -> socketserver.TCPServer:
    handler = partial(Handler, directory=str(PUBLIC))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def op_path(op, lang: str) -> str:
    return f"/{TYPE_SEGMENT[op['type']][lang]}/{op['id']}/"


def triple(max_cm):
    if not isinstance(max_cm, dict):
        return None
    v = [max_cm.get("length"), max_cm.get("width"), max_cm.get("height")]
    return None if any(x is None for x in v) else v


def main() -> None:
    with (PUBLIC / "operators.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    ops = data["operators"]

    httpd = serve()
    base = f"http://127.0.0.1:{PORT}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            # ------------------------------------------------ existencia
            print("\nTodas las fichas existen en los dos idiomas")
            missing = [
                op_path(o, lang) for o in ops for lang in ("en", "es")
                if not (PUBLIC / op_path(o, lang).strip("/") / "index.html").exists()
            ]
            check(f"{len(ops)*2} archivos de ficha en disco", not missing, str(missing))

            # ------------------------------------------ una ficha por operador
            for op in ops:
                print(f"\n{op['name']}  ({op['type']}, {op['limit_type']})")
                for lang in ("en", "es"):
                    path = op_path(op, lang)
                    page.goto(f"{base}{path}", wait_until="load")
                    tag = f"{op['id']}/{lang}"

                    check(
                        f"{tag}: html lang={lang}",
                        page.get_attribute("html", "lang") == lang,
                    )
                    check(
                        f"{tag}: canonical propio",
                        page.get_attribute('link[rel="canonical"]', "href")
                        == BASE_URL + path,
                        page.get_attribute('link[rel="canonical"]', "href"),
                    )
                    check(
                        f"{tag}: hreflang recíprocos y x-default al inglés",
                        page.get_attribute('link[hreflang="en"]', "href")
                        == BASE_URL + op_path(op, "en")
                        and page.get_attribute('link[hreflang="es"]', "href")
                        == BASE_URL + op_path(op, "es")
                        and page.get_attribute('link[hreflang="x-default"]', "href")
                        == BASE_URL + op_path(op, "en"),
                    )
                    check(
                        f"{tag}: el nombre del operador está en el h1",
                        op["name"].lower() in page.inner_text("h1").lower(),
                        page.inner_text("h1"),
                    )

                    # ---- LA COMPROBACIÓN CENTRAL: la cifra que se ve
                    shown = page.eval_on_selector_all(
                        ".allow__dims",
                        "els => els.map(e => e.childNodes[0].textContent.trim())",
                    )
                    expected = []
                    for key in ("personal_item", "cabin_bag"):
                        tri = triple((op.get(key) or {}).get("max_cm"))
                        if tri:
                            expected.append(" × ".join(str(d) for d in tri) + " cm")
                    check(
                        f"{tag}: las medidas mostradas son LAS DEL DATASET",
                        shown == expected,
                        f"en pantalla {shown} / en el dataset {expected}",
                    )

                    # ---- los kg también
                    subs = page.eval_on_selector_all(
                        ".allow__dims small", "els => els.map(e => e.textContent)"
                    )
                    kgs = []
                    for key in ("personal_item", "cabin_bag"):
                        allow = op.get(key) or {}
                        if triple(allow.get("max_cm")):
                            # sin peso por bulto, vale el combinado si existe
                            kg = allow.get("max_kg")
                            if kg is None:
                                kg = op.get("combined_max_kg")
                            kgs.append(kg)
                    # Cuando el dataset no publica peso, la ficha no puede
                    # mostrar NINGUNA cifra en ese renglón: un número inventado
                    # ahí sería el peor error posible del sitio.
                    kg_ok = all(
                        (str(kg) in sub) if kg is not None
                        else not any(ch.isdigit() for ch in sub)
                        for kg, sub in zip(kgs, subs)
                    )
                    check(f"{tag}: el peso mostrado coincide con el dataset, "
                          f"y sin peso publicado no aparece ninguna cifra",
                          len(subs) == len(kgs) and kg_ok, f"{subs} vs {kgs}")

                    # ---- fuente y fecha
                    src = page.get_attribute(".provenance a", "href")
                    when = page.inner_text(".provenance time").strip()
                    check(f"{tag}: enlaza la fuente oficial del dataset",
                          src == op["source_url"], str(src))
                    check(f"{tag}: muestra la fecha de verificación del dataset",
                          when == op["verified_on"], when)

                    # ---- las notas internas no se publican jamás
                    body = page.inner_text("body")
                    venenos = ["[SIN VERIFICAR]", "hoja Leyenda", "del asistente",
                               "revision_", "decisión abierta", "NO SÉ"]
                    filtradas = [v for v in venenos if v in body]
                    nota = (op.get("notes") or "")
                    trozo = nota[:60].strip()
                    if trozo and trozo in body:
                        filtradas.append("texto literal de notes")
                    check(f"{tag}: las notas internas NO aparecen en la página",
                          not filtradas, str(filtradas))

                    # ---- la cita descriptiva
                    if op["limit_type"] != "dimensional":
                        q = page.evaluate(
                            """() => {
                              const e = document.querySelector('.op__rule');
                              if (!e) return null;
                              return { lang: e.getAttribute('lang'),
                                       translate: e.getAttribute('translate'),
                                       cite: e.getAttribute('cite'),
                                       text: e.querySelector('p').textContent };
                            }"""
                        )
                        check(f"{tag}: la ficha descriptiva muestra la cita", q is not None)
                        if q:
                            original = op["descriptive_rule"]["en"]
                            check(f"{tag}: la cita es EXACTAMENTE la del dataset",
                                  q["text"] == original,
                                  f"largo {len(q['text'])} vs {len(original)}")
                            check(f'{tag}: la cita va marcada lang="en"', q["lang"] == "en")
                            check(
                                f"{tag}: translate=no solo cuando el idioma difiere",
                                (q["translate"] == "no") if lang == "es"
                                else (q["translate"] is None),
                                str(q["translate"]),
                            )
                            check(f"{tag}: la cita enlaza su fuente",
                                  q["cite"] == op["source_url"])
                    else:
                        check(f"{tag}: la ficha dimensional no inventa una cita",
                              page.query_selector(".op__rule") is None)

                # ---- fugas de inglés en la ficha española
                page.goto(f"{base}{op_path(op, 'es')}", wait_until="load")
                leaks = page.evaluate(
                    """() => {
                      const bad = ['Official source', 'Checked by a human',
                                   'What you can take', 'Included in the fare',
                                   'Costs extra', 'Not published', 'Up to ',
                                   'Handles and wheels', 'Before you rely'];
                      const clone = document.body.cloneNode(true);
                      clone.querySelectorAll('.op__rule p').forEach(n => n.remove());
                      const txt = clone.innerText;
                      return bad.filter(s => txt.includes(s));
                    }"""
                )
                check(f"{op['id']}/es: sin restos de interfaz en inglés",
                      not leaks, str(leaks))

            # -------------------------------------- la home enlaza a las fichas
            print("\nLas fichas son alcanzables desde la home")
            for lang, home in (("en", "/"), ("es", "/es/")):
                page.goto(f"{base}{home}", wait_until="load")
                hrefs = page.eval_on_selector_all(
                    ".index__links:not(.index__links--guides) a",
                    "els => els.map(e => e.getAttribute('href'))"
                )
                want = sorted(op_path(o, lang) for o in ops)
                guides = sorted(page.eval_on_selector_all(
                    ".index__links--guides a", "els => els.map(e => e.getAttribute('href'))"))
                check(f"la home {lang} enlaza las guías",
                      guides == sorted(f"/{GUIDES[k][lang]}/" for k in ("measure", "sizes")),
                      str(guides))
                check(f"la home {lang} enlaza las {len(ops)} fichas",
                      sorted(hrefs) == want, f"{sorted(hrefs)}")
                bad = []
                for h in hrefs:
                    with urlopen(f"{base}{h}") as r:
                        if r.status != 200:
                            bad.append((h, r.status))
                check(f"ningún enlace de la home {lang} da error", not bad, str(bad))

            # -------------------------------------------- páginas de texto
            print("\nPáginas de texto (legales y guías)")
            for key, slug in TEXT_PAGES.items():
                for lang in ("en", "es"):
                    path = f"/{slug[lang]}/"
                    page.goto(f"{base}{path}", wait_until="load")
                    tag = f"{key}/{lang}"
                    check(f"{tag}: existe y tiene h1",
                          bool(page.inner_text("h1").strip()))
                    check(f"{tag}: html lang={lang}",
                          page.get_attribute("html", "lang") == lang)
                    check(f"{tag}: canonical propio",
                          page.get_attribute('link[rel="canonical"]', "href")
                          == BASE_URL + path)
                    check(
                        f"{tag}: hreflang recíprocos",
                        page.get_attribute('link[hreflang="en"]', "href")
                        == BASE_URL + f"/{slug['en']}/"
                        and page.get_attribute('link[hreflang="es"]', "href")
                        == BASE_URL + f"/{slug['es']}/",
                    )
                    # ningún marcador de plantilla sin resolver
                    body = page.inner_text("body")
                    check(f"{tag}: sin marcadores sin resolver",
                          "{{" not in body and "}}" not in body)
                    # los enlaces internos entre páginas legales resuelven
                    hrefs = page.eval_on_selector_all(
                        ".legaldoc a[href^='/'], .footlinks a",
                        "els => [...new Set(els.map(e => e.getAttribute('href')))]")
                    bad = []
                    for h in hrefs:
                        with urlopen(f"{base}{h}") as r:
                            if r.status != 200: bad.append((h, r.status))
                    check(f"{tag}: sus enlaces internos no dan error", not bad, str(bad))

            print("\nEl pie enlaza las legales desde todas las páginas")
            muestras = ["/", "/es/", op_path(ops[0], "en"), op_path(ops[0], "es")]
            for path in muestras:
                page.goto(f"{base}{path}", wait_until="load")
                lang = "es" if path.startswith("/es/") else "en"
                hrefs = sorted(page.eval_on_selector_all(
                    ".footlinks a", "els => els.map(e => e.getAttribute('href'))"))
                want = sorted(f"/{s[lang]}/" for s in TEXT_PAGES.values())
                check(f"{path}: el pie lleva a las 3 páginas legales y a las 3 guías",
                      hrefs == want, str(hrefs))

            # ------------------------------------------ tabla de medidas
            print("\nLa tabla comparativa dice lo mismo que el dataset")
            for lang in ("en", "es"):
                page.goto(f"{base}/{GUIDES['sizes'][lang]}/", wait_until="load")
                rows = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.sz tbody tr')].map(r =>
                    [r.querySelector('th a').textContent.trim(),
                     [...r.querySelectorAll('.sz__dims')].map(d => d.textContent.trim())]))""")
                dim_ops = [o for o in ops if o["limit_type"] == "dimensional"]
                ok = len(rows) == len(dim_ops)
                for o in dim_ops:
                    want_dims = [" × ".join(str(d) for d in triple((o.get(k) or {}).get("max_cm"))) + " cm"
                                 for k in ("personal_item", "cabin_bag") if triple((o.get(k) or {}).get("max_cm"))]
                    if rows.get(o["name"]) != want_dims:
                        ok = False
                check(f"tabla {lang}: cada cifra es la del dataset, carácter por carácter", ok, str(rows))

            # -------------------------------------------------------- sitemap
            print("\nSitemap")
            sm = (PUBLIC / "sitemap.xml").read_text(encoding="utf-8")
            locs = [l.split("<loc>")[1].split("</loc>")[0]
                    for l in sm.splitlines() if "<loc>" in l]
            want = (["/", "/es/"]
                    + [op_path(o, l) for o in ops for l in ("en", "es")]
                    + [f"/{s[l]}/" for s in TEXT_PAGES.values() for l in ("en", "es")])
            check("el sitemap lista todas las páginas publicadas",
                  sorted(locs) == sorted(BASE_URL + w for w in want),
                  f"{len(locs)} locs")
            bad = []
            for loc in locs:
                p = loc[len(BASE_URL):]
                with urlopen(f"{base}{p}") as r:
                    if r.status != 200:
                        bad.append((p, r.status))
            check("todas las URLs del sitemap responden", not bad, str(bad))
            fechas = [l.split("<lastmod>")[1].split("</lastmod>")[0]
                      for l in sm.splitlines() if "<lastmod>" in l]
            # Ninguna fecha del sitemap puede ser inventada: o es la fecha en que
            # una persona verificó a un operador, o es la fecha declarada de
            # edición de una página de texto. Nada de "hoy" automático.
            permitidas = ({o["verified_on"] for o in ops} | set(LEGAL_UPDATED.values())
                          | set(GUIDE_UPDATED.values()))
            check("ningún lastmod es una fecha fabricada",
                  set(fechas) <= permitidas,
                  str(sorted(set(fechas) - permitidas)))
            check("cada página de texto declara su fecha de edición en el sitemap",
                  set(LEGAL_UPDATED.values()) <= set(fechas))

            # ---------------------------------------------------------- móvil
            print("\nMóvil a 375 px")
            phone = browser.new_page(viewport={"width": 375, "height": 780})
            overflow = []
            rutas = [(op_path(o, l), f"{o['id']}/{l}") for o in ops for l in ("en", "es")]
            rutas += [(f"/{s[l]}/", f"{k}/{l}")
                      for k, s in TEXT_PAGES.items() for l in ("en", "es")]
            for path, tag in rutas:
                phone.goto(f"{base}{path}", wait_until="load")
                if phone.evaluate(
                    "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                ):
                    overflow.append(tag)
            check(f"ninguna de las {len(rutas)} páginas desborda horizontalmente",
                  not overflow, str(overflow))
            phone.close()

            browser.close()
    finally:
        httpd.shutdown()

    print(f"\n{checks - len(failures)}/{checks} comprobaciones OK")
    if failures:
        print("FALLARON: " + ", ".join(failures))
        sys.exit(1)
    print("Todo bien.")


if __name__ == "__main__":
    main()
