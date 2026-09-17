# Willitboard

Herramienta gratuita que responde "¿mi valija entra?" comparando las medidas del
equipaje contra los límites **oficiales** de aerolíneas, trenes y ferries europeos.
En vivo: https://willitboard.com — español en https://willitboard.com/es/

## Regla de datos, no negociable

Ninguna medida, peso, precio ni condición sale de blogs, agregadores ni marcas de
valijas. Solo de la página oficial del operador. El campo `verificado_el` de la
planilla significa que **una persona abrió esa página y confirmó lo que dice**.
Una fila sin fecha se omite del JSON publicado: queda como borrador.

## Cómo se arma el sitio

    willitboard_operadores.xlsx   la fuente de verdad de los datos
        └─ convert.py             valida y genera public/operators.json
    sitio/template.html           estructura, CSS y lógica (una sola vez)
    sitio/i18n/en.json, es.json   los textos de interfaz, uno por idioma
        └─ build_site.py          genera public/index.html y public/es/index.html

**No editar nada dentro de `public/`: se regenera y se pisa.** Para cambiar un
texto se edita el diccionario del idioma; para cambiar la estructura, la plantilla.

    python3 convert.py        # datos  -> public/operators.json
    python3 build_site.py     # textos -> public/index.html y public/es/index.html

`build_site.py` falla a propósito si a un diccionario le falta una clave que el otro
tiene, o si una traducción pierde un marcador como `{dims}`. Así una traducción a
medias no llega a producción disfrazada de texto en inglés.

## Pruebas

    python3 -m unittest pruebas.test_converter   # 24 pruebas del conversor
    python3 pruebas/test_bilingue.py             # 23 comprobaciones en un navegador real

La comprobación central del segundo: **el idioma cambia el texto, nunca el veredicto.**
Si un mismo equipaje se clasificara distinto en inglés y en español, falla.

## Despliegue

Cloudflare Worker con assets estáticos. `wrangler.jsonc` publica todo lo que haya
en `public/`. El nombre del Worker tiene que seguir siendo `willitboard`: es el que
tiene enganchado el dominio.
