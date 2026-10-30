"""
Guardián de la guía "How to measure your bag" en la home (30/10/2026).

Bug encontrado por Marcos en la PC: al abrir la guía, el texto quedaba en una
franja de 0 px y la caja medía ~2500 px de alto. Causa: el cuerpo se partía en
dos columnas según el ancho de la PANTALLA (@media), pero en la PC la guía vive
en la columna izquierda, de ~330 px. Ahora decide por el ancho de la propia guía
(@container).

Comprueba, en inglés y en español y en cuatro anchos de pantalla, que el texto
abierto tenga ancho de lectura y que la caja no se dispare de alto.

    python3 pruebas/test_guia_medir.py
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import sys
import threading
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"
ANCHOS = [(390, 844), (800, 900), (1366, 900), (1920, 1000)]
MIN_TEXTO_PX = 220
MAX_ALTO_PX = 1400


async def main() -> int:
    from playwright.async_api import async_playwright

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Silencioso, directory=str(PUBLIC))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    ok = fallos = 0
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ruta in ("/", "/es/"):
            for w, h in ANCHOS:
                pg = await b.new_page(viewport={"width": w, "height": h})
                await pg.goto(f"http://127.0.0.1:{srv.server_port}{ruta}")
                await pg.evaluate("document.getElementById('measure').open = true")
                await pg.wait_for_timeout(300)
                ancho, alto = await pg.evaluate(
                    "[document.querySelector('.measure__text').getBoundingClientRect().width,"
                    " document.getElementById('measure').getBoundingClientRect().height]")
                for nombre, bien in ((f"{ruta} {w}px: texto {ancho:.0f}px >= {MIN_TEXTO_PX}", ancho >= MIN_TEXTO_PX),
                                     (f"{ruta} {w}px: guía {alto:.0f}px <= {MAX_ALTO_PX}", alto <= MAX_ALTO_PX)):
                    if bien:
                        ok += 1
                    else:
                        fallos += 1
                        print("FALLA:", nombre)
                await pg.close()
        await b.close()
    srv.shutdown()
    total = ok + fallos
    print(f"{ok}/{total} comprobaciones OK")
    if not fallos:
        print("Todo bien.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
