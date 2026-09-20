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

    willitboard_operadores.xlsx      la fuente de verdad de los DATOS
        └─ convert.py                valida y genera public/operators.json
    sitio/style.css                  el CSS, uno solo para todas las páginas
    sitio/template.html              la home: estructura y lógica del comparador
    sitio/template_operator.html     la ficha por operador
    sitio/i18n/en.json, es.json      los textos de interfaz, uno por idioma
        └─ build_site.py             lee las plantillas Y public/operators.json,
                                     y genera las dos home, una ficha por
                                     operador y por idioma, y el sitemap

**No editar nada dentro de `public/`: se regenera y se pisa.** Para cambiar un
texto se edita el diccionario del idioma; para cambiar la estructura, la plantilla.

    python3 convert.py        # datos -> public/operators.json
    python3 build_site.py     # páginas -> public/ (home, fichas y sitemap.xml)

**El orden importa:** `build_site.py` lee `public/operators.json`, así que
`convert.py` va primero. Si se cargó un operador nuevo y no se corre el conversor,
la ficha no se genera y nada avisa.

`build_site.py` falla a propósito si a un diccionario le falta una clave que el otro
tiene, o si una traducción pierde un marcador como `{dims}`. Así una traducción a
medias no llega a producción disfrazada de texto en inglés.

## Pruebas

    python3 -m unittest pruebas.test_converter   # 24 pruebas del conversor
    python3 pruebas/test_bilingue.py             # 23 comprobaciones de la home
    python3 pruebas/test_fichas.py               # 180 comprobaciones de las fichas

La comprobación central de `test_bilingue`: **el idioma cambia el texto, nunca el
veredicto.** Si un mismo equipaje se clasificara distinto en inglés y en español, falla.

La comprobación central de `test_fichas`: **la cifra que se ve en la ficha es la del
dataset**, comparada carácter por carácter contra `operators.json`. También falla si
una nota interna del campo `notes` se filtra a una página pública, o si una franquicia
sin peso publicado muestra alguna cifra.

## URLs

    /                          comparador, inglés
    /es/                       comparador, español
    /airlines/{id}/            ficha de aerolínea      ↔  /es/aerolineas/{id}/
    /trains/{id}/              ficha de tren           ↔  /es/trenes/{id}/
    /ferries/{id}/             ficha de ferry          ↔  /es/ferris/{id}/
    /sitemap.xml               todas las páginas publicadas

El `{id}` es el id del dataset, igual en los dos idiomas: una sola fuente para el
identificador evita que la URL y el dato se despeguen. Un operador nuevo en la
planilla genera sus dos fichas solo, sin tocar código.

## Despliegue

Cloudflare Worker con assets estáticos. `wrangler.jsonc` publica todo lo que haya
en `public/`. El nombre del Worker tiene que seguir siendo `willitboard`: es el que
tiene enganchado el dominio.
