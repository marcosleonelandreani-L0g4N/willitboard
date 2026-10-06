"""
Página 404 propia (06/10/2026).

Cloudflare sirve el 404.html MÁS CERCANO a la URL pedida, con estado 404, cuando
wrangler.jsonc tiene "not_found_handling": "404-page". Esta prueba imita ese
comportamiento con un servidor local y abre las páginas en Chromium real.

Lo que importa:
- wrangler.jsonc tiene la opción (sin ella Cloudflare devuelve una página en blanco);
- una URL rota en inglés recibe la 404 en inglés, y una bajo /es/ la española;
- la 404 lleva noindex y NO lleva canonical, hreflang ni og:url;
- no está en el sitemap;
- todos sus enlaces son absolutos, porque se sirve en direcciones arbitrarias;
- cada enlace interno de la 404 existe en public/.

Uso: python3 pruebas/test_404.py
"""
from __future__ import annotations

import http.server
import re
import socketserver
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"FALLA: {label}" + (f" — {detail}" if detail else ""))


class Handler(http.server.SimpleHTTPRequestHandler):
    """Sirve public/ y, si el archivo no existe, el 404.html más cercano con 404."""

    def log_message(self, *args):  # silencio
        pass

    def send_error(self, code, message=None, explain=None):
        if code != 404:
            return super().send_error(code, message, explain)
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        while True:
            candidate = PUBLIC.joinpath(*parts, "404.html")
            if candidate.exists():
                body = candidate.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if not parts:
                return super().send_error(404)
            parts.pop()


def internal_target_exists(href: str) -> bool:
    path = href.split("#")[0].split("?")[0]
    if not path:
        return True
    rel = path.lstrip("/")
    target = PUBLIC / rel
    if path.endswith("/"):
        return (target / "index.html").exists()
    return target.exists()


def main() -> None:
    wrangler = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    check("wrangler.jsonc pide la 404 propia",
          re.search(r'"not_found_handling"\s*:\s*"404-page"', wrangler) is not None)

    sitemap = (PUBLIC / "sitemap.xml").read_text(encoding="utf-8")
    check("la 404 no está en el sitemap", "404" not in sitemap)

    for rel, lang in (("404.html", "en"), ("es/404.html", "es")):
        f = PUBLIC / rel
        check(f"existe {rel}", f.exists())
        html = f.read_text(encoding="utf-8")
        check(f"{rel}: documento completo", html.startswith("<!doctype html>"))
        check(f"{rel}: noindex", '<meta name="robots" content="noindex">' in html)
        check(f"{rel}: sin canonical", 'rel="canonical"' not in html)
        check(f"{rel}: sin hreflang", 'rel="alternate"' not in html)
        check(f"{rel}: sin og:url", 'property="og:url"' not in html)
        check(f"{rel}: lang={lang}", f'<html lang="{lang}"' in html)
        hrefs = re.findall(r'href="([^"]*)"', html)
        relative = [h for h in hrefs if not h.startswith(("/", "https://", "#", "mailto:"))]
        check(f"{rel}: todos los enlaces son absolutos", not relative, ", ".join(relative[:5]))
        broken = [h for h in hrefs if h.startswith("/") and not internal_target_exists(h)]
        check(f"{rel}: los enlaces internos existen", not broken, ", ".join(broken[:5]))

    handler = partial(Handler, directory=str(PUBLIC))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"
        cases = [
            ("/no-existe/", "en", "Page not found"),
            ("/airlines/no-existe/", "en", "Page not found"),
            ("/es/no-existe/", "es", "Página no encontrada"),
            ("/es/aerolineas/no-existe/", "es", "Página no encontrada"),
        ]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width in (375, 1280):
                page = browser.new_page(viewport={"width": width, "height": 800})
                for path, lang, h1 in cases:
                    resp = page.goto(base + path)
                    label = f"{path} a {width}px"
                    check(f"{label}: estado 404", resp is not None and resp.status == 404,
                          str(resp.status if resp else None))
                    check(f"{label}: idioma {lang}", page.evaluate("document.documentElement.lang") == lang)
                    check(f"{label}: título", page.inner_text("h1").strip() == h1)
                    check(f"{label}: sin scroll horizontal",
                          page.evaluate("document.documentElement.scrollWidth") <= width)
                    check(f"{label}: tiene la lista de operadores",
                          page.locator(".index__links a").count() > 0)
                    check(f"{label}: tipografía propia cargada",
                          page.evaluate("document.fonts.check('16px Nunito')"))
                page.close()
            browser.close()
        httpd.shutdown()

    print()
    for f in failures:
        print(f)
    print(f"\n{checks - len(failures)}/{checks} comprobaciones OK")
    if failures:
        sys.exit(1)
    print("Todo bien.")


if __name__ == "__main__":
    main()
