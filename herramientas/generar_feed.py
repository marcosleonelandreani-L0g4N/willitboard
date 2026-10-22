#!/usr/bin/env python3
"""
generar_feed.py — los feeds RSS que Pinterest lee para crear los Pines.

    public/pins.xml       inglés  -> tablero en inglés
    public/es/pins.xml    español -> tablero en español

Lo corre todos los días la tarea de GitHub .github/workflows/pinterest.yml, y
también se puede correr a mano. Solo usa la biblioteca estándar de Python:
no hay nada que instalar.

Cómo se suelta de a poco (decisión del 21/10/2026):
  - Pinterest publica todo lo que encuentra en el feed (hasta 200 por día).
    Para no soltar los 48 de golpe, el feed solo muestra los operadores ya
    "liberados", y cada día se libera POR_DIA operadores más (uno = dos Pines,
    uno por idioma).
  - Lo liberado se guarda en herramientas/pinterest_estado.json, una lista que
    SOLO CRECE: un operador liberado no vuelve a salir del feed ni cambia de
    lugar. Así Pinterest nunca ve el mismo Pin dos veces.
  - Antes de arrancar (sin archivo de estado) el feed muestra solo el primer
    operador de la cola, para que Pinterest pueda validar el feed al conectarlo.
    El reloj arranca con  --empezar  (botón "Run workflow" en GitHub).

Qué publica cada Pin: la imagen de herramientas/generar_pines.py (sin medidas)
y un texto que tampoco lleva cifras. El enlace es la ficha del operador.

Uso:
    python3 herramientas/generar_feed.py              # tarea diaria
    python3 herramientas/generar_feed.py --empezar    # el día que se conecta Pinterest
    python3 herramientas/generar_feed.py --hoy 2026-11-03   # para pruebas
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402  (rutas de ficha, dominio y textos: una sola fuente)

DATASET = ROOT / "public" / "operators.json"
PINS_DIR = ROOT / "public" / "pins"          # imágenes: public/pins/<idioma>/<id>.jpg
ESTADO = ROOT / "herramientas" / "pinterest_estado.json"
FEEDS = {"en": ROOT / "public" / "pins.xml", "es": ROOT / "public" / "es" / "pins.xml"}
HOME = {"en": "/", "es": "/es/"}

POR_DIA = 1   # operadores por día; cada uno es un Pin en inglés y otro en español

# Orden de salida: primero lo más buscado. Un operador que no esté en esta
# lista sale después, en el orden del dataset (así uno nuevo entra solo, al
# final de la cola). Cambiar este orden NO mueve lo ya liberado.
ORDEN = [
    "ryanair", "easyjet", "wizz-air", "vueling", "iberia", "british-airways",
    "lufthansa", "klm", "air-france", "transavia", "norwegian", "sas",
    "aer-lingus", "eurowings", "tap-air-portugal", "jet2", "latam", "avianca",
    "jetsmart", "volaris", "eurostar", "deutsche-bahn", "trenitalia", "stena-line",
]

CHANNEL = {
    "en": ("Willitboard: will your cabin bag fit?",
           "Cabin bag limits from each operator's official page, checked by a person."),
    "es": ("Willitboard: ¿entra tu maleta?",
           "Límites de equipaje de mano de la página oficial de cada operador, comprobados por una persona."),
}

# Texto del Pin. Sin cifras a propósito: el Pin queda fijo en Pinterest y el
# operador puede cambiar sus límites. Las medidas viven solo en la ficha.
DESC = {
    "en": {
        "dimensional": "Will your bag fit {poss} cabin limits? Type its size on Willitboard and see in "
                       "seconds whether it goes at no extra cost, costs extra or doesn't fit. Taken from "
                       "{poss} official page and checked by a person, with the date shown on the page.",
        "descriptivo": "{name} publishes a written luggage rule instead of measurements. Read it word for "
                       "word on Willitboard, with the link to {poss} official page and the date a person "
                       "checked it.",
    },
    "es": {
        "dimensional": "¿Tu maleta entra en el equipaje de mano de {name}? Escribe sus medidas en "
                       "Willitboard y mira al instante si va sin costo extra, se paga aparte o no entra. "
                       "Sale de la página oficial de {name} y lo comprobó una persona, con la fecha a la vista.",
        "descriptivo": "{name} publica una regla escrita de equipaje, no medidas. Léela tal cual en "
                       "Willitboard, con el enlace a la página oficial de {name} y la fecha en que la "
                       "comprobó una persona.",
    },
}


def poss(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def imagen(op_id: str, lang: str) -> Path:
    return PINS_DIR / lang / f"{op_id}.jpg"


def cola(ops: list[dict]) -> list[str]:
    """Ids en orden de salida, solo los que tienen ficha publicada e imagen."""
    ids = [o["id"] for o in ops]
    orden = [i for i in ORDEN if i in ids] + [i for i in ids if i not in ORDEN]
    listos = []
    for i in orden:
        faltan = [lang for lang in FEEDS if not imagen(i, lang).exists()]
        if faltan:
            print(f"  AVISO: {i} sin imagen ({', '.join(faltan)}); queda fuera de la cola. "
                  f"Correr herramientas/generar_pines.py public/pins {i}")
            continue
        listos.append(i)
    return listos


def leer_estado() -> dict | None:
    if not ESTADO.exists():
        return None
    return json.loads(ESTADO.read_text(encoding="utf-8"))


def avanzar(estado: dict | None, q: list[str], hoy: date, empezar: bool) -> dict | None:
    """Devuelve el estado nuevo. Liberar es idempotente dentro del mismo día."""
    if estado is None:
        if not empezar:
            return None
        estado = {"inicio": hoy.isoformat(), "ultimo_dia": None, "publicados": []}
    if estado["ultimo_dia"] == hoy.isoformat():
        return estado
    if estado["ultimo_dia"] and hoy.isoformat() < estado["ultimo_dia"]:
        sys.exit(f"ERROR: la fecha {hoy} es anterior al último día liberado ({estado['ultimo_dia']}).")
    pendientes = [i for i in q if i not in estado["publicados"]]
    nuevos = pendientes[:POR_DIA]
    estado = dict(estado, publicados=estado["publicados"] + nuevos)
    estado["liberado_el"] = dict(estado.get("liberado_el", {}), **{i: hoy.isoformat() for i in nuevos})
    estado["ultimo_dia"] = hoy.isoformat()
    return estado


def item(op: dict, lang: str, dia: str) -> str:
    S = build_site.load_strings(lang)
    name = op["name"]
    kind = "dimensional" if op["limit_type"] == "dimensional" else "descriptivo"
    title = build_site.t(S, f"fiche_h1_{op['type']}", name=name)
    desc = DESC[lang][kind].format(name=name, poss=poss(name))
    link = build_site.BASE_URL + build_site.op_path(op, lang)
    img = imagen(op["id"], lang)
    img_url = f"{build_site.BASE_URL}/pins/{lang}/{op['id']}.jpg"
    when = format_datetime(datetime.fromisoformat(dia).replace(hour=6, tzinfo=timezone.utc))
    e = lambda x: html.escape(x, quote=False)
    return (f"    <item>\n"
            f"      <title>{e(title)}</title>\n"
            f"      <link>{e(link)}</link>\n"
            f"      <description>{e(desc)}</description>\n"
            f'      <guid isPermaLink="false">willitboard-pin-{lang}-{e(op["id"])}</guid>\n'
            f"      <pubDate>{when}</pubDate>\n"
            f'      <enclosure url="{html.escape(img_url)}" length="{img.stat().st_size}" type="image/jpeg"/>\n'
            f"    </item>\n")


def feed(lang: str, items: list[str]) -> str:
    title, desc = CHANNEL[lang]
    e = lambda x: html.escape(x, quote=False)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0">\n  <channel>\n'
            f"    <title>{e(title)}</title>\n"
            f"    <link>{build_site.BASE_URL}{HOME[lang]}</link>\n"
            f"    <description>{e(desc)}</description>\n"
            f"    <language>{lang}</language>\n"
            + "".join(items) +
            "  </channel>\n</rss>\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--empezar", action="store_true", help="arranca el reloj hoy (una sola vez)")
    ap.add_argument("--hoy", help="AAAA-MM-DD, para pruebas")
    a = ap.parse_args(argv)
    hoy = date.fromisoformat(a.hoy) if a.hoy else datetime.now(timezone.utc).date()

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    ops = {o["id"]: o for o in data["operators"]}
    q = cola(list(ops.values()))
    if not q:
        sys.exit("ERROR: no hay ningún operador con imagen. Correr herramientas/generar_pines.py public/pins")

    viejo = leer_estado()
    if viejo and a.empezar:
        print(f"  Ya había empezado el {viejo['inicio']}: --empezar no cambia nada.")
    estado = avanzar(viejo, q, hoy, a.empezar)
    if estado is not None and estado != viejo:
        ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if estado is None:
        # Antes de arrancar: solo el primero, para que Pinterest pueda validar
        # el feed. Fecha fija (la de su verificación) para que el archivo no
        # cambie todos los días mientras tanto.
        en_feed = [(q[0], ops[q[0]]["verified_on"])]
    else:
        # Un operador liberado que después dejó de publicarse sale del feed
        # (su ficha ya no existe), pero no vuelve a la cola.
        en_feed = [(i, estado["liberado_el"][i]) for i in estado["publicados"] if i in ops]
        # El primero ya estaba en el feed antes de arrancar: conserva la misma
        # fecha para que su item no cambie y Pinterest no lo tome como nuevo.
        if en_feed and en_feed[0][0] == estado["publicados"][0]:
            en_feed[0] = (en_feed[0][0], ops[en_feed[0][0]]["verified_on"])
    for lang, path in FEEDS.items():
        items = [item(ops[i], lang, d) for i, d in reversed(en_feed)]   # lo más nuevo arriba
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(feed(lang, items), encoding="utf-8")
        print(f"  {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {len(items)} Pines")
    estado_txt = "sin empezar" if estado is None else f"desde {estado['inicio']}"
    print(f"OK. {len(en_feed)} de {len(q)} operadores en el feed ({estado_txt}).")


if __name__ == "__main__":
    main()
