---
name: actualizar-tendencias-rss
description: Actualiza semanalmente la página /porsche/tendencias de mejorimposible.es con noticias de Porsche extraídas de un feed de Google Alerts (traducidas al español, filtradas por relevancia, con un bloque de resumen semanal), y publica el cambio con commit + push. Úsala para la actualización semanal programada de tendencias, o si el usuario pide "actualiza tendencias", "corre la skill de RSS" o similar.
---

# Actualizar /porsche/tendencias con el feed de Google Alerts

## Contexto

Este repo es el sitio estático de mejorimposible.es (GitHub Pages, rama `main`). El archivo `porsche/tendencias.html` tiene una zona de contenido generada automáticamente por esta skill, delimitada por comentarios marcadores. No toques nada fuera de esas zonas marcadas (cabecera, footer, filtros, el array `newsData` dentro de `<script>`, etc.).

Fuente del feed (Atom de Google Alerts para "Porsche"):
`https://www.google.es/alerts/feeds/05845247816632936990/7384118912035573051`

## Pasos

1. **Descarga el feed en crudo** (es Atom, no RSS 2.0):
   ```
   curl -s -L "https://www.google.es/alerts/feeds/05845247816632936990/7384118912035573051"
   ```
   Cada `<entry>` tiene: `<id>`, `<title type="html">` (con `<b>` alrededor de "Porsche", normalmente en formato "Titular - Fuente"), `<link href="https://www.google.com/url?...&url=<URL_REAL_CODIFICADA>&...">`, `<published>`, `<content type="html">` (snippet, a veces truncado con "...").

2. **Extrae de cada entrada**: el `<id>` (identificador único de la entrada), el titular limpio (sin las etiquetas `<b>`), el nombre de la fuente (lo que va después del último " - " del título, si lo hay), la URL real del artículo (decodifica el parámetro `url=` del enlace de Google, que va URL-encoded), la fecha de `<published>`, y el snippet de `<content>`.

3. **Deduplica contra lo ya publicado**: lee `.claude/state/tendencias-rss-seen.json` (array de `id` de entradas ya usadas en semanas anteriores). Si el archivo no existe o está vacío, trátalo como lista vacía. Descarta cualquier entrada cuyo `<id>` ya esté en ese array.

4. **Filtra por relevancia editorial** (usa tu criterio, no hay lista cerrada de reglas). Quédate solo con noticias que aporten valor real a alguien que se está informando para comprar un Porsche: lanzamientos y novedades de producto, cambios de gama o de precios, análisis o comparativas, movimientos de mercado o de la marca, tecnología, tendencias de compra o de segunda mano.

   Descarta explícitamente: cotilleos de famosos/influencers comprando o recibiendo un Porsche de regalo, resultados o crónicas de motorsport que solo mencionan "Porsche" de pasada, contenido de foros o redes de baja calidad, vídeos sin sustancia informativa más allá del titular, anuncios/inauguraciones/eventos locales de concesionarios o centros Porsche concretos (ese contenido pertenece a la sección de concesionarios del sitio, no a tendencias), clasificados de coches de segunda mano individuales, y cualquier entrada duplicada o casi idéntica a otra que ya hayas elegido esta misma semana.

   Es normal y esperado descartar la mayoría de las entradas del feed — suele venir con mucho ruido.

5. **Traduce y reescribe en español** cada noticia que sobreviva el filtro, aunque el titular o el snippet originales estén en inglés o en otro idioma. Nunca dejes texto en otro idioma en el resultado final. Escribe un titular corto y claro, y un extracto de 1-2 frases en tu propio estilo (no una traducción literal palabra por palabra), citando la fuente original.

6. **Clasifica cada noticia** en una de estas categorías (deben coincidir exactamente, son sensibles a mayúsculas, ya se usan en los botones de filtro de la página): `Lanzamientos` (producto nuevo, anuncios oficiales), `Análisis` (opinión, comparativas, mercado, estrategia de marca), `Modelos` (contenido centrado en un modelo concreto), `Guías` (consejos de compra o de uso). Si una noticia no encaja bien en ninguna, ponla en `Análisis` por defecto.

7. **Elige como máximo 6 noticias** de esta pasada (las más relevantes, si hay más candidatas válidas). Si tras el filtro no queda ninguna noticia con valor real, **no toques el bloque de noticias ni el de resumen esta semana** — termina sin hacer cambios ni commit. No rellenes con contenido de relleno solo por rellenar.

8. **Genera el bloque "Resumen de la semana"**: un párrafo corto (2-3 frases) que sintetice lo más destacado de las noticias elegidas esta semana, más una lista de 3-5 highlights, cada uno enlazando a la noticia correspondiente. Este bloque se **sustituye entero** cada semana (no se acumula con el de semanas anteriores).

9. **Edita `porsche/tendencias.html`**:

   - Sustituye TODO el contenido entre `<!-- RSS-SUMMARY:START -->` y `<!-- RSS-SUMMARY:END -->` por el nuevo resumen semanal, con esta estructura:
     ```html
     <div class="weekly-summary">
         <span class="eyebrow">Resumen de la semana</span>
         <h2>Lo más destacado de esta semana en el mundo Porsche</h2>
         <p>PÁRRAFO DE SÍNTESIS EN ESPAÑOL.</p>
         <ul>
             <li><a href="URL_1" target="_blank" rel="noopener">TITULAR CORTO 1</a> — apunte de una frase.</li>
             <li><a href="URL_2" target="_blank" rel="noopener">TITULAR CORTO 2</a> — apunte de una frase.</li>
         </ul>
     </div>
     ```

   - Dentro de `<!-- RSS-NEWS-CARDS:START -->` ... `<!-- RSS-NEWS-CARDS:END -->`, **añade** (no borres las que ya había) una tarjeta por cada noticia elegida esta semana, insertándolas justo después del marcador de inicio (las más nuevas siempre arriba). Plantilla exacta de cada tarjeta:
     ```html
     <div class="news-card" data-category="CATEGORIA">
         <div class="source">FUENTE</div>
         <h3>TITULAR EN ESPAÑOL</h3>
         <p class="excerpt">EXTRACTO EN ESPAÑOL</p>
         <div class="meta">
             <span>FECHA (formato "DD de Mes, AAAA")</span>
             <a href="URL_REAL_DEL_ARTICULO" target="_blank" rel="noopener" class="read-more-link">Leer más →</a>
         </div>
     </div>
     ```
   - **Miniatura opcional** (`.news-thumb`): el sitio tiene dos carpetas de fotos reales reutilizables, sin problema de derechos porque son del propio sitio:
     - `img/tendencias/` — fotos de ambiente/escena (no genéricas por modelo): `circuito.jfif` (curva de circuito tipo Spa vista desde un coche en marcha), `competicion.jfif` (911 GT3 RS verde en pista mojada), `concesionario.png` (showroom con varios Porsche expuestos), `deportivo.png` (911 GT3 plateado en puerto de montaña), `descapotable-amarillo.jfif` (718 Boxster amarillo en carretera costera), `fabrica.jfif` (línea de montaje/fábrica), `interior.png` (volante y cuadro de instrumentos), `motor.png` (motor en un taller), `noche.jfif` (Panamera de noche en ciudad asiática), `viaje-911.jfif` (911 azul en carretera de montaña), `viaje-taycan.jfif` (Taycan negro en autopista al atardecer).
     - `img/modelo/` — fotos de estudio (fondo neutro), 3 variantes por modelo: `911.jfif`/`9112.jfif`/`9113.jfif`, `718.jfif`/`7182.jfif`/`7183.jfif`, `cayenne.jfif`/`cayenne2.jfif`/`cayenne3.jfif`, `macan.jfif`/`macan2.jfif`/`macan3.jfif`, `panamera.jfif`/`panamera2.jfif`/`panamera3.jfif`, `taycan.jfif`/`taycan2.jfif`/`taycan3.jfif`.
     
     **Úsalo con moderación, no en todas las tarjetas** — solo cuando una de estas fotos encaje de verdad con la noticia (un modelo concreto, una escena de fábrica/concesionario/interior que pegue con el tema). Si ninguna encaja bien, no añadas `.news-thumb` a esa tarjeta — así se evita repetir siempre las mismas fotos o forzar una que no tenga sentido. Cuando sí encaje, insértala como primer hijo de la tarjeta:
     ```html
     <div class="news-card" data-category="CATEGORIA">
         <div class="news-thumb"><img src="/img/tendencias/ARCHIVO" alt="" loading="lazy"></div>
         <div class="source">FUENTE</div>
         ...
     ```
     Nunca reutilices la misma foto en dos tarjetas activas a la vez, y nunca hotlinkees ni descargues imágenes de las webs de origen de las noticias (riesgo de derechos y de enlaces rotos) — la miniatura sale siempre de `img/tendencias/` o `img/modelo/`.
   - Si después de añadir las nuevas tarjetas hay más de 30 en total dentro de esa zona, elimina las más antiguas (las del final) hasta dejar como máximo 30.
   - No toques nada fuera de esas dos zonas marcadas.

10. **Actualiza `.claude/state/tendencias-rss-seen.json`**: añade los `id` de las entradas del feed que hayas usado esta semana (las descartadas por poco relevantes NO hace falta guardarlas, así se pueden reconsiderar si el feed vuelve a traerlas más adelante con más contexto). Si el array supera 300 elementos, elimina los más antiguos del principio.

11. **Actualiza la fecha de modificación en `sitemap.xml`**: busca el bloque `<url>` cuyo `<loc>` sea `https://mejorimposible.es/porsche/tendencias` y pon (o si ya existe, sustituye) su `<lastmod>` por la fecha de hoy en formato `AAAA-MM-DD`, justo después de la etiqueta `<loc>`. No toques ningún otro `<url>` del sitemap. (El workflow de "última hora" también actualiza este mismo `<lastmod>` cada 5 horas; tu cambio semanal simplemente lo deja también al día en el momento de tu actualización.)

12. **Publica el cambio**:
    ```
    git add porsche/tendencias.html sitemap.xml .claude/state/tendencias-rss-seen.json
    git commit -m "Actualiza tendencias con noticias de la semana (RSS)"
    git push
    ```
    Si `git push` falla (conflicto, red, permisos...), deja el commit local hecho, no lo fuerces ni lo reintentes de forma agresiva, e informa claramente del problema en tu resumen final.

## Notas

- Esta skill está pensada para ejecutarse automáticamente cada semana vía una tarea programada, sin supervisión humana en el momento de ejecutarse. También se puede invocar a mano.
- Si el feed no responde, da error, o su formato ha cambiado de forma irreconocible, no toques la página: informa del fallo con el detalle del error y termina sin hacer commit.
- Los enlaces internos a posts del blog dentro de las tarjetas o el resumen deben usar el prefijo `/porsche/` (p. ej. `https://mejorimposible.es/porsche/nombre-del-post`), igual que el resto de URLs internas del sitio tras la migración a esa subcarpeta.
- Idioma de salida: siempre español, sin excepciones, aunque la fuente original esté en otro idioma.
- El tono debe ser coherente con el resto del sitio: directo, informativo, sin relleno artificial.
