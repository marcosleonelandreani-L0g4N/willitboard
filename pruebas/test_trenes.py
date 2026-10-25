"""
Trenes con medidas (25/10/2026): TGV INOUI y OUIGO, los primeros trenes
dimensionales del dataset.

Lo que importa:
- en un tren, la ficha y el comparador dicen "Hand luggage / Suitcase"
  ("Bolso de mano / Maleta"), nunca "Personal item / Cabin bag";
- las aerolíneas siguen diciendo "Personal item / Cabin bag" (no se rompió nada);
- OUIGO publica "with no weight limit": la ficha dice "sin límite de peso, según
  OUIGO" y NUNCA "no hay límite publicado" para esa franquicia;
- el rótulo cambia, el veredicto no: la misma maleta da la misma banda en la
  home y en la ficha, y en los dos idiomas;
- ninguna cifra se escribe a mano: las medidas que se ven son las del dataset.

Uso: python3 pruebas/test_trenes.py   (después de convert.py y build_site.py)
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
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402  (rutas de ficha: una sola fuente)

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    status = "OK  " if condition else "FALLA"
    print(f"  {status} {label}" + ("" if condition else f"  -> {detail}"))
    if not condition:
        failures.append(label)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def dims(op, key):
    m = op[key]["max_cm"]
    return f'{m["length"]} × {m["width"]} × {m["height"]} cm'


def main() -> None:
    data = json.loads((PUBLIC / "operators.json").read_text(encoding="utf-8"))
    ops = {o["id"]: o for o in data["operators"]}
    S = {lang: build_site.load_strings(lang) for lang in ("en", "es")}
    rail = [o for o in data["operators"] if o["type"] == "rail" and o["limit_type"] == "dimensional"]

    print("Dataset")
    check("hay trenes con medidas publicados", len(rail) >= 2, str([o["id"] for o in rail]))
    check("OUIGO: no_weight_limit = true y sin peso numérico",
          ops["ouigo"]["cabin_bag"]["no_weight_limit"] is True and ops["ouigo"]["cabin_bag"]["max_kg"] is None)
    check("TGV INOUI: no_weight_limit = false (SNCF no dice nada del peso)",
          ops["sncf-tgv-inoui"]["cabin_bag"]["no_weight_limit"] is False)
    check("ninguna aerolínea quedó con no_weight_limit = true",
          not [o["id"] for o in data["operators"] if o["type"] == "air"
               and (o.get("cabin_bag") or {}).get("no_weight_limit")])

    handler = partial(Quiet, directory=str(PUBLIC))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            # ------------------------------------------------------ fichas
            for lang in ("en", "es"):
                T = S[lang]
                print(f"\nFichas de tren ({lang})")
                for o in rail:
                    page.goto(base + build_site.op_path(o, lang), wait_until="load")
                    labels = page.eval_on_selector_all(".allow__label", "els => els.map(e => e.textContent.trim())")
                    check(f"{o['id']}: rótulos de tren",
                          labels == [T["fiche_label_personal_rail"], T["fiche_label_cabin_rail"]], str(labels))
                    body = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
                    for bad in (T["fiche_label_personal"], T["fiche_label_cabin"]):
                        check(f"{o['id']}: no dice «{bad}»", bad not in body)
                    shown = page.eval_on_selector_all(".allow__dims", "els => els.map(e => e.firstChild.textContent.trim())")
                    check(f"{o['id']}: las medidas son las del dataset",
                          shown == [dims(o, "personal_item"), dims(o, "cabin_bag")], str(shown))
                    meta = page.get_attribute('meta[name="description"]', "content")
                    check(f"{o['id']}: descripción de tren",
                          meta == build_site.t(T, "fiche_meta_dim_rail", name=o["name"]), meta)

                    subs = page.eval_on_selector_all(".allow__dims small", "els => els.map(e => e.textContent.trim())")
                    no_limit = build_site.t(T, "allow_no_limit_op", name=o["name"])
                    if o["cabin_bag"]["no_weight_limit"]:
                        check(f"{o['id']}: la maleta dice «{no_limit}»", subs[1] == no_limit, str(subs))
                        check(f"{o['id']}: la maleta NO dice «sin límite publicado»", subs[1] != T["allow_no_kg"])
                    else:
                        check(f"{o['id']}: sin peso publicado, se dice así", subs[1] == T["allow_no_kg"], str(subs))

                print(f"\nAerolínea de control ({lang})")
                page.goto(base + build_site.op_path(ops["ryanair"], lang), wait_until="load")
                labels = page.eval_on_selector_all(".allow__label", "els => els.map(e => e.textContent.trim())")
                check("ryanair: sigue con rótulos de avión",
                      labels == [T["fiche_label_personal"], T["fiche_label_cabin"]], str(labels))

            # ------------------------------------- la cuenta en la ficha de OUIGO
            print("\nCalculadora de la ficha de OUIGO")
            for lang in ("en", "es"):
                T = S[lang]
                page.goto(base + build_site.op_path(ops["ouigo"], lang), wait_until="load")
                page.fill("#try-a", "54"); page.fill("#try-b", "34"); page.fill("#try-c", "24"); page.fill("#try-w", "25")
                page.dispatch_event("#try-a", "input")
                cls = page.get_attribute("#try-out", "class")
                detail = page.inner_text("#try-d")
                check(f"{lang}: 54×34×24 y 25 kg entra (no hay límite de peso)", "tryit__out--fits" in cls, cls)
                check(f"{lang}: el detalle nombra «{T['label_cabin_rail']}» y no «{T['label_cabin']}»",
                      T["label_cabin_rail"] in detail and T["label_cabin"] not in detail, detail)

            # ---------------------------------------------------------- home
            print("\nHome: tarjetas de tren")
            bands = {}
            for lang, path in (("en", "/"), ("es", "/es/")):
                T = S[lang]
                page.goto(f"{base}{path}?l=60&w=40&h=25&kg=12&region=all", wait_until="load")
                page.wait_for_timeout(400)
                rows = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('li.rcard[data-id]')]
                    .map(li => [li.dataset.id, {band: li.dataset.band, text: li.textContent}]))""")
                for o in rail:
                    r = rows.get(o["id"])
                    check(f"{lang} {o['id']}: aparece en los resultados", r is not None)
                    if r:
                        check(f"{lang} {o['id']}: la fila dice «{T['fiche_label_cabin_rail']}» y no los rótulos de avión",
                              T["fiche_label_cabin_rail"] in r["text"]
                              and T["fiche_label_cabin"] not in r["text"]
                              and T["fiche_label_personal"] not in r["text"], r["text"][:240])
                bands[lang] = {o["id"]: (rows.get(o["id"]) or {}).get("band") for o in rail}
                air = rows.get("ryanair")
                check(f"{lang} ryanair: la fila sigue con rótulos de avión",
                      air is not None and (T["fiche_label_cabin"] in air["text"] or T["fiche_label_personal"] in air["text"]),
                      (air or {}).get("text", "")[:200])
            print(f"  bandas: {bands['en']}")
            check("el idioma cambia el texto, nunca la banda de los trenes",
                  bands["en"] == bands["es"], str(bands))
            browser.close()
        httpd.shutdown()

    print(f"\n{checks - len(failures)}/{checks} comprobaciones OK")
    if failures:
        print("FALLARON: " + ", ".join(failures))
        sys.exit(1)
    print("Todo bien.")


if __name__ == "__main__":
    main()
