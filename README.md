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
    sitio/template_page.html         las páginas de texto (legales y guías)
    sitio/legal/<pagina>.<idioma>.html  el cuerpo de cada página legal
    sitio/guides/<guia>.<idioma>.html   el cuerpo de las guías "cómo medir" y
                                     "sobre Willitboard" (la tabla de medidas
                                     se genera desde el dataset, no tiene archivo)
    sitio/partials/measure_art.svg   el dibujo de cómo medir (frente y costado)
    sitio/brand/mark-a|b|c|d.svg     las cuatro propuestas de logo
    sitio/static/                    se copia tal cual a public/: tipografías
                                     (Fredoka y Nunito, con su licencia OFL),
                                     favicon PNG, ícono del iPhone e imágenes
                                     para compartir en redes
    sitio/i18n/en.json, es.json      los textos de interfaz, uno por idioma
        └─ build_site.py             lee las plantillas Y public/operators.json,
                                     y genera las dos home, una ficha por
                                     operador y por idioma, las guías, las
                                     legales, el favicon.svg y el sitemap

    herramientas/generar_imagenes.py vuelve a dibujar las imágenes de
                                     sitio/static/ (para compartir, favicon PNG,
                                     ícono del iPhone) a partir del logo en uso.
                                     Solo hace falta si cambia el logo.

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

    python3 -m unittest pruebas.test_converter   # 32 pruebas del conversor
    python3 -m unittest pruebas.test_adsense     # 5 pruebas del interruptor de AdSense
    python3 pruebas/test_bilingue.py             # 36 comprobaciones de la home
    python3 pruebas/test_fichas.py               # 290 comprobaciones de fichas, legales y guías
    python3 pruebas/test_diseno.py               # 56 comprobaciones de diseño (móvil, modo noche)
    python3 pruebas/test_interaccion.py          # 70 comprobaciones de interacción
    python3 pruebas/test_v5.py                   # 62 comprobaciones de la home v5 (pestañas,
                                                 # carrusel, grupos, buscador, peso combinado)

Las pruebas con navegador usan Playwright y levantan un servidor local con `public/`:
correr `convert.py` y `build_site.py` antes.

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
    /privacy/                  privacidad             ↔  /es/privacidad/
    /cookies/                  cookies                ↔  /es/cookies/
    /disclosure/               publicidad y afiliados ↔  /es/divulgacion/
    /how-to-measure-luggage/   guía: cómo medir       ↔  /es/como-medir-una-maleta/
    /cabin-bag-sizes/          tabla de medidas       ↔  /es/medidas-equipaje-de-mano/
    /about/                    sobre Willitboard      ↔  /es/sobre-willitboard/
    /sitemap.xml               todas las páginas publicadas
    /ads.txt                   solo si ADSENSE_PUB_ID tiene un valor (ver abajo)

El `{id}` es el id del dataset, igual en los dos idiomas: una sola fuente para el
identificador evita que la URL y el dato se despeguen. Un operador nuevo en la
planilla genera sus dos fichas solo, sin tocar código.

## Despliegue

Cloudflare Worker con assets estáticos. `wrangler.jsonc` publica todo lo que haya
en `public/`. El nombre del Worker tiene que seguir siendo `willitboard`: es el que
tiene enganchado el dominio.

## Páginas de texto

El cuerpo de cada página legal vive en `sitio/legal/<pagina>.<idioma>.html` como
fragmento HTML: son miles de palabras de prosa y meterlas en una cadena JSON las
volvería imposibles de editar y de revisar. La plantilla solo aporta cabecera, pie y
canonical.

**La fecha de "última modificación" está escrita a mano** en `LEGAL_PAGES` de
`build_site.py`, no sale del build. Si se moviera sola en cada regeneración, la página
estaría fingiendo frescura — justo lo que el proyecto no hace con ningún otro dato.
**Al cambiar el texto de una página hay que cambiar su fecha ahí y en
`pruebas/test_fichas.py`**, que la comprueba a propósito.

## Columnas opcionales de la planilla (esquema 1.4)

- `tarifa_referencia` (columna AB): el nombre comercial de la tarifa a la que
  corresponden las cifras, tal como lo escribe el operador ("Basic", "Fly Light").
  Se muestra sin traducir. Vacío = no se muestra nada.
- `peso_combinado_kg` (columna AC): cuando el operador publica un solo peso para
  los dos bultos juntos. La maleta se compara contra ese total; **nunca se reparte**
  entre los bultos, porque esa cifra el operador no la publicó. El conversor
  rechaza la fila si un bulto solo tiene un peso mayor que el total.

Como todo dato, las dos cuentan solo en filas con `verificado_el` puesto por una
persona.

## Logo

`BRAND_MARK` en `build_site.py` elige el logo en uso (`sitio/brand/mark-<letra>.svg`,
hoy la **b**). Para cambiarlo: cambiar la letra, correr
`herramientas/generar_imagenes.py` (redibuja favicon PNG, ícono del iPhone e
imágenes para compartir) y después `build_site.py`.

## AdSense

`ADSENSE_PUB_ID` en `build_site.py`, vacío hoy. Es el **paso 1** (verificar el sitio):
con el ID de editor (`pub-` y 16 dígitos) el build agrega
`<meta name="google-adsense-account">` a todas las páginas y escribe `public/ads.txt`.
Ninguna de las dos cosas carga nada de Google ni instala cookies, así que las
páginas de privacidad y cookies siguen siendo ciertas.

El **paso 2** (el código que muestra anuncios) no está programado a propósito: entra
el día de la aprobación junto con privacidad, cookies y divulgación reescritas,
porque hoy esas páginas prometen "sin cookies y sin publicidad".
`pruebas/test_adsense.py` falla si aparece código de anuncios antes de tiempo.
