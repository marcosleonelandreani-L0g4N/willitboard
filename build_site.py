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

# Archivos que se copian tal cual a public/ (favicon, imágenes para compartir y
# las viejas tipografías, que desde el 10/10/2026 ya no usa ninguna página: el
# texto sale con la letra del aparato). Todo se sirve desde el propio dominio:
# el sitio no carga nada de terceros desde el 26/09/2026.
STATIC_DIR = SITE_DIR / "static"
BRAND_DIR = SITE_DIR / "brand"
PARTIALS_DIR = SITE_DIR / "partials"
VERDICT_JS = PARTIALS_DIR / "verdict.js"  # cuenta de "¿entra?" compartida home/ficha
GUIDES_DIR = SITE_DIR / "guides"

# Logo en uso: sitio/brand/mark-<letra>.svg. Hay cuatro propuestas (a, b, c, d);
# cambiar de logo es cambiar esta letra y volver a correr el script.
BRAND_MARK = "b"

# AdSense, paso 1 de 2: verificar el sitio. Vacío = nada de AdSense (hoy).
# Con el ID de editor ("pub-" y 16 dígitos, figura en AdSense > Cuenta) el build
# agrega a todas las páginas <meta name="google-adsense-account"> y escribe
# public/ads.txt. Ninguna de las dos cosas carga nada de Google ni instala
# cookies: solo sirven para que Google compruebe que el sitio es de Marcos y
# para pedir la revisión. El código que MUESTRA anuncios (paso 2) no está acá a
# propósito: entra el día de la aprobación junto con privacidad, cookies y
# divulgación reescritas, porque hoy esas tres páginas prometen "sin cookies y
# sin publicidad", y la de cookies promete cambiar ANTES de la primera cookie.
ADSENSE_PUB_ID = "pub-5571641673142734"
# Identificador fijo de Google en ads.txt, tal como lo da la guía oficial:
# https://support.google.com/adsense/answer/12171612
ADS_TXT_GOOGLE_ID = "f08c47fec0942fa0"

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
        "updated": "2026-10-10",
    },
    "cookies": {
        "slug": {"en": "cookies", "es": "es/cookies"},
        "nav": "nav_cookies",
        "updated": "2026-10-10",
    },
    "disclosure": {
        "slug": {"en": "disclosure", "es": "es/divulgacion"},
        "nav": "nav_disclosure",
        "updated": "2026-09-20",
    },
}

# Guías y páginas propias (26/09/2026). Mismo mecanismo que las legales: un
# fragmento HTML por idioma en sitio/guides/, salvo "sizes", que se GENERA
# desde el dataset en cada build (así la tabla nunca se despega de los datos).
# `updated` = fecha en que se editó el TEXTO, a mano. Para "sizes" no hay fecha
# manual: su lastmod es la última verificación humana del dataset.
GUIDE_PAGES = {
    "measure": {
        "slug": {"en": "how-to-measure-luggage", "es": "es/como-medir-una-maleta"},
        "nav": "nav_guide_measure",
        "updated": "2026-09-26",
    },
    "sizes": {
        "slug": {"en": "cabin-bag-sizes", "es": "es/medidas-equipaje-de-mano"},
        "nav": "nav_guide_sizes",
        "updated": None,
    },
    "about": {
        "slug": {"en": "about", "es": "es/sobre-willitboard"},
        "nav": "nav_about",
        "updated": "2026-10-01",
    },
    # Contacto (05/10/2026). Solo correo: el sitio es estático y un formulario
    # exigiría un servicio de terceros que reciba los datos.
    "contact": {
        "slug": {"en": "contact", "es": "es/contacto"},
        "nav": "nav_contact",
        "updated": "2026-10-05",
    },
}

# Página 404 (06/10/2026). Cloudflare la sirve con estado 404 para cualquier URL
# que no exista, gracias a "not_found_handling": "404-page" en wrangler.jsonc, y
# elige el 404.html MÁS CERCANO: una URL rota bajo /es/ recibe la versión en
# español. No va al sitemap, lleva noindex y no tiene canonical ni hreflang,
# porque no es una página que se pueda enlazar: aparece en direcciones ajenas.
NOT_FOUND_PAGES = {"en": "404.html", "es": "es/404.html"}

# marcadores que calcula el script, no el diccionario
COMPUTED_HOME = {"LANG", "CANONICAL", "NAV_EN_CUR", "NAV_ES_CUR", "STRINGS_JSON", "FICHE_PATHS",
                 "STYLE", "OPERATOR_INDEX", "FOOTER_LINKS", "HERO_STATS", "HEAD_EXTRA", "BRAND",
                 "SLIDE_1_LABEL", "SLIDE_2_LABEL", "SLIDE_3_LABEL", "SLIDE_4_LABEL",
                 "SLIDE_1_GO", "SLIDE_2_GO", "SLIDE_3_GO", "SLIDE_4_GO",
                 "MEASURE_ART", "GUIDE_MEASURE_HREF", "CMP_INTRO",
                 "SCENE_MEASURE", "SCENE_COMPARE", "SCENE_TRUST", "SCENE_SHARE",
                 "TOTOP", "GUIDE_LINKS", "BANNED_BLOCK", "VERDICT_JS",
                 "MEASURE_THUMB", "NOGO_JS"}
COMPUTED_OP = {"LANG", "CANONICAL", "STYLE", "DOC_TITLE", "META_DESCRIPTION", "HEAD_EXTRA", "BRAND",
               "HREF_EN", "HREF_ES", "NAV_EN_PATH", "NAV_ES_PATH",
               "NAV_EN_CUR", "NAV_ES_CUR", "CRUMBS", "H1", "STANDFIRST",
               "PROVENANCE", "ALLOWANCES", "RULE", "WHEELS", "CAVEATS",
               "CHECKER_HREF", "FICHE_STAMP", "FOOTER_LINKS", "TOTOP",
               "KG_TILE", "BANNED_TILE", "TRY", "COMPARE", "COMPARE_HREF", "HEAD_MOD",
               "FICHE_JS", "OP_JSON", "FICHE_STRINGS", "VERDICT_JS", "NOGO_JS"}
COMPUTED_PAGE = {"TOTOP", "LANG", "CANONICAL", "STYLE", "DOC_TITLE", "META_DESCRIPTION", "HEAD_EXTRA", "BRAND",
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
    """
    Fuente oficial y fecha humana, arriba de todo y a la vista (11/10/2026:
    van dentro de la tarjeta de cabecera). El primer <a> de .provenance es
    SIEMPRE la fuente: test_fichas lo lee así.
    """
    when = esc(op["verified_on"])
    check = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7" fill="none" '
             'stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return (
        f'        <a class="prov__src" href="{esc(op["source_url"])}" target="_blank" '
        f'rel="noopener nofollow">{t(S, "prov_source")} ↗</a>\n'
        f'        <span class="prov__ok">{check}{t(S, "prov_checked")} <time datetime="{when}">{when}</time></span>\n'
        f'        <span class="prov__why">{t(S, "prov_why")}</span>'
    )


# Dibujos de las tarjetas de franquicia (11/10/2026). Trazos propios, sin
# marcas: un bolso blando para el artículo personal, una maleta con ruedas
# para la de cabina. Decorativos: aria-hidden.
_ALLOW_ART = {
    "personal_item": (
        '<svg viewBox="0 0 64 64" aria-hidden="true">'
        '<path d="M22 22v-4a10 10 0 0 1 20 0v4" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/>'
        '<rect x="11" y="22" width="42" height="32" rx="9" fill="var(--art-fill)" stroke="currentColor" stroke-width="3.2"/>'
        '<path d="M11 33h42" stroke="currentColor" stroke-width="3.2"/>'
        '<rect x="27" y="30" width="10" height="7" rx="2.5" fill="var(--surface)" stroke="currentColor" stroke-width="2.6"/>'
        '</svg>'
    ),
    "cabin_bag": (
        '<svg viewBox="0 0 64 64" aria-hidden="true">'
        '<path d="M25 14V6h14v8" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<rect x="15" y="14" width="34" height="38" rx="8" fill="var(--art-fill)" stroke="currentColor" stroke-width="3.2"/>'
        '<path d="M26 22v22M38 22v22" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"/>'
        '<circle cx="23" cy="57" r="3.6" fill="currentColor"/><circle cx="41" cy="57" r="3.6" fill="currentColor"/>'
        '</svg>'
    ),
}


def one_allowance(op, key: str, label_key: str, S: dict) -> str:
    allow = op.get(key)
    if not isinstance(allow, dict):
        return ""
    included = allow.get("included")
    if included is True:
        status_cls, status_txt, tone = "status--free", t(S, "status_free"), "free"
    elif included is False:
        status_cls, status_txt, tone = "status--paid", t(S, "status_paid"), "paid"
    else:
        status_cls, status_txt, tone = "status--none", t(S, "status_unknown"), "none"

    dims = triple(allow.get("max_cm"))
    if dims:
        kg = allow.get("max_kg")
        shared = op.get("combined_max_kg")
        # Peso por bulto si existe; si el operador solo publica un peso para los
        # dos bultos juntos, se dice así. Nunca se reparte entre los bultos.
        if kg is not None:
            sub = t(S, "allow_kg", kg=kg)
        elif shared is not None:
            sub = t(S, "allow_kg_shared", kg=shared)
        else:
            sub = t(S, "allow_no_kg")
        figure = (
            f'          <p class="allow__dims">{esc(" × ".join(str(d) for d in dims))} cm'
            f"<small>{sub}</small></p>"
        )
    else:
        figure = f'          <p class="allow__none">{t(S, "allow_not_published", name=esc(op["name"]))}</p>'

    addon = allow.get("requires_addon")
    addon_html = (
        f'\n          <p class="allow__addon">{t(S, "allow_addon", addon=esc(addon))}</p>'
        if included is False and addon else ""
    )

    return (
        f'      <div class="allow glass allow--{tone}">\n'
        f'        <span class="allow__art">{_ALLOW_ART[key]}</span>\n'
        f'        <div class="allow__body">\n'
        f'          <p class="allow__label">{t(S, label_key)}</p>\n'
        f"{figure}\n"
        f'          <span class="status {status_cls}">{status_txt}</span>{addon_html}\n'
        f"        </div>\n"
        f"      </div>"
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
        '  <section class="allows2" aria-labelledby="allowances-h">\n'
        f'    <h2 id="allowances-h" class="eyebrow">{t(S, "fiche_allowances_h")}</h2>\n'
        f"{fare_html}"
        f'    <div class="allows">\n{inner}\n    </div>\n'
        "  </section>"
    )


def fiche_kg(op):
    """
    (valor, compartido) para la tarjeta grande de peso, o None.
    Solo cifras publicadas: el peso propio de la maleta de cabina, o si el
    operador solo publica un total para los dos bultos, ese total rotulado
    como total. Nunca se calcula ni se reparte nada.
    """
    if op.get("limit_type") != "dimensional":
        return None
    cabin = op.get("cabin_bag") or {}
    if not triple(cabin.get("max_cm")):
        return None
    if cabin.get("max_kg") is not None:
        return cabin["max_kg"], False
    if op.get("combined_max_kg") is not None:
        return op["combined_max_kg"], True
    return None


def fmt_num(v) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def block_kg_tile(op, S: dict, cls: str) -> str:
    k = fiche_kg(op)
    if not k:
        return ""
    kg, shared = k
    label = t(S, "fiche_kg_shared" if shared else "fiche_kg_cabin")
    return (
        f'  <section class="glass tile--kg {cls}" aria-label="{esc(fmt_num(kg))} kg, {esc(label)}">\n'
        f'    <p class="kg__n" aria-hidden="true">{esc(fmt_num(kg))}<small> kg</small></p>\n'
        f'    <p class="kg__l" aria-hidden="true">{label}</p>\n'
        "  </section>"
    )


def fiche_has_banned(op) -> bool:
    """
    Las fichas de prohibidos (UE) van en la ficha de una aerolínea solo si:
    hay fecha humana (BANNED_VERIFIED_ON), es un avión y su región es Europa.
    En Latinoamérica las reglas son otras (Chile, Colombia y México no usan
    los 100 ml de la UE), así que ahí no se muestran.
    """
    return bool(BANNED_VERIFIED_ON.strip()) and op.get("type") == "air" and op.get("region") == "EU"


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


def block_wheels(op, S: dict, cls: str = "") -> str:
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
    # maleta con el asa extendida y las ruedas marcadas: lo que dice la tarjeta
    art = ('<svg viewBox="0 0 48 48" aria-hidden="true">'
           '<path d="M19 13V4h10v9" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
           '<rect x="12" y="13" width="24" height="25" rx="6" fill="none" stroke="currentColor" stroke-width="2.6" opacity=".45"/>'
           '<circle cx="18" cy="42.5" r="3.6" fill="currentColor"/><circle cx="30" cy="42.5" r="3.6" fill="currentColor"/>'
           '</svg>')
    return (
        f'  <section class="glass tile--wheels {cls}" aria-labelledby="wheels-h">\n'
        f'    <span class="wheels__art">{art}</span>\n'
        f'    <h2 id="wheels-h">{t(S, "fiche_wheels_h")}</h2>\n'
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
    guide_links = "\n".join(
        f'        <li><a href="{guide_path(k, lang)}">{t(S, cfg["nav"])}</a></li>'
        for k, cfg in GUIDE_PAGES.items() if k not in ("about", "contact")
    )
    groups.append(
        f'    <div class="index__group">\n'
        f'      <h3>{t(S, "guides_h2")}</h3>\n'
        f'      <ul class="index__links index__links--guides">\n{guide_links}\n      </ul>\n'
        f"    </div>"
    )
    return (
        '  <section class="prose index" aria-labelledby="index-h">\n'
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
    guides = []
    for key, cfg in GUIDE_PAGES.items():
        cur = ' aria-current="page"' if key == current else ""
        guides.append(
            f'      <li><a href="{guide_path(key, lang)}"{cur}>{t(S, cfg["nav"])}</a></li>'
        )
    items = []
    for key, cfg in LEGAL_PAGES.items():
        cur = ' aria-current="page"' if key == current else ""
        items.append(
            f'      <li><a href="{legal_path(key, lang)}"{cur}>{t(S, cfg["nav"])}</a></li>'
        )
    return (
        f'    <ul class="footlinks footlinks--guides" aria-label="{t(S, "footer_guides_label")}">\n'
        + "\n".join(guides)
        + "\n    </ul>\n"
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


# ------------------------------------------------- objetos prohibidos (home)

# Fichas visuales de "qué no se puede llevar en cabina" (10/10/2026).
# Cada ficha resume UNA frase de la página oficial de la UE (Your Europe),
# vuelos desde aeropuertos de la UE:
#   https://europa.eu/youreurope/citizens/travel/carry/luggage-restrictions/index_en.htm
# Son condiciones de equipaje, así que siguen la regla del dataset: se
# publican SOLO cuando Marcos abrió la fuente, comparó cada ficha y puso la
# fecha acá (AAAA-MM-DD). Vacío = el sitio muestra solo los enlaces oficiales.
# Nunca la completa un asistente.
# 2026-10-10: Marcos pegó el texto de la versión en español (index_es.htm) y
# confirmó las 6 fichas. Se enlaza la versión del idioma de cada página.
BANNED_VERIFIED_ON = "2026-10-10"
BANNED_SOURCE_EN = "https://europa.eu/youreurope/citizens/travel/carry/luggage-restrictions/index_en.htm"
BANNED_SOURCE_UK = "https://www.gov.uk/hand-luggage-restrictions"
# Latinoamérica (10/10/2026): solo enlaces, con una nota que dice en qué se
# aparta de la UE. Sus reglas NO son las de la UE, así que nunca se les
# aplican las fichas. Las tres páginas las abrió Marcos el 2026-10-10 y mandó
# capturas: Chile (líquidos permitidos; 100 ml solo en vuelos a EE. UU.),
# Colombia (100 ml figura solo para vuelos internacionales; publicada
# 15/11/2024, modificada 16/04/2025) y México (aeropuertos GAP: 100 ml).
BANNED_SOURCE_CL = "https://www.dgac.gob.cl/pasajeros/articulos-prohibidos"
BANNED_SOURCE_CO = "https://www.aerocivil.gov.co/autoridad_aeronautica/publicaciones/3673/articulos-prohibidos-en-equipajes/"
BANNED_SOURCE_MX = "https://www.aeropuertosgap.com.mx/es/informacion-util-para-viajar/equipaje.html"

# (clave de texto, estado, ícono). Estados: no = no va en cabina,
# never = ni en cabina ni en bodega, limit = va con límites,
# ok = excepción permitida.
BANNED_ITEMS = [
    ("liquids", "no", "bottle"),       # envases de más de 100 ml: a la bodega
    ("sharp", "no", "scissors"),
    ("weapons", "no", "gun"),
    ("flammable", "never", "flame"),   # ni en cabina ni en bodega
    ("dutyfree", "limit", "bag"),
    ("meds", "ok", "pill"),
]

_BANNED_ICONS = {
    "bottle": '<path d="M10 3h4v3.2c0 .6.3 1.1.8 1.5 1.4 1 2.2 2.6 2.2 4.3V19a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-7c0-1.7.8-3.3 2.2-4.3.5-.4.8-.9.8-1.5z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M7.2 13.5h9.6" stroke="currentColor" stroke-width="1.9"/>',
    "pill": '<rect x="3.2" y="8.6" width="17.6" height="6.8" rx="3.4" transform="rotate(-35 12 12)" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M9.6 8.6l4.8 6.8" stroke="currentColor" stroke-width="1.9"/>',
    "bag": '<path d="M5.5 8h13l-1 12.2a1 1 0 0 1-1 .8h-9a1 1 0 0 1-1-.8z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M9 10V6.8a3 3 0 0 1 6 0V10" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
    "scissors": '<circle cx="6.5" cy="17.5" r="2.8" fill="none" stroke="currentColor" stroke-width="1.9"/><circle cx="17.5" cy="17.5" r="2.8" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M8.5 15.5L18 3.5M15.5 15.5L6 3.5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
    "gun": '<path d="M3 8h16.5a1.5 1.5 0 0 1 1.5 1.5V11h-7.5l-1 2.2a1 1 0 0 1-.9.6H10l-1.2 5.4a1 1 0 0 1-1 .8H5.2a1 1 0 0 1-1-1.2L5.4 13H4a1 1 0 0 1-1-1z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>',
    "flame": '<path d="M12 21c-3.9 0-6.5-2.6-6.5-6.1 0-3.3 2.3-5.2 3.6-7.5.6 1.6 1.4 2.5 2.4 3 0-3.1 1.2-5.6 3.5-7.4.2 2.8 1.4 4.6 2.6 6.2 1 1.4 1.9 2.8 1.9 5.1 0 4.3-3.3 6.7-7.5 6.7z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>',
}
_BANNED_BADGES = {
    "never": "",
    "no": '<circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M8 8l8 8M16 8l-8 8" stroke="#fff" stroke-width="2.8" stroke-linecap="round"/>',
    "limit": '<path d="M12 2.5l10 17.5H2z" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M12 9v5" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><circle cx="12" cy="17" r="1.5" fill="#fff"/>',
    "ok": '<circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M7.5 12.3l3 3 6-6.3" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>',
}


def banned_tiles(S: dict) -> list:
    """Las seis fichas con ícono. Las usan la home y la ficha de aerolínea."""
    e = html.escape
    tiles = []
    for key, state, icon in BANNED_ITEMS:
        tiles.append(
            f'      <li class="nogo__tile nogo__tile--{state}">\n'
            f'        <span class="nogo__art" aria-hidden="true"><svg class="nogo__ico" viewBox="0 0 24 24">{_BANNED_ICONS[icon]}</svg>'
            f'<svg class="nogo__badge" viewBox="0 0 24 24">{_BANNED_BADGES[state]}</svg></span>\n'
            f'        <span class="nogo__txt"><span class="nogo__state">{e(t(S, "nogo_state_" + state))}</span>\n'
            f'        <b class="nogo__t">{e(t(S, "nogo_" + key + "_t"))}</b>\n'
            f'        <span class="nogo__d">{e(t(S, "nogo_" + key + "_d"))}</span></span>\n'
            '      </li>'
        )
    return tiles


_CHEV_L = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 6l-6 6 6 6" fill="none" stroke="currentColor" '
           'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
_CHEV_R = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 6l6 6-6 6" fill="none" stroke="currentColor" '
           'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def nogo_carousel(S: dict, lang: str, idp: str, more_href, heading: str = "h2", stamp_html: str = None) -> str:
    """
    Banner chico de prohibidos con flechas (11/10/2026). Se desliza con el
    dedo (scroll-snap); las flechas avanzan una "página" (2 fichas en
    computadora, 1 en el teléfono). Sin JavaScript sigue siendo una lista
    que se desliza. Solo se arma con fecha humana: lo decide quien lo llama.
    """
    e = html.escape
    eu_url = t(S, "banned_eu_url")
    stamp = stamp_html or (f'<a href="{e(eu_url)}" target="_blank" rel="noopener nofollow">{e(t(S, "nogo_source"))}</a> · '
                           f'{e(t(S, "nogo_stamp", date=BANNED_VERIFIED_ON.strip()))}')
    more = f' <a href="{e(more_href)}">{e(t(S, "nogo_more"))}</a>' if more_href else ""
    return (
        f'    <div class="nogo-c__head">\n'
        f'      <{heading} class="nogo-c__h" id="{idp}-h">{e(t(S, "banned_h"))}</{heading}>\n'
        f'      <p class="nogo__src">{e(t(S, "nogo_scope"))} {stamp}</p>\n'
        '    </div>\n'
        f'    <ul class="nogo-c__track" id="{idp}-track" tabindex="0" aria-label="{e(t(S, "banned_h"))}">\n'
        + "\n".join(banned_tiles(S)) + '\n    </ul>\n'
        '    <div class="nogo-c__nav">\n'
        f'      <button type="button" class="nogo-c__btn" data-nogo="{idp}" data-dir="-1" aria-label="{e(t(S, "nogo_prev"))}">{_CHEV_L}</button>\n'
        f'      <span class="nogo-c__dots" id="{idp}-dots" data-label="{e(t(S, "nogo_page"))}"></span>\n'
        f'      <button type="button" class="nogo-c__btn" data-nogo="{idp}" data-dir="1" aria-label="{e(t(S, "nogo_next"))}">{_CHEV_R}</button>\n'
        '    </div>\n'
        f'    <p class="nogo__note">{e(t(S, "nogo_note"))}{more}</p>\n'
    )


def block_banned_tile(op, lang: str, S: dict) -> str:
    """
    18/10/2026: en la ficha va UNA línea con enlace a la lista de la home, no
    el carrusel completo. El carrusel era idéntico en las 16 fichas europeas
    (contenido repetido entre páginas, uno de los motivos posibles del rechazo
    de AdSense por "low value content"). La lista completa sigue en la home.
    """
    if not fiche_has_banned(op):
        return ""
    more = PAGES[lang][1] + "#banned"
    return (
        '  <section class="glass tile--banline" aria-label="' + esc(t(S, "banned_h")) + '">\n'
        f'    <p>{t(S, "fiche_banned_line")} <a href="{more}">{t(S, "fiche_banned_link")} →</a></p>\n'
        '  </section>'
    )


def block_try(op, lang: str, S: dict) -> str:
    """
    "¿Entra tu maleta en X?" dentro de la ficha. La cuenta es la MISMA que la
    de la home: partials/verdict.js se inyecta tal cual en las dos páginas.
    Valores iniciales = los de la home.
    """
    if op.get("limit_type") != "dimensional":
        return ""
    up = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 14.5l6-6 6 6" fill="none" stroke="currentColor" '
          'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    down = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" '
            'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    fields = []
    for fid, lab, val, unit in (("try-a", "f_length", "50", "cm"), ("try-b", "f_width", "38", "cm"),
                                ("try-c", "f_height", "22", "cm"), ("try-w", "f_weight", "9", "kg")):
        name = t(S, lab)
        fields.append(
            '        <div class="field">\n'
            f'          <label for="{fid}">{name}</label>\n'
            '          <div class="field__row">\n'
            f'            <input type="number" id="{fid}" inputmode="decimal" min="0" step="0.1" value="{val}">\n'
            f'            <span class="field__unit">{unit}</span>\n'
            '            <div class="stepper">\n'
            f'              <button type="button" class="nudge" data-nudge="{fid}" data-dir="1" aria-label="{t(S, "a11y_more")} {name}">{up}</button>\n'
            f'              <button type="button" class="nudge" data-nudge="{fid}" data-dir="-1" aria-label="{t(S, "a11y_less")} {name}">{down}</button>\n'
            '            </div>\n'
            '          </div>\n'
            '        </div>'
        )
    home = PAGES[lang][1]
    return (
        '  <section class="glass tile--try tryit" aria-labelledby="try-h">\n'
        f'    <h2 id="try-h">{t(S, "fiche_try_h", name=esc(op["name"]))}</h2>\n'
        '    <div class="fields">\n' + "\n".join(fields) + '\n    </div>\n'
        '    <div class="tryit__out" id="try-out" aria-live="polite">\n'
        f'      <p class="tryit__v" id="try-v">{t(S, "fiche_try_empty")}</p>\n'
        '      <p class="tryit__d" id="try-d"></p>\n'
        '    </div>\n'
        f'    <p class="tryit__foot"><span>{t(S, "fiche_try_same", name=esc(op["name"]))}</span> '
        f'<a id="try-all" href="{home}?l=50&amp;w=38&amp;h=22&amp;kg=9">{t(S, "fiche_try_all")} →</a></p>\n'
        '  </section>'
    )


# ------------------------------------- comparación con las otras aerolíneas
#
# Contenido propio de cada ficha (pedido de AdSense, 18/10/2026: "low value
# content"). Todo sale de operators.json en el momento del build: ninguna
# cifra se escribe a mano. Se comparan SOLO medidas publicadas, ordenadas de
# mayor a menor como en verdict.js (la maleta puede girar en el medidor). El
# peso y la tolerancia de ruedas quedan afuera de los hechos y se dice.

CMP_PRESETS = (  # las mismas tres maletas de ejemplo que la home (template.html)
    ("preset_backpack", (40, 25, 20), 6),
    ("preset_trolley", (55, 40, 23), 9),
    ("preset_big", (60, 42, 26), 12),
)
CMP_DEPTH_MAX_GROUP = 3  # "la menos/más profunda" solo si la comparten 3 o menos


def _sorted3(max_cm):
    v = triple(max_cm)
    return sorted(v, reverse=True) if v else None


def _fits(bag, limit) -> bool:
    return all(b <= l for b, l in zip(sorted(bag, reverse=True), limit))


def cmp_airlines(ops: list) -> list:
    """Aerolíneas con las dos ternas completas: las únicas comparables."""
    return [o for o in ops
            if o.get("type") == "air" and o.get("limit_type") == "dimensional"
            and _sorted3((o.get("personal_item") or {}).get("max_cm"))
            and _sorted3((o.get("cabin_bag") or {}).get("max_cm"))]


def _dims_txt(max_cm) -> str:
    return " × ".join(fmt_num(x) for x in triple(max_cm)) + " cm"


def _chips(others: list, lang: str) -> str:
    return ('<ul class="cmpx__chips">'
            + "".join(f'<li><a href="{op_path(o, lang)}">{esc(o["name"])}</a></li>' for o in others)
            + "</ul>")


def _fit_fact(op, peers, key: str, prefix: str, lang: str, S: dict) -> str:
    mine = (op[key] or {}).get("max_cm")
    bag = _sorted3(mine)
    no = [o for o in peers if not _fits(bag, _sorted3(o[key]["max_cm"]))]
    m, k = len(peers), len(peers) - len(no)
    variant = "all" if not no else ("none" if k == 0 else "some")
    title = t(S, f"{prefix}_{variant}", name=esc(op["name"]), k=k, m=m)
    body = f'<p>{t(S, "cmp_dims", dims=esc(_dims_txt(mine)))}'
    if no:
        body += f' {t(S, "cmp_toobig")}</p>{_chips(no, lang)}'
    else:
        body += "</p>"
    return f'      <li class="cmpx__fact"><b class="cmpx__t">{title}</b>{body}</li>\n'


def _depth_fact(op, airlines, lang: str, S: dict) -> str:
    depth = lambda o: _sorted3(o["cabin_bag"]["max_cm"])[2]
    d = depth(op)
    others = [o for o in airlines if o is not op]
    if not others:
        return ""
    lows, highs = min(depth(o) for o in airlines), max(depth(o) for o in airlines)
    if lows == highs:
        return ""
    if d == lows:
        title_key = "cmp_shallow"
    elif d == highs:
        title_key = "cmp_deep"
    else:
        return ""
    same = [o for o in others if depth(o) == d]
    if len(same) + 1 > CMP_DEPTH_MAX_GROUP:
        return ""
    rest = [depth(o) for o in others if depth(o) != d]
    lo, hi = min(rest), max(rest)
    rng = f"{fmt_num(lo)} cm" if lo == hi else t(S, "cmp_range", lo=fmt_num(lo), hi=fmt_num(hi))
    txt = t(S, "cmp_depth_d", name=esc(op["name"]), d=fmt_num(d), range=rng)
    extra = f' {t(S, "cmp_same")}</p>{_chips(same, lang)}' if same else "</p>"
    return f'      <li class="cmpx__fact"><b class="cmpx__t">{t(S, title_key)}</b><p>{txt}{extra}</li>\n'


def _incl_fact(op, airlines, lang: str, S: dict) -> str:
    incl = [o for o in airlines if (o["cabin_bag"] or {}).get("included") is True]
    if not incl:
        return ""
    mine = op in incl
    others = [o for o in incl if o is not op]
    title = t(S, "cmp_incl_t", k=len(incl), n=len(airlines))
    lead = t(S, "cmp_incl_yes" if mine else "cmp_incl_no", name=esc(op["name"]))
    chips = _chips(others, lang) if others else ""
    return f'      <li class="cmpx__fact"><b class="cmpx__t">{title}</b><p>{lead}</p>{chips}</li>\n'


def _bag_verdict(op, bag, S: dict):
    """(clase, texto) para una maleta de ejemplo en ESTA aerolínea, solo por medidas."""
    pers, cab = op["personal_item"], op["cabin_bag"]
    if _fits(bag, _sorted3(pers["max_cm"])) and pers.get("included") is True:
        return "status--free", t(S, "cmp_v_personal")
    lim = _sorted3(cab["max_cm"])
    if _fits(bag, lim):
        return (("status--free", t(S, "cmp_v_cabin_incl")) if cab.get("included") is True
                else ("status--paid", t(S, "cmp_v_cabin_paid")))
    b = sorted(bag, reverse=True)
    by = max(round(x - l, 1) for x, l in zip(b, lim))
    w = op.get("wheels_handles") or {}
    tol = w.get("tolerance_cm") if w.get("included_in_measurement") is False else None
    if tol is not None and by <= tol:
        return "status--paid", t(S, "cmp_v_maybe")
    return "status--over", t(S, "cmp_v_over", by=fmt_num(by))


def block_compare(op, ops: list, lang: str, S: dict) -> str:
    airlines = cmp_airlines(ops)
    if op not in airlines or len(airlines) < 2:
        return ""
    peers = [o for o in airlines if o is not op]
    n = len(airlines)
    facts = (_depth_fact(op, airlines, lang, S)
             + _fit_fact(op, peers, "cabin_bag", "cmp_cabin", lang, S)
             + _fit_fact(op, peers, "personal_item", "cmp_personal", lang, S)
             + _incl_fact(op, airlines, lang, S))
    home = PAGES[lang][1]
    rows = []
    for key, bag, kg in CMP_PRESETS:
        cls, verdict = _bag_verdict(op, bag, S)
        k = sum(1 for o in airlines if _fits(bag, _sorted3(o["cabin_bag"]["max_cm"])))
        allv = (t(S, "cmp_all_all", n=n) if k == n
                else t(S, "cmp_all_none") if k == 0 else t(S, "cmp_all_some", k=k))
        href = f'{home}?l={bag[0]}&amp;w={bag[1]}&amp;h={bag[2]}&amp;kg={kg}'
        rows.append(
            f'        <tr><th scope="row"><a href="{href}">{t(S, key)}</a>'
            f'<span class="cmpx__dims">{bag[0]} × {bag[1]} × {bag[2]} cm</span></th>'
            f'<td><span class="status {cls}">{verdict}</span></td><td class="cmpx__n">{allv}</td></tr>'
        )
    name = esc(op["name"])
    return (
        '  <section class="glass tile--cmpx cmpx" aria-labelledby="cmpx-h">\n'
        f'    <h2 id="cmpx-h">{t(S, "cmp_h", name=name)}</h2>\n'
        f'    <p class="cmpx__lead">{t(S, "cmp_lead", n=n)}</p>\n'
        f'    <ul class="cmpx__facts">\n{facts}    </ul>\n'
        f'    <h3 class="cmpx__h3">{t(S, "cmp_bags_h", name=name)}</h3>\n'
        '    <div class="cmpx__scroll">\n'
        '      <table class="cmpx__tbl">\n'
        f'        <thead><tr><th scope="col">{t(S, "cmp_col_bag")}</th><th scope="col">{t(S, "cmp_col_here", name=name)}</th>'
        f'<th scope="col">{t(S, "cmp_col_all", n=n)}</th></tr></thead>\n'
        '        <tbody>\n' + "\n".join(rows) + '\n        </tbody>\n'
        '      </table>\n'
        '    </div>\n'
        f'    <p class="cmpx__note">{t(S, "cmp_bags_note")}</p>\n'
        '  </section>'
    )


# Textos que necesita la cuenta compartida (partials/verdict.js) en la ficha.
# Se manda solo este subconjunto del diccionario, no las 347 claves.
VERDICT_KEYS = sorted(set(re.findall(r't\("([a-z_]+)"', (SITE_DIR / "partials" / "verdict.js").read_text(encoding="utf-8")))
                      | {"fiche_try_empty"})


def fiche_script_json(value) -> str:
    """JSON seguro dentro de <script>: sin </ ni comentarios HTML."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def fiche_spans(op) -> dict:
    """
    Ancho de las tarjetas de peso y de ruedas en la grilla de la ficha.
    Computadora: 4 columnas; teléfono y tablet: 2. El banner de prohibidos
    ocupa 2 columnas cuando está; peso y ruedas reparten lo que queda.
    """
    has_kg = fiche_kg(op) is not None
    has_banned = False  # 18/10/2026: los prohibidos son una línea a lo ancho
    if has_banned:
        d_kg, d_wh = ("d1", "d1") if has_kg else (None, "d2")
    else:
        d_kg, d_wh = ("d2", "d2") if has_kg else (None, "d4")
    p = "p1" if has_kg else "p2"
    return {"kg": f"span-{d_kg} span-{p}" if has_kg else "",
            "wheels": f"span-{d_wh} span-{p}"}


FICHE_JS = (SITE_DIR / "partials" / "fiche.js").read_text(encoding="utf-8")
# banner de prohibidos con flechas + mantener apretada una flecha ▲▼
NOGO_JS = ((SITE_DIR / "partials" / "nogo.js").read_text(encoding="utf-8")
           + (SITE_DIR / "partials" / "hold.js").read_text(encoding="utf-8"))


def block_banned(lang: str, S: dict, verified_on: str = None, draft: bool = False) -> str:
    """
    Bloque "qué no se puede llevar". Siempre lleva los enlaces oficiales.
    Las fichas con íconos aparecen solo con fecha humana (BANNED_VERIFIED_ON),
    o en una vista previa local marcada BORRADOR que nunca se publica.
    """
    if verified_on is None:
        verified_on = BANNED_VERIFIED_ON.strip()
    if verified_on and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified_on):
        sys.exit("ERROR: BANNED_VERIFIED_ON tiene que ser AAAA-MM-DD o quedar vacío.")
    e = html.escape
    eu_url = t(S, "banned_eu_url")
    links = (
        '      <ul class="banned__links">\n'
        f'        <li><a href="{e(eu_url)}" target="_blank" rel="noopener nofollow">{e(t(S, "banned_eu"))}</a><span>{e(t(S, "banned_eu_note"))}</span></li>\n'
        f'        <li><a href="{BANNED_SOURCE_UK}" target="_blank" rel="noopener nofollow" hreflang="en">{e(t(S, "banned_uk"))}</a><span>{e(t(S, "banned_uk_note"))}</span></li>\n'
        f'        <li><a href="{BANNED_SOURCE_CL}" target="_blank" rel="noopener nofollow" hreflang="es">{e(t(S, "banned_cl"))}</a><span>{e(t(S, "banned_cl_note"))}</span></li>\n'
        f'        <li><a href="{BANNED_SOURCE_CO}" target="_blank" rel="noopener nofollow" hreflang="es">{e(t(S, "banned_co"))}</a><span>{e(t(S, "banned_co_note"))}</span></li>\n'
        f'        <li><a href="{BANNED_SOURCE_MX}" target="_blank" rel="noopener nofollow" hreflang="es">{e(t(S, "banned_mx"))}</a><span>{e(t(S, "banned_mx_note"))}</span></li>\n'
        '      </ul>\n'
        f'      <p class="banned__foot">{e(t(S, "banned_foot"))}</p>\n'
    )
    chev = ('<span class="banned__chev" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 9.5l6 6 6-6" '
            'fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')

    if not verified_on and not draft:
        # Solo enlaces: lo que se publica mientras Marcos no haya verificado las fichas.
        return (
            '  <details class="banned" id="banned">\n'
            '    <summary class="banned__sum">\n'
            '      <span class="banned__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M6 6l12 12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg></span>\n'
            f'      <span class="banned__txt"><b>{e(t(S, "banned_h"))}</b><span class="banned__sub">{e(t(S, "banned_sub"))}</span></span>\n'
            f'      {chev}\n'
            '    </summary>\n'
            '    <div class="banned__body">\n'
            f'      <p>{e(t(S, "banned_p"))}</p>\n'
            f'{links}'
            '    </div>\n'
            '  </details>\n'
        )

    tiles = banned_tiles(S)
    if verified_on:
        stamp = t(S, "nogo_stamp", date=verified_on)
        stamp_html = (f'<a href="{e(eu_url)}" target="_blank" rel="noopener nofollow">{e(t(S, "nogo_source"))}</a> · '
                      f'{e(stamp)}')
    else:
        stamp_html = '<b class="nogo__draft">BORRADOR — sin verificar, no publicar</b>'
    # 11/10/2026: banner chico con flechas (antes, grilla de 6). Las fichas y
    # el sello son los mismos; abajo siguen las fuentes oficiales.
    return (
        '  <section class="banned nogo nogo-c glass" id="banned" aria-labelledby="nogo-h">\n'
        + nogo_carousel(S, lang, "nogo", None, stamp_html=stamp_html) +
        '    <details class="nogo__more">\n'
        f'      <summary class="banned__sum nogo__sum"><span class="banned__txt"><b>{e(t(S, "nogo_more"))}</b></span>{chev}</summary>\n'
        '      <div class="banned__body">\n'
        f'{links}'
        '      </div>\n'
        '    </details>\n'
        '  </section>\n'
    )


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
    last_check = max((o.get("verified_on") or "" for o in ops), default="") or None
    for key, cfg in GUIDE_PAGES.items():
        entry({lang: guide_path(key, lang) for lang in PAGES}, cfg["updated"] or last_check)

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"



# ------------------------------------------------------ marca, cabecera, <head>

def brand_mark(inline: bool = True) -> str:
    """
    El logo en uso, leído de sitio/brand/mark-<BRAND_MARK>.svg.

    inline=True: para la cabecera de cada página. El azul sale de --accent y la
    tinta de currentColor, así el modo noche lo repinta solo.
    inline=False: el favicon.svg, que vive fuera de la página y no ve el CSS
    del sitio; lleva sus colores fijos y su propio modo oscuro.
    """
    path = BRAND_DIR / f"mark-{BRAND_MARK}.svg"
    if not path.exists():
        sys.exit(f"ERROR: falta el logo {path}")
    svg = path.read_text(encoding="utf-8").strip()
    if inline:
        svg = svg.replace("{BLUE}", "var(--accent)").replace("{GRAD}", "wb-grad")
        svg = svg.replace('<svg xmlns="http://www.w3.org/2000/svg"',
                          '<svg class="wordmark__svg" aria-hidden="true" focusable="false"', 1)
        return svg
    svg = svg.replace("{BLUE}", "#1F5EFF").replace("{GRAD}", "g")
    style = ("<style>svg{color:#172033}@media (prefers-color-scheme:dark)"
             "{svg{color:#EEF2F9}}</style>")
    return svg.replace(">", ">" + style, 1)


def block_brand(home_href: str) -> str:
    return (
        f'      <a class="wordmark" href="{home_href}">'
        f'<span class="wordmark__mark">{brand_mark()}</span>'
        f'<span class="wordmark__name">Willitboard</span></a>'
    )


# Cloudflare Web Analytics (01/10/2026). Cuenta visitas sin cookies ni
# almacenamiento local; lo pide el navegador a Cloudflare, que ya es quien aloja
# el sitio, así que no suma ninguna empresa nueva. El token es público (va en el
# HTML de cualquier sitio que lo use). Vacío = el sitio no carga nada.
# La página de privacidad lo describe: si se saca esto, hay que cambiar ese texto.
CF_BEACON_TOKEN = "913c52a0ac4e4b3f9625c4bd93518318"


def cf_beacon() -> list[str]:
    tok = CF_BEACON_TOKEN.strip()
    if not tok:
        return []
    if not re.fullmatch(r"[0-9a-f]{32}", tok):
        sys.exit("ERROR: CF_BEACON_TOKEN tiene que ser 32 caracteres hexadecimales, o quedar vacío.")
    return ["<script defer src=\"https://static.cloudflareinsights.com/beacon.min.js\" "
            f"data-cf-beacon='{{\"token\": \"{tok}\"}}'></script>"]


def adsense_pub_id() -> str:
    """
    El ID de editor de AdSense validado, o "" si todavía no hay cuenta.
    Acepta "pub-…" o "ca-pub-…" (AdSense muestra las dos formas) y devuelve "pub-…".
    """
    pub = ADSENSE_PUB_ID.strip()
    if pub.startswith("ca-"):
        pub = pub[3:]
    if pub and not re.fullmatch(r"pub-\d{16}", pub):
        sys.exit('ERROR: ADSENSE_PUB_ID tiene que ser "pub-" seguido de 16 dígitos, '
                 "o quedar vacío.")
    return pub


def ads_txt_line(pub: str) -> str:
    return f"google.com, {pub}, DIRECT, {ADS_TXT_GOOGLE_ID}"


def attr(text: str) -> str:
    """Para meter un texto YA escapado para HTML dentro de un atributo."""
    return str(text).replace('"', "&quot;")


def head_extra(lang: str, S: dict, canonical: str, title: str, description: str) -> str:
    """
    Favicon, color de la barra del navegador y las etiquetas que usan WhatsApp,
    Facebook, LinkedIn o X para armar la vista previa cuando alguien comparte
    un enlace. Sin esto, un enlace compartido sale como texto pelado.
    """
    image = f"{BASE_URL}/og-{lang}.png"
    pub = adsense_pub_id()
    # Verificación de AdSense (paso 1): una etiqueta inerte, no pide nada a Google.
    adsense = [f'<meta name="google-adsense-account" content="ca-{pub}">'] if pub else []
    return "\n".join(adsense + cf_beacon() + [
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
        '<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
        '<meta name="theme-color" content="#1F5EFF">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Willitboard">',
        f'<meta property="og:locale" content="{t(S, "og_locale")}">',
        f'<meta property="og:title" content="{attr(title)}">',
        f'<meta property="og:description" content="{attr(description)}">',
        f'<meta property="og:url" content="{canonical}">',
        f'<meta property="og:image" content="{image}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        f'<meta property="og:image:alt" content="{attr(t(S, "og_image_alt"))}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ])


def scene_art(name: str) -> str:
    """
    Ilustración de una diapositiva del carrusel, estilo "Volumen" (elegido el
    30/09/2026). Dibujo propio, sin texto de equipaje que haya que verificar:
    las cifras del medidor son decorativas y no se presentan como límite de nadie.
    """
    path = PARTIALS_DIR / f"scene_{name}.svg"
    if not path.exists():
        sys.exit(f"ERROR: falta {path}")
    return path.read_text(encoding="utf-8").strip()


def totop_block(S: dict) -> str:
    """Botón para volver arriba. Aparece después de bajar un poco; sin guardar nada."""
    label = attr(t(S, "totop"))
    return (
        f'<button type="button" class="totop" id="totop" aria-label="{label}" title="{label}" hidden>'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5" fill="none" '
        'stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>\n'
        "<script>\n(function () {\n"
        '  var b = document.getElementById("totop"); if (!b) return;\n'
        "  var busy = false;\n"
        "  function sync() { b.hidden = window.scrollY < 300; busy = false; }\n"
        '  window.addEventListener("scroll", function () { if (!busy) { busy = true; requestAnimationFrame(sync); } }, { passive: true });\n'
        '  b.addEventListener("click", function () {\n'
        '    var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;\n'
        '    window.scrollTo({ top: 0, behavior: calm ? "auto" : "smooth" });\n'
        "  });\n  sync();\n})();\n</script>"
    )


def measure_art(S: dict) -> str:
    """El dibujo de la maleta de frente y de costado, con sus rótulos."""
    path = PARTIALS_DIR / "measure_art.svg"
    if not path.exists():
        sys.exit(f"ERROR: falta {path}")
    svg = path.read_text(encoding="utf-8").rstrip("\n")
    return render(svg, {"m_art_alt": t(S, "m_art_alt"), "m_front": t(S, "m_front"),
                        "m_side": t(S, "m_side")})


def measure_thumb(svg: str) -> str:
    """
    Copia chica del dibujo de cómo medir, para el renglón "Cómo medir la
    maleta" (11/10/2026: el dibujo a la vista en lugar de un ícono). Es
    decorativa: sin título, aria-hidden, y con los id renombrados para no
    chocar con el dibujo grande que está en la misma página.
    """
    ids = re.findall(r'id="([^"]+)"', svg)
    for i in ids:
        svg = svg.replace(f'id="{i}"', f'id="{i}-mini"').replace(f"url(#{i})", f"url(#{i}-mini)")
    svg = re.sub(r"\s*<title[^>]*>.*?</title>", "", svg, flags=re.S)
    svg = re.sub(r'\s(role|aria-labelledby)="[^"]*"', "", svg)
    return svg.replace('class="measure__art"', 'class="measure__mini" aria-hidden="true" focusable="false"', 1)


def copy_static() -> list[Path]:
    """Copia sitio/static/** a public/ y escribe el favicon.svg desde el logo."""
    out = []
    if STATIC_DIR.exists():
        for src in sorted(STATIC_DIR.rglob("*")):
            if src.is_file():
                dst = OUT_DIR / src.relative_to(STATIC_DIR)
                dst.parent.mkdir(parents=True, exist_ok=True)
                data = src.read_bytes()
                if not dst.exists() or dst.read_bytes() != data:
                    dst.write_bytes(data)
                out.append(dst)
    fav = OUT_DIR / "favicon.svg"
    fav.write_text(brand_mark(inline=False) + "\n", encoding="utf-8")
    out.append(fav)
    return out


# ------------------------------------------------------------ guías

def strip_linkable_head(html: str) -> str:
    """
    La 404 se sirve en direcciones que no son suyas. Un canonical, unos hreflang
    o un og:url ahí le dirían a Google que esa dirección rota es una página real.
    Se quitan y se agrega noindex.
    """
    out = []
    for line in html.split("\n"):
        s = line.strip()
        if s.startswith('<link rel="canonical"') or s.startswith('<link rel="alternate"'):
            continue
        if s.startswith('<meta property="og:url"'):
            continue
        out.append(line)
    html = "\n".join(out)
    marker = '<meta name="viewport"'
    i = html.index(marker)
    j = html.index("\n", i)
    return html[: j + 1] + '<meta name="robots" content="noindex">' + html[j:]


def guide_path(key: str, lang: str) -> str:
    return f"/{GUIDE_PAGES[key]['slug'][lang]}/"


def guide_outfile(key: str, lang: str) -> Path:
    return OUT_DIR / GUIDE_PAGES[key]["slug"][lang] / "index.html"


def link_markers(lang: str) -> dict:
    """Enlaces internos que pueden usar los fragmentos de texto."""
    hrefs = {f"HREF_{k.upper()}": legal_path(k, lang) for k in LEGAL_PAGES}
    hrefs.update({f"HREF_{k.upper()}": guide_path(k, lang) for k in GUIDE_PAGES})
    hrefs["CHECKER_HREF"] = PAGES[lang][1]
    hrefs["COMPARE_HREF"] = PAGES[lang][1] + "#compare"
    return hrefs


def load_guide_fragment(key: str, lang: str, S: dict) -> str:
    path = GUIDES_DIR / f"{key}.{lang}.html"
    if not path.exists():
        sys.exit(f"ERROR: falta el contenido {path}")
    fragment = path.read_text(encoding="utf-8").rstrip("\n")
    values = link_markers(lang)
    values["MEASURE_ART"] = measure_art(S)
    unknown = set(re.findall(r"\{\{(\w+)\}\}", fragment)) - set(values)
    if unknown:
        sys.exit(f"ERROR: {path} usa marcadores desconocidos: {', '.join(sorted(unknown))}")
    return render(fragment, values)


def sizes_status(allow: dict, S: dict) -> str:
    included = allow.get("included")
    if included is True:
        return f'<span class="status status--free">{t(S, "status_free")}</span>'
    if included is False:
        return f'<span class="status status--paid">{t(S, "status_paid")}</span>'
    return f'<span class="status status--none">{t(S, "status_unknown")}</span>'


def sizes_cell(op, key: str, S: dict) -> str:
    allow = op.get(key)
    if not isinstance(allow, dict):
        return '<td class="sz__none">—</td>'
    dims = triple(allow.get("max_cm"))
    if not dims:
        return f'<td class="sz__none">{sizes_status(allow, S)}<br>{t(S, "status_unknown")}</td>'
    kg = allow.get("max_kg")
    if kg is not None:
        kg_txt = t(S, "allow_kg", kg=esc(kg))
    elif op.get("combined_max_kg") is not None:
        kg_txt = t(S, "allow_kg_shared", kg=esc(op["combined_max_kg"]))
    else:
        kg_txt = t(S, "cmp_no_kg")
    addon = allow.get("requires_addon")
    addon_html = (f'<span class="sz__addon">{t(S, "flag_addon", addon=esc(addon))}</span>'
                  if allow.get("included") is False and addon else "")
    return (
        f'<td>{sizes_status(allow, S)}'
        f'<span class="sz__dims dims">{esc(" × ".join(str(d) for d in dims))} cm</span>'
        f'<span class="sz__kg">{kg_txt}</span>{addon_html}</td>'
    )


def sizes_wheels(op, S: dict) -> str:
    w = op.get("wheels_handles") or {}
    basis = w.get("included_in_measurement")
    if basis is True:
        return t(S, "wh_included")
    if basis is False:
        tol = w.get("tolerance_cm")
        return t(S, "wh_excluded_tol", tol=esc(tol)) if tol is not None else t(S, "wh_excluded")
    return t(S, "status_unknown")


def block_sizes(ops: list, lang: str, S: dict) -> str:
    """
    La tabla comparativa de medidas. SE GENERA desde operators.json en cada
    build: ninguna cifra se escribe a mano, así que la tabla no puede decir
    algo distinto de las fichas ni del comparador.
    """
    dim = sorted([o for o in ops if o.get("limit_type") == "dimensional"],
                 key=lambda o: o["name"].lower())
    rules = sorted([o for o in ops if o.get("limit_type") != "dimensional"],
                   key=lambda o: (o["type"], o["name"].lower()))
    parts = [f'    <p>{t(S, "sizes_intro")}</p>']

    incl = [o for o in dim if (o.get("cabin_bag") or {}).get("included") is True]
    if incl:
        names = ", ".join(f'<a href="{op_path(o, lang)}">{esc(o["name"])}</a>' for o in incl)
        parts.append(f'    <p class="caveat">{t(S, "sizes_included", names=names)}</p>')
    elif dim:
        parts.append(f'    <p class="caveat">{t(S, "sizes_included_none")}</p>')

    rows = []
    for o in dim:
        fare = o.get("reference_fare")
        fare_html = (f'<small class="sz__fare">{t(S, "sizes_fare", fare=esc(fare))}</small>'
                     if fare else "")
        rows.append(
            "        <tr>\n"
            f'          <th scope="row"><a href="{op_path(o, lang)}">{esc(o["name"])}</a>{fare_html}</th>\n'
            f"          {sizes_cell(o, 'personal_item', S)}\n"
            f"          {sizes_cell(o, 'cabin_bag', S)}\n"
            f"          <td>{sizes_wheels(o, S)}</td>\n"
            f'          <td><a href="{esc(o["source_url"])}" target="_blank" rel="noopener nofollow">'
            f'{t(S, "sizes_source")}</a><br><time datetime="{esc(o["verified_on"])}">{esc(o["verified_on"])}</time></td>\n'
            "        </tr>"
        )
    if rows:
        parts.append(
            '    <div class="sz__scroll">\n'
            '      <table class="sz">\n'
            "        <thead><tr>"
            f'<th scope="col">{t(S, "sizes_col_op")}</th>'
            f'<th scope="col">{t(S, "fiche_label_personal")}</th>'
            f'<th scope="col">{t(S, "fiche_label_cabin")}</th>'
            f'<th scope="col">{t(S, "fiche_wheels_h")}</th>'
            f'<th scope="col">{t(S, "sizes_col_checked")}</th>'
            "</tr></thead>\n"
            "        <tbody>\n" + "\n".join(rows) + "\n        </tbody>\n"
            "      </table>\n"
            "    </div>"
        )
    if rules:
        items = "\n".join(
            f'      <li><a href="{op_path(o, lang)}">{esc(o["name"])}</a> '
            f'<span class="sz__mode">({t(S, "mode_" + o["type"])})</span></li>'
            for o in rules
        )
        parts.append(f'    <h2>{t(S, "sizes_rules_h")}</h2>\n    <p>{t(S, "sizes_rules_p")}</p>\n'
                     f'    <ul class="sz__rules">\n{items}\n    </ul>')
    parts.append(f'    <p class="caveat">{t(S, "caveat_missing")}</p>')
    parts.append(f'    <p class="caveat">{t(S, "p_noguarantee")}</p>')
    parts.append(f'    <p><a class="cta" href="{PAGES[lang][1]}">{t(S, "fiche_cta")}</a></p>')
    return "\n".join(parts)


# ---------------------------------------------------------------------- main

def main() -> None:
    for required in (TEMPLATE, TEMPLATE_OP, TEMPLATE_PAGE, STYLE):
        if not required.exists():
            sys.exit(f"ERROR: falta {required}")
    if not DATASET.exists():
        sys.exit(f"ERROR: falta {DATASET}. Correr convert.py primero.")
    adsense_pub_id()  # un ID mal copiado frena el build antes de escribir nada

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
        spans = fiche_spans(op)
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
                "WHEELS": block_wheels(op, S, spans["wheels"]),
                "KG_TILE": block_kg_tile(op, S, spans["kg"]),
                "BANNED_TILE": block_banned_tile(op, lang, S),
                "TRY": block_try(op, lang, S),
                "COMPARE": block_compare(op, data["operators"], lang, S),
                "COMPARE_HREF": f'{PAGES[lang][1]}?c={op["id"]}#compare',
                "HEAD_MOD": "" if op["limit_type"] == "dimensional" else " tile--head-full",
                "FICHE_JS": FICHE_JS if op["limit_type"] == "dimensional" else "",
                "OP_JSON": fiche_script_json(op) if op["limit_type"] == "dimensional" else "null",
                "FICHE_STRINGS": fiche_script_json({k: S[k] for k in VERDICT_KEYS}),
                "VERDICT_JS": VERDICT_JS.read_text(encoding="utf-8") if op["limit_type"] == "dimensional" else "",
                "NOGO_JS": NOGO_JS if op["limit_type"] == "dimensional" else "",
                "CAVEATS": block_caveats(op, S),
                "CHECKER_HREF": PAGES[lang][1],
                "FICHE_STAMP": t(
                    S, "fiche_stamp",
                    version=esc(data["schema_version"]), date=esc(data["generated_on"]),
                ),
                "FOOTER_LINKS": block_footer_links(lang, S),
                "TOTOP": totop_block(S),
                "BRAND": block_brand(PAGES[lang][1]),
            }
            values["HEAD_EXTRA"] = head_extra(lang, S, values["CANONICAL"],
                                              values["DOC_TITLE"], values["META_DESCRIPTION"])
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
        values["BRAND"] = block_brand(canonical_path)
        values["HEAD_EXTRA"] = head_extra(lang, S, values["CANONICAL"],
                                          S["doc_title"], S["meta_description"])
        for n in range(1, 5):
            values[f"SLIDE_{n}_LABEL"] = t(S, "slide_n", n=n, total=4)
            values[f"SLIDE_{n}_GO"] = t(S, "slide_go", n=n)
        values["MEASURE_ART"] = measure_art(S)
        values["MEASURE_THUMB"] = measure_thumb(values["MEASURE_ART"])
        values["NOGO_JS"] = NOGO_JS
        values["GUIDE_MEASURE_HREF"] = guide_path("measure", lang)
        for key in ("MEASURE", "COMPARE", "TRUST", "SHARE"):
            values["SCENE_" + key] = scene_art(key.lower())
        values["TOTOP"] = totop_block(S)
        values["VERDICT_JS"] = VERDICT_JS.read_text(encoding="utf-8")
        values["BANNED_BLOCK"] = block_banned(lang, S, draft=bool(__import__("os").environ.get("WIB_BANNED_PREVIEW")))
        # guías que también encuentra el buscador de arriba
        values["GUIDE_LINKS"] = json.dumps(
            [{"name": t(S, GUIDE_PAGES[k]["nav"]), "href": guide_path(k, lang)} for k in GUIDE_PAGES],
            ensure_ascii=False)
        values["CMP_INTRO"] = t(S, "cmp_intro", max=3)
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
                "TOTOP": totop_block(S),
                "BRAND": block_brand(PAGES[lang][1]),
            })
            values["HEAD_EXTRA"] = head_extra(lang, S, values["CANONICAL"],
                                              values["DOC_TITLE"], values["META_DESCRIPTION"])
            out = legal_outfile(key, lang)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(template_page, values), encoding="utf-8")
            written.append(out)

    # ---------- guías ----------
    last_check = max((o.get("verified_on") or "" for o in published), default="")
    for key, cfg in GUIDE_PAGES.items():
        for lang in PAGES:
            S = dicts[lang]
            if key == "sizes":
                content = block_sizes(published, lang, S)
                updated = t(S, "sizes_updated", date=esc(last_check))
            else:
                content = load_guide_fragment(key, lang, S)
                updated = t(S, "guide_updated", date=cfg["updated"])
            values = dict(S)
            values.update({
                "STYLE": css,
                "LANG": lang,
                "CANONICAL": BASE_URL + guide_path(key, lang),
                "HREF_EN": BASE_URL + guide_path(key, "en"),
                "HREF_ES": BASE_URL + guide_path(key, "es"),
                "NAV_EN_PATH": guide_path(key, "en"),
                "NAV_ES_PATH": guide_path(key, "es"),
                "NAV_EN_CUR": ' aria-current="page"' if lang == "en" else "",
                "NAV_ES_CUR": ' aria-current="page"' if lang == "es" else "",
                "DOC_TITLE": t(S, f"{key}_title"),
                "META_DESCRIPTION": t(S, f"{key}_meta"),
                "H1": t(S, f"{key}_h1"),
                "STANDFIRST": t(S, f"{key}_standfirst"),
                "CRUMB_SELF": t(S, cfg["nav"]),
                "CONTENT": content,
                "CHECKER_HREF": PAGES[lang][1],
                "PAGE_UPDATED": updated,
                "FOOTER_LINKS": block_footer_links(lang, S, current=key),
                "TOTOP": totop_block(S),
                "BRAND": block_brand(PAGES[lang][1]),
            })
            values["HEAD_EXTRA"] = head_extra(lang, S, values["CANONICAL"],
                                              values["DOC_TITLE"], values["META_DESCRIPTION"])
            out = guide_outfile(key, lang)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render(template_page, values), encoding="utf-8")
            written.append(out)

    # ---------- página 404 ----------
    for lang in PAGES:
        S = dicts[lang]
        home = PAGES[lang][1]
        content = (
            f'    <p>{t(S, "notfound_body")}</p>\n'
            f'    <p><a class="cta" href="{home}">{t(S, "fiche_cta")}</a></p>\n'
            + block_operator_index(published, lang, S)
        )
        values = dict(S)
        values.update({
            "STYLE": css,
            "LANG": lang,
            "CANONICAL": "",
            "HREF_EN": "",
            "HREF_ES": "",
            "NAV_EN_PATH": PAGES["en"][1],
            "NAV_ES_PATH": PAGES["es"][1],
            "NAV_EN_CUR": ' aria-current="page"' if lang == "en" else "",
            "NAV_ES_CUR": ' aria-current="page"' if lang == "es" else "",
            "DOC_TITLE": t(S, "notfound_title"),
            "META_DESCRIPTION": t(S, "notfound_meta"),
            "H1": t(S, "notfound_h1"),
            "STANDFIRST": t(S, "notfound_standfirst"),
            "CRUMB_SELF": t(S, "notfound_crumb"),
            "CONTENT": content,
            "CHECKER_HREF": home,
            "PAGE_UPDATED": "",
            "FOOTER_LINKS": block_footer_links(lang, S),
            "TOTOP": totop_block(S),
            "BRAND": block_brand(home),
        })
        values["HEAD_EXTRA"] = head_extra(lang, S, BASE_URL + home,
                                          values["DOC_TITLE"], values["META_DESCRIPTION"])
        html = strip_linkable_head(render(template_page, values))
        html = html.replace("    <p></p>\n", "")
        out = OUT_DIR / NOT_FOUND_PAGES[lang]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        written.append(out)

    # ---------- archivos estáticos ----------
    written.extend(copy_static())

    # ---------- ads.txt (AdSense, paso 1) ----------
    ads = OUT_DIR / "ads.txt"
    pub = adsense_pub_id()
    if pub:
        ads.write_text(ads_txt_line(pub) + "\n", encoding="utf-8")
        written.append(ads)
    elif ads.exists():
        ads.unlink()

    # ---------- sitemap ----------
    sitemap = OUT_DIR / "sitemap.xml"
    sitemap.write_text(build_sitemap(published), encoding="utf-8")
    written.append(sitemap)

    # ---------- informe ----------
    for path in written:
        rel = path.relative_to(ROOT)
        if rel.parts[:2] == ("public", "fonts"):
            continue
        print(f"  {rel}  ({path.stat().st_size:,} bytes)")

    n_urls = (len(published) + 1 + len(LEGAL_PAGES) + len(GUIDE_PAGES)) * len(PAGES)
    print(
        f"\nOK. {len(dicts['en'])} textos por idioma, {len(dicts)} idiomas, "
        f"{len(published)} de {len(all_ops)} operadores con ficha, "
        f"{len(LEGAL_PAGES)} páginas legales, {len(GUIDE_PAGES)} guías, "
        f"{n_urls} URLs en el sitemap."
    )
    if held:
        print("\nOperadores SIN ficha, por no alcanzar el umbral de publicación:")
        for op, why in held:
            print(f"  {op['id']}: {why}")
    if unused:
        print(f"\nClaves que la home no usa directamente (las usa el JS): {len(unused)}")


if __name__ == "__main__":
    main()
