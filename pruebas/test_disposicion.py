"""
Guardián de la disposición de la home (30/10/2026), en Chromium real.

1. En la computadora, "Qué no se puede llevar" (#banned) va en la columna
   derecha, debajo de los resultados, al lado del panel de medidas (antes ahí
   quedaba un hueco de ~300 px y el bloque iba abajo, a todo el ancho).
2. En el teléfono va justo después de los resultados.
3. "What the colours mean" no queda pegado a las tarjetas de "How it works".
4. El atajo "Qué no puedo llevar" de arriba funciona aunque se esté en Comparar.

    python3 pruebas/test_disposicion.py
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import sys
import threading
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"

MEDIR = """(() => {
  const r = s => document.querySelector(s).getBoundingClientRect();
  const res = r('#results-sec'), ban = r('#banned'), pan = r('#panel-check > .panel');
  const steps = r('.steps'), how = r('.howto');
  return {res_left: res.left, res_bottom: res.bottom, ban_left: ban.left, ban_top: ban.top,
          ban_w: ban.width, res_w: res.width, pan_bottom: pan.bottom, pan_right: pan.right,
          gap_how: how.top - steps.bottom};
})()"""


async def main() -> int:
    from playwright.async_api import async_playwright

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Silencioso, directory=str(PUBLIC)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    ok = fallos = 0

    def check(bien: bool, nombre: str) -> None:
        nonlocal ok, fallos
        if bien:
            ok += 1
        else:
            fallos += 1
            print("FALLA:", nombre)

    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ruta in ("/", "/es/"):
            for w, h in ((1366, 900), (1920, 1000), (390, 844)):
                pg = await b.new_page(viewport={"width": w, "height": h})
                errores: list[str] = []
                pg.on("pageerror", lambda e: errores.append(str(e)))
                await pg.goto(base + ruta)
                await pg.wait_for_timeout(500)
                m = await pg.evaluate(MEDIR)
                if w >= 1000:
                    check(abs(m["ban_left"] - m["res_left"]) < 2 and abs(m["ban_w"] - m["res_w"]) < 2,
                          f"{ruta} {w}px: prohibidos en la columna de los resultados")
                    check(m["ban_left"] > m["pan_right"], f"{ruta} {w}px: prohibidos a la derecha del panel")
                    check(m["ban_top"] < m["pan_bottom"], f"{ruta} {w}px: prohibidos al lado del panel, no debajo")
                check(8 <= m["ban_top"] - m["res_bottom"] <= 48,
                      f"{ruta} {w}px: prohibidos justo después de los resultados ({m['ban_top'] - m['res_bottom']:.0f}px)")
                check(m["gap_how"] >= 8, f"{ruta} {w}px: 'colores' separado de las tarjetas ({m['gap_how']:.0f}px)")
                # atajo desde la pestaña Comparar
                await pg.click("#tab-compare")
                await pg.wait_for_timeout(200)
                await pg.click('[data-quick="banned"]')
                await pg.wait_for_timeout(800)
                vis = await pg.evaluate("(() => { const r = document.getElementById('banned').getBoundingClientRect();"
                                        " return !document.getElementById('panel-check').hidden && r.height > 0"
                                        " && r.top < innerHeight && r.bottom > 0; })()")
                check(vis, f"{ruta} {w}px: el atajo muestra los prohibidos desde Comparar")
                check(not errores, f"{ruta} {w}px: sin errores de JavaScript {errores}")
                await pg.close()
        await b.close()
    srv.shutdown()
    print(f"{ok}/{ok + fallos} comprobaciones OK")
    if not fallos:
        print("Todo bien.")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
