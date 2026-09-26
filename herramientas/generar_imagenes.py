#!/usr/bin/env python3
"""
generar_imagenes.py — genera las imágenes fijas del sitio a partir del logo.

    sitio/static/favicon-32.png        favicon para navegadores sin SVG
    sitio/static/apple-touch-icon.png  ícono al guardar el sitio en el iPhone
    sitio/static/og-en.png             vista previa al compartir un enlace (inglés)
    sitio/static/og-es.png             ídem en español

NO forma parte del build: las imágenes se generan una vez y se suben al
repositorio. Hay que volver a correrlo solo si cambia el logo o el título.
Requiere Playwright (pip install playwright; playwright install chromium).

Uso:  python3 herramientas/generar_imagenes.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402  (reusa el logo y los textos)

STATIC = ROOT / "sitio" / "static"
FONTS = STATIC / "fonts"


def mark(color_ink: str = "#172033") -> str:
    svg = build_site.brand_mark(inline=False)
    return svg.replace("<svg ", f'<svg style="color:{color_ink}" ', 1)


def fontface() -> str:
    """Las tipografías del sitio, incrustadas: una página armada en memoria no
    puede leer archivos locales por file://."""
    import base64
    rules = []
    for fam, key, weights in (("Fredoka", "fredoka", (600, 700)), ("Nunito", "nunito", (600, 800))):
        for w in weights:
            data = base64.b64encode((FONTS / f"{key}-latin-{w}-normal.woff2").read_bytes()).decode()
            rules.append(f"@font-face{{font-family:'{fam}';font-weight:{w};"
                         f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "".join(rules)


def og_html(lang: str) -> str:
    S = json.loads((ROOT / "sitio" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    sub = {
        "en": "Cabin bag limits of European airlines, trains and ferries — from each operator's own page, checked by a person.",
        "es": "Límites de equipaje de mano de aerolíneas, trenes y ferris europeos — de la página de cada operador, comprobados por una persona.",
    }[lang]
    return f"""<html><head><style>{fontface()}
    body{{margin:0;width:1200px;height:630px;overflow:hidden;font-family:Nunito,sans-serif;
      background:radial-gradient(520px 320px at 92% 6%,rgba(255,200,61,.45),transparent 70%),
      radial-gradient(520px 300px at -5% 60%,rgba(20,196,154,.18),transparent 70%),
      linear-gradient(180deg,#DDEBFF,#F3F8FF 75%,#FFFFFF)}}
    .wrap{{display:grid;grid-template-columns:1fr 400px;gap:40px;align-items:center;height:100%;padding:0 80px;box-sizing:border-box}}
    .brand{{display:flex;align-items:center;gap:16px;font:700 44px/1 Fredoka;color:#172033}}
    .brand svg{{width:72px;height:72px}}
    h1{{margin:34px 0 0;font:700 92px/1.02 Fredoka;color:#172033;letter-spacing:-.01em}}
    p{{margin:26px 0 0;font:600 30px/1.35 Nunito;color:#465370;max-width:620px}}
    .url{{margin-top:30px;font:800 26px/1 Nunito;color:#1F5EFF}}
    .art svg{{width:400px;height:400px}}
    </style></head><body><div class="wrap"><div>
    <div class="brand">{mark()}<span>Willitboard</span></div>
    <h1>{S['h1']}</h1><p>{sub}</p><div class="url">willitboard.com</div></div>
    <div class="art">{mark()}</div></div></body></html>"""


def icon_html(size: int, pad: float, bg: str | None) -> str:
    inner = size - 2 * pad
    bgcss = f"background:{bg};" if bg else "background:transparent;"
    svg = mark().replace("<svg ", '<svg width="100%" height="100%" ', 1)
    return (f"<html><body style='margin:0;width:{size}px;height:{size}px;{bgcss}"
            f"display:grid;place-items:center'><div style='width:{inner}px;height:{inner}px'>"
            f"{svg}</div></body></html>")


async def main() -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for lang in ("en", "es"):
            pg = await b.new_page(viewport={"width": 1200, "height": 630})
            await pg.set_content(og_html(lang))
            await pg.wait_for_timeout(400)
            await pg.screenshot(path=str(STATIC / f"og-{lang}.png"))
            await pg.close()
        for name, size, pad, bg in (("favicon-32.png", 32, 1, None),
                                    ("apple-touch-icon.png", 180, 18, "#FFFFFF")):
            pg = await b.new_page(viewport={"width": size, "height": size})
            await pg.set_content(icon_html(size, pad, bg))
            await pg.screenshot(path=str(STATIC / name), omit_background=bg is None)
            await pg.close()
        await b.close()
    for f in ("og-en.png", "og-es.png", "favicon-32.png", "apple-touch-icon.png"):
        print(f"  sitio/static/{f}  ({(STATIC / f).stat().st_size:,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
