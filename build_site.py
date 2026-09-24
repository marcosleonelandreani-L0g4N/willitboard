#!/usr/bin/env python3
"""
build_site.py — genera las páginas de Willitboard desde UNA plantilla por tipo
de página y un diccionario por idioma.

Por qué existe
--------------
Para publicar en dos idiomas sin mantener archivos que se van desincronizando,
la fuente de verdad es:

    sitio/style.css               el CSS, una sola vez para todas las páginas
    sitio/template.html           la home: estructura y lógica del comparador
    sitio/template_operator.html  la ficha por operador
    sitio/i18n/en.json            los textos en inglés
    sitio/i18n/es.json            los textos en español
    public/operators.json         los DATOS, que genera convert.py

y este script emite:

    public/index.html                    (inglés,  canonical https://willitboard.com/)
    public/es/index.html                 (español, canonical https://willitboard.com/es/)
    public/airlines/{id}/index.html      ficha en inglés
    public/es/aerolineas/{id}/index.html ficha en español
    public/trains|ferries/...            ídem para rail y ferry
    public/sitemap.xml                   todas las páginas publicadas

Reglas que el script hace cumplir
---------------------------------
1. Los dos idiomas comparten la MISMA lógica de comparación. El idioma cambia
   el texto, nunca el veredicto.
2. Los dos idiomas usan el MISMO dataset, cargado desde /operators.json con
   ruta absoluta. No hay una copia por carpeta.
3. Las claves de los dos diccionarios tienen que coincidir exactamente. Si a
   uno le falta una clave que el otro tiene, el build falla: es la forma de
   que una traducción a medias no llegue a producción disfrazada de texto en
   inglés.
4. Ningún dato de equipaje se escribe acá. Medidas, condiciones, citas,
   fuentes y fechas se LEEN de operators.json y se muestran tal cual. Este
   script no inventa, no redondea y no completa huecos.
5. El campo `notes` de un operador NUNCA se publica: son notas internas de
   trabajo, en español, con marcas [SIN VERIFICAR] y correcciones de errores.
   La ficha publica solo campos estructurados y la cita descriptiva.
6. Las citas de los operadores no se traducen nunca.

Uso:  python3 build_site.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "sitio"
TEMPLATE = SITE_DIR / "template.html"
TEMPLATE_OP = SITE_DIR / "template_operator.html"
TEMPLATE_PAGE = SITE_DIR / "template_page.html"
LEGAL_DIR = SITE_DIR / "legal"
STYLE = SITE_DIR / "style.css"
I18N_DIR = SITE_DIR / "i18n"
OUT_DIR = ROOT / "public"
DATASET = OUT_DIR / "operators.json"

BASE_URL = "https://willitboard.com"

# lang -> (subcarpeta de salida, ruta canónica)
PAGES = {
    "en": ("", "/"),
    "es": ("es", "/es/"),
}

# tipo de operador -> segmento de URL por idioma.
# El {id} del slug ES el id del dataset, sin traducir: una sola fuente para el
# identificador evita que la URL y el dato se despeguen.
TYPE_SEGMENT = {
    "air":   {"en": "airlines", "es": "es/aerolineas"},
    "rail":  {"en": "trains",   "es": "es/trenes"},
    "ferry": {"en": "ferries",  "es": "es/ferris"},
}

# clave del diccionario para el nombre del tipo en la miga de pan
TYPE_CRUMB = {"air": "crumbs_air", "rail": "crumbs_rail", "ferry": "crumbs_ferry"}

# Páginas de texto. El cuerpo de cada una está en sitio/legal/<clave>.<idioma>.html.
#
# `updated` es la fecha en que se editó EL CONTENIDO, escrita a mano. No es la
# fecha del build a propósito: si se moviera sola en cada regeneración, la página
# estaría fingiendo frescura, que es exactamente lo que este proyecto no hace con
# ningún otro dato. Cambiar el texto de una página = cambiar su fecha acá.
LEGAL_PAGES = {
    "privacy": {
        "slug": {"en": "privacy", "es": "es/privacidad"},
        "nav": "nav_privacy",
        "updated": "2026-09-20",
    },
    "cookies": {
        "slug": {"en": "cookies", "es": "es/cookies"},
        "nav": "nav_cookies",
        "updated": "2026-09-20",
    },
    "disclosure": {
        "slug": {"en": "disclosure", "es": "es/divulgacion"},
        "nav": "nav_disclosure",
        "updated": "2026-09-20",
    },
}

# marcadores que calcula el script, no el diccionario
COMPUTED_HOME = {"LANG", "CANONICAL", "NAV_EN_CUR", "NAV_ES_CUR", "STRINGS_JSON", "FICHE_PATHS",
                 "STYLE", "OPERATOR_INDEX", "FOOTER_LINKS", "HERO_STATS"}
COMPUTED_OP = {"LANG", "CANONICAL", "STYLE", "DOC_TITLE", "META_DESCRIPTION",
               "HREF_EN", "HREF_ES", "NAV_EN_PATH", "NAV_ES_PATH",
               "NAV_EN_CUR", "NAV_ES_CUR", "CRUMBS", "H1", "STANDFIRST",
               "PROVENANCE", "ALLOWANCES", "RULE", "WHEELS", "CAVEATS",
               "CHECKER_HREF", "FICHE_STAMP", "FOOTER_LINKS"}
COMPUTED_PAGE = {"LANG", "CANONICAL", "STYLE", "DOC_TITLE", "META_DESCRIPTION",
                 "HREF_EN", "HREF_ES", "NAV_EN_PATH", "NAV_ES_PATH",
                 "NAV_EN_CUR", "NAV_ES_CUR", "CRUMB_SELF", "H1", "STANDFIRST",
                 "CONTENT", "CHECKER_HREF", "PAGE_UPDATED", "FOOTER_LINKS"}


# ---------------------------------------------------------------- diccionarios

def is_note(key: str) -> bool:
    """Las claves que empiezan con "_" son notas para nosotros, no textos."""
    return key.startswith("_")


def load_strings(lang: str) -> dict:
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        sys.exit(f"ERROR: falta el diccionario {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not is_note(k)}


def check_key_parity(dicts: dict[str, dict]) -> None:
    """Todos los idiomas tienen que tener exactamente las mismas claves."""
    reference_lang = "en"
    reference = set(dicts[reference_lang])
    problems = []
    for lang, d in dicts.items():
        if lang == reference_lang:
            continue
        missing = sorted(reference - set(d))
        extra = sorted(set(d) - reference)
        if missing:
            problems.append(f"  {lang}.json: faltan {len(missing)} claves -> {', '.join(missing)}")
        if extra:
            problems.append(f"  {lang}.json: sobran {len(extra)} claves -> {', '.join(extra)}")
    if problems:
        sys.exit("ERROR: los diccionarios no coinciden.\n" + "\n".join(problems))


def check_placeholders(dicts: dict[str, dict]) -> None:
    """
    Una cadena traducida tiene que usar los mismos {marcadores} que el original.
    Si la traducción se come un {dims}, la página sale con un hueco donde iba
    una medida. Esto lo detecta antes de publicar.
    """
    ref = dicts["en"]
    problems = []
    for lang, d in dicts.items():
        if lang == "en":
            continue
        for key, value in ref.items():
            want = set(re.findall(r"\{(\w+)\}", value))
            got = set(re.findall(r"\{(\w+)\}", d[key]))
            if want != got:
                problems.append(
                    f"  {lang}.json / {key}: marcadores esperados {sorted(want) or '[]'}, "
                    f"encontrados {sorted(got) or '[]'}"
                )
    if problems:
        sys.exit("ERROR: marcadores desalineados entre idiomas.\n" + "\n".join(problems))


def check_template_keys(template: str, strings: dict, computed: set, label: str) -> set:
    """Todo {{marcador}} de la plantilla tiene que resolverse."""
    used = set(re.findall(r"\{\{(\w+)\}\}", template))
    unknown = sorted(used - computed - set(strings))
    if unknown:
        sys.exit(
            f"ERROR: {label} usa marcadores que no existen en el diccionario:\n  "
            + ", ".join(unknown)
        )
    return set(strings) - used


# ------------------------------------------------------------------ utilidades

def t(strings: dict, key: str, **vars) -> str:
    """Mismo comportamiento que la función t() del navegador."""
    s = strings.get(key)
    if s is None:
        sys.exit(f"ERROR: falta la clave de texto '{key}'")
    if not vars:
        return s
    return re.sub(
        r"\{(\w+)\}",
        lambda m: "" if vars.get(m.group(1)) is None else str(vars[m.group(1)]),
        s,
    )


def esc(value) -> str:
    """Todo lo que venga de operators.json pasa por acá antes de ir al HTML."""
    return html.escape(str(value), quote=True)


def render(template: str, values: dict) -> str:
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            sys.exit(f"ERROR: marcador sin valor: {{{{{key}}}}}")
        return values[key]

    # re.sub no vuelve a escanear lo que inserta, así que el CSS y el JSON
    # inyectados no pueden disparar sustituciones nuevas.
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


# ------------------------------------------------------- lectura del dataset

def triple(max_cm) -> list | None:
    """Devuelve [largo, ancho, alto] solo si la terna está COMPLETA."""
    if not isinstance(max_cm, dict):
        return None
    v = [max_cm.get("length"), max_cm.get("width"), max_cm.get("height")]
    return None if any(x is None for x in v) else v


def rule_text(op) -> tuple[str | None, str | None]:
    """(texto, idioma) de la regla descriptiva, en su idioma original."""
    dr = op.get("descriptive_rule") or {}
    if dr.get("en"):
        return dr["en"], "en"
    if dr.get("es"):
        return dr["es"], "es"
    return None, None


def is_publishable(op) -> tuple[bool, str]:
    """
    Umbral de publicación (WILLITBOARD_SEO_ARQUITECTURA.md, sección 2.2), con
    la rama que faltaba para los operadores descriptivos.

    Una ficha no se publica indexable si le faltan los datos que la hacen útil.
    Pero "útil" no significa lo mismo para los dos tipos de operador:

      - dimensional: hace falta al menos una terna completa Y que
        cabina_incluida esté resuelta (SI o NO, no vacío). Sin eso la ficha
        sería media página de "sin confirmar".
      - descriptivo: hace falta la regla oficial con texto. Ahí el contenido
        ES la cita, y una ficha con la regla entera del operador, su fuente y
        su fecha no es una página fina: es exactamente lo que busca alguien
        que quiere saber qué se puede subir a ese tren.

    fuente_url y verificado_el ya los exige convert.py: nada sin ellos llega
    hasta acá.
    """
    if op.get("limit_type") == "dimensional":
        has_triple = any(
            triple((op.get(k) or {}).get("max_cm")) for k in ("personal_item", "cabin_bag")
        )
        cabin = op.get("cabin_bag")
        cabin_resolved = isinstance(cabin, dict) and cabin.get("included") is not None
        if not has_triple:
            return False, "sin ninguna terna dimensional completa"
        if not cabin_resolved:
            return False, "cabina_incluida sin resolver"
        return True, ""
    text, _ = rule_text(op)
    if not (text or "").strip():
        return False, "regla descriptiva vacía"
    return True, ""


# ------------------------------------------------------------ rutas de ficha

def op_path(op, lang: str) -> str:
    """Ruta canónica de la ficha, con barra final. Ej: /airlines/ryanair/"""
    seg = TYPE_SEGMENT[op["type"]][lang]
    return f"/{seg}/{op['id']}/"


def op_outfile(op, lang: str) -> Path:
    seg = TYPE_SEGMENT[op["type"]][lang]
    return OUT_DIR / seg / op["id"] / "index.html"


# --------------------------------------------------- bloques HTML de la ficha

def block_crumbs(op, lang: str, S: dict) -> str:
    home = PAGES[lang][1]
    return (
        f'      <a href="{home}">{t(S, "crumbs_home")}</a>\n'
        f'      <span aria-hidden="true">/</span>\n'
        f'      <span>{t(S, TYPE_CRUMB[op["type"]])}</span>\n'
        f'      <span aria-hidden="true">/</span>\n'
        f'      <span>{esc(op["name"])}</span>'
    )


def block_provenance(op, S: dict) -> str:
    when = esc(op["verified_on"])
    return (
        f'    <span><a href="{esc(op["source_url"])}" target="_blank" '
        f'rel="noopener nofollow">{t(S, "prov_source")} ↗</a></span>\n'
        f'    <span>{t(S, "prov_checked")} <time datetime="{when}">{when}</time></span>\n'
        f'    <span>{t(S, "prov_why")}</span>'
    )


def one_allowance(op, key: str, label_key: str, S: dict) -> str:
    allow = op.get(key)
    if not isinstance(allow, dict):
        return ""
    included = allow.get("included")
    if included is True:
        status_cls, status_txt = "status--free", t(S, "status_free")
    elif included is False:
        status_cls, status_txt = "status--paid", t(S, "status_paid")
    else:
        status_cls, status_txt = "status--none", t(S, "status_unknown")

    dims = triple(allow.get("max_cm"))
    if dims:
        kg = allow.get("max_kg")
        sub = t(S, "allow_kg", kg=kg) if kg is not None else t(S, "allow_no_kg")
        figure = (
            f'      <p class="allow__dims">{esc(" × ".join(str(d) for d in dims))} cm'
            f"<small>{sub}</small></p>"
        )
    else:
        figure = f'      <p class="allow__none">{t(S, "allow_not_published", name=esc(op["name"]))}</p>'

    addon = allow.get("requires_addon")
    addon_html = (
        f'\n      <p class="allow__addon">{t(S, "allow_addon", addon=esc(addon))}</p>'
        if included is False and addon else ""
    )

    return (
        f'    <div class="allow">\n'
        f'      <p class="allow__label">{t(S, label_key)}</p>\n'
        f'      <span class="status {status_cls}">{status_txt}</span>\n'
        f"{figure}{addon_html}\n"
        f"    </div>"
    )


def block_allowances(op, S: dict) -> str:
    if op.get("limit_type") != "dimensional":
        return ""
    parts = [
        one_allowance(op, "personal_item", "fiche_label_personal", S),
        one_allowance(op, "cabin_bag", "fiche_label_cabin", S),
    ]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    inner = "\n".join(parts)
    fare = op.get("reference_fare")
    fare_html = f'    <p class="allows__fare">{t(S, "fiche_fare", fare=esc(fare))}</p>\n' if fare else ""
    return (
        '  <section aria-labelledby="allowances-h">\n'
        f'    <h2 id="allowances-h">{t(S, "fiche_allowances_h")}</h2>\n'
        f"{fare_html}"
        f'    <div class="allows">\n{inner}\n    </div>\n'
        "  </section>"
    )


def block_rule(op, lang: str, S: dict) -> str:
    """
    La cita del operador NO se traduce nunca. Se marca su idioma real y, si no
    coincide con el de la página, se rotula y se le pide a los traductores
    automáticos que la dejen tal cual. Mismo criterio que la home.
    """
    text, rule_lang = rule_text(op)
    if not text:
        return ""
    attrs = f' lang="{rule_lang}"'
    if rule_lang != lang:
        attrs += ' translate="no"'
    caption = t(S, "cite_words", name=esc(op["name"]))
    if rule_lang != lang:
        caption += t(S, f"cite_orig_{rule_lang}")
    return (
        '  <section class="prose" aria-labelledby="rule-h">\n'
        f'    <h2 id="rule-h">{t(S, "fiche_rule_h", name=esc(op["name"]))}</h2>\n'
        f'    <blockquote class="op__rule band--rule"{attrs} cite="{esc(op["source_url"])}">\n'
        f'      <cite lang="{lang}">{caption}</cite>\n'
        f'      <p style="margin:0">{esc(text)}</p>\n'
        "    </blockquote>\n"
        "  </section>"
    )


def block_wheels(op, S: dict) -> str:
    if op.get("limit_type") != "dimensional":
        return ""
    w = op.get("wheels_handles") or {}
    basis = w.get("included_in_measurement")
    tol = w.get("tolerance_cm")
    if basis is True:
        text = t(S, "flag_wheels_included")
    elif basis is False:
        text = (t(S, "flag_wheels_excluded_tol", tol=tol) if tol is not None
                else t(S, "flag_wheels_excluded"))
    else:
        text = t(S, "flag_wheels_unknown")
    return (
        '  <section class="prose">\n'
        f'    <h2>{t(S, "fiche_wheels_h")}</h2>\n'
        f'    <p class="caveat">{text}</p>\n'
        "  </section>"
    )


def block_caveats(op, S: dict) -> str:
    lines = [t(S, "caveat_missing")]
    if op.get("limit_type") == "dimensional":
        fare = op.get("reference_fare")
        lines.append(t(S, "caveat_fares_named", fare=esc(fare)) if fare else t(S, "caveat_fares"))
    lines.append(t(S, "p_noguarantee"))
    return "\n".join(f'    <p class="caveat">{line}</p>' for line in lines)


# --------------------------------------------- índice de operadores en la home

def block_operator_index(ops: list, lang: str, S: dict) -> str:
    """
    Enlaces HTML reales a cada ficha, agrupados por tipo. Sin esto las fichas
    quedarían huérfanas: accesibles por sitemap pero sin ningún enlace interno
    que las conecte con el resto del sitio.
    """
    if not ops:
        return ""
    groups = []
    for kind in ("air", "rail", "ferry"):
        mine = [o for o in ops if o["type"] == kind]
        if not mine:
            continue
        links = "\n".join(
            f'        <li><a href="{op_path(o, lang)}">{esc(o["name"])}</a></li>'
            for o in sorted(mine, key=lambda o: o["name"].lower())
        )
        groups.append(
            f'    <div class="index__group">\n'
            f'      <h3>{t(S, TYPE_CRUMB[kind])}</h3>\n'
            f'      <ul class="index__links">\n{links}\n      </ul>\n'
            f"    </div>"
        )
    return (
        '  <section class="prose" aria-labelledby="index-h">\n'
        f'    <h2 id="index-h">{t(S, "index_h2")}</h2>\n'
        f'    <p>{t(S, "index_intro")}</p>\n'
        + "\n".join(groups)
        + "\n  </section>"
    )


# ------------------------------------------------------- páginas de texto

def legal_path(key: str, lang: str) -> str:
    return f"/{LEGAL_PAGES[key]['slug'][lang]}/"


def legal_outfile(key: str, lang: str) -> Path:
    return OUT_DIR / LEGAL_PAGES[key]["slug"][lang] / "index.html"


def block_footer_links(lang: str, S: dict, current: str | None = None) -> str:
    """
    Enlaces legales en el pie de TODAS las páginas. Una política de privacidad
    a la que no se llega desde ninguna parte no sirve de nada.
    """
    items = []
    for key, cfg in LEGAL_PAGES.items():
        cur = ' aria-current="page"' if key == current else ""
        items.append(
            f'      <li><a href="{legal_path(key, lang)}"{cur}>{t(S, cfg["nav"])}</a></li>'
        )
    return (
        f'    <ul class="footlinks" aria-label="{t(S, "footer_legal_label")}">\n'
        + "\n".join(items)
        + "\n    </ul>"
    )


def load_fragment(key: str, lang: str) -> str:
    """
    El cuerpo de cada página de texto vive como fragmento HTML propio, no en el
    diccionario: son miles de palabras de prosa y meterlas en una cadena JSON
    las volvería imposibles de editar y de revisar.
    """
    path = LEGAL_DIR / f"{key}.{lang}.html"
    if not path.exists():
        sys.exit(f"ERROR: falta el contenido {path}")
    fragment = path.read_text(encoding="utf-8").rstrip("\n")
    # Los fragmentos se enlazan entre sí. Se resuelve acá, antes de insertarlos,
    # porque render() no vuelve a escanear lo que ya insertó.
    hrefs = {f"HREF_{k.upper()}": legal_path(k, lang) for k in LEGAL_PAGES}
    unknown = set(re.findall(r"\{\{(\w+)\}\}", fragment)) - set(hrefs)
    if unknown:
        sys.exit(f"ERROR: {path} usa marcadores desconocidos: {', '.join(sorted(unknown))}")
    return render(fragment, hrefs)


# ---------------------------------------------------------- cifras del hero

def block_hero_stats(ops: list, S: dict) -> str:
    """
    Las tres cifras del encabezado de la home. TODAS salen del dataset
    publicado en el momento del build; ninguna se escribe a mano. Es el
    equivalente honesto del "10.000 viajeros confían en nosotros" de los
    constructores de sitios: llamativo, pero verdadero y comprobable.

    - operadores: los que tienen ficha publicada.
    - tipos de transporte: los que aparecen de verdad en el dataset (hoy
      avión y tren; el día que se cargue un ferry, pasa a 3 solo).
    - límites copiados de blogs: 0, porque convert.py rechaza cualquier fila
      sin fuente oficial y fecha humana. Si eso dejara de ser cierto, esta
      cifra tendría que desaparecer, no cambiar.
    """
    modes = len({o["type"] for o in ops})
    items = [
        (len(ops), t(S, "stat_ops_label")),
        (modes, t(S, "stat_modes_label")),
        (0, t(S, "stat_copied_label")),
    ]
    lis = "\n".join(f"          <li><b>{n}</b><span>{label}</span></li>" for n, label in items)
    return f'        <ul class="stats">\n{lis}\n        </ul>'


# ------------------------------------------------------------------- sitemap

def build_sitemap(ops: list) -> str:
    """
    Una entrada por página, con sus alternativas de idioma declaradas.

    lastmod de una ficha = verificado_el, que es una fecha real y humana. No se
    inventa una fecha de hoy para aparentar frescura: eso es justo lo que el
    proyecto existe para no hacer.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]

    def entry(paths: dict[str, str], lastmod: str | None) -> None:
        for lang, path in paths.items():
            lines.append("  <url>")
            lines.append(f"    <loc>{BASE_URL}{path}</loc>")
            for alt_lang, alt_path in paths.items():
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="{alt_lang}" '
                    f'href="{BASE_URL}{alt_path}"/>'
                )
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" '
                f'href="{BASE_URL}{paths["en"]}"/>'
            )
            if lastmod:
                lines.append(f"    <lastmod>{lastmod}</lastmod>")
            lines.append("  </url>")

    entry({lang: PAGES[lang][1] for lang in PAGES}, None)
    for op in ops:
        entry({lang: op_path(op, lang) for lang in PAGES}, op.get("verified_on"))
    for key, cfg in LEGAL_PAGES.items():
        entry({lang: legal_path(key, lang) for lang in PAGES}, cfg["updated"])

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- main

def main() -> None:
    for required in (TEMPLATE, TEMPLATE_OP, TEMPLATE_PAGE, STYLE):
        if not required.exists():
            sys.exit(f"ERROR: falta {required}")
    if not DATASET.exists():
        sys.exit(f"ERROR: falta {DATASET}. Correr convert.py primero.")

    template = TEMPLATE.read_text(encoding="utf-8")
    template_op = TEMPLATE_OP.read_text(encoding="utf-8")
    template_page = TEMPLATE_PAGE.read_text(encoding="utf-8")
    css = STYLE.read_text(encoding="utf-8").rstrip("\n")

    dicts = {lang: load_strings(lang) for lang in PAGES}
    check_key_parity(dicts)
    check_placeholders(dicts)
    unused = check_template_keys(template, dicts["en"], COMPUTED_HOME, "template.html")
    check_template_keys(template_op, dicts["en"], COMPUTED_OP, "template_operator.html")
    check_template_keys(template_page, dicts["en"], COMPUTED_PAGE, "template_page.html")

    with DATASET.open(encoding="utf-8") as fh:
        data = json.load(fh)
    all_ops = data["operators"]

    published, held = [], []
    for op in all_ops:
        ok, why = is_publishable(op)
        (published if ok else held).append(op if ok else (op, why))

    written = []

    # ---------- fichas ----------
    for op in published:
        for lang in PAGES:
            S = dicts[lang]
            kind = op["type"]
            values = {
                "STYLE": css,
                "LANG": lang,
                "CANONICAL": BASE_URL + op_path(op, lang),
                "HREF_EN": BASE_URL + op_path(op, "en"),
                "HREF_ES": BASE_URL + op_path(op, "es"),
                "NAV_EN_PATH": op_path(op, "en"),
                "NAV_ES_PATH": op_path(op, "es"),
                "NAV_EN_CUR": ' aria-current="page"' if lang == "en" else "",
                "NAV_ES_CUR": ' aria-current="page"' if lang == "es" else "",
                "DOC_TITLE": t(S, f"fiche_title_{kind}", name=esc(op["name"])),
                "META_DESCRIPTION": t(
                    S,
                    "fiche_meta_dim" if op["limit_type"] == "dimensional" else "fiche_meta_rule",
                    name=esc(op["name"]),
                ),
                "H1": t(S, f"fiche_h1_{kind}", name=esc(op["name"])),
                "STANDFIRST": t(
                    S,
                    "fiche_standfirst_dim" if op["limit_type"] == "dimensional"
                    else "fiche_standfirst_rule",
                    name=esc(op["name"]),
                ),
                "CRUMBS": block_crumbs(op, lang, S),
                "PROVENANCE": block_provenance(op, S),
                "ALLOWANCES": block_allowances(op, S),
                "RULE": block_rule(op, lang, S),
                "WHEELS": block_wheels(op, S),
                "CAVEATS": block_caveats(op, S),
                "CHECKER_HREF": PAGES[lang][1],
                "FICHE_STAMP": t(
                    S, "fiche_stamp",
                    version=esc(data["schema_version"]), date=esc(data["generated_on"]),
                ),
                "FOOTER_LINKS": block_footer_links(lang, S),
            }
            values.update(S)
            out = op_outfile(op, lang)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(template_op, values), encoding="utf-8")
            written.append(out)

    # ---------- home ----------
    for lang, (subdir, canonical_path) in PAGES.items():
        S = dicts[lang]
        values = dict(S)
        values["STYLE"] = css
        values["LANG"] = lang
        values["CANONICAL"] = BASE_URL + canonical_path
        values["NAV_EN_CUR"] = ' aria-current="page"' if lang == "en" else ""
        values["NAV_ES_CUR"] = ' aria-current="page"' if lang == "es" else ""
        values["OPERATOR_INDEX"] = block_operator_index(published, lang, S)
        values["FOOTER_LINKS"] = block_footer_links(lang, S)
        values["HERO_STATS"] = block_hero_stats(published, S)
        # El diccionario entero viaja al JS. ensure_ascii=False para que los
        # acentos y el × salgan como caracteres reales en un archivo UTF-8.
        values["STRINGS_JSON"] = json.dumps(S, ensure_ascii=False, indent=2)
        # Rutas de las fichas para los enlaces "Todas las reglas de…" de cada
        # resultado. Salen de TYPE_SEGMENT, la misma tabla que genera las
        # fichas: si una cambia, la otra la sigue sola.
        values["FICHE_PATHS"] = json.dumps(
            {kind: f"/{seg[lang]}/" for kind, seg in TYPE_SEGMENT.items()})

        out_dir = OUT_DIR / subdir if subdir else OUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        out_file.write_text(render(template, values), encoding="utf-8")
        written.append(out_file)

    # ---------- páginas de texto ----------
    for key, cfg in LEGAL_PAGES.items():
        for lang in PAGES:
            S = dicts[lang]
            values = dict(S)
            values.update({
                "STYLE": css,
                "LANG": lang,
                "CANONICAL": BASE_URL + legal_path(key, lang),
                "HREF_EN": BASE_URL + legal_path(key, "en"),
                "HREF_ES": BASE_URL + legal_path(key, "es"),
                "NAV_EN_PATH": legal_path(key, "en"),
                "NAV_ES_PATH": legal_path(key, "es"),
                "NAV_EN_CUR": ' aria-current="page"' if lang == "en" else "",
                "NAV_ES_CUR": ' aria-current="page"' if lang == "es" else "",
                "DOC_TITLE": t(S, f"{key}_title"),
                "META_DESCRIPTION": t(S, f"{key}_meta"),
                "H1": t(S, f"{key}_h1"),
                "STANDFIRST": t(S, f"{key}_standfirst"),
                "CRUMB_SELF": t(S, cfg["nav"]),
                "CONTENT": load_fragment(key, lang),
                "CHECKER_HREF": PAGES[lang][1],
                "PAGE_UPDATED": t(S, "legal_updated", date=cfg["updated"]),
                "FOOTER_LINKS": block_footer_links(lang, S, current=key),
            })
            out = legal_outfile(key, lang)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(template_page, values), encoding="utf-8")
            written.append(out)

    # ---------- sitemap ----------
    sitemap = OUT_DIR / "sitemap.xml"
    sitemap.write_text(build_sitemap(published), encoding="utf-8")
    written.append(sitemap)

    # ---------- informe ----------
    for path in written:
        rel = path.relative_to(ROOT)
        print(f"  {rel}  ({path.stat().st_size:,} bytes)")

    n_urls = (len(published) + 1 + len(LEGAL_PAGES)) * len(PAGES)
    print(
        f"\nOK. {len(dicts['en'])} textos por idioma, {len(dicts)} idiomas, "
        f"{len(published)} de {len(all_ops)} operadores con ficha, "
        f"{len(LEGAL_PAGES)} páginas de texto, {n_urls} URLs en el sitemap."
    )
    if held:
        print("\nOperadores SIN ficha, por no alcanzar el umbral de publicación:")
        for op, why in held:
            print(f"  {op['id']}: {why}")
    if unused:
        print(f"\nClaves que la home no usa directamente (las usa el JS): {len(unused)}")


if __name__ == "__main__":
    main()
