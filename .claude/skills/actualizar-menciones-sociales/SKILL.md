---
name: actualizar-menciones-sociales
description: Actualiza la página /porsche/menciones de mejorimposible.es con menciones reales sobre Porsche recogidas de prensa (Google News RSS) y, si hay navegador disponible en la sesión, Reddit. Sustituye los KPIs, el gráfico de sentimiento, el gráfico por fuente, la nube de palabras y el feed de menciones por datos honestos y verificables, con enlace a la fuente original de cada mención. Publica el cambio con commit + push. Úsala para la actualización periódica de menciones sociales, o si el usuario pide "actualiza menciones", "corre la skill de menciones sociales" o similar.
---

# Actualizar /porsche/menciones con datos reales

## Contexto y principio rector

Este repo es el sitio estático de mejorimposible.es (GitHub Pages, rama `main`). `porsche/menciones.html` es un dashboard de "menciones sociales" sobre Porsche.

**Principio innegociable: nunca inventes cifras ni citas.** La versión original de esta página tenía datos 100% ficticios, incluidas citas inventadas atribuidas a cuentas reales (`@SupercarBlondie`, `MotorTrend`...) — eso es un riesgo real de credibilidad y no se debe repetir. Todo lo que aparezca en la página después de ejecutar esta skill debe venir de una fuente real que puedas citar con enlace. Si en una ejecución no consigues suficientes menciones reales para rellenar una sección con solvencia, dejar esa sección en su estado vacío (ver más abajo) es preferible a rellenar con relleno.

No existe una herramienta de "social listening" de pago configurada en este proyecto (nada de Brandwatch/Talkwalker/X API). Por eso las métricas de esta página son deliberadamente modestas y verificables (recuentos reales, no "alcance potencial" o "impresiones" que nadie puede auditar).

La página tiene zonas marcadas con comentarios que delimitan lo que esta skill debe tocar. No edites nada fuera de esas zonas (cabecera, footer, CSS, funciones de renderizado JS, estructura de las secciones):

- `<!-- MENCIONES-META:START -->` ... `<!-- MENCIONES-META:END -->` — línea de metodología/fecha, justo debajo de la cabecera.
- `<!-- MENCIONES-KPI:START -->` ... `<!-- MENCIONES-KPI:END -->` — las 4 tarjetas KPI.
- `// MENCIONES-DATA:START` ... `// MENCIONES-DATA:END` — el objeto `const socialData = {...}` dentro del `<script>` final (comentarios de JS, no de HTML, porque están dentro de un `<script>`). Este bloque se sustituye entero y solo refleja los últimos 7 días.

Además, la página tiene una sección "Histórico de menciones analizadas" que no se edita en el HTML: carga en el navegador el fichero público `porsche/menciones-historico.json` mediante `fetch()`. Ese fichero SÍ lo actualiza esta skill en cada ejecución (ver paso 12b), acumulando entre ejecuciones en vez de sustituirse entero.

## Fuentes

### 1. Google News RSS (siempre disponible, sin API key, vía `curl`)

Endpoint de búsqueda, sin autenticación:
```
https://news.google.com/rss/search?q=<QUERY_URL_ENCODED>&hl=es&gl=ES&ceid=ES:es
```

Usa `when:7d` en la query para limitar a la última semana (o el rango que corresponda si ha pasado más tiempo desde la última ejecución). Lanza varias búsquedas para cubrir el ángulo de "opinión/reacción" (no noticia pura, que ya cubre la skill `actualizar-tendencias-rss`):

```
curl -s -A "Mozilla/5.0 (compatible; mejorimposible-bot/1.0)" "https://news.google.com/rss/search?q=Porsche%20opiniones%20when:7d&hl=es&gl=ES&ceid=ES:es"
curl -s -A "Mozilla/5.0 (compatible; mejorimposible-bot/1.0)" "https://news.google.com/rss/search?q=Porsche%20prueba%20when:7d&hl=es&gl=ES&ceid=ES:es"
curl -s -A "Mozilla/5.0 (compatible; mejorimposible-bot/1.0)" "https://news.google.com/rss/search?q=Porsche%20review%20when:7d&hl=en-US&gl=US&ceid=US:en"
```

Puedes ajustar o añadir queries si lo consideras útil (p. ej. un modelo concreto que esté de actualidad), pero mantén siempre el ángulo de "reacción/opinión/prueba", no lanzamientos oficiales puros (eso es tendencias, no menciones).

Cada `<item>` trae: `<title>` (normalmente "Titular - Medio"), `<link>` (enlace válido de `news.google.com` que redirige al artículo real — no hace falta decodificar nada, úsalo tal cual), `<guid isPermaLink="false">` (identificador único y estable de la entrada), `<pubDate>`, `<description>` (snippet en HTML).

### 2. Reddit (opcional, solo si hay herramientas de navegador en la sesión)

El endpoint JSON público de Reddit (`reddit.com/r/.../search.json`) bloquea peticiones `curl`/sin navegador (devuelve 403). Por eso Reddit **solo se incluye si la sesión tiene disponibles las herramientas `mcp__Claude_Browser__*`**. Si no las tienes disponibles (ejecución desatendida/programada), omite Reddit sin más y sigue solo con Google News — no falles la skill entera por esto, ni avises como si fuera un error grave, es un comportamiento esperado en ejecución desatendida.

Si tienes navegador, visita con `navigate` + `get_page_text`/`read_page`:
```
https://www.reddit.com/r/Porsche/search/?q=Porsche&restrict_sr=1&sort=new&t=week
```
Y opcionalmente 2-3 subreddits más específicos si hay actividad reciente relevante (`r/Taycan`, `r/Cayenne`, `r/911`, `r/Macan`). De cada post extrae: título, autor, subreddit, texto/extracto visible, número de upvotes, número de comentarios, y el enlace permalink (`href` del propio post, conviértelo a absoluto con `https://www.reddit.com` si viene relativo).

## Pasos

1. **Descarga las fuentes** (Google News siempre; Reddit si hay navegador) como se describe arriba.

2. **Parsea cada fuente**:
   - Google News: extrae título, medio (lo que va después del último " - " en el `<title>`), enlace, fecha, snippet, y el `<guid>` como identificador único.
   - Reddit: usa como identificador único el permalink del post (o el id que puedas extraer de la URL, tipo `t3_xxxxx`).

3. **Deduplica** contra `.claude/state/menciones-seen.json` (array de identificadores ya usados en ejecuciones anteriores). Si el archivo no existe o está vacío, trátalo como lista vacía. Descarta cualquier entrada cuyo identificador ya esté en ese array.

4. **Filtra por relevancia editorial** (usa tu criterio). Esta página busca **reacción y opinión real**, no solo noticia — mantén tanto contenido de prensa especializada con opinión (pruebas, comparativas, análisis de mercado) como comentarios genuinos de propietarios/aficionados si vienen de Reddit.

   Descarta explícitamente: notas de prensa institucionales sin opinión, resultados de motorsport sin comentario, contenido publicitario o de concesionarios concretos, clasificados de coches individuales, entradas dedicadas a otra marca que solo mencionan Porsche de pasada, y spam/bots evidentes en Reddit.

   Es normal descartar buena parte de lo recogido. Si tras filtrar no queda contenido suficiente (por ejemplo, menos de 4-5 menciones válidas en total), es preferible hacer una actualización parcial honesta (menos menciones de las habituales) antes que rellenar con contenido flojo. Si no queda prácticamente nada aprovechable, no toques la página esta vez y termina sin commit, explicando por qué.

5. **Clasifica el sentimiento** de cada mención superviviente como `positive`, `negative` o `neutral`, con criterio honesto (no fuerces positividad ni negatividad — si el texto es informativo/neutro, es `neutral`, no lo fuerces a positivo solo porque el marcador de neutral se usa poco).

6. **Traduce y reescribe en español** cada mención que esté en otro idioma (título/extracto). Igual que en `actualizar-tendencias-rss`: nunca dejes texto en otro idioma en el resultado final, y no hagas una traducción literal palabra por palabra, sino una reescritura clara en 1-2 frases.

7. **Calcula los agregados de esta ejecución**:
   - `totalMentions`: nº total de menciones que sobreviven el filtro (Google News + Reddit).
   - `distinctSources`: nº de fuentes distintas entre ellas (cada medio de prensa cuenta como una fuente; cada subreddit cuenta como una fuente).
   - `sentimentCounts`: recuento de `positive` / `negative` / `neutral` sobre el total clasificado.
   - `sentimentNet`: `round((positive - negative) / total * 100)`, expresado en puntos porcentuales (puede ser negativo).
   - `negativeCount`: nº de menciones `negative`.
   - `channels`: objeto `{ "Nombre de la fuente": nº de menciones de esa fuente }`, agregando por medio de prensa o por subreddit (usa el nombre real, p. ej. `"Coches.net"`, `"r/Porsche"`).

8. **Extrae la nube de palabras**: lee los títulos y extractos de todas las menciones elegidas y saca una lista de 10-15 temas/palabras clave recurrentes (modelos, características, adjetivos, problemas mencionados). Asigna a cada uno un valor relativo de 1 a 100 según su frecuencia/relevancia relativa dentro de esta tanda (no acumules con nubes de semanas anteriores, se sustituye entera).

9. **Elige 6-8 menciones destacadas** para el feed, priorizando diversidad: mezcla de fuentes, mezcla de sentimiento (no elijas solo las positivas), y sustancia real (evita elegir dos menciones casi idénticas sobre lo mismo).

10. **Lee el historial** `.claude/state/menciones-history.json` (array de ejecuciones anteriores, más reciente al final; trátalo como `[]` si no existe). Si tiene al menos una entrada, calcula la tendencia de cada KPI frente a la última entrada registrada:
    - **Menciones analizadas**: variación porcentual de `totalMentions` (`▲ N%` si sube, `▼ N%` si baja, `→ Igual` si no cambia). Si el valor anterior era 0, usa `▲ Nuevo`.
    - **Fuentes distintas**: diferencia absoluta (`▲ N` / `▼ N` / `→ Igual`).
    - **Sentimiento neto**: diferencia en puntos porcentuales (`▲ N pts` / `▼ N pts` / `→ Igual`).
    - **Menciones negativas a vigilar**: diferencia absoluta, pero con la semántica invertida porque menos negativas es mejor: si `negativeCount` sube usa la clase `trend-down` (rojo) aunque el texto diga `▲ N`; si baja usa `trend-up` (verde) con `▼ N`; si no cambia, `trend-flat` con `→ Igual`.

    Para los otros tres KPIs, usa `trend-up` (verde) cuando el cambio es un aumento y `trend-down` (rojo) cuando es una bajada; `trend-flat` (gris) si no hay cambio o si es la primera medición (en ese caso el texto es `→ Primera medición`, sin flecha).

11. **Edita `porsche/menciones.html`**:

    - Sustituye el contenido entre `<!-- MENCIONES-META:START -->` y `<!-- MENCIONES-META:END -->` por:
      ```html
      <p class="page-meta">Datos de prensa especializada[ y Reddit, si aplica] de los últimos 7 días · Sentimiento clasificado automáticamente · Actualizado el DD de mes de AAAA.</p>
      ```
      Incluye " y Reddit" solo si esta ejecución ha incluido datos de Reddit.

    - Sustituye el contenido entre `<!-- MENCIONES-KPI:START -->` y `<!-- MENCIONES-KPI:END -->` por las 4 tarjetas con los valores y tendencias calculados en el paso 10, con esta estructura exacta (cambia solo `VALOR`, `CLASE_TREND` y `TEXTO_TREND`):
      ```html
      <div class="card kpi-card"><div class="card-title">Menciones analizadas (7 días)</div><div class="value">VALOR</div><div class="trend CLASE_TREND">TEXTO_TREND</div></div>
      <div class="card kpi-card"><div class="card-title">Fuentes distintas</div><div class="value">VALOR</div><div class="trend CLASE_TREND">TEXTO_TREND</div></div>
      <div class="card kpi-card"><div class="card-title">Sentimiento neto</div><div class="value">VALOR</div><div class="trend CLASE_TREND">TEXTO_TREND</div></div>
      <div class="card kpi-card"><div class="card-title">Menciones negativas a vigilar</div><div class="value">VALOR</div><div class="trend CLASE_TREND">TEXTO_TREND</div></div>
      ```
      El valor de "Sentimiento neto" se escribe como `+N%` o `-N%`. `CLASE_TREND` es una de `trend-up`, `trend-down`, `trend-flat`.

    - Sustituye el contenido entre `// MENCIONES-DATA:START` y `// MENCIONES-DATA:END` por el objeto `socialData` completo con los datos de esta ejecución:
      ```js
      const socialData = {
          sentiment: { positive: N, negative: N, neutral: N },
          channels: { "Fuente A": N, "Fuente B": N },
          mentions: [
              { author: "Nombre o medio", text: "Texto en español, sin HTML.", source: "Nombre de la fuente", url: "https://enlace-real-al-articulo-o-post", sentiment: "positive" }
          ],
          wordCloud: [ {key: "Palabra", value: N} ]
      };
      ```
      Importante: el texto de `text`, `author` y `source` se inserta luego en el HTML mediante una función que ya escapa entidades (`escapeHtml`), así que no necesitas escapar tú mismo el HTML — pero sí debes escribir cadenas JS válidas (usa comillas dobles y escapa las comillas dobles internas con `\"`, o usa comillas simples si el texto no las contiene). No incluyas markup HTML dentro del texto.

    - No toques nada fuera de esas tres zonas: ni el CSS, ni las funciones de renderizado, ni la cabecera/footer.

12. **Actualiza `.claude/state/menciones-seen.json`**: añade los identificadores usados en esta ejecución (los descartados por poco relevantes no hace falta guardarlos). Si el array supera 500 elementos, elimina los más antiguos del principio.

12b. **Actualiza `porsche/menciones-historico.json`** (fichero público, servido directamente por el sitio y consumido por `fetch()` desde la sección "Histórico de menciones analizadas" de `porsche/menciones.html`): es un array de menciones, más antigua primero, que se **acumula** entre ejecuciones (a diferencia del bloque `socialData`, que se sustituye entero). Si el fichero no existe, trátalo como `[]`.

    Añade al final **todas** las menciones que sobrevivieron el filtro editorial en esta ejecución (todas las que cuentan en `totalMentions`, no solo las 6-8 destacadas para el feed de "últimas menciones"), con este formato exacto por entrada:
    ```json
    { "date": "AAAA-MM-DD", "author": "Nombre o medio", "text": "Texto en español, sin HTML.", "source": "Nombre de la fuente", "url": "https://enlace-real", "sentiment": "positive" }
    ```
    `date` es la fecha de esta ejecución (la misma que va en `MENCIONES-META`). Si el array supera 500 elementos tras añadir los nuevos, elimina los más antiguos del principio para dejarlo en 500 (igual criterio que `menciones-seen.json`).

13. **Actualiza `.claude/state/menciones-history.json`**: añade al final un objeto con `{ "date": "AAAA-MM-DD", "totalMentions": N, "distinctSources": N, "sentimentNet": N, "negativeCount": N }` correspondiente a esta ejecución. Si el array supera 20 entradas, elimina las más antiguas del principio.

14. **Publica el cambio**:
    ```
    git add porsche/menciones.html porsche/menciones-historico.json .claude/state/menciones-seen.json .claude/state/menciones-history.json
    git commit -m "Actualiza menciones sociales de Porsche"
    git push
    ```
    Si `git push` falla, deja el commit local hecho, no lo fuerces, e informa del problema.

15. **Resumen final**: indica cuántas menciones se han incorporado, de qué fuentes (y si Reddit estuvo disponible o no esta vez), el sentimiento neto resultante y su tendencia, cuántas menciones acumula ya el histórico (`porsche/menciones-historico.json`), y si algún centro/fuente destacó por tener menciones negativas relevantes que merezcan atención.

## Notas

- Esta skill puede ejecutarse tanto desatendida (solo Google News, vía cron/schedule) como a mano en una sesión con navegador (Google News + Reddit). Ninguna de las dos formas es un fallo de la otra.
- Si Google News no responde o cambia de formato de forma irreconocible, no toques la página: informa del fallo y termina sin commit.
- Nunca inventes cifras de "alcance" o "impresiones" — si no las puedes verificar con una fuente real, no existen en esta página.
- Los enlaces internos del sitio usan el prefijo `/porsche/` tras la migración a esa subcarpeta.
- Idioma de salida: siempre español.
- Si una misma noticia aparece en varias de las búsquedas de Google News (mismo `<guid>` o mismo enlace real), cuéntala una sola vez.
