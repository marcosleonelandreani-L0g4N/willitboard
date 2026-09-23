#!/usr/bin/env python3
"""
test_bilingue.py — comprueba las dos versiones del sitio en un navegador real.

Lo importante que verifica
--------------------------
1. /es/ se sirve desde es/index.html (el comportamiento por defecto de
   Cloudflare Workers con html_handling = auto-trailing-slash).
2. Un mismo equipaje produce EXACTAMENTE la misma clasificación de operadores
   en los dos idiomas. Si el idioma cambiara un veredicto, el sitio estaría
   mintiendo en uno de los dos.
3. Las citas de los operadores salen sin traducir y marcadas lang="en".
4. canonical, hreflang y lang son los correctos y recíprocos.
5. No queda texto de interfaz en inglés colgando en la página española.

Uso:  python3 pruebas/test_bilingue.py
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

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
PORT = 8099

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
    """Imita auto-trailing-slash: /es/ sirve es/index.html."""

    def log_message(self, *args):  # silencio
        pass


def serve() -> socketserver.TCPServer:
    handler = partial(Handler, directory=str(PUBLIC))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def bands_of(page) -> dict:
    """Devuelve {titulo_de_banda: [nombres de operador]} tal como se ve."""
    return page.evaluate(
        """() => {
          const out = {};
          document.querySelectorAll('#results .band').forEach(b => {
            const title = b.querySelector('h2').textContent.trim();
            out[title] = Array.from(b.querySelectorAll('.op__name'))
                              .map(n => n.textContent.trim());
          });
          return out;
        }"""
    )


def main() -> None:
    # La cantidad esperada sale del propio dataset, no de un número escrito a
    # mano: así cargar un operador nuevo no rompe el test por el motivo
    # equivocado. Lo que importa no es que sean 6 o 7, sino que TODOS los
    # publicados se clasifiquen y que los dos idiomas coincidan.
    with (PUBLIC / "operators.json").open(encoding="utf-8") as fh:
        _ops = json.load(fh)["operators"]
    esperados = len(_ops)
    # Igual con las citas: una por cada operador descriptivo publicado. Estaba
    # escrito "3" a mano y se rompió el día que entró el primer ferry.
    descriptivos = sum(1 for o in _ops if o["limit_type"] != "dimensional")
    httpd = serve()
    base = f"http://127.0.0.1:{PORT}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()

            # ---------- inglés ----------
            print("\nPágina inglesa  /")
            page.goto(f"{base}/", wait_until="networkidle")
            check("html lang=en", page.get_attribute("html", "lang") == "en")
            check(
                "canonical apunta a la raíz",
                page.get_attribute('link[rel="canonical"]', "href")
                == "https://willitboard.com/",
            )
            check(
                "hreflang es recíproco",
                page.get_attribute('link[hreflang="es"]', "href")
                == "https://willitboard.com/es/"
                and page.get_attribute('link[hreflang="en"]', "href")
                == "https://willitboard.com/",
            )
            check(
                "el selector marca English como página actual",
                page.get_attribute('.langnav a[hreflang="en"]', "aria-current") == "page"
                and page.get_attribute('.langnav a[hreflang="es"]', "aria-current") is None,
            )
            check("h1 en inglés", "Will your bag fit" in page.inner_text("h1"))
            en_bands = bands_of(page)
            n_en = sum(len(v) for v in en_bands.values())
            check(f"se clasifican los {esperados} operadores publicados",
                  n_en == esperados, f"salieron {n_en}")
            print("        " + json.dumps(en_bands, ensure_ascii=False))

            # ---------- español ----------
            print("\nPágina española  /es/")
            page.goto(f"{base}/es/", wait_until="networkidle")
            check("html lang=es", page.get_attribute("html", "lang") == "es")
            check(
                "canonical apunta a sí misma, no al inglés",
                page.get_attribute('link[rel="canonical"]', "href")
                == "https://willitboard.com/es/",
            )
            check(
                "hreflang es recíproco",
                page.get_attribute('link[hreflang="en"]', "href")
                == "https://willitboard.com/"
                and page.get_attribute('link[hreflang="es"]', "href")
                == "https://willitboard.com/es/",
            )
            check(
                "el selector marca Español como página actual",
                page.get_attribute('.langnav a[hreflang="es"]', "aria-current") == "page"
                and page.get_attribute('.langnav a[hreflang="en"]', "aria-current") is None,
            )
            check("h1 en español", "¿Entra tu maleta?" in page.inner_text("h1"))
            check(
                "el dataset se carga desde la raíz, no desde /es/",
                "Conjunto de datos" in page.inner_text("#dataset-stamp"),
                page.inner_text("#dataset-stamp"),
            )
            es_bands = bands_of(page)
            n_es = sum(len(v) for v in es_bands.values())
            check(f"se clasifican los {esperados} operadores publicados",
                  n_es == esperados, f"salieron {n_es}")
            print("        " + json.dumps(es_bands, ensure_ascii=False))

            # ---------- el punto clave ----------
            print("\nMismo equipaje, mismo veredicto")
            en_groups = sorted(sorted(v) for v in en_bands.values() if v)
            es_groups = sorted(sorted(v) for v in es_bands.values() if v)
            check(
                "los operadores se agrupan igual en los dos idiomas",
                en_groups == es_groups,
                f"EN={en_groups} ES={es_groups}",
            )

            # ---------- las citas ----------
            print("\nCitas de los operadores")
            quotes = page.evaluate(
                """() => Array.from(document.querySelectorAll('#results .op__rule')).map(q => ({
                     lang: q.getAttribute('lang'),
                     translate: q.getAttribute('translate'),
                     cite: q.getAttribute('cite'),
                     caption: q.querySelector('cite').textContent,
                     text: q.querySelector('p').textContent.slice(0, 60)
                   }))"""
            )
            check(f"hay {descriptivos} citas descriptivas, una por operador descriptivo",
                  len(quotes) == descriptivos, str(len(quotes)))
            check(
                'todas marcadas lang="en"',
                all(q["lang"] == "en" for q in quotes),
                str([q["lang"] for q in quotes]),
            )
            check(
                'todas marcadas translate="no" en la página española',
                all(q["translate"] == "no" for q in quotes),
            )
            check(
                "todas rotuladas como texto original en inglés",
                all("texto original en inglés" in q["caption"] for q in quotes),
                str([q["caption"] for q in quotes]),
            )
            check(
                "el texto de la cita sigue en inglés, sin traducir",
                all(
                    q["text"].strip()[:20]
                    for q in quotes
                )
                and any("luggage" in q["text"].lower() or "passengers" in q["text"].lower()
                        for q in quotes),
            )
            check("cada cita enlaza su fuente", all(q["cite"] for q in quotes))

            # ---------- fugas de inglés en la interfaz ----------
            print("\nInterfaz española sin restos en inglés")
            leaks = page.evaluate(
                """() => {
                  const bad = ['Travels free', 'Doesn\\'t fit', 'Fits, but costs extra',
                               'Check the baggage rule', 'Size not confirmed',
                               'Official source', 'Checked by a human', 'Your bag',
                               'Airline', 'Train', 'How to read this',
                               'Your results', 'Compare side by side',
                               'Choose operators', 'How it works',
                               'Try an example', 'Read their rule'];
                  // se ignora lo que esté dentro de una cita del operador
                  const clone = document.body.cloneNode(true);
                  clone.querySelectorAll('.op__rule p').forEach(n => n.remove());
                  const txt = clone.innerText;
                  return bad.filter(s => txt.includes(s));
                }"""
            )
            check("no quedan cadenas en inglés fuera de las citas", not leaks, str(leaks))

            # ---------- unidades ----------
            print("\nLas unidades siguen funcionando en español")
            page.click("#unit-in")
            page.wait_for_timeout(150)
            check(
                "al pasar a pulgadas el largo se convierte",
                page.input_value("#dim-a") == "19.7",
                page.input_value("#dim-a"),
            )
            check(
                "las bandas se mantienen iguales tras cambiar la unidad",
                sorted(sorted(v) for v in bands_of(page).values() if v) == es_groups,
            )

            # ---------- rediseño 23/09: cifras del hero ----------
            print("\nCifras del encabezado (salen del dataset, no se escriben a mano)")
            with (PUBLIC / "operators.json").open(encoding="utf-8") as fh:
                ops = json.load(fh)["operators"]
            nums = page.eval_on_selector_all(".stats b", "els => els.map(e => e.textContent.trim())")
            check("operadores = los del dataset",
                  nums and nums[0] == str(len(ops)), str(nums))
            check("tipos de transporte = los presentes en el dataset",
                  len(nums) > 1 and nums[1] == str(len({o["type"] for o in ops})), str(nums))

            # ---------- comparador lado a lado ----------
            print("\nComparador lado a lado")
            page.click("#unit-cm"); page.wait_for_timeout(100)
            cols = page.eval_on_selector_all(".cmp thead th", "els => els.length")
            check("arranca comparando 3 operadores", cols == 3, str(cols))
            boxes = page.eval_on_selector_all("#picker-list input", "els => els.length")
            check("el desplegable ofrece todos los operadores", boxes == len(ops), str(boxes))
            dis = page.eval_on_selector_all("#picker-list input:disabled", "els => els.length")
            check("con 3 elegidos, el resto queda bloqueado", dis == len(ops) - 3, str(dis))

            same = page.evaluate('''() => {
              const card = {};
              document.querySelectorAll('#results .rcard').forEach(c =>
                card[c.querySelector('.op__name').textContent.trim()] =
                  c.querySelector('.rcard__verdict').textContent.trim());
              const out = [];
              const names = [...document.querySelectorAll('.cmp thead .cmp__name')].map(n => n.textContent.trim());
              const verdicts = [...document.querySelectorAll('.cmp tbody tr:nth-child(2) .vbadge')].map(v => v.textContent.trim());
              names.forEach((n, i) => out.push([n, card[n], verdicts[i]]));
              return out;
            }''')
            check("el comparador dice lo mismo que la tarjeta",
                  same and all(c == v for _, c, v in same), str(same))

            page.click("#cmp-clear"); page.wait_for_timeout(150)
            check("limpiar deja el comparador vacío",
                  page.query_selector(".cmp") is None and page.query_selector(".cmp__empty") is not None)
            page.click("#results .rcard.band--rule .rcard__cmp"); page.wait_for_timeout(150)
            check("una regla escrita se compara con su cita, sin traducir",
                  page.get_attribute(".cmp__rules .op__rule", "translate") == "no")

            # ---------- filtros del resumen ----------
            print("\nFiltros del resumen")
            page.click("#summary .tile.band--rule"); page.wait_for_timeout(150)
            vis = page.evaluate("() => [...document.querySelectorAll('#results .rcard')].filter(c => !c.hidden).length")
            rules = sum(1 for o in ops if o["limit_type"] != "dimensional")
            check("filtrar por 'regla' deja solo esos", vis == rules, f"{vis} visibles")
            page.click("#summary .tile.band--rule"); page.wait_for_timeout(150)
            vis = page.evaluate("() => [...document.querySelectorAll('#results .rcard')].filter(c => !c.hidden).length")
            check("tocar de nuevo muestra todos", vis == len(ops), f"{vis} visibles")

            # ---------- móvil ----------
            print("\nMóvil a 375 px")
            phone = browser.new_page(viewport={"width": 375, "height": 800})
            for path in ("/", "/es/"):
                phone.goto(f"{base}{path}", wait_until="networkidle")
                ov = phone.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                check(f"{path}: sin desborde horizontal", ov <= 1, f"{ov}px")
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
