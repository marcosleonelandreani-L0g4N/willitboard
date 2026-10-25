#!/usr/bin/env python3
"""
generar_pines.py — genera las imágenes de los Pines de Pinterest (1000 × 1500, 2:3).

Una imagen por ficha de operador y por idioma. Decisión del 21/10/2026: las
imágenes NO llevan medidas, pesos ni precios. Un Pin queda fijo en Pinterest y
no se puede redirigir; si el operador cambia su límite, la imagen seguiría
circulando con un dato viejo. Las cifras viven solo en la ficha, que se
regenera con cada reverificación.

Lo único que sale del dataset es el nombre y el tipo de operador (aerolínea con
medidas, o regla escrita). Ninguna afirmación sobre lo que incluye la tarifa.

NO forma parte del build todavía. Requiere Playwright (igual que
generar_imagenes.py).

Uso:  python3 herramientas/generar_pines.py public/pins [id ...]
      sin ids, genera todos los operadores publicados. Escribe
      public/pins/<idioma>/<id>.jpg, que es lo que lee generar_feed.py.
"""
from __future__ import annotations

import asyncio
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "herramientas"))
from generar_imagenes import fontface, mark  # noqa: E402  (logo y tipografías del sitio)

W, H = 1000, 1500

TXT = {
    "en": {
        "q_measured": "Cabin bag:<br>will yours fit?",
        "q_measured_rail": "Train luggage:<br>will yours fit?",
        "q_rule": "Luggage rules:<br>what can you bring?",
        "lead_measured": "Type your bag's size. See in seconds where it goes:",
        "lead_rule": "{name} publishes a written rule, not measurements. We show it word for word, from the official page.",
        "pass": "No extra cost", "paid": "Fits, but costs extra", "fail": "Doesn't fit",
        "trust": "From {poss} official page, checked by a person.",
        "cta": "Check your bag", "cta_rule": "Read the rule",
    },
    "es": {
        "q_measured": "Equipaje de mano:<br>¿entra tu maleta?",
        "q_measured_rail": "Equipaje en el tren:<br>¿entra tu maleta?",
        "q_rule": "Equipaje:<br>¿qué puedes llevar?",
        "lead_measured": "Escribe sus medidas y mira al instante dónde queda:",
        "lead_rule": "{name} publica una regla escrita, no medidas. La mostramos tal cual, de la página oficial.",
        "pass": "Sin costo extra", "paid": "Entra, pero se paga aparte", "fail": "No entra",
        "trust": "De la página oficial de {name}, comprobado por una persona.",
        "cta": "Comprueba tu maleta", "cta_rule": "Lee la regla",
    },
}

# Dibujo aprobado por Marcos el 21/10/2026 (versión "F"): cartel de puerta de
# embarque, la maleta entre una regla vertical y una horizontal, y un check.
# Las reglas no llevan números a propósito: ninguna cifra en la imagen.
BAG_SVG = """<svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
<path d="M58 0v12M142 0v12" stroke="#2B3A5C" stroke-width="4"/>
<rect x="30" y="10" width="140" height="46" rx="9" fill="#172033"/>
<path d="M95 50C95 46 90 45 85 45L62 45L40 12L31 12L45 45L22 45L13 33L6 33L11 50L6 67L13 67L22 55L45 55L31 88L40 88L62 55L85 55C90 55 95 54 95 50Z" fill="#FFC83D" transform="translate(38 11) rotate(0 22.0 22.0) scale(0.44)"/>
<path d="M96 33h48m-13-13l13 13-13 13" fill="none" stroke="#FFC83D" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="230" y="80" width="34" height="186" rx="6" fill="#FFC83D" stroke="#2B3A5C" stroke-width="4"/><path d="M230 88h22" stroke="#2B3A5C" stroke-width="3"/><path d="M230 100h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 112h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 124h22" stroke="#2B3A5C" stroke-width="3"/><path d="M230 136h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 148h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 160h22" stroke="#2B3A5C" stroke-width="3"/><path d="M230 172h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 184h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 196h22" stroke="#2B3A5C" stroke-width="3"/><path d="M230 208h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 220h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 232h22" stroke="#2B3A5C" stroke-width="3"/><path d="M230 244h14" stroke="#2B3A5C" stroke-width="3"/><path d="M230 256h14" stroke="#2B3A5C" stroke-width="3"/>
<rect x="40" y="276" width="180" height="22" rx="6" fill="#FFC83D" stroke="#2B3A5C" stroke-width="4"/><path d="M48 276v16" stroke="#2B3A5C" stroke-width="3"/><path d="M60 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M72 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M84 276v16" stroke="#2B3A5C" stroke-width="3"/><path d="M96 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M108 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M120 276v16" stroke="#2B3A5C" stroke-width="3"/><path d="M132 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M144 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M156 276v16" stroke="#2B3A5C" stroke-width="3"/><path d="M168 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M180 276v10" stroke="#2B3A5C" stroke-width="3"/><path d="M192 276v16" stroke="#2B3A5C" stroke-width="3"/><path d="M204 276v10" stroke="#2B3A5C" stroke-width="3"/>
<path d="M60 105H230M60 245H230" stroke="#7AA7FF" stroke-width="3" stroke-dasharray="7 6"/>
<path d="M101.0 105v-13a11 11 0 0 1 11-11h26a11 11 0 0 1 11 11v13" fill="none" stroke="#2B3A5C" stroke-width="9"/><rect x="60" y="105" width="130" height="140" rx="18" fill="#1F5EFF" stroke="#2B3A5C" stroke-width="6"/><path d="M99.0 121v108M151.0 121v108" stroke="rgba(255,255,255,.35)" stroke-width="8" stroke-linecap="round"/><circle cx="84" cy="254" r="9" fill="#2B3A5C"/><circle cx="166" cy="254" r="9" fill="#2B3A5C"/><circle cx="190" cy="105" r="32" fill="#22C55E" stroke="#fff" stroke-width="7"/><path d="M175 106l10 10l21-23" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

RULE_SVG = """<svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
  <rect x="62" y="34" width="176" height="232" rx="20" fill="#FFFFFF" stroke="#2B3A5C" stroke-width="6"/>
  <text x="96" y="118" font-family="Fredoka" font-weight="700" font-size="90" fill="#6A43F0">“</text>
  <rect x="96" y="134" width="108" height="10" rx="5" fill="#C9D4E8"/>
  <rect x="96" y="160" width="96" height="10" rx="5" fill="#C9D4E8"/>
  <rect x="96" y="186" width="108" height="10" rx="5" fill="#C9D4E8"/>
  <rect x="96" y="212" width="70" height="10" rx="5" fill="#C9D4E8"/>
</svg>"""


def pin_html(op: dict, lang: str) -> str:
    T = TXT[lang]
    name = html.escape(op["name"])
    measured = op["limit_type"] == "dimensional"
    # Posesivo inglés: "British Airways' page", no "British Airways's".
    poss = name + ("'" if name.endswith("s") else "'s")
    # Un tren con medidas no tiene "cabin bag" (25/10/2026): pregunta propia.
    q = (T.get(f"q_measured_{op['type']}", T["q_measured"]) if measured else T["q_rule"])
    if measured:
        body = f"""<p class="lead">{T['lead_measured']}</p>
        <ul class="chips">
          <li class="c pass"><i></i>{T['pass']}</li>
          <li class="c paid"><i></i>{T['paid']}</li>
          <li class="c fail"><i></i>{T['fail']}</li>
        </ul>"""
        art = BAG_SVG
    else:
        body = f"""<p class="lead">{T['lead_rule'].format(name=name)}</p>"""
        art = RULE_SVG
    return f"""<html lang="{lang}"><head><meta charset="utf-8"><style>{fontface()}
    *{{box-sizing:border-box}}
    body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;font-family:Nunito,sans-serif;color:#172033;
      background:radial-gradient(560px 380px at 95% 4%,rgba(255,200,61,.42),transparent 70%),
      radial-gradient(520px 360px at -8% 55%,rgba(20,196,154,.16),transparent 70%),
      linear-gradient(180deg,#DDEBFF,#F3F8FF 62%,#FFFFFF)}}
    .wrap{{height:100%;padding:84px 80px 80px;display:flex;flex-direction:column}}
    .wrap>*{{flex-shrink:0}}
    .brand{{display:flex;align-items:center;gap:14px;font:700 40px/1 Fredoka}}
    .brand svg{{width:62px;height:62px}}
    .op{{margin:44px 0 0;font:700 116px/1 Fredoka;letter-spacing:-.015em;color:#1F5EFF;
      }}
    h1{{margin:22px 0 0;font:700 82px/1.04 Fredoka;letter-spacing:-.01em}}
    .art{{align-self:center;width:340px;height:340px;margin:22px 0 6px}}
    .art svg{{width:100%;height:100%}}
    .lead{{margin:6px 0 0;font:700 34px/1.3 Nunito;color:#465370}}
    .chips{{list-style:none;margin:26px 0 0;padding:0;display:grid;gap:10px}}
    .c{{display:flex;align-items:center;gap:16px;font:800 32px/1 Nunito;padding:15px 24px;border-radius:18px;border:3px solid}}
    .c i{{width:22px;height:22px;border-radius:50%;flex:none}}
    .pass{{background:#E4F8EC;border-color:#22C55E;color:#0B8457}} .pass i{{background:#22C55E}}
    .paid{{background:#FFF2D9;border-color:#F59E0B;color:#A5520A}} .paid i{{background:#F59E0B}}
    .fail{{background:#FEEBEA;border-color:#F04438;color:#D0281D}} .fail i{{background:#F04438}}
    .foot{{margin-top:auto;padding-top:30px}}
    .trust{{font:700 27px/1.35 Nunito;color:#5F6C86}}
    .cta{{margin-top:22px;display:flex;justify-content:space-between;align-items:center;
      background:#1F5EFF;color:#fff;border-radius:22px;padding:26px 34px;font:800 38px/1 Nunito}}
    .cta b{{font:700 34px/1 Fredoka;color:#FFC83D}}
    </style></head><body><div class="wrap">
    <div class="brand">{mark()}<span>Willitboard</span></div>
    <div class="op">{name}</div>
    <h1>{q}</h1>
    <div class="art">{art}</div>
    {body}
    <div class="foot">
      <div class="trust">{T['trust'].format(name=name, poss=poss)}</div>
      <div class="cta"><span>{T['cta'] if measured else T['cta_rule']} →</span><b>willitboard.com</b></div>
    </div></div></body></html>"""


async def render(ops: list[dict], out: Path) -> list[Path]:
    from playwright.async_api import async_playwright
    out.mkdir(parents=True, exist_ok=True)
    made = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for op in ops:
            for lang in ("en", "es"):
                pg = await b.new_page(viewport={"width": W, "height": H})
                await pg.set_content(pin_html(op, lang))
                await pg.wait_for_timeout(300)
                # Si algo no entra (nombres largos como "TAP Air Portugal", o el
                # español, que ocupa más), primero se achica un poco el nombre del
                # operador, después el dibujo y al final otra vez el nombre, con pisos. El botón tiene que terminar
                # dejando el margen inferior completo (80 px).
                fits_js = """() => {
                  const op = document.querySelector('.op');
                  return document.querySelector('.cta').getBoundingClientRect().bottom <= innerHeight - 80
                      && op.scrollWidth <= op.clientWidth;
                }"""
                await pg.evaluate("""(fits) => {
                  const ok = eval(fits), op = document.querySelector('.op'), art = document.querySelector('.art');
                  let a = 340, s = 116;
                  while (!ok() && s > 88) { s -= 4; op.style.fontSize = s + 'px'; }
                  while (!ok() && a > 220) { a -= 10; art.style.width = art.style.height = a + 'px'; }
                  while (!ok() && s > 64) { s -= 4; op.style.fontSize = s + 'px'; }
                }""", fits_js)
                if not await pg.evaluate(fits_js):
                    raise SystemExit(f"El Pin de {op['id']} ({lang}) no entra en {W}×{H}")
                f = out / lang / f"{op['id']}.jpg"
                f.parent.mkdir(parents=True, exist_ok=True)
                await pg.screenshot(path=str(f), type="jpeg", quality=88)
                made.append(f)
                await pg.close()
        await b.close()
    return made


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    data = json.loads((ROOT / "public" / "operators.json").read_text(encoding="utf-8"))
    ops = data["operators"]
    want = sys.argv[2:]
    if want:
        ops = [o for o in ops if o["id"] in want]
        missing = set(want) - {o["id"] for o in ops}
        if missing:
            raise SystemExit(f"No están publicados: {', '.join(sorted(missing))}")
    for f in asyncio.run(render(ops, out)):
        print(f"  {f}  ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
