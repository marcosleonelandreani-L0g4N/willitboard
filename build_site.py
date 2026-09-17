#!/usr/bin/env python3
"""
build_site.py — genera las páginas de Willitboard desde UNA plantilla y un
diccionario por idioma.

Por qué existe
--------------
Hasta ahora el sitio era un único index.html con los textos incrustados. Para
publicar en dos idiomas sin mantener dos archivos que se van desincronizando,
la fuente de verdad pasa a ser:

    site/template.html   la estructura, el CSS y la lógica (una sola vez)
    site/i18n/en.json    los textos en inglés
    site/i18n/es.json    los textos en español

y este script emite:

    public/index.html      (inglés,  canonical https://willitboard.com/)
    public/es/index.html   (español, canonical https://willitboard.com/es/)

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
4. Ningún dato de equipaje pasa por acá. Medidas, condiciones, citas, fuentes
   y fechas viven en operators.json y las genera convert.py.

Uso:  python3 build_site.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "sitio" / "template.html"
I18N_DIR = ROOT / "sitio" / "i18n"
OUT_DIR = ROOT / "public"

BASE_URL = "https://willitboard.com"

# lang -> (subcarpeta de salida, ruta canónica)
PAGES = {
    "en": ("", "/"),
    "es": ("es", "/es/"),
}

# Las claves que empiezan con "_" son notas para nosotros, no textos.
def is_note(key: str) -> bool:
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


def check_template_keys(template: str, dicts: dict[str, dict]) -> None:
    """Todo {{marcador}} de la plantilla tiene que resolverse."""
    computed = {"LANG", "CANONICAL", "NAV_EN_CUR", "NAV_ES_CUR", "STRINGS_JSON"}
    used = set(re.findall(r"\{\{(\w+)\}\}", template))
    unknown = sorted(used - computed - set(dicts["en"]))
    if unknown:
        sys.exit(
            "ERROR: la plantilla usa marcadores que no existen en el diccionario:\n  "
            + ", ".join(unknown)
        )
    unused = sorted(set(dicts["en"]) - used)
    return unused  # informativo, no es error: muchas claves las usa el JS


def render(template: str, lang: str, strings: dict) -> str:
    subdir, canonical_path = PAGES[lang]
    values = dict(strings)
    values["LANG"] = lang
    values["CANONICAL"] = BASE_URL + canonical_path
    values["NAV_EN_CUR"] = ' aria-current="page"' if lang == "en" else ""
    values["NAV_ES_CUR"] = ' aria-current="page"' if lang == "es" else ""
    # El diccionario entero viaja al JS. ensure_ascii=False para que los
    # acentos y el × salgan como caracteres reales en un archivo UTF-8.
    values["STRINGS_JSON"] = json.dumps(strings, ensure_ascii=False, indent=2)

    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            sys.exit(f"ERROR: marcador sin valor: {{{{{key}}}}}")
        return values[key]

    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def main() -> None:
    if not TEMPLATE.exists():
        sys.exit(f"ERROR: falta la plantilla {TEMPLATE}")
    template = TEMPLATE.read_text(encoding="utf-8")

    dicts = {lang: load_strings(lang) for lang in PAGES}
    check_key_parity(dicts)
    check_placeholders(dicts)
    unused = check_template_keys(template, dicts)

    for lang, (subdir, canonical_path) in PAGES.items():
        out_dir = OUT_DIR / subdir if subdir else OUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        html = render(template, lang, dicts[lang])
        out_file.write_text(html, encoding="utf-8")
        rel = out_file.relative_to(ROOT)
        print(f"  {rel}  ({len(html.encode('utf-8')):,} bytes)  ->  {BASE_URL}{canonical_path}")

    print(f"\nOK. {len(dicts['en'])} textos por idioma, {len(dicts)} idiomas.")
    if unused:
        print(f"Claves que la plantilla no usa directamente (las usa el JS): {len(unused)}")


if __name__ == "__main__":
    main()
